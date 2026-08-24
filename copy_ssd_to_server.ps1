<#
.SYNOPSIS
    Copy a field-data SSD to the lab server share (Q:) in one command.

    *** RUN THIS ON THE CAMPUS / SERVER PC, NOT ON THE FIELD PC. ***
    The field PC has no route to BioHPC (DNS resolves, ICMP+445 blocked - verified
    2026-08-19), so the SSD is sneakernet: plug it into a machine that maps
    Q: = \\cbsuruizfs1.biohpc.cornell.edu\storage and run this there.

    *** COPY-ONLY. ADDITIVE. NOTHING IS EVER DELETED OR RENAMED. ***
    The SSD is read-only at the source; on Q: this only ever adds files. /MIR,
    /MOV, /MOVE and /PURGE are hard-blocked in code (Invoke-Robo throws if one
    ever appears in the argument list).

    What it does:
      - Finds every day folder (yyyy-MM-dd) on the SSD plus the extra data
        folders (Wiser_backup, WILD, nvr_rescue, Wiser_plot, weather_data, ...)
        and merges each into <Dest>\<same name>\ , preserving the per-stream
        subfolders. This is exactly the layout Q: already uses:
            Q:\hc997\SocialFieldRat2026\2026-08-15\CH01\CH01_..._to_....mp4
      - Verifies every file by NAME + EXACT BYTE SIZE (the house convention -
        no hashing), and reports anything missing or size-mismatched.
      - Writes <report dir>\<stamp>_ssd_to_server_report.txt + _verify.csv.
      - Is fully resumable: re-run it after an unplug/crash and it copies only
        what is missing or different.

.PARAMETER Ssd
    The source drive or folder, e.g.  F:  or  F:\  or  E:\staging .
    Omit it and the script auto-detects the one drive that has yyyy-MM-dd day
    folders at its root (it refuses to guess if two candidates exist).

.PARAMETER Dest
    Server destination. Default Q:\hc997\SocialFieldRat2026 .

.PARAMETER Include
    Only copy these top-level folders (day folders and/or extras), e.g.
    -Include 2026-08-15,2026-08-16  or  -Include Wiser_backup .
    Default = everything on the SSD except -ExcludeDirs.

.PARAMETER Threads
    robocopy /MT threads (default 8). Lower it if the share complains.

.PARAMETER Restartable
    Add /Z (restartable mode). Slower, but survives a flaky share mid-file.

.PARAMETER DryRun
    List what would be copied and how much, copy nothing.

.PARAMETER VerifyOnly
    Skip copying; just re-run the name+size audit of SSD vs server.

.PARAMETER SelfTest
    Offline logic test on synthetic temp data. Touches no real data, no server.

.PARAMETER ReportDir
    Where to write the report + CSV. Default: <Dest>\_transfer_reports .

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_ssd_to_server.ps1
    # auto-detect the SSD, copy everything to Q:\hc997\SocialFieldRat2026, verify

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_ssd_to_server.ps1 -Ssd F: -DryRun

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_ssd_to_server.ps1 -Ssd F: -VerifyOnly

.NOTES
    Exit codes: 0 = everything copied and verified, 1 = warnings only,
    2 = errors (robocopy failure, or files missing/mismatched after the copy).
#>

[CmdletBinding()]
param(
    [string]$Ssd,
    [string]$Dest = 'Q:\hc997\SocialFieldRat2026',
    [string[]]$Include,
    [string[]]$ExcludeDirs = @('$RECYCLE.BIN', 'System Volume Information', 'tmp',
                               '_transfer_reports', 'found.000'),
    [int]$Threads = 8,
    [switch]$Restartable,
    [switch]$DryRun,
    [switch]$VerifyOnly,
    [switch]$SelfTest,
    [string]$ReportDir
)

$ErrorActionPreference = 'Stop'

function Say([string]$msg, [string]$color = 'Gray') { Write-Host $msg -ForegroundColor $color }

# `powershell -File` passes "a,b" as ONE string (no array binding) - split ourselves
if ($Include) { $Include = @($Include | ForEach-Object { $_ -split ',' } | Where-Object { $_ }) }

# ---------------------------------------------------------------- helpers ----

# robocopy exit codes: <8 = success (0 none, 1 copied, 2 extra, 4 mismatch); >=8 = failure
function Robo-Ok([int]$rc) { return ($rc -lt 8) }

