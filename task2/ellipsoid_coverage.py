"""Continuous rectangular access to WGS84 grid points, independently of STK.

A conservative spatial search proposes point/pass pairs. Along-track roots and
cross-track clipping refine each encounter; candidate time spacing is not an
access sampling interval. Supported domain: circular 500--700 km, .81 deg FOV.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.optimize import minimize_scalar,brentq
from earth_frames import AXES,EarthFrames,StkOrbit,geodetic_xyz,DEFAULT_EOP
from ellipsoid_access import point_margin
from continuous_region import _camera
from coverage import Grid,max_reachable_lat
from constellation import epoch_jd
from run_sim import load_elements

TAN=np.tan(np.radians(.81))


def camera_values(orbit,t,p):
    r,v=orbit.state(t)
    rho,up,along,cross=_camera(r,v)
    ray=p-r
    return np.column_stack((np.sum(ray*along,axis=1),np.sum(ray*cross,axis=1),
                            -np.sum(ray*up,axis=1)))


def satellite_intervals(orbit,points,tree,duration_s,candidate_step=10.):
    if not 0<candidate_step<=30: raise ValueError('candidate spacing must be in (0,30]')
    ts=np.r_[np.arange(0,duration_s,candidate_step),duration_s]
    r,_=orbit.state(ts)
    sub=r/np.sqrt(np.sum((r/AXES)**2,axis=1))[:,None]
    # 8 km/s bounds the surface subpoint speed in the supported altitude range.
    # 20 km bounds the diagonal footprint radius, including ellipsoid effects.
    neighbors=tree.query_ball_point(sub,20+8*candidate_step/2)
    sizes=np.fromiter(map(len,neighbors),int,len(neighbors))
    if not sizes.sum(): return np.empty((0,3))
    ids=np.concatenate([x for x in neighbors if len(x)])
    t=np.repeat(ts,sizes)
    p=points[ids]
    # Solve the along-track midline crossing, not the closest sampled location.
    for _ in range(3):
        c=camera_values(orbit,t,p)
        derivative=(camera_values(orbit,t+.1,p)[:,0]-camera_values(orbit,t-.1,p)[:,0])/.2
        if np.any(abs(derivative)<1): raise ValueError('unsupported slow along-track encounter')
        t-=c[:,0]/derivative
    valid=(t>=-4)&(t<=duration_s+4)
    ids,t,p=ids[valid],t[valid],p[valid]
    c=camera_values(orbit,t,p)
    valid=(TAN*c[:,2]-abs(c[:,1])>=-.1)
    ids,t,p=ids[valid],t[valid],p[valid]
    if not len(t): return np.empty((0,3))
    order=np.lexsort((t,ids));ids,t,p=ids[order],t[order],p[order]
    keep=np.r_[True,(np.diff(ids)!=0)|(np.diff(t)>1.)]
    ids,t,p=ids[keep],t[keep],p[keep]
    # For these nadir circular passes x decreases monotonically. Newton roots
    # of the two along-track planes have nonzero slope throughout the bracket.
    bounds=[]
    for side in (-1.,1.):
        tt=t+side*2
        for _ in range(3):
            c=camera_values(orbit,tt,p)
            value=TAN*c[:,2]+side*c[:,0]
            cp=camera_values(orbit,tt+.05,p);cm=camera_values(orbit,tt-.05,p)
            slope=(TAN*(cp[:,2]-cm[:,2])+side*(cp[:,0]-cm[:,0]))/.1
            tt-=value/slope
        bounds.append(tt)
    lo,hi=bounds
    if np.any(lo>hi) or np.any(lo<t-4) or np.any(hi>t+4): raise ValueError('along-track root escaped bound')
    a,b=camera_values(orbit,lo,p),camera_values(orbit,hi,p)
    mid=camera_values(orbit,t,p)
    ma,mb,mm=[TAN*c[:,2]-abs(c[:,1]) for c in (a,b,mid)]
    # Near-tangent cross-track curvature can create TWO windows with a real
    # gap between them. Never replace their union with the first/last endpoints.
    inside=np.minimum.reduce([ma,mb,mm])>.01
    marginal=np.flatnonzero(~inside & (np.maximum.reduce([ma,mb,mm])>=-.01))
    extras=[]
    for j in marginal:
        def margin(tt):
            c=camera_values(orbit,np.array([tt]),p[j:j+1])[0]
            return TAN*c[2]-abs(c[1])
        low=minimize_scalar(margin,bounds=(lo[j],hi[j]),method='bounded',options={'xatol':1e-6})
        high=minimize_scalar(lambda tt:-margin(tt),bounds=(lo[j],hi[j]),method='bounded',options={'xatol':1e-6})
        knots=sorted(set([float(lo[j]),float(hi[j]),float(t[j]),float(low.x),float(high.x)]))
        roots=[]
        for left,right in zip(knots[:-1],knots[1:]):
            if margin(left)*margin(right)<0:roots.append(brentq(margin,left,right,xtol=1e-6))
        edges=[lo[j],*sorted(roots),hi[j]]
        for left,right in zip(edges[:-1],edges[1:]):
            if margin((left+right)/2)>=0:
                left,right=max(0.,left),min(duration_s,right)
                if right>left:extras.append([ids[j],left,right])
    lo,hi=np.maximum(lo,0),np.minimum(hi,duration_s)
    keep=inside&(hi>lo)
    return np.vstack((np.column_stack((ids[keep],lo[keep],hi[keep])),np.asarray(extras).reshape(-1,3)))


def simulate_global(elems,jd0,days=7.,candidate_step=10.,eop_path=DEFAULT_EOP,progress=None):
    if elems.empty or not elems.alt_km.between(500,700).all(): raise ValueError('supports circular 500--700 km orbits')
    if 'ecc' in elems and (elems.ecc!=0).any(): raise ValueError('only circular orbits supported')
    duration=days*86400.
    frames=EarthFrames(jd0,duration,eop_path)
    grid=Grid(-90,90,1)
    reach=max_reachable_lat(elems.inc_deg.to_numpy(),elems.alt_km.to_numpy())
    mask=abs(grid.lat_c)<=reach
    lat,lon=grid.lat_c[mask],grid.lon_c[mask]
    points=geodetic_xyz(lon,lat);tree=cKDTree(points)
    first=np.full(len(points),np.inf);count=np.zeros(len(points),int)
    accesses=[]
    for el in elems.itertuples():
        windows=satellite_intervals(StkOrbit(el,frames),points,tree,duration,candidate_step)
        ids=windows[:,0].astype(int)
        np.minimum.at(first,ids,windows[:,1]);np.add.at(count,ids,1)
        accesses.extend((int(el.sat_id),int(i),float(a),float(b)) for i,a,b in windows)
        if progress:progress(int(el.sat_id),len(windows),int(np.isfinite(first).sum()))
    times=np.sort(first);n=len(first);k90=int(np.ceil(.9*n))-1
    metrics=dict(n_valid=n,n_covered=int(np.isfinite(first).sum()),coverage=float(np.isfinite(first).mean()),
                 T90_s=float(times[k90]) if np.isfinite(times[k90]) else None,
                 T100_s=float(times[-1]) if np.isfinite(times[-1]) else None)
    cells=pd.DataFrame(dict(point_id=np.arange(n),lat_deg=lat,lon_deg=lon,
                            first_access_s=np.where(np.isfinite(first),first,np.nan),n_accesses=count))
    return dict(global_coverage=metrics,access_rows=len(accesses),
                model=dict(earth='WGS84',rate_model='stk',eop_sha256=frames.sha256,
                           candidate_step_s=candidate_step,geometry='analytic rectangular FOV with event roots',
                           stk_verified=False)),cells,pd.DataFrame(accesses,columns=['sat_id','point_id','start_s','stop_s'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elements',required=True);p.add_argument('--out',required=True)
    p.add_argument('--days',type=float,default=7.);p.add_argument('--candidate-step',type=float,default=10.)
    p.add_argument('--eop',default=str(DEFAULT_EOP))
    a=p.parse_args();out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    result,cells,windows=simulate_global(load_elements(a.elements),epoch_jd(),a.days,a.candidate_step,a.eop,
        progress=lambda sid,n,k:print(f'Satellite {sid}: {n} accesses; {k} covered points',flush=True))
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    cells.to_csv(out.with_suffix('.csv'),index=False)
    windows.to_csv(out.with_name(out.stem+'_intervals.csv'),index=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
