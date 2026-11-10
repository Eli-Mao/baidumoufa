param(
    [Parameter(Mandatory=$true)][string]$Run,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference='Stop'
$runPath=(Resolve-Path -LiteralPath $Run).Path
$status=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $runPath 'run_status.json') | ConvertFrom-Json
if($status.status -eq 'failed'){throw 'Cannot package a failed STK run.'}
$source=Join-Path $runPath 'Task2_Constellation.sc'
if(-not (Test-Path -LiteralPath $source)){throw 'Saved native scene is missing; rebuild using run_stk.ps1.'}
$outputPath=[IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$staging=Join-Path $env:TEMP ('task2_scene_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
$sceneDirectory=Join-Path $staging 'Task2_Constellation_STK116'
New-Item -ItemType Directory -Path $sceneDirectory | Out-Null
# The standard native scene format also works with the no-graphics Engine.
# SaveVDFAs can create a graphics-only VDF with no analytical child objects.
Get-ChildItem -LiteralPath $runPath -File | Where-Object {$_.Name -notin @('run_status.json','package_evidence.json','commands.log','stk_positions.csv')} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $sceneDirectory
}
Get-ChildItem -LiteralPath $sceneDirectory -Filter '*.cv' -File | ForEach-Object {
    $content=Get-Content -Raw -LiteralPath $_.FullName
    $content=[regex]::Replace($content,'(?m)^(\s*CustomPointFile\s+).*/([^/\r\n]+\.pnt)\s*$', '$1$2')
    [IO.File]::WriteAllText($_.FullName,$content,[Text.Encoding]::ASCII)
}
$scPath=Join-Path $sceneDirectory 'Task2_Constellation.sc'
$scContent=Get-Content -Raw -LiteralPath $scPath
if($status.eop_file){
    if(-not(Test-Path -LiteralPath (Join-Path $sceneDirectory $status.eop_file))){throw 'Frozen EOP data missing from scene.'}
    $scContent=[regex]::Replace($scContent,'(?m)^(\s*EOPFilename\s+).*$',('$1'+$status.eop_file))
    [IO.File]::WriteAllText($scPath,$scContent,[Text.Encoding]::ASCII)
}
$app=New-Object -ComObject STKX11.Application
$app.NoGraphics=$true
$root=New-Object -ComObject AgStkObjects11.AgStkObjectRoot
try {
    Write-Output 'Reopening portable native scene with relative point files.'
    $root.LoadScenario((Join-Path $sceneDirectory 'Task2_Constellation.sc'))
    Write-Output ('Reopened objects: '+$root.CurrentScenario.Children.Count)
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while($root.CurrentScenario.Children.Count -ne 34 -and $timer.Elapsed.TotalSeconds -lt 30){Start-Sleep -Milliseconds 250}
    if($root.CurrentScenario.Children.Count -ne 34){throw ('Reopened scene has '+$root.CurrentScenario.Children.Count+' objects.')}
    $eopHash=$null
    if($status.eop_file){
        $null=$root.ExecuteCommand('EarthData * EOPFile Reload')
        $eopHash=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $sceneDirectory $status.eop_file)).Hash.ToLowerInvariant()
    }
    $satellites=0
    for($id=1;$id -le 28;$id++){
        $sat=$root.GetObjectFromPath(('Satellite/SAT_{0:D3}' -f $id))
        $sensor=$root.GetObjectFromPath(('Satellite/SAT_{0:D3}/Sensor/Cam' -f $id))
        if($sat.Children.Count -ne 1 -or $sensor.ClassName -ne 'Sensor'){throw 'Missing sensor in portable scene.'}
        $satellites++
    }
    $counts=[ordered]@{}
    foreach($name in @('GlobalAll','GlobalReachable','YRD_GridDiagnostic')){
        $cov=$root.GetObjectFromPath('CoverageDefinition/'+$name)
        Write-Output ('Checking point table: '+$name)
        $data=$cov.DataProviders.Item('Grid Point Locations').ExecElements(@('Latitude'))
        $counts[$name]=$data.DataSets.GetDataSetByName('Latitude').GetValues().Count
        Write-Output ($name+': '+$counts[$name])
    }
    if($counts.GlobalAll -ne 64800 -or $counts.GlobalReachable -ne 59040 -or $counts.YRD_GridDiagnostic -ne 3270){throw 'Point grids did not survive portable scene reopening.'}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=Join-Path $outputPath 'Task2_Constellation_STK116.zip'
    if(Test-Path -LiteralPath $zip){throw 'Scene archive already exists; choose a new output directory.'}
    [IO.Compression.ZipFile]::CreateFromDirectory($sceneDirectory,$zip)
    [ordered]@{ok=$true;source_run=$runPath;native_reopen_verified=$true;satellites=$satellites;sensors=$satellites;area_targets=3;coverage_definitions=3;grid_counts=$counts;eop_file=$status.eop_file;eop_sha256=$eopHash;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant();open_instructions='Extract all files to an ASCII path and open Task2_Constellation.sc in STK 11.6.'} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $outputPath 'scene_validation.json')
    Write-Output $zip
} finally {
    if($root.CurrentScenario){$root.CloseScenario()}
    $app.Terminate()
}
