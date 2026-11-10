"""One complete, frozen-input Python/STK verification workflow (no optimization)."""
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import pandas as pd
from compare_geometry import (sha,load_json,points_comparison,windows_comparison,
                              read_refinement,refined_points)

ROOT=Path(__file__).resolve().parent


def verify_reused_scene(package,reference):
    """Allow native-result reuse only for identical physical inputs and grids."""
    package,reference=Path(package),Path(reference)
    a,b=load_json(package/'manifest.json'),load_json(reference/'manifest.json')
    for key in ('epoch_utc','stop_utc','duration_s','step_s','satellite_ids','grid_counts','region_area_targets'):
        if a.get(key)!=b.get(key):raise ValueError('native reference differs: '+key)
    if sha(package/a['eop_file'])!=sha(reference/b['eop_file']):raise ValueError('native reference EOP differs')
    def normalized(path):
        s=path.read_text(encoding='utf-8-sig')
        return re.sub(r'EarthData \* EOPFile "[^"]+"','EarthData * EOPFile "@FROZEN@"',s).strip()
    if normalized(package/'build_scenario.txt')!=normalized(reference/'build_scenario.txt'):
        raise ValueError('native reference orbital elements, sensor or boundary differs')
    for name in ('build_coverage.txt','GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt'):
        if sha(package/name)!=sha(reference/name):raise ValueError('native reference grid/assets differ: '+name)
    return True


