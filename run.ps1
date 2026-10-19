# 一键运行。用法：
#   .\run.ps1                    # 全链路
#   .\run.ps1 -Stage meta        # 只解析原始数据（契约层自检）
#   .\run.ps1 -WithReport        # 全链路 + 出图
#   .\run.ps1 -Test              # 跑测试
param(
    [ValidateSet('all', 'meta', 'windows', 'plan')][string]$Stage = 'all',
    [switch]$Force,
    [switch]$WithReport,
    [switch]$Test
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONPATH = Join-Path $root 'src'

if ($Test) {
    & py -3 -X utf8 (Join-Path $root 'tests\run_tests.py')
    exit $LASTEXITCODE
}

$extra = @()
if ($Force) { $extra += '--force' }
if ($WithReport) { $extra += '--with-report' }

& py -3 -X utf8 -m satplan.pipeline --stage $Stage @extra
exit $LASTEXITCODE
