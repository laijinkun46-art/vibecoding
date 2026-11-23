"""补查逐小时降雨的累计时段；检查 CHIRPS v3 的实际目录。"""
import datetime as dt,hashlib,json,urllib.parse
from phase0_acquire import DOC,fetch,save_json
folder=DOC/'rainfall_alternatives'
params={'latitude':22.79,'longitude':108.335,'start_date':'2024-09-06','end_date':'2024-09-14','hourly':'precipitation','models':'era5','timezone':'Asia/Shanghai','cell_selection':'nearest'}
url='https://archive-api.open-meteo.com/v1/archive?'+urllib.parse.urlencode(params)
result={}
try:
    data,_=fetch(url,'rainfall_alternatives/open_meteo_aligned',limit=200000)
    obj=json.loads(data)
    save_json(folder/'open_meteo_era5_extended_response.json',obj)
    start=dt.datetime(2024,9,6); end=dt.datetime(2024,9,14)
    items=[{'interval_start_local':(dt.datetime.fromisoformat(t)-dt.timedelta(hours=1)).isoformat(timespec='minutes'),'interval_end_local':t,'precipitation_mm':v} for t,v in zip(obj['hourly']['time'],obj['hourly']['precipitation']) if start<dt.datetime.fromisoformat(t)<=end]
    expected=[(start+dt.timedelta(hours=i+1)).isoformat(timespec='minutes') for i in range(192)]
    result['open_meteo_aligned']={'url':url,'count':len(items),'interval_sequence_correct':[x['interval_end_local'] for x in items]==expected,'missing':sum(x['precipitation_mm'] is None for x in items),'negative':sum(x['precipitation_mm'] is not None and x['precipitation_mm']<0 for x in items),'first':items[0],'last':items[-1],'units':obj['hourly_units']['precipitation'],'grid_latitude':obj['latitude'],'grid_longitude':obj['longitude'],'kind':'ERA5 0.25° 再分析格点试样；不是雨量站实测或研究区面平均','raw_response_sha256':hashlib.sha256(data).hexdigest(),'raw_response_bytes':len(data)}
    save_json(folder/'open_meteo_era5_aligned_intervals.json',items)
except Exception as e: result['open_meteo_aligned']={'error':str(e)}
url='https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/2024/'
try:
    data,_=fetch(url,'rainfall_alternatives/chirps3_index',limit=500000)
    text=data.decode('utf-8'); import re
    links=re.findall(r'href="([^"]+)"',text)
    selected=[x for x in links if any(f'2024.09.{i:02d}' in x or f'202409{i:02d}' in x or f'2024-09-{i:02d}' in x for i in range(6,14))]
    (folder/'chirps3_2024_index.html').write_bytes(data)
    result['chirps3']={'url':url,'status':'index_checked','matching_files':selected,'raster_data_downloaded':False}
except Exception as e: result['chirps3']={'url':url,'status':'failed','error':str(e)}
save_json(folder/'detail_checks.json',result)
print(json.dumps(result,ensure_ascii=True,indent=2))