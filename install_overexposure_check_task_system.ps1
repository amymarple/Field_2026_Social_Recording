<#
.SYNOPSIS
    Installs the overexposure / near-black QC as two SYSTEM scheduled tasks.

.DESCRIPTION
    Run once from an elevated Administrator PowerShell. Because a Windows task has one
    fixed action (fixed args) but many triggers, each frame-source mode gets its own
    task so the trigger that fires always uses the right -Mode:

      - "Field Overexposure Check (Finished)"  -> -Mode Finished, hourly all day.
        Reads only COMPLETED hourly files. Never touches an active recording.
      - "Field Overexposure Check (Sunrise Active)" -> -Mode Active, at 08:10/08:30/08:50.
        Samples the currently-recording file via a read-only shared handle to catch the
        morning overexposure transition. Fails fast + falls back; never blocks recording.

    Slack credentials live in -ConfigPath (kept out of git). Fill that in and run
    `overexposure_check.ps1 -TestSlack` before relying on alerts.
#>

[CmdletBinding()]
param(
    [string]$TaskNameFinished = 'Field Overexposure Check (Finished)',
    [string]$TaskNameActive   = 'Field Overexposure Check (Sunrise Active)',
    [string]$ScriptPath,
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$ReportRoot = 'E:\recording_qc\overexposure',
    [string]$FinishedAt = '00:05',                       # hourly anchor
    [string[]]$ActiveTimes = @('08:10', '08:30', '08:50'),
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
# Resolve in the body, not the param default: $PSScriptRoot is unreliable inside param().
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'overexposure_check.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) {
    Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run this installer again.' -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReportRoot | Out-Null

$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT5M'

function New-Arg([string]$Mode) {
    @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $ScriptPath),
        '-Mode', $Mode,
        '-ConfigPath', ('"{0}"' -f $ConfigPath),
        '-ReportRoot', ('"{0}"' -f $ReportRoot)
    ) -join ' '
}

# --- Finished task: fire at FinishedAt, repeat every hour, indefinitely ---
$argFin = New-Arg 'Finished'
$actFin = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argFin
$trgFin = New-ScheduledTaskTrigger -Once -At $FinishedAt `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $TaskNameFinished -Action $actFin -Trigger $trgFin -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed: {0}" -f $TaskNameFinished) -ForegroundColor Green
Write-Host ("  hourly from {0}; command: powershell.exe {1}" -f $FinishedAt, $argFin)

# --- Sunrise Active task: three daily triggers ---
$argAct = New-Arg 'Active'
$actAct = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argAct
$trgAct = @(foreach ($t in $ActiveTimes) { New-ScheduledTaskTrigger -Daily -At $t })
Register-ScheduledTask -TaskName $TaskNameActive -Action $actAct -Trigger $trgAct -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed: {0}" -f $TaskNameActive) -ForegroundColor Green
Write-Host ("  daily at {0}; command: powershell.exe {1}" -f ($ActiveTimes -join ', '), $argAct)

Write-Host ("`nReports/logs: {0}" -f $ReportRoot)
Write-Host ("Config (fill in Slack token + IDs): {0}" -f $ConfigPath) -ForegroundColor Yellow

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskNameFinished
    Write-Host "`nStarted the Finished task once for verification." -ForegroundColor Cyan
}
