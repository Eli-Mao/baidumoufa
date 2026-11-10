$ErrorActionPreference='Stop'
$app=New-Object -ComObject STKX11.Application
$app.NoGraphics=$true
$root=New-Object -ComObject AgStkObjects11.AgStkObjectRoot
try{
    $staging=Join-Path $env:TEMP ('task2_sso_'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging | Out-Null
    Copy-Item -LiteralPath 'data/earth_orientation/EOP-20261105.txt' -Destination $staging
    $eop=Join-Path $staging 'EOP-20261105.txt'
    foreach($cmd in @('Units_SetConnect / Distance Kilometer Time Second Date GregorianUTC','New / Scenario SSO_Check',('EarthData * EOPFile "'+$eop.Replace('\','/')+'"'),'SetAnalysisTimePeriod * "1 Jan 2027 00:00:00.000" "8 Jan 2027 00:00:00.000"','SetEpoch * "1 Jan 2027 00:00:00.000"','New / */Satellite SSO','SetState */Satellite/SSO Classical J2Perturbation "1 Jan 2027 00:00:00.000" "8 Jan 2027 00:00:00.000" 60 J2000 "1 Jan 2027 00:00:00.000" 7071 0 98.16402649374777 0 0 0')){
        $null=$root.ExecuteCommand($cmd)
    }
    $root.UnitPreferences.Item('DateFormat').SetCurrentUnit('EpSec')
    $sat=$root.GetObjectFromPath('Satellite/SSO')
    $data=$sat.DataProviders.Item('Classical Elements').Group.Item('J2000').ExecElements(0,604800,86400,@('Time','RAAN'))
    $times=$data.DataSets.GetDataSetByName('Time').GetValues()
    $angles=$data.DataSets.GetDataSetByName('RAAN').GetValues()
    $rate=(([double]$angles[-1]-[double]$angles[0]+360)%360)/7
    $target=360/365.2422
    $result=[ordered]@{inclination_deg=98.16402649374777;height_km=700;epoch='2027-01-01';frame='J2000';days=7;times_s=$times;raan_deg=$angles;measured_node_rate_deg_day=$rate;target_deg_day=$target;difference_deg_day=[Math]::Abs($rate-$target);tolerance_deg_day=0.000001;ok=([Math]::Abs($rate-$target)-lt 0.000001)}
    $result | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath 'out/stk_validation_eop2026/sso_native_check.json'
    $result | ConvertTo-Json -Depth 6
    if(-not $result.ok){throw 'Native SSO rate differs from target.'}
}finally{
    if($root.CurrentScenario){$root.CloseScenario()}
    $app.Terminate()
}