def resolve_reference(base,package):
    base=Path(base);summary=load_json(base/'validation_summary.json')
    if not summary.get('native_metrics_convergence_verified'):raise ValueError('native reference has not passed convergence')
    # Old source hashes describe the source at that historical run. Verify all
    # frozen artifact hashes; current code is bound separately in this run.
    verified=0
    for name,digest in summary['evidence_sha256'].items():
        p=(ROOT/name).resolve()
        p.relative_to(ROOT)
        if p.suffix in ('.py','.ps1'):continue
        if sha(p)!=digest:raise ValueError('modified native reference evidence: '+name)
        verified+=1
    native_package=base/'stk';verify_reused_scene(package,native_package)
    fine=native_package/summary['runs']['global_fine']
    orbit=native_package/summary['runs']['orbit']/'stk_positions.csv'
    return dict(package=native_package,global_csv=base/'global_native_30.csv',
                global_raw=fine/'GlobalReachable_accesses.txt',region_csv=base/'region_access_intervals.csv',
                orbit=orbit,reference=base,verified_artifacts=verified)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elements',default=str(ROOT/'out/n28/constellation.csv'))
    p.add_argument('--out',default=str(ROOT/'out'/('engineering_'+datetime.now().strftime('%Y%m%d_%H%M%S'))))
    p.add_argument('--profile',default=str(ROOT/'data/validation_profile.json'))
    p.add_argument('--reuse-stk',help='Reuse verified native evidence only after identical-input checks; Python is always recomputed')
    p.add_argument('--cores',type=int,default=8)
    args=p.parse_args(argv)
    out=Path(args.out).resolve();elements=Path(args.elements).resolve();profile_path=Path(args.profile).resolve()
    if out.exists() and any(out.iterdir()):p.error('output directory must be new or empty')
    if not 1<=args.cores<=16:p.error('cores must be between 1 and 16')
    out.mkdir(parents=True,exist_ok=True)
    profile=load_json(profile_path);eop=ROOT/profile['eop'];region=ROOT/profile['region']
    if profile['days']!=7 or profile['epoch_utc']!='2027-01-01T00:00:00' or profile['rate_model']!='stk':
        raise ValueError('this verified workflow requires the fixed 7-day 2027 STK scenario')
    for key,required in [('native_global_min_step_s',.001),('native_event_tolerance_s',.01),('grazing_event_tolerance_s',.00001)]:
        if profile[key]!=required:raise ValueError('unsupported native profile setting: '+key)
    if sha(eop)!=profile['eop_sha256'] or sha(region)!=profile['region_sha256']:raise ValueError('profile input hash differs')
    from model_convention import element_model
    from run_sim import load_elements
    from validate import check_output
    el=load_elements(elements)
    checked=check_output(el,n_expected=len(el))
    if not checked['ok']:raise ValueError('invalid input constellation: '+str(checked))
    sources=list(ROOT.glob('*.py'))+list(ROOT.glob('*.ps1'))+list((ROOT/'famou').glob('*.py'))+list((ROOT/'tests').rglob('*.py'))+[x for x in (ROOT/'tests/data').rglob('*') if x.is_file()]+[ROOT/'requirements.txt']
    hashes={str(x.relative_to(ROOT)):sha(x) for x in sources}
    manifest=dict(status='running',started_utc=datetime.now(timezone.utc).isoformat(),
                  elements_path=str(elements),elements_sha256=sha(elements),profile=profile,
                  profile_sha256=sha(profile_path),design_rate_model=element_model(el),
                  propagation_rate_model='stk',source_sha256=hashes,
                  packages={name:importlib.metadata.version(name) for name in ('numpy','pandas','scipy','pyerfa')},
                  native_reference_requested=args.reuse_stk,steps=[])
    (out/'profile.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')

    def command(label,parts):
        print(label,flush=True)
        log=out/(f'{len(manifest["steps"])+1:02d}_'+label+'.log')
        with log.open('w',encoding='utf-8') as stream:
            completed=subprocess.run(parts,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        manifest['steps'].append(dict(label=label,command=list(map(str,parts)),returncode=completed.returncode,log=log.name))
        if completed.returncode:raise RuntimeError(label+' failed; see '+str(log))

    def python(label,*parts):command(label,[sys.executable,'-B','-X','utf8',*map(str,parts)])
    def native(label,script,*parts):command(label,['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/script),*map(str,parts)])
    checks={}
    try:
        python('unit_tests','-m','unittest','discover','-s','tests','-v')
        test_log=(out/manifest['steps'][-1]['log']).read_text(encoding='utf-8')
        tests_run=re.search(r'Ran (\d+) tests? in ([\d.]+)s',test_log)
        if not tests_run:raise RuntimeError('test result count missing')
        checks['unit_tests']=dict(ok=True,count=int(tests_run[1]),seconds=float(tests_run[2]))
        package=out/'stk'
        python('export_frozen_scene','stk_export.py','--elements',elements,'--out',package,'--region',region,'--eop',eop)
        python('python_global_coarse','ellipsoid_coverage.py','--elements',elements,'--out',out/'global_coarse.json',
               '--candidate-step',profile['python_global_candidate_steps_s'][0],'--eop',eop)
        python('python_global_fine','ellipsoid_coverage.py','--elements',elements,'--out',out/'global_fine.json',
               '--candidate-step',profile['python_global_candidate_steps_s'][1],'--eop',eop)
        for tag,step in zip(('coarse','fine'),profile['region_steps_s']):
            python('python_region_'+tag,'run_official_region.py','--elements',elements,'--out',out/('region_'+tag+'.json'),
                   '--region',region,'--eop',eop,'--step',step,'--tolerance',profile['python_event_tolerance_s'])
        checks['python_global_convergence']=windows_comparison(pd.read_csv(out/'global_coarse_intervals.csv'),
            pd.read_csv(out/'global_fine_intervals.csv'),keys=('sat_id','point_id'),tolerance_s=.001)
        checks['python_region_convergence']=windows_comparison(pd.read_csv(out/'region_coarse.csv'),
            pd.read_csv(out/'region_fine.csv'),tolerance_s=profile['comparison_tolerance_s'])
        if args.reuse_stk:
            ref=resolve_reference(Path(args.reuse_stk).resolve(),package)
            manifest['native_reuse']=dict(reference=str(ref['reference']),verified_artifacts=ref['verified_artifacts'],identical_physical_inputs=True)
            checks['native_global_convergence']=load_json(ref['reference']/'global_native_convergence.json')
            checks['native_region_convergence']=load_json(ref['reference']/'region_native_refined_convergence.json')
        else:
            runs=[]
            for tag,gstep,rstep in zip(('coarse','fine'),profile['native_global_max_steps_s'],profile['region_steps_s']):
                previous=set(package.glob('stk_run_*'))
                native('native_'+tag,'run_stk.ps1','-Package',package,'-Engine','-GlobalMaxStep',gstep,
                       '-RegionStep',rstep,'-ParallelCores',args.cores)
                created=set(package.glob('stk_run_*'))-previous
                if len(created)!=1:raise RuntimeError('ambiguous native run directory')
                run=created.pop();runs.append(run)
                python('native_global_'+tag,'summarize_stk_coverage.py','--package',package,'--run',run,'--out',out/('native_global_'+tag+'.json'))
                python('native_region_'+tag,'summarize_stk_region.py','--package',package,'--run',run,'--out',out/('native_region_'+tag+'.json'))
            for kind in ('global','region'):
                python('native_'+kind+'_convergence','compare_stk_convergence.py','--kind',kind,
                       '--coarse',out/('native_'+kind+'_coarse.json'),'--fine',out/('native_'+kind+'_fine.json'),
                       '--out',out/('native_'+kind+'_convergence.json'))
                checks['native_'+kind+'_convergence']=load_json(out/('native_'+kind+'_convergence.json'))
            ref=dict(package=package,global_csv=out/'native_global_fine.csv',
                     global_raw=runs[1]/'GlobalReachable_accesses.txt',region_csv=out/'native_region_fine.csv',
                     orbit=runs[0]/'stk_positions.csv')
        manifest['native_files']={key:str(value) for key,value in ref.items() if isinstance(value,Path)}
        python('orbit_comparison','compare_stk.py','--elements',elements,'--states',ref['orbit'],
               '--out',out/'orbit_comparison.json','--rate-model','stk','--tolerance-km',profile['orbit_tolerance_km'])
        orbit=load_json(out/'orbit_comparison.json');checks['orbit']=dict(ok=orbit['orbit_ok'],
            max_error_m=max(row['max_error_km'] for row in orbit['satellites'])*1000,samples=sum(row['samples'] for row in orbit['satellites']))
        from prepare_grazing_checks import prepare
        cases_path=out/'grazing_cases.csv'
        selected=prepare(out/'global_fine.csv',ref['global_csv'],ref['global_raw'],cases_path,profile['comparison_tolerance_s'])
        native_points=pd.read_csv(ref['global_csv'])
        if selected['cases']:
            refined=[]
            for tag,step in zip(('coarse','fine'),profile['grazing_steps_s']):
                directory=out/('grazing_'+tag)
                native('native_grazing_'+tag,'refine_stk_points.ps1','-Package',package,'-Cases',cases_path,'-Out',directory,'-Step',step)
                refined.append(read_refinement(directory,cases_path,sha(eop),sha(package/'build_scenario.txt')))
            cases,windows,_=refined[1]
            checks['native_grazing_convergence']=windows_comparison(refined[0][1],windows,keys=('case_id','sat_id'),tolerance_s=.001)
            lookup=cases[['point_id_py','point_id_stk']].drop_duplicates()
            pw=pd.read_csv(out/'global_fine_intervals.csv').merge(lookup,left_on='point_id',right_on='point_id_py')
            checks['grazing_geometry']=windows_comparison(pw,windows,keys=('point_id_stk','sat_id'),tolerance_s=.001)
            native_points=refined_points(native_points,cases,windows)
        else:
            checks['native_grazing_convergence']=dict(ok=True,not_required=True)
        native_points.to_csv(out/'native_global_refined.csv',index=False)
        checks['global_geometry']=points_comparison(pd.read_csv(out/'global_fine.csv'),native_points,profile['comparison_tolerance_s'])
        checks['region_geometry']=windows_comparison(pd.read_csv(out/'region_fine.csv'),pd.read_csv(ref['region_csv']),
                                                     tolerance_s=profile['comparison_tolerance_s'])
        # Exercise actual generated J2000 SSO inputs at three heights/four RAANs.
        import designs
        from generate import output_table
        from model_convention import using_rate_model
        with using_rate_model('stk'):
            sso=output_table(pd.concat([designs.walker(4,4,1,h) for h in (500.,600.,700.)],ignore_index=True))
        sso.to_csv(out/'sso_designs.csv',index=False)
        native('native_sso','check_stk_sso.ps1','-Elements',out/'sso_designs.csv','-Out',out/'sso_native.json','-Eop',eop)
        sd=load_json(out/'sso_native.json');checks['sso']=dict(ok=sd['ok'],max_error_deg_day=sd['max_error_deg_day'],cases=len(sd['satellites']))
        for name,digest in hashes.items():
            if sha(ROOT/name)!=digest:raise RuntimeError('source changed during verification: '+name)
        if sha(elements)!=manifest['elements_sha256'] or sha(eop)!=profile['eop_sha256'] or sha(region)!=profile['region_sha256'] or sha(profile_path)!=manifest['profile_sha256']:
            raise RuntimeError('input changed during verification')
        result=dict(validation_passed=all(x['ok'] for x in checks.values()),checks=checks,
                    global_coverage=load_json(out/'global_fine.json')['global_coverage'],
                    region_revisit=load_json(out/'region_fine.json')['region_revisit'],
                    grazing_refinement=selected,native_access_rows_after_refinement=int(native_points.n_accesses.sum()),
                    current_candidate_full_coverage=bool(native_points.first_access_s.notna().all()),
                    optimization_repeated=False,scope=profile['scope'],
                    artifacts_sha256={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.suffix in ('.csv','.json','.log','.sca')})
        (out/'verification_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if not result['validation_passed']:raise RuntimeError('engineering checks failed; see verification_summary.json')
        manifest['status']='passed'
        print(json.dumps({k:v for k,v in result.items() if k!='artifacts_sha256'},ensure_ascii=False,indent=2),flush=True)
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));raise
    finally:
        manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
        (out/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
