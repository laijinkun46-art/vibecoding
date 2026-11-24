"""Independently check full-reach overbank paths, then publish a validated version."""
from __future__ import annotations

import argparse
import base64
import hashlib
import heapq
from pathlib import Path

import numpy as np
from run_overbank_hydro import BASE, ROOT, CONFIG, assess, matching_mesh, model, model_frames, raw_state
from osgeo import ogr, osr


def locations(rects):
    with ogr.Open(str(model.DOMAIN),0) as source:
        layer=source.GetLayerByName('main_centerline')
        feature=layer.GetNextFeature()
        line=model.geom(feature.GetGeometryRef())
    geo=np.column_stack(((rects[:,0]+rects[:,2])*.5,(rects[:,1]+rects[:,3])*.5))
    projection=osr.CoordinateTransformation(model.spatial_ref(4326),model.spatial_ref(32649))
    xy=np.array(projection.TransformPoints(geo.tolist()))[:,:2]
    coords=np.array(line.coords)
    vectors=np.diff(coords,axis=0)
    length=np.linalg.norm(vectors,axis=1)
    chain=np.r_[0,np.cumsum(length)]
    off, along, side=[],[],[]
    for p in xy:
        delta=p-coords[:-1]
        t=np.clip(np.sum(delta*vectors,axis=1)/length**2,0,1)
        residual=delta-t[:,None]*vectors
        j=np.argmin(np.linalg.norm(residual,axis=1))
        off.append(float(np.linalg.norm(residual[j])))
        along.append(float(chain[j]+t[j]*length[j]))
        side.append(int(np.sign(vectors[j,0]*residual[j,1]-vectors[j,1]*residual[j,0])))
    return geo,xy,np.array(off),np.array(along),np.array(side)


def flux(states, beds, l, r, normal, lengths):
    """Re-evaluate the existing solver's instantaneous interior-face mass flux."""
    h=states[:,0]
    uv=np.divide(states[:,1:],h[:,None],out=np.zeros_like(states[:,1:]),where=h[:,None]>model.DRY)
    un=np.sum(uv[l]*normal,axis=1)
    ur=np.sum(uv[r]*normal,axis=1)
    crest=np.maximum(beds[l],beds[r])
    stage=beds+h
    a=np.maximum(stage[l]-crest,0)
    b=np.maximum(stage[r]-crest,0)
    wave=np.maximum(abs(un)+np.sqrt(9.81*a),abs(ur)+np.sqrt(9.81*b))
    return .5*lengths*(a*un+b*ur-wave*(b-a))


def flow_tree(h, rates, xy, channel, l, r):
    """Shortest wet path directed by the signs of the snapshot's face fluxes."""
    wet=h>=model.WET
    graph=[[] for _ in h]
    for at in np.flatnonzero(wet[l]&wet[r]&(abs(rates)>.02)):
        a,b=(l[at],r[at]) if rates[at]>0 else (r[at],l[at])
        graph[a].append((b,at))
    distances=np.full(len(h),np.inf)
    parents=np.full(len(h),-1)
    joins=np.full(len(h),-1)
    source=np.flatnonzero(wet&channel)
    distances[source]=0
    q=[(0,int(k)) for k in source]
    heapq.heapify(q)
    while q:
        dist,a=heapq.heappop(q)
        if dist!=distances[a]:
            continue
        for b,face in graph[a]:
            candidate=dist+np.linalg.norm(xy[a]-xy[b])
            if candidate<2200 and candidate<distances[b]:
                distances[b]=candidate
                parents[b]=a
                joins[b]=face
                heapq.heappush(q,(candidate,b))
    return distances,parents,joins


