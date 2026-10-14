# Run from repository root: .\scripts\check-all.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

node scripts/check_all.mjs @args
exit $LASTEXITCODE
