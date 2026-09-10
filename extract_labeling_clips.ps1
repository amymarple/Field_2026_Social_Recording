<#
.SYNOPSIS
    Cut keyframe-aligned, full-resolution, stream-copied clips (+ manifest.json) from a CLOSED
    recording segment for the IR identity labeler (ir_identity_labeler.html).

.DESCRIPTION
    For each centre time you give, the clip starts at the last keyframe <= centre - LeadSeconds and
    runs ClipSeconds. No re-encode (-c copy), so the CPU cost is a few seconds per clip and the frames
    are the recorder's own. The manifest carries the exact keyframe start of every clip, so the
    labeler shows wall-clock time to the frame.

    LIVE-SYSTEM RULES (enforced here, in addition to the repo hook):
      - the source must be a CLOSED segment: its name must contain '_to_' (the filename contract);
      - a copy under D:\ is preferred; a closed segment under E:\Reolink_record is accepted (that is a
        read of a finished file) but the recorders are checked first (check_recording.ps1) and the
        clip is a single short stream copy, never a decode of the whole hour;
      - nothing is ever written next to the source; output goes to -OutDir.

.EXAMPLE
    .\extract_labeling_clips.ps1 -Source 'D:\07_08_camera\CH07_2026-09-05_08-00-00_to_09-00-00.mp4' `
        -Centres '08:04:44=still_A','08:11:10=still_B','08:45:42=round_start' `
        -OutDir 'D:\07_08_camera\pilot_CH07_2026-09-05_08h\clips_fullres'
    Centre times are wall-clock HH:MM:SS (the segment's hour is read from its file name); an optional
    '=moment' names the clip.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string[]]$Centres,
    [Parameter(Mandatory)][string]$OutDir,
    [double]$LeadSeconds = 11,
    [double]$ClipSeconds = 22,
    [string]$Ffmpeg = 'ffmpeg',
    [string]$Ffprobe = 'ffprobe',
    [switch]$SkipRecorderCheck
)
$ErrorActionPreference = 'Stop'

# ---- guards ---------------------------------------------------------------------------
$name = [IO.Path]::GetFileName($Source)
if ($name -notmatch '_to_') { throw "Refusing: '$name' has no '_to_' in its name = possibly still being written. Use a closed segment." }
if ($Source -match '(?i)Wiser[\\/]+data') { throw 'Refusing: the live WISER DB is never read.' }
if (-not (Test-Path -LiteralPath $Source)) { throw "Source not found: $Source" }
if ($name -notmatch '^(?<cam>[A-Za-z0-9]+)_(?<date>\d{4}-\d{2}-\d{2})_(?<h>\d{2})-(?<m>\d{2})-(?<s>\d{2})_to_') { throw "Cannot parse camera/date/start from '$name'" }
$cam = $Matches.cam; $date = $Matches.date
$segStart = [datetime]::ParseExact("$date $($Matches.h):$($Matches.m):$($Matches.s)", 'yyyy-MM-dd HH:mm:ss', $null)

if (-not $SkipRecorderCheck) {
    $chk = Join-Path $PSScriptRoot 'check_recording.ps1'
    if (Test-Path -LiteralPath $chk) {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $chk 2>&1 | Out-String
        $growing = ([regex]::Matches($out, 'GROWING')).Count
        Write-Host ("recorder check: {0} channels GROWING" -f $growing) -ForegroundColor $(if ($growing -ge 6) { 'Green' } else { 'Yellow' })
        if ($growing -lt 6) { Write-Host $out; throw 'Recorders are not all growing - not touching anything now.' }
    }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ---- keyframe table (demux only, no decode) --------------------------------------------
Write-Host "reading keyframe timestamps (packet scan, no decode)..." -ForegroundColor Cyan
$pkts = & $Ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 $Source 2>$null
$kf = @()
foreach ($line in $pkts) { $p = $line -split ','; if ($p.Count -ge 2 -and $p[1] -match 'K') { $kf += [double]$p[0] } }
if ($kf.Count -eq 0) { throw 'No keyframes found - is this an H.264 mp4?' }
$fps = & $Ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 $Source 2>$null
$fpsNum = 20.0; if ($fps -match '^(\d+)/(\d+)$') { $fpsNum = [double]$Matches[1] / [double]$Matches[2] }
$dims = (& $Ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 $Source 2>$null) -split ','
Write-Host ("{0} keyframes, {1:F2} fps, {2}x{3}" -f $kf.Count, $fpsNum, $dims[0], $dims[1])

# ---- clips ----------------------------------------------------------------------------
$clips = @()
foreach ($c in $Centres) {
    $parts = $c -split '=', 2
    $ct = [datetime]::ParseExact("$date $($parts[0])", 'yyyy-MM-dd HH:mm:ss', $null)
    $moment = if ($parts.Count -eq 2) { $parts[1] } else { $ct.ToString('HH-mm-ss') }
    $centreSec = ($ct - $segStart).TotalSeconds
    if ($centreSec -lt 0 -or $centreSec -gt 3700) { throw "Centre $($parts[0]) is not inside segment $name" }
    $target = $centreSec - $LeadSeconds
    $start = ($kf | Where-Object { $_ -le $target } | Select-Object -Last 1); if ($null -eq $start) { $start = $kf[0] }
    $absStart = $segStart.AddSeconds($start)
    $file = ('{0}_{1}_{2}_to_{3}.mp4' -f $cam, $moment, $absStart.ToString('HH-mm-ss'), $absStart.AddSeconds($ClipSeconds).ToString('HH-mm-ss'))
    $outPath = Join-Path $OutDir $file
    & $Ffmpeg -v error -threads 1 -ss $start -i $Source -t $ClipSeconds -c:v copy -an -avoid_negative_ts make_zero -movflags +faststart -y $outPath
    $dur = [double](& $Ffprobe -v error -show_entries format=duration -of csv=p=0 $outPath 2>$null)
    $clips += [ordered]@{ file = $file; moment = $moment; centre_s = [math]::Round($centreSec, 3); abs_start_s = [math]::Round($start, 3)
                          abs_start_local = $absStart.ToString('HH:mm:ss.ff'); duration_s = [math]::Round($dur, 3); why = '' }
    Write-Host ("  {0}: start {1} ({2:F3} s into the segment), {3:F1} s, {4:F1} MB" -f $moment, $absStart.ToString('HH:mm:ss'), $start, $dur, ((Get-Item $outPath).Length / 1MB))
}
$manifest = [ordered]@{ source = $Source; camera = $cam; segment_start_local = $segStart.ToString('yyyy-MM-ddTHH:mm:ss'); fps = [math]::Round($fpsNum, 3)
                        width = [int]$dims[0]; height = [int]$dims[1]; clips = $clips }
[IO.File]::WriteAllText((Join-Path $OutDir 'manifest.json'), ($manifest | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))   # no BOM
$lab = Join-Path $PSScriptRoot 'ir_identity_labeler.html'
if (Test-Path -LiteralPath $lab) { Copy-Item -LiteralPath $lab -Destination (Join-Path $OutDir 'ir_identity_labeler.html') -Force }
Write-Host ("manifest.json + labeler written to {0}; open ir_identity_labeler.html and pick that folder" -f $OutDir) -ForegroundColor Green
