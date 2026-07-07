<#
.SYNOPSIS
    Hourly image-quality QC for the 6 visible-light Reolink channels: grab ONE
    recent frame per channel, measure exposure, and Slack-alert if a frame is
    OVEREXPOSED (blown-out / sun glare) or NEAR-BLACK (dead feed / covered lens).

    *** NEVER interrupts or risks the live recording. ***
    - Finished mode (default, all normal hours): reads only the newest COMPLETED
      hourly file (name contains "_to_"). Zero interaction with any active file.
    - Active mode (sunrise window only): reads ONE recent frame from the currently-
      recording fragmented-MP4 via a read-only SHARED handle, copying out only
      COMPLETE moof+mdat fragments that end at/before a single snapshotted length.
      It NEVER lets ffmpeg open the growing file, NEVER opens RTSP/NVR streams, has a
      hard timeout, and on ANY uncertainty fails fast and falls back to the newest
      finished file.

.PARAMETER Mode
    Finished | Active | Auto.  Finished and Active are the real entry points and the
    scheduled tasks pass an explicit -Mode. Auto (manual use only) picks Active inside
    the sunrise window, else Finished.

.PARAMETER DryRun     Compute + print metrics, write a frame for flagged channels, but
                      send NO Slack and do NOT update state.
.PARAMETER TestSlack  Post a hello message to every configured destination, then exit.
.PARAMETER SelfTest   Run the metric + decision logic on synthetic in-memory bitmaps
                      (bright / black / gray). No disk, no ffmpeg, no Slack. Then exit.

.NOTES
    Slack credentials + thresholds live in -ConfigPath (default
    E:\recording_qc\overexposure.config.psd1), kept OUT of git. Exit codes:
    0 = ran (no flagged channels), 1 = at least one channel flagged, 2 = error.
#>

[CmdletBinding()]
param(
    [ValidateSet('Finished', 'Active', 'Auto')][string]$Mode = 'Auto',
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string[]]$Roots = @('E:\Reolink_record'),
    [string]$ReportRoot = 'E:\recording_qc\overexposure',
    [string]$FfmpegPath = 'E:\Reolink_record\bin\ffmpeg.exe',
    [string]$ActiveWindowStart = '08:00',
    [string]$ActiveWindowEnd = '09:00',
    [int]$ActiveTimeoutSec = 5,
    [switch]$DryRun,
    [switch]$TestSlack,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

# ============================ defaults (overridable in config) ============================
$Cfg = @{
    ExcludeDirs     = @('bin', 'logs')
    SatLuma         = 250      # a pixel with luma >= this counts as "saturated/clipped"
    DarkLuma        = 16       # a pixel with luma <= this counts as "black"
    SatRatioThresh  = 0.20     # overexposed if this fraction of pixels is saturated...
    MeanHighThresh  = 235      # ...or mean luma >= this
    DarkRatioThresh = 0.98     # near-black if this fraction of pixels is black...
    MeanLowThresh   = 12       # ...or mean luma <= this
    RealertHours    = 6        # while still flagged, re-alert at most this often
    SendRecovery    = $true    # send a one-line "cleared" note when a channel recovers
    UploadImage     = $false   # best-effort attach the frame to Slack (needs files:write)
    SlackBotToken   = $null
    SlackChannels   = @()
}
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $loaded = Import-PowerShellDataFile -LiteralPath $ConfigPath
        foreach ($k in $loaded.Keys) { $Cfg[$k] = $loaded[$k] }
        # Overexposure alerts may target a narrower destination list than the shared
        # one (disk-space warnings keep SlackChannels). Fall back if not set.
        if ($Cfg.OverexposureChannels) { $Cfg.SlackChannels = @($Cfg.OverexposureChannels) }
        Say "Loaded config: $ConfigPath" DarkGray
    } catch { Say "WARNING: could not read config $ConfigPath : $($_.Exception.Message)" Yellow }
} else {
    Say "No config at $ConfigPath (Slack disabled; QC + logging still run)." Yellow
}

