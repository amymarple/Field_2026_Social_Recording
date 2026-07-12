<#
.SYNOPSIS
    Daily capped-keyframe (encoder truncation) monitor for the Duo 3 channels (CH01/CH02).
    READ-ONLY at the source: scans yesterday's CLOSED *_to_*.mp4 recordings with ffprobe
    (packet metadata only, one sequential pass, never the open/recording file), appends
    results to E:\recording_qc\, and Slack-alerts if the per-frame cap signature returns.

.DESCRIPTION
    Background: Reolink Duo 3 firmware hard-caps intra keyframes at ~2,000,090 bytes.
    A keyframe that "wants" more is truncated bottom-first, so the bottom band of the
    stitched panorama becomes stale/garbage for that whole GOP (worst at golden hour).
    Fixed 2026-07-11 by setting CH01/CH02 main stream to VBR max 8192 kbps (see
    EXPERIMENT_encoder_bitrate_2026-07-09.md in the recording repo). This check catches
    regression: firmware updates, settings drift, or scene complexity growth.

    Detection is two-fold per scanned hour:
      1) keyframes at exactly -CapBytes (the known Duo 3 cap), and
      2) generic "pinning": the max keyframe size repeating byte-identically
         >= -PinCountMin times (catches a DIFFERENT cap value after a firmware change).
    An alert fires when either exceeds -WarnPercent of that hour's keyframes.

.EXAMPLE
    .\capped_keyframe_check.ps1 -SelfTest          # offline logic check, no disk/Slack
    .\capped_keyframe_check.ps1 -DryRun            # scan yesterday, print, send nothing
    .\capped_keyframe_check.ps1 -Date 2026-07-10 -Hours 17 -DryRun
#>

[CmdletBinding()]
param(
    [string]$Date,                                # yyyy-MM-dd; default = yesterday
    [string[]]$Channels = @('CH01','CH02'),      # only the Duo 3 panoramas ever cap
    [int[]]$Hours = @(5, 12, 17, 19, 20),        # dawn gain-ramp, midday ref, sun-detail peak, dusk gain-ramp (worst: 19:30-20:45)
    [long]$CapBytes = 2000090,
    [double]$WarnPercent = 10.0,
    [int]$PinCountMin = 20,
    [string]$Root = 'E:\Reolink_record',
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$LogDir = 'E:\recording_qc',
    [switch]$DryRun,
    [switch]$SelfTest,
    [switch]$TestSlack
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- helpers ----

function Get-FfprobePath {
    $pinned = Join-Path $Root 'bin\ffprobe.exe'
    if (Test-Path -LiteralPath $pinned) { return $pinned }
    $c = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    throw "ffprobe not found (looked at $pinned and PATH)"
}

# Parse ffprobe csv rows ("<size>,<flags>") and count keyframe statistics.
function Get-KfStat {
    param([string[]]$CsvLines, [long]$Cap, [int]$PinMin)
    $kf = 0; $capped = 0; $sum = [long]0; $max = [long]0; $maxCount = 0
    foreach ($ln in $CsvLines) {
        if (-not $ln) { continue }
        $p = $ln.Split(',')
        if ($p.Count -lt 2) { continue }
        if ($p[$p.Count - 1] -notmatch 'K') { continue }   # keyframes only
        $sz = [long]0
        if (-not [long]::TryParse($p[0], [ref]$sz)) { continue }
        $kf++
        $sum += $sz
        if ($sz -eq $Cap) { $capped++ }
        if ($sz -gt $max) { $max = $sz; $maxCount = 1 }
        elseif ($sz -eq $max -and $sz -gt 0) { $maxCount++ }
    }
    $cappedPct = 0.0; $pinnedPct = 0.0; $meanMB = 0.0
    if ($kf -gt 0) {
        $cappedPct = [math]::Round(100.0 * $capped / $kf, 1)
        if ($maxCount -ge $PinMin) { $pinnedPct = [math]::Round(100.0 * $maxCount / $kf, 1) }
        $meanMB = [math]::Round($sum / $kf / 1048576.0, 2)
    }
    $alertPct = [math]::Max($cappedPct, $pinnedPct)
    [pscustomobject]@{
        Keyframes = $kf; Capped = $capped; CappedPct = $cappedPct
        MaxBytes = $max; MaxCount = $maxCount; PinnedPct = $pinnedPct
        MeanMB = $meanMB; AlertPct = $alertPct
    }
}

function Send-Slack {
    param([string]$Token, [string[]]$Targets, [string]$Text)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ Authorization = "Bearer $Token"; 'Content-Type' = 'application/json; charset=utf-8' }
    foreach ($t in $Targets) {
        $chan = $t
        try {
            if ($t -match '^[UW]') {   # user id -> open DM first
                $body = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json @{ users = $t }))
                $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post -Headers $headers -Body $body
                if (-not $r.ok) { Write-Host "Slack conversations.open failed for ${t}: $($r.error)" -ForegroundColor Yellow; continue }
                $chan = $r.channel.id
            }
            $body = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json @{ channel = $chan; text = $Text }))
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post -Headers $headers -Body $body
            if ($r.ok) { Write-Host "Slack sent -> $t" -ForegroundColor Green }
            else { Write-Host "Slack post failed for ${t}: $($r.error)" -ForegroundColor Yellow }
        } catch { Write-Host "Slack error for ${t}: $($_.Exception.Message)" -ForegroundColor Yellow }
    }
}

