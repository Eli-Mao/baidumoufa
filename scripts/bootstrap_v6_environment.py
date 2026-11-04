"""Populate a fresh venv with the hashed offline Windows CPython 3.12 packages.

This copies distribution files, including metadata/licenses; it is not a wheel
build or a claim that an online pip installation was validated.
"""
import argparse,hashlib,json,platform,sys,sysconfig,zipfile
from pathlib import Path,PurePosixPath
def main():
    a=argparse.ArgumentParser();a.add_argument('--archive',type=Path,required=True);a.add_argument('--manifest',type=Path,required=True);a.add_argument('--receipt',type=Path,required=True);args=a.parse_args()
    if sys.prefix==sys.base_prefix:raise RuntimeError('Run inside a newly created venv; global environment installation is forbidden')
    if sys.version_info[:2]!=(3,12) or sys.platform!='win32' or platform.architecture()[0]!='64bit':raise RuntimeError('Offline package ABI requires Windows x64 CPython 3.12')
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    assert hashlib.sha256(args.archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    site=Path(sysconfig.get_path('purelib')).resolve();assert site.is_relative_to(Path(sys.prefix).resolve())
    with zipfile.ZipFile(args.archive) as z:
        assert set(z.namelist())==set(manifest['files_sha256'])
        # Verify all members and destinations before writing any dependency.
        for name,digest in manifest['files_sha256'].items():
            rel=PurePosixPath(name)
            assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
            dest=(site/name).resolve();assert dest.is_relative_to(site)
            data=z.read(name);assert hashlib.sha256(data).hexdigest()==digest
            if dest.exists():assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest,'Use a clean venv; refusing to replace a different installed file'
        for name in z.namelist():
            dest=site/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
    receipt={'status':'offline_packages_installed','python':sys.version,'executable':sys.executable,'isolated_site_packages':str(site),'versions':manifest['versions'],'archive_sha256':manifest['archive_sha256'],'files':len(manifest['files_sha256']),'method':'hashed distribution file copy, not pip wheel install'}
    args.receipt.parent.mkdir(parents=True,exist_ok=True);args.receipt.write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt))
if __name__=='__main__':main()
