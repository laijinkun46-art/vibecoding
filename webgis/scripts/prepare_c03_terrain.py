"""Phase 4.1.2：从已确认的 C03 裁剪原网格并复核剖面。"""
import csv
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

if os.name == 'nt':
    gdal_bin = Path('D:/Arcgis10.8.2/bin')
    gdal_dlls = os.add_dll_directory(str(gdal_bin)) if gdal_bin.is_dir() else None

import numpy as np
from osgeo import gdal, ogr, osr

from gis_processing import digest, geometry_mask, spatial_ref, valid_pixels

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / 'data/processed/hydrodynamics/preparation'
OUT = PREP / 'terrain_c03'
SOURCE = ROOT / 'data/processed/phase2/dem_utm49n_30m.tif'
DOMAIN = PREP / 'domain/candidate_model_domains.gpkg'
CANDIDATES = PREP / 'domain/domain_candidates.json'
PROFILES = PREP / 'domain/river_profile.csv'
MASK = ROOT / 'data/processed/phase2/aoi_mask.tif'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def elevation_stats(values):
    require(values.size > 0, '高程统计没有有效样本')
    low, p10, median, p90, high = np.percentile(values, [0, 10, 50, 90, 100])
    return dict(count=int(values.size), min_m=float(low), p10_m=float(p10),
                median_m=float(median), p90_m=float(p90), max_m=float(high))


def verify_profiles(values, valid, domain_mask, gt, interval):
    """用原网格逐点复核 C03 的既有纵横剖面及端界、侧界样点。"""
    groups = defaultdict(list)
    with PROFILES.open(encoding='utf-8-sig', newline='') as file:
        for item in csv.DictReader(file):
            kind = item['profile_kind']
            chainage = float(item['chainage_m'])
            if kind == 'longitudinal':
                if not interval[0] <= chainage <= interval[1]:
                    continue
            elif item['candidate_id'] != 'C03':
                continue
            x, y = float(item['easting_m']), float(item['northing_m'])
            col, row = int(np.floor((x - gt[0]) / 30)), int(np.floor((gt[3] - y) / 30))
            require(0 <= row < values.shape[0] and 0 <= col < values.shape[1],
                    '剖面样点不在源网格范围内')
            require((row, col) == (int(item['raster_row']), int(item['raster_col']))
                    and item['sample_method'] == 'containing_pixel'
                    and item['vertical_datum'] == 'EGM2008' and item['is_measured_bed'] == '0'
                    and item['valid'] == '1' and valid[row, col]
                    and float(item['dem_elevation_m']) == float(values[row, col]),
                    f"剖面与源 DEM 不一致：{item['profile_id']}")
            groups[(kind, item['profile_id'])].append((float(values[row, col]), bool(domain_mask[row, col])))
    expected = {'longitudinal': 1, 'cross_section': 3, 'boundary': 2, 'lateral_edge': 2}
    require({kind: sum(k == kind for k, _ in groups) for kind in expected} == expected,
            'C03 既有剖面数量不完整')
    return [dict(kind=kind, profile_id=pid, source_elevation=elevation_stats(np.array([z for z, _ in samples])),
                 samples_in_local_dem=sum(in_domain for _, in_domain in samples))
            for (kind, pid), samples in groups.items()]


def adjacent_gradients(values, inside, gt):
    """统计 30 m 正交相邻像元高差，用最大值定位人工核查对象。"""
    pairs = []
    for dy, dx in [(0, 1), (1, 0)]:
        first = (slice(0, -dy or None), slice(0, -dx or None))
        second = (slice(dy, None), slice(dx, None))
        good = inside[first] & inside[second]
        delta = np.abs(values[first] - values[second])
        rows, cols = np.nonzero(good)
        pair_index = int(np.argmax(delta[good]))
        row, col = int(rows[pair_index]), int(cols[pair_index])
        pairs.append((delta[good], row, col, dy, dx))
    combined = np.concatenate([item[0] for item in pairs])
    _, row, col, dy, dx = max(pairs, key=lambda item: item[0].max())
    to_wgs = osr.CoordinateTransformation(spatial_ref(32649), spatial_ref(4326))
    locations = []
    for r, c in [(row, col), (row + dy, col + dx)]:
        x, y = gt[0] + (c + .5) * 30, gt[3] - (r + .5) * 30
        locations.append(dict(utm=[x, y], lon_lat=list(to_wgs.TransformPoint(x, y)[:2]),
                              elevation_m=float(values[r, c])))
    return dict(absolute_difference=elevation_stats(combined),
                diagnostic_threshold_m=10, pairs_at_or_above_threshold=int((combined >= 10).sum()),
                maximum_pair=locations)


