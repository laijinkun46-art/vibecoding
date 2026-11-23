"""离线处理已验收的 DEM、逐日降雨和河流；不下载数据或计算洪水。

输入：Phase 0 原始 DEM、WGS84 研究区、原始值 CSV、OSM 中心线。
输出：data/processed/phase2 下的 GeoTIFF/GeoJSON/GeoPackage/CSV/JSON。
"""
import csv
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr
from gis_processing import (NODATA, digest, geometry_mask, save_json, spatial_ref,
                            transform_geometry, valid_pixels, write_grid)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/phase2'
DEM = ROOT / 'data/raw/dem/N22E108_FABDEM_V1-2.tif'
AOI = ROOT / 'data/study_area/nanning_yongjiang_aoi.geojson'
RAIN = ROOT / 'data/processed/chm_pre_v2_nanning_daily_cells.csv'
RIVERS = ROOT / 'data/processed/rivers_osm_current.geojson'
EPSG = 32649  # 南宁在 UTM 49N 分带内；水平单位米，适合课程区距离/坡度计算。


def process_dem(aoi, bbox):
    """保留原始像元裁剪，再生成 30 m 米制分析网格及 Horn 坡度、地形阴影。"""
    west, south, east, north = bbox
    native = gdal.Translate(str(OUT / 'dem_native_clip.tif'), str(DEM),
                            projWin=[west, north, east, south],
                            creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
    native.SetMetadataItem('VERTICAL_DATUM', 'EGM2008 / EPSG:3855; source documentation')
    native.GetRasterBand(1).SetUnitType('m')
    native = None
    # 经纬线投影后为曲线，加密计算区边缘，避免只转换四角形成直线误差。
    dense_aoi = aoi.Clone()
    dense_aoi.Segmentize(.001)
    projected = transform_geometry(dense_aoi, 4326, EPSG)
    xmin, xmax, ymin, ymax = projected.GetEnvelope()
    metric = gdal.Warp(str(OUT / 'dem_utm49n_30m.tif'), str(DEM), dstSRS=f'EPSG:{EPSG}',
                       xRes=30, yRes=30, targetAlignedPixels=True,
                       outputBounds=[xmin, ymin, xmax, ymax],
                       resampleAlg='bilinear', dstNodata=NODATA, outputType=gdal.GDT_Float32,
                       creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
    metric.SetMetadata({'VERTICAL_DATUM': 'EGM2008 / EPSG:3855; heights not converted',
                        'RESAMPLING': 'bilinear, nominal 30 m analysis grid, not increased source accuracy'})
    metric.GetRasterBand(1).SetUnitType('m')
    metric.FlushCache()
    values, valid = valid_pixels(metric)
    aoi_mask = geometry_mask([projected], metric)
    if (aoi_mask.astype(bool) & ~valid).any():
        raise ValueError('研究区内存在 DEM 缺失')
    values[aoi_mask == 0] = NODATA
    metric.GetRasterBand(1).WriteArray(values)
    metric.FlushCache()
    valid = aoi_mask.astype(bool)
    write_grid(OUT / 'aoi_mask.tif', aoi_mask, metric, 255, '1', '1=计算区；0=计算区外')
    for name in ('slope', 'hillshade'):
        options = {'slopeFormat': 'degree', 'alg': 'Horn'} if name == 'slope' else {'azimuth': 315, 'altitude': 45, 'alg': 'Horn'}
        result = gdal.DEMProcessing(str(OUT / f'{name}.tif'), metric, name,
                                    computeEdges=False, creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'], **options)
        result.GetRasterBand(1).SetUnitType('degree' if name == 'slope' else '1')
        result = None
    return metric, {'horizontal_epsg': EPSG, 'vertical_datum': 'EGM2008 / EPSG:3855（未转换）',
                    'grid_size_m': 30, 'shape_rows_cols': list(values.shape),
                    'geotransform': list(metric.GetGeoTransform()), 'nodata': NODATA,
                    'valid_pixels': int(valid.sum()), 'area_by_grid_km2': float(valid.sum() * 900 / 1e6),
                    'elevation_m': {'min': float(values[valid].min()), 'max': float(values[valid].max())},
                    'native_clip': 'dem_native_clip.tif', 'metric_dem': 'dem_utm49n_30m.tif',
                    'slope': 'slope.tif', 'hillshade': 'hillshade.tif',
                    'resampling': '原生裁剪不重采样；UTM 网格双线性，30 m 不代表精度提高',
                    'edge_policy': '坡度/阴影不外推边缘；3×3 邻域含 NoData 时保持 NoData'}


def process_rivers(aoi, metric):
    """裁剪真实线几何并投影；不吸附不相连河流，不虚构河宽或历史岸线。"""
    source = json.loads(RIVERS.read_text(encoding='utf-8'))
    features, projected = [], []
    gpkg_path = OUT / 'rivers_utm49n.gpkg'
    # 仅替换本脚本拥有的派生 GeoPackage，保留原始文件和其他目录。
    driver = ogr.GetDriverByName('GPKG')
    if gpkg_path.exists():
        driver.DeleteDataSource(str(gpkg_path))
    vector = driver.CreateDataSource(str(gpkg_path))
    layer = vector.CreateLayer('rivers', srs=spatial_ref(EPSG), geom_type=ogr.wkbUnknown)
    for field in ('osm_way_id', 'name'):
        layer.CreateField(ogr.FieldDefn(field, ogr.OFTString))
    lengths = []
    main = []
    for item in source['features']:
        geometry = ogr.CreateGeometryFromJson(json.dumps(item['geometry']))
        clipped = geometry.Intersection(aoi)
        if clipped.IsEmpty():
            continue
        if not clipped.IsValid() or clipped.GetDimension() != 1:
            raise ValueError('河流裁剪结果不是有效线几何')
        transformed = transform_geometry(clipped, 4326, EPSG)
        props = dict(item['properties'], length_m=transformed.Length())
        features.append({'type': 'Feature', 'properties': props, 'geometry': json.loads(clipped.ExportToJson())})
        projected.append(transformed)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(transformed)
        for field in ('osm_way_id', 'name'):
            feature.SetField(field, str(props.get(field, '')))
        layer.CreateFeature(feature)
        lengths.append({'name': props.get('name'), 'osm_way_id': props['osm_way_id'], 'length_m': transformed.Length()})
        if props.get('name') == '邕江':
            main.append(transformed)
    vector = None
    if not main:
        raise ValueError('没有找到邕江主河道')
    save_json(OUT / 'rivers_wgs84.geojson', {'type': 'FeatureCollection', 'features': features})
    _, valid = valid_pixels(metric)
    for filename, geometries in [('river_mask.tif', projected), ('main_river_mask.tif', main)]:
        mask = geometry_mask(geometries, metric, all_touched=True)
        mask[~valid] = 0
        write_grid(OUT / filename, mask, metric, 255, '1', '1=中心线触及像元；不是河宽或淹没范围')
    components = []
    pending = list(range(len(projected)))
    while pending:
        group = [pending.pop()]
        for current in group:
            connected = [index for index in pending if projected[current].Intersects(projected[index])]
            group.extend(connected)
            pending = [index for index in pending if index not in connected]
        components.append([lengths[index]['osm_way_id'] for index in group])
    return {'features': lengths, 'components_by_geometric_intersection': components,
            'mask_policy': 'ALL_TOUCHED 栅格化，再限制在有效 DEM 内；仅作后续连通分析候选种子',
            'historical_2024': False, 'source': '© OpenStreetMap contributors / ODbL；Phase 0 当前中心线'}


def process_rainfall(aoi):
    """保持 0.1° 原生格点；按单元与研究区交叠面积计算逐日面平均及累计量。"""
    with RAIN.open(encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    groups = defaultdict(list)
    for row in rows:
        groups[row['date_label']].append(row)
    dates = [(dt.date(2024, 9, 6) + dt.timedelta(days=i)).isoformat() for i in range(8)]
    if sorted(groups) != dates or len(rows) != 48:
        raise ValueError('降雨记录应为连续 8 日、每日 6 个原始格点')
    cells = sorted({(float(row['lon']), float(row['lat'])) for row in rows})
    lons = sorted({cell[0] for cell in cells})
    lats = sorted({cell[1] for cell in cells}, reverse=True)
    weights, cell_features = {}, []
    aoi_area = transform_geometry(aoi, 4326, 6933).GetArea()
    for lon, lat in cells:
        west, east, south, north = lon - .05, lon + .05, lat - .05, lat + .05
        geometry = ogr.CreateGeometryFromWkt(f'POLYGON (({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))')
        clipped = geometry.Intersection(aoi)
        area = transform_geometry(clipped, 4326, 6933).GetArea()
        weights[(lon, lat)] = area / aoi_area
        cell_features.append({'type': 'Feature', 'properties': {'lon': lon, 'lat': lat, 'overlap_area_m2': area,
                              'aoi_weight': weights[(lon, lat)]}, 'geometry': json.loads(geometry.ExportToJson())})
    if not math.isclose(sum(weights.values()), 1, abs_tol=1e-9):
        raise ValueError('降雨原生单元没有完整覆盖研究区')
    save_json(OUT / 'rainfall_cells_wgs84.geojson', {'type': 'FeatureCollection', 'features': cell_features})
    grid = gdal.GetDriverByName('MEM').Create('', len(lons), len(lats), 1, gdal.GDT_Float64)
    grid.SetGeoTransform((min(lons) - .05, .1, 0, max(lats) + .05, 0, -.1))
    grid.SetProjection(spatial_ref(4326).ExportToWkt())
    cumulative = np.zeros((len(lats), len(lons)), dtype=np.float64)
    daily = []
    cumulative_mean = 0.
    for date in dates:
        records = groups[date]
        by_cell = {(float(row['lon']), float(row['lat'])): row for row in records}
        if len(records) != 6 or set(by_cell) != set(cells):
            raise ValueError('降雨格点重复或缺失')
        expected_end = dt.datetime.fromisoformat(date + 'T20:00:00+08:00')
        for row in records:
            if (dt.datetime.fromisoformat(row['interval_end_bjt']) != expected_end or
                    dt.datetime.fromisoformat(row['interval_start_bjt']) != expected_end - dt.timedelta(days=1)):
                raise ValueError('降雨气象日时段错误')
        values = np.array([[float(by_cell[(lon, lat)]['prec_mm_per_day']) for lon in lons] for lat in lats])
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('降雨包含非有限数或负值')
        cumulative += values
        mean = sum(float(row['prec_mm_per_day']) * weights[(float(row['lon']), float(row['lat']))] for row in records)
        cumulative_mean += mean
        daily.append({'date_label': date, 'interval_start_bjt': (expected_end - dt.timedelta(days=1)).isoformat(),
                      'interval_end_bjt': expected_end.isoformat(), 'mean_precip_mm': mean,
                      'cumulative_precip_mm': cumulative_mean, 'min_cell_mm': float(values.min()),
                      'max_cell_mm': float(values.max())})
        write_grid(OUT / f'rainfall_{date}.tif', values, grid, NODATA, 'mm', '原生格点单个24小时累计降雨量')
    write_grid(OUT / 'rainfall_accumulated.tif', cumulative, grid, NODATA, 'mm', '8个气象日累计降雨量')
    with (OUT / 'rainfall_daily_aoi.csv').open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(daily[0]))
        writer.writeheader()
        writer.writerows(daily)
    result = {'source': 'CHM_PRE V2 / V2.1.1', 'horizontal_epsg_assumption': 4326,
              'grid_degree': .1, 'resampling': 'none', 'weight_area_epsg': 6933,
              'aoi_area_m2_equal_area': aoi_area, 'weight_sum': sum(weights.values()),
              'daily': daily, 'total_precip_mm': cumulative_mean,
              'units': '原始 mm/day；每条记录覆盖完整24小时，累计量按 mm 解释',
              'limitations': '格点估计的研究区面平均；不是站点实测或上游流域降雨，不推导洪水水位'}
    save_json(OUT / 'rainfall_timeseries.json', result)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {str(path.relative_to(ROOT)): digest(path) for path in (DEM, AOI, RAIN, RIVERS)}
    collection = json.loads(AOI.read_text(encoding='utf-8'))
    feature = collection['features'][0]
    aoi = ogr.CreateGeometryFromJson(json.dumps(feature['geometry']))
    metric, dem = process_dem(aoi, feature['properties']['bbox_wsen'])
    river = process_rivers(aoi, metric)
    rain = process_rainfall(aoi)
    metric = None
    if any(digest(ROOT / path) != value for path, value in sources.items()):
        raise RuntimeError('输入文件在处理期间发生变化')
    outputs = {str(path.relative_to(ROOT)): {'bytes': path.stat().st_size, 'sha256': digest(path)}
               for path in sorted(OUT.iterdir()) if path.is_file()}
    report = {'phase': 2, 'processed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'runtime': {'gdal': gdal.VersionInfo(), 'numpy': np.__version__},
              'source_sha256': sources, 'inputs_unchanged': True, 'outputs': outputs,
              'dem': dem, 'rivers': river, 'rainfall': rain,
              'vertical_datum_limit': '没有可信水位基准换算；后续情景水位必须明确为与 DEM 一致的 EGM2008 高程，不将报道水位直接代入',
              'phase_boundary': '本阶段仅处理数据；未计算淹没、未接入 Cesium 地形或降雨图层'}
    save_json(ROOT / 'docs/phase2_processing.json', report)
    print(json.dumps({'outputs': len(outputs), 'dem': dem, 'total_rainfall_mm': rain['total_precip_mm'],
                      'river_components': river['components_by_geometric_intersection']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
