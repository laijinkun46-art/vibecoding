"""Phase 4.1.1：只读既有地形，输出独立计算域候选、剖面和评审。

不下载数据、不修改输入、不求解水动力；任何目标文件已存在时拒绝覆盖。
使用项目既有 GDAL/OGR、Shapely、NumPy、Matplotlib，复用 gis_processing。
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path


def arguments():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=root / 'data/processed/hydrodynamics/preparation/domain')
    parser.add_argument('--report-path', type=Path,
                        default=root / 'docs/PHASE_4_1_1_DOMAIN_REVIEW.md')
    parser.add_argument('--gdal-bin', type=Path, default=Path('D:/Arcgis10.8.2/bin'))
    return root, parser.parse_args()


def main():
    root, args = arguments()
    out = args.output_dir.resolve()
    report_path = args.report_path.resolve()
    names = ['candidate_model_domains.gpkg', 'boundary_candidates.gpkg',
             'river_profile.csv', 'domain_preview.png', 'domain_candidates.json']
    targets = [out / name for name in names] + [report_path]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError('拒绝覆盖已有成果：' + ', '.join(existing))

    # 仅为本进程补充既有GDAL的DLL搜索路径，不改系统PATH。
    dll_handle = None
    if os.name == 'nt' and args.gdal_bin.is_dir():
        dll_handle = os.add_dll_directory(str(args.gdal_bin))
    import numpy as np
    from osgeo import gdal, ogr
    from shapely import wkb
    from shapely.geometry import Point, LineString, Polygon
    from shapely.ops import substring
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.lines import Line2D
    from gis_processing import (digest, geometry_mask, spatial_ref,
                                transform_geometry, valid_pixels)

    gdal.UseExceptions()
    ogr.UseExceptions()
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
                         'axes.unicode_minus': False, 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    paths = {key: root / value for key, value in {
        'dem': 'data/processed/phase2/dem_utm49n_30m.tif',
        'aoi': 'data/study_area/nanning_yongjiang_aoi.geojson',
        'mask': 'data/processed/phase2/aoi_mask.tif',
        'rivers': 'data/processed/phase2/rivers_utm49n.gpkg',
    }.items()}
    hashes = {str(path.relative_to(root)): digest(path) for path in paths.values()}
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def shape(geometry):
        return wkb.loads(bytes(geometry.ExportToWkb()))

    def og(geometry):
        return ogr.CreateGeometryFromWkb(geometry.wkb)

    def json_write(path, value):
        with path.open('x', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)

    dem = gdal.Open(str(paths['dem']), gdal.GA_ReadOnly)
    mask_ds = gdal.Open(str(paths['mask']), gdal.GA_ReadOnly)
    values, valid = valid_pixels(dem)
    gt = dem.GetGeoTransform()
    check('DEM为EPSG:32649、30m北向上网格',
          dem.GetSpatialRef().GetAuthorityCode(None) == '32649'
          and gt[1:] == (30., 0., 2529600., 0., -30.))
    check('AOI掩膜与DEM网格、CRS完全一致',
          mask_ds.GetGeoTransform() == gt and mask_ds.ReadAsArray().shape == values.shape
          and mask_ds.GetProjection() == dem.GetProjection())
    check('AOI掩膜内DEM全部有效，掩膜外DEM无有效值',
          np.array_equal(mask_ds.ReadAsArray() == 1, valid))
    aoi_json = json.loads(paths['aoi'].read_text(encoding='utf-8'))
    aoi_ogr = ogr.CreateGeometryFromJson(json.dumps(aoi_json['features'][0]['geometry']))
    aoi_ogr.Segmentize(.001)
    aoi = shape(transform_geometry(aoi_ogr, 4326, 32649))
    vector = ogr.Open(str(paths['rivers']), 0)
    layer = vector.GetLayer()
    check('河流GeoPackage为EPSG:32649', layer.GetSpatialRef().GetAuthorityCode(None) == '32649')
    rivers = [{'name': f.GetField('name'), 'osm_way_id': f.GetField('osm_way_id'),
               'geometry': shape(f.GetGeometryRef())} for f in layer]
    main_rivers = [r for r in rivers if r['name'] == '邕江']
    check('唯一邕江主线存在', len(main_rivers) == 1)
    river = main_rivers[0]['geometry']
    check('邕江主线单段连续且有效、无自交',
          river.geom_type == 'LineString' and river.is_valid and river.is_simple)
    check('邕江主线无相邻重复节点', all(
        a != b for a, b in zip(list(river.coords), list(river.coords)[1:])))
    # 仅按两端东西位置规范里程起点；绝不把坐标顺序等同于实际流向。
    if river.coords[0][0] > river.coords[-1][0]:
        river = LineString(list(river.coords)[::-1])
    tributaries = [r for r in rivers if r['name'] != '邕江']
    to_wgs = __import__('osgeo.osr', fromlist=['CoordinateTransformation']).CoordinateTransformation(
        spatial_ref(32649), spatial_ref(4326))

    def lonlat(x, y):
        lon, lat, _ = to_wgs.TransformPoint(float(x), float(y))
        return [float(lon), float(lat)]

    def sample(x, y):
        col = math.floor((x - gt[0]) / gt[1])
        row = math.floor((y - gt[3]) / gt[5])
        ok = (0 <= row < values.shape[0] and 0 <= col < values.shape[1]
              and valid[row, col])
        return (float(values[row, col]) if ok else None, row, col, bool(ok))

    def stations(length, interval=30.):
        result = list(np.arange(0., length, interval))
        if not result or length - result[-1] > 1e-8:
            result.append(float(length))
        return result

    def stats(numbers):
        data = np.array([v for v in numbers if v is not None], dtype=float)
        if not data.size:
            return {'count': 0}
        q = np.percentile(data, [0, 10, 50, 90, 100])
        return {'count': int(data.size), 'min_m': float(q[0]), 'p10_m': float(q[1]),
                'median_m': float(q[2]), 'p90_m': float(q[3]), 'max_m': float(q[4]),
                'mean_m': float(data.mean()), 'std_m': float(data.std())}

    rows = []

    def profile_row(kind, cid, pid, s, distance, point):
        z, row, col, ok = sample(point.x, point.y)
        lon, lat = lonlat(point.x, point.y)
        item = {'profile_kind': kind, 'candidate_id': cid, 'profile_id': pid,
                'chainage_m': float(s), 'offset_or_distance_m': float(distance),
                'easting_m': point.x, 'northing_m': point.y,
                'longitude': lon, 'latitude': lat, 'dem_elevation_m': z,
                'valid': int(ok), 'raster_row': row, 'raster_col': col,
                'vertical_datum': 'EGM2008', 'sample_method': 'containing_pixel',
                'is_measured_bed': 0}
        rows.append(item)
        return item

    longitudinal = [profile_row('longitudinal', '', 'YONGJIANG', s, s,
                                river.interpolate(s)) for s in stations(river.length)]
    full_profile_stats = stats([r['dem_elevation_m'] for r in longitudinal])
    valid_long = [r for r in longitudinal if r['valid']]
    plateau = sum(abs(r['dem_elevation_m'] - 63) < 1e-6 for r in valid_long)

    def normal_at(s):
        # 1m邻域只用于确定当前源线段的几何切向，不平滑DEM。
        p0 = river.interpolate(max(0., s - 1.))
        p1 = river.interpolate(min(river.length, s + 1.))
        dx, dy = p1.x - p0.x, p1.y - p0.y
        length = math.hypot(dx, dy)
        return np.array([-dy / length, dx / length])

    def raster_stats(geometry):
        selected = geometry_mask([og(geometry)], dem, all_touched=True).astype(bool)
        good = selected & valid
        return {'touched_pixels': int(selected.sum()), 'valid_pixels': int(good.sum()),
                'invalid_pixels': int((selected & ~valid).sum()),
                'valid_fraction': float(good.sum() / selected.sum()),
                'elevation': stats(values[good].tolist())}

    def transverse(s, halfwidth, cid, pid, kind):
        point = river.interpolate(s)
        n = normal_at(s)
        start = Point(*(np.array(point.coords[0]) - n * halfwidth))
        end = Point(*(np.array(point.coords[0]) + n * halfwidth))
        line = LineString([start, end])
        sampled = [profile_row(kind, cid, pid, s, d - halfwidth,
                               line.interpolate(d)) for d in stations(line.length)]
        return line, sampled

    def end_cap(domain, center, label):
        """提取缓冲多边形实际端边，并按负到正的几何法向排列。"""
        coords = np.asarray(center.coords)
        if label == 'A':
            point, tangent = coords[0], coords[1] - coords[0]
        else:
            point, tangent = coords[-1], coords[-1] - coords[-2]
        tangent /= np.linalg.norm(tangent)
        normal = np.array([-tangent[1], tangent[0]])
        ring = np.asarray(domain.exterior.coords)
        edges = []
        for a, b in zip(ring, ring[1:]):
            a0, b0 = a - point, b - point
            if max(abs(a0 @ tangent), abs(b0 @ tangent)) > 1e-6:
                continue
            a_offset, b_offset = a0 @ normal, b0 @ normal
            if min(a_offset, b_offset) < 0 < max(a_offset, b_offset):
                if a_offset > b_offset:
                    a, b = b, a
                    a_offset, b_offset = b_offset, a_offset
                edges.append((LineString([a, b]), float(a_offset), float(b_offset)))
        if len(edges) != 1:
            raise ValueError(f'{label}端未找到唯一穿过中心线的多边形端边')
        return edges[0]

    specs = [('C01', '西段紧凑方案', 4000., 9000., 1200.),
             ('C02', '西中段扩展方案', 3000., 12000., 1800.),
             ('C03', '东段独立河段方案（推荐候选）', 20000., 27000., 1500.)]
    colors = {'C01': '#e08e24', 'C02': '#8555ad', 'C03': '#008b89'}
    candidates, polygons, centerlines = [], {}, {}
    boundaries, crosses, laterals = [], [], []
    for cid, title, start, end, halfwidth in specs:
        center = substring(river, start, end)
        domain = center.buffer(halfwidth, cap_style=2, quad_segs=16)
        polygons[cid], centerlines[cid] = domain, center
        check(cid + '候选域为单一有效多边形', domain.geom_type == 'Polygon' and domain.is_valid)
        check(cid + '候选域完全位于AOI内', aoi.covers(domain))
        check(cid + '只包含一个连续主河段，长度与选段一致',
              river.intersection(domain).geom_type == 'LineString'
              and abs(river.intersection(domain).length - (end - start)) < .01)
        coverage = raster_stats(domain)
        check(cid + '候选域所有触及像元均有有效DEM', coverage['invalid_pixels'] == 0)
        boundary_info = []
        for label, s in [('A', start), ('B', end)]:
            bid = cid + '_' + label
            line, negative_offset, positive_offset = end_cap(domain, center, label)
            distances = sorted(set(stations(line.length) + [-negative_offset]))
            sampled = [profile_row('boundary', cid, bid, s, d + negative_offset,
                                   line.interpolate(d)) for d in distances]
            check(bid + '整条端盖匹配计算域边界',
                  line.difference(domain.boundary.buffer(.01)).length < .01)
            intersection = line.intersection(river)
            point = river.interpolate(s)
            check(bid + '只横切主河道一次且交点位于目标里程',
                  intersection.geom_type == 'Point' and intersection.distance(point) < .01)
            check(bid + '端界剖面有效覆盖', all(r['valid'] for r in sampled))
            zs = [r['dem_elevation_m'] for r in sampled]
            info = {'boundary_id': bid, 'end_label': label, 'chainage_m': s,
                    'center_utm': [point.x, point.y], 'center_wgs84': lonlat(point.x, point.y),
                    'endpoints_utm': [list(line.coords[0]), list(line.coords[-1])],
                    'endpoints_wgs84': [lonlat(*line.coords[0]), lonlat(*line.coords[-1])],
                    'length_m': line.length, 'elevation': stats(zs),
                    'endpoint_offsets_m': [negative_offset, positive_offset],
                    'endpoint_elevations_m': [zs[0], zs[-1]],
                    'valid_fraction': sum(r['valid'] for r in sampled) / len(sampled),
                    'hydraulic_role': 'unconfirmed_either_upstream_or_downstream',
                    'flow_direction_confirmed': False,
                    'review': '覆盖中心线两侧候选洪泛走廊；尚非最终水力边界，无流量/水位赋值'}
            boundaries.append({'geometry': line, 'info': info, 'candidate_id': cid})
            boundary_info.append(info)
        for i, fraction in enumerate([.25, .5, .75], 1):
            s = start + (end - start) * fraction
            pid = f'{cid}_X{i}'
            line, sampled = transverse(s, halfwidth, cid, pid, 'cross_section')
            crosses.append({'geometry': line, 'candidate_id': cid, 'profile_id': pid,
                            'chainage_m': s, 'rows': sampled,
                            'river_intersections': line.intersection(river).geom_type})
        side_info = []
        for sign, side in [(-1, 'R'), (1, 'L')]:
            edge = center.offset_curve(sign * halfwidth, quad_segs=16)
            check(cid + side + '侧边界单线且匹配域边界', edge.geom_type == 'LineString'
                  and edge.difference(domain.boundary.buffer(.01)).length < .01)
            sampled = [profile_row('lateral_edge', cid, cid + '_' + side, start,
                                   d, edge.interpolate(d)) for d in stations(edge.length)]
            zs = [r['dem_elevation_m'] for r in sampled if r['valid']]
            info = {'side': side, 'reference': 'L/R仅相对于西端起算里程增加方向，非水文左右岸',
                    'length_m': edge.length, 'elevation': stats(zs),
                    'fraction_le_diagnostic_elevation': {
                        str(t): sum(z <= t for z in zs) / len(zs) for t in [75, 80, 85]},
                    'lowest_sample_wgs84': [min(sampled, key=lambda r:
                        r['dem_elevation_m'] if r['valid'] else float('inf'))[key]
                        for key in ['longitude', 'latitude']]}
            side_info.append(info)
            laterals.append({'geometry': edge, 'candidate_id': cid, 'side': side, 'info': info})
        domain_geo = shape(transform_geometry(og(domain), 32649, 4326))
        near = center.buffer(300).intersection(domain)
        near100 = center.buffer(100).intersection(domain)
        candidates.append({'id': cid, 'name': title, 'recommended': cid == 'C03',
            'status': 'candidate_pending_user_confirmation', 'area_km2': domain.area / 1e6,
            'aoi_area_fraction': domain.area / aoi.area,
            'main_river_length_m': center.length, 'chainage_interval_m': [start, end],
            'half_corridor_width_m': halfwidth,
            'bounds_utm_wsen': list(domain.bounds), 'bounds_wgs84_wsen': list(domain_geo.bounds),
            'distance_to_aoi_boundary_m': domain.distance(aoi.boundary),
            'dem_coverage': coverage, 'near_centerline_300m': raster_stats(near),
            'near_centerline_100m': raster_stats(near100),
            'tributary_intersections': [{'name': r['name'],
                'length_inside_domain_m': r['geometry'].intersection(domain).length,
                'distance_to_domain_m': r['geometry'].distance(domain)} for r in tributaries],
            'boundaries': boundary_info, 'lateral_edges': side_info,
            'mesh_triangle_estimates_uniform_equilateral': {
                str(size): math.ceil(domain.area / (math.sqrt(3) / 4 * size ** 2))
                for size in [30, 60, 90, 120]},
            'risks': {'C01': ['走廊窄且L侧低平，潜在侧向截流', '朝阳溪在域外附近，未排除未绘连接'],
                      'C02': ['包含现有朝阳溪线的一部分但未连主线，侧向来流未知', 'L侧低平且范围较大',
                              'B端负偏移一侧受相邻河弯走廊挤压，需核对洪泛出口'],
                      'C03': ['L侧存在低口，不能默认封闭', 'B端正偏移末端地形偏低，需核对洪泛通道',
                              '河床、水位、来流资料缺失；上下游角色未确认']}[cid]})

    # 输出前验证剖面与候选指标，全部采用原网格像元取值。
    check('纵剖面里程严格增加且终点准确', all(
        a['chainage_m'] < b['chainage_m'] for a, b in zip(longitudinal, longitudinal[1:]))
        and abs(longitudinal[-1]['chainage_m'] - river.length) < 1e-6)
    check('9条横剖面均包含中心点且有效覆盖', len(crosses) == 9 and all(
        any(abs(r['offset_or_distance_m']) < 1e-6 for r in c['rows'])
        and all(r['valid'] for r in c['rows']) for c in crosses))
    check('全体剖面值与原DEM像元一致', all(
        (r['dem_elevation_m'] == float(values[r['raster_row'], r['raster_col']]))
        for r in rows if r['valid']))
    for row in rows:
        if not row['valid']:
            check(row['profile_id'] + '无效点保持空值', row['dem_elevation_m'] is None)

    out.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def write_layer(ds, name, geomtype, fields, records):
        layer = ds.CreateLayer(name, srs=spatial_ref(32649), geom_type=geomtype,
                               options=['SPATIAL_INDEX=YES'])
        for key, fieldtype in fields:
            layer.CreateField(ogr.FieldDefn(key, fieldtype))
        for geometry, attrs in records:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(og(geometry))
            for key, value in attrs.items():
                feature.SetField(key, value)
            layer.CreateFeature(feature)

    driver = ogr.GetDriverByName('GPKG')
    ds = driver.CreateDataSource(str(out / names[0]))
    write_layer(ds, 'candidate_domains', ogr.wkbPolygon,
                [('candidate_id', ogr.OFTString), ('name', ogr.OFTString),
                 ('area_km2', ogr.OFTReal), ('river_m', ogr.OFTReal),
                 ('halfwidth_m', ogr.OFTReal), ('recommended', ogr.OFTInteger),
                 ('status', ogr.OFTString)],
                [(polygons[c['id']], {'candidate_id': c['id'], 'name': c['name'],
                  'area_km2': c['area_km2'], 'river_m': c['main_river_length_m'],
                  'halfwidth_m': c['half_corridor_width_m'], 'recommended': int(c['recommended']),
                  'status': 'pending_confirmation'}) for c in candidates])
    write_layer(ds, 'candidate_river_segments', ogr.wkbLineString,
                [('candidate_id', ogr.OFTString), ('chainage0_m', ogr.OFTReal),
                 ('chainage1_m', ogr.OFTReal), ('direction', ogr.OFTString)],
                [(centerlines[c['id']], {'candidate_id': c['id'],
                    'chainage0_m': c['chainage_interval_m'][0],
                    'chainage1_m': c['chainage_interval_m'][1],
                    'direction': 'west_endpoint_chainage_not_flow'}) for c in candidates])
    ds = None
    ds = driver.CreateDataSource(str(out / names[1]))
    write_layer(ds, 'end_boundary_candidates', ogr.wkbLineString,
                [('candidate_id', ogr.OFTString), ('boundary_id', ogr.OFTString),
                 ('chainage_m', ogr.OFTReal), ('length_m', ogr.OFTReal),
                 ('hydraulic_role', ogr.OFTString), ('confirmed', ogr.OFTInteger)],
                [(b['geometry'], {'candidate_id': b['candidate_id'],
                    'boundary_id': b['info']['boundary_id'], 'chainage_m': b['info']['chainage_m'],
                    'length_m': b['info']['length_m'], 'hydraulic_role': 'UNCONFIRMED_A_OR_B',
                    'confirmed': 0}) for b in boundaries])
    write_layer(ds, 'terrain_cross_sections', ogr.wkbLineString,
                [('candidate_id', ogr.OFTString), ('profile_id', ogr.OFTString),
                 ('chainage_m', ogr.OFTReal), ('intersections', ogr.OFTString)],
                [(c['geometry'], {key: c[key] for key in ['candidate_id', 'profile_id', 'chainage_m']}
                  | {'intersections': c['river_intersections']}) for c in crosses])
    write_layer(ds, 'lateral_boundary_review', ogr.wkbLineString,
                [('candidate_id', ogr.OFTString), ('side', ogr.OFTString),
                 ('min_dem_m', ogr.OFTReal), ('le80_fraction', ogr.OFTReal),
                 ('closed_confirmed', ogr.OFTInteger)],
                [(e['geometry'], {'candidate_id': e['candidate_id'], 'side': e['side'],
                    'min_dem_m': e['info']['elevation']['min_m'],
                    'le80_fraction': e['info']['fraction_le_diagnostic_elevation']['80'],
                    'closed_confirmed': 0}) for e in laterals])
    ds = None
    with (out / names[2]).open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # 单张复合图：总览、3个局部图、纵剖面、9条横剖面。不请求在线底图。
    fig = plt.figure(figsize=(18, 20), layout='constrained')
    grid = fig.add_gridspec(4, 3, height_ratios=[1.15, 1., .65, .9])
    norm = Normalize(63, 220)
    extent = [gt[0] / 1000, (gt[0] + gt[1] * values.shape[1]) / 1000,
              (gt[3] + gt[5] * values.shape[0]) / 1000, gt[3] / 1000]
    raster = np.ma.array(values, mask=~valid)

    def plot_line(ax, geometry, **kwargs):
        if geometry.is_empty:
            return
        if hasattr(geometry, 'geoms'):
            for part in geometry.geoms:
                plot_line(ax, part, **kwargs)
        else:
            coords = np.array(geometry.coords)
            ax.plot(coords[:, 0] / 1000, coords[:, 1] / 1000, **kwargs)

    def map_background(ax):
        image = ax.imshow(raster, extent=extent, cmap='terrain', norm=norm, origin='upper')
        plot_line(ax, aoi.boundary, color='#4d5963', lw=1, ls='--')
        for r in rivers:
            plot_line(ax, r['geometry'], color='#1f69ba', lw=1.3)
        ax.set_aspect('equal')
        ax.set_xlabel('UTM Easting / km')
        ax.set_ylabel('UTM Northing / km')
        ax.ticklabel_format(style='plain', useOffset=False)
        return image

    overview = fig.add_subplot(grid[0, :2])
    image = map_background(overview)
    for c in candidates:
        cid = c['id']
        plot_line(overview, polygons[cid].boundary, color=colors[cid], lw=2)
        p = polygons[cid].representative_point()
        overview.text(p.x / 1000, p.y / 1000, cid, color=colors[cid], weight='bold',
                      bbox={'facecolor': 'white', 'alpha': .85, 'edgecolor': 'none'})
    overview.set_title('现有 AOI 与三个局部计算域候选（无在线底图）', loc='left', weight='bold')
    overview.text(.97, .96, 'N ↑', transform=overview.transAxes, ha='right', va='top', weight='bold')
    fig.colorbar(image, ax=overview, shrink=.76, pad=.02, label='FABDEM地表高程 / m（EGM2008）', extend='max')
    text_ax = fig.add_subplot(grid[0, 2])
    text_ax.axis('off')
    summary = ['Phase 4.1.1 计算域候选', '',
               f'AOI投影面积：{aoi.area / 1e6:.2f} km²',
               f'主线全长：{river.length / 1000:.2f} km', '',
               *[f"{c['id']}  {c['area_km2']:.2f} km² / {c['main_river_length_m']/1000:.1f} km"
                 for c in candidates], '', '推荐：C03，仍待用户确认',
               '三域DEM触及像元均100%有效', '', 'A / B：端盖编号，不代表上下游',
               'L / R：相对里程方向，非水文左右岸', '',
               '地表高程不是实测河床；', '63 m平台不能确定流向或河床坡降。',
               '', '侧界尚未证实为分水岭/封闭边界。', '未设置水位、流量或河床深度。']
    text_ax.text(.03, .97, '\n'.join(summary), transform=text_ax.transAxes,
                 va='top', linespacing=1.65, fontsize=11)
    for j, c in enumerate(candidates):
        cid = c['id']
        ax = fig.add_subplot(grid[1, j])
        map_background(ax)
        plot_line(ax, polygons[cid].boundary, color=colors[cid], lw=2)
        for b in boundaries:
            if b['candidate_id'] == cid:
                plot_line(ax, b['geometry'], color='#ce3f47', lw=2.5)
                coords = b['geometry'].coords[-1]
                ax.annotate(b['info']['end_label'], (coords[0]/1000, coords[1]/1000),
                            xytext=(3, 3), textcoords='offset points', color='#ae2631', weight='bold')
        for cross in crosses:
            if cross['candidate_id'] == cid:
                plot_line(ax, cross['geometry'], color='#26374d', ls=':', lw=1.1)
                p = river.interpolate(cross['chainage_m'])
                ax.annotate(cross['profile_id'][-2:], (p.x/1000, p.y/1000), xytext=(3, 4),
                            textcoords='offset points', fontsize=9)
        x0, y0, x1, y1 = polygons[cid].bounds
        ax.set_xlim(x0/1000-.35, x1/1000+.35)
        ax.set_ylim(y0/1000-.35, y1/1000+.35)
        ax.set_title(f"{cid} | {c['area_km2']:.2f} km² | 河段 {c['main_river_length_m']/1000:.1f} km",
                     loc='left', color=colors[cid], weight='bold')
    long_ax = fig.add_subplot(grid[2, :])
    long_ax.plot([r['chainage_m']/1000 for r in longitudinal],
                 [r['dem_elevation_m'] if r['valid'] else np.nan for r in longitudinal],
                 color='#334c69', lw=1.4)
    for c in candidates:
        start, end = c['chainage_interval_m']
        long_ax.axvspan(start/1000, end/1000, alpha=.12, color=colors[c['id']], label=c['id'])
    long_ax.set(title='沿OSM中心线取地表DEM纵剖面（西端起算；不表示实际流向/河床坡降）',
                xlabel='距主线西端的几何里程 / km', ylabel='DEM高程 / m EGM2008')
    low, high = full_profile_stats['min_m'], full_profile_stats['max_m']
    long_ax.set_ylim(min(low-1, 62), max(high+1, 65))
    long_ax.legend(loc='upper right', ncol=3)
    long_ax.grid(alpha=.2)
    for j, c in enumerate(candidates):
        ax = fig.add_subplot(grid[3, j])
        for cross in crosses:
            if cross['candidate_id'] == c['id']:
                ax.plot([r['offset_or_distance_m'] for r in cross['rows']],
                        [r['dem_elevation_m'] for r in cross['rows']],
                        label=f"{cross['profile_id'][-2:]} @ {cross['chainage_m']/1000:.2f} km")
        ax.axvline(0, color='#55616a', lw=.8, ls='--')
        ax.set(title=c['id'] + ' 三条横向地表剖面', xlabel='距中心线几何偏移 / m（正值为L侧）',
               ylabel='DEM高程 / m EGM2008')
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
    fig.suptitle('南宁邕江局部水动力计算域准备 · 候选分析，未开展水动力模拟', fontsize=18, weight='bold')
    fig.savefig(out / names[3], dpi=150)
    plt.close(fig)

    expected_layers = {names[0]: {'candidate_domains': 3, 'candidate_river_segments': 3},
                       names[1]: {'end_boundary_candidates': 6, 'terrain_cross_sections': 9,
                                  'lateral_boundary_review': 6}}
    for filename, layers in expected_layers.items():
        ds = ogr.Open(str(out / filename), 0)
        check(filename + '图层数量回读', ds.GetLayerCount() == len(layers))
        for name, count in layers.items():
            layer = ds.GetLayerByName(name)
            check(name + '要素数/坐标系/有效性回读', layer.GetFeatureCount() == count
                  and layer.GetSpatialRef().GetAuthorityCode(None) == '32649'
                  and all(f.GetGeometryRef().IsValid() for f in layer))
        ds = None
    with (out / names[2]).open(encoding='utf-8-sig', newline='') as f:
        reread = list(csv.DictReader(f))
    check('CSV回读记录数及高程、空值一致', len(reread) == len(rows) and all(
        (a['dem_elevation_m'] == '' if b['dem_elevation_m'] is None
         else float(a['dem_elevation_m']) == b['dem_elevation_m']) for a, b in zip(reread, rows)))
    from PIL import Image
    with Image.open(out / names[3]) as image:
        image.verify()
    check('预览PNG可解码', True)
    check('四项输入SHA256未改变', all(digest(root / p) == value for p, value in hashes.items()))
    endpoints = [Point(river.coords[0]), Point(river.coords[-1])]
    info = {'phase': '4.1.1', 'status': 'candidate_pending_user_confirmation',
        'generated_bjt': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        'recommended_candidate': 'C03', 'selected_candidate': None,
        'horizontal_crs': 'EPSG:32649', 'vertical_datum': 'EGM2008',
        'flow_direction_confirmed': False, 'source_sha256': hashes,
        'method': {'domain': 'substring along west-end chainage, constant-width flat-capped buffer',
                   'end_cap': 'actual polygon edge along the endpoint normal, may be asymmetric after buffer overlap',
                   'chainage': 'west endpoint zero, purely geometric, not upstream direction',
                   'halfwidths_m': [1200, 1800, 1500], 'sample_spacing_m': 30,
                   'sampling': 'containing valid Phase2 pixel, no interpolation, missing stays null',
                   'side_reference': 'L=positive geometric normal; not hydrologic left bank',
                   'diagnostic_elevations_m': [75, 80, 85],
                   'diagnostic_warning': '仅地形截断筛查；不是设定水位、洪水范围或边界条件'},
        'aoi': {'bounds_wgs84_wsen': [108.23, 22.73, 108.44, 22.85],
                'bounds_utm_wsen': list(aoi.bounds), 'area_projected_km2': aoi.area/1e6,
                'dem_valid_pixels': int(valid.sum()), 'dem_pixel_area_km2': int(valid.sum())*.0009,
                'dem_grid_shape': list(values.shape), 'dem_geotransform': list(gt),
                'dem_elevation': stats(values[valid].tolist()),
                'main_river_length_m': river.length, 'main_river_points': len(river.coords),
                'main_river_simple': river.is_simple,
                'main_end_distance_to_aoi_boundary_m': [p.distance(aoi.boundary) for p in endpoints],
                'main_end_wgs84': [lonlat(p.x, p.y) for p in endpoints],
                'main_intersection_with_exact_projected_aoi_boundary': river.intersection(aoi.boundary).wkt,
                'river_components_by_intersection': len(rivers) if not any(
                    river.intersects(r['geometry']) for r in tributaries) else 1,
                'tributary_gap_to_main_m': [{'name': r['name'], 'distance_m': river.distance(r['geometry'])}
                                          for r in tributaries],
                'mesh_triangles_at_30m_equilateral': math.ceil(aoi.area/(math.sqrt(3)/4*30**2))},
        'longitudinal_profile': {'sample_count': len(longitudinal),
                'valid_count': len(valid_long), 'invalid_count': len(longitudinal)-len(valid_long),
                'valid_elevation': full_profile_stats, 'count_equal_63m': plateau,
                'fraction_equal_63m': plateau/len(valid_long), 'bed_slope_inferred': False},
        'profiles': {'csv_rows': len(rows), 'cross_sections': len(crosses),
                     'boundary_sections': len(boundaries), 'lateral_edges': len(laterals)},
        'candidates': candidates,
        'validation': {'passed': True, 'check_count': len(checks), 'checks': checks},
        'outputs_sha256': {name: digest(out / name) for name in names[:-1]},
        'script_sha256': digest(Path(__file__)), 'no_data_downloaded': True,
        'no_anuga_installed_or_run': True, 'bed_modified': False,
        'discharge_or_stage_boundary_assigned': False}
    json_write(out / names[4], info)
    with (out / names[4]).open(encoding='utf-8') as f:
        assert json.load(f)['candidates'] == candidates
    report = make_report(root, out, report_path, info)
    with report_path.open('x', encoding='utf-8') as f:
        f.write(report)
    # 保持句柄存活直到GDAL调用结束。
    _ = dll_handle
    print(json.dumps({'output_dir': str(out), 'report': str(report_path),
                      'check_count': len(checks), 'profiles': info['profiles'],
                      'longitudinal': info['longitudinal_profile'],
                      'candidates': [{'id': c['id'], 'area_km2': c['area_km2'],
                                      'river_length_m': c['main_river_length_m']} for c in candidates]},
                     ensure_ascii=True))


def make_report(root, out, report_path, data):
    """输入已计算与验证的候选指标，输出中文评审；不引入外部事实。"""
    aoi, long = data['aoi'], data['longitudinal_profile']
    cs = data['candidates']
    links = lambda name: Path(os.path.relpath(out / name, report_path.parent)).as_posix()
    fmt = lambda bounds: ', '.join(f'{v:.6f}' for v in bounds)
    table = '\n'.join(
        f"| {c['id']} | {c['main_river_length_m']/1000:.2f} | {c['half_corridor_width_m']:.0f} | "
        f"{c['area_km2']:.4f} | {c['aoi_area_fraction']*100:.2f}% | "
        f"{c['mesh_triangle_estimates_uniform_equilateral']['60']:,} | "
        f"{c['distance_to_aoi_boundary_m']:.0f} |" for c in cs)
    details = []
    for c in cs:
        text = [f"### {c['id']}：{c['name']}", '',
                f"- 选取西端起算几何里程 {c['chainage_interval_m'][0]/1000:.2f}～"
                f"{c['chainage_interval_m'][1]/1000:.2f} km；单个连续河段。",
                f"- EPSG:32649外包范围（西、南、东、北，m）：{fmt(c['bounds_utm_wsen'])}。",
                f"- WGS84外包范围（西、南、东、北，度）：{fmt(c['bounds_wgs84_wsen'])}。",
                f"- 候选域为中心线每侧{c['half_corridor_width_m']:.0f}m的平端走廊，"
                '覆盖两侧待核实的河岸与洪泛地形；这不是实测河宽，也不是已证明的完整洪泛区。',
                f"- DEM触及{c['dem_coverage']['touched_pixels']:,}像元，全部有效；"
                f"域内地表高程{c['dem_coverage']['elevation']['min_m']:.2f}～"
                f"{c['dem_coverage']['elevation']['max_m']:.2f}m；"
                f"中心线300m邻域地表高程中位数"
                f"{c['near_centerline_300m']['elevation']['median_m']:.2f}m。", '']
        for b in c['boundaries']:
            text.append(f"- {b['boundary_id']}：里程{b['chainage_m']/1000:.2f}km；"
                        f"中心经纬度 {b['center_wgs84'][0]:.6f}, {b['center_wgs84'][1]:.6f}；"
                        f"中心UTM {b['center_utm'][0]:.2f}, {b['center_utm'][1]:.2f}m；"
                        f"端边长{b['length_m']:.0f}m，负/正向偏移"
                        f"{b['endpoint_offsets_m'][0]:.0f}/{b['endpoint_offsets_m'][1]:.0f}m；端点DEM高程"
                        f"{b['endpoint_elevations_m'][0]:.2f}/{b['endpoint_elevations_m'][1]:.2f}m。")
        text += ['', '端盖均只穿主线一次，并与域多边形端边完整重合；'
                 '**A和B都是上下游边界的待确认候选，未给二者分配入流或出流角色。**', '',
                 '| 几何侧界 | 侧界最低/中位高程 m | ≤80m样本比例 | 最低样本位置（经度，纬度） |',
                 '| --- | --- | --- | --- |']
        for side in c['lateral_edges']:
            text.append(f"| {side['side']} | {side['elevation']['min_m']:.2f} / "
                        f"{side['elevation']['median_m']:.2f} | "
                        f"{100*side['fraction_le_diagnostic_elevation']['80']:.1f}% | "
                        f"{fmt(side['lowest_sample_wgs84'])} |")
        text += ['', '≤80m只是统一地形诊断阈值，**没有设定80m边界水位**。75/85m的对应筛查比例也保存在JSON；'
                 '即便高于阈值，也不证明该侧界一定不越流。', '',
                 '现有支流关系：' + '；'.join(
                     f"{t['name']}入域线长{t['length_inside_domain_m']:.1f}m，"
                     f"距域{t['distance_to_domain_m']:.1f}m" for t in c['tributary_intersections']) + '。', '',
                 '主要风险：' + '；'.join(c['risks']) + '。', '']
        details.append('\n'.join(text))
    files = '\n'.join(f'- [{name}]({links(name)})' for name in
                      ['candidate_model_domains.gpkg', 'boundary_candidates.gpkg',
                       'river_profile.csv', 'domain_preview.png', 'domain_candidates.json'])
    return f'''# Phase 4.1.1：水动力计算域候选评审

分析对象：`{root}`。生成时间：{data['generated_bjt']}。

本阶段完成现有AOI、DEM、河流的只读检查，生成3个局部候选域、6条端边界、9条横剖面及纵剖面。**推荐C03，但尚未选定计算域，等待用户确认；不进入4.1.2。**

## 1. 范围与输入

已阅读AGENTS.md、PROJECT_SPEC.md、TASKS.md、EXISTING_PROJECT_AUDIT.md和INCREMENTAL_UPGRADE_PLAN.md，并检查既有GIS工具。采用现有GDAL/OGR、NumPy、Shapely、Matplotlib，不联网、不安装ANUGA、不修改前端、不设置河床深度或流量。用户要求不覆盖已有文件，因此不更新原有TASKS.md；本报告记录本阶段状态，所有旧Git修改保留。

四个直接输入为 `data/processed/phase2/dem_utm49n_30m.tif`、`aoi_mask.tif`、`rivers_utm49n.gpkg`，以及 `data/study_area/nanning_yongjiang_aoi.geojson`。输入SHA256在JSON中保存并于生成后复核，原始DEM和Phase 2/3处理流程均未重跑。

## 2. 现有研究区与连续性

- AOI为WGS84矩形108.23～108.44°E、22.73～22.85°N；边界加密到0.001°后仅在内存投影。UTM外包范围为{fmt(aoi['bounds_utm_wsen'])}m。
- AOI投影矢量面积{aoi['area_projected_km2']:.4f}km²；DEM有效像元{aoi['dem_valid_pixels']:,}个，像元面积合计{aoi['dem_pixel_area_km2']:.4f}km²。二者口径不同，不把边缘离散差当数据缺失。
- DEM为EPSG:32649、30m、457×728网格，EGM2008高程；有效像元与AOI掩膜等值，范围内地表高程{aoi['dem_elevation']['min_m']:.2f}～{aoi['dem_elevation']['max_m']:.2f}m。矩形网格外包范围并不等于全部有效范围。
- 邕江为1条有效、无自交、无相邻重复点的连续LineString，{aoi['main_river_points']}个节点、长{aoi['main_river_length_m']/1000:.4f}km。两端位于AOI西、东边界附近，距加密投影AOI边界分别{aoi['main_end_distance_to_aoi_boundary_m'][0]:.6f}/{aoi['main_end_distance_to_aoi_boundary_m'][1]:.6f}m；按1m几何核对容差，确认主线在两侧穿越AOI边界。精确浮点相交WKT另存JSON，不把投影细小差异当河道缺口。
- 邕江与朝阳溪仍为{aoi['river_components_by_intersection']}个几何连通分量；最小间距{aoi['tributary_gap_to_main_m'][0]['distance_m']:.2f}m。没有吸附、补线或虚构支流汇入口。主线连续不代表支流水系完整。
- 全主线纵剖面{long['sample_count']}个点，其中有效{long['valid_count']}、无效{long['invalid_count']}；无效点保留空值，多位于裁剪边界附近，不能将NoData当0m或补成河床。候选域及其纵横端界全部位于有效数据内。

## 3. 候选域构造及比较

为了可复现而规范里程：以邕江几何**西端**为0，沿线累计距离。它是空间索引，**不是上游起点**；未使用OSM原始节点顺序认定流向。各方案沿连续河段构造恒宽平端缓冲走廊，不直接套用整个AOI，也没有根据尚未确定的设计洪水选边界。

| 方案 | 河段长 km | 每侧走廊宽 m | 投影面积 km² | 占AOI | 60m等边三角形粗估数 | 距AOI边界最小值 m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{table}

面积为多边形投影面积，不是预报淹没面积。三角形数量按面积/(√3/4×边长²)估计，只用于量级比较，实际边界加密、网格质量和混合尺度会改变数量，未生成网格。

{chr(10).join(details)}

## 4. 地形剖面与附近高程

纵向点沿完整中心线每30m取样并保留末端；3个候选各设25%、50%、75%里程横剖面，共9条，端盖另外6条。横线按当地源线段几何法向扩展至两侧走廊边缘，每30m采样。CSV还含6条侧界的地表高程，便于定位潜在截流低口。

采用**取所在像元原值**，不是双线性插值，不改变Phase 2网格、精度或高程。CSV的`profile_kind`区分longitudinal/cross_section/boundary/lateral_edge；`chainage_m`为主线里程。横向偏移正值为相对里程方向的几何L侧，负值为R侧，**不是已确定的水文左右岸**；lateral_edge行中的chainage_m只是选段起点标识，`offset_or_distance_m`是沿该侧界的累计距离，不可误当河道投影里程。横线可能在弯道附近再次遇到其他河段，图层的intersections字段用于核查，不把曲线全部解释为单一河槽断面。

有效纵剖面的地表高程范围为{long['valid_elevation']['min_m']:.6f}～{long['valid_elevation']['max_m']:.6f}m；其中{long['count_equal_63m']}点（{long['fraction_equal_63m']*100:.2f}%）为63m。该平台是当前DEM沿水面参考线的取样现象，可能与水域表达或源产品处理有关，**本轮没有验证成因**，不能解释为实测河底、正常水位或反推实际水深；更不能据此确定河床坡降与实际流向。

JSON提供每域地形、中心线100m/300m邻域、两侧边界、端界的最小/10分位/中位/90分位/最大值。邻域也是几何缓冲区，未划分真实河岸；这些统计不等于河槽糙率、河宽或洪泛区完整性证明。

![候选域、端界与纵横剖面对比]({links('domain_preview.png')})

## 5. 上下游和侧向边界如何确认

6条红色端盖与各候选走廊的端边重合，各只穿主线一次，并覆盖两侧候选洪泛走廊。**几何上可设置端边界，水力上尚未能最终确定**。JSON记录端盖中心及两端UTM/经纬度；GeoPackage可直接在QGIS叠加核查。

所有方案的上游边界候选集合为A/B，下游候选集合也为A/B；需在外部可靠证据确认总体流向后才能互斥分配。不能因为A更西、里程较小、OSM先出现或DEM出现平台，就直接写A=上游。后续应由有来源的河网流向/水文站关系/实际边界记录核对；本轮未搜索或下载这些证据。

端盖沿河段端点法向，从走廊多边形提取实际端边。弯道处缓冲区重叠会缩短一侧，C02 的 B 端尤其明显。端盖附近仍需核查桥梁、闸坝、主槽偏移、回流和两侧溢流通路，再决定边界是否外延以及适用的边界类型。

侧界只是恒距筛选边，未沿完整分水岭或堤顶追踪。C03比西段具有更多高地约束，但L侧低口仍必须人工核查，不能直接设为反射墙。即便是高地，是否可作封闭边界也取决于未来水位与最大淹没范围；当前没有该范围依据，故不宣称已闭合洪泛区。

## 6. 对七个问题的明确回答

1. **课程设计优先哪个？** 推荐C03作为待确认的起点：7km连续河段、约{cs[2]['area_km2']:.2f}km²，约AOI的{cs[2]['aoi_area_fraction']*100:.1f}%；有效DEM完整，距现有朝阳溪较远；与西段方案相比，两侧更多地形高地可供后续调整边界。C01适合更小规模的程序试验，但低平侧界截流风险较强；C02含未连接支流且约束更多，不优先。推荐不是用户已选定，也不是水力可用性最终验收。
2. **为什么不整个AOI高分辨率计算？** 全AOI约{aoi['area_projected_km2']:.2f}km²，主线33.68km，包含更多支流、侧向来流及未知边界。均匀30m等边三角形约{aoi['mesh_triangles_at_30m_equilateral']:,}个，而C03约{cs[2]['mesh_triangle_estimates_uniform_equilateral']['30']:,}个，面积量级相差约{aoi['area_projected_km2']/cs[2]['area_km2']:.1f}倍。更大域还增加资料、校准和运行成本，且网格加密不能补足河床缺失；实际运行时间未测量。
3. **DEM是否适合？** 适合当前候选域的地形筛查、宏观高地与洪泛地表分析，三个域触及像元100%有效；不充分支持可靠河槽输水能力、堤防精细越流和真实流速率定。不能据此挖深河床或赋值水位。
4. **河道与两岸是否连续？** 矢量主线连续且各域只包含一个连通选段；两侧地表剖面没有NoData断裂。地形数据覆盖连续不等于真实河床、堤防或水力通道连续，支流也未完全连接。
5. **上下游边界能合理设置吗？** A/B端盖在几何上可用，横跨候选走廊；总体流向、端界处水位/流量、过流结构和低地侧口缺少依据，暂不能最终指定上下游及边界类型。
6. **哪些位置人工确认？** 优先C03_A/B整条端盖及附近河道、C03_L最低样本位置和B端正偏移低地、L/R侧界所有潜在穿越通路、现有主线与实际主槽吻合程度；若改选C01/C02，另外核对朝阳溪的真实汇入关系。精确坐标见各方案表与JSON，GIS文件可直接定位；本轮不擅自命名桥闸或划定真实河岸。
7. **后续网格尺度？** 在C03上先评估主河道约60m、两侧洪泛地表90～120m的渐变三角网；关键弯道/确认的结构线附近可试30m并做网格敏感性比较，避免全域小于30m。60m均匀量级约{cs[2]['mesh_triangle_estimates_uniform_equilateral']['60']:,}个，实际混合网格未生成。60/30m只是数值离散尺度，不代表水下河床或堤防达到对应测量精度；最终尺度待真实河宽、边界和稳定性试验后确定。

## 7. 成果结构、复现与验证

{files}

candidate_model_domains.gpkg含`candidate_domains`（3个多边形）、`candidate_river_segments`（3条线）。boundary_candidates.gpkg含`end_boundary_candidates`（6条端界）、`terrain_cross_sections`（9条横剖面）、`lateral_boundary_review`（6条侧界）；全部EPSG:32649。没有指定真实入流、出流、左右岸，也没有修改高程。

复现脚本`scripts/prepare_hydrodynamic_domains.py`复用现有gis_processing.py，正常运行写入本阶段6个成果。再次复现请指定新的空输出目录和新的报告路径，脚本检测到目标文件已存在时会退出。

PowerShell在项目根执行（本轮已执行；原目标存在后再次运行会拒绝）：

```powershell
Set-Location '{root}'
& 'D:\\Arcgis10.8.2\\apps\\Python312\\python.exe' -B '.\\scripts\\prepare_hydrodynamic_domains.py'
```

可在同一PowerShell命令中附加 `--output-dir '新的空目录' --report-path '新的报告路径.md'` 做独立复现。脚本通过os.add_dll_directory只影响当前进程，不修改系统环境。没有安装依赖，没有修改README/PROJECT_SPEC/TASKS或旧验收报告。

已执行{data['validation']['check_count']}项检查：CRS/30m网格、掩膜一致、主线有效/连续、候选单一多边形且位于AOI、各域有效DEM全覆盖、单河段长度、端盖吻合与单次穿河、横剖面覆盖、原像元取值、2个GeoPackage图层和要素回读、CSV数值/空值回读、PNG解码及4项输入哈希不变。检查名称及前4个成果哈希存于JSON，JSON自身采用严格有限数值序列化并回读。

预览由现有DEM绘制，不使用在线地图，不构成灾时影像。没有运行ANUGA、网格生成、Phase 2/3处理脚本、前端构建或浏览器回归；本阶段没有前端改动。几何/读写验证不能替代水动力验证。

## 8. 阶段状态

**4.1.1候选分析完成；selected_candidate=null，等待用户确认C03或其他候选。** 本轮不开展4.1.2，不进行河床修正、来流编造、边界水位赋值或后续模拟。现有规范中的完整水动力模型限制未擅自更改。
'''


if __name__ == '__main__':
    main()
