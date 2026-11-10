param([string]$Package='out/stk_validation_eop2026/stk', [string]$Out='out/model_alignment')
$ErrorActionPreference='Stop'
$packagePath=(Resolve-Path -LiteralPath $Package).Path
$outPath=if([IO.Path]::IsPathRooted($Out)){[IO.Path]::GetFullPath($Out)}else{[IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))}
$null=New-Item -ItemType Directory -Path $outPath -Force
$runtime=Join-Path ([IO.Path]::GetTempPath()) ('task2_frames_'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $runtime
$manifest=Get-Content -Raw -Encoding UTF8 (Join-Path $packagePath 'manifest.json') | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $packagePath $manifest.eop_file) -Destination $runtime
$app=New-Object -ComObject STKX11.Application
$app.NoGraphics=$true
$root=New-Object -ComObject AgStkObjects11.AgStkObjectRoot
try {
    foreach($line in Get-Content -Encoding UTF8 (Join-Path $packagePath 'build_scenario.txt')) {
        if($line -and -not $line.StartsWith('#')) { $null=$root.ExecuteCommand($line.Replace('@PACKAGE@',$runtime.Replace('\','/'))) }
    }
    $root.UnitPreferences.Item('DateFormat').SetCurrentUnit('EpSec')
    $root.UnitPreferences.Item('Distance').SetCurrentUnit('km')
    $root.UnitPreferences.Item('Time').SetCurrentUnit('sec')
    $grav=$root.GetObjectFromPath('Satellite/SAT_001').DataProviders.Item('Gravity Model').Exec()
    $gravity=[ordered]@{}
    foreach($key in @('Name','mu','J2')) {$gravity[$key]=@($grav.DataSets.GetDataSetByName($key).GetValues())[0]}
    $gravity | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outPath 'native_gravity.json')
    $writer=[IO.StreamWriter]::new((Join-Path $outPath 'native_grazing_states.csv'),$false,[Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine('sat_id,t_s,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms')
        foreach($entry in @(@(22,396249,396257),@(25,35112,35121))) {
            $sat=$root.GetObjectFromPath(('Satellite/SAT_{0:D3}' -f $entry[0]))
            $p=$sat.DataProviders.Item('Cartesian Position').Group.Item('Fixed').ExecElements($entry[1],$entry[2],.01,@('Time','x','y','z'))
            $v=$sat.DataProviders.Item('Cartesian Velocity').Group.Item('Fixed').ExecElements($entry[1],$entry[2],.01,@('x','y','z'))
            $t=$p.DataSets.GetDataSetByName('Time').GetValues();$values=@()
            foreach($a in @('x','y','z')) {$values+=,@($p.DataSets.GetDataSetByName($a).GetValues())}
            foreach($a in @('x','y','z')) {$values+=,@($v.DataSets.GetDataSetByName($a).GetValues())}
            for($i=0;$i -lt $t.Length;$i++) {
                $nums=@($entry[0],$t[$i]);foreach($axis in $values){$nums+=$axis[$i]}
                $row=$nums | ForEach-Object {([double]$_).ToString('R',[cultureinfo]::InvariantCulture)}
                $writer.WriteLine(($row -join ','))
            }
        }
    } finally {$writer.Dispose()}
    $writer=[IO.StreamWriter]::new((Join-Path $outPath 'native_states.csv'),$false,[Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine('sat_id,frame,t_s,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms')
        foreach($id in @(1,6,14,28)) {
            $sat=$root.GetObjectFromPath(('Satellite/SAT_{0:D3}' -f $id))
            foreach($frame in @('J2000','ICRF','Fixed')) {
                $p=$sat.DataProviders.Item('Cartesian Position').Group.Item($frame).ExecElements(0,604800,3600,@('Time','x','y','z'))
                $v=$sat.DataProviders.Item('Cartesian Velocity').Group.Item($frame).ExecElements(0,604800,3600,@('x','y','z'))
                $t=$p.DataSets.GetDataSetByName('Time').GetValues()
                $values=@()
                foreach($a in @('x','y','z')) { $values+=,@($p.DataSets.GetDataSetByName($a).GetValues()) }
                foreach($a in @('x','y','z')) { $values+=,@($v.DataSets.GetDataSetByName($a).GetValues()) }
                for($i=0;$i -lt $t.Length;$i++) {
                    $nums=@($t[$i]); foreach($axis in $values) {$nums+=$axis[$i]}
                    $row=$nums | ForEach-Object {([double]$_).ToString('R',[cultureinfo]::InvariantCulture)}
                    $writer.WriteLine((@($id,$frame)+$row -join ','))
                }
            }
        }
    } finally { $writer.Dispose() }
    [ordered]@{stk_version=$root.Version; eop_sha256=(Get-FileHash (Join-Path $runtime $manifest.eop_file)).Hash; source='fresh native J2Perturbation, not imported ephemeris'; satellite_ids=@(1,6,14,28);step_s=3600;duration_s=604800} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outPath 'native_states_provenance.json')
    Write-Output 'Native frame and velocity samples exported.'
} finally {$root.CloseScenario();$app.Terminate()}