function Write-Log {
    param([string]$Line)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath (Join-Path $LogDir 'capped_kf_log.txt') -Value "[$stamp] $Line" -Encoding UTF8
    Write-Host $Line
}

# --------------------------------------------------------------- self test ----

if ($SelfTest) {
    Write-Host 'SelfTest: offline logic check (no disk, no Slack)' -ForegroundColor Cyan
    $pass = $true

    # 1) 90 normal KFs + 10 at cap + non-KF noise -> 10% capped
    $lines = @()
    1..90 | ForEach-Object { $lines += "1500000,K__" }
    1..10 | ForEach-Object { $lines += "2000090,K__" }
    1..50 | ForEach-Object { $lines += "300000,___" }     # P-frames must be ignored
    $s = Get-KfStat -CsvLines $lines -Cap 2000090 -PinMin 20
    if ($s.Keyframes -eq 100 -and $s.Capped -eq 10 -and $s.CappedPct -eq 10.0 -and $s.AlertPct -eq 10.0) {
        Write-Host '  [PASS] cap counting + P-frame filtering' -ForegroundColor Green
    } else { Write-Host "  [FAIL] cap counting: $($s | ConvertTo-Json -Compress)" -ForegroundColor Red; $pass = $false }

    # 2) generic pinning at a DIFFERENT ceiling (firmware drift) -> alert via PinnedPct
    $lines = @(); 1..60 | ForEach-Object { $lines += "1234567,K__" }; 1..40 | ForEach-Object { $lines += "900000,K__" }
    $s = Get-KfStat -CsvLines $lines -Cap 2000090 -PinMin 20
    if ($s.Capped -eq 0 -and $s.PinnedPct -eq 60.0 -and $s.AlertPct -eq 60.0) {
        Write-Host '  [PASS] generic ceiling (pinning) detection' -ForegroundColor Green
    } else { Write-Host "  [FAIL] pinning: $($s | ConvertTo-Json -Compress)" -ForegroundColor Red; $pass = $false }

    # 3) healthy hour -> no alert
    $lines = @(); 1..100 | ForEach-Object { $lines += "$(1000000 + $_ * 137),K__" }
    $s = Get-KfStat -CsvLines $lines -Cap 2000090 -PinMin 20
    if ($s.AlertPct -eq 0.0) { Write-Host '  [PASS] healthy hour stays quiet' -ForegroundColor Green }
    else { Write-Host "  [FAIL] healthy: $($s | ConvertTo-Json -Compress)" -ForegroundColor Red; $pass = $false }

    if ($pass) { Write-Host 'SelfTest: ALL PASS' -ForegroundColor Green; exit 0 }
    Write-Host 'SelfTest: FAILED' -ForegroundColor Red; exit 1
}

# ------------------------------------------------------------------- setup ----

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not $Date) { $Date = (Get-Date).Date.AddDays(-1).ToString('yyyy-MM-dd') }

$cfg = $null; $token = $null; $targets = @()
if (Test-Path -LiteralPath $ConfigPath) {
    $cfg = Import-PowerShellDataFile -LiteralPath $ConfigPath
    $token = $cfg.SlackBotToken
    if ($cfg.ContainsKey('CappedKfChannels')) { $targets = @($cfg.CappedKfChannels) }
    elseif ($cfg.ContainsKey('SlackChannels')) { $targets = @($cfg.SlackChannels) }
} else {
    Write-Host "WARNING: Slack config not found at $ConfigPath (scan will run, alerts cannot send)" -ForegroundColor Yellow
}

if ($TestSlack) {
    if (-not $token) { Write-Host 'No Slack token available.' -ForegroundColor Red; exit 2 }
    $dm = @($targets | Where-Object { $_ -match '^[UW]' })
    if (-not $dm) { $dm = $targets }
    Send-Slack -Token $token -Targets $dm -Text "Test from capped_keyframe_check.ps1 on $env:COMPUTERNAME - wiring OK. Daily scan watches CH01/CH02 for the Duo 3 keyframe cap (truncated panorama bottom)."
    exit 0
}

