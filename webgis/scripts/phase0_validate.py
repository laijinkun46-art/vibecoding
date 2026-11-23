"""Phase 0 本地验收：边界、DEM 原始栅格、降雨时间清单及河流几何。
只做数据获取阶段的检查，不实现地形分析或洪水业务算法。
运行环境：本机已有 QGIS Python 3.12 + GDAL + NumPy + pyproj。
"""
import datetime as dt, hashlib, json, math, pathlib
import numpy as np
from osgeo import gdal, ogr, osr
from pyproj import Geod
ROOT=pathlib.Path(__file__).resolve().parents[1]
DOC=ROOT/'docs'
gdal.UseExceptions()
W,S,E,N=108.23,22.73,108.44,22.85
ring=[[W,S],[E,S],[E,N],[W,N],[W,S]]
aoi={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'南宁邕江城区课程试验区','status':'课程设计选定的计算范围，可按教学需求调整','source':'课程设计人工定义的 WGS84 矩形，不是行政边界或实测淹没边界','bbox_wsen':[W,S,E,N]},'geometry':{'type':'Polygon','coordinates':[ring]}}]}
path=ROOT/'data/study_area/nanning_yongjiang_aoi.geojson'
if path.exists():
    existing=json.loads(path.read_text(encoding='utf-8'))
    if existing['features'][0]['geometry']!=aoi['features'][0]['geometry']: raise RuntimeError('已有研究区几何不同，未覆盖')
