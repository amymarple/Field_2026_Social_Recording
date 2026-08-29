<#
.SYNOPSIS
    Install the LED sync pulser as a SYSTEM scheduled task.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers a SYSTEM task that
    runs led_sync.ps1 at startup and self-heals (repeats every 5 min; the script's
    Global\FieldLedSync mutex makes duplicate launches exit immediately). Independent
    of every recorder - it only opens the Pico's COM port and appends to E:\led_sync.

    Before installing, prove the hardware from a normal PowerShell (and STOP that
    test with Ctrl+C before -RunNow - the COM port is exclusive to one process):
        powershell -NoProfile -ExecutionPolicy Bypass -File led_sync.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File led_sync.ps1 -TestSeconds 10

    Day-to-day pause/resume needs NO elevation - use the STOP flag:
        New-Item -ItemType File E:\led_sync\STOP    # clean stop within ~1 s
        Remove-Item E:\led_sync\STOP                # resumes on the next 5-min tick
    (Start-ScheduledTask 'Field LED Sync' to resume immediately.)
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'Field LED Sync',
    [string]$ScriptPath,
    [string]$Port     = 'COM11',
    [string]$LogDir   = 'E:\led_sync',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'led_sync.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$arg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath), '-Port', $Port, '-LogDir', ('"{0}"' -f $LogDir)) -join ' '

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
    Write-Host "Started now. Give it ~10s, then check $LogDir for a growing LEDSYNC_*.txt (and the LED blinking)." -ForegroundColor Cyan
}
