# End-of-cohort shutdown: disable + stop every recorder and watchdog task, kill ffmpeg.
# Run from an ELEVATED (Administrator) PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File stop_all_recording.ps1
# Re-enable for the next cohort with -Enable.
param([switch]$Enable)

$tasks = @(
    'Reolink RTSP Recorder'
    'EmpireTech Thermal Cameras Recorder'
    'Field UltraMic Recorder'
    'Field RTSP Failover Recorder'
    'Field Recording Alive Check'
    'Field Neurologger Alive Check'
    'Field Overexposure Check (Finished)'
    'Field Overexposure Check (Sunrise Active)'
    'Field Recording Continuity Check'
    'Field Disk Space Check'
    'Field Capped Keyframe Check'
)

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED - run from an Administrator PowerShell.' -ForegroundColor Red; exit 1 }

foreach ($t in $tasks) {
    if ($Enable) {
        try { Enable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null; Write-Host "enabled:  $t" }
        catch { Write-Host "not found: $t" -ForegroundColor Yellow }
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
