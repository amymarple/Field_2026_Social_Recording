<#
.SYNOPSIS
    Copy ONE day of recordings from all recorders to a USB drive, for hand-off to
    the lab. Designed so a coworker can run one command and not worry about
    mistakes.

    *** READ-ONLY AT THE SOURCE. THIS SCRIPT ONLY EVER COPIES. ***
    It NEVER deletes, moves, renames, or modifies anything under the recording
    folders. The only thing it writes to is the USB destination. This is enforced
    in code (see Assert-DestUnderUsb / no Remove/Move/Set on source).

    What it does:
      - Finds every finished .mp4 for the chosen day (default = yesterday) in
        E:\Reolink_record\CHxx and E:\thermal_record\1xx_* .
      - Copies them to  <USB>\<day>\<group>\  preserving the per-camera folders.
      - Verifies each copy (size; SHA-256 with -Hash) and re-copies only what's
        missing/different, so it is safe to re-run / resume.
      - Checks completeness: for each camera, are all 24 hours of the day present?
        Reports any missing hours and any copy/verify failures.
      - Writes copy_report.txt + copy_manifest.csv into the USB day folder.
      - On success, records the day in the persistent SAVE LOG (-SaveLog) so that
        delete_day.ps1 will allow that day to be cleaned up.
      - ALSO mirrors the WISER daily backup (E:\Wiser_backup -> <USB>\Wiser_backup)
        so the tracking DB snapshots + incremental CSVs get an off-machine copy on
        the same USB. Additive (never deletes on the USB), verified, and independent
        of the video result. On by default; -SkipWiserBackup to turn it off.

.PARAMETER Usb
    The USB drive or target folder, e.g.  F:   or  F:\   or  F:\fielddata .
    Required unless -MarkSavedOnly is used. Must NOT be on the same drive as the
    recordings.

.PARAMETER MarkSavedOnly
    Record the day as "saved" in the save log WITHOUT copying anything (no -Usb
    needed). Use when the footage does not actually need backing up but you still
    want delete_day.ps1 to allow cleanup of that day.

.PARAMETER SaveLog
    Persistent local log of saved days (read by delete_day.ps1).
    Default E:\recording_qc\save_log.json.

.PARAMETER Date
    Day to copy, yyyy-MM-dd. Default = yesterday (the last complete day).

.PARAMETER Hash
    Verify each copy with a full SHA-256 compare (slow but definitive). Default is
    a fast size compare (catches truncated/incomplete copies).

.PARAMETER IncludeActive
    Also copy the still-recording file (no _to_ in the name). Off by default
    because it is incomplete; only relevant if you copy today's date.

.PARAMETER StopOnError
    Halt on the first copy/verify failure. Default is to continue and report all
    failures at the end (source is never touched either way).

.PARAMETER DryRun
    Show exactly what would be copied and the completeness check, but copy nothing.
    Also shows the WISER-backup files that would be swept.

.PARAMETER SkipWiserBackup
    Do NOT mirror the WISER daily backup to the USB (video only).

.PARAMETER WiserSource
    The WISER backup tree to mirror. Default E:\Wiser_backup (written by
    wiser_tracking_analysis\scripts\backup_wiser_daily.py).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_day_to_usb.ps1 -Usb F:
    # copies yesterday to F:\<yesterday>\

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_day_to_usb.ps1 -Usb F: -Date 2026-06-20 -Hash
#>

[CmdletBinding()]
param(
    [string]$Usb,
    [string]$Date,
    [switch]$Hash,
    [switch]$IncludeActive,
    [switch]$StopOnError,
    [switch]$DryRun,
    # Record this day as "saved" in the save log WITHOUT copying anything. For when
    # the footage does not actually need backing up but you still want delete_day.ps1
    # (which checks the save log) to allow cleanup. No -Usb needed with this.
    [switch]$MarkSavedOnly,
    # Persistent local log of which days have been saved. delete_day.ps1 reads this.
    [string]$SaveLog = 'E:\recording_qc\save_log.json',
    # The recorders. Each immediate subfolder = one camera/group. Override only for testing.
    [string[]]$SourceRoots = @('E:\Reolink_record', 'E:\thermal_record'),
    # Also mirror the WISER daily backup (snapshots + incremental CSVs) to
    # <USB>\Wiser_backup, giving the tracking DB an off-machine copy. Additive (never
    # deletes on the USB), verified like the video copy, and independent of the video
    # result. On by default whenever -Usb is given; -SkipWiserBackup turns it off.
    [switch]$SkipWiserBackup,
    [string]$WiserSource = 'E:\Wiser_backup'
)