function Invoke-Robo {
    param([string]$Src, [string]$Dst, [string]$LogFile, [switch]$List)
    if (-not (Test-Path -LiteralPath $Src)) { Say "  (skip, missing source: $Src)" DarkGray; return 0 }
    # NO /XO: a partial file at the dest from an interrupted run has a NEWER
    # timestamp than the source, and /XO would skip it forever, leaving it
    # silently truncated. Without /XO robocopy still skips identical files
    # (size+time "Same") but re-copies anything partial/differing - the SSD is
    # the truth on this link.
    $flags = @('/E', '/R:2', '/W:5', "/MT:$Threads", '/NP', '/NDL', '/NJH', '/NJS', '/TEE')
    if ($LogFile)     { $flags += "/LOG+:$LogFile" }
    if ($Restartable) { $flags = @('/Z') + $flags }
    if ($List)        { $flags += '/L' }
    # HARD BLOCK: never allow destructive/mirroring flags
    foreach ($bad in @('/MIR', '/MOV', '/MOVE', '/PURGE')) {
        if ($flags -contains $bad) { throw "SAFETY ABORT: destructive robocopy flag $bad present." }
    }
    $argList = @("`"$Src`"", "`"$Dst`"") + $flags
    $p = Start-Process robocopy -ArgumentList $argList -NoNewWindow -Wait -PassThru
    return $p.ExitCode
}

# relative-path -> size map for one tree (metadata only; file contents are never read)
function Get-Inventory {
    param([string]$Root)
    $inv = @{}
    if (-not (Test-Path -LiteralPath $Root)) { return $inv }
    $prefix = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\') + '\'
    foreach ($f in (Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue)) {
        $inv[$f.FullName.Substring($prefix.Length)] = $f.Length
    }
    return $inv
}

# name + exact byte size compare (house convention: no hashing)
function Compare-Trees {
    param([hashtable]$SrcInv, [hashtable]$DstInv, [string]$Area)
    $rows = @()
    foreach ($rel in $SrcInv.Keys) {
        $srcSize = $SrcInv[$rel]
        if (-not $DstInv.ContainsKey($rel)) { $status = 'MISSING'; $dstSize = -1 }
        elseif ($DstInv[$rel] -ne $srcSize) { $status = 'SIZE_MISMATCH'; $dstSize = $DstInv[$rel] }
        else                                { $status = 'ok'; $dstSize = $DstInv[$rel] }
        $rows += New-Object psobject -Property @{
            area = $Area; relative_path = $rel; size_bytes = $srcSize
            dest_bytes = $dstSize; status = $status
        }
    }
    return $rows
}

# --------------------------------------------------------------- selftest ----

if ($SelfTest) {
    Say "SELF-TEST (synthetic data under TEMP - no real data, no server)" Cyan
    $t   = Join-Path $env:TEMP ('ssd2srv_selftest_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    $src = Join-Path $t 'src\2026-01-01\CH01'
    $dst = Join-Path $t 'dst'
    New-Item -ItemType Directory -Path $src -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $src 'CH01_2026-01-01_00-00-00_to_01-00-00.mp4') -Value ('a' * 1000)
    Set-Content -LiteralPath (Join-Path $src 'CH01_2026-01-01_01-00-00.mp4') -Value ('b' * 500)
    $ok = $true

    $rc = Invoke-Robo -Src (Join-Path $t 'src') -Dst $dst
    if (-not (Robo-Ok $rc)) { Say "  FAIL: robocopy exit $rc" Red; $ok = $false }
    $rows = Compare-Trees -SrcInv (Get-Inventory (Join-Path $t 'src')) -DstInv (Get-Inventory $dst) -Area 'test'
    if (@($rows).Count -ne 2) { Say "  FAIL: expected 2 rows, got $(@($rows).Count)" Red; $ok = $false }
    if (@($rows | Where-Object { $_.status -ne 'ok' }).Count -ne 0) { Say '  FAIL: clean copy should verify clean' Red; $ok = $false }

    # truncate a file at the dest -> must be caught as SIZE_MISMATCH
    Set-Content -LiteralPath (Join-Path $dst '2026-01-01\CH01\CH01_2026-01-01_01-00-00.mp4') -Value 'short'
    $rows = Compare-Trees -SrcInv (Get-Inventory (Join-Path $t 'src')) -DstInv (Get-Inventory $dst) -Area 'test'
    if (@($rows | Where-Object { $_.status -eq 'SIZE_MISMATCH' }).Count -ne 1) { Say '  FAIL: truncation not caught' Red; $ok = $false }

    # delete a file at the dest -> must be caught as MISSING
    Remove-Item -LiteralPath (Join-Path $dst '2026-01-01\CH01\CH01_2026-01-01_00-00-00_to_01-00-00.mp4') -Force
    $rows = Compare-Trees -SrcInv (Get-Inventory (Join-Path $t 'src')) -DstInv (Get-Inventory $dst) -Area 'test'
    if (@($rows | Where-Object { $_.status -eq 'MISSING' }).Count -ne 1) { Say '  FAIL: missing file not caught' Red; $ok = $false }

    # re-run must heal both problems (resumability)
    $rc = Invoke-Robo -Src (Join-Path $t 'src') -Dst $dst
    $rows = Compare-Trees -SrcInv (Get-Inventory (Join-Path $t 'src')) -DstInv (Get-Inventory $dst) -Area 'test'
    if (@($rows | Where-Object { $_.status -ne 'ok' }).Count -ne 0) { Say '  FAIL: re-run did not heal the tree' Red; $ok = $false }

    Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue
    if ($ok) { Say 'SELF-TEST PASSED' Green; exit 0 }
    Say 'SELF-TEST FAILED' Red
    exit 2
}

# ------------------------------------------------------- resolve the source ----

if (-not $Ssd) {
    $cands = @()
    foreach ($v in (Get-Volume | Where-Object { $_.DriveLetter -and $_.DriveType -ne 'CD-ROM' })) {
        $root = "$($v.DriveLetter):\"
        if ($root -eq 'C:\') { continue }
        $days = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' })
        if ($days.Count -gt 0) { $cands += $root }
    }
    if ($cands.Count -eq 1) { $Ssd = $cands[0]; Say "auto-detected SSD: $Ssd" DarkGray }
    elseif ($cands.Count -eq 0) {
        Say 'No drive with yyyy-MM-dd day folders found. Pass -Ssd F: explicitly.' Red; exit 2
    } else {
        Say "Several candidate drives ($($cands -join ', ')). Pass -Ssd explicitly." Red; exit 2
    }
}
if (-not (Test-Path -LiteralPath $Ssd)) { Say "Source not found: $Ssd" Red; exit 2 }
$Ssd = (Resolve-Path -LiteralPath $Ssd).Path

# ---- destination sanity: never copy onto the source drive ----
$srcQual  = if ($Ssd  -match '^[A-Za-z]:') { Split-Path $Ssd  -Qualifier } else { '' }
$destQual = if ($Dest -match '^[A-Za-z]:') { Split-Path $Dest -Qualifier } else { '' }
if ($srcQual -and $destQual -and ($srcQual -eq $destQual)) {
    Say "REFUSING: destination is on the SAME drive as the source ($srcQual)." Red; exit 2
}
$destParent = try { Split-Path $Dest -Parent } catch { $null }
if (-not (Test-Path -LiteralPath $Dest) -and -not ($destParent -and (Test-Path -LiteralPath $destParent))) {
    Say "Destination not reachable: $Dest" Red
    Say '  Is Q: mapped on this machine?   net use Q: \\cbsuruizfs1.biohpc.cornell.edu\storage' Yellow
    Say '  (The FIELD PC cannot reach BioHPC - run this on the campus/server PC.)' Yellow
    exit 2
}
if (-not $DryRun -and -not $VerifyOnly -and -not (Test-Path -LiteralPath $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
}

# ---- which top-level folders travel ----
$folders = @(Get-ChildItem -LiteralPath $Ssd -Directory -ErrorAction SilentlyContinue |
             Where-Object { $ExcludeDirs -notcontains $_.Name } |
             Where-Object { (-not $Include) -or ($Include -contains $_.Name) } |
             Sort-Object Name)
if ($folders.Count -eq 0) { Say "Nothing to copy from $Ssd (after excludes / -Include)." Yellow; exit 1 }

$stamp     = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
if (-not $ReportDir) { $ReportDir = Join-Path $Dest '_transfer_reports' }
$logFile   = Join-Path $ReportDir ($stamp + '_ssd_to_server.log')
$reportTxt = Join-Path $ReportDir ($stamp + '_ssd_to_server_report.txt')
$csvPath   = Join-Path $ReportDir ($stamp + '_ssd_to_server_verify.csv')
if (-not $DryRun) { New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null }

$modeText = if ($VerifyOnly) { 'VERIFY ONLY' }
            elseif ($DryRun) { 'DRY RUN' }
            else { "COPY ($Threads threads" + $(if ($Restartable) { ' /Z' } else { '' }) + ')' }
$headNames = ($folders | Select-Object -First 8 | ForEach-Object { $_.Name }) -join ', '
if ($folders.Count -gt 8) { $headNames = $headNames + ', ...' }

Say '==================================================================' Cyan
Say '  SSD -> SERVER   (copy-only, additive; SSD never modified)' Cyan
Say "  Source: $Ssd" Cyan
Say "  Dest:   $Dest" Cyan
Say "  Scope:  $($folders.Count) folder(s): $headNames" Cyan
Say "  Mode:   $modeText" Cyan
Say '==================================================================' Cyan

# ------------------------------------------------------------------ copy ----

$fail = 0
if (-not $VerifyOnly) {
    foreach ($f in $folders) {
        $dst = Join-Path $Dest $f.Name
        Say "`n[$($f.Name)] -> $dst" White
        $lf = if ($DryRun) { $null } else { $logFile }
        $rc = Invoke-Robo -Src $f.FullName -Dst $dst -LogFile $lf -List:$DryRun
        if (-not (Robo-Ok $rc)) { $fail++; Say "  robocopy FAILED (exit $rc)" Red }
    }
}
if ($DryRun) {
    Say "`nDRY RUN - nothing was copied, nothing was written." Yellow
    if ($fail -gt 0) { exit 2 }
    exit 0
}

# ---------------------------------------------------------------- verify ----

Say "`n[verify] name + exact byte size, SSD vs server ..." White
$allRows  = @()
$perArea  = @{}
foreach ($f in $folders) {
    $srcInv = Get-Inventory $f.FullName
    $dstInv = Get-Inventory (Join-Path $Dest $f.Name)
    $rows   = @(Compare-Trees -SrcInv $srcInv -DstInv $dstInv -Area $f.Name)
    $bad    = @($rows | Where-Object { $_.status -ne 'ok' })
    $bytes  = ($srcInv.Values | Measure-Object -Sum).Sum
    if (-not $bytes) { $bytes = 0 }
    $perArea[$f.Name] = New-Object psobject -Property @{
        Files = $srcInv.Count; Bytes = $bytes; Bad = $bad.Count
    }
    $mark = if ($bad.Count -eq 0) { 'OK ' } else { 'BAD' }
    $col  = if ($bad.Count -eq 0) { 'Green' } else { 'Red' }
    $note = if ($bad.Count -eq 0) { 'verified' } else { "$($bad.Count) PROBLEM(S)" }
    Say ("  {0} {1,-28} {2,5} files  {3,8:n1} GB  {4}" -f $mark, $f.Name, $srcInv.Count, ($bytes / 1GB), $note) $col
    $allRows += $rows
}

$bad     = @($allRows | Where-Object { $_.status -ne 'ok' })
$sumAll  = ($allRows | Measure-Object -Property size_bytes -Sum).Sum
if (-not $sumAll) { $sumAll = 0 }
$totalGB = $sumAll / 1GB
$allRows | Select-Object area, relative_path, size_bytes, dest_bytes, status |
    Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

$result = if ($fail -gt 0)        { 'COPY FAILED - robocopy reported errors (re-run to retry)' }
          elseif ($bad.Count -gt 0) { 'INCOMPLETE - files missing or size-mismatched (re-run to retry)' }
          else                    { 'COMPLETE - every file on the SSD is on the server, byte sizes match' }

$lines = @(
    'SSD -> server transfer report'
    '============================='
    "generated:   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "source:      $Ssd   (READ-ONLY - never modified)"
    "destination: $Dest  (additive - nothing deleted or renamed)"
    'verify:      filename + exact byte size'
    "result:      $result"
    ("files: {0}   verified ok: {1}   problems: {2}   total: {3:n1} GB" -f $allRows.Count, ($allRows.Count - $bad.Count), $bad.Count, $totalGB)
    ''
    'Per-folder:'
)
foreach ($f in $folders) {
    $a = $perArea[$f.Name]
    $note = if ($a.Bad -eq 0) { 'verified' } else { "$($a.Bad) PROBLEM(S)" }
    $lines += ("  {0,-28} {1,5} files  {2,8:n1} GB  {3}" -f $f.Name, $a.Files, ($a.Bytes / 1GB), $note)
}
if ($bad.Count -gt 0) {
    $lines += ''
    $lines += 'PROBLEMS (first 40):'
    foreach ($b in ($bad | Select-Object -First 40)) {
        $lines += ("  {0}\{1}  {2}  (src {3} B, dest {4} B)" -f $b.area, $b.relative_path, $b.status, $b.size_bytes, $b.dest_bytes)
    }
}
$lines += ''
$lines += "verify csv:   $csvPath"
$lines += "robocopy log: $logFile"
$lines | Set-Content -LiteralPath $reportTxt -Encoding UTF8

$resultColor = if ($fail -gt 0 -or $bad.Count -gt 0) { 'Red' } else { 'Green' }
Say ''
Say '------------------------------------------------------------------' Cyan
Say "  $result" $resultColor
Say ("  {0:n0} files, {1:n1} GB" -f $allRows.Count, $totalGB) Cyan
Say "  report: $reportTxt" Cyan
Say '------------------------------------------------------------------' Cyan

if ($fail -gt 0 -or $bad.Count -gt 0) { exit 2 }
exit 0
