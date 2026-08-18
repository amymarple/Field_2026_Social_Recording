<#
.SYNOPSIS
    SAFELY delete ONE day of recordings from the recorders, after confirming that
    day was already saved (copied to USB) by copy_day_to_usb.ps1.

    This is the targeted cleanup tool: you give it ONE day and it removes only the
    finished .mp4 files for THAT day from E:\Reolink_record and E:\thermal_record.
    Every other day is left completely untouched.

    Three safety layers, all on by default:
      1. -Date is REQUIRED. There is no "delete everything" mode.
      2. A file is only deleted if the START DATE embedded in its name (parsed with
         a strict regex, not a loose substring match) equals the target day, AND it
         is a finished segment (has "_to_" in the name). The still-recording file is
         never touched.
      3. -RequireSaved (default TRUE) refuses to delete a day unless the save log
         (written by copy_day_to_usb.ps1) shows that day was copied with 0 failures.

    It writes an audit record of everything it deleted to the delete log.

.PARAMETER Date
    REQUIRED. The day to delete, yyyy-MM-dd. Only files whose filename start date is
    this day are removed.

.PARAMETER RequireSaved
    Default TRUE. When true, the day must appear in the save log as successfully
    saved (failed=0) or the script refuses to delete. Set -RequireSaved:$false to
    delete WITHOUT a save check (dangerous — only for data you intend to discard).

.PARAMETER SaveLog
    Path to the save log written by copy_day_to_usb.ps1.
    Default E:\recording_qc\save_log.json.

.PARAMETER DryRun
    List exactly what WOULD be deleted (and the save-check result) but delete nothing.

.PARAMETER Yes
    Skip the interactive "type the date to confirm" prompt. For unattended runs.

.PARAMETER SourceRoots
    The recorder roots to clean. Override only for testing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File delete_day.ps1 -Date 2026-06-20 -DryRun
    # preview what would be removed for 2026-06-20

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File delete_day.ps1 -Date 2026-06-20
    # delete 2026-06-20, but only if the save log says it was copied

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File delete_day.ps1 -Date 2026-06-20 -RequireSaved:$false -Yes
    # delete without the save check and without the confirmation prompt
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Date,
    [bool]$RequireSaved = $true,
    [string]$SaveLog = 'E:\recording_qc\save_log.json',
    [switch]$DryRun,
    [switch]$Yes,
    [string[]]$SourceRoots = @('E:\Reolink_record', 'E:\thermal_record', 'E:\ultramic_record')   # ultramic added 2026-07-18
)

# ============================ CONFIG ============================
$ExcludeDirs = @('bin', 'logs')
$Extensions  = @('.mp4', '.wav', '.flac')     # video + UltraMic audio segments
$DeleteLog   = $SaveLog -replace 'save_log\.json$', 'delete_log.json'
if ($DeleteLog -eq $SaveLog) { $DeleteLog = Join-Path (Split-Path -Parent $SaveLog) 'delete_log.json' }
# ===============================================================

$ErrorActionPreference = 'Stop'

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

function Get-SavedDays([string]$LogPath) {
    if (-not (Test-Path -LiteralPath $LogPath)) { return @() }
    try {
        $raw = Get-Content -LiteralPath $LogPath -Raw -Encoding UTF8
        if (-not $raw.Trim()) { return @() }
        return @($raw | ConvertFrom-Json)
    } catch { return @() }
}

function Add-DeleteLogEntry([string]$LogPath, $Entry) {
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
    $line = "{0}  day={1}  deleted_files={2}  freed_GB={3}  require_saved={4}  dryrun={5}" -f `
        $Entry.deleted_at, $Entry.day, $Entry.deleted_files, $Entry.freed_GB, $Entry.require_saved, $Entry.dry_run
    Add-Content -LiteralPath $txt -Value $line -Encoding UTF8
}

# ---- resolve + validate the day ----
try { $dayObj = [datetime]::ParseExact($Date, 'yyyy-MM-dd', $null) }
catch { Say "Bad -Date '$Date'. Use yyyy-MM-dd (e.g. 2026-06-20)." Red; exit 2 }
$dayStr  = $dayObj.ToString('yyyy-MM-dd')
$isToday = ($dayObj.Date -eq (Get-Date).Date)

Say ("==================================================================") Cyan
Say ("  DELETE DAY    (targeted cleanup - only the chosen day is touched)") Cyan
Say ("  Day:         $dayStr" + $(if ($isToday) { '  (TODAY - active recording is protected)' } else { '' })) Cyan
Say ("  Sources:     $($SourceRoots -join ' ; ')") Cyan
Say ("  Save check:  " + $(if ($RequireSaved) { "ON  (save log: $SaveLog)" } else { 'OFF (-RequireSaved:$false)' })) Cyan
Say ("  Mode:        " + $(if ($DryRun) { 'DRY RUN (nothing will be deleted)' } else { 'DELETE' })) Cyan
Say ("==================================================================") Cyan

# ---- save check: was this day already copied to USB? ----
if ($RequireSaved) {
    $rec = Get-SavedDays $SaveLog | Where-Object { $_.day -eq $dayStr -and (@($_.failed)[0] -eq 0) } | Select-Object -Last 1   # @() guard: legacy entries stored 'failed' as an array
    if (-not $rec) {
        Say "`nREFUSING to delete: no successful save record for $dayStr in the save log." Red
        Say "  Save the day first:   copy_day_to_usb.ps1 -Usb F: -Date $dayStr" Yellow
        Say "  Or override (danger): re-run this with -RequireSaved:`$false" Yellow
        exit 2
    }
    Say ("`nSave check PASSED - $dayStr was saved on $($rec.saved_at) -> $($rec.destination) [$($rec.method)]") Green
}

