$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { throw 'Run scripts/setup_windows.ps1 first.' }
& $venvPython -m nadlan_balagan check
if ($LASTEXITCODE -ne 0) { throw 'Environment sanity check failed.' }
& $venvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Unit sanity tests failed.' }
Write-Host 'Windows sanity checks passed.'
