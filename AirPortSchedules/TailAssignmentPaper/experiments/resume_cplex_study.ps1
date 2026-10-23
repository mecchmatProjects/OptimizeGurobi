param(
    [string]$Executable = 'F:\LT\IJOC_SDDP_for_Multi-Echelon_Lot-Sizing_with_Component_Substitution\cplex\CPLEX_Studio\cplex\bin\x64_win64\cplex.exe',
    [ValidateSet('core', 'extended', 'all')]
    [string]$Stage = 'all',
    [string]$Tag = '20261023'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$driver = Join-Path $PSScriptRoot 'refresh_cplex_study.py'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python not found: $python"
}
& $python -u $driver --executable $Executable --stage $Stage --tag $Tag
exit $LASTEXITCODE
