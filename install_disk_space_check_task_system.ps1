<#
.SYNOPSIS
    Installs the disk-space Slack warning as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an elevated Administrator PowerShell. Because the recorders no
    longer auto-delete, this task is the safety net: it checks the recording drive
    every few hours and Slack-alerts at 50% / 80% / 90% full. Reuses the Slack
    credentials in the overexposure QC config (E:\recording_qc\overexposure.config.psd1).
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'Field Disk Space Check',
    [string]$ScriptPath,
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$Drive = 'E',
    [string]$At = '00:15',
    [int]$EveryHours = 6,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'disk_space_check.ps1'
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
    '-Drive', $Drive,
    '-ConfigPath', ('"{0}"' -f $ConfigPath)
) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At $At `
    -RepetitionInterval (New-TimeSpan -Hours $EveryHours) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT5M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  every {0} h from {1}; command: powershell.exe {2}" -f $EveryHours, $At, $arg)

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started once for verification.' -ForegroundColor Cyan
}
