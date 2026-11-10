param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$ProgId = 'STK11.Application',
    [ValidateRange(0.001,60)][double]$RegionStep = 0.03125,
    [ValidateRange(0.01,60)][double]$GlobalStep = 5.0,
    [switch]$ComputeCoverage = $true,
    [switch]$SkipGlobal,
    [switch]$SkipRegion,
    [switch]$SkipOrbit,
    [string]$ScenarioFile,
    [switch]$Engine,
    [switch]$GlobalAdaptive = $true,
    [ValidateRange(1,360)][double]$GlobalMaxStep = 30,
    [ValidateRange(1,16)][int]$ParallelCores = [Math]::Min(8,[Environment]::ProcessorCount),
    [ValidateSet('GlobalReachable','GlobalAll')][string[]]$GlobalDefinitions = @('GlobalReachable'),
    [switch]$Show
)
$ErrorActionPreference = 'Stop'
$packagePath = (Resolve-Path -LiteralPath $Package).Path
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $packagePath 'manifest.json') | ConvertFrom-Json
if (-not $manifest.eop_file) { throw 'A frozen EOP file is required. Re-export the package with stk_export.py.' }
$resultPath = Join-Path $packagePath ('stk_run_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $resultPath -ErrorAction Stop | Out-Null
$runtimePath = Join-Path ([IO.Path]::GetTempPath()) ('task2_stk_' + [guid]::NewGuid().ToString('N'))
if ($runtimePath -match '[^\x00-\x7F]') { throw 'STK 11 Connect requires an ASCII staging directory.' }
New-Item -ItemType Directory -Path $runtimePath -ErrorAction Stop | Out-Null
# STK 11 Connect's file reader cannot open this workspace's Chinese path.
foreach ($pointName in @('GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt')) {
    Copy-Item -LiteralPath (Join-Path $packagePath $pointName) -Destination (Join-Path $runtimePath $pointName)
}
if ($manifest.eop_file) {
    if ([IO.Path]::GetFileName($manifest.eop_file) -ne $manifest.eop_file) { throw 'EOP package name must be a plain filename.' }
    Copy-Item -LiteralPath (Join-Path $packagePath $manifest.eop_file) -Destination $runtimePath
}
$status = [ordered]@{ status='running'; prog_id=$ProgId; coverage_computed=$false; region_step_s=$RegionStep; global_step_s=$GlobalStep; global_definitions=$GlobalDefinitions; skip_global=[bool]$SkipGlobal; skip_region=[bool]$SkipRegion; stk_verified=$false }
$status.runtime_ascii_path = $runtimePath
$status.orbit_exported = -not [bool]$SkipOrbit
$status.loaded_scenario = $ScenarioFile
$status.engine = [bool]$Engine
$status.global_sampling = if($GlobalAdaptive) {'adaptive'} else {'fixed'}
$status.global_max_step_s = $GlobalMaxStep
$status.parallel_cores = $ParallelCores
$packageFiles = @('manifest.json','build_scenario.txt','build_coverage.txt','GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt')
if ($manifest.eop_file) { $packageFiles += $manifest.eop_file; $status.eop_file = $manifest.eop_file }
$packageHashes = [ordered]@{}
foreach ($relativePath in $packageFiles) {
    $packageHashes[$relativePath] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $packagePath $relativePath)).Hash.ToLowerInvariant()
}
$packageHashes | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $resultPath 'package_evidence.json')
$app = $null
try {
    # A fresh instance leaves the user's existing scenario untouched.
    if ($Engine) {
        if ($Show) { throw 'Engine mode does not display graphics.' }
        $app = New-Object -ComObject STKX11.Application
        $app.NoGraphics = $true
        $root = New-Object -ComObject AgStkObjects11.AgStkObjectRoot
    } else {
        $app = New-Object -ComObject $ProgId
        $app.Visible = [bool]$Show
        $root = $app.Personality2
    }
    Write-Output 'STK started; building scene.'
    if ($null -ne $root.CurrentScenario) { throw 'A scenario is already open in the new instance. Refusing to replace it.' }
    if ($ScenarioFile) {
        $sourceScenario = (Resolve-Path -LiteralPath $ScenarioFile).Path
        if ($sourceScenario -match '[^\x00-\x7F]') { throw 'Loaded STK scene must have an ASCII path.' }
        $root.LoadScenario($sourceScenario)
        if ($root.CurrentScenario.InstanceName -ne 'Task2_Constellation') { throw 'Unexpected verification scenario.' }
    } else {
    foreach ($file in @('build_scenario.txt','build_coverage.txt')) {
        foreach ($line in Get-Content -Encoding UTF8 -LiteralPath (Join-Path $packagePath $file)) {
            if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) { continue }
            $command = $line.Replace('@PACKAGE@', $runtimePath.Replace('\','/'))
            Add-Content -Encoding UTF8 -LiteralPath (Join-Path $resultPath 'commands.log') -Value $command
            try { $null = $root.ExecuteCommand($command) }
            catch { throw "STK command failed: $command -- $($_.Exception.Message)" }
        }
    }
    }
    $root.UnitPreferences.Item('DateFormat').SetCurrentUnit('EpSec')
    $root.UnitPreferences.Item('Distance').SetCurrentUnit('km')
    $root.UnitPreferences.Item('Time').SetCurrentUnit('sec')
    Write-Output 'Scene built; exporting independent orbit samples.'
    if (-not $SkipOrbit) {
    $orbitPath = Join-Path $resultPath 'stk_positions.csv'
    $writer = [System.IO.StreamWriter]::new($orbitPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine('sat_id,t_s,x_km,y_km,z_km')
        foreach ($id in $manifest.satellite_ids) {
            $name = 'SAT_{0:D3}' -f [int]$id
            $sat = $root.GetObjectFromPath('Satellite/' + $name)
            $provider = $sat.DataProviders.Item('Cartesian Position').Group.Item('J2000')
            $data = $provider.ExecElements(0, [double]$manifest.duration_s, 60.0, @('Time','x','y','z'))
            $t = $data.DataSets.GetDataSetByName('Time').GetValues()
            $x = $data.DataSets.GetDataSetByName('x').GetValues()
            $y = $data.DataSets.GetDataSetByName('y').GetValues()
            $z = $data.DataSets.GetDataSetByName('z').GetValues()
            for ($i=0; $i -lt $t.Length; $i++) {
                $row = @($id,$t[$i],$x[$i],$y[$i],$z[$i]) | ForEach-Object { ([double]$_).ToString('R',[cultureinfo]::InvariantCulture) }
                $writer.WriteLine(($row -join ','))
            }
        }
    } finally { $writer.Dispose() }
    }
    Write-Output 'Orbit stage finished; configuring coverage.'
    # Regional grid coverage is a legacy diagnostic only (QA E41).
    # Whole-region revisit uses continuous Sensor -> AreaTarget accesses below.
    foreach ($name in @('GlobalAll','GlobalReachable')) {
        Write-Output ("Configure $name")
        $cov = $root.GetObjectFromPath('CoverageDefinition/' + $name)
        $cov.Advanced.AutoRecompute = $false
        $cov.Advanced.Sampling.SetType(1) # eSamplingMethodFixedStep (STK enum)
        $cov.Advanced.Sampling.Strategy.FixedTimeStep = $GlobalStep
        $cov.Advanced.Sampling.Strategy.TimeBound = 0.0 # Sample alignment, not event tolerance.
        $null = $root.ExecuteCommand("Cov */CoverageDefinition/$name Access AdvComputeOptions EventsBasedOnSamples Off TimeConvergence 0.01 UseLightTimeDelay Off")
        if ($GlobalAdaptive) {
            $null = $root.ExecuteCommand("Cov */CoverageDefinition/$name Access AdvComputeOptions MinStepSize 0.001 MaxStepSize $GlobalMaxStep")
        }
        Write-Output ("Configured $name")
        if ($ComputeCoverage -and -not $SkipGlobal -and $name -in $GlobalDefinitions) {
            Write-Output ("Computing global coverage: $name")
            $computeTimer = [Diagnostics.Stopwatch]::StartNew()
            if ($ParallelCores -gt 1) {
                $sharedPath=Join-Path $runtimePath 'parallel'
                New-Item -ItemType Directory -Path $sharedPath -Force | Out-Null
                $null=$root.ExecuteCommand('Parallel / Configuration ParallelType Local NumberOfLocalCores ' + $ParallelCores + ' LocalSharedDirectory "' + $sharedPath.Replace('\','/') + '" LocalScenarioCopyStrategy SaveAsVDF')
                $null=$root.ExecuteCommand('Parallel / ShutdownLocalWorkersOnJobCompletion On')
                $null=$root.ExecuteCommand("Cov */CoverageDefinition/$name Access ParallelCompute")
            } else { $cov.ComputeAccesses() }
            $status.global_compute_seconds = $computeTimer.Elapsed.TotalSeconds
            $cov.ExportAccessesAsText((Join-Path $runtimePath ($name + '_accesses.txt')))
            Copy-Item -LiteralPath (Join-Path $runtimePath ($name + '_accesses.txt')) -Destination $resultPath
            Write-Output ("Global coverage exported: $name")
        }
    }
    if ($ComputeCoverage -and -not $SkipRegion) {
        $regionStatus = [System.Collections.Generic.List[object]]::new()
        # Keep COM access/settings wrappers alive through native scene saving.
        # STK 11.6 can retain their sampling storage by reference.
        $accessHandles = [System.Collections.Generic.List[object]]::new()
        $advancedHandles = [System.Collections.Generic.List[object]]::new()
        $regionWriter = [System.IO.StreamWriter]::new((Join-Path $resultPath 'region_access_raw.csv'), $false, [System.Text.UTF8Encoding]::new($false))
        try {
            $regionWriter.WriteLine('sat_id,component_id,start_s,stop_s')
            $regionProcessed=0
            foreach ($id in $manifest.satellite_ids) {
                $regionProcessed++
                Write-Output ("Computing region access: satellite $id (" + $regionProcessed + ' / ' + $manifest.satellite_ids.Count + ')')
                $sensor = $root.GetObjectFromPath(('Satellite/SAT_{0:D3}/Sensor/Cam' -f [int]$id))
                foreach ($component in $manifest.region_area_targets) {
                    $area = $root.GetObjectFromPath('AreaTarget/' + $component)
                    # STK 11.6 COM Advanced readback alone does not prove that
                    # ComputeAccess used the settings. Connect applies the options
                    # to the calculation itself; also verify the saved native .sca.
                    $sensorPath = '*/Satellite/SAT_{0:D3}/Sensor/Cam' -f [int]$id
                    $accessCommand = "Access $sensorPath */AreaTarget/$component Mode Transpond TimeConvergence 0.01 EventsBasedOnSamples Off FixedSampleStep $RegionStep FixedStepTimeBound 0.001"
                    Add-Content -Encoding UTF8 -LiteralPath (Join-Path $resultPath 'commands.log') -Value $accessCommand
                    $null = $root.ExecuteCommand($accessCommand)
                    $access = $sensor.GetAccessToObject($area)
                    $advanced = $access.Advanced
                    $accessHandles.Add($access)
                    $advancedHandles.Add($advanced)
                    if (-not $access.Advanced.UseFixedTimeStep -or [Math]::Abs($access.Advanced.FixedStepSize-$RegionStep) -gt 1e-9) {
                        throw 'STK did not retain the requested regional fixed sampling settings.'
                    }
                    $count = $access.ComputedAccessIntervalTimes.Count
                    if ($count -gt 0) {
                        $data = $access.DataProviders.Item('Access Data').Exec(0, [double]$manifest.duration_s)
                        $starts = $data.DataSets.GetDataSetByName('Start Time').GetValues()
                        $stops = $data.DataSets.GetDataSetByName('Stop Time').GetValues()
                        for ($i=0; $i -lt $starts.Length; $i++) {
                            $a = ([double]$starts[$i]).ToString('R',[cultureinfo]::InvariantCulture)
                            $b = ([double]$stops[$i]).ToString('R',[cultureinfo]::InvariantCulture)
                            $regionWriter.WriteLine("$id,$component,$a,$b")
                        }
                    }
                    $regionStatus.Add([ordered]@{sat_id=$id; component_id=$component; intervals=$count; computed=$true; fixed_step_enabled=$access.Advanced.UseFixedTimeStep; actual_step_s=$access.Advanced.FixedStepSize; time_convergence_s=$access.Advanced.TimeConvergence})
                }
            }
        } finally { $regionWriter.Dispose() }
        ConvertTo-Json -InputObject @($regionStatus.ToArray()) -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $resultPath 'region_access_status.json')
    }
    foreach ($relativePath in $packageFiles) {
        $afterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $packagePath $relativePath)).Hash.ToLowerInvariant()
        if ($afterHash -ne $packageHashes[$relativePath]) { throw "Scene package changed during execution: $relativePath" }
    }
    Write-Output 'Saving STK scene.'
    $null = $root.ExecuteCommand('Save / * "' + $runtimePath.Replace('\','/') + '"')
    Write-Output 'STK scene saved; copying artifacts.'
    Get-ChildItem -LiteralPath $runtimePath -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $resultPath }
    if ($ComputeCoverage -and -not $SkipRegion) {
        $nativeAccess = Get-Content -Raw -LiteralPath (Join-Path $resultPath 'Task2_Constellation.sca')
        $savedSteps = [regex]::Matches($nativeAccess,'(?m)^\s*FixedStepSampling\s+(\S+)')
        if ($savedSteps.Count -ne ($manifest.satellite_ids.Count * $manifest.region_area_targets.Count)) { throw 'Native .sca does not preserve all regional fixed sampling settings.' }
        foreach($savedStep in $savedSteps) {
            if ([Math]::Abs([double]$savedStep.Groups[1].Value-$RegionStep) -gt 1e-9) { throw 'Native regional sample step differs.' }
        }
        $status.region_native_sampling_verified = $true
    }
    $status.status = 'completed'
    $status.coverage_computed = [bool]$ComputeCoverage
    $status.note = 'Execution is not validation: compare orbit CSV and review coverage surface/frame/interval conventions.'
} catch {
    $status.status = 'failed'
    $status.error = $_.Exception.Message
    throw
} finally {
    $status | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $resultPath 'run_status.json')
    if ($null -ne $app -and -not $Show) {
        if ($Engine) {
            if ($root.CurrentScenario) { $root.CloseScenario() }
            # Required final Engine call; otherwise STK 11.6 can return 1 at teardown.
            $app.Terminate()
        }
        else { $app.Quit() }
    }
}
Write-Output $resultPath