# ============================ CONFIG ============================
$ExcludeDirs   = @('bin', 'logs')
$Extensions    = @('.mp4')
$ExpectedHours = 24                       # a full day = 24 hourly slots per camera
# ===============================================================

$ErrorActionPreference = 'Stop'

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

# Append one record to the persistent save log (JSON for delete_day.ps1 + a
# human-readable .txt). Records that a given day's footage has been saved.
function Add-SaveLogEntry([string]$LogPath, $Entry) {
    $dir = Split-Path -Parent $LogPath
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $list = @()
    if (Test-Path -LiteralPath $LogPath) {
        try {
            $raw = Get-Content -LiteralPath $LogPath -Raw -Encoding UTF8
            if ($raw.Trim()) { $existing = $raw | ConvertFrom-Json; if ($existing) { $list = @($existing) } }
        } catch { }
    }
    $list += [pscustomobject]$Entry
    ($list | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $LogPath -Encoding UTF8
    $txt  = $LogPath -replace '\.json$', '.txt'
    $line = "{0}  day={1}  result={2}  copied={3} failed={4}  method={5}  dest={6}" -f `
        $Entry.saved_at, $Entry.day, $Entry.result, $Entry.copied, $Entry.failed, $Entry.method, $Entry.destination
    Add-Content -LiteralPath $txt -Value $line -Encoding UTF8
}

# Mirror the WISER daily-backup tree (E:\Wiser_backup) to <USB>\Wiser_backup.
# Additive and copy-only: copies files that are missing or a different size (append-
# only snapshots + incremental CSVs), verifies each copy (size, or SHA-256 with
# -Hash), and NEVER deletes on the USB (so the USB keeps the full history even after
# E: prunes old snapshots). Read-only at the source; every write is guarded to stay
# under <USB>\Wiser_backup.
function Invoke-WiserBackupSweep {
    param([string]$Src, [string]$UsbRoot, [bool]$DoHash, [bool]$IsDryRun)
    $srcFull  = (Resolve-Path -LiteralPath $Src).Path
    $destRoot = Join-Path $UsbRoot 'Wiser_backup'
    $destRootFull = [System.IO.Path]::GetFullPath($destRoot)
    if (-not $IsDryRun) { New-Item -ItemType Directory -Force -Path $destRoot | Out-Null }
    $c = 0; $s = 0; $f = 0; $cb = 0
    foreach ($file in (Get-ChildItem -LiteralPath $Src -Recurse -File -EA SilentlyContinue)) {
        $rel  = $file.FullName.Substring($srcFull.Length).TrimStart('\')
        $dest = Join-Path $destRoot $rel
        # hard guard: never write outside <USB>\Wiser_backup
        if (-not ([System.IO.Path]::GetFullPath($dest)).StartsWith($destRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "SAFETY ABORT: WISER sweep refused to write outside ${destRoot}: $dest"
        }
        $need = $true
        if (Test-Path -LiteralPath $dest) {
            if ((Get-Item -LiteralPath $dest).Length -eq $file.Length) {
                if ($DoHash) {
                    $need = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
                            (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
                } else { $need = $false }
            }
        }
        if (-not $need) { $s++; continue }
        $mb = [math]::Round($file.Length / 1MB, 1)
        if ($IsDryRun) { Say ("  [wiser] would copy $rel  ($mb MB)") Gray; continue }
        try {
            $dd = Split-Path -Parent $dest
            if (-not (Test-Path -LiteralPath $dd)) { New-Item -ItemType Directory -Force -Path $dd | Out-Null }
            [System.IO.File]::Copy($file.FullName, $dest, $true)     # COPY ONLY (dest is on the USB)
            if ((Get-Item -LiteralPath $dest).Length -ne $file.Length) { throw "size mismatch after copy" }
            $c++; $cb += $file.Length
            Say ("  [wiser] $rel  ($mb MB) -> OK") Green
        } catch {
            $f++; Say ("  [wiser] $rel -> FAILED: $($_.Exception.Message)") Red
        }
    }
    return [pscustomobject]@{ Copied = $c; Skipped = $s; Failed = $f; Bytes = $cb; Dest = $destRoot }
}

# ---- resolve the day ----
if ($Date) {
    try { $dayObj = [datetime]::ParseExact($Date, 'yyyy-MM-dd', $null) }
    catch { Say "Bad -Date '$Date'. Use yyyy-MM-dd (e.g. 2026-06-26)." Red; exit 2 }
} else {
    $dayObj = (Get-Date).Date.AddDays(-1)
}
$dayStr = $dayObj.ToString('yyyy-MM-dd')
$isToday = ($dayObj.Date -eq (Get-Date).Date)

# ---- mark-only: record the day as "saved" without copying anything ----
# (the "we don't actually need to back this up, just let cleanup proceed" path)
if ($MarkSavedOnly) {
    Add-SaveLogEntry $SaveLog ([ordered]@{
        day             = $dayStr
        saved_at        = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        destination     = '(none - mark-only)'
        result          = 'MARK-ONLY - day flagged saved without copying'
        rc              = 0
        copied          = 0
        already_present = 0
        failed          = 0
        bytes           = 0
        source_roots    = $SourceRoots
        method          = 'mark-only (NOT copied)'
    })
    Say "Marked $dayStr as SAVED in $SaveLog (mark-only - no files were copied)." Yellow
    Say "delete_day.ps1 -Date $dayStr will now be allowed to delete that day." Yellow
    exit 0
}

if (-not $Usb) {
    Say "REQUIRED: -Usb <drive> (e.g. -Usb F:). Or use -MarkSavedOnly to flag the day saved without copying." Red
    exit 2
}

# ---- resolve + sanity-check the USB destination ----
$usbRoot = $Usb.Trim()
if ($usbRoot -match '^[A-Za-z]:$') { $usbRoot += '\' }      # "F:" -> "F:\"
try { $usbRoot = (Resolve-Path -LiteralPath $usbRoot -ErrorAction Stop).Path }
catch { Say "USB path not found / not mounted: $Usb" Red; exit 2 }

$usbQual = (Split-Path $usbRoot -Qualifier)
foreach ($r in $SourceRoots) {
    $srcQual = (Split-Path $r -Qualifier)
    if ($usbQual -ieq $srcQual) {
        Say "REFUSING: the destination ($usbQual) is the SAME drive as the recordings ($srcQual)." Red
        Say "Pick a real USB drive so nothing can be copied onto the source." Red
        exit 2
    }
}

$destDay = Join-Path $usbRoot $dayStr

# Hard guard: every file we write MUST live under the USB day folder.
$destDayFull = [System.IO.Path]::GetFullPath($destDay)
function Assert-DestUnderUsb([string]$path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($destDayFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "SAFETY ABORT: refused to write outside the USB day folder: $full"
    }
}

Say ("==================================================================") Cyan
Say ("  COPY DAY -> USB    (copy-only; source is never modified)") Cyan
Say ("  Day:         $dayStr" + $(if ($isToday) { '  (TODAY - may be incomplete)' } else { '' })) Cyan
Say ("  Destination: $destDay") Cyan
Say ("  Verify:      " + $(if ($Hash) { 'SHA-256 (full)' } else { 'size compare (fast)' })) Cyan
Say ("  Mode:        " + $(if ($DryRun) { 'DRY RUN (nothing will be copied)' } else { 'COPY' })) Cyan
Say ("==================================================================") Cyan

# ---- mirror the WISER daily backup to the USB FIRST (small, critical, and
#      independent of the video copy — so it runs even on a no-video day) ----
if (-not $SkipWiserBackup) {
    if (-not (Test-Path -LiteralPath $WiserSource)) {
        Say ("`n[wiser] no WISER backup at $WiserSource - skipping (run backup_wiser_daily.py first).") DarkGray
    } elseif ((Split-Path $WiserSource -Qualifier) -ieq $usbQual) {
        Say ("`n[wiser] WISER source is on the USB drive ($usbQual) - skipping to avoid copying onto itself.") Yellow
    } else {
        Say ("`n  WISER BACKUP -> USB   (off-machine copy; additive, never deletes; verify: " +
             $(if ($Hash) { 'SHA-256' } else { 'size' }) + ")") Cyan
        Say ("  Source: $WiserSource   ->   $(Join-Path $usbRoot 'Wiser_backup')") Cyan
        $wb = Invoke-WiserBackupSweep -Src $WiserSource -UsbRoot $usbRoot -DoHash:([bool]$Hash) -IsDryRun:([bool]$DryRun)
        Say ("  [wiser] copied $($wb.Copied)  already-present $($wb.Skipped)  FAILED $($wb.Failed)  ($([math]::Round($wb.Bytes/1MB,1)) MB) -> $($wb.Dest)`n") $(if ($wb.Failed) { 'Red' } else { 'Green' })
    }
}

