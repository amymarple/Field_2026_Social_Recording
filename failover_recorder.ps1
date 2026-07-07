<#
.SYNOPSIS
    Dedicated STORAGE-FAILOVER recorder for the Reolink RTSP capture.

    Watches the PRIMARY recording drive (E:). While it is healthy this script is
    DORMANT — it only write-probes the drive every few seconds and pulls NO streams,
    so it never disturbs the running primary recorder (rtsp_record.ps1, which it does
    NOT modify or share code/mutex with).

    If the primary drive becomes UNWRITABLE (disk failure), it:
      1. Slack-alerts,
      2. STOPS the primary recorder task (it's writing to a dead disk anyway), and
      3. records all channels to the FALLBACK drive (D:) itself,
    so capture continues. This is triggered by a DISK write-probe failing
    -ProbeFailsToTrip times in a row — independent of "files not growing", so an
    RTSP/NVR outage will NOT trip it.

    Failback is MANUAL (no drive flapping): once on D: it stays there until a human
    fixes E:, stops this task, runs -Reset, and restarts the primary. See README.

.PARAMETER Once     Run ONE diagnostic check (probe + report) and exit. Never acts. Read-only.
.PARAMETER Reset    Clear the failover state flag (use after E: is fixed) and exit.
.PARAMETER SelfTest Offline logic check (probe + naming) on temp dirs. No Slack/streams. Exit.
.PARAMETER TestSlack Send a test alert to the configured destinations, then exit.
.PARAMETER DryRun   In the loop, detect + log + alert but do NOT stop primary or start ffmpeg.

.NOTES
    ffmpeg + config + Slack creds must live on a NON-E: drive so an E: death doesn't
    take them too; install_failover_recorder_task_system.ps1 mirrors them to D:.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath      = 'D:\Reolink_record\recorder.config.psd1',
    [string]$PrimaryRoot     = 'E:\Reolink_record',
    [string]$FailoverRoot    = 'D:\Reolink_record',
    [string]$PrimaryTaskName = 'Reolink RTSP Recorder',
    [string]$Ffmpeg          = 'D:\Reolink_record\bin\ffmpeg.exe',
    [string]$SlackConfig     = 'D:\recording_qc\overexposure.config.psd1',
    [string]$StatePath       = 'D:\recording_qc\failover_state.json',
    [string]$LogPath         = 'D:\recording_qc\failover_recorder.log',
    [int]$ProbeFailsToTrip   = 4,
    [int]$PollSeconds        = 15,
    [int]$StallSeconds       = 240,
    [switch]$Once,
    [switch]$Reset,
    [switch]$SelfTest,
    [switch]$TestSlack,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Log([string]$m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Write-Host $line
    try { $d = Split-Path -Parent $LogPath; if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }; Add-Content -LiteralPath $LogPath -Value $line } catch {}
}

# ---------- config (RTSP creds/channels); prefer the D: mirror, fall back to E: ----------
function Load-RecorderConfig {
    foreach ($p in @($ConfigPath, 'E:\Reolink_record\recorder.config.psd1')) {
        if ($p -and (Test-Path -LiteralPath $p)) { try { return (Import-PowerShellDataFile -LiteralPath $p) } catch {} }
    }
    return $null
}

# ---------- drive write-probe (the DISK test; not an RTSP test) ----------
function Test-RootWritable([string]$Root) {
    try {
        if (-not (Test-Path -LiteralPath $Root)) { return $false }
        $probe = Join-Path $Root ('.failover_probe_{0}.tmp' -f $PID)
        [System.IO.File]::WriteAllText($probe, [DateTime]::UtcNow.Ticks.ToString())
        $ok = Test-Path -LiteralPath $probe
        Remove-Item -LiteralPath $probe -Force -EA SilentlyContinue
        return [bool]$ok
    } catch { return $false }
}

