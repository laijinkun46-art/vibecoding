"""按 1 MiB 分段、可续传获取 DEM；校验每个响应的字节范围及最终 CRC32。"""
import datetime as dt, hashlib, json, pathlib, struct, zlib
from phase0_acquire import ROOT, DOC, STATE, ZIP_URL, fetch, save_json
state=json.loads(STATE.read_text(encoding='utf-8'))
item=state['dem']['archive']['matching_entries'][0]
if item['compressed_bytes']>80_000_000: raise RuntimeError('超过已报告的单幅体积上限')
target=ROOT/'data/raw/dem'/pathlib.Path(item['name']).name
if target.exists(): raise RuntimeError('原始文件已存在，未覆盖')
cache=ROOT/'data/.download_cache/fabdem_n22e108'
cache.mkdir(parents=True,exist_ok=True)
(DOC/'dem_chunks').mkdir(exist_ok=True)
head,headers=fetch(ZIP_URL,'fabdem_local_header',1000,f"{item['offset']}-{item['offset']+29}")
local=struct.unpack('<4s5H3L2H',head)
assert local[0]==b'PK\x03\x04'
start=item['offset']+30+local[-2]+local[-1]
size=item['compressed_bytes']; step=1024*1024
parts=[]
for number,at in enumerate(range(0,size,step)):
    count=min(step,size-at); path=cache/f'{number:03d}.part'
    if path.exists() and path.stat().st_size==count:
        chunk=path.read_bytes()
    else:
        for attempt in range(2):
            try:
                chunk,h=fetch(ZIP_URL,f'dem_chunks/chunk_{number:03d}',count+1,f'{start+at}-{start+at+count-1}',timeout=45)
                expected=f'bytes {start+at}-{start+at+count-1}/'
                if len(chunk)!=count or expected not in h: raise RuntimeError('返回范围/长度错误')
                path.write_bytes(chunk)
                break
            except Exception:
                if attempt==1: raise
        print(f'chunk {number+1}/27 verified, total {at+count} bytes',flush=True)
    parts.append(chunk)
packed=b''.join(parts)
unpacked=zlib.decompress(packed,-15) if item['method']==8 else packed
if item['method'] not in [0,8]: raise RuntimeError('压缩方法不支持')
if len(unpacked)!=item['uncompressed_bytes'] or (zlib.crc32(unpacked)&0xffffffff)!=item['crc32']: raise RuntimeError('最终长度或 CRC32 校验失败')
target.write_bytes(unpacked)
state=json.loads(STATE.read_text(encoding='utf-8'))
state['dem']['transfer_attempts']=['整幅字节段 45 秒超时，未保存原始文件','整幅字节段 180 秒超时，未保存原始文件','改用 1 MiB 可续传字节分段']
state['dem']['download']={'file':str(target.relative_to(ROOT)),'bytes':len(unpacked),'sha256':hashlib.sha256(unpacked).hexdigest(),'zip_crc32_verified':True,'downloaded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'chunk_cache':str(cache.relative_to(ROOT))}
save_json(STATE,state)
print(json.dumps(state['dem']['download'],ensure_ascii=True),flush=True)