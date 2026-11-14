# Scheduler configuration: registers a Windows Task Scheduler job that runs run_windows.bat every 30 minutes.
# Usage (PowerShell, from this folder):  .\register_task.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Join-Path $root "run_windows.bat"
$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "TrainerCentralSync" -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Registered TrainerCentralSync (every 30 min). Check: Get-ScheduledTaskInfo -TaskName TrainerCentralSync"
# Remove with: Unregister-ScheduledTask -TaskName TrainerCentralSync -Confirm:$false