def main():
    if OUT.resolve() != OUT or OUT.exists():
        raise FileExistsError(f'局部地形目录已存在或指向其他位置：{OUT}')
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in (SOURCE, MASK, DOMAIN, CANDIDATES, PROFILES)}
    manifest = json.loads(CANDIDATES.read_text(encoding='utf-8'))
    for name in (SOURCE, MASK):
        key = str(name.relative_to(ROOT))
        require(hashes[key] == manifest['source_sha256'][key], f'输入指纹不一致：{key}')
    for name in (DOMAIN, PROFILES):
        require(hashes[str(name.relative_to(ROOT))] == manifest['outputs_sha256'][name.name],
                f'候选成果指纹不一致：{name.name}')
    candidate = next(item for item in manifest['candidates'] if item['id'] == 'C03')
    source = gdal.Open(str(SOURCE), gdal.GA_ReadOnly)
    mask_ds = gdal.Open(str(MASK), gdal.GA_ReadOnly)
    geo = ogr.Open(str(DOMAIN), 0)
    layer = geo.GetLayerByName('candidate_domains')
    layer.SetAttributeFilter("candidate_id = 'C03'")
    require(layer.GetFeatureCount() == 1 and layer.GetSpatialRef().IsSame(source.GetSpatialRef()),
            'C03 几何或坐标参考系不唯一或不一致')
    feature = layer.GetNextFeature()
    polygon = feature.GetGeometryRef().Clone()
    require(polygon.IsValid() and not polygon.IsEmpty(), 'C03 几何无效')
    values, valid = valid_pixels(source)
    gt = source.GetGeoTransform()
    band = source.GetRasterBand(1)
    datum = source.GetMetadataItem('VERTICAL_DATUM')
    nodata = band.GetNoDataValue()
    require(source.GetSpatialRef().GetAuthorityCode(None) == '32649'
            and (gt[1], gt[2], gt[4], gt[5]) == (30, 0, 0, -30)
            and datum and 'EGM2008' in datum and band.GetUnitType() == 'm' and nodata is not None,
            '源 DEM 的坐标、网格、高程基准或单位与既有约定不一致')
    require(mask_ds.GetGeoTransform() == gt and mask_ds.GetSpatialRef().IsSame(source.GetSpatialRef())
            and np.array_equal(mask_ds.ReadAsArray() == 1, valid), '源 DEM 有效范围与 AOI 掩膜不一致')
    touched = geometry_mask([polygon], source, all_touched=True).astype(bool)
    inside = geometry_mask([polygon], source).astype(bool)
    require(np.all(valid[touched]) and np.all(touched[inside])
            and int(touched.sum()) == candidate['dem_coverage']['touched_pixels'],
            'C03 有缺测或覆盖口径与此前验收不一致')
    rows, cols = np.nonzero(inside)
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    c0, c1 = int(cols.min()), int(cols.max()) + 1
    local_mask = inside[r0:r1, c0:c1]
    local = np.where(local_mask, values[r0:r1, c0:c1], nodata).astype(values.dtype, copy=False)
    local_gt = (gt[0] + c0 * 30, 30, 0, gt[3] - r0 * 30, 0, -30)
    profiles = verify_profiles(values, valid, inside, gt, candidate['chainage_interval_m'])
    stats = adjacent_gradients(local, local_mask, local_gt)
    keys = ('id', 'area_km2', 'bounds_utm_wsen', 'chainage_interval_m', 'main_river_length_m')
    info = {
        'phase': '4.1.2',
        'domain_selection': {'selected_candidate': 'C03', 'extent_adjusted': False,
                             'confirmed_by': 'user', 'confirmation_text': '确认', 'date_bjt': '2026-11-24',
                             'candidate_geometry': {k: candidate[k] for k in keys}},
        'horizontal_crs': 'EPSG:32649',
        'source_vertical_datum': datum,
        'vertical_transform_applied': False,
        'pixel_selection': '像元中心入域。触及边界但中心在域外的像元只参与源覆盖核查。',
        'nodata': nodata,
        'grid_shape_rows_cols': list(local.shape),
        'geotransform': list(local_gt),
        'source_window_col_row_width_height': [c0, r0, c1 - c0, r1 - r0],
        'valid_touched_source_pixels': int(touched.sum()),
        'inside_missing_pixels': int((inside & ~valid).sum()),
        'outside_domain_nodata_pixels_in_window': int((~local_mask).sum()),
        'surface_elevation': elevation_stats(local[local_mask]),
        'adjacent_cell_diagnostics': stats,
        'profile_checks': profiles,
        'source_sha256': hashes,
        'script_sha256': digest(Path(__file__)),
        'bathymetry_modified': False,
        'flow_direction_confirmed': False,
    }
    with tempfile.TemporaryDirectory(prefix='c03-terrain-', dir=PREP) as staged:
        ready = Path(staged) / 'ready'
        ready.mkdir()
        path = ready / 'c03_dem_utm49n_30m.tif'
        height, width = local.shape
        ds = gdal.GetDriverByName('GTiff').Create(str(path), width, height, 1, band.DataType,
                                                 options=['COMPRESS=DEFLATE', 'TILED=YES'])
        ds.SetGeoTransform(local_gt)
        ds.SetProjection(source.GetProjection())
        ds.SetMetadata(source.GetMetadata())
        ds.SetMetadataItem('DOMAIN_MASK', 'C03 polygon, pixel-center inclusion')
        output_band = ds.GetRasterBand(1)
        output_band.SetNoDataValue(nodata)
        output_band.SetUnitType('m')
        output_band.SetDescription('C03 FABDEM surface elevation, masked source grid')
        output_band.WriteArray(local)
        output_band = None
        ds.Close()
        with gdal.Open(str(path), gdal.GA_ReadOnly) as check:
            reread = check.GetRasterBand(1)
            require(check.GetGeoTransform() == local_gt and check.GetProjection() == source.GetProjection()
                    and check.GetMetadataItem('VERTICAL_DATUM') == datum and reread.GetUnitType() == 'm'
                    and reread.GetNoDataValue() == nodata and reread.DataType == band.DataType
                    and np.array_equal(reread.ReadAsArray(), local), '输出 DEM 回读不一致')
            reread = None
        info['dem_sha256'] = digest(path)
        require(all(digest(ROOT / p) == h for p, h in hashes.items()), '源文件在执行期间变化')
        info['verified_readback'] = True
        text = json.dumps(info, ensure_ascii=False, indent=2, allow_nan=False)
        (ready / 'terrain_review.json').write_text(text + '\n', encoding='utf-8')
        if OUT.exists():
            raise FileExistsError(OUT)
        ready.rename(OUT)
    print(json.dumps(info, ensure_ascii=True))


if __name__ == '__main__':
    main()
