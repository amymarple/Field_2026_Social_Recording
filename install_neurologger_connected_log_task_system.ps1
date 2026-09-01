<#
.SYNOPSIS
    Install the connected-telemetry logger (advertisement replacement) as a SYSTEM
    task running every minute.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers 'Field Neurologger
    Connected Log' running neurologger_connected_log.ps1 every 1 min: decodes the
    0xAF heartbeats of every logger currently CONNECTED in wild_console into
    E:\recording_qc\neurologger_connected_telemetry.csv (append-only history) and
    E:\recording_qc\neurologger_connected_status.txt (live table with battery-to-knee
    and card-to-full ETAs).

    Prove it first from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_connected_log.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_connected_log.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'Field Neurologger Connected Log',
    [string]$ScriptPath,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'neurologger_connected_log.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$arg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath)) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT2M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0} (every 1 min)" -f $TaskName) -ForegroundColor Green

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started now. Watch E:\recording_qc\neurologger_connected_status.txt refresh.' -ForegroundColor Cyan
}
