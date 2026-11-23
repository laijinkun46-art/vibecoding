"""Phase 0：获取公开元数据与河流；按字节范围检查 FABDEM，禁止自动下载完整压缩包。
使用系统 curl 的 TLS 验证，既不携带凭据也不跳过认证。
"""
import argparse, datetime as dt, hashlib, io, json, pathlib, struct, subprocess, urllib.parse, zipfile, zlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs'
BASE = 'https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/'
ZIP_URL = BASE + 'N20E100-N30E110_FABDEM_V1-2.zip'
BBOX = [108.23, 22.73, 108.44, 22.85]
STATE = DOC / 'phase0_acquisition.json'

def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def fetch(url, label, limit=2_000_000, byte_range=None, post=None, timeout=45):
    """返回原始响应字节和响应头；限制下载大小，不禁用证书验证。"""
    header = DOC / (label + '.headers.txt')
    cmd = ['curl.exe', '-f', '-sS', '-L', '--connect-timeout', '12', '--max-time', str(timeout), '--max-filesize', str(limit), '-D', str(header), '-H', 'User-Agent: Nanning-WebGIS-course-data-check/0.1']
    if byte_range:
        cmd += ['--range', byte_range, '-H', 'Accept-Encoding: identity']
    if post:
        cmd += ['--data-urlencode', 'data=' + post]
    result = subprocess.run(cmd + [url], capture_output=True)
    headers = header.read_text(encoding='utf-8', errors='replace') if header.exists() else ''
    if result.returncode:
        raise RuntimeError(f'curl exit {result.returncode}: {result.stderr.decode(errors="replace")[:300]}')
    if len(result.stdout) > limit:
        raise RuntimeError('响应超过体积上限')
    return result.stdout, headers

def metadata():
    if STATE.exists():
        raise RuntimeError('已有获取记录，拒绝覆盖；续传请运行 phase0_dem_chunks.py，清单更新请运行 phase0_inventory.py')
    state = {'checked_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'bbox_wsen': BBOX, 'dem': {}, 'rainfall': {}, 'rivers': {}}
    for name in ['readme.txt', 'license.txt']:
        try:
            data, _ = fetch(BASE + name, 'fabdem_' + name.split('.')[0], limit=100000)
            path = ROOT / 'data/raw/dem' / name
            if not path.exists(): path.write_bytes(data)
            state['dem'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'url': BASE + name}
        except Exception as e: state['dem'][name] = {'error': str(e)}
    try:
        data, headers = fetch(ZIP_URL, 'fabdem_zip_tail', 200000, '-131072')
        import re
        ranges = re.findall(r'Content-Range:\s*bytes\s+(\d+)-(\d+)/(\d+)', headers, re.I)
        if not ranges: raise RuntimeError('服务器未返回 Content-Range，拒绝下载完整 ZIP')
        start, end, total = map(int, ranges[-1])
        pos = data.rfind(b'PK\x05\x06')
        if pos < 0: raise RuntimeError('没有找到 ZIP 目录结束标记')
        eocd = struct.unpack_from('<4s4H2LH', data, pos)
        count, cd_size, cd_offset = eocd[4], eocd[5], eocd[6]
        cd = data[cd_offset-start:cd_offset-start+cd_size] if cd_offset >= start else fetch(ZIP_URL, 'fabdem_zip_directory', 200000, f'{cd_offset}-{cd_offset+cd_size-1}')[0]
        entries, at = [], 0
        for _ in range(count):
            entry = struct.unpack_from('<4s6H3L5H2L', cd, at)
            if entry[0] != b'PK\x01\x02': raise RuntimeError('ZIP 中央目录格式错误')
            name = cd[at+46:at+46+entry[10]].decode('utf-8')
            if 'N22E108' in name:
                entries.append({'name': name, 'compressed_bytes': entry[8], 'uncompressed_bytes': entry[9], 'offset': entry[16], 'method': entry[4], 'crc32': entry[7]})
            at += 46 + entry[10] + entry[11] + entry[12]
        state['dem']['archive'] = {'url': ZIP_URL, 'total_bytes': total, 'http_range_verified': True, 'matching_entries': entries}
    except Exception as e: state['dem']['archive'] = {'url': ZIP_URL, 'error': str(e)}
    query = '[out:json][timeout:25][date:"2024-09-13T16:00:00Z"];way["waterway"="river"](22.73,108.23,22.85,108.44);out meta geom;'
    (ROOT / 'scripts/overpass_rivers.ql').write_text(query + '\n', encoding='utf-8')
    attempts = []
    for i, endpoint in enumerate(['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter']):
        try:
            data, _ = fetch(endpoint, 'osm_rivers_' + str(i), limit=8_000_000, post=query)
            obj = json.loads(data)
            if obj.get('remark'): raise RuntimeError(obj['remark'])
            ways = [el for el in obj.get('elements', []) if el.get('type') == 'way' and el.get('geometry')]
            if not ways: raise RuntimeError('查询结果没有河流几何')
            path = ROOT / 'data/raw/rivers/osm_rivers_20240913.json'
            if not path.exists(): path.write_bytes(data)
            state['rivers'] = {'status': 'downloaded', 'endpoint': endpoint, 'snapshot_utc': '2024-09-13T16:00:00Z', 'ways': len(ways), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'attribution': '© OpenStreetMap contributors, ODbL', 'attempts': attempts}
            break
        except Exception as e: attempts.append({'endpoint': endpoint, 'error': str(e)})
    else: state['rivers'] = {'status': 'unavailable', 'attempts': attempts}
    params = {'short_name': 'GPM_3IMERGHH', 'version': '07', 'temporal': '2024-09-05T16:00:00Z,2024-09-13T15:59:59Z', 'bounding_box': ','.join(map(str, BBOX)), 'page_size': '1', 'sort_key': 'start_date'}
    url = 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urllib.parse.urlencode(params)
    try:
        data, headers = fetch(url, 'imerg_cmr', limit=2_000_000)
        obj = json.loads(data)
        save_json(DOC / 'imerg_granule_sample.json', obj)
        import re
        hits = re.findall(r'CMR-Hits:\s*(\d+)', headers, re.I)
        samples = []
        for item in obj.get('feed', {}).get('entry', []):
            samples.append({key: item.get(key) for key in ['title','time_start','time_end','granule_size','links','boxes']})
        state['rainfall'] = {'status': 'metadata_only', 'query_url': url, 'expected_half_hour_intervals': 384, 'cmr_hits': int(hits[-1]) if hits else None, 'samples': samples}
    except Exception as e: state['rainfall'] = {'status': 'unavailable', 'query_url': url, 'error': str(e)}
    save_json(STATE, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))

