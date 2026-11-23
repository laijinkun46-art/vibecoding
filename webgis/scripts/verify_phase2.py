"""离线验收 Phase 2 成果：源像元、单位、空间对齐、时序及已知平面坡度。"""
import csv
import json
from collections import deque

import numpy as np
from osgeo import gdal, ogr, osr
from phase2_process import ROOT, OUT, DEM, RAIN, AOI
from gis_processing import digest, save_json, valid_pixels


def run_checks():
    report = json.loads((ROOT / 'docs/phase2_processing.json').read_text(encoding='utf-8'))
    checks = []

    def check(name, condition):
        if not bool(condition):
            raise AssertionError(name)
        checks.append({'name': name, 'passed': True})

    check('四个输入文件 SHA256 未改变', all(digest(ROOT / path) == value for path, value in report['source_sha256'].items()))
    check('全部派生文件 SHA256 一致', all(digest(ROOT / path) == value['sha256'] for path, value in report['outputs'].items()))
    raw = gdal.Open(str(DEM))
    native = gdal.Open(str(OUT / 'dem_native_clip.tif'))
    rgt, ngt = raw.GetGeoTransform(), native.GetGeoTransform()
    xoff = round((ngt[0] - rgt[0]) / rgt[1])
    yoff = round((ngt[3] - rgt[3]) / rgt[5])
    check('原生 DEM 裁剪与源像元逐值一致', np.array_equal(native.ReadAsArray(), raw.ReadAsArray(xoff, yoff, native.RasterXSize, native.RasterYSize)))
    dem = gdal.Open(str(OUT / 'dem_utm49n_30m.tif'))
    heights, valid = valid_pixels(dem)
    check('分析网格 EPSG:32649、30 m 且为米制', dem.GetSpatialRef().GetAuthorityCode(None) == '32649' and dem.GetGeoTransform()[1::4] == (30., -30.))
    mask = gdal.Open(str(OUT / 'aoi_mask.tif')).ReadAsArray()
    check('DEM 有效范围等于研究区栅格掩膜', np.array_equal(valid, mask == 1))
    phase0 = json.loads((ROOT / 'docs/phase0_validation.json').read_text(encoding='utf-8'))
    check('栅格面积与 Phase 0 边界面积差小于 0.2%', abs(valid.sum() * .0009 / phase0['aoi']['area_km2'] - 1) < .002)
    for filename in ('slope.tif', 'hillshade.tif', 'aoi_mask.tif', 'river_mask.tif', 'main_river_mask.tif'):
        item = gdal.Open(str(OUT / filename))
        check(filename + ' 与 DEM 网格完全对齐', item.GetGeoTransform() == dem.GetGeoTransform() and
              item.GetProjection() == dem.GetProjection() and item.RasterXSize == dem.RasterXSize and item.RasterYSize == dem.RasterYSize)
        values, meaningful = valid_pixels(item)
        if filename == 'slope.tif':
            check('坡度范围为 0—90° 且不向 NoData 区域外推', np.all((values[meaningful] >= 0) & (values[meaningful] <= 90)) and not (meaningful & ~valid).any())
        if 'river_mask' in filename:
            check(filename + ' 非空且严格位于有效地形内', np.any(values == 1) and not ((values == 1) & ~valid).any())
    main_mask = gdal.Open(str(OUT / 'main_river_mask.tif')).ReadAsArray() == 1
    unseen = set(map(tuple, np.argwhere(main_mask)))
    components = 0
    while unseen:
        queue = deque([unseen.pop()])
        components += 1
        while queue:
            y, x = queue.popleft()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    pixel = (y + dy, x + dx)
                    if pixel in unseen:
                        unseen.remove(pixel)
                        queue.append(pixel)
    check('邕江种子像元为单个八邻域连通分量', components == 1)
    # 用解析解核对坡度单位，坡面 z=0.1x+0.2y；这些是测试输入，不是历史数据。
    flat = gdal.GetDriverByName('MEM').Create('', 7, 7, 1, gdal.GDT_Float32)
    flat.SetGeoTransform((0, 30, 0, 210, 0, -30))
    flat.SetProjection(dem.GetProjection())
    yy, xx = np.indices((7, 7))
    flat.GetRasterBand(1).WriteArray(xx * 3. - yy * 6.)
    slope = gdal.DEMProcessing('', flat, 'slope', format='MEM', slopeFormat='degree', alg='Horn')
    check('已知解析坡面验证 Horn 坡度与米制单位', np.allclose(slope.ReadAsArray()[1:-1, 1:-1], np.degrees(np.arctan(np.sqrt(.05))), atol=1e-5))
    flat.GetRasterBand(1).Fill(100)
    slope = gdal.DEMProcessing('', flat, 'slope', format='MEM', slopeFormat='degree', alg='Horn')
    check('平坦地形坡度为零', np.all(slope.ReadAsArray()[1:-1, 1:-1] == 0))
    with RAIN.open(encoding='utf-8-sig', newline='') as stream:
        records = list(csv.DictReader(stream))
    timeseries = json.loads((OUT / 'rainfall_timeseries.json').read_text(encoding='utf-8'))
    cells = json.loads((OUT / 'rainfall_cells_wgs84.geojson').read_text(encoding='utf-8'))['features']
    weights = {(item['properties']['lon'], item['properties']['lat']): item['properties']['aoi_weight'] for item in cells}
    # 6933 是等积圆柱投影；矩形面积可由转换后对角点差值独立核对。
    from pyproj import Transformer
    transform = Transformer.from_crs(4326, 6933, always_xy=True)
    bbox = json.loads(AOI.read_text(encoding='utf-8'))['features'][0]['properties']['bbox_wsen']
    west, south, east, north = bbox
    def rectangle_area(w, s, e, n):
        x0, y0 = transform.transform(w, s)
        x1, y1 = transform.transform(e, n)
        return (x1 - x0) * (y1 - y0)
    for lon, lat in weights:
        expected = rectangle_area(max(west, lon-.05), max(south, lat-.05), min(east, lon+.05), min(north, lat+.05)) / rectangle_area(*bbox)
        check(f'降雨单元 {lon},{lat} 面积权重独立复核', abs(weights[(lon, lat)] - expected) < 1e-10)
    check('六个降雨单元权重和为一', abs(sum(weights.values()) - 1) < 1e-9)
    total_grid = np.zeros((2, 3))
    total_mean = 0.
    for index, entry in enumerate(timeseries['daily']):
        current = [row for row in records if row['date_label'] == entry['date_label']]
        raster = gdal.Open(str(OUT / f"rainfall_{entry['date_label']}.tif"))
        expected = np.array([float(row['prec_mm_per_day']) for row in sorted(current, key=lambda row: (-float(row['lat']), float(row['lon']))) ]).reshape(2, 3)
        check(entry['date_label'] + ' 保留六个源格点原值与地理位置', np.array_equal(expected, raster.ReadAsArray()) and np.allclose(raster.GetGeoTransform(), (108.2, .1, 0, 22.9, 0, -.1)))
        mean = sum(float(row['prec_mm_per_day']) * weights[(float(row['lon']), float(row['lat']))] for row in current)
        total_mean += mean
        total_grid += expected
        check(entry['date_label'] + ' 日均量和累计量一致', abs(mean - entry['mean_precip_mm']) < 1e-10 and abs(total_mean-entry['cumulative_precip_mm']) < 1e-10)
    check('八日累计栅格逐像元等于逐日之和', np.array_equal(total_grid, gdal.Open(str(OUT / 'rainfall_accumulated.tif')).ReadAsArray()))
    check('累计面平均量等于逐日面平均之和', abs(total_mean-timeseries['total_precip_mm']) < 1e-10)
    rivers = ogr.Open(str(OUT / 'rivers_utm49n.gpkg'))
    layer = rivers.GetLayer(0)
    check('投影河流文件可回读且为有效线几何', layer.GetSpatialRef().GetAuthorityCode(None) == '32649' and
          layer.GetFeatureCount() == 2 and all(feature.GetGeometryRef().IsValid() and feature.GetGeometryRef().GetDimension() == 1 for feature in layer))
    save_json(ROOT / 'docs/phase2_checks.json', {'passed': True, 'check_count': len(checks), 'checks': checks})
    print(json.dumps({'passed': True, 'checks': len(checks), 'main_river_components': components}, ensure_ascii=False))


if __name__ == '__main__':
    run_checks()
