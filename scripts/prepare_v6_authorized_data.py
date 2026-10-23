"""Verify and copy explicitly supplied authorized data; never fetch or propagate."""
import argparse,json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--release',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--ephemeris',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--test-cache-5000',type=Path);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    identity=json.loads((a.release/'provenance/historical_identity.json').read_text(encoding='utf-8'))
    expected={Path(k).name:v for k,v in identity.items()}
    names=['orbits.tle','stations.txt','priority_high.txt','priority_medium.txt','priority_low.txt']
    sources={a.raw/n:ROOT/'data/raw'/n for n in names};sources[a.ephemeris]=ROOT/'de421.bsp'
    checks={}
    for source,dest in sources.items():
        assert source.is_file(),str(source)
        digest=sha(source);assert digest==expected[source.name],'Wrong data version: '+source.name
        if dest.exists():assert sha(dest)==digest,'Existing different local input preserved: '+str(dest)
        checks[source.name]=digest
    for name in ['windows.csv','selected_targets.csv']:
        assert sha(a.cache/name)==expected[name],'Wrong cached data version: '+name
        checks[name]=expected[name]
    assert (a.cache/'experiment_report.json').is_file(),'Cached V4 experiment_report.json required by frozen runner'
    for source,dest in sources.items():
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(source,dest)
    # Tests use local fixtures, never regenerate orbits. Copy only with matching
    # destination protection; these derived caches remain gitignored.
    fixtures={a.cache/'windows.csv':ROOT/'data/out/real_aug2026_10000/windows.csv',a.cache/'final_plan.csv':ROOT/'data/out/real_aug2026_10000/v4_plan.csv'}
    if a.test_cache_5000:fixtures[a.test_cache_5000/'windows.csv']=ROOT/'data/out/real_aug2026_5000/windows.csv'
    for source,dest in fixtures.items():
        assert source.is_file(),str(source)
        if dest.exists():assert sha(dest)==sha(source),'Existing different fixture preserved: '+str(dest)
        else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    a.receipt.parent.mkdir(parents=True,exist_ok=True)
    r={'status':'authorized_local_data_verified','sha256':checks,'cache':str(a.cache.resolve()),'test_cache_5000_supplied':a.test_cache_5000 is not None,'network_download':False,'full_orbit_propagation':False}
    a.receipt.write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
