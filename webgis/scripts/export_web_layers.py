"""将已验收成果整理为网页静态资源；不重新计算、平滑或简化分析几何。"""
import json
from pathlib import Path
from gis_processing import digest, save_json

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'frontend/public/analysis'


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    phase2 = json.loads((ROOT / 'docs/phase2_processing.json').read_text(encoding='utf-8'))
    phase3 = json.loads((ROOT / 'docs/phase3_processing.json').read_text(encoding='utf-8'))
    paths = [ROOT / 'data/processed/phase3/summary.json', ROOT / 'data/processed/phase2/rainfall_timeseries.json',
             ROOT / 'data/processed/phase2/rivers_wgs84.geojson']
    paths += sorted((ROOT / 'data/processed/phase3').glob('*.geojson'))
    catalog = export_paths(paths, phase2['outputs'] | phase3['outputs'], DEST, '/analysis')
    save_json(DEST / 'catalog.json', catalog)
    save_json(ROOT / 'docs/phase4_export_checks.json', {'passed': True, 'asset_count': len(paths), 'catalog': catalog})
    print('网页成果导出并逐项回读验证通过：', len(paths))


def export_paths(paths, output_records, dest, url_base):
    catalog = {'kind': 'hypothetical_scenario_not_observation', 'assets': {}}
    for path in paths:
        key = str(path.relative_to(ROOT))
        record = output_records.get(key)
        if record is None or digest(path) != record['sha256']:
            raise ValueError('源成果与验收清单不一致：'+key)
        value = json.loads(path.read_text(encoding='utf-8'))
        target = dest / path.name
        # 仅去掉排版空白，保留全部坐标精度、孔洞、分类和属性。
        target.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        if json.loads(target.read_text(encoding='utf-8')) != value:
            raise ValueError('网页副本与源数据不同')
        catalog['assets'][path.stem] = {'url': url_base+'/'+path.name, 'sha256': digest(target),
                                      'bytes': target.stat().st_size, 'source': key, 'source_sha256': record['sha256']}
    return catalog


if __name__ == '__main__':
    main()
