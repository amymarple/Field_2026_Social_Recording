<#
.SYNOPSIS
    Continuous RTSP recorder for EXTRA direct-IP cameras (Dahua-format), recorded as
    additional channels alongside the Reolink footage. Writes hourly fragmented-MP4
    per camera into the SAME root as the Reolink recorder, e.g.:

        E:\Reolink_record\CH07\CH07_2026-07-01_20-00-00_to_21-00-00.mp4
        E:\Reolink_record\CH08\...

    A SEPARATE instance from rtsp_record.ps1 / thermal_record.ps1: its own mutex, its
    own log, and its own scheduled task. Same robustness (restart on drop, stall-
    watchdog, start_to_end naming).

    *** DOES NOT TOUCH THE OTHER RECORDERS. ***
    - It NEVER blanket-kills ffmpeg (that would hit the Reolink/thermal recorders).
    - Retention / disk-guard are scoped to ONLY this recorder's own channels (from the
      config Streams list), so even if enabled they can never delete CH01-CH06.

.NOTES
    Settings + credentials live in extra_cam.config.psd1 (kept OUT of git, on E:).
    Meant to be launched by a SYSTEM scheduled task, NOT from a Claude session.
#>

param([string]$ConfigPath = 'E:\Reolink_record\extra_cam.config.psd1')

$ErrorActionPreference = 'Continue'

# single-instance guard (distinct name from the main + thermal recorders)
try   { $script:xMutex = New-Object System.Threading.Mutex($false, 'Global\ReolinkExtraCamRecorder') }
catch { $script:xMutex = New-Object System.Threading.Mutex($false, 'ReolinkExtraCamRecorder') }
if (-not $script:xMutex.WaitOne(0)) { Write-Host 'Extra-cam recorder already running; exiting.'; exit 0 }

if (-not (Test-Path $ConfigPath)) { Write-Error "Config not found: $ConfigPath"; exit 1 }
$cfg = Import-PowerShellDataFile -Path $ConfigPath

$root   = $cfg.Root
$ffmpeg = $cfg.Ffmpeg
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$masterLog = Join-Path $logDir 'extra_cam_recorder.log'

# ONLY this recorder's own channel dirs (never the whole Reolink root) -> retention /
# disk-guard can never touch CH01-CH06 even if someone enables them.
$OwnChannels = @($cfg.Streams | ForEach-Object { $_.Name })

function Log([string]$m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Write-Host $line
    Add-Content -Path $masterLog -Value $line
}

function Get-FreeGB { $name = (Split-Path $root -Qualifier).TrimEnd(':'); [math]::Round((Get-PSDrive -Name $name).Free / 1GB, 1) }

# Scoped to $OwnChannels ONLY - this recorder never enumerates other channels' files.
function Get-AllRecordings {
    foreach ($n in $OwnChannels) {
        $d = Join-Path $root $n
        if (Test-Path -LiteralPath $d) { Get-ChildItem $d -File -Filter '*.mp4' -EA SilentlyContinue }
    }
}
function Invoke-Retention {
    if ($cfg.RetentionDays -le 0) { return }
    $cut = (Get-Date).AddDays(-$cfg.RetentionDays)
    Get-AllRecordings | Where-Object { $_.LastWriteTime -lt $cut } |
        ForEach-Object { try { Remove-Item $_.FullName -Force; Log ("retention removed " + $_.Name) } catch {} }
}
function Invoke-DiskGuard {
    if ($cfg.MinFreeGB -le 0) { return }
    if (Get-FreeGB -ge $cfg.MinFreeGB) { return }
    Log ("DISK GUARD: only {0} GB free (< {1}); deleting oldest (own channels only)" -f (Get-FreeGB), $cfg.MinFreeGB)
    foreach ($f in (Get-AllRecordings | Sort-Object LastWriteTime)) {
        if (Get-FreeGB -ge $cfg.MinFreeGB) { break }
        try { Remove-Item $f.FullName -Force; Log ("DISK GUARD removed " + $f.Name) } catch {}
    }
}

function Get-NewestFile([string]$dir) {
    Get-ChildItem $dir -File -Filter '*.mp4' -EA SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
}
function Get-HandleLen([string]$path, [double]$fallback = 0) {
    try { $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite); $len = $fs.Length; $fs.Dispose(); return $len }
    catch { return $fallback }
}

