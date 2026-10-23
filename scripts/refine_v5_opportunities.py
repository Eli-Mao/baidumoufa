"""Bounded shorter/interior search for free intervals rejected at their edges."""
import sys,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from satplan.v5 import State,Catalog
from satplan.v5_physics import PhysicalOracle
BASE=Path(os.environ.get('V6_CACHE_DIR','D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'))
SEALED=Path(os.environ.get('V6_BASELINE_DIR',str(ROOT.parents[1]/'outputs/v5_sealed')))
OUT=Path(os.environ.get('V6_ANALYSIS_DIR',str(ROOT/'data/out/v6_analysis')))
def run():
    p=pd.read_csv(SEALED/'best_v5_plan.csv');w=pd.read_csv(BASE/'windows.csv');s=State(p);c=Catalog(w);oracle=PhysicalOracle()
    f=pd.read_csv(OUT/'uncovered_opportunities.csv');rows=[]
    for r in f[(f.free_windows>0)&~f.direct_physical_insert].itertuples(index=False):
        found=None;tested=0
        for i in c.by_sat[int(r.sat_id)]:
            for a,b in s.free_intervals(int(c.site[i]),int(r.sat_id),float(c.start[i]),float(c.end[i])):
                for dur in [120.,180.,240.]:
                    for start in [a+.1,a+1.,(a+b-dur)/2,b-dur-.1,b-dur-1.]:
                        if start<a or start+dur>b:continue
                        t=c.task(i,start,start+dur,s.next_id)
                        if not s.fits(t):continue
                        tested+=1
                        if oracle(t):found=t;break
                    if found:break
                if found:break
            if found:break
        row={'sat_id':int(r.sat_id),'priority':r.priority,'tested_candidates':tested,'shorter_interior_physical_insertion':found is not None}
        if found:row.update(station=found.station,start=found.start,end=found.end,score=found.score)
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/'edge_rejected_refinement.csv',index=False)
    (OUT/'edge_refinement.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps(rows))
if __name__=='__main__':run()
