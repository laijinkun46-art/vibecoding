"""Run independent overbank sensitivity cases with the existing solver and fixed v2 mesh."""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import run_full_reach_hydro as model
import numpy as np
from osgeo import gdal

ROOT = model.ROOT
BASE = model.RUNS / 'full_reach_v2'
OUT = ROOT / 'outputs/full_reach_overbank_v1'
CONFIG = ROOT / 'data/scenarios/overbank_trials_v1.json'


def matching_mesh(params):
    mesh = model.make_mesh(params,False)
    cells, _, rectangles, lookup, *_ = mesh
    original = np.fromfile(BASE/'web/cells.bin',dtype='<f4').reshape(-1,5)
    if not np.array_equal(original,np.column_stack((rectangles,cells[:,0])).astype('<f4')):
        raise ValueError('试验网格或地形偏离固定的 v2 基准')
    if not np.array_equal(np.fromfile(BASE/'web/index.bin',dtype='<u4'),lookup.ravel()):
        raise ValueError('试验索引偏离固定的 v2 基准')
    return mesh


def prepare(params, case, settings):
    key = params['clock']['warmup']['value']
    original_stop = params['clock']['end']['value']
    for terminal, name in [('W','west'),('E','east')]:
        points = params['boundary'][terminal]['series']['value']
        initial = points[0][1]
        factor = case[name+'_excursion_factor']
        for point in points:
            if point[0]>key:
                if terminal=='W':
                    point[0] = key+round((point[0]-key)*case['west_duration_factor'])
                elif case['east_shift_h']:
                    point[0] += round(case['east_shift_h']*3600)
                point[1] = initial + (point[1]-initial)*factor
        if not all(b[0]>a[0] for a,b in zip(points,points[1:])):
            raise ValueError('边界过程节点顺序无效')
        params['boundary'][terminal]['series']['basis'] = '教学参数敏感性试验；基流不变，只缩放洪水扰动。'
        if terminal=='E':
            floor=params['bathymetry']['derived']['east_bed_m']
            params['boundary']['E']['relative_depth_knots']=[[t,q-floor] for t,q in points]
    final=max(original_stop,*(params['boundary'][t]['series']['value'][-1][0] for t in ('W','E')))
    final=max(final,key+round(settings.get('display_h',0)*3600))
    params['clock']['end']['value']=int(np.ceil(final/1800)*1800)
    params['clock']['warmup']['basis']='沿用 v2 已验收的 36 h 预热条件。'
    params['run_adjustment']={'protocol':'fixed_v2_mesh_overbank',**case}
    params['scenario_id']='full_reach_overbank_'+settings['id']
    params['label_zh']='2024 年洪水背景 · 二维漫岸教学情景'


def model_frames(raw, begin):
    budgets=model.budgets(raw/'budget.csv')
    return budgets,[row for row in budgets if row['t_seconds']>=begin]


def raw_state(raw, row):
    return np.fromfile(raw/('%04d.f64'%int(row['index'])),dtype='<f8').reshape(-1,3)


def assess(raw, mesh, begin):
    cells,_,_,_,overbank,*_=mesh
    budgets, after=model_frames(raw,begin)
    baseline=raw_state(raw,after[0])[:,0]
    allowed=(baseline<model.WET)&overbank
    area=cells[:,2]/1e6
    first=budgets[0]['volume_m3']
    history=[]
    for row in after:
        h=raw_state(raw,row)[:,0]
        residual=row['volume_m3']-first-row['inlet_m3']+row['east_m3']+row['lateral_m3']-row['correction_m3']
        history.append({'seconds':row['t_seconds']-begin,'wet_km2':float(area[h>=model.WET].sum()),
                        'new_km2':float(area[allowed&(h>=model.WET)].sum()),
                        'new_10cm_km2':float(area[allowed&(h>=.1)].sum()),
                        'mass_error':abs(residual)/max(1,first+row['inlet_m3'])})
    peak=max(history,key=lambda r:r['new_km2'])
    E=np.diff([r['east_m3'] for r in after])
    W=np.diff([r['inlet_m3'] for r in after])
    last=budgets[-1]
    return {'peak':peak,'last':history[-1],'peak_recession_km2':peak['new_km2']-history[-1]['new_km2'],
            'max_mass_error':max(r['mass_error'] for r in history),'max_speed_mps':last['max_speed_mps'],
            'min_raw_depth_m':last['min_raw_depth_m'],'east_reverse_m3':float(-E[E<0].sum()),
            'east_out_m3':float(E[E>0].sum()),'inlet_m3':float(W.sum()),
            'lateral_m3':last['lateral_m3']-after[0]['lateral_m3'],'history':history}


