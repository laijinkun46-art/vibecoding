"""用已有 requests 客户端补查 HTTPS；始终启用证书验证，不覆盖原始数据。"""
import datetime, hashlib, json, pathlib, requests
ROOT=pathlib.Path(__file__).resolve().parents[1]
query=(ROOT/'scripts/overpass_rivers.ql').read_text(encoding='utf-8').strip().replace('[date:"2024-09-13T16:00:00Z"]','')
report={'attempts':[],'status':'unavailable'}
for endpoint in ['https://overpass.private.coffee/api/interpreter']:
    try:
        response=requests.get(endpoint,params={'data':query},headers={'User-Agent':'Nanning-WebGIS-course-data-check/0.1'},timeout=(10,35))
        response.raise_for_status()
        if len(response.content)>8_000_000: raise RuntimeError('响应超过上限')
        obj=response.json()
        if obj.get('remark'): raise RuntimeError(obj['remark'])
        ways=[x for x in obj.get('elements',[]) if x.get('type')=='way' and x.get('geometry')]
        if not ways: raise RuntimeError('没有河流几何')
        path=ROOT/'data/raw/rivers/osm_rivers_current.json'
        if path.exists(): raise RuntimeError('原文件已存在，未覆盖')
        path.write_bytes(response.content)
        report.update(status='downloaded',endpoint=endpoint,snapshot_utc=obj.get('osm3s',{}).get('timestamp_osm_base'), historical_2024=False,ways=len(ways),bytes=len(response.content),sha256=hashlib.sha256(response.content).hexdigest(),attribution='© OpenStreetMap contributors, ODbL')
        break
    except Exception as error: report['attempts'].append({'endpoint':endpoint,'error':str(error)[:400]})
(ROOT/'docs/river_retry_current_result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))