"""离线验收 CHM_PRE 子集：校验原始分段、源字节、时间、覆盖、单位、空值与 CSV 回读。
不访问网络，不推导水位；图仅作输入数据质量检查。
"""
import csv,datetime as dt,hashlib,json,pathlib,struct,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tools/python'))
import h5py,numpy as np
from phase0_chm_subset import RangeFile,plain
DOC=ROOT/'docs/chm_pre'

def validate_chm(root=ROOT,preview=False):
    record=json.loads((DOC/'subset_validation.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'data/raw/rainfall/chm_pre_v2_2024_byte_ranges/manifest.json').read_text(encoding='utf-8'))
    for b in manifest['blocks']:
        data=(ROOT/b['file']).read_bytes()
        assert len(data)==b['end_inclusive']-b['start']+1==b['bytes']
        assert hashlib.sha256(data).hexdigest()==b['sha256']
    target=ROOT/record['subset_file']
    assert hashlib.sha256(target.read_bytes()).hexdigest()==record['subset_sha256']
    remote=RangeFile(offline=True)
    try:
        with h5py.File(remote,'r') as src, h5py.File(target,'r') as dest:
            lat,lon,time=src['lat'][:],src['lon'][:],src['time'][:]
            labels=[(dt.datetime(1960,1,1)+dt.timedelta(days=float(x))).strftime('%Y-%m-%d') for x in time]
            expected=[f'2024-09-{d:02d}' for d in range(6,14)]
            ti=[labels.index(d) for d in expected]
            yi=np.flatnonzero((lat+0.05>22.73)&(lat-0.05<22.85))
            xi=np.flatnonzero((lon+0.05>108.23)&(lon-0.05<108.44))
            values=dest['prec'][:]
            assert np.array_equal(dest['lat'][:],lat[yi]) and np.array_equal(dest['lon'][:],lon[xi]) and np.array_equal(dest['time'][:],time[ti])
            assert values.shape==(8,len(yi),len(xi)) and np.isfinite(values).all() and (values>=0).all()
            assert plain(src['prec'].attrs['units'])=='mm/day'
            assert plain(src['time'].attrs['units'])=='days since 1960-01-01'
            assert np.allclose(np.diff(lat),0.1) and np.allclose(np.diff(lon),0.1)
            # 文件中降水变量是未压缩、连续存储的 float64；直接定位源字节作独立数值比对。
            ds=src['prec']; offset=ds.id.get_offset()
            assert ds.chunks is None and ds.compression is None and ds.dtype.str=='<f8' and offset is not None
            for t,it in enumerate(ti):
                for y,iy in enumerate(yi):
                    for x,ix in enumerate(xi):
                        address=offset+((it*len(lat)+int(iy))*len(lon)+int(ix))*8
                        remote.seek(address); original=struct.unpack('<d',remote.read(8))[0]
                        assert original==float(values[t,y,x]),(t,y,x)
            assert min(lon[xi])-0.05<=108.23 and max(lon[xi])+0.05>=108.44
            assert min(lat[yi])-0.05<=22.73 and max(lat[yi])+0.05>=22.85
            rows=list(csv.DictReader((ROOT/record['cells_csv']).open(encoding='utf-8-sig',newline='')))
            assert len(rows)==values.size==48
            for row in rows:
                t=expected.index(row['date_label']); y=int(np.flatnonzero(lat[yi]==float(row['lat']))[0]); x=int(np.flatnonzero(lon[xi]==float(row['lon']))[0])
                assert float(row['prec_mm_per_day'])==float(values[t,y,x])
                end=dt.datetime.fromisoformat(row['interval_end_bjt']); start=dt.datetime.fromisoformat(row['interval_start_bjt'])
                assert (end-start)==dt.timedelta(days=1) and end.hour==start.hour==20 and end.utcoffset()==dt.timedelta(hours=8)
            metadata={'global_attributes':{k:plain(v) for k,v in src.attrs.items()},'variables':{k:{'shape':list(v.shape),'dtype':str(v.dtype),'dtype_string':v.dtype.str,'offset':v.id.get_offset(),'chunks':v.chunks,'compression':v.compression,'attributes':{a:plain(b) for a,b in v.attrs.items() if a not in ['DIMENSION_LIST','REFERENCE_LIST']}} for k,v in src.items()}}
    finally: remote.close()
    result={**record,'status':'subset_acquired_checked','raw_byte_hashes_verified':len(manifest['blocks']),'source_values_replayed_exactly':True,'csv_values_roundtrip_equal':True,'time_sequence_passed':True,'aoi_cell_coverage_passed':True,'source_coordinate_metadata':'经纬度，单位 degrees_north/degrees_east；源 NetCDF 无独立 EPSG/椭球定义。按官方 GeoTIFF WGS84 说明作本项目 WGS84 匹配假设，未做坐标变换。','daily_statistics':[{'date_label':label,'min_mm_per_day':float(values[i].min()),'max_mm_per_day':float(values[i].max())} for i,label in enumerate(expected)],'validation_network_bytes':remote.transferred,'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    assert result['validation_network_bytes']==0
    (DOC/'file_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (DOC/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    if preview:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']; plt.rcParams['axes.unicode_minus']=False
        fig,axes=plt.subplots(2,4,figsize=(13,7),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat):
            image=ax.imshow(values[i],origin='lower',extent=[lon[xi].min()-0.05,lon[xi].max()+0.05,lat[yi].min()-0.05,lat[yi].max()+0.05],vmin=0,vmax=float(values.max()),cmap='Blues',interpolation='nearest')
            ax.add_patch(Rectangle((108.23,22.73),0.21,0.12,fill=False,edgecolor='crimson',linewidth=1.4))
            ax.set_title(expected[i]); ax.set_xticks([108.25,108.35,108.45]); ax.set_yticks([22.75,22.85]); ax.tick_params(labelsize=8)
        fig.suptitle('CHM_PRE V2 南宁研究区逐日降水原始格点检查',fontsize=16)
        fig.subplots_adjust(top=0.88,bottom=0.16,right=0.88,hspace=0.28)
        cax=fig.add_axes([0.91,0.23,0.018,0.56]); fig.colorbar(image,cax=cax,label='降水 / mm/day')
        fig.text(0.08,0.05,'红框为研究区；保留原始 0.1° 格点，不做空间插值。\n各日期表示前一日北京时间 20:00 至当日 20:00；此图是降雨输入，不是洪水模拟。',fontsize=10)
        fig.savefig(ROOT/'outputs/phase0_chm_precipitation_preview.png',dpi=160); plt.close(fig)
    return result

if __name__=='__main__':
    print(json.dumps(validate_chm(preview=('--no-preview' not in sys.argv)),ensure_ascii=True,indent=2),flush=True)