# ---- gather the files for THIS day only (strict start-date match) ----
$startDateRe = '_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}'   # the leading start-time token in the name
$targets = New-Object System.Collections.Generic.List[object]
$perGroup = [ordered]@{}

foreach ($root in $SourceRoots) {
    if (-not (Test-Path $root)) { Say "WARNING: source root missing: $root" Yellow; continue }
    $rootFull = [System.IO.Path]::GetFullPath($root)
    foreach ($dir in (Get-ChildItem $root -Directory -EA SilentlyContinue | Where-Object { $ExcludeDirs -notcontains $_.Name })) {
        $hits = @()
        foreach ($f in (Get-ChildItem $dir.FullName -File -EA SilentlyContinue)) {
            if ($Extensions -notcontains $f.Extension.ToLower()) { continue }
            if ($f.BaseName -notlike '*_to_*') { continue }                  # never the still-recording file
            $m = [regex]::Match($f.Name, $startDateRe)
            if (-not $m.Success -or $m.Groups[1].Value -ne $dayStr) { continue }   # STRICT: start date must equal target
            # defense in depth: the file must really live under a known source root
            $full = [System.IO.Path]::GetFullPath($f.FullName)
            if (-not $full.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
            $hits += $f
            $targets.Add($f)
        }
        if ($hits.Count -gt 0) { $perGroup[("{0}\{1}" -f (Split-Path $root -Leaf), $dir.Name)] = @($hits | Sort-Object Name) }
    }
}

$totalBytes = ($targets | Measure-Object Length -Sum).Sum; if (-not $totalBytes) { $totalBytes = 0 }
$totalGB = [math]::Round($totalBytes / 1GB, 2)

Say ("`nMatched $($targets.Count) finished file(s) for $dayStr across $($perGroup.Count) camera folder(s): $totalGB GB") White
foreach ($g in $perGroup.Keys) {
    Say ("  {0,-28} {1,3} file(s)  {2,8:n2} GB" -f $g, $perGroup[$g].Count, (($perGroup[$g] | Measure-Object Length -Sum).Sum / 1GB)) Gray
}

if ($targets.Count -eq 0) {
    Say "`nNothing to delete for $dayStr (already clean, or no finished files for that day)." Yellow
    exit 0
}

# ---- reassurance: list the OTHER days present that we are NOT touching ----
$otherDays = New-Object System.Collections.Generic.HashSet[string]
foreach ($root in $SourceRoots) {
    if (-not (Test-Path $root)) { continue }
    foreach ($dir in (Get-ChildItem $root -Directory -EA SilentlyContinue | Where-Object { $ExcludeDirs -notcontains $_.Name })) {
        foreach ($f in (Get-ChildItem $dir.FullName -File -Filter '*.mp4' -EA SilentlyContinue)) {
            $m = [regex]::Match($f.Name, $startDateRe)
            if ($m.Success -and $m.Groups[1].Value -ne $dayStr) { [void]$otherDays.Add($m.Groups[1].Value) }
        }
    }
}
if ($otherDays.Count -gt 0) {
    Say ("`nOther days present and LEFT UNTOUCHED: " + (($otherDays | Sort-Object) -join ', ')) DarkGray
}

if ($DryRun) {
    Say "`nDRY RUN - no files were deleted." Yellow
    exit 0
}

# ---- confirm ----
if (-not $Yes) {
    Say ("`nAbout to PERMANENTLY DELETE the $($targets.Count) file(s) above ($totalGB GB) for $dayStr.") Red
    $ans = Read-Host "Type the date ($dayStr) to confirm, anything else to abort"
    if ($ans -ne $dayStr) { Say "Aborted - nothing was deleted." Yellow; exit 1 }
}

# ---- delete ----
$deleted = 0; $failed = 0; $freedBytes = 0
$audit = New-Object System.Collections.Generic.List[object]
foreach ($f in $targets) {
    # final per-file guard right before deletion
    $m = [regex]::Match($f.Name, $startDateRe)
    if (-not $m.Success -or $m.Groups[1].Value -ne $dayStr -or $f.BaseName -notlike '*_to_*') {
        Say ("  SKIP (failed final guard): $($f.FullName)") Yellow; continue
    }
    try {
        $sz = $f.Length
        [System.IO.File]::Delete($f.FullName)
        $deleted++; $freedBytes += $sz
        $audit.Add([pscustomobject]@{ File = $f.FullName; SizeBytes = $sz; Status = 'deleted' })
        Say ("  deleted  $($f.FullName)") Gray
    } catch {
        $failed++
        $audit.Add([pscustomobject]@{ File = $f.FullName; SizeBytes = $f.Length; Status = "FAILED: $($_.Exception.Message)" })
        Say ("  FAILED   $($f.FullName)  -  $($_.Exception.Message)") Red
    }
}

$freedGB = [math]::Round($freedBytes / 1GB, 2)
Say ("`n------------------------------------------------------------------") Cyan
Say ("  deleted: $deleted   FAILED: $failed   freed: $freedGB GB   day: $dayStr") $(if ($failed) { 'Red' } else { 'Green' })

# ---- audit log ----
Add-DeleteLogEntry $DeleteLog ([ordered]@{
    deleted_at    = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    day           = $dayStr
    deleted_files = $deleted
    failed        = $failed
    freed_GB      = $freedGB
    require_saved = $RequireSaved
    dry_run       = $false
    source_roots  = $SourceRoots
    files         = $audit
})
Say ("  audit log: $DeleteLog") DarkGray

exit $(if ($failed -gt 0) { 2 } else { 0 })