def download_dem():
    state = json.loads(STATE.read_text(encoding='utf-8'))
    matches = state['dem']['archive']['matching_entries']
    if len(matches) != 1: raise RuntimeError('无法唯一确定目标分幅')
    item = matches[0]
    if item['compressed_bytes'] > 80_000_000: raise RuntimeError('目标超过 80 MB，需要重新报告体积')
    target = ROOT / 'data/raw/dem' / pathlib.Path(item['name']).name
    if target.exists(): raise RuntimeError('原始分幅已存在，拒绝覆盖')
    head, _ = fetch(ZIP_URL, 'fabdem_local_header', 1000, f"{item['offset']}-{item['offset']+29}")
    local = struct.unpack('<4s5H3L2H', head)
    if local[0] != b'PK\x03\x04': raise RuntimeError('ZIP 本地头无效')
    offset = item['offset'] + 30 + local[-2] + local[-1]
    packed, headers = fetch(ZIP_URL, 'fabdem_tile_range', item['compressed_bytes'] + 1, f"{offset}-{offset+item['compressed_bytes']-1}", timeout=180)
    if 'content-range:' not in headers.lower() or len(packed) != item['compressed_bytes']: raise RuntimeError('分段下载长度或响应头不符')
    if item['method'] == 8: unpacked = zlib.decompress(packed, -15)
    elif item['method'] == 0: unpacked = packed
    else: raise RuntimeError('不支持的 ZIP 压缩方法')
    if len(unpacked) != item['uncompressed_bytes'] or zlib.crc32(unpacked) & 0xffffffff != item['crc32']: raise RuntimeError('ZIP CRC32/大小校验失败')
    target.write_bytes(unpacked)
    state['dem']['download'] = {'file': str(target.relative_to(ROOT)), 'bytes': len(unpacked), 'sha256': hashlib.sha256(unpacked).hexdigest(), 'zip_crc32_verified': True, 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    save_json(STATE, state)
    print(json.dumps(state['dem']['download'], ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['metadata','download-dem'])
    action = parser.parse_args().action
    metadata() if action == 'metadata' else download_dem()