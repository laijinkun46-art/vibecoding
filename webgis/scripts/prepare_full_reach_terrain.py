"""形成全河段计算域和地形索引，直接引用现有 Phase 2 栅格。"""
import csv
import json
import math
import os
import tempfile
from collections import Counter
from itertools import groupby
from pathlib import Path

if os.name == 'nt':
    gis_bin = Path('D:/Arcgis10.8.2/bin')
    dll_directory = os.add_dll_directory(str(gis_bin)) if gis_bin.is_dir() else None

import numpy as np
from osgeo import gdal, ogr, osr
from scipy.ndimage import binary_propagation, label
from shapely import wkb
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring, unary_union

from gis_processing import digest, geometry_mask, spatial_ref, transform_geometry, valid_pixels

ROOT = Path(__file__).resolve().parents[1]
PHASE2 = ROOT / 'data/processed/phase2'
PREP = ROOT / 'data/processed/hydrodynamics/preparation'
OUT = PREP / 'full_reach_v1'
AOI = ROOT / 'data/study_area/nanning_yongjiang_aoi.geojson'
DEM = PHASE2 / 'dem_utm49n_30m.tif'
MASK = PHASE2 / 'aoi_mask.tif'
SEED = PHASE2 / 'main_river_mask.tif'
RIVERS = PHASE2 / 'rivers_utm49n.gpkg'
PROFILE = PREP / 'domain/river_profile.csv'
EPSG = 32649
THRESHOLDS = (75, 80, 85)
TOL = .001


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def shape(geometry):
    return wkb.loads(bytes(geometry.ExportToWkb()))


def ogr_geometry(geometry):
    return ogr.CreateGeometryFromWkb(geometry.wkb)


def domain_geometry():
    """由 AOI 四边构造共用投影坐标的周界与多边形。"""
    with ogr.Open(str(AOI), 0) as ds:
        layer = ds.GetLayer()
        require(layer.GetFeatureCount() == 1 and layer.GetSpatialRef().IsSame(spatial_ref(4326)),
                'AOI 应为单一 WGS84 要素')
        feature = layer.GetNextFeature()
        geom = feature.GetGeometryRef().Clone()
    w, e, s, n = geom.GetEnvelope()
    require(shape(geom).equals(Polygon([(w, s), (e, s), (e, n), (w, n)])), '当前 AOI 不是预期的矩形')
    corners = {'S': [(w, s), (e, s)], 'E': [(e, s), (e, n)],
               'N': [(w, n), (e, n)], 'W': [(w, s), (w, n)]}
    edges = {}
    for name, coords in corners.items():
        line = ogr_geometry(LineString(coords))
        line.Segmentize(.001)
        edges[name] = shape(transform_geometry(line, 4326, EPSG))
    ring = []
    for name in ('S', 'E', 'N', 'W'):
        coords = list(edges[name].coords)
        ring.extend((coords if name in ('S', 'E') else coords[::-1])[:-1])
    domain = Polygon(ring)
    geom.Segmentize(.001)
    direct = shape(transform_geometry(geom, 4326, EPSG))
    require(domain.is_valid and domain.symmetric_difference(direct).area < .01, '投影后的 AOI 不一致')
    return domain, edges


def read_rivers():
    with ogr.Open(str(RIVERS), 0) as ds:
        layer = ds.GetLayerByName('rivers')
        require(layer.GetSpatialRef().IsSame(spatial_ref(EPSG)), '河线 CRS 不符')
        features = [(f.GetField('name'), shape(f.GetGeometryRef())) for f in layer]
    mains = [g for name, g in features if name == '邕江']
    require(len(mains) == 1, '邕江主线不唯一')
    main = mains[0]
    require(main.geom_type == 'LineString' and main.is_valid and main.is_simple, '邕江主线几何无效')
    if main.coords[0][0] > main.coords[-1][0]:
        main = LineString(list(main.coords)[::-1])
    return main, [(name, g) for name, g in features if name != '邕江']


class Surface:
    """读取 Phase 2 原网格，缺测返回空值。"""
    def __init__(self, dataset):
        self.values, self.valid = valid_pixels(dataset)
        self.gt = dataset.GetGeoTransform()

    def sample(self, point):
        col = math.floor((point.x - self.gt[0]) / self.gt[1])
        row = math.floor((self.gt[3] - point.y) / -self.gt[5])
        height, width = self.values.shape
        if 0 <= row < height and 0 <= col < width and self.valid[row, col]:
            return float(self.values[row, col]), row, col
        return None


