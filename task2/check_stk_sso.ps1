param([Parameter(Mandatory=$true)][string]$Elements,
      [Parameter(Mandatory=$true)][string]$Out,
      [string]$Eop='data/earth_orientation/EOP-20261105.txt')
$ErrorActionPreference='Stop'
[Threading.Thread]::CurrentThread.CurrentCulture=[cultureinfo]::InvariantCulture
$inputPath=(Resolve-Path -LiteralPath $Elements).Path
$data=Import-Csv -LiteralPath $inputPath
$runtime=Join-Path ([IO.Path]::GetTempPath()) ('task2_sso_'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $runtime
Copy-Item -LiteralPath $Eop -Destination (Join-Path $runtime 'EOP.txt')
$app=New-Object -ComObject STKX11.Application;$app.NoGraphics=$true
$root=New-Object -ComObject AgStkObjects11.AgStkObjectRoot
$results=New-Object 'Collections.Generic.List[object]'
try {
    foreach($cmd in @('Units_SetConnect / Distance Kilometer Time Second Date GregorianUTC','New / Scenario SSO_Check',('EarthData * EOPFile "'+$runtime.Replace('\','/')+'/EOP.txt"'),'SetAnalysisTimePeriod * "1 Jan 2027 00:00:00.000" "8 Jan 2027 00:00:00.000"','SetEpoch * "1 Jan 2027 00:00:00.000"')){$null=$root.ExecuteCommand($cmd)}
    $root.UnitPreferences.Item('DateFormat').SetCurrentUnit('EpSec')
    foreach($el in $data) {
        $name='SSO_'+$el.sat_id
        $null=$root.ExecuteCommand("New / */Satellite $name")
        $cmd="SetState */Satellite/$name Classical J2Perturbation `"1 Jan 2027 00:00:00.000`" `"8 Jan 2027 00:00:00.000`" 60 J2000 `"1 Jan 2027 00:00:00.000`" $($el.a_km) 0 $($el.inc_deg) 0 $($el.raan_deg) $($el.u_deg)"
        $null=$root.ExecuteCommand($cmd)
        $sat=$root.GetObjectFromPath('Satellite/'+$name)
        $provider=$sat.DataProviders.Item('Classical Elements').Group.Item('ICRF')
        $d=$provider.ExecElements(0,604800,86400,@('Time','RAAN'))
        $angles=@($d.DataSets.GetDataSetByName('RAAN').GetValues())
        $rate=(([double]$angles[-1]-[double]$angles[0]+360)%360)/7
        $results.Add([pscustomobject]@{sat_id=[int]$el.sat_id;height_km=[double]$el.h_km;inclination_j2000_deg=[double]$el.inc_deg;raan_j2000_deg=[double]$el.raan_deg;raan_icrf_deg=$angles;measured_node_rate_deg_day=$rate;error_deg_day=[math]::Abs($rate-360/365.2422)})
    }
    $max=($results | Measure-Object error_deg_day -Maximum).Maximum
    $report=[ordered]@{stk_version=$root.Version;input_sha256=(Get-FileHash $inputPath).Hash;eop_sha256=(Get-FileHash (Join-Path $runtime 'EOP.txt')).Hash;input_frame='J2000';propagation_frame='ICRF';days=7;target_deg_day=360/365.2422;tolerance_deg_day=.000001;max_error_deg_day=$max;ok=($max-lt .000001);satellites=$results.ToArray()}
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $Out
    Write-Output ("Checked $($results.Count) SSO designs, max rate error $max deg/day.")
    if(-not $report.ok){throw 'SSO engineering tolerance exceeded'}
} finally {$root.CloseScenario();$app.Terminate()}