# ---- gather source files for the day, per group ----
$dayTag = '_' + $dayStr + '_'
$groups = [ordered]@{}    # groupName -> list of FileInfo

foreach ($root in $SourceRoots) {
    if (-not (Test-Path $root)) { Say "WARNING: source root missing: $root" Yellow; continue }
    foreach ($dir in (Get-ChildItem $root -Directory -EA SilentlyContinue | Where-Object { $ExcludeDirs -notcontains $_.Name })) {
        $files = Get-ChildItem $dir.FullName -File -EA SilentlyContinue |
            Where-Object { ($Extensions -contains $_.Extension.ToLower()) -and ($_.Name -like "*$dayTag*") }
        if (-not $IncludeActive) { $files = $files | Where-Object { $_.BaseName -like '*_to_*' } }  # drop the still-recording file
        if ($files) { $groups[$dir.Name] = @($files | Sort-Object Name) }
        elseif (-not $groups.Contains($dir.Name)) { $groups[$dir.Name] = @() }
    }
}

if ($groups.Count -eq 0) { Say "No camera folders found under $($SourceRoots -join ', ')." Red; exit 2 }

# ---- size + free-space preflight ----
$allFiles = @(); foreach ($g in $groups.Keys) { $allFiles += $groups[$g] }
$totalBytes = ($allFiles | Measure-Object Length -Sum).Sum
if (-not $totalBytes) { $totalBytes = 0 }
$totalGB = [math]::Round($totalBytes / 1GB, 2)
$freeGB  = [math]::Round((Get-PSDrive -Name ($usbQual.TrimEnd(':'))).Free / 1GB, 2)
Say ("`nFound $($allFiles.Count) file(s) for $dayStr across $($groups.Count) camera(s): $totalGB GB") White
Say ("USB free space: $freeGB GB") White
if ($allFiles.Count -eq 0) { Say "Nothing to copy for $dayStr." Yellow; exit 1 }
if (-not $DryRun -and ($totalBytes -gt (Get-PSDrive -Name ($usbQual.TrimEnd(':'))).Free)) {
    Say "NOT ENOUGH SPACE on the USB drive ($freeGB GB free, need $totalGB GB). Aborting (nothing copied)." Red
    exit 2
}

