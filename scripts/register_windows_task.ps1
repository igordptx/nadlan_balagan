$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { throw 'Run scripts/setup_windows.ps1 first.' }
$action = New-ScheduledTaskAction -Execute $venvPython -Argument '-m nadlan_balagan serve' -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName 'NadlanBalagan' -Action $action -Trigger $trigger -Settings $settings -Description 'Local dashboard and 08:00 UTC real-estate searches' -Force | Out-Null
Write-Host 'Task registered to start at logon. Application files and data remain in the project root.'
