"""Combine disjoint regional worklists that used identical full scene commands.

Each package's satellite_ids selects its worklist. All other manifest fields,
scene commands, point tables and frozen EOP must equal the parent package.
Native sampling and execution are checked separately in every source run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from summarize_stk_region import aggregate,check_package_binding
from stk_evidence import native_region_sampling,native_eop_binding


def combine(package,runs):
    package=Path(package)
    parent=json.loads((package/'manifest.json').read_text())
    expected=set(parent['satellite_ids']);seen=set();frames=[];statuses=[];provenance=[];steps=set()
    common={k:v for k,v in parent.items() if k!='satellite_ids'}
    names={'manifest.json','build_scenario.txt','build_coverage.txt','GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt'}
    if parent.get('eop_file'):names.add(parent['eop_file'])
    parent_hashes={n:hashlib.sha256((package/n).read_bytes()).hexdigest() for n in names}
    for path in runs:
        run=Path(path);group_package=run.parent
        manifest=json.loads((group_package/'manifest.json').read_text())
        if {k:v for k,v in manifest.items() if k!='satellite_ids'}!=common:
            raise ValueError('partition changes scenario metadata')
        ids=set(manifest['satellite_ids'])
        if not ids or not ids.issubset(expected) or seen & ids:
            raise ValueError('empty, unknown or duplicate satellite worklist')
        seen.update(ids)
        evidence=json.loads((run/'package_evidence.json').read_text(encoding='utf-8-sig'))
        check_package_binding(group_package,evidence)
        if any(evidence[n]!=parent_hashes[n] for n in names-{'manifest.json'}):
            raise ValueError('partition changes scene commands or input data')
        execution=json.loads((run/'run_status.json').read_text(encoding='utf-8-sig'))
        if execution['status']!='completed' or not execution['coverage_computed'] or execution['skip_region']:
            raise ValueError('partition did not complete regional computation')
        native=native_region_sampling(run/'Task2_Constellation.sca',manifest,execution['region_step_s'])
        eop=native_eop_binding(run,group_package,manifest)
        steps.add(native['fixed_step_s'])
        status=json.loads((run/'region_access_status.json').read_text(encoding='utf-8-sig'))
        raw=pd.read_csv(run/'region_access_raw.csv')
        aggregate(raw,status,manifest)  # Check counts and all component pairs before combining.
        frames.append(raw);statuses.extend(status)
        provenance.append(dict(run=str(run),satellite_ids=sorted(ids),native_sampling=native,
            native_eop=eop,package_sha256=evidence,source_sha256=hashlib.sha256((run/'region_access_raw.csv').read_bytes()).hexdigest(),
            native_sampling_sha256=hashlib.sha256((run/'Task2_Constellation.sca').read_bytes()).hexdigest()))
    if seen!=expected or len(steps)!=1:raise ValueError('incomplete worklists or mixed sampling steps')
    result=aggregate(pd.concat(frames,ignore_index=True),statuses,parent)
    result.update(package_binding_verified=True,package_sha256=parent_hashes,
        native_sampling=dict(verified=True,pairs=len(statuses),fixed_step_s=steps.pop()),
        native_eop=provenance[0]['native_eop'],
        execution_settings=dict(method='disjoint worklists; identical full scene input',source_runs=provenance))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True);p.add_argument('--runs',nargs='+',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();result=combine(a.package,a.runs)
    Path(a.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['region_revisit'],indent=2))
