"""Phase 0：构建 IMERG 文件清单、检验时间连续性；补试 OSM 历史河流服务。"""
import datetime as dt, hashlib, json, pathlib, subprocess, urllib.parse
from phase0_acquire import ROOT, DOC, STATE, BBOX, fetch, save_json
state = json.loads(STATE.read_text(encoding='utf-8'))
params = {'collection_concept_id':'C2723754847-GES_DISC','temporal':'2024-09-05T16:00:00Z,2024-09-13T15:59:59Z','bounding_box':','.join(map(str,BBOX)),'page_size':'400','sort_key':'start_date'}
url='https://cmr.earthdata.nasa.gov/search/granules.json?'+urllib.parse.urlencode(params)
try:
    data, headers=fetch(url,'imerg_cmr_full',limit=10_000_000)
    entries=json.loads(data)['feed']['entry']
    items=[]
    for item in entries:
        downloads=[link['href'] for link in item.get('links',[]) if not link.get('inherited') and link.get('rel','').endswith('/data#') and link['href'].startswith('https:')]
        items.append({'title':item['title'],'start_utc':item['time_start'],'end_utc':item['time_end'],'size_mib':float(item['granule_size']),'download_url':downloads[0] if downloads else None})
    starts=[dt.datetime.fromisoformat(x['start_utc'].replace('Z','+00:00')) for x in items]
    start=dt.datetime(2024,9,5,16,tzinfo=dt.timezone.utc)
    expected={start+dt.timedelta(minutes=30*i) for i in range(384)}
    actual=set(starts)
    check={'count':len(items),'unique_starts':len(actual),'expected':384,'missing_start_utc':[x.isoformat() for x in sorted(expected-actual)],'unexpected_start_utc':[x.isoformat() for x in sorted(actual-expected)],'total_mib':sum(x['size_mib'] for x in items),'first':items[0]['start_utc'] if items else None,'last_end':items[-1]['end_utc'] if items else None,'downloaded_data_files':0,'authentication':'用户确认无 Earthdata 账号；本轮不开展认证或数据下载。'}
    save_json(DOC/'imerg_download_manifest.json',{'query_url':url,'interval_local':'[2024-09-06T00:00:00+08:00,2024-09-14T00:00:00+08:00)','check':check,'files':items})
    state['rainfall']['manifest_check']=check
    print('IMERG_MANIFEST',json.dumps(check,ensure_ascii=False))
except Exception as e:
    state['rainfall']['manifest_error']=str(e)
    print('IMERG_ERROR',str(e))
if state['rivers']['status'] != 'downloaded':
    query=(ROOT/'scripts/overpass_rivers.ql').read_text(encoding='utf-8').strip()
    attempts=state['rivers']['attempts']
    endpoint='https://maps.mail.ru/osm/tools/overpass/api/interpreter'
    try:
        data,_=fetch(endpoint+'?'+urllib.parse.urlencode({'data':query}),'osm_rivers_mailru',limit=8_000_000)
        obj=json.loads(data)
        if obj.get('remark'): raise RuntimeError(obj['remark'])
        ways=[x for x in obj.get('elements',[]) if x.get('type')=='way' and x.get('geometry')]
        if not ways: raise RuntimeError('没有河流几何')
        path=ROOT/'data/raw/rivers/osm_rivers_20240913.json'
        if path.exists(): raise RuntimeError('原始文件已存在，未覆盖')
        path.write_bytes(data)
        state['rivers']={'status':'downloaded','endpoint':endpoint,'snapshot_utc':'2024-09-13T16:00:00Z','ways':len(ways),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'attribution':'© OpenStreetMap contributors, ODbL','attempts':attempts}
        print('RIVERS',json.dumps(state['rivers'],ensure_ascii=False))
    except Exception as e:
        attempts.append({'endpoint':endpoint,'error':str(e)})
        state['rivers']['attempts']=attempts
        print('RIVERS_ERROR',str(e))
save_json(STATE,state)