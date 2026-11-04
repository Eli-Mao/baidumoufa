param(
    [string]$Python = 'D:\SatelliteProject\Task4_Phase0_DataCheck\.venv\Scripts\python.exe'
)
$ErrorActionPreference='Stop'
$ProjectRoot=Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python)) { throw 'Supply -Python with the existing Python environment; no dependencies are installed automatically.' }
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$processCheck=@'
import psutil,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();active=[]
for p in psutil.process_iter(['pid','cmdline']):
    try:
        args=p.info['cmdline'] or []
        if any(Path(a).name in {'run_v5_comparison.py','run_v5_trial.py'} for a in args):
            if Path(p.cwd()).resolve()==root or any(str(root).lower() in a.lower() for a in args):active.append(p.pid)
    except (psutil.Error,ValueError):pass
if active:print('A comparison/trial is already running:',active);sys.exit(2)
'@
& $Python -c $processCheck $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'Refusing duplicate experiment processes.' }
$comparison=Join-Path $ProjectRoot 'data/out/v5_comparison'
$verifiedGeometry=$false
if (Test-Path -LiteralPath $comparison) {
    foreach ($file in Get-ChildItem -LiteralPath $comparison -Recurse -Filter trial.json -File) {
        $trial=Get-Content -LiteralPath $file.FullName -Raw|ConvertFrom-Json
        if ($trial.status -ne 'accepted') {continue}
        if (-not $verifiedGeometry) {
            $baseline='D:\SatelliteProject_GitHub\data\out\real_aug2026_10000'
            if ((Get-FileHash -LiteralPath (Join-Path $baseline 'windows.csv') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $trial.windows_sha256) {throw 'Cached windows changed; refusing mixed results.'}
            if ((Get-FileHash -LiteralPath (Join-Path $baseline 'final_plan.csv') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $trial.baseline_plan_sha256) {throw 'Sealed V4 plan changed; refusing mixed results.'}
            $verifiedGeometry=$true
        }
        foreach ($property in $trial.code_sha256.PSObject.Properties) {
            $source=Join-Path $ProjectRoot $property.Name
            if (-not (Test-Path -LiteralPath $source)) {throw "Recorded source missing: $source"}
            if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) {
                throw "Code changed since an accepted trial: $source. Use a fresh experiment directory; do not mix versions."
            }
        }
        foreach ($property in $trial.input_sha256.PSObject.Properties) {
            $input=Join-Path $ProjectRoot $property.Name
            if ((Get-FileHash -LiteralPath $input -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) {throw "Input changed: $input"}
        }
    }
}
Set-Location -LiteralPath $ProjectRoot
& $Python -u (Join-Path $PSScriptRoot 'run_v5_comparison.py')
if ($LASTEXITCODE -ne 0) {throw 'Comparison stopped; inspect the per-trial logs and saved checkpoints.'}
