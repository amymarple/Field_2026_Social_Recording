<#
.SYNOPSIS
    Copy EVERYTHING needed for offline analysis (Reolink video + thermal + WISER
    backup) from the field PC to the analysis computer over the direct USB-Ethernet
    link, in ONE command. So you can run the audio, CV, and WISER analysis on the
    other machine.

    *** READ-ONLY AT THE SOURCE. THIS SCRIPT ONLY EVER COPIES. ***
    It uses robocopy in copy-only mode: NO /MIR, NO /MOV, NO /PURGE (all three are
    hard-blocked below), so it can never delete/move/modify anything on E:. It only
    writes to the destination you give.

    Safety built in:
      - Closed files only: the still-recording file (CHxx_<start>.mp4, no "_to_") is
        SKIPPED via the "*_to_*.mp4" filter, honoring the open-file rule. -IncludeActive
        overrides (not recommended).
      - WISER: copies the SNAPSHOT backups in E:\Wiser_backup (consistent), NOT the live
        D:\Wiser\data DB (which is mid-write and unsafe to copy).
      - Refuses if the destination is on the recording drive.
      - Resumable/idempotent: re-run to copy only what's new (robocopy skips in-sync files).

.PARAMETER Dest
    Destination root on the analysis computer, e.g.  \\192.168.50.2\audio_in  (a writable
    share over the USB link) or any folder/drive NOT on the recording disk. Required.

.PARAMETER Date
    Limit VIDEO to one day (yyyy-MM-dd). Omit to copy ALL closed recordings. (WISER backup
    is always fully mirrored; it is small.)

.PARAMETER IncludeActive
    Also copy the still-recording (open) file. OFF by default. Leave off on the live rig.

.PARAMETER SkipVideo / SkipThermal / SkipWiser
    Turn off a modality. All ON by default ("copy everything").

.PARAMETER Gentle
    Add an inter-packet gap (robocopy /IPG) to ease link/disk pressure during capture.

.PARAMETER Threads
    robocopy /MT threads (default 8).

.PARAMETER DryRun
    List what would be copied and total sizes; copy nothing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_to_analysis.ps1 -Dest \\192.168.50.2\audio_in
    # copies ALL closed video + thermal + WISER backup to the analysis computer

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_to_analysis.ps1 -Dest \\192.168.50.2\audio_in -Date 2026-06-29 -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Dest,
    [string]$Date,
    [switch]$IncludeActive,
    [switch]$SkipVideo,
    [switch]$SkipThermal,
    [switch]$SkipWiser,
    [switch]$Gentle,
    [int]$Threads = 8,
    [switch]$DryRun,
    [string]$ReolinkRoot = 'E:\Reolink_record',
    [string]$ThermalRoot = 'E:\thermal_record',
    [string]$WiserSource = 'E:\Wiser_backup'
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