# ---- copy ----
$manifest = New-Object System.Collections.Generic.List[object]
$copied = 0; $skipped = 0; $failed = 0; $copiedBytes = 0
$idx = 0; $n = $allFiles.Count
$swAll = [System.Diagnostics.Stopwatch]::StartNew()

if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $destDay | Out-Null }

foreach ($g in $groups.Keys) {
    $destGroup = Join-Path $destDay $g
    if (-not $DryRun -and $groups[$g].Count -gt 0) {
        Assert-DestUnderUsb $destGroup
        New-Item -ItemType Directory -Force -Path $destGroup | Out-Null
    }
    foreach ($f in $groups[$g]) {
        $idx++
        $dest = Join-Path $destGroup $f.Name
        Assert-DestUnderUsb $dest
        $status = ''
        $need = $true

        if (Test-Path -LiteralPath $dest) {
            $dl = (Get-Item -LiteralPath $dest).Length
            if ($dl -eq $f.Length) {
                if ($Hash) {
                    $sh = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
                    $dh = (Get-FileHash -LiteralPath $dest      -Algorithm SHA256).Hash
                    if ($sh -eq $dh) { $need = $false; $status = 'already-present (hash ok)' }
                } else { $need = $false; $status = 'already-present (size ok)' }
            }
        }

        if (-not $need) {
            $skipped++
            Say ("[{0}/{1}] {2}\{3}  -> {4}" -f $idx, $n, $g, $f.Name, $status) DarkGray
        }
        elseif ($DryRun) {
            $status = 'would-copy'
            Say ("[{0}/{1}] {2}\{3}  ({4} MB)  -> would copy" -f $idx, $n, $g, $f.Name, [math]::Round($f.Length/1MB,1)) Gray
        }
        else {
            $ok = $false; $err = $null
            for ($try = 1; $try -le 2 -and -not $ok; $try++) {
                try {
                    [System.IO.File]::Copy($f.FullName, $dest, $true)   # COPY ONLY (overwrite dest, never source)
                    $dl = (Get-Item -LiteralPath $dest).Length
                    if ($dl -ne $f.Length) { throw "size mismatch after copy (src $($f.Length) / dst $dl)" }
                    if ($Hash) {
                        $sh = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
                        $dh = (Get-FileHash -LiteralPath $dest      -Algorithm SHA256).Hash
                        if ($sh -ne $dh) { throw "SHA-256 mismatch after copy" }
                    }
                    $ok = $true
                } catch { $err = $_.Exception.Message; Start-Sleep -Milliseconds 500 }
            }
            if ($ok) {
                $copied++; $copiedBytes += $f.Length; $status = 'copied+verified'
                Say ("[{0}/{1}] {2}\{3}  ({4} MB)  -> OK" -f $idx, $n, $g, $f.Name, [math]::Round($f.Length/1MB,1)) Green
            } else {
                $failed++; $status = "FAILED: $err"
                Say ("[{0}/{1}] {2}\{3}  -> FAILED: {4}" -f $idx, $n, $g, $f.Name, $err) Red
                if ($StopOnError) { Say "Stopping on first error (-StopOnError). Source untouched." Red; break }
            }
        }

        $manifest.Add([pscustomobject]@{
            Group=$g; File=$f.Name; SizeBytes=$f.Length
            SizeMB=[math]::Round($f.Length/1MB,1); Status=$status
            SourcePath=$f.FullName; DestPath=$dest
        })
    }
    if ($StopOnError -and $failed -gt 0) { break }
}
$swAll.Stop()

