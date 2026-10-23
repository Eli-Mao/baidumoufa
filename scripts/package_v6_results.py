"""Local-only commit, full portable bundle and evidence ZIP; no remote writes."""
import sys,json,hashlib,subprocess,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT.parents[1];OUT=HERE/'outputs/v6_results'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def git(*args):return subprocess.check_output(['git','-c','core.quotepath=false','-C',str(ROOT),*args],encoding='utf-8',stderr=subprocess.STDOUT).strip()
def save(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8')
def main():
    assert 'OK' in (OUT/'test_results.txt').read_text(encoding='utf-8')
    r=json.loads((OUT/'comparison_report.json').read_text(encoding='utf-8'));assert r['formal_trials']==18 and r['all_formal_accepted']
    assert git('branch','--show-current')=='codex/v6-deep-optimization'
    frozen=['src/satplan/config.py','src/satplan/rules.py','src/satplan/v5.py','src/satplan/v5_physics.py','scripts/audit_plan_physics.py','scripts/repair_plan_physics.py','scripts/v4_budget_reference.py']
    assert not git('diff','0337bb2593ea89c05b6778fcc592194279067816','--',*frozen),'Frozen V4/V5 files modified'
    include=['.gitignore','src/satplan/v6.py','tests/test_v6.py','PROJECT_STATUS.md','docs/V6_HANDOFF.md','docs/V4_V5_V6比较报告.md',*[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'scripts').glob('*v6*.py')], 'scripts/RenderV6Charts.cs','scripts/analyze_v5_opportunities.py','scripts/summarize_v5_resources.py','scripts/refine_v5_opportunities.py']
    include=list(dict.fromkeys(include));git('add','--',*include)
    staged=git('diff','--cached','--name-only').splitlines()
    assert staged and all(n in include for n in staged)
    assert not any(n.startswith(('data/','de421','.env')) for n in staged)
    message=OUT/'commit_message.txt';message.write_text('feat: add validated V6 adaptive neighborhood refinement\n\nPreserve frozen V4/V5; compare 18 equal-budget seeded trials from the same V5 start.\nAdd independent exact-interval acceptance, concrete resource analysis and reproducible handoff.\n',encoding='utf-8')
    git('-c','user.name=Iceswing','-c','user.email=755875603@qq.com','commit','-F',str(message))
    head=git('rev-parse','HEAD');assert not git('status','--porcelain','--untracked-files=no')
    remotes=git('remote').splitlines()
    if 'team' not in remotes:git('remote','add','team','https://github.com/Eli-Mao/baidumoufa.git')
    bundle=OUT/'v6_complete.bundle';git('bundle','create',str(bundle),'--all')
    verify=git('bundle','verify',str(bundle))
    restore=HERE/'work'/('v6_restore_'+head[:10])
    subprocess.run(['git','clone','--branch','codex/v6-deep-optimization',str(bundle),str(restore)],check=True)
    restored=subprocess.check_output(['git','-C',str(restore),'rev-parse','HEAD'],text=True).strip();assert restored==head
    fsck=subprocess.run(['git','-C',str(restore),'fsck','--full'],capture_output=True,text=True,check=True)
    save(OUT/'bundle_restore.json',{'commit':head,'branch':'codex/v6-deep-optimization','bundle':bundle.name,'sha256':sha(bundle),'verify':verify,'independent_clone_head':restored,'fsck':fsck.stdout+fsck.stderr,'full_bundle_no_external_prerequisites':True,'pushed':False,'frozen_files_unchanged':frozen})
    git('format-patch','0337bb2593ea89c05b6778fcc592194279067816..HEAD','-o',str(OUT))
    snapshot=OUT/'code_snapshot';snapshot.mkdir(exist_ok=True)
    for name in git('ls-files').splitlines():
        p=ROOT/name
        if p.is_file() and (name.startswith(('src/','scripts/','tests/','docs/')) or name in ['.gitignore','requirements.txt','PROJECT_STATUS.md']):
            dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    # V5 seal is checked again before declaring the enhanced package complete.
    seal=json.loads((HERE/'outputs/v5_sealed/seal.json').read_text(encoding='utf-8'))
    for n,d in seal['copied_sha256'].items():assert sha(HERE/'outputs/v5_sealed'/n)==d
    manifest={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in ['artifact_manifest.json','SHA256SUMS.txt','v6_results.zip','zip_receipt.json']}
    save(OUT/'artifact_manifest.json',manifest)
    (OUT/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(manifest.items())),encoding='utf-8')
    archive=OUT/'v6_results.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.rglob('*'):
            if p.is_file() and p.name not in ['v6_results.zip','zip_receipt.json']:z.write(p,'results/'+str(p.relative_to(OUT)).replace('\\','/'))
        for p in (ROOT/'data/out/v6_comparison').rglob('*'):
            if p.is_file() and p.name!='comparison.lock':z.write(p,'experiments/'+str(p.relative_to(ROOT/'data/out/v6_comparison')).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    save(OUT/'zip_receipt.json',{'file':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive),'crc_pass':True,'contents':'Source and reports, all trials including pilot and excluded startup evidence; no raw TLE/ephemeris/window cache, environment or credentials'})
    print(json.dumps({'commit':head,'bundle_restored':True,'zip_crc_pass':True,'bytes':archive.stat().st_size,'staged_files':staged},ensure_ascii=False))
if __name__=='__main__':main()
