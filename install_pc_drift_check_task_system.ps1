<#
.SYNOPSIS
    Install the passive PC-clock drift monitor as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers a SYSTEM task
    that runs pc_drift_check.ps1 four times a day (00:45, 06:45, 12:45, 18:45).
    Each run sends a few read-only NTP queries (it NEVER adjusts the clock),
    appends one row to E:\recording_qc\pc_drift_log.csv, and refreshes
    E:\recording_qc\pc_drift.png.

    Prove it first from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File pc_drift_check.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File pc_drift_check.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'Field PC Drift Check',
    [string]$ScriptPath,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'pc_drift_check.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$arg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath)) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Daily -At '00:45'
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration (New-TimeSpan -Hours 23)).Repetition
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT5M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0} (00:45 + every 6 h)" -f $TaskName) -ForegroundColor Green
Write-Host ("  runs: powershell.exe {0}" -f $arg) -ForegroundColor DarkGray

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started now. Check E:\recording_qc\pc_drift_log.csv for a new row and pc_drift.png.' -ForegroundColor Cyan
}
