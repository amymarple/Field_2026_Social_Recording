<#
.SYNOPSIS
    Install the EXTRA-CAM recorder (CH07/CH08) as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers a SYSTEM task that
    runs extra_cam_record.ps1 at startup and self-heals (repeats every 5 min; the
    recorder's own mutex makes duplicate launches exit immediately). Independent of the
    Reolink and thermal recorders - it never touches them.
#>
[CmdletBinding()]
param(
    [string]$TaskName   = 'Field Extra Cam Recorder (CH07-CH08)',
    [string]$ScriptPath,
    [string]$ConfigPath = 'E:\Reolink_record\extra_cam.config.psd1',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'extra_cam_record.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Config not found: $ConfigPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$arg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath), '-ConfigPath', ('"{0}"' -f $ConfigPath)) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
# At startup + repeat every 5 min for self-heal (mutex prevents duplicate instances).
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT0S'   # no time limit (runs continuously)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  runs: powershell.exe {0}" -f $arg) -ForegroundColor DarkGray

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started now. Give it ~10s, then check E:\Reolink_record\CH07 / CH08 for a growing file.' -ForegroundColor Cyan
}
