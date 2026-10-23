"""Independent CSV arithmetic plus frozen whole-plan constraint verification."""
import sys,argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd,numpy as np
from satplan import rules
def verify(plan,targets,windows=None):
    p=pd.read_csv(plan);m=pd.read_csv(targets)
    assert p.task_id.is_unique and m.sat_id.is_unique
    truth=p.merge(m[['sat_id','priority','priority_score']],on='sat_id',suffixes=('','_truth'),validate='many_to_one')
    assert len(truth)==len(p) and (truth.priority==truth.priority_truth).all() and (truth.priority_score==truth.priority_score_truth).all()
    assert np.isfinite(p[['t_start_s','t_end_s','dur_s']]).all().all()
    assert p.dur_s.between(120,240).all() and ((p.t_end_s-p.t_start_s-p.dur_s).abs()<=1e-6).all()
    coefficients=.6+.4*(p.dur_s-120)/120
    assert ((coefficients-p.duration_score).abs()<1e-9).all()
    score=float((truth.priority_score_truth*coefficients).sum())
    out={'independent_csv_score':score,'tasks':len(p),'covered':p.sat_id.nunique(),'coverage_by_priority':p.drop_duplicates('sat_id').groupby('priority').size().to_dict()}
    if windows:
        issues=rules.plan_violations(p,pd.read_csv(windows),max_report=1000000)
        out['hard_violations']=len(issues);assert not issues,issues[:5]
    return out
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--plan',type=Path,required=True);a.add_argument('--targets',type=Path,required=True);a.add_argument('--windows',type=Path);o=a.parse_args();print(json.dumps(verify(o.plan,o.targets,o.windows),indent=2))