def run_case(settings, case_id, final_id=None):
    config=settings['cases'][case_id]
    design={'id':case_id,**settings}
    params=model.read(BASE/'parameters.json')
    prepare(params,config,design)
    mesh=matching_mesh(params)
    warm=params['clock']['warmup']['value']
    target= (model.RUNS / final_id) if final_id else (OUT/'trials'/case_id)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(dir=target.parent,prefix='_pending_'+target.name+'_'))
    raw=work/'raw'
    raw.mkdir()
    model.save(work/'parameters.json',params)
    sources=(model.SOURCE,Path(model.__file__),Path(__file__),CONFIG,BASE/'parameters.json',
             BASE/'manifest.json',BASE/'web/cells.bin',BASE/'web/index.bin',model.BOUNDARY,
             model.TERRAIN,model.DOMAIN,model.DEM,ROOT/'data/study_area/nanning_yongjiang_aoi.geojson')
    if not final_id:
        warm_row=model.read(BASE/'manifest.json')['frames'][0]['raw_index']
        warmfile=BASE/'raw'/('%04d.f64'%warm_row)
        mesh[0][:,3:]=np.fromfile(warmfile,dtype='<f8').reshape(-1,3)
        sources=(*sources,warmfile)
    fingerprints={p.relative_to(ROOT).as_posix():model.digest(p) for p in sources}
    begin=warm if final_id else 0
    offset=0 if final_id else warm
    duration=params['clock']['end']['value'] if final_id else int(settings['pilot_display_h']*3600)
    w,e=[params['boundary'][end]['series']['value'] for end in ('W','E')]
    curves=[(t,model.interpolate(w,t+offset),model.interpolate(e,t+offset)) for t in range(0,duration+1,60)]
    side=params['boundary']['lateral']
    model.write_solver_input(raw/'mesh_and_forcing.bin',mesh[0],mesh[1],curves,duration,1800,
                             tuple(side[k]['value'] for k in ('wet_threshold','friction_slope','manning')))
    exe=work/'solver.exe'
    subprocess.run([str(model.COMPILER),'/nologo','/optimize+','/platform:x64','/out:'+str(exe),str(model.SOURCE)],check=True)
    with tempfile.TemporaryDirectory(prefix='overbank-cases-') as temp:
        checks=model.analytical_checks(exe,Path(temp))
    start=time.monotonic()
    print('Solving',case_id,'hours',duration/3600,flush=True)
    with (work/'solver.log').open('x',encoding='utf-8') as log:
        subprocess.run([str(exe),str(raw/'mesh_and_forcing.bin'),str(raw)],check=True,stdout=log,stderr=subprocess.STDOUT)
    elapsed=time.monotonic()-start
    result=assess(raw,mesh,begin)
    result.update(case=case_id,wall_seconds=elapsed,check_cases=checks,input_sha256=fingerprints,
                  mode='full_unpublished' if final_id else 'warm_restart_sensitivity')
    model.save(work/'overbank_assessment.json',result)
    if (result['max_mass_error']>model.LIMITS['relative_mass_error'] or result['max_speed_mps']>model.LIMITS['max_speed_mps']
            or result['min_raw_depth_m']<model.LIMITS['min_raw_depth_m']):
        raise ValueError('新试算未通过原有数值门槛')
    if final_id:
        model.export_result(work,mesh,params,duration,checks,fingerprints,elapsed,False)
    if any(model.digest(ROOT/p)!=s for p,s in fingerprints.items()):
        raise ValueError('源输入发生变化')
    for k in ['peak','last','peak_recession_km2','east_reverse_m3','east_out_m3','inlet_m3','max_speed_mps']:
        print(k,result[k],flush=True)
    exe.unlink()
    # Full results still need independent pathway evidence before the final directory is visible to the API.
    if final_id:
        print('Independent acceptance required at',work,flush=True)
    else:
        work.rename(target)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('case')
    parser.add_argument('--final-id')
    args=parser.parse_args()
    gdal.SetConfigOption('GDAL_PAM_ENABLED','NO')
    settings=model.read(CONFIG)
    if args.final_id and not (args.final_id.startswith('full_reach_v') and args.final_id.removeprefix('full_reach_v').isdigit()):
        raise ValueError('最终运行号不符合 full_reach_vN 格式')
    run_case(settings,args.case,args.final_id)


if __name__=='__main__':
    main()
