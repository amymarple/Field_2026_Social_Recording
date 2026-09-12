# End-of-cohort shutdown: disable + stop every recorder and watchdog task, kill ffmpeg.
# Run from an ELEVATED (Administrator) PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File stop_all_recording.ps1
# Cohort start: -Enable re-enables AND starts every task immediately (no reboot needed;
# the at-startup/at-logon triggers alone would otherwise wait for the next boot/logon).
# Manual GUI starts remain: wild_console (BLE scan) and the WISER acquisition software.
# 2026-09-12 (end of cohort 3): list completed with every task registered by this repo's
# installers - the weather listener, LED sync, PC drift check, neurologger battery forecast
# and connected log, WISER alive check and the daily health check were missing. The sibling
# repo's tasks (WISER backup 13:00, hourly occupancy) are analysis jobs and are NOT touched.
param([switch]$Enable)

$tasks = @(
    # recorders / producers first
    'Reolink RTSP Recorder'
    'EmpireTech Thermal Cameras Recorder'
    'Field UltraMic Recorder'
    'Field RTSP Failover Recorder'
    'Field Weather Listener'
    'Field LED Sync'
    # watchdogs / QC
    'Field Recording Alive Check'
    'Field Neurologger Alive Check'
    'Field Neurologger Battery Forecast'
    'Field Neurologger Connected Log'
    'Field WISER Alive Check'
    'Field PC Drift Check'
    'Field Overexposure Check (Finished)'
    'Field Overexposure Check (Sunrise Active)'
    'Field Recording Continuity Check'
    'Field Disk Space Check'
    'Field Capped Keyframe Check'
    'Recording Health Check'
)

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED - run from an Administrator PowerShell.' -ForegroundColor Red; exit 1 }

foreach ($t in $tasks) {
    if ($Enable) {
        try { Enable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null }
        catch { Write-Host "not found: $t" -ForegroundColor Yellow; continue }
        try { Start-ScheduledTask -TaskName $t -ErrorAction Stop; Write-Host "enabled + started: $t" }
        catch { Write-Host "enabled (start failed: $($_.Exception.Message)): $t" -ForegroundColor Yellow }
    } else {
        try { Disable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null } catch { Write-Host "not found: $t" -ForegroundColor Yellow; continue }
        Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        Write-Host "disabled: $t"
    }
}

if (-not $Enable) {
    Stop-Process -Name ffmpeg -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    if (Get-Process ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host 'WARNING: ffmpeg still running - run again or check Task Manager' -ForegroundColor Red
    } else {
        Write-Host 'ALL RECORDERS STOPPED - no ffmpeg left.' -ForegroundColor Green
    }
}
