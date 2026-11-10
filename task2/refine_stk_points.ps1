param([Parameter(Mandatory=$true)][string]$Cases,
      [string]$Package='out/stk_validation_eop2026/stk',
      [string]$Out='out/model_alignment/native_grazing',
      [ValidateRange(.00001,.01)][double]$Step=.002)
$ErrorActionPreference='Stop'
[Threading.Thread]::CurrentThread.CurrentCulture=[cultureinfo]::InvariantCulture
$packagePath=(Resolve-Path -LiteralPath $Package).Path
$casesPath=(Resolve-Path -LiteralPath $Cases).Path
$outPath=if([IO.Path]::IsPathRooted($Out)){[IO.Path]::GetFullPath($Out)}else{[IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))}
if(Test-Path -LiteralPath $outPath){throw 'Output already exists; keep prior evidence immutable.'}
$null=New-Item -ItemType Directory -Path $outPath
$runtime=Join-Path ([IO.Path]::GetTempPath()) ('task2_grazing_'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $runtime
$manifest=Get-Content -Raw -Encoding UTF8 (Join-Path $packagePath 'manifest.json')|ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $packagePath $manifest.eop_file) -Destination $runtime
Copy-Item -LiteralPath $casesPath -Destination (Join-Path $outPath 'cases.csv')
$status=[ordered]@{status='running';step_s=$Step;time_convergence_s=.00001;cases_sha256=(Get-FileHash $casesPath).Hash;scene_commands_sha256=(Get-FileHash (Join-Path $packagePath 'build_scenario.txt')).Hash;eop_sha256=(Get-FileHash (Join-Path $runtime $manifest.eop_file)).Hash}
$app=New-Object -ComObject STKX11.Application;$app.NoGraphics=$true
$root=New-Object -ComObject AgStkObjects11.AgStkObjectRoot
$handles=New-Object 'Collections.Generic.List[object]'
$rows=New-Object 'Collections.Generic.List[object]'
$counts=New-Object 'Collections.Generic.List[object]'
try {
    foreach($line in Get-Content -Encoding UTF8 (Join-Path $packagePath 'build_scenario.txt')) {
        if($line -and -not $line.StartsWith('#')){$null=$root.ExecuteCommand($line.Replace('@PACKAGE@',$runtime.Replace('\','/')))}
    }
    $root.UnitPreferences.Item('DateFormat').SetCurrentUnit('EpSec')
    $root.UnitPreferences.Item('Distance').SetCurrentUnit('km')
    $root.UnitPreferences.Item('Time').SetCurrentUnit('sec')
    $null=$root.ExecuteCommand('Units_SetConnect / Date EpochSeconds')
    $casesData=Import-Csv -LiteralPath $casesPath
    foreach($case in $casesData) {
        $name='CHECK_'+$case.case_id
        $null=$root.ExecuteCommand("New / */Target $name")
        $null=$root.ExecuteCommand("SetPosition */Target/$name Geodetic $($case.lat_deg) $($case.lon_deg) 0")
        $sensorPath='*/Satellite/SAT_{0:D3}/Sensor/Cam' -f [int]$case.sat_id
        $command="Access $sensorPath */Target/$name TimePeriod `"$($case.start_s)`" `"$($case.stop_s)`" Mode Transpond AberrationType None TimeConvergence 0.00001 EventsBasedOnSamples Off FixedSampleStep $Step FixedStepTimeBound 0.00001"
        Add-Content -Encoding UTF8 -LiteralPath (Join-Path $outPath 'commands.log') -Value $command
        $null=$root.ExecuteCommand($command)
        $sensor=$root.GetObjectFromPath($sensorPath.Substring(2))
        $target=$root.GetObjectFromPath('Target/'+$name)
        $access=$sensor.GetAccessToObject($target);$advanced=$access.Advanced
        $handles.Add($access);$handles.Add($advanced)
        if(-not $advanced.UseFixedTimeStep -or [math]::Abs($advanced.FixedStepSize-$Step)>1e-12){throw 'Native fixed step differs'}
        $count=$access.ComputedAccessIntervalTimes.Count
        if($count -gt 0) {
            $d=$access.DataProviders.Item('Access Data').Exec([double]$case.start_s,[double]$case.stop_s)
            $starts=$d.DataSets.GetDataSetByName('Start Time').GetValues();$stops=$d.DataSets.GetDataSetByName('Stop Time').GetValues()
            for($i=0;$i -lt $starts.Length;$i++){$rows.Add([pscustomobject]@{case_id=$case.case_id;point_id_stk=$case.point_id_stk;sat_id=$case.sat_id;start_s=$starts[$i];stop_s=$stops[$i]})}
        }
        $counts.Add([pscustomobject]@{case_id=$case.case_id;interval_count=$count})
    }
    if($rows.Count){$rows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outPath 'intervals.csv')}
    else{'case_id,point_id_stk,sat_id,start_s,stop_s' | Set-Content -Encoding UTF8 (Join-Path $outPath 'intervals.csv')}
    $counts | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outPath 'counts.csv')
    $null=$root.ExecuteCommand('Save / * "'+$runtime.Replace('\','/')+'"')
    Copy-Item -LiteralPath (Join-Path $runtime 'Task2_Constellation.sca') -Destination $outPath
    $status.status='completed';$status.cases=$counts.Count;$status.intervals=$rows.Count
    Write-Output ("Refined $($counts.Count) encounters; $($rows.Count) native intervals.")
}catch{$status.status='failed';$status.error=$_.Exception.Message;throw}
finally{
    $status | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outPath 'status.json')
    $root.CloseScenario();$app.Terminate()
}
