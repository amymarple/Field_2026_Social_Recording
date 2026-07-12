<#
.SYNOPSIS
    Installs the daily capped-keyframe monitor as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an elevated Administrator PowerShell. Registers a SYSTEM task that runs
    capped_keyframe_check.ps1 every day at 05:20 (after the 05:00 health check) to scan
    YESTERDAY's CH01/CH02 daylight hours for the Duo 3 keyframe-cap regression and Slack-
    alert if it returns. Read-only at the source; reuses the Slack credentials in
    E:\recording_qc\overexposure.config.psd1.
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'Field Capped Keyframe Check',
    [string]$ScriptPath,
    [string]$At = '05:20',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'capped_keyframe_check.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) {
    Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run this installer again.' -ForegroundColor Red
    exit 1
}

$arg = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $ScriptPath)
) -join ' '

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger   = New-ScheduledTaskTrigger -Daily -At $At
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT30M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  daily at {0}; command: powershell.exe {1}" -f $At, $arg)
Write-Host '  Scans yesterday CH01/CH02 hours 12/16/17 for the 2,000,090-byte keyframe cap; Slack-alerts on >=10%.'

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started once for verification (scans yesterday).' -ForegroundColor Cyan
}