def terminal_records(main, edges, surface, to_wgs):
    """保持原河线，端点图层投影到对应的 AOI 边线。"""
    terminals = {}
    for side, station, direction, role in [
        ('W', 0.0, 1, 'assumed_inlet_option'), ('E', main.length, -1, 'assumed_outlet_option')
    ]:
        source = main.interpolate(station)
        edge_station = edges[side].project(source)
        point = edges[side].interpolate(edge_station)
        require(point.distance(source) < TOL, f'{side} 端未到达对应 AOI 边缘')
        exact = surface.sample(source)
        support, sample, offset = source, exact, 0
        if sample is None:
            for offset in range(5, 46, 5):
                support = main.interpolate(station + direction * offset)
                sample = surface.sample(support)
                if sample is not None:
                    break
        require(sample is not None, f'{side} 端缺少有效的沿河内侧支持点')
        lon, lat, _ = to_wgs.TransformPoint(point.x, point.y)
        attrs = dict(terminal_id=f'YONGJIANG_{side}', side=side, scenario_role=role,
                     flow_confirmed=0, boundary_type='unassigned',
                     line_chainage_m=station, side_chainage_m=edge_station,
                     lon=lon, lat=lat, source_gap_m=point.distance(source),
                     exact_z_m=None if exact is None else exact[0],
                     support_z_m=sample[0], support_x=support.x, support_y=support.y,
                     pixel_row=sample[1], pixel_col=sample[2], line_inset_m=offset,
                     support_method='line_inward_valid_pixel' if offset else 'phase2_containing_pixel')
        terminals[side] = (point, attrs)
    return terminals


def verify_main_profile(main, surface):
    """回用已经提供的全河段纵剖面，逐条确认里程、高程与缺测。"""
    stations, values, missing = [], [], []
    with PROFILE.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.DictReader(source):
            if row['profile_kind'] != 'longitudinal':
                continue
            station = float(row['chainage_m'])
            point = Point(float(row['easting_m']), float(row['northing_m']))
            require(main.interpolate(station).distance(point) < TOL, '纵剖面样点偏离主线')
            sample = surface.sample(point)
            require((sample is not None) == (row['valid'] == '1') and row['is_measured_bed'] == '0',
                    '纵剖面有效标记不一致')
            if sample is None:
                require(row['dem_elevation_m'] == '', '纵剖面缺测应保留空值')
                missing.append(station)
            else:
                require(sample == (float(row['dem_elevation_m']), int(row['raster_row']), int(row['raster_col'])),
                        '纵剖面与 Phase 2 原格网不一致')
                values.append(sample[0])
            stations.append(station)
    require(stations[0] == 0 and abs(stations[-1] - main.length) < TOL
            and all(0 < b - a <= 30.000001 for a, b in zip(stations, stations[1:])), '纵剖面未完整覆盖')
    return dict(path=relative(PROFILE), filter={'profile_kind': 'longitudinal'}, samples=len(stations),
                valid=len(values), missing_chainages_m=missing, min_z_m=min(values), max_z_m=max(values),
                terminal_support_layer='river_terminals', values='surface elevation, not surveyed bathymetry')