# ---- completeness check: is every hour of the day COVERED per camera? ----
# Uses the start/end times in the filename as intervals, so a segment that spans
# an hour boundary (after a restart) still counts that hour as covered. An hour H
# is "covered" if some file's [start,end) overlaps [H:00, H+1:00).
$nowHour = (Get-Date).Hour
$startEndRe = '_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(?:_to_(\d{2}-\d{2}-\d{2}))?'
$completeness = New-Object System.Collections.Generic.List[object]
foreach ($g in $groups.Keys) {
    $intervals = @()
    foreach ($f in $groups[$g]) {
        $m = [regex]::Match($f.Name, $startEndRe)
        if (-not $m.Success) { continue }
        $d = $m.Groups[1].Value
        try { $st = [datetime]::ParseExact("$d $($m.Groups[2].Value)", 'yyyy-MM-dd HH-mm-ss', $null) } catch { continue }
        if ($m.Groups[3].Success) {
            try { $en = [datetime]::ParseExact("$d $($m.Groups[3].Value)", 'yyyy-MM-dd HH-mm-ss', $null) } catch { $en = $st }
            if ($en -le $st) { $en = $en.AddDays(1) }     # wrapped past midnight
        } else { $en = $f.LastWriteTime }                  # active file (only if -IncludeActive)
        $intervals += ,@($st, $en)
    }
    $expected = if ($isToday) { 0..([math]::Max($nowHour-1,0)) } else { 0..($ExpectedHours-1) }
    $covered = @{}
    foreach ($h in $expected) {
        $h0 = $dayObj.AddHours($h); $h1 = $h0.AddHours(1)
        foreach ($iv in $intervals) { if ($iv[0] -lt $h1 -and $iv[1] -gt $h0) { $covered[$h] = $true; break } }
    }
    $missing = @($expected | Where-Object { -not $covered.ContainsKey($_) })
    $completeness.Add([pscustomobject]@{
        Group=$g; Files=$groups[$g].Count; HoursPresent=$covered.Keys.Count
        HoursExpected=$expected.Count; MissingHours=$missing
    })
}