# =========================================================================================
# Exposure metric (the core; takes a System.Drawing.Bitmap)
# =========================================================================================
function Measure-ExposureBitmap {
    param([System.Drawing.Bitmap]$Bmp)
    $rect = New-Object System.Drawing.Rectangle 0, 0, $Bmp.Width, $Bmp.Height
    $data = $Bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $stride = $data.Stride
        $buf = New-Object byte[] ($stride * $Bmp.Height)
        [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $buf.Length)
    } finally { $Bmp.UnlockBits($data) }

    $total = 0; $sat = 0; $dark = 0; [double]$sum = 0
    $satL = $Cfg.SatLuma; $darkL = $Cfg.DarkLuma
    for ($y = 0; $y -lt $Bmp.Height; $y++) {
        $row = $y * $stride
        for ($x = 0; $x -lt $Bmp.Width; $x++) {
            $i = $row + $x * 4                       # BGRA
            $l = 0.114 * $buf[$i] + 0.587 * $buf[$i + 1] + 0.299 * $buf[$i + 2]
            $sum += $l; $total++
            if ($l -ge $satL) { $sat++ }
            if ($l -le $darkL) { $dark++ }
        }
    }
    if ($total -eq 0) { $total = 1 }
    [pscustomobject]@{
        Mean     = [math]::Round($sum / $total, 1)
        SatRatio = [math]::Round($sat / $total, 4)
        DarkRatio = [math]::Round($dark / $total, 4)
        Width    = $Bmp.Width; Height = $Bmp.Height
    }
}

function Measure-ExposureFile {
    param([string]$Path)
    $bmp = New-Object System.Drawing.Bitmap $Path
    try { return Measure-ExposureBitmap $bmp } finally { $bmp.Dispose() }
}

function Get-ExposureStatus {
    param($M)
    $over  = ($M.SatRatio -ge $Cfg.SatRatioThresh) -or ($M.Mean -ge $Cfg.MeanHighThresh)
    $black = ($M.DarkRatio -ge $Cfg.DarkRatioThresh) -or ($M.Mean -le $Cfg.MeanLowThresh)
    if ($over) { return 'OVEREXPOSED' } elseif ($black) { return 'NEAR_BLACK' } else { return 'OK' }
}