def perimeter_data(domain, edges, surface, connected, terminals, to_wgs):
    """采样整条周界，按筛查证据合并连续站点，保持周界完整。"""
    segments, rows = [], []
    for side, edge in edges.items():
        cuts = np.linspace(0, edge.length, math.ceil(edge.length / 30) + 1)
        samples = []
        for i, (start, end) in enumerate(zip(cuts, cuts[1:])):
            distance = float((start + end) / 2)
            p = edge.interpolate(distance)
            before, after = edge.interpolate(distance - 1), edge.interpolate(distance + 1)
            dx, dy = after.x - before.x, after.y - before.y
            scale = math.hypot(dx, dy)
            # S/E 沿 AOI 环逆时针，N/W 的站号采用相反方向。
            sign = 1 if side in ('S', 'E') else -1
            nx, ny = sign * -dy / scale, sign * dx / scale
            inner = Point(p.x + nx * 45, p.y + ny * 45)
            low = surface.sample(inner)
            require(domain.covers(inner) and low is not None, f'{side} 内缘超出 DEM 有效范围')
            base = surface.sample(p)
            support_point, support, inset = p, base, 0
            if support is None:
                for inset in range(5, 46, 5):
                    support_point = Point(p.x + nx * inset, p.y + ny * inset)
                    if domain.covers(support_point):
                        support = surface.sample(support_point)
                        if support is not None:
                            break
            require(support is not None, f'{side} 精确边缘缺少域内支持点')
            low_z, low_row, low_col = low
            lon, lat, _ = to_wgs.TransformPoint(p.x, p.y)
            samples.append(dict(side=side, segment_id='', side_chainage_m=distance,
                                x=p.x, y=p.y, lon=lon, lat=lat,
                                exact_z_m=None if base is None else base[0],
                                support_z_m=support[0], support_inset_m=inset,
                                support_method='inward_valid_pixel' if inset else 'phase2_containing_pixel',
                                support_x=support_point.x, support_y=support_point.y,
                                support_row=support[1], support_col=support[2],
                                inner_x=inner.x, inner_y=inner.y, inner_z_m=low_z,
                                inner_row=low_row, inner_col=low_col,
                                **{f'linked_le{z}': int(connected[z][low_row, low_col]) for z in THRESHOLDS}))
        classes = []
        for row in samples:
            category = 'unclassified_review'
            if row['linked_le80']:
                category = 'lateral_connected_low80'
            elif row['linked_le85']:
                category = 'lateral_connected_low85'
            elif row['inner_z_m'] <= 85:
                category = 'low_ground_connection_unconfirmed'
            classes.append(category)
        terminal = terminals.get(side)
        if terminal:
            center = terminal[1]['side_chainage_m']
            index = max(0, min(len(samples) - 1, int(np.searchsorted(cuts, center, side='right') - 1)))
            require(samples[index]['linked_le75'], f'{side} 端缺少连续的低地筛查证据')
            lo, hi = index, index + 1
            while lo and samples[lo - 1]['linked_le75']:
                lo -= 1
            while hi < len(samples) and samples[hi]['linked_le75']:
                hi += 1
            classes[lo:hi] = ['river_end_candidate'] * (hi - lo)
        i = 0
        for index, (category, members) in enumerate(groupby(classes), 1):
            j = i + sum(1 for _ in members)
            segment_id = f'{side}{index:03d}'
            segment = substring(edge, float(cuts[i]), float(cuts[j]))
            batch = samples[i:j]
            for row in batch:
                row['segment_id'] = segment_id
            attrs = dict(segment_id=segment_id, side=side, review_class=category,
                         boundary_type='unassigned', from_m=float(cuts[i]), to_m=float(cuts[j]),
                         length_m=segment.length, inner_min_z_m=min(row['inner_z_m'] for row in batch),
                         sample_count=len(batch), terminal_id=terminal[1]['terminal_id']
                         if category == 'river_end_candidate' else None)
            segments.append((segment, attrs))
            i = j
        rows.extend(samples)
    return segments, rows


def verify_perimeter(domain, segments, terminals):
    """端边线覆盖且无重叠，两个端点各落在对应候选段。"""
    lines = [g for g, _ in segments]
    combined = unary_union(lines)
    require(domain.boundary.difference(combined.buffer(TOL)).length < TOL
            and combined.difference(domain.boundary.buffer(TOL)).length < TOL
            and abs(sum(x.length for x in lines) - combined.length) < TOL, '周界有遗漏或重叠')
    for point, terminal in terminals.values():
        matches = [g for g, a in segments if a['terminal_id'] == terminal['terminal_id']]
        require(len(matches) == 1 and matches[0].distance(point) < TOL, '河道端点没有对应候选端界')


def write_layer(dataset, name, geom_type, items):
    layer = dataset.CreateLayer(name, spatial_ref(EPSG), geom_type)
    sample = items[0][1]
    for key in sample:
        # 可空字段在端点或边界记录中依然采用其固定字段类型。
        first_value = next((a[key] for _, a in items if a[key] is not None), '')
        field_type = {int: ogr.OFTInteger, float: ogr.OFTReal, str: ogr.OFTString}[type(first_value)]
        layer.CreateField(ogr.FieldDefn(key, field_type))
    for geometry, attrs in items:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr_geometry(geometry))
        for key, value in attrs.items():
            if value is not None:
                feature.SetField(key, value)
        layer.CreateFeature(feature)