def verify_paths(raw, frames, mesh):
    cells, faces, rects, _, outside,*_=mesh
    geo,xy,distance,station,sides=locations(rects)
    internal=np.asarray([row for row in faces if row[1]>=0])
    l,r=internal[:,:2].astype(int).T
    lengths=internal[:,3]
    normal=internal[:,4:6]
    channel=distance<111
    snapshots=np.stack([raw_state(raw,row) for row in frames])
    depths=snapshots[:,:,0]
    initial=depths[0]<model.WET
    wet=depths>=model.WET
    # Work well inside the model edges and on both sides of the urban middle reach.
    domain=model.read(BASE/'manifest.json')['bounds']
    inside=(geo[:,0]>domain[0]+.012)&(geo[:,0]<domain[2]-.012)&(geo[:,1]>domain[1]+.011)&(geo[:,1]<domain[3]-.011)
    sustained=np.sum(depths>=.10,axis=0)>=2
    eligible=initial&outside&inside&sustained&(distance>=310)&(distance<=1450)&(station>6000)&(station<28000)
    first=np.argmax(wet,axis=0)
    top=np.argmax(depths,axis=0)
    result={-1:None,1:None}
    scores={-1:-1.,1:-1.}
    for i in range(1,len(frames)):
        candidates=np.flatnonzero(eligible&(first<=i)&(i-first<=3)&(depths[i]>=.15))
        if not len(candidates):
            continue
        q=flux(snapshots[i],cells[:,0],l,r,normal,lengths)
        ds,parent,edge=flow_tree(depths[i],q,xy,channel,l,r)
        for target in candidates[np.isfinite(ds[candidates])]:
            side=sides[target]
            if side not in scores:
                continue
            # Prefer a long connected inland path that has begun to wet and later recedes.
            score=.45*distance[target]/1000+.35*min(depths[top[target],target],2)/2
            score+=.25*float(depths[-1,target]<model.WET)-.04*(i-first[target])
            if score<=scores[side]:
                continue
            path=[int(target)]
            while parent[path[-1]]>=0:
                path.append(int(parent[path[-1]]))
            path.reverse()
            crosses=next(((a,b,edge[b]) for a,b in zip(path,path[1:]) if not outside[a] and outside[b]),None)
            if crosses is None:
                continue
            bank_l,bank_r,face=crosses
            depth=depths[i,target]
            speed=float(np.linalg.norm(snapshots[i,target,1:])/depth)
            offset=frames[0]['t_seconds']
            uv=lambda at,cell: snapshots[at,cell,1:]/max(depths[at,cell],model.DRY)
            pids=[max(0,int(first[target])-1),i,int(top[target]),len(frames)-1]
            observed=[dict(seconds=frames[j]['t_seconds']-offset,depth_m=float(depths[j,target]),
                           stage_m=float(depths[j,target]+cells[target,0]),speed_mps=float(np.linalg.norm(uv(j,target)))) for j in pids]
            result[side]={'cell':int(target),'lon':geo[target,0],'lat':geo[target,1],
                          'side':int(side),'offset_m':distance[target],'chainage_m':station[target],
                          'first_wet_seconds':frames[first[target]]['t_seconds']-offset,
                          'path_seconds':frames[i]['t_seconds']-offset,
                          'consecutive_frames_at_least_10cm':bool(np.any((depths[:-1,target]>=.1)&(depths[1:,target]>=.1))),
                          'path_cells':path,'path_coordinates':geo[path].tolist(),'path_length_m':ds[target],
                          'min_path_rate_m3s':float(min(abs(q[edge[k]]) for k in path[1:])),
                          'crossing':{'from':bank_l,'to':bank_r,'lonlat':geo[[bank_l,bank_r]].tolist(),
                                      'bed_m':cells[[bank_l,bank_r],0].tolist(),
                                      'depth_m':depths[i,[bank_l,bank_r]].tolist(),
                                      'stage_m':(cells[[bank_l,bank_r],0]+depths[i,[bank_l,bank_r]]).tolist(),
                                      'uv_mps':[uv(i,k).tolist() for k in (bank_l,bank_r)],
                                      'instantaneous_m3s_into_overbank':float(abs(q[face]))},
                          'samples':observed,'depth_m_at_path':float(depth),'speed_mps_at_path':speed}
            scores[side]=score
    return [dict(record,label=f'城区低地 {tag}') for tag,record in zip('AB',result.values()) if record is not None]


