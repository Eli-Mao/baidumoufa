"""Correct endpoint membership metadata after a fresh, unchanged physical audit."""
from pathlib import Path
import sys,json,shutil,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import numpy as np,pandas as pd
import audit_plan_physics

def endpoint_membership(duration,step=1.):
    offsets=np.unique(np.append(np.arange(0.,duration+1e-9,step),duration))
    return bool(np.any(offsets==duration)),len(offsets),float(max(0.,offsets[-1]-duration))

def run(folder):
    original=folder/'original_endpoint_flags';original.mkdir(exist_ok=True)
    for name in ['physics_audit.csv','physics_audit.json']:
        if not (original/name).exists():shutil.copy2(folder/name,original/name)
    started=time.perf_counter()
    report=audit_plan_physics.run(folder/'final_plan.csv',folder/'physics_audit.json')
    details=pd.read_csv(folder/'physics_audit.csv');plan=pd.read_csv(folder/'final_plan.csv').set_index('task_id')
    previous=details.exact_end_included.copy();overruns=[]
    for idx,row in details.iterrows():
        task=plan.loc[row.task_id];actual,n,overrun=endpoint_membership(float(task.t_end_s-task.t_start_s))
        assert actual and n==int(row.samples)
        details.at[idx,'exact_end_included']=actual;overruns.append(overrun)
    details['original_last_element_flag']=previous;details['last_grid_offset_excess_s']=overruns
    details.to_csv(folder/'physics_audit.csv',index=False)
    report['exact_endpoints_included']=bool(details.exact_end_included.all())
    report['endpoint_flag_logic']='Exact endpoint membership, rather than comparison to final sorted element. Sampling arrays and physical predicates unchanged.'
    report['corrected_metadata_rows']=int((~previous).sum())
    report['additional_full_reaudit_s']=time.perf_counter()-started
    (folder/'physics_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert report['all_pass'] and report['exact_endpoints_included']
    trial=json.loads((folder/'trial.json').read_text());trial['additional_full_reaudit_s']=report['additional_full_reaudit_s'];trial['endpoint_metadata_corrected_rows']=report['corrected_metadata_rows'];trial['endpoint_correction_does_not_change_physical_sampling']=True
    (folder/'trial.json').write_text(json.dumps(trial,indent=2),encoding='utf-8')
    print(json.dumps({'trial':folder.name,'all_pass':True,'tasks':report['tasks'],'corrected_metadata_rows':report['corrected_metadata_rows'],'additional_reaudit_s':report['additional_full_reaudit_s']}),flush=True)

if __name__=='__main__':
    base=ROOT/'data/out/v5_comparison'
    for name in ['formal_b20_s11_v5','formal_b60_s11_v5']:run(base/name)