$ExcludeDirs = @('bin', 'logs')
$logFile = Join-Path $env:TEMP ("copy_to_analysis_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

# ---- validate date ----
if ($Date) {
    try { [void][datetime]::ParseExact($Date, 'yyyy-MM-dd', $null) }
    catch { Say "Bad -Date '$Date'. Use yyyy-MM-dd." Red; exit 2 }
}

# ---- destination sanity: must NOT be on a recording source drive ----
$srcQuals = @($ReolinkRoot, $ThermalRoot, $WiserSource | ForEach-Object { (Split-Path $_ -Qualifier) } | Where-Object { $_ })
# NOTE: Split-Path -Qualifier THROWS on a UNC path (\\server\share), so only ask for a
# qualifier when the dest is a drive-letter path. A UNC dest has no drive qualifier -> ''
# -> the same-drive-as-source guard is skipped (a UNC dest can't be a local recording drive).
$destQual = if ($Dest -match '^[A-Za-z]:') { Split-Path $Dest -Qualifier } else { '' }
if ($destQual -and ($srcQuals -contains $destQual)) {
    Say "REFUSING: destination ($destQual) is a recording drive. Pick the analysis computer's share/drive." Red
    exit 2
}
# reachability check (share up? drive present?) - guard Split-Path against UNC edge cases
$destParent = try { Split-Path $Dest -Parent } catch { $null }
if (-not (Test-Path -LiteralPath $Dest) -and -not ($destParent -and (Test-Path -LiteralPath $destParent))) {
    Say "Destination not reachable: $Dest" Red
    Say "  Is the USB link up (Test-Connection 192.168.50.2) and the share created + writable?" Yellow
    exit 2
}

# ---- the safe robocopy runner: constructs args itself so /MIR /MOV /PURGE can't appear ----
function Invoke-Robo {
    param([string]$Src, [string]$Dst, [string[]]$Patterns, [switch]$Recurse)
    if (-not (Test-Path -LiteralPath $Src)) { Say "  (skip, missing source: $Src)" DarkGray; return 0 }
    $flags = @('/Z', '/R:2', '/W:5', "/MT:$Threads", '/XO', '/NP', '/NDL', '/NJH', '/NJS',
               '/XD') + $ExcludeDirs + @('/TEE', "/LOG+:$logFile")
    if ($Recurse) { $flags += '/E' }
    if ($Gentle)  { $flags += @('/IPG:20') }
    if ($DryRun)  { $flags += '/L' }
    # HARD BLOCK: never allow destructive/mirroring flags
    foreach ($bad in @('/MIR', '/MOV', '/MOVE', '/PURGE')) {
        if ($flags -contains $bad) { throw "SAFETY ABORT: destructive robocopy flag $bad present." }
    }
    $argList = @("`"$Src`"", "`"$Dst`"") + $Patterns + $flags
    $p = Start-Process robocopy -ArgumentList $argList -NoNewWindow -Wait -PassThru
    return $p.ExitCode
}

# robocopy exit codes: <8 = success (0 none,1 copied,2 extra,4 mismatch); >=8 = failure
function Robo-Ok([int]$rc) { return ($rc -lt 8) }

# video filename filter (closed files only unless -IncludeActive)
$datePart = if ($Date) { "*_${Date}_" } else { '*' }
$videoPatterns = if ($IncludeActive) { @("$datePart*.mp4") } else { @("$datePart*_to_*.mp4") }

Say ("==================================================================") Cyan
Say ("  COPY -> ANALYSIS COMPUTER   (copy-only; source never modified)") Cyan
Say ("  Dest:   $Dest") Cyan
Say ("  Scope:  " + $(if ($Date) { "video for $Date" } else { 'ALL closed video' }) +
     "  |  filter: $($videoPatterns -join ',')") Cyan
Say ("  Modes:  video=$(-not $SkipVideo) thermal=$(-not $SkipThermal) wiser=$(-not $SkipWiser)" +
     "  |  $(if ($DryRun){'DRY RUN'}else{'COPY'})$(if($Gentle){' (gentle)'})") Cyan
Say ("  Log:    $logFile") Cyan
Say ("==================================================================") Cyan

$fail = 0

# ---- Reolink video: each CHxx -> Dest\Reolink_record\CHxx ----
if (-not $SkipVideo -and (Test-Path $ReolinkRoot)) {
    Say "`n[Reolink video]" White
    foreach ($d in (Get-ChildItem $ReolinkRoot -Directory -EA SilentlyContinue | Where-Object { $ExcludeDirs -notcontains $_.Name })) {
        $dst = Join-Path (Join-Path $Dest 'Reolink_record') $d.Name
        Say "  $($d.Name) -> $dst"
        $rc = Invoke-Robo -Src $d.FullName -Dst $dst -Patterns $videoPatterns
        if (-not (Robo-Ok $rc)) { $fail++; Say "    robocopy FAILED (exit $rc)" Red }
    }
}

# ---- thermal: each group -> Dest\thermal_record\<group> ----
if (-not $SkipThermal -and (Test-Path $ThermalRoot)) {
    Say "`n[thermal]" White
    foreach ($d in (Get-ChildItem $ThermalRoot -Directory -EA SilentlyContinue | Where-Object { $ExcludeDirs -notcontains $_.Name })) {
        $dst = Join-Path (Join-Path $Dest 'thermal_record') $d.Name
        Say "  $($d.Name) -> $dst"
        $rc = Invoke-Robo -Src $d.FullName -Dst $dst -Patterns $videoPatterns
        if (-not (Robo-Ok $rc)) { $fail++; Say "    robocopy FAILED (exit $rc)" Red }
    }
}

# ---- WISER: mirror the whole backup tree (snapshots + incremental) additively ----
if (-not $SkipWiser) {
    Say "`n[WISER backup]" White
    if (-not (Test-Path $WiserSource)) {
        Say "  no WISER backup at $WiserSource (run backup_wiser_daily.py first) - skipping" DarkYellow
    } else {
        $dst = Join-Path $Dest 'Wiser_backup'
        Say "  $WiserSource -> $dst  (all snapshots + incremental CSVs)"
        $rc = Invoke-Robo -Src $WiserSource -Dst $dst -Patterns @('*.*') -Recurse
        if (-not (Robo-Ok $rc)) { $fail++; Say "    robocopy FAILED (exit $rc)" Red }
    }
}

Say ("`n==================================================================") Cyan
if ($DryRun) {
    Say "  DRY RUN complete - see $logFile for the file list + sizes (robocopy /L)." Yellow
    exit 0
}
if ($fail -eq 0) {
    Say "  >>> DONE - everything copied (or already in sync). Source untouched. <<<" Green
    Say "  Re-run any time to copy only what's new (resumable)." DarkGray
    exit 0
} else {
    Say "  >>> $fail group(s) had robocopy failures - see $logFile. Re-run to retry. <<<" Red
    exit 2
}