function Start-Stream($s) {
    $dir = Join-Path $root $s.Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $args = @(
        '-nostdin', '-loglevel', 'warning',
        '-rtsp_transport', 'tcp', '-use_wallclock_as_timestamps', '1',
        '-i', $s.Url,
        '-c', 'copy', '-f', 'segment',
        '-segment_time', $cfg.SegmentSeconds,
        '-segment_atclocktime', '1', '-reset_timestamps', '1', '-strftime', '1',
        '-segment_format', 'mp4',
        '-segment_format_options', 'movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=2000000',
        (Join-Path $dir ("{0}_%Y-%m-%d_%H-%M-%S.mp4" -f $s.Name))
    )
    $errLog = Join-Path $logDir ("{0}.ffmpeg.log" -f $s.Name)
    Start-Process -FilePath $ffmpeg -ArgumentList $args -WindowStyle Hidden -RedirectStandardError $errLog -PassThru
}

# NOTE: intentionally NO blanket "Get-Process ffmpeg | Stop-Process" here - that would
# kill the Reolink and thermal recorders' ffmpeg too. The mutex handles single-instance;
# a crashed instance's orphan ffmpeg for OUR channels is reaped by the stall-watchdog.

Log ("=== extra-cam recorder starting: {0} stream(s) [{1}], segment {2}s, retention {3}d ===" -f $cfg.Streams.Count, ($OwnChannels -join ','), $cfg.SegmentSeconds, $cfg.RetentionDays)
Log ("free space: {0} GB" -f (Get-FreeGB))

$procs = @{}; $lastSize = @{}; $lastGrew = @{}; $lastName = @{}
$StallSeconds = 240
$lastMaint = (Get-Date).AddHours(-1)

while ($true) {
    foreach ($s in $cfg.Streams) {
        $name = $s.Name
        $dir  = Join-Path $root $name
        $alive = $procs.ContainsKey($name) -and (-not $procs[$name].HasExited)

        if ($alive) {
            $nf = Get-NewestFile $dir
            if ($nf) {
                if ($nf.Name -ne $lastName[$name]) {
                    if ($lastName[$name]) {
                        $prev = Join-Path $dir $lastName[$name]
                        if ((Test-Path -LiteralPath $prev) -and ($lastName[$name] -notlike '*_to_*')) {
                            $endT = ($nf.BaseName -split '_')[-1]
                            $newBn = [System.IO.Path]::GetFileNameWithoutExtension($lastName[$name]) + '_to_' + $endT + '.mp4'
                            try { Rename-Item -LiteralPath $prev -NewName $newBn -ErrorAction Stop; Log ("{0} finalized {1}" -f $name, $newBn) } catch {}
                        }
                    }
                    $lastName[$name] = $nf.Name; $lastSize[$name] = 0; $lastGrew[$name] = Get-Date
                }
                $sz = Get-HandleLen $nf.FullName $lastSize[$name]
                if ($sz -gt $lastSize[$name]) { $lastSize[$name] = $sz; $lastGrew[$name] = Get-Date }
                elseif (((Get-Date) - $lastGrew[$name]).TotalSeconds -gt $StallSeconds) {
                    Log ("{0} stalled ({1}s no growth); restarting" -f $name, $StallSeconds)
                    try { Stop-Process -Id $procs[$name].Id -Force } catch {}
                    $alive = $false
                }
            }
        }

        if (-not $alive) {
            if ($procs.ContainsKey($name)) { Log ("{0} ffmpeg stopped; restarting" -f $name) }
            $procs[$name]    = Start-Stream $s
            $lastSize[$name] = 0
            $lastGrew[$name] = Get-Date
            Log ("{0} started (pid {1})" -f $name, $procs[$name].Id)
            Start-Sleep -Seconds 2
        }
    }

    if (((Get-Date) - $lastMaint).TotalMinutes -ge 60) {
        $lastMaint = Get-Date
        Invoke-Retention
        Invoke-DiskGuard
        Log ("heartbeat: free {0} GB" -f (Get-FreeGB))
    }
    Start-Sleep -Seconds 15
}
