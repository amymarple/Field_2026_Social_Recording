<#
.SYNOPSIS
    Install the WISER acquisition watchdog as a SYSTEM scheduled task (every 5 min).

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers 'Field WISER Alive
    Check' running wiser_alive_check.ps1 every 5 minutes: pages Slack when wiserex is
    not running, when the watched live DB stops being written, or (one-shot) when the
    newest sqlite in the data dir is not the watched one (file roll / new cohort).
    Metadata-only - it never opens any file under the live WISER data dir.

    Per cohort, re-register with the current live DB:
        .\install_wiser_alive_check_task_system.ps1 -DbPath 'D:\Wiser\data\<cohort db>.sqlite' -RunNow

    Prove it first from a normal PowerShell:
        powershell -NoProfile -ExecutionPolicy Bypass -File wiser_alive_check.ps1 -SelfTest
        powershell -NoProfile -ExecutionPolicy Bypass -File wiser_alive_check.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'Field WISER Alive Check',
    [string]$ScriptPath,
    [string]$DbPath = 'D:\Wiser\data\3rdcohort_Spike_2026_3.sqlite',
    [switch]$FollowNewest,   # watch whichever .sqlite in the DbPath dir is newest (survives wiserex file rolls)
    [int]$StaleMinutes = 30,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'wiser_alive_check.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

$argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath),
         '-DbPath', ('"{0}"' -f $DbPath),
         '-StaleMinutes', $StaleMinutes)
if ($FollowNewest) { $argList += '-FollowNewest' }
$arg = $argList -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT5M'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0} (every 5 min, watching {1})" -f $TaskName, $DbPath) -ForegroundColor Green

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'Started now. Check E:\recording_qc\wiser_alive_log.txt for the first line.' -ForegroundColor Cyan
}