# ---------- Slack (creds mirrored off E:) ----------
function Get-Slack {
    $s = @{ Token = $null; Channels = @() }
    foreach ($p in @($SlackConfig, 'E:\recording_qc\overexposure.config.psd1')) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            try { $c = Import-PowerShellDataFile -LiteralPath $p; if ($c.SlackBotToken) { $s.Token = $c.SlackBotToken; $s.Channels = @($c.SlackChannels) }; break } catch {}
        }
    }
    return $s
}
function Resolve-SlackChannelId([string]$Token, [string]$Dest) {
    if ($Dest -match '^[UW]') {
        try { $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' -Body (@{ users = $Dest } | ConvertTo-Json); if ($r.ok) { return $r.channel.id } } catch {}
        return $null
    }
    return $Dest
}
function Send-SlackAlert([string]$Text) {
    $s = Get-Slack
    if (-not $s.Token -or $s.Channels.Count -eq 0) { Log "  (no Slack creds reachable; alert not sent: $Text)"; return $false }
    $any = $false
    foreach ($d in $s.Channels) {
        $cid = Resolve-SlackChannelId $s.Token $d; if (-not $cid) { continue }
        try { $r = Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post -Headers @{ Authorization = "Bearer $($s.Token)" } -ContentType 'application/json; charset=utf-8' -Body (@{ channel = $cid; text = $Text } | ConvertTo-Json); if ($r.ok) { $any = $true } } catch {}
    }
    return $any
}

# ---------- state ----------
function Get-State { if (Test-Path -LiteralPath $StatePath) { try { return (Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json) } catch {} }; return $null }
function Set-FailedOver([bool]$v) {
    $d = Split-Path -Parent $StatePath; if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    (@{ failedOver = $v; since = (Get-Date).ToString('o') } | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

# ---------- ffmpeg / channel recording to the FALLBACK root ----------
function Resolve-Ffmpeg { if (Test-Path -LiteralPath $Ffmpeg) { return $Ffmpeg }; $c = Get-Command ffmpeg -EA SilentlyContinue; if ($c) { return $c.Source }; return $null }
function Get-Url($cfg, [int]$n) { $ch = '{0:D2}' -f $n; 'rtsp://{0}:{1}@{2}:{3}/Preview_{4}_main' -f $cfg.User, $cfg.Pass, $cfg.NvrIp, $cfg.RtspPort, $ch }
function Get-HandleLen([string]$path, [double]$fallback = 0) { try { $fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite'); $l = $fs.Length; $fs.Dispose(); return $l } catch { return $fallback } }
function Get-NewestFile([string]$dir) { Get-ChildItem $dir -File -Filter '*.mp4' -EA SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1 }

function Start-FailoverChannel($cfg, $ff, [int]$n, [int]$segSec) {
    $ch = '{0:D2}' -f $n
    $outDir = Join-Path $FailoverRoot "CH$ch"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $args = @(
        '-nostdin', '-loglevel', 'warning',
        '-rtsp_transport', 'tcp', '-use_wallclock_as_timestamps', '1',
        '-i', (Get-Url $cfg $n),
        '-c', 'copy', '-f', 'segment',
        '-segment_time', $segSec,
        '-segment_atclocktime', '1', '-reset_timestamps', '1', '-strftime', '1',
        '-segment_format', 'mp4',
        '-segment_format_options', 'movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=2000000',
        (Join-Path $outDir ("CH{0}_%Y-%m-%d_%H-%M-%S.mp4" -f $ch))
    )
    $errLog = Join-Path (Split-Path -Parent $LogPath) "failover_CH$ch.ffmpeg.log"
    Start-Process -FilePath $ff -ArgumentList $args -WindowStyle Hidden -RedirectStandardError $errLog -PassThru
}

# ============================ SELF TEST ============================
if ($SelfTest) {
    Say '=== SELF TEST (probe + naming; no Slack, no streams) ===' Cyan
    $tmp = Join-Path $env:TEMP ('fo_selftest_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $wOk = Test-RootWritable $tmp
    $wBad = Test-RootWritable (Join-Path $tmp 'no\such\path')
    Remove-Item $tmp -Recurse -Force -EA SilentlyContinue
    $cfgOk = [bool](Load-RecorderConfig)
    Say ("  writable dir  -> probe {0} (expect True)" -f $wOk) $(if ($wOk) { 'Green' } else { 'Red' })
    Say ("  missing dir   -> probe {0} (expect False)" -f $wBad) $(if (-not $wBad) { 'Green' } else { 'Red' })
    Say ("  config loadable: {0}" -f $cfgOk) $(if ($cfgOk) { 'Green' } else { 'Yellow' })
    $pass = $wOk -and (-not $wBad)
    Say ("`nSELF TEST: {0}" -f $(if ($pass) { 'PASS' } else { 'FAIL' })) $(if ($pass) { 'Green' } else { 'Red' })
    exit $(if ($pass) { 0 } else { 2 })
}

if ($Reset) {
    Set-FailedOver $false
    Say "Failover state cleared (failedOver=false). Now: stop this task, then Start-ScheduledTask '$PrimaryTaskName'." Green
    exit 0
}

if ($TestSlack) {
    $ok = Send-SlackAlert (":satellite: Failover recorder test - {0} armed, watching {1} (fallback {2})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'), $PrimaryRoot, $FailoverRoot)
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# ============================ diagnostic single check ============================
if ($Once) {
    $writable = Test-RootWritable $PrimaryRoot
    $st = Get-State
    Say ("[{0}] primary {1} writable={2}  failedOver={3}" -f (Get-Date).ToString('HH:mm:ss'), $PrimaryRoot, $writable, $(if ($st) { $st.failedOver } else { $false })) $(if ($writable) { 'Green' } else { 'Red' })
    Say '  (read-only check; took no action)' DarkGray
    exit 0
}

# ============================ MAIN LOOP (the scheduled task) ============================
# single-instance guard, distinct from the primary recorder
try { $mutex = New-Object System.Threading.Mutex($false, 'Global\ReolinkFailoverRecorder') }
catch { $mutex = New-Object System.Threading.Mutex($false, 'ReolinkFailoverRecorder') }
if (-not $mutex.WaitOne(0)) { Write-Host 'Failover recorder already running; exiting.'; exit 0 }

$cfg = Load-RecorderConfig
if (-not $cfg) { Log "FATAL: no recorder config found (looked in $ConfigPath and E:). Exiting."; exit 1 }
$segSec = if ($cfg.SegmentSeconds) { [int]$cfg.SegmentSeconds } else { 3600 }
$channels = @($cfg.Channels)

$st = Get-State
$failedOver = [bool]($st -and $st.failedOver)
# If we boot up already in failover mode (e.g. PC rebooted while E: was dead), keep the
# primary recorder stopped so it can't flail on the dead drive / fight for NVR sessions.
if ($failedOver -and -not $DryRun) {
    try { Stop-ScheduledTask -TaskName $PrimaryTaskName -EA SilentlyContinue; Log "resumed in FAILOVER mode; ensured primary '$PrimaryTaskName' stopped" } catch {}
}
$consecFail = 0
$procs = @{}; $lastSize = @{}; $lastGrew = @{}; $lastName = @{}

Log ("=== failover recorder started; watching $PrimaryRoot, fallback $FailoverRoot; failedOver=$failedOver; trip after $ProbeFailsToTrip fails x ${PollSeconds}s ===")

while ($true) {
    if (-not $failedOver) {
        # ---- DORMANT: just probe the primary drive ----
        if (Test-RootWritable $PrimaryRoot) {
            $consecFail = 0
        } else {
            $consecFail++
            Log ("primary $PrimaryRoot write-probe FAILED ($consecFail/$ProbeFailsToTrip)")
            if ($consecFail -ge $ProbeFailsToTrip) {
                Log ("*** STORAGE FAILOVER TRIGGERED: $PrimaryRoot unwritable ***")
                [void](Send-SlackAlert (":rotating_light: *STORAGE FAILOVER* - {0} is unwritable. Stopping the primary recorder and switching capture to {1}. Fix the drive, then fail back manually." -f $PrimaryRoot, $FailoverRoot))
                if ($DryRun) { Log 'DRYRUN: would stop primary + start failover recording (no action taken).'; $consecFail = 0 }
                else {
                    $ff = Resolve-Ffmpeg
                    if (-not $ff) { Log 'FATAL: no ffmpeg reachable off E: — cannot fail over.'; }
                    else {
                        try { Stop-ScheduledTask -TaskName $PrimaryTaskName -EA Stop; Log "stopped primary task '$PrimaryTaskName'" } catch { Log "could not stop primary task: $($_.Exception.Message)" }
                        Start-Sleep -Seconds 3   # let primary ffmpegs die on their E: write error, freeing NVR sessions
                        foreach ($n in $channels) { $ch = '{0:D2}' -f $n; $procs[$ch] = Start-FailoverChannel $cfg $ff $n $segSec; $lastSize[$ch] = 0; $lastGrew[$ch] = Get-Date; Log "CH$ch failover recording -> $FailoverRoot (pid $($procs[$ch].Id))"; Start-Sleep -Seconds 2 }
                        $failedOver = $true; Set-FailedOver $true
                        [void](Send-SlackAlert (":floppy_disk: Failover recording ACTIVE on {0} for {1} channel(s)." -f $FailoverRoot, $channels.Count))
                    }
                }
            }
        }
    } else {
        # ---- FAILOVER ACTIVE: keep the D: recorders alive (start/stall-restart/rollover-rename) ----
        $ff = Resolve-Ffmpeg
        foreach ($n in $channels) {
            $ch = '{0:D2}' -f $n
            $alive = $procs.ContainsKey($ch) -and $procs[$ch] -and (-not $procs[$ch].HasExited)
            if ($alive) {
                $dir = Join-Path $FailoverRoot "CH$ch"; $nf = Get-NewestFile $dir
                if ($nf) {
                    if ($nf.Name -ne $lastName[$ch]) {
                        if ($lastName[$ch]) {
                            $prev = Join-Path $dir $lastName[$ch]
                            if ((Test-Path -LiteralPath $prev) -and ($lastName[$ch] -notlike '*_to_*')) {
                                $endT = ($nf.BaseName -split '_')[-1]
                                $newBn = [System.IO.Path]::GetFileNameWithoutExtension($lastName[$ch]) + '_to_' + $endT + '.mp4'
                                try { Rename-Item -LiteralPath $prev -NewName $newBn -EA Stop } catch {}
                            }
                        }
                        $lastName[$ch] = $nf.Name; $lastSize[$ch] = 0; $lastGrew[$ch] = Get-Date
                    }
                    $sz = Get-HandleLen $nf.FullName $lastSize[$ch]
                    if ($sz -gt $lastSize[$ch]) { $lastSize[$ch] = $sz; $lastGrew[$ch] = Get-Date }
                    elseif (((Get-Date) - $lastGrew[$ch]).TotalSeconds -gt $StallSeconds) { Log "CH$ch failover stalled; restarting"; try { Stop-Process -Id $procs[$ch].Id -Force } catch {}; $alive = $false }
                }
            }
            if (-not $alive -and $ff) { $procs[$ch] = Start-FailoverChannel $cfg $ff $n $segSec; $lastSize[$ch] = 0; $lastGrew[$ch] = Get-Date; Log "CH$ch failover (re)started (pid $($procs[$ch].Id))" }
        }
    }
    Start-Sleep -Seconds $PollSeconds
}
