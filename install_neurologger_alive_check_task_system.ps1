<#
.SYNOPSIS
    Installs the Neurologger "logger missing" Slack alert as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an elevated Administrator PowerShell. Registers a SYSTEM task that
    runs neurologger_alive_check.ps1 every few minutes. It watches the
    discovered_devices.csv snapshot that wild_console keeps rewriting and pages when
    a logger has not been heard over BLE for an hour, when the feed itself goes stale
    (console closed / scan stopped), or on low battery / high storage. Reuses the
    Slack credentials in the overexposure QC config.

    Prove the logic first from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_alive_check.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_alive_check.ps1 -DryRun
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_alive_check.ps1 -TestSlack
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'Field Neurologger Alive Check',
    [string]$ScriptPath,
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [int]$StaleMinutes = 60,
    [int]$EveryMinutes = 5,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'neurologger_alive_check.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) {
    Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run this installer again.' -ForegroundColor Red
    exit 1
}

$arg = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $ScriptPath),
    '-StaleMinutes', $StaleMinutes,
    '-ConfigPath', ('"{0}"' -f $ConfigPath)
) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT4M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  every {0} min; logger stale threshold {1} min; command: powershell.exe {2}" -f $EveryMinutes, $StaleMinutes, $arg)

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started once for verification. Check E:\recording_qc\neurologger_alive_log.txt.' -ForegroundColor Cyan
}
