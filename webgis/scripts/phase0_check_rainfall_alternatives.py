"""替代降雨源可用性检查：只取小样本和元数据，不替换项目默认数据源。"""
import csv,datetime as dt,hashlib,io,json,pathlib,urllib.parse
from phase0_acquire import ROOT,DOC,fetch,save_json
folder=DOC/'rainfall_alternatives'; folder.mkdir(exist_ok=True)
results={'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'候选来源可用性验证；不替换 IMERG，不推进阶段','sources':{}}
params={'latitude':22.79,'longitude':108.335,'start_date':'2024-09-06','end_date':'2024-09-13','hourly':'precipitation','models':'era5','timezone':'Asia/Shanghai','cell_selection':'nearest'}
url='https://archive-api.open-meteo.com/v1/archive?'+urllib.parse.urlencode(params)
try:
    data,_=fetch(url,'rainfall_alternatives/open_meteo',limit=200000)
    obj=json.loads(data); times=obj['hourly']['time']; values=obj['hourly']['precipitation']
    expected=[(dt.datetime(2024,9,6)+dt.timedelta(hours=i)).isoformat(timespec='minutes') for i in range(192)]
    check={'url':url,'status':'sample_downloaded','sample_kind':'固定 ERA5 再分析格点，不是站点实测或研究区面平均','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'returned_latitude':obj['latitude'],'returned_longitude':obj['longitude'],'timezone':obj['timezone'],'utc_offset_seconds':obj['utc_offset_seconds'],'unit':obj['hourly_units']['precipitation'],'count':len(times),'time_sequence_correct':times==expected,'missing_values':sum(v is None for v in values),'negative_values':sum(v is not None and v<0 for v in values),'first':times[0],'last':times[-1]}
    save_json(folder/'open_meteo_era5_sample.json',obj)
    results['sources']['open_meteo_era5']=check
except Exception as e: results['sources']['open_meteo_era5']={'url':url,'status':'failed','error':str(e)}
url='https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2024/'
try:
    data,_=fetch(url,'rainfall_alternatives/chirps_index',limit=400000)
    text=data.decode('utf-8')
    files=[f'chirps-v2.0.2024.09.{day:02d}.tif.gz' for day in range(6,14)]
    found=[name for name in files if name in text]
    (folder/'chirps_2024_index.html').write_bytes(data)
    results['sources']['chirps2']={'url':url,'status':'index_checked','requested_files':files,'found_files':found,'all_eight_listed':len(found)==8,'data_downloaded':False}
except Exception as e: results['sources']['chirps2']={'url':url,'status':'failed','error':str(e)}
url='https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv'
try:
    data,_=fetch(url,'rainfall_alternatives/noaa_station_history',limit=5000000)
    stations=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    matching=[s for s in stations if 'NANNING' in s.get('STATION NAME','').upper()]
    save_json(folder/'noaa_nanning_station_metadata.json',matching)
    results['sources']['noaa_gsod']={'status':'station_index_checked','station_history_url':url,'stations':matching,'checked_stations':[]}
    for s in matching[:3]:
        ident=s['USAF']+s['WBAN']; target='https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/2024/'+ident+'.csv'
        try:
            raw,_=fetch(target,'rainfall_alternatives/noaa_'+ident,limit=500000)
            rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            dates={f'2024-09-{i:02d}' for i in range(6,14)}
            selected=[r for r in rows if r['DATE'] in dates]
            (folder/('noaa_'+ident+'_2024.csv')).write_bytes(raw)
            valid=[r for r in selected if r.get('PRCP') not in [None,'','99.99','999.9']]
            results['sources']['noaa_gsod']['checked_stations'].append({'id':ident,'url':target,'sample_bytes':len(raw),'selected_days':len(selected),'valid_precip_days':len(valid),'station_latitude':selected[0]['LATITUDE'] if selected else s.get('LAT'),'station_longitude':selected[0]['LONGITUDE'] if selected else s.get('LON'),'selected_precip_fields':[{'date':r['DATE'],'PRCP':r.get('PRCP'),'PRCP_ATTRIBUTES':r.get('PRCP_ATTRIBUTES')} for r in selected]})
        except Exception as e: results['sources']['noaa_gsod']['checked_stations'].append({'id':ident,'url':target,'error':str(e)})
except Exception as e: results['sources']['noaa_gsod']={'url':url,'status':'failed','error':str(e)}
save_json(folder/'availability_checks.json',results)
print(json.dumps(results,ensure_ascii=True,indent=2))