def check(run, publish):
    model.gdal.SetConfigOption('GDAL_PAM_ENABLED','NO')
    manifest=model.read(run/'manifest.json')
    params=model.read(run/'parameters.json')
    for p,expected in manifest['sources_sha256'].items():
        if model.digest(ROOT/p)!=expected:
            raise ValueError(f'源指纹不一致：{p}')
    mesh=matching_mesh(params)
    begin=params['clock']['warmup']['value']
    test=assess(run/'raw',mesh,begin)
    old=assess(BASE/'raw',mesh,begin)
    _,frames=model_frames(run/'raw',begin)
    witnesses=verify_paths(run/'raw',frames,mesh)
    # Independent comparison of every display frame against the solver's raw h/hu/hv.
    cells=mesh[0]
    for row, frame in zip(frames,manifest['frames'],strict=True):
        raw=raw_state(run/'raw',row)
        h=raw[:,0]
        uv=np.divide(raw[:,1:],h[:,None],out=np.zeros_like(raw[:,1:]),where=h[:,None]>model.DRY)
        expected=np.column_stack((h,h+cells[:,0],uv)).astype('<f4')
        path=run/'web'/frame['file']
        if model.digest(path)!=manifest['assets'][path.name]['sha256']:
            raise ValueError(f'网页帧指纹不一致：{path.name}')
        if not np.array_equal(expected,np.fromfile(path,dtype='<f4').reshape(-1,4)):
            raise ValueError(f'网页帧与求解结果不一致：{path.name}')
    targets=model.read(CONFIG)
    gate=(test['peak']['new_km2']>=targets['target_new_km2'] and test['peak_recession_km2']>=1
          and len(witnesses)>=2 and all(w['consecutive_frames_at_least_10cm'] for w in witnesses)
          and test['east_reverse_m3']<.01*test['inlet_m3'])
    v={'selected':publish,'accepted':gate,'target_km2':targets['target_new_km2'],
       'criterion':'initially dry, outside fixed v2 channel and blend footprint, wet at current frame',
       'witnesses':witnesses,'baseline':old,'new':test,'verified_frame_count':len(frames),
       'note':'Face fluxes are recomputed on snapshots. East reverse volume is summed from signed output-interval net fluxes.'}
    model.save(run/'independent_overbank_validation.json',v)
    print('Comparison peak/end',old['peak'],old['last'],test['peak'],test['last'],flush=True)
    print('Witnesses',[(w['label'],w['cell'],w['lon'],w['lat'],w['crossing']['instantaneous_m3s_into_overbank']) for w in witnesses],flush=True)
    if not gate:
        raise ValueError('未满足漫岸、持续湿润、退水或主河槽进水验收')
    if publish:
        masks=np.where(mesh[4],cells[:,2],0).astype('<f8').tobytes()
        manifest['overbank']={'weights_base64':base64.b64encode(masks).decode('ascii'),
                              'weights_sha256':hashlib.sha256(masks).hexdigest(),
                              'peak_seconds':test['peak']['seconds'],
                              'witnesses':[{k:w[k] for k in ('label','cell','lon','lat')} for w in witnesses]}
        for published, metrics in zip(manifest['frames'],test['history'],strict=True):
            if published['t_seconds']!=metrics['seconds']:
                raise ValueError('统计时刻与网页帧不一致')
            published['overbank_added_km2']=metrics['new_km2']
            published['overbank_added_10cm_km2']=metrics['new_10cm_km2']
        manifest['validation']['overbank_acceptance']='passed'
        target=model.RUNS/publish
        if target.exists():
            raise FileExistsError(target)
        model.save(run/'manifest.json',manifest)
        run.rename(target)
    print('Accepted',publish or run,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('draft',type=Path)
    parser.add_argument('--publish',choices=['full_reach_v3'])
    args=parser.parse_args()
    if args.draft.resolve().parent!=model.RUNS.resolve() or not args.draft.name.startswith('_pending_full_reach_'):
        raise ValueError('只允许独立的未发布完整运行')
    check(args.draft.resolve(),args.publish)


if __name__=='__main__':
    main()