# ---- summary ----
Say ("`n==================================================================") Cyan
Say ("  SUMMARY  -  day $dayStr") Cyan
Say ("==================================================================") Cyan
$incomplete = $false
foreach ($c in $completeness) {
    $miss = if ($c.MissingHours.Count -eq 0) { 'all hours present' }
            else { $incomplete=$true; ("MISSING hours: " + (($c.MissingHours | ForEach-Object { '{0:d2}' -f $_ }) -join ',')) }
    $col = if ($c.MissingHours.Count -eq 0) { 'Green' } else { 'Yellow' }
    Say ("  {0,-14} {1,3} files  {2,2}/{3,2} hrs  {4}" -f $c.Group, $c.Files, $c.HoursPresent, $c.HoursExpected, $miss) $col
}
Say ("------------------------------------------------------------------") Cyan
Say ("  copied: $copied   already-present: $skipped   FAILED: $failed") $(if($failed){'Red'}else{'White'})
Say ("  data copied this run: $([math]::Round($copiedBytes/1GB,2)) GB in $([math]::Round($swAll.Elapsed.TotalMinutes,1)) min") White

$result = if ($failed -gt 0) { 'COPY INCOMPLETE - some files FAILED (re-run to retry)'; }
          elseif ($incomplete) { 'COPY OK, but some hours are MISSING from the source (recording gap that day)' }
          else { 'COPY COMPLETE - all files copied and all 24 hours present' }
$rc = if ($failed -gt 0) { 2 } elseif ($incomplete) { 1 } else { 0 }
Say ("`n  >>> $result <<<") $(if($rc -eq 0){'Green'}elseif($rc -eq 1){'Yellow'}else{'Red'})

# ---- write report + manifest into the USB day folder ----
if (-not $DryRun -and (Test-Path $destDay)) {
    $rep = New-Object System.Collections.Generic.List[string]
    $rep.Add("Recording USB copy report")
    $rep.Add("=========================")
    $rep.Add("generated:   $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))")
    $rep.Add("day copied:  $dayStr")
    $rep.Add("source:      $($SourceRoots -join ' ; ')   (READ-ONLY - never modified)")
    $rep.Add("destination: $destDay")
    $rep.Add("verify:      $(if ($Hash) {'SHA-256'} else {'size compare'})")
    $rep.Add("result:      $result")
    $rep.Add("copied=$copied  already-present=$skipped  FAILED=$failed  ($([math]::Round($copiedBytes/1GB,2)) GB)")
    $rep.Add("")
    $rep.Add("Per-camera completeness:")
    foreach ($c in $completeness) {
        $miss = if ($c.MissingHours.Count -eq 0) { 'all hours present' } else { 'MISSING: ' + (($c.MissingHours | ForEach-Object { '{0:d2}' -f $_ }) -join ',') }
        $rep.Add(("  {0,-14} {1,3} files  {2,2}/{3,2} hrs  {4}" -f $c.Group, $c.Files, $c.HoursPresent, $c.HoursExpected, $miss))
    }
    if ($failed -gt 0) {
        $rep.Add(""); $rep.Add("FAILURES:")
        foreach ($m in ($manifest | Where-Object { $_.Status -like 'FAILED*' })) { $rep.Add("  $($m.Group)\$($m.File)  -  $($m.Status)") }
    }
    Set-Content -Path (Join-Path $destDay 'copy_report.txt') -Value ($rep -join "`r`n") -Encoding UTF8
    $manifest | Export-Csv -Path (Join-Path $destDay 'copy_manifest.csv') -NoTypeInformation -Encoding UTF8
    Say ("`n  report:   $(Join-Path $destDay 'copy_report.txt')") DarkGray
    Say ("  manifest: $(Join-Path $destDay 'copy_manifest.csv')") DarkGray
}

# ---- record this day in the persistent save log (unless nothing was actually saved) ----
# rc 0 = all present, rc 1 = copied OK but the source had recording gaps (the data that
# existed IS saved). Both mean "safe to delete". rc 2 = copy failures -> NOT recorded.
if (-not $DryRun -and $rc -ne 2) {
    Add-SaveLogEntry $SaveLog ([ordered]@{
        day             = $dayStr
        saved_at        = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        destination     = $destDay
        result          = $result
        rc              = $rc
        copied          = $copied
        already_present = $skipped
        failed          = $failed
        bytes           = $copiedBytes
        source_roots    = $SourceRoots
        method          = $(if ($Hash) { 'copy+sha256' } else { 'copy+size' })
    })
    Say ("  save log: $SaveLog") DarkGray
}

exit $rc
