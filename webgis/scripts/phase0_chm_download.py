"""获取官方 CHM_PRE V2 年文件。保留可续传缓存，验证长度、MD5，禁止覆盖原始数据。"""
import datetime as dt,hashlib,json,pathlib,re,shutil,time
import requests
ROOT=pathlib.Path(__file__).resolve().parents[1]
META=json.loads((ROOT/'docs/rainfall_alternatives/chm_pre_2024_metadata.json').read_text(encoding='utf-8'))
F=META['files_2024'][0]; SIZE=F['size']; MD5=F['checksum'].split(':')[1]
URL='https://zenodo.org/records/20378336/files/CHM_PRE_V2_daily_2024.nc?download=1'
cache=ROOT/'data/.download_cache/chm_pre_2024.nc.part'
cache.parent.mkdir(parents=True,exist_ok=True)
target=ROOT/'data/raw/rainfall'/F['key']
if target.exists():
    if target.stat().st_size!=SIZE or hashlib.md5(target.read_bytes()).hexdigest()!=MD5: raise RuntimeError('原文件存在但校验不同，未覆盖')
    print('Existing original file verified',flush=True)
else:
    if shutil.disk_usage(ROOT).free<SIZE*2: raise RuntimeError('剩余空间不足')
    failures=0; session=requests.Session(); last_print=0; began=time.monotonic()
    while (cache.stat().st_size if cache.exists() else 0)<SIZE:
        start=cache.stat().st_size if cache.exists() else 0
        try:
            with session.get(URL,headers={'Range':f'bytes={start}-{SIZE-1}','Accept-Encoding':'identity','User-Agent':'Nanning-WebGIS-course-data-check/0.1'},stream=True,timeout=(15,45)) as response:
                response.raise_for_status()
                expected=f'bytes {start}-{SIZE-1}/{SIZE}'
                if response.status_code!=206 or response.headers.get('Content-Range')!=expected: raise RuntimeError('响应字节范围不符，停止避免写入错误内容')
                with cache.open('ab') as handle:
                    for block in response.iter_content(chunk_size=1024*1024):
                        if not block: continue
                        if handle.tell()+len(block)>SIZE: raise RuntimeError('响应超过官方文件长度')
                        handle.write(block); handle.flush()
                        if handle.tell()-last_print>=16*1024*1024:
                            last_print=handle.tell()
                            print(f'{handle.tell()}/{SIZE} bytes ({100*handle.tell()/SIZE:.1f}%), elapsed {time.monotonic()-began:.1f}s',flush=True)
            failures=0
        except Exception as error:
            failures+=1; print(f'retry {failures}: {error}',flush=True)
            if failures>=3: raise
    digest=hashlib.md5(cache.read_bytes()).hexdigest()
    if cache.stat().st_size!=SIZE or digest!=MD5: raise RuntimeError('下载的长度或 MD5 校验失败，不纳入原始数据')
    if target.exists(): raise RuntimeError('目标在下载期间已出现，拒绝覆盖')
    cache.rename(target)
provenance={'dataset':'CHM_PRE V2','repository_version':META['version'],'doi':META['doi'],'url':URL,'file':target.relative_to(ROOT).as_posix(),'bytes':target.stat().st_size,'expected_bytes':SIZE,'md5':hashlib.md5(target.read_bytes()).hexdigest(),'expected_md5':MD5,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'downloaded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'license':'CC BY 4.0','method':'原始官方年文件，通过 HTTPS 分段续传；保留证书验证'}
(ROOT/'docs/chm_pre/download_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(provenance,ensure_ascii=True,indent=2),flush=True)