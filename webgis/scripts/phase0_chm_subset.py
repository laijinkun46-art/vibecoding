"""只读官方 HDF5 字节范围，保存原样响应分段并提取研究区八日原始格点。
不重采样，不把气象日改成自然日，不将子集标成官方完整年文件。
"""
import datetime as dt,hashlib,io,json,math,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tools/python'))
import h5py,numpy as np,requests
URL='https://zenodo.org/records/20378336/files/CHM_PRE_V2_daily_2024.nc?download=1'
SIZE=674638949
RAW=ROOT/'data/raw/rainfall/chm_pre_v2_2024_byte_ranges'; RAW.mkdir(parents=True,exist_ok=True)
DOC=ROOT/'docs/chm_pre'

def plain(value):
    if isinstance(value,bytes): return value.decode('utf-8',errors='replace')
    if isinstance(value,np.ndarray): return [plain(x) for x in value.tolist()]
    if isinstance(value,np.generic): return plain(value.item())
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,(str,int,float,bool)) or value is None: return value
    return str(value)

class RangeFile(io.RawIOBase):
    def __init__(self,offline=False):
        super().__init__(); self.offline=offline; self.pos=0; self.step=65536; self.session=requests.Session(); self.blocks={}; self.records=[]; self.transferred=0
    def readable(self): return True
    def seekable(self): return True
    def writable(self): return False
    def tell(self): return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else SIZE+offset
        if self.pos<0: raise ValueError('负偏移')
        return self.pos
    def get_block(self,index):
        if index in self.blocks: return self.blocks[index]
        start=index*self.step; end=min(SIZE,start+self.step)-1
        path=RAW/f'{start:010d}-{end:010d}.bin'
        if path.exists():
            data=path.read_bytes(); headers={'cache_reused':True}
            if len(data)!=end-start+1: raise RuntimeError('已有分段长度错误，未覆盖')
        else:
            if self.offline: raise RuntimeError('离线验证缺少所需原始字节段')
            for attempt in range(3):
                try:
                    with self.session.get(URL,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','User-Agent':'Nanning-WebGIS-course-data-check/0.1'},stream=True,timeout=(12,35)) as r:
                        if r.status_code==429:
                            if attempt==2: r.raise_for_status()
                            print('服务限流，等待 30 秒后重试',flush=True); time.sleep(30); continue
                        r.raise_for_status()
                        if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{SIZE}': raise RuntimeError('服务器未遵守请求范围')
                        data=r.raw.read(end-start+2)
                        if len(data)!=end-start+1: raise RuntimeError('响应长度与范围不符')
                        headers={key:r.headers.get(key) for key in ['Content-Range','ETag','Last-Modified','Content-Length']}
                    self.transferred+=len(data)
                    if self.transferred>64*1024*1024: raise RuntimeError('超过 64 MiB 子集流量预算，停止')
                    path.write_bytes(data)
                    break
                except requests.RequestException:
                    if attempt==2: raise
            else: raise RuntimeError('无法取得字节段')
        self.records.append({'start':start,'end_inclusive':end,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'file':path.relative_to(ROOT).as_posix(),'headers':headers})
        self.blocks[index]=data
        if len(self.records)%10==0: print(f'已验证 {len(self.records)} 个原始字节段，新增传输 {self.transferred} 字节',flush=True)
        return data
    def read(self,size=-1):
        if size<0: size=SIZE-self.pos
        size=min(size,SIZE-self.pos)
        if size<=0: return b''
        start=self.pos; end=start+size; chunks=[]
        while self.pos<end:
            index=self.pos//self.step; block=self.get_block(index); offset=self.pos%self.step
            length=min(len(block)-offset,end-self.pos); chunks.append(block[offset:offset+length]); self.pos+=length
        return b''.join(chunks)
    def readinto(self,buffer):
        data=self.read(len(buffer)); buffer[:len(data)]=data; return len(data)
    def write(self,data): raise io.UnsupportedOperation('只读')
    def truncate(self,size=None): raise io.UnsupportedOperation('只读')
    def flush(self): pass
    def close(self):
        self.session.close(); super().close()

def main():
    remote=RangeFile()
    try:
        with h5py.File(remote,'r') as f:
            metadata={'dataset':'CHM_PRE V2','repository_version':'V2.1.1','url':URL,'source_file_bytes':SIZE,'global_attributes':{k:plain(v) for k,v in f.attrs.items()},'variables':{k:{'shape':list(v.shape),'dtype':str(v.dtype),'dtype_string':v.dtype.str,'offset':v.id.get_offset(),'chunks':v.chunks,'compression':v.compression,'attributes':{a:plain(b) for a,b in v.attrs.items() if a not in ['DIMENSION_LIST','REFERENCE_LIST']}} for k,v in f.items() if isinstance(v,h5py.Dataset)}}
            (DOC/'file_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            print(json.dumps(metadata,ensure_ascii=True,indent=2),flush=True)
            lat=f['lat'][:]; lon=f['lon'][:]; times=f['time'][:]
            time_units=plain(f['time'].attrs['units']); units=plain(f['prec'].attrs['units'])
            if not time_units.startswith('days since 1960-01-01'): raise RuntimeError('时间基准不符合已核实定义')
            labels=[(dt.datetime(1960,1,1)+dt.timedelta(days=float(t))).strftime('%Y-%m-%d') for t in times]
            wanted=[f'2024-09-{i:02d}' for i in range(6,14)]
            tidx=[labels.index(day) for day in wanted]
            if tidx!=list(range(tidx[0],tidx[0]+8)): raise RuntimeError('目标日期不连续')
            if f['prec'].shape!=(len(times),len(lat),len(lon)): raise RuntimeError('降水维度顺序不是 time,lat,lon')
            if not np.allclose(np.abs(np.diff(lat)),0.1) or not np.allclose(np.abs(np.diff(lon)),0.1): raise RuntimeError('实际网格间距不是 0.1 度')
            # 选择与研究区相交的完整网格单元，而非只选择中心落在区内的格点。
            iy=np.flatnonzero((lat+0.05>22.73)&(lat-0.05<22.85))
            ix=np.flatnonzero((lon+0.05>108.23)&(lon-0.05<108.44))
            if not len(iy) or not len(ix): raise RuntimeError('研究区无相交网格')
            values=np.asarray(f['prec'][tidx[0]:tidx[-1]+1,iy[0]:iy[-1]+1,ix[0]:ix[-1]+1])
            subset_lat=lat[iy]; subset_lon=lon[ix]; subset_time=times[tidx]
            attrs={k:plain(v) for k,v in f['prec'].attrs.items() if k not in ['DIMENSION_LIST','REFERENCE_LIST']}
            if 'scale_factor' in attrs or 'add_offset' in attrs: raise RuntimeError('发现打包比例，需要明确解码后才能验收')
            valid=np.isfinite(values)
            for name in ['_FillValue','missing_value']:
                if name in attrs:
                    for fill in np.asarray(attrs[name]).ravel():
                        if fill is not None and np.isfinite(float(fill)): valid &= values!=float(fill)
            if not valid.all() or (values<0).any(): raise RuntimeError('目标子集有缺失或负降雨，未验收')
            # 本地独立数据文件保留原始数值与轴，明确标注为提取子集。
            target=ROOT/'data/processed/chm_pre_v2_nanning_20240906_13.h5'
            if target.exists(): raise RuntimeError('提取子集已存在，未覆盖')
            with h5py.File(target,'x') as dest:
                dest.attrs['source_url']=URL; dest.attrs['source_version']='V2.1.1'; dest.attrs['product']='CHM_PRE V2 extracted subset, not full official annual file'
                dest.attrs['daily_window_bjt']='previous day 20:00 to label day 20:00'
                for key,arr in [('lat',subset_lat),('lon',subset_lon),('time',subset_time)]:
                    d=dest.create_dataset(key,data=arr)
                    for attr,value in f[key].attrs.items():
                        if attr not in ['DIMENSION_LIST','REFERENCE_LIST','CLASS','NAME','_Netcdf4Dimid']:
                            try: d.attrs[attr]=value
                            except (TypeError,ValueError): pass
                    d.make_scale(key)
                d=dest.create_dataset('prec',data=values)
                for attr,value in f['prec'].attrs.items():
                    if attr not in ['DIMENSION_LIST','REFERENCE_LIST','_Netcdf4Coordinates']:
                        try: d.attrs[attr]=value
                        except (TypeError,ValueError): pass
                for axis,key in enumerate(['time','lat','lon']): d.dims[axis].attach_scale(dest[key]); d.dims[axis].label=key
            with h5py.File(target,'r') as test:
                if not np.array_equal(test['prec'][:],values): raise RuntimeError('本地子集数值回读不一致')
            import csv
            table=ROOT/'data/processed/chm_pre_v2_nanning_daily_cells.csv'
            with table.open('x',encoding='utf-8-sig',newline='') as handle:
                writer=csv.writer(handle); writer.writerow(['date_label','interval_start_bjt','interval_end_bjt','lat','lon','prec_mm_per_day'])
                for t,label in enumerate(wanted):
                    day=dt.datetime.fromisoformat(label)
                    for y,la in enumerate(subset_lat):
                        for x,lo in enumerate(subset_lon): writer.writerow([label,(day-dt.timedelta(days=1)).strftime('%Y-%m-%dT20:00:00+08:00'),day.strftime('%Y-%m-%dT20:00:00+08:00'),float(la),float(lo),float(values[t,y,x])])
            result={'status':'subset_acquired_checked','dataset':'CHM_PRE V2','repository_version':'V2.1.1','doi':'10.5281/zenodo.20378336','source_url':URL,'source_file_bytes':SIZE,'full_file_downloaded':False,'full_file_md5_verified':False,'reference_full_file_md5':'3360750e943c9372761b8cf0bc6f2fa2','date_labels':wanted,'time_units':time_units,'units':units,'shape':list(values.shape),'lat_centers':subset_lat.tolist(),'lon_centers':subset_lon.tolist(),'missing_count':int((~valid).sum()),'negative_count':int((values<0).sum()),'min':float(values.min()),'max':float(values.max()),'source_prec_attributes':attrs,'subset_file':target.relative_to(ROOT).as_posix(),'subset_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'cells_csv':table.relative_to(ROOT).as_posix(),'interval_start_bjt':'2024-09-05T20:00:00+08:00','interval_end_bjt':'2024-09-13T20:00:00+08:00','no_resampling':True,'raw_byte_blocks':len(remote.records),'raw_byte_count':sum(r['bytes'] for r in remote.records),'new_network_bytes':remote.transferred,'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
            (DOC/'subset_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            print('SUBSET_RESULT '+json.dumps(result,ensure_ascii=True,indent=2),flush=True)
    finally:
        (RAW/'manifest.json').write_text(json.dumps({'url':URL,'source_size':SIZE,'scope':'原始 HTTP 字节段，非完整年文件；SHA256 逐段校验','blocks':remote.records},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        remote.close()

if __name__ == '__main__':
    main()
