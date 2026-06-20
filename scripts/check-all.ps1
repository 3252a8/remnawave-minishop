# Run from repository root: .\scripts\check-all.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Python: pip install runtime and dev requirements" -ForegroundColor Cyan
python -m pip install -q -r backend/requirements.txt -r requirements-dev.txt

if (-not (Test-Path (Join-Path $root "frontend/node_modules"))) {
  Write-Host "npm install --prefix frontend" -ForegroundColor Cyan
  npm --prefix frontend install
}

Write-Host "npm run check" -ForegroundColor Cyan
npm run check
