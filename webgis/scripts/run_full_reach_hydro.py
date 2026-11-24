"""Compile the existing Windows C# toolchain and run the offline teaching model."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path

if os.name == 'nt':
    dll = os.add_dll_directory(r'D:\Arcgis10.8.2\bin')

import numpy as np
from osgeo import gdal, ogr, osr
from scipy.ndimage import distance_transform_edt
from shapely import wkb
from shapely.geometry import Point

from gis_processing import digest, spatial_ref, valid_pixels

ROOT = Path(__file__).resolve().parents[1]
HYDRO = ROOT / 'data/processed/hydrodynamics'
PREP = HYDRO / 'preparation'
RUNS = HYDRO / 'runs'
SOURCE = Path(__file__).with_name('HydroShallowWater.cs')
TERRAIN = PREP / 'full_reach_v1/terrain_manifest.json'
PARAMS = PREP / 'full_reach_scenario_v1/scenario_parameters.json'
BOUNDARY = PARAMS.with_name('boundary_assessment.csv')
DEM = ROOT / 'data/processed/phase2/dem_utm49n_30m.tif'
DOMAIN = TERRAIN.with_name('domain.gpkg')
COMPILER = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
WET = .05
DRY = .003
LIMITS = {'relative_mass_error': 1e-9, 'max_speed_mps': 12., 'min_raw_depth_m': -1e-7,
          'lake_max_velocity_mps': 1e-9, 'lake_max_depth_error_m': 1e-9,
          'min_overbank_growth_km2': 1., 'min_recession_km2': 1.}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def geom(value):
    return wkb.loads(bytes(value.ExportToWkb()))


def smooth(x):
    return x*x*(3-2*x)


def interpolate(series, t):
    for (t0,v0), (t1,v1) in zip(series, series[1:]):
        if t <= t1:
            return v0+(v1-v0)*smooth(max(0,(t-t0)/(t1-t0)))
    return series[-1][1]


def write_solver_input(path, cells, faces, curves, duration, stride, lateral):
    with path.open('wb') as f:
        f.write(struct.pack('<iiiddddd', len(cells), len(faces), len(curves), duration, stride, *lateral))
        f.write(np.array(curves, dtype='<f8').tobytes())
        f.write(np.array(cells, dtype='<f8').tobytes())
        face_type = np.dtype([('ids','<i4',3),('geometry','<f8',3)])
        buf=np.empty(len(faces),dtype=face_type)
        buf['ids']=[x[:3] for x in faces]
        buf['geometry']=[x[3:] for x in faces]
        f.write(buf.tobytes())


def analytical_checks(program, work):
    """Still water on steps and a separate dam break on a closed 2-D grid."""
    checks={}
    nx=12
    for kind in ('lake','dam_break'):
        path=work/kind
        path.mkdir()
        cells=[]; faces=[]
        for j in range(nx):
            for i in range(nx):
                k=j*nx+i
                z=(.15*(i%5)+.11*(j%3)) if kind=='lake' else 0
                h=max(0, .55-z) if kind=='lake' else (1.5 if 3<=i<=7 and 3<=j<=7 else 0)
                cells.append((z,.032,100,h,0,0))
                faces.append((k,k+1 if i<nx-1 else -1,0,10,1,0))
                faces.append((k,k+nx if j<nx-1 else -1,0,10,0,1))
                if i==0: faces.append((k,-1,0,10,-1,0))
                if j==0: faces.append((k,-1,0,10,0,-1))
        inp=path/'input.bin'
        write_solver_input(inp,cells,faces,[(0,0,1),(30,0,1)],30,30,(.05,.00005,.065))
        subprocess.run([str(program),str(inp),str(path)],check=True,capture_output=True)
        before,after=[np.fromfile(path/f'{i:04}.f64',dtype='<f8').reshape(-1,3) for i in range(2)]
        error=float(np.max(np.abs(after[:,0]-before[:,0])))
        mass_error=float(abs(np.sum(before[:,0])-np.sum(after[:,0])))
        wet=after[:,0]>DRY
        speed=float((np.linalg.norm(after[wet,1:],axis=1)/after[wet,0]).max())
        require(mass_error<1e-9 and (after[:,0]>=0).all() and np.isfinite(after).all(),'小算例水量或干湿失败')
        if kind=='lake':
            require(error<LIMITS['lake_max_depth_error_m'] and speed<LIMITS['lake_max_velocity_mps'],'静水平衡失败')
        else:
            require((after[:,0]>WET).sum()>(before[:,0]>WET).sum() and speed>0,'溃坝算例没有推进湿润前沿')
        checks[kind]={'max_depth_change_m':error,'absolute_mass_error_m3':mass_error*100,'max_speed_mps':speed,
                      'wet_cells_initial':int((before[:,0]>WET).sum()),'wet_cells_final':int((after[:,0]>WET).sum())}
    return checks


def make_mesh(params, coarse):
    with ogr.Open(str(DOMAIN),0) as ds:
        layer=ds.GetLayerByName('main_centerline')
        f=layer.GetNextFeature()
        main=geom(f.GetGeometryRef())
        layer=ds.GetLayerByName('perimeter_segments')
        segments=[(f.items(),geom(f.GetGeometryRef())) for f in layer]
    with BOUNDARY.open(encoding='utf-8-sig',newline='') as f:
        roles={r['segment_id']:r['baseline_intent'] for r in csv.DictReader(f)}
    bbox=read(ROOT/'data/study_area/nanning_yongjiang_aoi.geojson')['features'][0]['properties']['bbox_wsen']
    west,south,east,north=bbox
    # The logical lattice covers the exact geographic AOI. Flux geometry is in UTM metres.
    cols,rows=(176,112) if coarse else (352,224)
    dl=(east-west)/cols; dp=(north-south)/rows
    xx,yy=np.meshgrid(np.linspace(west,east,cols+1),np.linspace(south,north,rows+1))
    transform=osr.CoordinateTransformation(spatial_ref(4326),spatial_ref(32649))
    xy=np.array(transform.TransformPoints(np.column_stack([xx.ravel(),yy.ravel()]).tolist()))[:,:2].reshape(rows+1,cols+1,2)
    seg=np.asarray(main.coords); v=np.diff(seg,axis=0); lengths=np.linalg.norm(v,axis=1)
    cumulative=np.r_[0.,np.cumsum(lengths)]

    def locate(p):
        delta=p-seg[:-1]
        t=np.clip(np.einsum('ij,ij->i',delta,v)/(lengths**2),0,1)
        distances=np.linalg.norm(delta-t[:,None]*v,axis=1)
        k=distances.argmin()
        return distances[k],cumulative[k]+t[k]*lengths[k],v[k]/lengths[k]

    ds=gdal.Open(str(DEM),gdal.GA_ReadOnly)
    z,valid=valid_pixels(ds); gt=ds.GetGeoTransform()
    nearest=distance_transform_edt(~valid, return_distances=False, return_indices=True)
    bath=params['bathymetry']
    B=bath['bottom_width']['value']; D=bath['design_bank_depth']['value']; Z=bath['bank_side_slope']['value']
    slope=bath['bed_slope']['value']; westbed=bath['west_bed_elevation']['value']; blend=bath['blend_width']['value']
    # v1 refines the specified channel; a validated run may use a separate calibrated geometry variant.
    half=B/2+Z*D
    init=params['initial']; hc=init['channel_depth']['value']; speed=init['channel_speed']['value']
    nc=params['friction']['channel']['value']; nf=params['friction']['floodplain']['value']
    grid=np.empty((rows,cols),dtype='<u4')
    cells=[]; rects=[]; overbank=[]; lowered=[]; sample_fallbacks=0

    def leaf(x,y,side):
        nonlocal sample_fallbacks
        corners=np.array([xy[y,x],xy[y,x+side],xy[y+side,x+side],xy[y+side,x]])
        center=xy[y+side//2,x+side//2] if side>1 else corners.mean(axis=0)
        distance,s,tangent=locate(center)
        if side>1 and (distance<(470 if coarse else 350)+side*25 or
                       side>2 and distance<850+side*35 or side>4 and distance<1900):
            n=side//2
            for oy,ox in [(0,0),(0,n),(n,0),(n,n)]: leaf(x+ox,y+oy,n)
            return
        area=abs(np.dot(corners[:,0],np.roll(corners[:,1],-1))-np.dot(corners[:,1],np.roll(corners[:,0],-1)))/2
        ix=int(np.clip(math.floor((center[0]-gt[0])/30),0,z.shape[1]-1))
        iy=int(np.clip(math.floor((gt[3]-center[1])/30),0,z.shape[0]-1))
        if not valid[iy,ix]:
            yy0,xx0=nearest[:,iy,ix]
            require(math.hypot(yy0-iy,xx0-ix)*30<=45,'边缘支持像元距离超过约定')
            iy,ix=int(yy0),int(xx0); sample_fallbacks+=1
        base=float(z[iy,ix]); bed=westbed-slope*s
        w=1-smooth(float(np.clip((distance-half)/blend,0,1)))
        target=bed+min(D,max(0,(distance-B/2)/Z))
        elevation=base+w*(min(base,target)-base)
        h=max(0,bed+hc-elevation) if distance<=half else 0
        cells.append((elevation,nf+w*(nc-nf),area,h,h*speed*tangent[0],h*speed*tangent[1]))
        rects.append([west+x*dl,south+y*dp,west+(x+side)*dl,south+(y+side)*dp])
        overbank.append(distance>half+blend)
        lowered.append(base-elevation)
        grid[y:y+side,x:x+side]=len(cells)-1
    for y in range(0,rows,8):
        for x in range(0,cols,8): leaf(x,y,8)

    # Split coarse/fine interfaces exactly on the same base lattice so vectors close.
    faces=[]
    sums=np.zeros((len(cells),2))
    end_points=[seg[0],seg[-1]]
    end_directions=[v[0]/lengths[0],v[-1]/lengths[-1]]
    def add_face(l,r,a,b,direction,outer_side=None):
        vector=b-a; length=float(np.linalg.norm(vector)); nx,ny=vector[1]/length*direction,-vector[0]/length*direction
        code=0
        if r<0:
            middle=(a+b)*.5
            center=Point(*middle)
            selected=min((pair for pair in segments if pair[0]['side']==outer_side),key=lambda x:x[1].distance(center))[0]
            role=roles[selected['segment_id']]
            if outer_side in ('W','E') and selected['terminal_id']:
                k=0 if outer_side=='W' else 1
                dp0=middle-end_points[k]; d0=end_directions[k]
                if abs(dp0[0]*d0[1]-dp0[1]*d0[0])<=half:
                    code=k+1
                else: code=3
            elif role.startswith('outflow_if_wet'): code=3
        faces.append((l,r,code,length,float(nx),float(ny)))
        sums[l]+=length*np.array([nx,ny])
        if r>=0: sums[r]-=length*np.array([nx,ny])

    def runs(pairs):
        start=0
        for end in range(1,len(pairs)+1):
            if end==len(pairs) or pairs[end]!=pairs[start]:
                yield start,end,pairs[start]
                start=end
    for x in range(cols+1):
        pairs=[(int(grid[y,max(0,x-1)]),int(grid[y,x]) if 0<x<cols else -1) for y in range(rows)]
        for y0,y1,(l,r) in runs(pairs):
            if l!=r: add_face(l,r,xy[y0,x],xy[y1,x],-1 if x==0 else 1,'W' if x==0 else 'E')
    for y in range(rows+1):
        pairs=[(int(grid[max(0,y-1),x]),int(grid[y,x]) if 0<y<rows else -1) for x in range(cols)]
        for x0,x1,(l,r) in runs(pairs):
            if l!=r: add_face(l,r,xy[y,x0],xy[y,x1],1 if y==0 else -1,'S' if y==0 else 'N')
    require(np.linalg.norm(sums,axis=1).max()<.001,'网格控制体法向量不闭合')
    counts={str(k):sum(f[2]==k and f[1]<0 for f in faces) for k in range(4)}
    require(counts['1']>=2 and counts['2']>=2 and counts['3']>0,'边界标签不足')
    cells=np.asarray(cells,dtype='<f8')
    return cells,faces,np.asarray(rects,dtype='<f8'),grid,np.asarray(overbank),np.asarray(lowered),bbox,counts,sample_fallbacks


def budgets(path):
    with path.open(encoding='utf-8',newline='') as f: return [dict((k,float(v)) for k,v in r.items()) for r in csv.DictReader(f)]


def export_result(run, mesh, parameters, duration, checks, fingerprints, elapsed, pilot):
    cells,faces,rects,grid,overbank,lowered,bbox,counts,fallbacks=mesh
    raw=run/'raw'
    data=budgets(raw/'budget.csv')
    first=data[0]['volume_m3']
    assessment=[]
    begin=parameters['clock']['warmup']['value']
    web=run/'web'
    if not pilot: web.mkdir()
    areas=cells[:,2]
    for i,b in enumerate(data):
        frame=np.fromfile(raw/f'{i:04}.f64',dtype='<f8').reshape(len(cells),3)
        h=frame[:,0]; wet=h>=WET
        require(np.isfinite(frame).all() and (h>=0).all(),'输出含无效水深')
        vv=np.divide(frame[:,1:],h[:,None],out=np.zeros_like(frame[:,1:]),where=h[:,None]>DRY)
        baseline=first+b['inlet_m3']
        residual=b['volume_m3']-baseline+b['east_m3']+b['lateral_m3']-b['correction_m3']
        row={'t_seconds':b['t_seconds'],'raw_index':i,'wet_km2':float(areas[wet].sum()/1e6),
             'overbank_km2':float(areas[wet&overbank].sum()/1e6),'max_depth_m':float(h.max()),
             'max_wet_speed_mps':float(np.linalg.norm(vv[wet],axis=1).max()) if wet.any() else 0,
             'relative_mass_error':abs(residual)/max(1,baseline)}
        assessment.append(row)
        if not pilot and b['t_seconds']>=begin:
            derived=np.column_stack((h,h+cells[:,0],vv)).astype('<f4')
            comparison=np.column_stack((h,h+cells[:,0],vv))
            require(np.max(np.abs(derived-comparison))<.001,'网页派生帧偏离原结果')
            derived.tofile(web/f'{i:04}.bin')
            back=np.fromfile(web/f'{i:04}.bin',dtype='<f4').reshape(derived.shape)
            require(np.array_equal(back,derived),'网页帧回读错误')
    error=max(q['relative_mass_error'] for q in assessment)
    require(error<=LIMITS['relative_mass_error'] and data[-1]['max_speed_mps']<=LIMITS['max_speed_mps']
            and data[-1]['min_raw_depth_m']>=LIMITS['min_raw_depth_m'],'全域数值阈值未通过')
    validation={'small_cases':checks,'limits':LIMITS,'max_relative_mass_error':error,
                'max_speed_mps':data[-1]['max_speed_mps'],'min_raw_depth_m':data[-1]['min_raw_depth_m'],
                'raw_frame_count':len(data),'steps':int(data[-1]['steps']),'elapsed_s':elapsed,'pilot':pilot,
                'final_budget_m3':data[-1]}
    if not pilot:
        after_warm=[b for b in assessment if b['t_seconds']>=begin]
        peak=max(after_warm,key=lambda r:r['overbank_km2'])
        growth=peak['overbank_km2']-after_warm[0]['overbank_km2']
        recession=peak['overbank_km2']-after_warm[-1]['overbank_km2']
        require(growth>LIMITS['min_overbank_growth_km2'] and recession>LIMITS['min_recession_km2'],'全域未形成可验证的漫岸和退水变化')
        warm_end=next(b for b in data if b['t_seconds']==begin)
        before=next(b for b in data if b['t_seconds']==begin-7200)
        wi=warm_end['inlet_m3']-before['inlet_m3']
        wo=sum(warm_end[k]-before[k] for k in ['east_m3','lateral_m3'])
        storage_delta=warm_end['volume_m3']-before['volume_m3']
        validation.update(growth_km2=growth,recession_km2=recession,peak=peak,
                          warmup_storage_change_fraction=abs(storage_delta)/parameters['initial']['warmup_acceptance']['storage_reference_m3'],
                          warmup_flux_imbalance=abs(wi-wo)/wi)
        require(validation['warmup_storage_change_fraction']<.02 and validation['warmup_flux_imbalance']<.05,
                f"预热未收敛：{validation['warmup_storage_change_fraction']:.4f}/{validation['warmup_flux_imbalance']:.4f}")
        # Cell rectangle, ground elevation. Ordering is identical in raw and web frames.
        np.column_stack((rects,cells[:,0])).astype('<f4').tofile(web/'cells.bin')
        grid.tofile(web/'index.bin')
        require((np.fromfile(web/'index.bin',dtype='<u4')==grid.ravel()).all(),'查询索引回读失败')
        files={p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in web.iterdir()}
        info={'schema':1,'status':'ready','scenario_id':parameters['scenario_id'],'observed':False,'label':parameters['label_zh'],
              'terrain_datum':'EGM2008','horizontal_coordinates':'WGS84 display / UTM 49N model',
              'frame_fields':['depth_m','stage_m','u_grid_mps','v_grid_mps'],'wet_threshold_m':WET,
              'bounds':bbox,'rows':grid.shape[0],'cols':grid.shape[1],'cell_count':len(cells),
              'cell_fields':['west_deg','south_deg','east_deg','north_deg','model_bed_m'],
              'geometry_faces':len(faces),'boundary_face_counts':counts,'edge_sample_fallback_cells':fallbacks,
              'main_length_m':read(TERRAIN)['domain']['main_length_m'],
              'mesh_area_km2':float(areas.sum()/1e6),'lowered_cell_count':int((lowered>1e-6).sum()),
              'duration_seconds':duration-begin,'warmup_seconds':begin,'assets':files,
              'frames':[dict(row,t_seconds=row['t_seconds']-begin,file=f"{row['raw_index']:04}.bin") for row in after_warm],
              'sources_sha256':fingerprints,'validation':validation}
        save(run/'manifest.json',info)
    save(run/'validation.json',validation)
    save(run/'statistics.json',assessment)
    return validation


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--warmup-hours',type=int,default=24)
    args=parser.parse_args()
    require(args.run_id.isascii() and args.run_id.replace('_','').isalnum(),'运行 ID 仅允许 ASCII 字母、数字、下划线')
    dest=RUNS/args.run_id
    if dest.exists(): raise FileExistsError(dest)
    gdal.SetConfigOption('GDAL_PAM_ENABLED','NO')
    parameters=read(PARAMS)
    original=parameters['clock']['warmup']['value']
    requested=args.warmup_hours*3600
    require(requested>=original and requested%1800==0,'预热扩展必须是整帧且不能缩短已准备的基准')
    if requested>original:
        shift=requested-original
        for end in ('W','E'):
            for row in parameters['boundary'][end]['series']['value']:
                if row[0]>=original: row[0]+=shift
        for row in parameters['boundary']['E']['relative_depth_knots']:
            if row[0]>=original: row[0]+=shift
        parameters['clock']['warmup']['value']=requested
        parameters['clock']['end']['value']+=shift
        parameters['run_adjustment']={'warmup_hours':args.warmup_hours,'shifted_forcing_seconds':shift,
                                      'reason':'24 h pilot of full input exceeded last-window 5% flux-imbalance threshold'}
    require(parameters['rainfall']['value']==0,'此求解入口只接受已经验收的零降雨情景')
    fingerprints={str(p.relative_to(ROOT)).replace(os.sep,'/'):digest(p) for p in (SOURCE,Path(__file__),PARAMS,BOUNDARY,TERRAIN,DOMAIN,DEM)}
    require(fingerprints[str(DEM.relative_to(ROOT).as_posix())]==read(TERRAIN)['sources_sha256'][DEM.relative_to(ROOT).as_posix()],
            'Phase 2 DEM 指纹不符')
    RUNS.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(dir=RUNS,prefix=f'_incomplete_{args.run_id}_'))
    raw=work/'raw'; raw.mkdir()
    save(work/'parameters.json',parameters)
    program=work/'solver.exe'
    subprocess.run([str(COMPILER),'/nologo','/optimize+','/platform:x64','/out:'+str(program),str(SOURCE)],check=True)
    with tempfile.TemporaryDirectory(prefix='hydro-cases-') as temp:
        checks=analytical_checks(program,Path(temp))
    mesh=make_mesh(parameters,args.pilot)
    duration=7200 if args.pilot else parameters['clock']['end']['value']
    stride=900 if args.pilot else 1800
    # Sample each independent smoothstep forcing every 60 s; the solver interpolates those samples.
    w=parameters['boundary']['W']['series']['value']; e=parameters['boundary']['E']['series']['value']
    schedule=[(t,interpolate(w,t),interpolate(e,t)) for t in range(0,duration+1,60)]
    side=parameters['boundary']['lateral']
    write_solver_input(raw/'mesh_and_forcing.bin',mesh[0],mesh[1],schedule,duration,stride,
                       (side['wet_threshold']['value'],side['friction_slope']['value'],side['manning']['value']))
    print(f'Start {args.run_id}: {len(mesh[0])} cells, {len(mesh[1])} faces',flush=True)
    start=time.monotonic()
    subprocess.run([str(program),str(raw/'mesh_and_forcing.bin'),str(raw)],check=True)
    validation=export_result(work,mesh,parameters,duration,checks,fingerprints,time.monotonic()-start,args.pilot)
    require(all(digest(ROOT/p)==h for p,h in fingerprints.items()),'源输入在运行期间变化')
    (work/'solver.exe').unlink()
    if dest.exists(): raise FileExistsError(dest)
    work.rename(dest)
    print(json.dumps(validation,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