$ffprobe = Get-FfprobePath
$histCsv = Join-Path $LogDir 'capped_kf_history.csv'
if (-not (Test-Path -LiteralPath $histCsv)) {
    Set-Content -LiteralPath $histCsv -Value 'date,channel,hour,segments,keyframes,capped,capped_pct,pinned_pct,mean_kf_mb,max_kf_bytes,alert' -Encoding UTF8
}

# -------------------------------------------------------------------- scan ----

$rows = @(); $breaches = @(); $scanErrors = 0
foreach ($ch in $Channels) {
    foreach ($h in $Hours) {
        $hh = '{0:00}' -f $h
        $pattern = ('{0}_{1}_{2}-*_to_*.mp4' -f $ch, $Date, $hh)
        $dir = Join-Path $Root $ch
        $segs = @(Get-ChildItem -LiteralPath $dir -Filter $pattern -File -ErrorAction SilentlyContinue | Sort-Object Name)
        if ($segs.Count -eq 0) {
            Write-Log ("{0} {1} {2}:00 - no closed recording found (skipped)" -f $Date, $ch, $hh)
            continue
        }
        $allLines = @()
        foreach ($seg in $segs) {
            try {
                $allLines += & $ffprobe -v error -select_streams v:0 -show_entries packet=size,flags -of 'csv=p=0' $seg.FullName
            } catch {
                Write-Log ("{0} {1} {2}:00 - ffprobe failed on {3}: {4}" -f $Date, $ch, $hh, $seg.Name, $_.Exception.Message)
                $scanErrors++
            }
        }
        $s = Get-KfStat -CsvLines $allLines -Cap $CapBytes -PinMin $PinCountMin
        if ($s.Keyframes -eq 0) {
            Write-Log ("{0} {1} {2}:00 - no keyframes parsed ({3} segment(s)) - check manually" -f $Date, $ch, $hh, $segs.Count)
            $scanErrors++
            continue
        }
        $isAlert = ($s.AlertPct -ge $WarnPercent)
        $row = [pscustomobject]@{
            Date = $Date; Channel = $ch; Hour = $hh; Segments = $segs.Count
            Keyframes = $s.Keyframes; Capped = $s.Capped; CappedPct = $s.CappedPct
            PinnedPct = $s.PinnedPct; MeanMB = $s.MeanMB; MaxBytes = $s.MaxBytes; Alert = $isAlert
        }
        $rows += $row
        if ($isAlert) { $breaches += $row }
        Add-Content -LiteralPath $histCsv -Encoding UTF8 -Value (
            '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}' -f $Date, $ch, $hh, $segs.Count,
            $s.Keyframes, $s.Capped, $s.CappedPct, $s.PinnedPct, $s.MeanMB, $s.MaxBytes, $isAlert)
        Write-Log ("{0} {1} {2}:00 - KFs={3} capped={4} ({5}%) pinned={6}% meanKF={7}MB maxKF={8}B alert={9}" -f
            $Date, $ch, $hh, $s.Keyframes, $s.Capped, $s.CappedPct, $s.PinnedPct, $s.MeanMB, $s.MaxBytes, $isAlert)
    }
}

# ------------------------------------------------------------------- alert ----

if ($breaches.Count -gt 0) {
    $lines = @("[ALERT] Capped keyframes are BACK on the Duo 3 stream(s) - $Date")
    foreach ($b in $breaches) {
        $lines += (" - {0} {1}:00  {2}% of keyframes truncated (mean {3} MB, max {4} B, {5} KFs)" -f
            $b.Channel, $b.Hour, [math]::Max($b.CappedPct, $b.PinnedPct), $b.MeanMB, $b.MaxBytes, $b.Keyframes)
    }
    $lines += 'Impact: bottom band of the panorama is stale/dropped during those GOPs (bad for CV).'
    $lines += 'Check camera encode settings: CH01/CH02 main stream should be VBR max 8192 kbps.'
    $lines += 'If settings are correct and this persists, step down to 6144. History: E:\recording_qc\capped_kf_history.csv'
    $text = $lines -join "`n"
    if ($DryRun) {
        Write-Host "`n--- DRY RUN: alert that WOULD be sent ---" -ForegroundColor Yellow
        Write-Host $text
    } elseif ($token -and $targets.Count -gt 0) {
        Send-Slack -Token $token -Targets $targets -Text $text
    } else {
        Write-Log 'ALERT condition but no Slack config available - alert NOT sent'
    }
} else {
    Write-Host ("All scanned hours healthy (worst alert-pct {0}%)" -f (@($rows | ForEach-Object { $_.CappedPct }) | Measure-Object -Maximum).Maximum) -ForegroundColor Green
}

if ($scanErrors -gt 0) { exit 2 }
exit 0
