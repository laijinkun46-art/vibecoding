"""用可手算微型地形及真实输出不变量检验洪水情景算法。"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.gis.flood import connected_inundation, detect_change, inundation_statistics
from gis_processing import digest, geometry_mask, save_json, transform_geometry, valid_pixels


class FloodAlgorithmTests(unittest.TestCase):
    def test_barrier_and_isolated_depression(self):
        dem = np.zeros((5, 7))
        dem[:, 3] = 9
        seeds = np.zeros(dem.shape, bool)
        seeds[2, 1] = True
        wet, depth = connected_inundation(dem, np.ones(dem.shape, bool), seeds, 5)
        self.assertEqual(wet.sum(), 15)
        self.assertFalse(wet[:, 4:].any())
        self.assertTrue(np.all(depth[:, :3] == 5))

    def test_four_vs_eight_neighbors(self):
        dem = np.array([[0, 9], [9, 0]])
        valid = np.ones((2, 2), bool)
        seeds = np.array([[1, 0], [0, 0]], bool)
        self.assertEqual(connected_inundation(dem, valid, seeds, 5, 4)[0].sum(), 1)
        self.assertEqual(connected_inundation(dem, valid, seeds, 5, 8)[0].sum(), 2)

    def test_nodata_blocks_flow(self):
        dem = np.zeros((3, 3))
        valid = np.ones((3, 3), bool)
        valid[:, 1] = False
        seeds = np.zeros((3, 3), bool)
        seeds[1, 0] = True
        wet, depth = connected_inundation(dem, valid, seeds, 1)
        self.assertEqual(wet.sum(), 3)
        self.assertTrue(np.all(depth[:, 1] == -9999))
        self.assertTrue(np.all(depth[:, 2] == 0))

    def test_equal_elevation_is_dry(self):
        wet, depth = connected_inundation(np.full((2, 2), 5), np.ones((2, 2), bool), np.ones((2, 2), bool), 5)
        self.assertFalse(wet.any())
        self.assertTrue(np.all(depth == 0))

    def test_no_valid_seed_is_error(self):
        with self.assertRaises(ValueError):
            connected_inundation(np.zeros((2, 2)), np.ones((2, 2), bool), np.zeros((2, 2), bool), 5)

    def test_invalid_shapes(self):
        with self.assertRaises(ValueError):
            connected_inundation(np.zeros((2, 2)), np.ones((3, 2), bool), np.ones((2, 2), bool), 5)

    def test_invalid_level_and_dem(self):
        for level in [np.nan, np.inf]:
            with self.assertRaises(ValueError):
                connected_inundation(np.zeros((2, 2)), np.ones((2, 2), bool), np.ones((2, 2), bool), level)
        with self.assertRaises(ValueError):
            connected_inundation(np.full((2, 2), np.nan), np.ones((2, 2), bool), np.ones((2, 2), bool), 5)

    def test_invalid_connectivity(self):
        with self.assertRaises(ValueError):
            connected_inundation(np.zeros((2, 2)), np.ones((2, 2), bool), np.ones((2, 2), bool), 5, 6)

    def test_depth_and_volume_by_hand(self):
        wet = np.array([[1, 1], [1, 0]], bool)
        stats = inundation_statistics(wet, np.array([[1, 2], [3, 0]]), 6)
        self.assertEqual(stats['wet_pixels'], 3)
        self.assertEqual(stats['area_km2'], 18/1e6)
        self.assertEqual(stats['mean_depth_m'], 2)
        self.assertEqual(stats['max_depth_m'], 3)
        self.assertEqual(stats['water_column_volume_m3'], 36)

    def test_empty_stats(self):
        stats = inundation_statistics(np.zeros((2, 2), bool), np.zeros((2, 2)), 900)
        self.assertEqual(stats['area_km2'], 0)
        self.assertEqual(stats['mean_depth_m'], 0)

    def test_all_change_classes(self):
        before = np.array([[1, 1], [0, 0]], bool)
        after = np.array([[1, 0], [1, 0]], bool)
        valid = np.ones((2, 2), bool)
        np.testing.assert_array_equal(detect_change(before, after, valid), [[2, 3], [1, 0]])
        valid[1, 1] = False
        self.assertEqual(detect_change(before, after, valid)[1, 1], 255)

    def test_change_outside_valid_is_error(self):
        with self.assertRaises(ValueError):
            detect_change(np.ones((2, 2), bool), np.zeros((2, 2), bool), np.zeros((2, 2), bool))


def verify_real_outputs():
    folder = ROOT / 'data/processed/phase3'
    report = json.loads((ROOT / 'docs/phase3_processing.json').read_text(encoding='utf-8'))
    summary = report['summary']
    checks = []
    def check(name, passed):
        if not bool(passed):
            raise AssertionError(name)
        checks.append({'name': name, 'passed': True})
    check('所有分析输入哈希未改变', all(digest(ROOT/path) == value for path, value in report['source_sha256'].items()))
    check('所有成果哈希一致', all(digest(ROOT/path) == value['sha256'] for path, value in report['outputs'].items()))
    dem_ds = gdal.Open(str(ROOT / 'data/processed/phase2/dem_utm49n_30m.tif'))
    dem, valid = valid_pixels(dem_ds)
    seeds = gdal.Open(str(ROOT / 'data/processed/phase2/main_river_mask.tif')).ReadAsArray() == 1
    gt = dem_ds.GetGeoTransform()
    masks = {}
    for item in summary['scenarios']:
        sid, level = item['id'], item['water_level_m']
        raster = gdal.Open(str(folder / f'{sid}_wet.tif'))
        depth_ds = gdal.Open(str(folder / f'{sid}_depth.tif'))
        classes, depth = raster.ReadAsArray(), depth_ds.ReadAsArray()
        wet = classes == 1
        masks[sid] = wet
        check(sid+' 分类及水深与DEM同网格', all(ds.GetGeoTransform() == gt and ds.GetProjection() == dem_ds.GetProjection() and
              ds.RasterXSize == dem_ds.RasterXSize and ds.RasterYSize == dem_ds.RasterYSize for ds in (raster, depth_ds)))
        check(sid+' 无效区分类255且水深-9999', np.array_equal(classes == 255, ~valid) and np.all(depth[~valid] == -9999))
        check(sid+' 所有湿像元严格低于假设水面', np.all(dem[wet] < level) and not (wet & ~valid).any())
        check(sid+' 干地水深0、湿区水深=水位减DEM', np.all(depth[valid & ~wet] == 0) and np.array_equal(depth[wet], level-dem[wet]))
        check(sid+' 所有合格主河道种子都被纳入', np.all(wet[seeds & valid & (dem < level)]))
        # 若任何合格干像元四邻域接触湿区，说明搜索未闭合。
        pad = np.pad(wet, 1)
        adjacent = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
        check(sid+' 连通搜索已闭合', not (adjacent & valid & (dem < level) & ~wet).any())
        check(sid+' 面积水深及体积统计独立核对', item['wet_pixels'] == int(wet.sum()) and
              abs(item['area_km2']-wet.sum()*.0009) < 1e-9 and abs(item['mean_depth_m']-depth[wet].mean()) < 1e-9 and
              abs(item['water_column_volume_m3']-depth[wet].sum()*900) < 1e-5)
        data = json.loads((folder / f'{sid}_wet.geojson').read_text(encoding='utf-8'))
        geometries = [transform_geometry(ogr.CreateGeometryFromJson(json.dumps(feature['geometry'])), 4326, 32649) for feature in data['features']]
        check(sid+' 矢量几何有效且栅格回写完全一致', all(geometry.IsValid() for geometry in geometries) and
              np.array_equal(geometry_mask(geometries, dem_ds).astype(bool), wet))
        check(sid+' 矢量面积与像元面积一致', abs(sum(feature['properties']['area_km2'] for feature in data['features'])-item['area_km2']) < 1e-8)
        # 每个四邻域湿区矢量组件均须包含至少一个源种子，排除独立湿岛。
        check(sid+' 每个湿区组件均与主河道种子相交', all((geometry_mask([geometry], dem_ds).astype(bool) & seeds).any() for geometry in geometries))
    ordered = sorted(summary['scenarios'], key=lambda item: item['water_level_m'])
    check('提高水位时湿区单调包含', all(not (masks[a['id']] & ~masks[b['id']]).any() for a, b in zip(ordered, ordered[1:])))
    for item in summary['comparisons']:
        name = item['id']
        ds = gdal.Open(str(folder / f'{name}_change.tif'))
        values = ds.ReadAsArray()
        before, after = masks[item['before']], masks[item['after']]
        check(name+' 变化分类与布尔集合运算一致', np.array_equal(values == 1, ~before & after) and
              np.array_equal(values == 2, before & after) and np.array_equal(values == 3, before & ~after) and
              np.array_equal(values == 255, ~valid))
        check(name+' 前后面积守恒', int(before.sum()) == item['persistent_pixels']+item['receded_pixels'] and
              int(after.sum()) == item['persistent_pixels']+item['added_pixels'])
        check(name+' 净面积变化与两期面积差一致', abs(item['net_area_change_km2']-(int(after.sum())-int(before.sum()))*.0009) < 1e-8)
        vector = json.loads((folder / f'{name}_change.geojson').read_text(encoding='utf-8'))
        check(name+' 变化几何有效且各类面积一致', all(ogr.CreateGeometryFromJson(json.dumps(feature['geometry'])).IsValid() for feature in vector['features']) and
              all(abs(sum(feature['properties']['area_km2'] for feature in vector['features'] if feature['properties']['category'] == code)-item[f'{label}_area_km2']) < 1e-8
                  for code, label in [(1, 'added'), (2, 'persistent'), (3, 'receded')]))
    return checks


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FloodAlgorithmTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    checks = verify_real_outputs()
    save_json(ROOT / 'docs/phase3_checks.json', {'passed': True, 'synthetic_tests': result.testsRun,
              'real_data_checks': len(checks), 'checks': checks})
    print(json.dumps({'passed': True, 'synthetic_tests': result.testsRun, 'real_data_checks': len(checks)}, ensure_ascii=False))