path.write_text(json.dumps(aoi,ensure_ascii=False,indent=2),encoding='utf-8')
poly=ogr.CreateGeometryFromJson(json.dumps(aoi['features'][0]['geometry']))
area=abs(Geod(ellps='WGS84').polygon_area_perimeter([p[0] for p in ring],[p[1] for p in ring])[0])/1e6
state=json.loads((DOC/'phase0_acquisition.json').read_text(encoding='utf-8'))
report={'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'runtime':{'gdal':gdal.VersionInfo(),'numpy':np.__version__},'aoi':{'bbox_wsen':[W,S,E,N],'geometry_valid':bool(poly.IsValid()),'area_km2':area,'finalized':True},'dem':{'status':'not_downloaded'},'rainfall':{'status':'metadata_only_not_downloaded'},'rivers':{'status':'unavailable'}}
raw=ROOT/'data/raw/dem/N22E108_FABDEM_V1-2.tif'
if raw.exists():
    ds=gdal.Open(str(raw),gdal.GA_ReadOnly); band=ds.GetRasterBand(1)
    gt=ds.GetGeoTransform(); srs=ds.GetSpatialRef(); srs.AutoIdentifyEPSG()
    bounds=[gt[0],gt[3]+gt[5]*ds.RasterYSize,gt[0]+gt[1]*ds.RasterXSize,gt[3]]
    covered=bounds[0]<=W and bounds[1]<=S and bounds[2]>=E and bounds[3]>=N
    if not (gt[1]>0 and gt[5]<0 and gt[2]==0 and gt[4]==0): raise RuntimeError('仅支持北向上的原始分幅检查')
    x0=max(0,math.floor((W-gt[0])/gt[1])); x1=min(ds.RasterXSize,math.ceil((E-gt[0])/gt[1]))
    y0=max(0,math.floor((N-gt[3])/gt[5])); y1=min(ds.RasterYSize,math.ceil((S-gt[3])/gt[5]))
    arr=band.ReadAsArray(x0,y0,x1-x0,y1-y0)
    nodata=band.GetNoDataValue(); valid=np.isfinite(arr)
    if nodata is not None: valid &= arr!=nodata
    values=arr[valid]
    digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    downloaded=state['dem'].get('download',{})
    report['dem']={'status':'downloaded_checked','file':str(raw.relative_to(ROOT)),'bytes':raw.stat().st_size,'sha256':digest,'download_hash_matches':digest==downloaded.get('sha256'),'archive_crc32_verified':downloaded.get('zip_crc32_verified',False),'horizontal_epsg':srs.GetAuthorityCode(None),'vertical_datum_documented':'EGM2008 EPSG:3855, official FABDEM readme','bounds_wsen':bounds,'pixel_size_degree':[gt[1],gt[5]],'raster_size':[ds.RasterXSize,ds.RasterYSize],'data_type':gdal.GetDataTypeName(band.DataType),'nodata':nodata,'aoi_fully_covered':covered,'aoi_window_size':[arr.shape[1],arr.shape[0]],'aoi_pixels':int(arr.size),'valid_pixels':int(valid.sum()),'invalid_pixels':int((~valid).sum()),'valid_fraction':float(valid.mean()),'elevation_m':{'min':float(values.min()),'max':float(values.max()),'median':float(np.median(values))} if len(values) else None,'limits':'像元完整性通过不等于高程精度经过实测检验；DEM 不是 2024 年实测河床。'}
    ds=None
manifest=DOC/'imerg_download_manifest.json'
if manifest.exists():
    inventory=json.loads(manifest.read_text(encoding='utf-8'))
    files=inventory['files']; start=dt.datetime(2024,9,5,16,tzinfo=dt.timezone.utc)
    expected={start+dt.timedelta(minutes=30*i) for i in range(384)}
    actual=[dt.datetime.fromisoformat(x['start_utc'].replace('Z','+00:00')) for x in files]
    bad_end=[]
    for x in files:
        a=dt.datetime.fromisoformat(x['start_utc'].replace('Z','+00:00'))
        b=dt.datetime.fromisoformat(x['end_utc'].replace('Z','+00:00'))
        if abs((b-a).total_seconds()-1799.999)>0.01: bad_end.append(x['title'])
    report['rainfall'].update(file_count=len(files),unique_start_count=len(set(actual)),expected_count=384,missing_count=len(expected-set(actual)),unexpected_count=len(set(actual)-expected),bad_interval_end_count=len(bad_end),time_inventory_passed=len(files)==384 and set(actual)==expected and not bad_end,total_mib=sum(x['size_mib'] for x in files),local_interval=inventory['interval_local'],data_files_downloaded=len(list((ROOT/'data/raw/rainfall').glob('*.HDF5'))),spatial_coverage='仅由产品全球范围元数据推知；未验证实际像元',units_and_quality='未下载文件，单位、填充值、质量标识和数值均未验收',authentication='用户无 Earthdata 账号，本轮不下载、不绕过登录')
riverways_path=DOC/'osm_main_api_river_ways.json'
if riverways_path.exists():
    ways=json.loads(riverways_path.read_text(encoding='utf-8'))
    checked=[]; parents={}
    def find(x):
        parents.setdefault(x,x)
        while parents[x]!=x:
            parents[x]=parents[parents[x]]; x=parents[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parents[b]=a
    for w in ways:
        coords=w['geometry']; g=ogr.CreateGeometryFromJson(json.dumps({'type':'LineString','coordinates':coords}))
        for a,b in zip(w['nodes'],w['nodes'][1:]): union(a,b)
        checked.append({'id':w['id'],'name':w['tags'].get('name'),'valid':bool(g.IsValid()),'intersects_aoi':bool(g.Intersects(poly)),'node_count':len(w['nodes']),'bounds':list(g.GetEnvelope()),'timestamp':w['timestamp']})
    report['rivers']={'status':'current_reference_checked' if ways else 'no_river_in_response','historical_2024':False,'way_count':len(ways),'valid_way_count':sum(x['valid'] for x in checked),'intersecting_way_count':sum(x['intersects_aoi'] for x in checked),'components_by_original_osm_node_ids':len({find(x) for x in parents}),'ways':checked,'full_aoi_river_coverage_verified':False,'limits':'小范围主站地图响应只能确认所返回河段；连通分量不是完整邕江水系的连通性验收。'}
# 只确认指定主河道在矩形计算区内的连续覆盖，不等价于完整流域或历史岸线。
main=[w for w in json.loads(riverways_path.read_text(encoding='utf-8')) if w['tags'].get('name')=='邕江'] if riverways_path.exists() else []
if len(main)==1:
    line=ogr.CreateGeometryFromJson(json.dumps({'type':'LineString','coordinates':main[0]['geometry']}))
    west=ogr.CreateGeometryFromWkt(f'LINESTRING ({W} {S},{W} {N})')
    east=ogr.CreateGeometryFromWkt(f'LINESTRING ({E} {S},{E} {N})')
    clipped=line.Intersection(poly)
    trace={'crosses_west_boundary':bool(line.Intersects(west)),'crosses_east_boundary':bool(line.Intersects(east)),'clipped_geometry_type':clipped.GetGeometryName(),'geometry_valid':bool(clipped.IsValid()),'osm_way_id':main[0]['id']}
    trace['main_channel_coverage_passed']=trace['crosses_west_boundary'] and trace['crosses_east_boundary'] and trace['clipped_geometry_type']=='LINESTRING' and trace['geometry_valid']
    report['rivers']['main_channel_check']=trace
# 数据覆盖检查图，重用原始像元；不计算坡度或洪水，不将显示插值当成提高精度。
if raw.exists():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    fig,ax=plt.subplots(figsize=(10,6.7))
    extent=[gt[0]+x0*gt[1],gt[0]+x1*gt[1],gt[3]+y1*gt[5],gt[3]+y0*gt[5]]
    im=ax.imshow(np.ma.masked_where(~valid,arr),extent=extent,origin='upper',cmap='terrain',interpolation='nearest')
    ax.set_aspect(1/math.cos(math.radians((S+N)/2)))
    ax.add_patch(Rectangle((W,S),E-W,N-S,fill=False,edgecolor='crimson',linewidth=2,label='课程研究区'))
    if riverways_path.exists():
        for w in json.loads(riverways_path.read_text(encoding='utf-8')):
            coords=np.array(w['geometry']); ax.plot(coords[:,0],coords[:,1],linewidth=1.8,label=w['tags'].get('name','河流'))
    ax.set_xlim(W-0.003,E+0.003); ax.set_ylim(S-0.003,N+0.003)
    ax.set_xlabel('经度 °E'); ax.set_ylabel('纬度 °N')
    ax.set_title('Phase 0 南宁邕江研究区与数据覆盖检查')
    ax.legend(loc='upper right'); ax.grid(alpha=0.2)
    fig.colorbar(im,ax=ax,shrink=0.8,label='DEM 高程 / m（EGM2008）')
    fig.text(0.05,0.025,'FABDEM v1.2；© OpenStreetMap contributors（当前河道参考）\n矩形为人工定义计算范围；图中没有模拟洪水或实测淹没结果。',fontsize=9)
    fig.subplots_adjust(bottom=0.17)
    fig.savefig(ROOT/'outputs/phase0_data_preview.png',dpi=160)
    plt.close(fig)
# 用户已采用 CHM_PRE 时，以实际子集的离线验收替代旧的 IMERG 元数据状态。
if (DOC/'chm_pre/subset_validation.json').exists():
    # GDAL 与 h5py 使用不同 HDF5 动态库，独立进程避免 DLL 冲突。
    import subprocess,sys
    child=subprocess.run([sys.executable,str(ROOT/'scripts/phase0_chm_validate.py'),'--no-preview'],capture_output=True,text=True,encoding='utf-8')
    if child.returncode!=0: raise RuntimeError('CHM_PRE 离线检查失败：'+child.stderr)
    report['rainfall']=json.loads((DOC/'chm_pre/validation.json').read_text(encoding='utf-8'))
(DOC/'phase0_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
