<#
.SYNOPSIS
    Install the UltraMic384K audio recorder as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers a SYSTEM task that
    runs ultramic_record.ps1 at startup and self-heals (repeats every 5 min; the
    recorder's own mutex makes duplicate launches exit immediately). Independent of
    the camera recorders - it never touches them or their footage.

    Before installing, prove the mic works from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -ListDevices
        powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -TestClip 5

    NOTE: capture is WASAPI (see README_ultramic.md); audio endpoints are system-wide,
    so the SYSTEM task can open the mic as long as it is plugged into this machine.
    Do NOT install while a user-session test recording is running - the exclusive-mode
    capture locks the mic to one process (stop your test first, then -RunNow).
#>
[CmdletBinding()]
param(
    [string]$TaskName   = 'Field UltraMic Recorder',
    [string]$ScriptPath,
    [string]$ConfigPath = 'E:\ultramic_record\ultramic.config.psd1',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'ultramic_record.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Config not found: $ConfigPath  (copy ultramic.config.example.psd1 to it and fill in the device name)" }

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
    Write-Host 'Started now. Give it ~15s, then check E:\ultramic_record\MIC01 for a growing .wav file.' -ForegroundColor Cyan
}
