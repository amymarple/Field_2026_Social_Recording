<#
.SYNOPSIS
    Manual calibration-session recorder: all 10 cameras (12 streams) -> E:\calibration.

.DESCRIPTION
    One-shot console recorder for the calibration field sessions. Run it from a cmd
    window, do the field work, press Ctrl+C to stop. Reuses the PRODUCTION configs
    (recorder.config.psd1 + thermal.config.psd1) for URLs/credentials/ffmpeg so the
    streams are identical to the experiment recordings, but is fully independent of
    the production recorders:
      - no shared mutex, no scheduled task;
      - writes ONLY under E:\calibration\session_<start>\ (never the production trees);
      - stops ONLY the ffmpeg PIDs it spawned itself - NEVER a blanket ffmpeg kill
        (the production recorders may be running concurrently).
    Segments follow the standard naming contract (hourly clock-aligned fragmented MP4;
    a closed segment gets its _to_<end> suffix, including at Ctrl+C), so the existing
    QC / verify / copy tooling reads a session like any recording day.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File calibration_record.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File calibration_record.ps1 -DryRun
    powershell -NoProfile -ExecutionPolicy Bypass -File calibration_record.ps1 -Seconds 20 -Only CH01,108_visual
#>
[CmdletBinding()]
param(
    [string]$OutRoot       = 'E:\calibration',
    [string]$NvrConfig     = 'E:\Reolink_record\recorder.config.psd1',
    [string]$ThermalConfig = 'E:\thermal_record\thermal.config.psd1',
    [int]$Seconds  = 0,                 # 0 = record until Ctrl+C
    [string[]]$Only = @(),              # subset of stream names (testing), e.g. CH01,108_visual
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# refuse to point at any production tree
foreach ($forbidden in 'E:\Reolink_record', 'E:\thermal_record', 'E:\ultramic_record', 'E:\nvr_rescue', 'E:\WILD') {
    if (([System.IO.Path]::GetFullPath($OutRoot)).TrimEnd('\') -like "$forbidden*") {
        throw "OutRoot must not be under a production recording tree: $OutRoot"
    }
}

$nvr = Import-PowerShellDataFile -Path $NvrConfig
$th  = Import-PowerShellDataFile -Path $ThermalConfig
$ffmpeg = $nvr.Ffmpeg
if (-not (Test-Path $ffmpeg)) { throw "ffmpeg not found: $ffmpeg" }

function Mask([string]$u) { $u -replace '(rtsp://[^:]+:)[^@]+@', '$1***@' }

# ---- stream roster: 8 NVR channels + every thermal-config stream -------------------
$streams = @()
foreach ($n in $nvr.Channels) {
    $ch = '{0:D2}' -f [int]$n
    $streams += @{ Name = "CH$ch"
                   Url  = ('rtsp://{0}:{1}@{2}:{3}/Preview_{4}_main' -f $nvr.User, $nvr.Pass, $nvr.NvrIp, $nvr.RtspPort, $ch) }
}
foreach ($s in $th.Streams) { $streams += @{ Name = $s.Name; Url = $s.Url } }
if ($Only.Count) {
    # `powershell -File` passes "A,B" as one string - split on commas ourselves
    $Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
    $streams = @($streams | Where-Object { $Only -contains $_.Name })
    if (-not $streams.Count) { throw "no stream matches -Only $($Only -join ',')" }
}

$stamp   = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$session = Join-Path $OutRoot "session_$stamp"
$logDir  = Join-Path $session 'logs'

Write-Host ("calibration recorder: {0} stream(s) -> {1}" -f $streams.Count, $session)
foreach ($s in $streams) { Write-Host ("  {0,-12} {1}" -f $s.Name, (Mask $s.Url)) }
$freeGB = [math]::Round((Get-PSDrive -Name ((Split-Path $OutRoot -Qualifier).TrimEnd(':'))).Free / 1GB, 1)
Write-Host ("free on target drive: {0} GB" -f $freeGB)
if ($DryRun) { Write-Host 'DRY RUN - nothing launched.'; exit 0 }

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# True length of a file ffmpeg is still writing (Get-ChildItem .Length is stale 0).
function Get-HandleLen([string]$path, [long]$fallback) {
    try {
        $fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
        try { return $fs.Length } finally { $fs.Close() }
    } catch { return $fallback }
}

function Get-NewestSeg([string]$name) {
    Get-ChildItem $session -File -Filter "$name`_*.mp4" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
}

function Start-Stream($s) {
    $args = @(
        '-nostdin', '-loglevel', 'warning',
        '-rtsp_transport', 'tcp', '-use_wallclock_as_timestamps', '1',
        '-i', $s.Url,
        '-c', 'copy', '-f', 'segment',
        '-segment_time', '3600',
        '-segment_atclocktime', '1', '-reset_timestamps', '1', '-strftime', '1',
        '-segment_format', 'mp4',
        '-segment_format_options', 'movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=2000000',
        (Join-Path $session ("{0}_%Y-%m-%d_%H-%M-%S.mp4" -f $s.Name))
    )
    $errLog = Join-Path $logDir ("{0}.ffmpeg.log" -f $s.Name)
    Start-Process -FilePath $ffmpeg -ArgumentList $args -WindowStyle Hidden -RedirectStandardError $errLog -PassThru
}

# rename a stream's previous segment with its _to_<end> suffix once a newer one exists
function Close-PrevSeg([string]$name, [string]$prevName, [string]$endHms) {
    if (-not $prevName -or $prevName -like '*_to_*') { return }
    $prev = Join-Path $session $prevName
    if (Test-Path -LiteralPath $prev) {
        $newBn = [System.IO.Path]::GetFileNameWithoutExtension($prevName) + '_to_' + $endHms + '.mp4'
        try { Rename-Item -LiteralPath $prev -NewName $newBn; Write-Host ("  closed {0}" -f $newBn) } catch {}
    }
}

$procs = @{}; $lastName = @{}; $lastSize = @{}; $lastGrew = @{}; $startedAt = @{}
$StallSeconds   = 90
$ConnectSeconds = 60     # no first segment within this long -> ffmpeg is stuck in the RTSP connect
$t0 = Get-Date

try {
    foreach ($s in $streams) {
        $procs[$s.Name] = Start-Stream $s
        $lastName[$s.Name] = ''; $lastSize[$s.Name] = 0; $lastGrew[$s.Name] = Get-Date; $startedAt[$s.Name] = Get-Date
    }
    Write-Host ("started {0} ffmpeg processes. Recording... press Ctrl+C to stop." -f $procs.Count)

    $lastPrint = Get-Date
    while ($true) {
        Start-Sleep -Seconds 5
        if ($Seconds -gt 0 -and ((Get-Date) - $t0).TotalSeconds -ge $Seconds) { Write-Host 'time limit reached.'; break }

        foreach ($s in $streams) {
            $name = $s.Name
            # dead process -> restart (only our own child)
            if ($procs[$name].HasExited) {
                Write-Host ("  {0} ffmpeg exited (code {1}); restarting" -f $name, $procs[$name].ExitCode)
                $procs[$name] = Start-Stream $s
                $lastGrew[$name] = Get-Date; $startedAt[$name] = Get-Date
                continue
            }
            $nf = Get-NewestSeg $name
            if (-not $nf) {
                # ffmpeg hangs silently in the RTSP connect when the camera is unreachable (no
                # exit, no error, no file - seen 2026-09-18 with the thermal cams powered off);
                # it never recovers on its own once the camera returns, so restart it (our PID only).
                if (((Get-Date) - $startedAt[$name]).TotalSeconds -gt $ConnectSeconds) {
                    Write-Host ("  {0} no stream after {1}s (camera unreachable?); restarting its ffmpeg" -f $name, $ConnectSeconds)
                    try { Stop-Process -Id $procs[$name].Id -Force } catch {}
                    $procs[$name] = Start-Stream $s
                    $lastGrew[$name] = Get-Date; $startedAt[$name] = Get-Date
                }
                continue
            }
            if ($nf.Name -ne $lastName[$name]) {                       # rollover: close previous
                if ($lastName[$name]) { Close-PrevSeg $name $lastName[$name] (($nf.BaseName -split '_')[-1]) }
                $lastName[$name] = $nf.Name; $lastSize[$name] = 0; $lastGrew[$name] = Get-Date
            }
            $sz = Get-HandleLen $nf.FullName $lastSize[$name]
            if ($sz -gt $lastSize[$name]) { $lastSize[$name] = $sz; $lastGrew[$name] = Get-Date }
            elseif (((Get-Date) - $lastGrew[$name]).TotalSeconds -gt $StallSeconds) {
                Write-Host ("  {0} stalled ({1}s no growth); restarting its ffmpeg" -f $name, $StallSeconds)
                try { Stop-Process -Id $procs[$name].Id -Force } catch {}   # OUR child only, by PID
                $procs[$name] = Start-Stream $s
                $lastGrew[$name] = Get-Date; $startedAt[$name] = Get-Date
            }
        }

        if (((Get-Date) - $lastPrint).TotalSeconds -ge 30) {
            $parts = foreach ($s in $streams) { '{0} {1:N0}MB' -f $s.Name, ($lastSize[$s.Name] / 1MB) }
            Write-Host ('[{0:HH:mm:ss}] {1}' -f (Get-Date), ($parts -join ' | '))
            $lastPrint = Get-Date
        }
    }
}
finally {
    Write-Host 'stopping (only the ffmpeg PIDs this script started)...'
    foreach ($name in $procs.Keys) {
        try { if (-not $procs[$name].HasExited) { Stop-Process -Id $procs[$name].Id -Force } } catch {}
    }
    foreach ($name in $procs.Keys) { try { $procs[$name].WaitForExit(5000) | Out-Null } catch {} }
    $endHms = Get-Date -Format 'HH-mm-ss'
    foreach ($s in $streams) {
        $nf = Get-NewestSeg $s.Name
        if ($nf -and $nf.Name -notlike '*_to_*') { Close-PrevSeg $s.Name $nf.Name $endHms }
    }
    Write-Host ''
    Write-Host ("session folder: {0}" -f $session)
    Get-ChildItem $session -File -Filter '*.mp4' -ErrorAction SilentlyContinue | Sort-Object Name |
        ForEach-Object { Write-Host ("  {0,-55} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
    $tot = (Get-ChildItem $session -File -Filter '*.mp4' -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    Write-Host ("total: {0:N2} GB across {1} file(s). Verify, then back up to the analysis PC." -f ($tot / 1GB), (Get-ChildItem $session -File -Filter '*.mp4' -ErrorAction SilentlyContinue).Count)
}
