"""离线执行指定水位情景并输出水深、范围、两期变化和统计；不修改原始数据。"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.gis.flood import DEPTH_NODATA, connected_inundation, detect_change, inundation_statistics
from gis_processing import digest, save_json, transform_geometry, valid_pixels, write_grid

INPUT = ROOT / 'data/processed/phase2'
OUT = ROOT / 'data/processed/phase3'
CONFIG = ROOT / 'data/scenarios/flood_scenarios.json'


def polygonize_classes(path, classes, reference, labels, extra):
    """分类栅格转WGS84多边形，只保留非零有效类别；输出面积采用原投影几何。"""
    source = gdal.GetDriverByName('MEM').Create('', reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Byte)
    source.SetGeoTransform(reference.GetGeoTransform())
    source.SetProjection(reference.GetProjection())
    source.GetRasterBand(1).WriteArray(classes)
    mask = gdal.GetDriverByName('MEM').Create('', reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Byte)
    mask.GetRasterBand(1).WriteArray(((classes > 0) & (classes < 255)).astype(np.uint8))
    vector = ogr.GetDriverByName('MEM').CreateDataSource('')
    layer = vector.CreateLayer('polygons', srs=reference.GetSpatialRef(), geom_type=ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn('class', ogr.OFTInteger))
    # 四邻域矢量化避免对角接触产生自交多边形；与本轮四邻域分析一致。
    gdal.Polygonize(source.GetRasterBand(1), mask.GetRasterBand(1), layer, 0)
    features = []
    for feature in layer:
        code = feature.GetField('class')
        geometry = feature.GetGeometryRef()
        if not geometry.IsValid():
            raise ValueError('矢量化生成无效几何')
        props = dict(extra, category=code, category_label=labels[code], area_km2=geometry.GetArea()/1e6)
        features.append({'type': 'Feature', 'properties': props,
                         'geometry': json.loads(transform_geometry(geometry, 32649, 4326).ExportToJson())})
    save_json(path, {'type': 'FeatureCollection', 'features': features})
    return len(features)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_files = [INPUT / 'dem_utm49n_30m.tif', INPUT / 'main_river_mask.tif', CONFIG]
    sources = {str(path.relative_to(ROOT)): digest(path) for path in source_files}
    previous = json.loads((ROOT / 'docs/phase2_processing.json').read_text(encoding='utf-8'))
    for path in source_files[:2]:
        if digest(path) != previous['outputs'][str(path.relative_to(ROOT))]['sha256']:
            raise ValueError('Phase 2 输入与已验收清单不一致')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if config['vertical_datum'] != 'EGM2008' or config['rainfall_to_stage_model'] is not None:
        raise ValueError('情景必须使用DEM一致的EGM2008基准，且不得绑定未经验证的降雨水位模型')
    reference = gdal.Open(str(source_files[0]))
    seed_ds = gdal.Open(str(source_files[1]))
    if (reference.GetProjection() != seed_ds.GetProjection() or reference.GetGeoTransform() != seed_ds.GetGeoTransform()
            or reference.RasterXSize != seed_ds.RasterXSize or reference.RasterYSize != seed_ds.RasterYSize):
        raise ValueError('DEM与主河道种子网格不一致')
    if reference.GetSpatialRef().GetAuthorityCode(None) != '32649' or 'EGM2008' not in reference.GetMetadata().get('VERTICAL_DATUM', ''):
        raise ValueError('分析坐标或源高程基准不符合约定')
    dem, valid = valid_pixels(reference)
    seeds = seed_ds.ReadAsArray() == 1
    gt = reference.GetGeoTransform()
    area = abs(gt[1]*gt[5]-gt[2]*gt[4])
    scenarios, masks, summaries = {}, {}, []
    for item in config['scenarios']:
        sid = item['id']
        if not sid.isalnum() or sid in scenarios:
            raise ValueError('情景ID必须唯一且只含字母数字')
        wet, depth = connected_inundation(dem, valid, seeds, item['water_level_m'], config['connectivity'])
        masks[sid] = wet
        classes = np.full(dem.shape, 255, dtype=np.uint8)
        classes[valid] = wet[valid]
        stats = inundation_statistics(wet, depth, area)
        stats.update(item)
        stats['eligible_seed_pixels'] = int((seeds & valid & (dem < item['water_level_m'])).sum())
        stats['isolated_low_pixels_excluded'] = int((valid & (dem < item['water_level_m']) & ~wet).sum())
        padded = np.pad(valid, 1, constant_values=False)
        boundary = ~(padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:])
        stats['touches_analysis_boundary'] = bool((wet & boundary).any())
        write_grid(OUT / f'{sid}_wet.tif', classes, reference, 255, '1', '0干地、1情景淹没、255无效')
        write_grid(OUT / f'{sid}_depth.tif', depth, reference, DEPTH_NODATA, 'm', '假设水位减DEM；干地0，无效-9999')
        stats['polygon_count'] = polygonize_classes(OUT / f'{sid}_wet.geojson', classes, reference, {1: '情景淹没'},
                                                    {'scenario_id': sid, 'water_level_m': item['water_level_m'], 'kind': 'hypothetical_scenario'})
        scenarios[sid] = stats
        summaries.append(stats)
    changes = []
    for before, after in config['comparisons']:
        classes = detect_change(masks[before], masks[after], valid)
        name = f'{before}_to_{after}'
        stats = {'id': name, 'before': before, 'after': after}
        for code, label in [(1, 'added'), (2, 'persistent'), (3, 'receded')]:
            stats[f'{label}_pixels'] = int((classes == code).sum())
            stats[f'{label}_area_km2'] = float((classes == code).sum()*area/1e6)
        stats['net_area_change_km2'] = stats['added_area_km2']-stats['receded_area_km2']
        write_grid(OUT / f'{name}_change.tif', classes, reference, 255, '1', '0均干、1新增、2持续、3退水、255无效')
        stats['polygon_count'] = polygonize_classes(OUT / f'{name}_change.geojson', classes, reference,
                        {1: '新增情景淹没', 2: '持续情景淹没', 3: '情景退水'}, {'comparison_id': name, 'kind': 'hypothetical_scenario'})
        changes.append(stats)
    with (OUT / 'scenario_statistics.csv').open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    with (OUT / 'change_statistics.csv').open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(changes[0]))
        writer.writeheader()
        writer.writerows(changes)
    summary = {'kind': 'hypothetical_scenario_not_observation', 'vertical_datum': 'EGM2008',
               'connectivity': config['connectivity'], 'cell_area_m2_projected': area, 'horizontal_epsg': 32649,
               'scenarios': summaries, 'comparisons': changes,
               'rainfall_relationship': '历史降雨作为事件背景；没有降雨到水位的率定模型，情景水位独立指定且不绑定历史日期',
               'area_definition': 'UTM网格的全部连通湿像元面积，包含现有河道，不等于河道外受灾陆地面积',
               'limitations': ['静态等水位，不含流速、沿程水面坡降或洪水到达时间', 'DEM不含可靠水下河床、精细堤防或闸门',
                              '默认四邻域，NoData为不可穿越边界，范围外来水未知', '回落情景从头计算，不模拟滞水或退水历时',
                              '体积为静态水柱几何量，不是流量或来水量', '全部数值仅为课程假设情景，不代表2024实测或预报']}
    save_json(OUT / 'summary.json', summary)
    if any(digest(ROOT/path) != checksum for path, checksum in sources.items()):
        raise ValueError('分析输入在处理期间发生变化')
    outputs = {str(path.relative_to(ROOT)): {'bytes': path.stat().st_size, 'sha256': digest(path)}
               for path in sorted(OUT.iterdir()) if path.is_file()}
    save_json(ROOT / 'docs/phase3_processing.json', {'phase': 3, 'processed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'inputs_unchanged': True, 'source_sha256': sources, 'outputs': outputs, 'summary': summary})
    print(json.dumps({'scenarios': summaries, 'changes': changes, 'outputs': len(outputs)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
