"""探测 CHM_PRE 官方文件的字节范围支持；不下载年度大文件。"""
import datetime as dt,json,pathlib,requests
ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'docs/chm_pre'; out.mkdir(exist_ok=True)
urls=['https://zenodo.org/records/20378336/files/CHM_PRE_V2_daily_2024.nc?download=1','https://zenodo.org/api/records/20378336/files/CHM_PRE_V2_daily_2024.nc/content']
results=[]
for i,url in enumerate(urls):
    item={'url':url,'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        with requests.get(url,headers={'Range':'bytes=0-65535','Accept-Encoding':'identity','User-Agent':'Nanning-WebGIS-course-data-check/0.1'},stream=True,timeout=(12,35)) as r:
            item.update(status=r.status_code,content_range=r.headers.get('Content-Range'),content_length=r.headers.get('Content-Length'),content_type=r.headers.get('Content-Type'))
            r.raise_for_status()
            if r.status_code!=206: raise RuntimeError('服务器未返回部分内容；停止读取大文件')
            data=r.raw.read(65537)
            if len(data)!=65536: raise RuntimeError('探测内容长度不符')
            item.update(bytes=len(data),magic_hex=data[:8].hex())
            (out/'header_64k.bin').write_bytes(data)
            results.append(item)
            break
    except Exception as e: item['error']=str(e); results.append(item)
(out/'range_probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=True,indent=2))