# =========================================================================================
# SELF TEST  (no disk / ffmpeg / Slack)
# =========================================================================================
if ($SelfTest) {
    Add-Type -AssemblyName System.Drawing
    Say "=== SELF TEST (synthetic bitmaps; no disk, ffmpeg, or Slack) ===" Cyan
    function New-Fill([int]$v) {
        $b = New-Object System.Drawing.Bitmap 320, 180
        $g = [System.Drawing.Graphics]::FromImage($b)
        $g.Clear([System.Drawing.Color]::FromArgb($v, $v, $v)); $g.Dispose(); return $b
    }
    $cases = @{ 'bright(250)' = 250; 'black(2)' = 2; 'gray(128)' = 128 }
    $ok = $true
    foreach ($name in $cases.Keys) {
        $bmp = New-Fill $cases[$name]
        try { $m = Measure-ExposureBitmap $bmp } finally { $bmp.Dispose() }
        $st = Get-ExposureStatus $m
        $expect = switch ($cases[$name]) { 250 { 'OVEREXPOSED' } 2 { 'NEAR_BLACK' } default { 'OK' } }
        $pass = $st -eq $expect
        if (-not $pass) { $ok = $false }
        Say ("  {0,-12} mean={1,5} sat={2,6} dark={3,6} -> {4,-12} (expect {5}) {6}" -f `
            $name, $m.Mean, $m.SatRatio, $m.DarkRatio, $st, $expect, $(if ($pass) { 'OK' } else { 'FAIL' })) $(if ($pass) { 'Green' } else { 'Red' })
    }
    Say ("`nSELF TEST: {0}" -f $(if ($ok) { 'PASS' } else { 'FAIL' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

Add-Type -AssemblyName System.Drawing

# =========================================================================================
# ffmpeg
# =========================================================================================
$ff = if (Test-Path -LiteralPath $FfmpegPath) { $FfmpegPath }
      else { $c = Get-Command ffmpeg -EA SilentlyContinue; if ($c) { $c.Source } else { $null } }

function Invoke-FfmpegFirstFrame {
    param([string]$InPath, [string]$OutJpg, [int]$TimeoutSec = 20)
    if (-not $ff) { return $false }
    $args = @('-nostdin', '-loglevel', 'error', '-y', '-i', $InPath,
              '-frames:v', '1', '-vf', 'scale=320:-2', $OutJpg)
    $errF = [IO.Path]::GetTempFileName()
    try {
        Remove-Item -LiteralPath $OutJpg -Force -EA SilentlyContinue
        $p = Start-Process -FilePath $ff -ArgumentList $args -NoNewWindow -PassThru -RedirectStandardError $errF
        if (-not $p.WaitForExit($TimeoutSec * 1000)) { try { $p.Kill() } catch {}; return $false }
        # Success = ffmpeg produced a non-empty JPG. (Start-Process -PassThru does not
        # reliably surface ExitCode, so judge by the output, which ffmpeg only writes
        # on a successful single-frame decode.)
        return ((Test-Path -LiteralPath $OutJpg) -and ((Get-Item -LiteralPath $OutJpg).Length -gt 0))
    } catch { return $false } finally { Remove-Item $errF -Force -EA SilentlyContinue }
}

# =========================================================================================
# Fragmented-MP4 reader: build a tiny temp MP4 = init segment + ONE complete fragment,
# reading the source through a read-only SHARED handle. Used for BOTH finished files
# (static, safe) and active files (currently being written). Returns the temp path or
# $null. NEVER assumes EOF is a complete fragment; only copies moof+mdat pairs that end
# at/before the single snapshotted length.
# =========================================================================================
function Read-BoxHeader {
    param([System.IO.FileStream]$Fs, [long]$Limit)
    $pos = $Fs.Position
    if ($pos + 8 -gt $Limit) { return $null }
    $hb = New-Object byte[] 8
    if ($Fs.Read($hb, 0, 8) -lt 8) { return $null }
    [uint64]$size = ([uint64]$hb[0] -shl 24) -bor ([uint64]$hb[1] -shl 16) -bor ([uint64]$hb[2] -shl 8) -bor [uint64]$hb[3]
    $type = [System.Text.Encoding]::ASCII.GetString($hb, 4, 4)
    $hdr = 8
    if ($size -eq 1) {
        if ($pos + 16 -gt $Limit) { return $null }
        $lb = New-Object byte[] 8
        if ($Fs.Read($lb, 0, 8) -lt 8) { return $null }
        [uint64]$size = 0
        for ($k = 0; $k -lt 8; $k++) { $size = ($size -shl 8) -bor [uint64]$lb[$k] }
        $hdr = 16
    } elseif ($size -eq 0) {
        return [pscustomobject]@{ Type = $type; Start = $pos; Size = 0; End = $Limit; ToEof = $true }
    }
    [long]$end = $pos + [long]$size
    return [pscustomobject]@{ Type = $type; Start = $pos; Size = [long]$size; End = $end; ToEof = $false }
}

function Copy-Range {
    param([System.IO.FileStream]$Fs, [long]$Start, [long]$End, [System.IO.FileStream]$Out)
    $Fs.Position = $Start
    [long]$remaining = $End - $Start
    $buf = New-Object byte[] 1048576
    while ($remaining -gt 0) {
        $want = [int][math]::Min([long]$buf.Length, $remaining)
        $got = $Fs.Read($buf, 0, $want)
        if ($got -le 0) { break }
        $Out.Write($buf, 0, $got)
        $remaining -= $got
    }
}

function Build-FragmentClip {
    param([string]$Path, [string]$TempMp4, [bool]$PreferSecondLast)
    $fs = $null
    try {
        # read-only SHARED handle — identical to the recorder's Get-HandleLen pattern,
        # so we can never block or disturb the writer.
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        [long]$snap = $fs.Length          # the ONE trusted EOF for this whole operation

        # --- init segment: top-level boxes from 0 up to and including 'moov' ---
        $fs.Position = 0
        [long]$initEnd = -1
        while ($true) {
            $h = Read-BoxHeader -Fs $fs -Limit $snap
            if (-not $h -or $h.ToEof -or $h.End -gt $snap) { break }
            if ($h.Type -eq 'moov') { $initEnd = $h.End; break }
            $fs.Position = $h.End
        }
        if ($initEnd -lt 0) { return $null }   # no complete moov -> bail (fail fast)

        # --- collect COMPLETE moof+mdat fragments only ---
        $fs.Position = $initEnd
        $frags = New-Object System.Collections.Generic.List[object]
        while ($true) {
            $h = Read-BoxHeader -Fs $fs -Limit $snap
            if (-not $h -or $h.ToEof -or $h.End -gt $snap) { break }   # incomplete tail -> stop
            if ($h.Type -eq 'moof') {
                $moofStart = $h.Start
                $fs.Position = $h.End
                $h2 = Read-BoxHeader -Fs $fs -Limit $snap
                if (-not $h2 -or $h2.ToEof -or $h2.End -gt $snap) { break }   # mdat not fully written
                if ($h2.Type -eq 'mdat') {
                    $frags.Add([pscustomobject]@{ Start = $moofStart; End = $h2.End })
                }
                $fs.Position = $h2.End
            } else {
                $fs.Position = $h.End
            }
        }
        if ($frags.Count -lt 1) { return $null }

        $idx = if ($PreferSecondLast -and $frags.Count -ge 2) { $frags.Count - 2 } else { $frags.Count - 1 }
        $frag = $frags[$idx]

        $out = [System.IO.File]::Open($TempMp4, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
        try {
            Copy-Range -Fs $fs -Start 0 -End $initEnd -Out $out
            Copy-Range -Fs $fs -Start $frag.Start -End $frag.End -Out $out
        } finally { $out.Dispose() }
        return $TempMp4
    } catch {
        return $null
    } finally {
        if ($fs) { $fs.Dispose() }
    }
}

# Extract a recent frame from a recording file into $OutJpg. For both modes we go
# through the complete-fragment clip (fast + index-free); the only difference is which
# fragment we prefer and the hard timeout for the active path.
function Get-RecentFrame {
    param([string]$SourceFile, [string]$OutJpg, [bool]$Active)
    $tmp = Join-Path $ReportRoot ("_tmp_{0}.mp4" -f ([guid]::NewGuid().ToString('N')))
    $deadline = (Get-Date).AddSeconds($ActiveTimeoutSec)
    try {
        $clip = Build-FragmentClip -Path $SourceFile -TempMp4 $tmp -PreferSecondLast:$Active
        if ($Active -and (Get-Date) -gt $deadline) { return $false }   # bounded; fail fast
        if ($clip) {
            $to = if ($Active) { [int][math]::Max(2, ($deadline - (Get-Date)).TotalSeconds) } else { 20 }
            if (Invoke-FfmpegFirstFrame -InPath $clip -OutJpg $OutJpg -TimeoutSec $to) { return $true }
        }
        # finished files are static & safe -> a direct ffmpeg read is a fine fallback.
        if (-not $Active) { return (Invoke-FfmpegFirstFrame -InPath $SourceFile -OutJpg $OutJpg -TimeoutSec 25) }
        return $false
    } finally { Remove-Item -LiteralPath $tmp -Force -EA SilentlyContinue }
}

# =========================================================================================
# Slack
# =========================================================================================
function Resolve-SlackChannelId {
    param([string]$Token, [string]$Dest)
    if ($Dest -match '^[UW]') {
        try {
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                -Body (@{ users = $Dest } | ConvertTo-Json)
            if ($r.ok) { return $r.channel.id }
            Say "  conversations.open($Dest) failed: $($r.error)" Yellow; return $null
        } catch { Say "  conversations.open($Dest) error: $($_.Exception.Message)" Yellow; return $null }
    }
    return $Dest
}

function Send-SlackText {
    param([string]$Token, [string[]]$Dests, [string]$Text)
    $any = $false
    foreach ($d in $Dests) {
        $cid = Resolve-SlackChannelId -Token $Token -Dest $d
        if (-not $cid) { continue }
        try {
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                -Body (@{ channel = $cid; text = $Text } | ConvertTo-Json)
            if ($r.ok) { $any = $true } else { Say "  chat.postMessage($d) failed: $($r.error)" Yellow }
        } catch { Say "  chat.postMessage($d) error: $($_.Exception.Message)" Yellow }
    }
    return $any
}

# Best-effort image upload (Slack external-upload flow). Never throws.
function Send-SlackImage {
    param([string]$Token, [string[]]$Dests, [string]$ImagePath, [string]$Comment)
    if (-not $Cfg.UploadImage -or -not (Test-Path -LiteralPath $ImagePath)) { return $false }
    try {
        $len = (Get-Item -LiteralPath $ImagePath).Length
        $fn = Split-Path $ImagePath -Leaf
        $u = Invoke-RestMethod -Uri 'https://slack.com/api/files.getUploadURLExternal' -Method Post `
            -Headers @{ Authorization = "Bearer $Token" } `
            -Body @{ filename = $fn; length = $len }
        if (-not $u.ok) { Say "  getUploadURLExternal failed: $($u.error)" Yellow; return $false }
        Invoke-RestMethod -Uri $u.upload_url -Method Post -InFile $ImagePath -ContentType 'application/octet-stream' | Out-Null
        foreach ($d in $Dests) {
            $cid = Resolve-SlackChannelId -Token $Token -Dest $d
            if (-not $cid) { continue }
            $body = @{ files = @(@{ id = $u.file_id; title = $fn }); channel_id = $cid; initial_comment = $Comment } | ConvertTo-Json -Depth 5
            Invoke-RestMethod -Uri 'https://slack.com/api/files.completeUploadExternal' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' -Body $body | Out-Null
        }
        return $true
    } catch { Say "  image upload error: $($_.Exception.Message)" Yellow; return $false }
}

# =========================================================================================
# TEST SLACK
# =========================================================================================
if ($TestSlack) {
    if (-not $Cfg.SlackBotToken -or $Cfg.SlackChannels.Count -eq 0) {
        Say "TestSlack: set SlackBotToken and SlackChannels in $ConfigPath first." Red; exit 2
    }
    $ok = Send-SlackText -Token $Cfg.SlackBotToken -Dests $Cfg.SlackChannels `
        -Text (":white_check_mark: Overexposure QC test message ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered to at least one destination' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# =========================================================================================
# MAIN
# =========================================================================================
# resolve mode
$winS = [datetime]::ParseExact($ActiveWindowStart, 'HH:mm', $null).TimeOfDay
$winE = [datetime]::ParseExact($ActiveWindowEnd, 'HH:mm', $null).TimeOfDay
$nowTod = (Get-Date).TimeOfDay
$effMode = switch ($Mode) {
    'Finished' { 'Finished' }
    'Active'   { 'Active' }
    default    { if ($nowTod -ge $winS -and $nowTod -lt $winE) { 'Active' } else { 'Finished' } }
}
$useActive = ($effMode -eq 'Active')

New-Item -ItemType Directory -Force -Path $ReportRoot | Out-Null
$statePath = Join-Path $ReportRoot 'state.json'
$state = @{}
if (Test-Path -LiteralPath $statePath) {
    try { (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $state[$_.Name] = $_.Value } } catch {}
}

Say ("Overexposure QC  mode=$effMode  roots=$($Roots -join ',')  $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))") Cyan
if (-not $ff) { Say "ERROR: ffmpeg not found ($FfmpegPath or PATH)." Red; exit 2 }

# discover channel folders
$dirs = @()
foreach ($root in $Roots) {
    if (-not (Test-Path $root)) { Say "WARNING: root missing: $root" Yellow; continue }
    $dirs += Get-ChildItem $root -Directory -EA SilentlyContinue | Where-Object { $Cfg.ExcludeDirs -notcontains $_.Name }
}
if ($dirs.Count -eq 0) { Say "No channel folders under $($Roots -join ', ')." Red; exit 2 }

$logJson = Join-Path $ReportRoot 'overexposure_log.json'
$logTxt  = Join-Path $ReportRoot 'overexposure_log.txt'
$rows = New-Object System.Collections.Generic.List[object]
$flagged = 0
$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$fstamp = (Get-Date).ToString('yyyyMMdd_HHmmss')

foreach ($dir in $dirs) {
    $ch = $dir.Name
    $files = Get-ChildItem $dir.FullName -File -Filter '*.mp4' -EA SilentlyContinue | Sort-Object Name -Descending
    $finished = $files | Where-Object { $_.BaseName -like '*_to_*' } | Select-Object -First 1
    $active   = $files | Where-Object { $_.BaseName -notlike '*_to_*' } | Select-Object -First 1

    $srcFile = $null; $srcKind = $null
    $jpg = Join-Path $ReportRoot ("_frame_{0}.jpg" -f $ch)
    Remove-Item -LiteralPath $jpg -Force -EA SilentlyContinue

    $gotFrame = $false
    if ($useActive -and $active) {
        $srcFile = $active.FullName; $srcKind = 'active'
        $gotFrame = Get-RecentFrame -SourceFile $active.FullName -OutJpg $jpg -Active $true
        if (-not $gotFrame -and $finished) {
            Say "  $ch active read failed/uncertain -> fallback to finished file" DarkYellow
            $srcFile = $finished.FullName; $srcKind = 'finished(fallback)'
            $gotFrame = Get-RecentFrame -SourceFile $finished.FullName -OutJpg $jpg -Active $false
        }
    } elseif ($finished) {
        $srcFile = $finished.FullName; $srcKind = 'finished'
        $gotFrame = Get-RecentFrame -SourceFile $finished.FullName -OutJpg $jpg -Active $false
    } elseif ($active -and -not $useActive) {
        # no finished file yet (e.g. first hour) and we're not allowed active -> skip
        Say "  $ch : no finished file yet; skipping (finished mode)" DarkGray
    }

    if (-not $gotFrame) {
        Say ("  {0,-8} no frame ({1}) - skipped" -f $ch, $(if ($srcKind) { $srcKind } else { 'no source' })) Yellow
        $rows.Add([pscustomobject]@{ time = $stamp; channel = $ch; mode = $effMode; source_kind = $srcKind; source_file = $srcFile; status = 'NO_FRAME'; mean = $null; sat_ratio = $null; dark_ratio = $null })
        continue
    }

    $m = Measure-ExposureFile -Path $jpg
    $status = Get-ExposureStatus $m
    $col = switch ($status) { 'OVEREXPOSED' { 'Red' } 'NEAR_BLACK' { 'Magenta' } default { 'Green' } }
    Say ("  {0,-8} {1,-12} mean={2,5}  sat={3,6:p1}  dark={4,6:p1}  [{5}]" -f $ch, $status, $m.Mean, $m.SatRatio, $m.DarkRatio, $srcKind) $col

    $savedJpg = $null
    if ($status -ne 'OK') {
        $flagged++
        $savedJpg = Join-Path $ReportRoot ("{0}_{1}_{2}.jpg" -f $ch, $fstamp, $status)
        Copy-Item -LiteralPath $jpg -Destination $savedJpg -Force -EA SilentlyContinue
    }
    Remove-Item -LiteralPath $jpg -Force -EA SilentlyContinue

    $rows.Add([pscustomobject]@{
        time = $stamp; channel = $ch; mode = $effMode; source_kind = $srcKind
        source_file = $srcFile; status = $status
        mean = $m.Mean; sat_ratio = $m.SatRatio; dark_ratio = $m.DarkRatio; frame = $savedJpg
    })

    # ---- alert decision (skip in DryRun) ----
    if ($DryRun) { continue }
    $prev = if ($state.ContainsKey($ch)) { $state[$ch] } else { $null }
    $prevStatus = if ($prev) { $prev.status } else { 'OK' }
    $lastAlert  = if ($prev -and $prev.lastAlert) { [datetime]$prev.lastAlert } else { $null }

    if ($status -ne 'OK') {
        $due = (-not $lastAlert) -or (((Get-Date) - $lastAlert).TotalHours -ge $Cfg.RealertHours)
        if (($prevStatus -ne $status) -or $due) {
            $note = if ($useActive) { 'sunrise active sample' } else { 'hourly check' }
            $msg = ":warning: *{0} {1}* - saturated {2:p0} of pixels, mean luma {3} ({4}, {5})" -f `
                $ch, $status, $m.SatRatio, $m.Mean, (Get-Date).ToString('HH:mm'), $note
            if ($Cfg.SlackBotToken -and $Cfg.SlackChannels.Count -gt 0) {
                [void](Send-SlackText -Token $Cfg.SlackBotToken -Dests $Cfg.SlackChannels -Text $msg)
                [void](Send-SlackImage -Token $Cfg.SlackBotToken -Dests $Cfg.SlackChannels -ImagePath $savedJpg -Comment $msg)
            } else { Say "  (no Slack creds; would have alerted: $msg)" DarkYellow }
            $state[$ch] = @{ status = $status; lastAlert = (Get-Date).ToString('o') }
        } else {
            $state[$ch] = @{ status = $status; lastAlert = $(if ($lastAlert) { $lastAlert.ToString('o') } else { (Get-Date).ToString('o') }) }
        }
    } else {
        if ($prevStatus -ne 'OK' -and $Cfg.SendRecovery -and $Cfg.SlackBotToken -and $Cfg.SlackChannels.Count -gt 0) {
            [void](Send-SlackText -Token $Cfg.SlackBotToken -Dests $Cfg.SlackChannels `
                -Text (":white_check_mark: {0} exposure back to normal (mean luma {1}, {2})." -f $ch, $m.Mean, (Get-Date).ToString('HH:mm')))
        }
        $state[$ch] = @{ status = 'OK'; lastAlert = $null }
    }
}

# ---- persist log + state ----
if (-not $DryRun) {
    foreach ($r in $rows) {
        Add-Content -LiteralPath $logTxt -Encoding UTF8 -Value ("{0}  {1,-8} {2,-12} mode={3} mean={4} sat={5} dark={6} kind={7}" -f `
            $r.time, $r.channel, $r.status, $r.mode, $r.mean, $r.sat_ratio, $r.dark_ratio, $r.source_kind)
    }
    $existing = @()
    if (Test-Path -LiteralPath $logJson) { try { $raw = Get-Content -LiteralPath $logJson -Raw; if ($raw.Trim()) { $existing = @($raw | ConvertFrom-Json) } } catch {} }
    ($existing + $rows) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $logJson -Encoding UTF8
    ($state | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $statePath -Encoding UTF8
}

Say ("`nDone. channels={0}  flagged={1}  mode={2}{3}" -f $dirs.Count, $flagged, $effMode, $(if ($DryRun) { '  (DRY RUN - no Slack, no state/log writes)' } else { '' })) Cyan
exit $(if ($flagged -gt 0) { 1 } else { 0 })
