"""Build the stage replay from the accepted four-connected static flood masks."""
import heapq
import json
import os
from pathlib import Path

if os.name == 'nt' and (bin_dir := Path(r'D:\Arcgis10.8.2\bin')).is_dir():
    gis_dll = os.add_dll_directory(str(bin_dir))

import numpy as np
from osgeo import gdal

from gis_processing import digest, save_json, valid_pixels

ROOT = Path(__file__).resolve().parents[1]
PHASE2 = ROOT / 'data/processed/phase2'
OUT = ROOT / 'frontend/public/analysis/stage_replay_v1'
NODATA_CODE = (1 << 24) - 1
STAGE_ORIGIN = 32
STAGE_SCALE = 1 << 18


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def activation_thresholds(dem, valid, seeds, ceiling):
    """A pixel wets above the lowest crest that connects it to a river seed."""
    rows, cols = dem.shape
    levels = dem.ravel()
    allowed = (valid & (dem < ceiling)).ravel()
    activation = np.full(len(levels), np.inf, dtype=np.float32)
    indices = np.flatnonzero(seeds.ravel() & allowed)
    queue = [(float(levels[i]), int(i)) for i in indices]
    for height, i in queue:
        activation[i] = height
    heapq.heapify(queue)
    while queue:
        height, i = heapq.heappop(queue)
        if height != activation[i]:
            continue
        row, col = divmod(i, cols)
        adjacent = (
            i - cols if row else -1, i + cols if row < rows-1 else -1,
            i - 1 if col else -1, i + 1 if col < cols-1 else -1,
        )
        for j in adjacent:
            if j >= 0 and allowed[j]:
                required = max(height, float(levels[j]))
                if required < activation[j]:
                    activation[j] = required
                    heapq.heappush(queue, (required, j))
    return activation.reshape(dem.shape)


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    gdal.UseExceptions()
    gdal.SetConfigOption('GDAL_PAM_ENABLED', 'NO')
    dem_path = PHASE2 / 'dem_utm49n_30m.tif'
    seed_path = PHASE2 / 'main_river_mask.tif'
    phase2 = load(ROOT / 'docs/phase2_processing.json')['outputs']
    base_dir = ROOT / 'data/processed/phase3'
    extended_dir = ROOT / 'data/processed/phase3_extension_v1'
    groups = [(base_dir, load(ROOT / 'docs/phase3_processing.json')['outputs'])]
    if extended_dir.is_dir():
        groups.append((extended_dir, load(extended_dir/'manifest.json')['outputs']))
    sources = {}

    def checked(path, records):
        relative = path.relative_to(ROOT).as_posix()
        reference = next(v['sha256'] for name, v in records.items() if name.replace(chr(92),'/') == relative)
        if digest(path) != reference:
            raise ValueError(f'源文件指纹不一致：{relative}')
        sources[relative] = reference

    for path in (dem_path,seed_path):
        checked(path,phase2)
    dem_ds = gdal.Open(str(dem_path),gdal.GA_ReadOnly)
    seed_ds = gdal.Open(str(seed_path),gdal.GA_ReadOnly)
    gt = dem_ds.GetGeoTransform()
    if gt[2] or gt[4] or gt[1]!=30 or gt[5]!=-30 or dem_ds.GetSpatialRef().GetAuthorityCode(None)!='32649':
        raise ValueError('回放要求已有 EPSG:32649 的 30 m 网格')
    if seed_ds.GetGeoTransform()!=gt or seed_ds.GetProjection()!=dem_ds.GetProjection():
        raise ValueError('河道种子与 DEM 网格不同')
    dem, valid = valid_pixels(dem_ds)
    seeds = seed_ds.ReadAsArray() == 1
    originals = {row['id']:row['water_level_m'] for row in load(base_dir/'summary.json')['scenarios']}
    keys = [[0, originals['S01']], [.32, originals['S02']], [.60, originals['S03']], [1, originals['S04']]]
    activation = activation_thresholds(dem, valid, seeds, max(originals.values()))
    finite = np.isfinite(activation)
    cols, rows = dem_ds.RasterXSize, dem_ds.RasterYSize
    stats = {}
    for folder,records in groups:
        checked(folder/'summary.json',records)
        for row in load(folder/'summary.json')['scenarios']:
            sid, level = row['id'], row['water_level_m']
            path = folder / f'{sid}_wet.tif'
            checked(path,records)
            expected = gdal.Open(str(path),gdal.GA_ReadOnly).ReadAsArray()==1
            wet = activation < level
            if not np.array_equal(wet,expected):
                raise ValueError(f'连续阈值与已验收情景不一致：{sid}')
            stats[sid] = {'stage_m':level,'wet_pixels':int(wet.sum()),'wet_km2':row['area_km2']}

    codes = np.full(activation.shape, NODATA_CODE, dtype=np.uint32)
    if activation[finite].min() < STAGE_ORIGIN:
        raise ValueError('阈值超出演示编码区间')
    codes[finite] = (activation[finite].astype(np.float64)-STAGE_ORIGIN)*STAGE_SCALE
    if not np.array_equal(codes[finite]/STAGE_SCALE+STAGE_ORIGIN,activation[finite]):
        raise ValueError('图层阈值编码精度不足')

    # Exact cumulative area, on the original projected grid.
    levels, counts = np.unique(activation[finite], return_counts=True)
    bins = np.empty(len(levels),dtype=[('level','<f4'),('count','<u4')])
    bins['level'] = levels
    bins['count'] = np.cumsum(counts)
    source = gdal.GetDriverByName('MEM').Create('',cols,rows,3,gdal.GDT_Byte)
    for band, shift in enumerate((16,8,0),1):
        source.GetRasterBand(band).WriteArray(((codes>>shift)&255).astype(np.uint8))
    OUT.mkdir(parents=True)
    image = OUT/'activation.png'
    output = gdal.GetDriverByName('PNG').CreateCopy(str(image),source)
    output = None
    table = OUT/'areas.bin'
    bins.tofile(table)
    metadata = {'kind':'static_connected_stage_replay','crs':'EPSG:32649','vertical_datum':'EGM2008',
                'grid_bounds':[gt[0],gt[3]+rows*gt[5],gt[0]+cols*gt[1],gt[3]],
                'cols':cols,'rows':rows,'cell_area_m2':900,'duration_s':12,'stages':keys,
                'encoding':{'origin_m':STAGE_ORIGIN,'ticks_per_m':STAGE_SCALE,'nodata':NODATA_CODE},
                'assets':{p.name:{'url':'/analysis/stage_replay_v1/'+p.name,'bytes':p.stat().st_size,
                                  'sha256':digest(p)} for p in (image,table)},
                'sources_sha256':sources,'validated_scenarios':stats}
    save_json(OUT/'manifest.json',metadata)
    print(f'{len(stats)} original scenarios verified, {int(finite.sum())} peak pixels, {len(levels)} exact thresholds')


if __name__=='__main__':
    main()
