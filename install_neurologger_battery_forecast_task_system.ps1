<#
.SYNOPSIS
    Install the twice-daily neurologger battery forecast as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers 'Field Neurologger
    Battery Forecast' running neurologger_battery_forecast.ps1 at 01:02 and 13:02 daily
    (two minutes past the hour so the :01 telemetry sample is already on disk). Posts the
    per-logger auto-stop projection and the "start the round by" advice to Slack.

    Prove it first from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -DryRun
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -TestSlack

    Change the planned round times with -RoundHours (decimal local hours), e.g. 8,20.
    The value reaches the worker as ONE "8.25,19.75" string under 'powershell -File'; the worker
    splits it itself (fixed 2026-09-05 - the first build failed parameter binding in the task).
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'Field Neurologger Battery Forecast',
    [string]$ScriptPath,
    [double[]]$RoundHours = @(8.25, 19.75),
    [string[]]$RunAt = @('01:02', '13:02'),
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'neurologger_battery_forecast.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$arg = ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -RoundHours {1}' -f $ScriptPath, ($RoundHours -join ','))
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$triggers = @()
foreach ($t in $RunAt) { $triggers += New-ScheduledTaskTrigger -Daily -At $t }
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT5M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0} (daily at {1}; planned rounds {2})" -f $TaskName, ($RunAt -join ' and '), ($RoundHours -join ', ')) -ForegroundColor Green

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started now. Check E:\recording_qc\neurologger_battery_forecast.txt and Slack.' -ForegroundColor Cyan
}
