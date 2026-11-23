"""仅在 Overpass 不可用时，用 OSM 公共主站小范围地图查询获取当前河流参考。"""
import datetime as dt, hashlib, json, pathlib, xml.etree.ElementTree as ET
from phase0_acquire import ROOT, DOC, fetch, save_json
url='https://www.openstreetmap.org/api/0.6/map?bbox=108.30,22.79,108.33,22.82'
result={'status':'unavailable','url':url,'historical_2024':False,'requested_bbox':[108.30,22.79,108.33,22.82]}
try:
    data,_=fetch(url,'osm_main_api',limit=5_000_000,timeout=45)
    root=ET.fromstring(data)
    if root.tag!='osm': raise RuntimeError('响应不是 OSM XML')
    path=ROOT/'data/raw/rivers/osm_map_context_current.osm'
    if path.exists(): raise RuntimeError('原始响应文件已存在，未覆盖')
    path.write_bytes(data)
    nodes={n.attrib['id']:[float(n.attrib['lon']),float(n.attrib['lat'])] for n in root.findall('node')}
    features=[]; riverways=[]
    for way in root.findall('way'):
        tags={t.attrib['k']:t.attrib['v'] for t in way.findall('tag')}
        if tags.get('waterway')!='river': continue
        refs=[n.attrib['ref'] for n in way.findall('nd')]
        if any(n not in nodes for n in refs): raise RuntimeError('河流节点坐标不全')
        coords=[nodes[n] for n in refs]
        if len(coords)<2: continue
        riverways.append({'id':way.attrib['id'],'nodes':refs,'tags':tags,'geometry':coords,'timestamp':way.attrib.get('timestamp')})
        features.append({'type':'Feature','properties':{'osm_way_id':way.attrib['id'],**tags,'source_kind':'OSM current API, not 2024 observation'},'geometry':{'type':'LineString','coordinates':coords}})
    save_json(DOC/'osm_main_api_river_ways.json',riverways)
    save_json(ROOT/'data/processed/rivers_osm_current.geojson',{'type':'FeatureCollection','features':features})
    if not features: raise RuntimeError('地图返回有效，但小范围内没有 waterway=river 中心线')
    result.update(status='downloaded',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),raw_file=str(path.relative_to(ROOT)),river_ways=len(riverways),downloaded_utc=dt.datetime.now(dt.timezone.utc).isoformat(),names=sorted(set(w['tags'].get('name','') for w in riverways)),attribution='© OpenStreetMap contributors, ODbL')
except Exception as e: result['error']=str(e)
save_json(DOC/'osm_main_api_result.json',result)
print(json.dumps(result,ensure_ascii=True,indent=2))