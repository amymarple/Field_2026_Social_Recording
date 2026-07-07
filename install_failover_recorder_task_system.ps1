<#
.SYNOPSIS
    Installs the storage-failover recorder as a SYSTEM task, and MIRRORS the pieces it
    needs onto the fallback drive (D:) so an E: failure can't take them down with it:
      - ffmpeg.exe            -> D:\Reolink_record\bin\
      - recorder config       -> D:\Reolink_record\recorder.config.psd1   (NVR creds/channels)
      - Slack QC config       -> D:\recording_qc\overexposure.config.psd1  (alert creds)

    The task runs failover_recorder.ps1 continuously. While E: is healthy it is DORMANT
    (probe only, no streams) and does NOT touch the primary recorder. Run once from an
    elevated Administrator PowerShell.

.NOTES
    Re-run this any time the recorder config or Slack creds change, to refresh the D:
    mirror. Safe to run while everything is healthy (does not restart the primary).
#>

[CmdletBinding()]
param(
    [string]$TaskName        = 'Field RTSP Failover Recorder',
    [string]$ScriptPath,
    [string]$PrimaryRoot     = 'E:\Reolink_record',
    [string]$FailoverRoot    = 'D:\Reolink_record',
    [string]$PrimaryConfig   = 'E:\Reolink_record\recorder.config.psd1',
    [string]$PrimaryFfmpeg   = 'E:\Reolink_record\bin\ffmpeg.exe',
    [string]$PrimarySlack    = 'E:\recording_qc\overexposure.config.psd1',
    [int]$ProbeFailsToTrip   = 4,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'failover_recorder.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run this installer again.' -ForegroundColor Red; exit 1 }

# ---------- mirror the essentials to the fallback drive (independent of E:) ----------
$foBin = Join-Path $FailoverRoot 'bin'
New-Item -ItemType Directory -Force -Path $foBin | Out-Null
New-Item -ItemType Directory -Force -Path 'D:\recording_qc' | Out-Null

# ffmpeg: prefer the pinned copy, else whatever is on PATH
$srcFfmpeg = if (Test-Path $PrimaryFfmpeg) { $PrimaryFfmpeg } else { $c = Get-Command ffmpeg -EA SilentlyContinue; if ($c) { $c.Source } else { $null } }
if (-not $srcFfmpeg) { throw 'No ffmpeg found to mirror (checked E: pin and PATH).' }
Copy-Item -LiteralPath $srcFfmpeg -Destination (Join-Path $foBin 'ffmpeg.exe') -Force
Write-Host ("mirrored ffmpeg  {0} -> {1}" -f $srcFfmpeg, (Join-Path $foBin 'ffmpeg.exe')) -ForegroundColor Green

if (Test-Path $PrimaryConfig) { Copy-Item -LiteralPath $PrimaryConfig -Destination (Join-Path $FailoverRoot 'recorder.config.psd1') -Force; Write-Host "mirrored recorder config -> $FailoverRoot" -ForegroundColor Green }
else { Write-Host "WARNING: primary config not found at $PrimaryConfig (failover will fall back to E: config, which won't exist if E: dies)." -ForegroundColor Yellow }

if (Test-Path $PrimarySlack) { Copy-Item -LiteralPath $PrimarySlack -Destination 'D:\recording_qc\overexposure.config.psd1' -Force; Write-Host 'mirrored Slack creds -> D:\recording_qc\' -ForegroundColor Green }
else { Write-Host "WARNING: Slack config not found at $PrimarySlack (failover alerts may not send)." -ForegroundColor Yellow }

# ---------- register the SYSTEM task (continuous; starts at boot) ----------
$arg = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $ScriptPath),
    '-PrimaryRoot', ('"{0}"' -f $PrimaryRoot),
    '-FailoverRoot', ('"{0}"' -f $FailoverRoot),
    '-ProbeFailsToTrip', $ProbeFailsToTrip
) -join ' '

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$settings.ExecutionTimeLimit = 'PT0S'   # no time limit (runs forever)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("`nInstalled: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  command: powershell.exe {0}" -f $arg)
Write-Host '  While E: is healthy it stays DORMANT (probe only) and does NOT touch the primary recorder.'

if ($RunNow) { Start-ScheduledTask -TaskName $TaskName; Write-Host 'Started (will sit dormant while E: is healthy).' -ForegroundColor Cyan }