def legacy_fingerprints():
    checks = {}
    for phase in (2, 3):
        doc = json.loads((ROOT / f'docs/phase{phase}_processing.json').read_text(encoding='utf-8'))
        checks[f'phase{phase}'] = {p: row['sha256'] for p, row in doc['outputs'].items()}
    candidate = json.loads((PREP / 'domain/domain_candidates.json').read_text(encoding='utf-8'))
    c03 = json.loads((PREP / 'terrain_c03/terrain_review.json').read_text(encoding='utf-8'))
    checks['candidate_domain'] = {relative(PREP / 'domain' / p): h
                                  for p, h in candidate['outputs_sha256'].items()}
    checks['c03'] = {**c03['source_sha256'],
                     relative(PREP / 'terrain_c03/c03_dem_utm49n_30m.tif'): c03['dem_sha256']}
    return checks


def verify_legacy(checks):
    for category, files in checks.items():
        require(all(digest(ROOT / p) == h for p, h in files.items()), f'历史成果指纹不一致：{category}')


def main():
    if OUT.exists() or OUT.resolve() != OUT:
        raise FileExistsError(f'结果目录已存在或解析后指向其他位置：{OUT}')
    gdal.SetConfigOption('GDAL_PAM_ENABLED', 'NO')
    checks = legacy_fingerprints()
    verify_legacy(checks)
    sources = {relative(p): digest(p) for p in (AOI, DEM, MASK, SEED, RIVERS, PROFILE)}
    domain, edges = domain_geometry()
    main_line, branches = read_rivers()
    require(domain.buffer(TOL).covers(main_line), '完整主线超出 AOI')
    source = gdal.Open(str(DEM), gdal.GA_ReadOnly)
    surface = Surface(source)
    srs = spatial_ref(EPSG)
    band = source.GetRasterBand(1)
    datum = source.GetMetadataItem('VERTICAL_DATUM')
    require(source.GetSpatialRef().IsSame(srs) and (surface.gt[1], surface.gt[2], *surface.gt[4:]) == (30, 0, 0, -30)
            and datum and 'EGM2008' in datum and band.GetUnitType() == 'm', '源 DEM 坐标或高程基准不符')
    mask, seed = [gdal.Open(str(path), gdal.GA_ReadOnly) for path in (MASK, SEED)]
    require(all(ds.GetGeoTransform() == surface.gt and ds.GetSpatialRef().IsSame(srs) for ds in (mask, seed)),
            '掩膜坐标或格网不相符')
    domain_ogr = ogr_geometry(domain)
    inside = geometry_mask([domain_ogr], source).astype(bool)
    valid = surface.valid
    require(np.array_equal(inside, mask.ReadAsArray() == 1) and np.array_equal(inside, valid)
            and label(valid)[1] == 1, 'AOI 掩膜与有效 DEM 不一致')
    touches = geometry_mask([domain_ogr], source, all_touched=True).astype(bool)
    seeds = seed.ReadAsArray() == 1
    require(seeds.any() and (seeds & valid).any(), '找不到有效主河道种子')
    connected = {}
    for z in THRESHOLDS:
        low = valid & (surface.values <= z)
        connected[z] = binary_propagation(seeds & low, mask=low)
    to_wgs = osr.CoordinateTransformation(srs, spatial_ref(4326))
    terminals = terminal_records(main_line, edges, surface, to_wgs)
    profile = verify_main_profile(main_line, surface)
    segments, perimeter = perimeter_data(domain, edges, surface, connected, terminals, to_wgs)
    verify_perimeter(domain, segments, terminals)
    options = [('domain', ogr.wkbPolygon, [(domain, dict(domain_id='full_reach_v1', area_km2=domain.area / 1e6))]),
               ('main_centerline', ogr.wkbLineString, [(main_line, dict(name='邕江', length_m=main_line.length,
                    station_order='west_endpoint_zero', flow_confirmed=0))]),
               ('perimeter_segments', ogr.wkbLineString, segments),
               ('river_terminals', ogr.wkbPoint, list(terminals.values()))]
    side_checks = {}
    for side in edges:
        rows = [r for r in perimeter if r['side'] == side]
        side_checks[side] = dict(length_m=edges[side].length, samples=len(rows),
                                 exact_nodata=sum(r['exact_z_m'] is None for r in rows),
                                 max_support_inset_m=max(r['support_inset_m'] for r in rows),
                                 min_inner_z_m=min(r['inner_z_m'] for r in rows),
                                 linked_samples={str(z): sum(r[f'linked_le{z}'] for r in rows) for z in THRESHOLDS})
    manifest = dict(
        stage='extension_4.1.2_full_reach', status='terrain_inputs_prepared',
        horizontal_crs='EPSG:32649', vertical_datum=datum, resolution_m=30, elevation_unit='m',
        base_dem=dict(path=relative(DEM), mode='direct_reference', nodata=band.GetNoDataValue(),
                      shape=list(surface.values.shape), geotransform=surface.gt,
                      valid_pixels=int(valid.sum()), inside_nodata=int((inside & ~valid).sum()),
                      all_touched_pixels=int(touches.sum()), all_touched_nodata=int((touches & ~valid).sum()),
                      z_min_m=float(surface.values[inside].min()), z_max_m=float(surface.values[inside].max())),
        domain=dict(area_km2=domain.area / 1e6, perimeter_m=domain.length, main_length_m=main_line.length,
                    outside_main_length_m=main_line.difference(domain).length),
        profile=profile, terminals=[a for _, a in terminals.values()], side_checks=side_checks,
        perimeter_layer_classes=dict(Counter(attrs['review_class'] for _, attrs in segments)),
        tributaries=[dict(name=name, geometry_gap_m=main_line.distance(g), role='unassigned')
                     for name, g in branches],
        screening=dict(thresholds_m=list(THRESHOLDS), step_max_m=30, inner_offset_m=45,
                       connectivity=4, seed_raster=relative(SEED),
                       terminal_segment_rule='contiguous <=75 m connected inner samples around mainline endpoint',
                       interpretation='terrain screening only; thresholds are not scenario water levels'),
        sampling=dict(exact='Phase 2 containing pixel, null when masked', inset_step_m=5, max_inset_m=45,
                      perimeter_support='first valid in-domain pixel on inward normal',
                      terminal_support='first valid pixel on the centerline toward the study area interior',
                      raw_dem_needed=False),
        scenario_assumptions=dict(flow_option='west inlet and east outlet may be adopted as a teaching scenario',
                                  observed_flow_confirmed=False, boundary_conditions='unassigned',
                                  numeric_parameters='deferred', bathymetry_modified=False),
        sources_sha256=sources, legacy_verified_counts={k: len(v) for k, v in checks.items()},
        script_sha256=digest(Path(__file__)))
    with tempfile.TemporaryDirectory(prefix='full-reach-stage-', dir=PREP) as folder:
        ready = Path(folder) / 'ready'
        ready.mkdir()
        gpkg = ready / 'domain.gpkg'
        with ogr.GetDriverByName('GPKG').CreateDataSource(str(gpkg)) as ds:
            for name, geom_type, items in options:
                write_layer(ds, name, geom_type, items)
        with ogr.Open(str(gpkg), 0) as check:
            require(check.GetLayerCount() == len(options), 'GeoPackage 图层数量异常')
            for name, geom_type, items in options:
                layer = check.GetLayerByName(name)
                require(layer.GetSpatialRef().IsSame(srs) and layer.GetGeomType() == geom_type
                        and layer.GetFeatureCount() == len(items), f'{name} 图层回读不符')
                for feature, (geom, attrs) in zip(layer, items):
                    require(shape(feature.GetGeometryRef()).equals_exact(geom, 1e-8)
                            and all(feature.GetField(k) == v for k, v in attrs.items()), f'{name} 要素回读不符')
        csv_path = ready / 'perimeter_samples.csv'
        with csv_path.open('x', encoding='utf-8-sig', newline='') as target:
            writer = csv.DictWriter(target, fieldnames=list(perimeter[0]))
            writer.writeheader()
            writer.writerows(perimeter)
        with csv_path.open(encoding='utf-8-sig', newline='') as check:
            rows = list(csv.DictReader(check))
        require(len(rows) == len(perimeter) and all(
            a == {k: '' if v is None else str(v) for k, v in b.items()}
            for a, b in zip(rows, perimeter)), '周界采样表回读不符')
        manifest['outputs_sha256'] = {p.name: digest(p) for p in (gpkg, csv_path)}
        manifest['readback_verified'] = True
        (ready / 'terrain_manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        verify_legacy(checks)
        require(all(digest(ROOT / p) == h for p, h in sources.items()), '执行期间源文件发生变化')
        if OUT.exists():
            raise FileExistsError(OUT)
        ready.rename(OUT)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
