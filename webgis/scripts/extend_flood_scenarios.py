"""在独立目录生成新增静态水位、相邻比较和对应网页资产。"""
import json
import os
from pathlib import Path

# 启动本机已有的 ArcGIS GIS Python 时加载其 GDAL DLL。
if os.name == 'nt' and (arcgis_bin := Path(r'D:\Arcgis10.8.2\bin')).is_dir():
    gis_dll = os.add_dll_directory(str(arcgis_bin))

from osgeo import gdal

from export_web_layers import export_paths
from gis_processing import digest, save_json
from phase3_analyze import OUT as BASE, ROOT, main as analyze

CONFIG = ROOT / 'data/scenarios/flood_scenarios_extension_v1.json'
OUT = ROOT / 'data/processed/phase3_extension_v1'
WEB = ROOT / 'frontend/public/analysis/expanded_v1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    if OUT.exists() or WEB.exists():
        raise FileExistsError('扩展情景目录已存在，请保留已有成果并使用独立版本')
    gdal.SetConfigOption('GDAL_PAM_ENABLED', 'NO')
    baseline = load(ROOT / 'docs/phase3_processing.json')
    accepted = {key.replace(chr(92), '/'): v['sha256'] for key, v in baseline['outputs'].items()}
    summary_path = BASE / 'summary.json'
    base_scenarios = load(summary_path)['scenarios']
    legacy = {row['id']: BASE / f"{row['id']}_wet.tif" for row in base_scenarios}
    for path in [summary_path, *legacy.values()]:
        if digest(path) != accepted[path.relative_to(ROOT).as_posix()]:
            raise ValueError(f'原情景文件与验收指纹不一致：{path.name}')

    manifest_path = OUT / 'manifest.json'
    analyze(CONFIG, OUT, manifest_path, legacy_masks=legacy)
    manifest = load(manifest_path)
    added = manifest['summary']
    records = {row['id']: row for row in [*base_scenarios, *added['scenarios']]}
    for row in added['comparisons']:
        before, after = (records[row[key]] for key in ('before', 'after'))
        if (before['wet_pixels'] != row['persistent_pixels'] + row['receded_pixels']
                or after['wet_pixels'] != row['persistent_pixels'] + row['added_pixels']):
            raise ValueError(f"对比掩膜与情景统计不一致：{row['id']}")
        rising = after['water_level_m'] > before['water_level_m']
        if (rising and row['receded_pixels']) or (not rising and row['added_pixels']):
            raise ValueError(f"连通范围与水位趋势不一致：{row['id']}")

    WEB.mkdir(parents=True)
    # 发布前逐资产核对源指纹，网页副本只去掉 JSON 排版空白。
    paths = [OUT / 'summary.json', *sorted(OUT.glob('*.geojson'))]
    catalog = export_paths(paths, manifest['outputs'], WEB, '/analysis/expanded_v1')
    catalog['playback_order'] = load(CONFIG)['playback_order']
    save_json(WEB / 'catalog.json', catalog)
    print('新增情景、水位和面积：', [(r['id'], r['water_level_m'], r['area_km2']) for r in added['scenarios']])
    print('新增比较：', len(added['comparisons']))


if __name__ == '__main__':
    main()
