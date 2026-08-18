<#
.SYNOPSIS
    Copy a WHOLE COHORT of recordings to a USB drive, one day at a time, laid out as
    <USB>\<cohort_id>\<date>\<camera>\ .

    Thin wrapper around the proven copy_day_to_usb.ps1 - it changes NOTHING about how
    each day is copied (copy-only, read-only at source, verified, resumable, save-log).
    It only (a) reads the cohort's date range from COHORTS.csv and (b) points each
    day's copy at the <USB>\<cohort_id> subfolder. Re-running resumes/verifies.

.DESCRIPTION
    Cohort membership lives in COHORTS.csv (cohort_id,start_date,end_date,animals,notes),
    kept next to this script. Capture folders stay flat and date-named; the cohort
    folder structure appears only here, at the archive boundary.

.PARAMETER Usb
    USB drive or folder, e.g. G:  - the cohort lands at <Usb>\<cohort_id>\ .

.PARAMETER Cohort
    cohort_id from COHORTS.csv (e.g. cohort1).

.PARAMETER ListOnly
    Just print the resolved date list and destinations; copy nothing, scan nothing.

.PARAMETER DryRun / Hash
    Passed through to copy_day_to_usb.ps1 for every day.

.PARAMETER StartFrom
    Resume the loop at this date (yyyy-MM-dd), skipping earlier days. (Each day is
    itself resumable, so this is just a time-saver on re-runs.)

.PARAMETER MaxDays
    Copy at most this many days this run (default: all). Useful for staging.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File copy_cohort_to_usb.ps1 -Usb G: -Cohort cohort1 -ListOnly
    powershell -ExecutionPolicy Bypass -File copy_cohort_to_usb.ps1 -Usb G: -Cohort cohort1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Usb,
    [Parameter(Mandatory = $true)][string]$Cohort,
    [string]$Manifest,
    [switch]$ListOnly,
    [switch]$DryRun,
    [switch]$Hash,
    [string]$StartFrom,
    [int]$MaxDays = 0
)

$ErrorActionPreference = 'Stop'
$base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Manifest) { $Manifest = Join-Path $base 'COHORTS.csv' }
$dayScript = Join-Path $base 'copy_day_to_usb.ps1'
if (-not (Test-Path -LiteralPath $dayScript)) { Write-Host "copy_day_to_usb.ps1 not found next to this script." -ForegroundColor Red; exit 2 }
if (-not (Test-Path -LiteralPath $Manifest))  { Write-Host "Cohort manifest not found: $Manifest" -ForegroundColor Red; exit 2 }

$row = Import-Csv -LiteralPath $Manifest | Where-Object { $_.cohort_id -eq $Cohort }
if (-not $row) {
    Write-Host "Cohort '$Cohort' not in $Manifest. Known: $((Import-Csv -LiteralPath $Manifest | ForEach-Object { $_.cohort_id }) -join ', ')" -ForegroundColor Red
    exit 2
}
$start = [datetime]::ParseExact($row.start_date, 'yyyy-MM-dd', $null)
$end   = [datetime]::ParseExact($row.end_date,   'yyyy-MM-dd', $null)
if ($end -lt $start) { Write-Host "Manifest error: end before start." -ForegroundColor Red; exit 2 }

$days = @(); $d = $start
while ($d -le $end) { $days += $d.ToString('yyyy-MM-dd'); $d = $d.AddDays(1) }
if ($StartFrom) { $days = @($days | Where-Object { $_ -ge $StartFrom }) }
if ($MaxDays -gt 0 -and $days.Count -gt $MaxDays) { $days = @($days | Select-Object -First $MaxDays) }

$usbTrim = $Usb.Trim(); if ($usbTrim -match '^[A-Za-z]:$') { $usbTrim += '\' }
$destRoot = $usbTrim.TrimEnd('\') + '\' + $Cohort   # not Join-Path: it fails if the drive is not plugged in yet

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  COPY COHORT -> USB   $Cohort  ($($row.start_date) .. $($row.end_date), $($days.Count) day(s) this run)" -ForegroundColor Cyan
Write-Host "  Destination: $destRoot\<date>\<camera>\" -ForegroundColor Cyan
if ($row.notes) { Write-Host "  Notes: $($row.notes)" -ForegroundColor DarkGray }
Write-Host "==================================================================" -ForegroundColor Cyan

if ($ListOnly) {
    foreach ($day in $days) { Write-Host ("  {0}  ->  {1}\{0}\" -f $day, $destRoot) }
    Write-Host "`n(ListOnly - nothing scanned or copied)" -ForegroundColor Yellow
    exit 0
}

# The cohort folder must exist before copy_day_to_usb.ps1 validates the path.
# (Writes only on the USB side - the source is never touched.)
if (-not (Test-Path -LiteralPath $destRoot)) { New-Item -ItemType Directory -Force -Path $destRoot | Out-Null }

# The cohort's last day often ends mid-day with cleanly-killed (still un-renamed)
# segments; include them ONLY if that day is fully in the past.
$today = (Get-Date).ToString('yyyy-MM-dd')

$results = @()
$worst = 0
foreach ($day in $days) {
    $extra = @{}
    if ($day -eq $row.end_date -and $day -lt $today) { $extra['IncludeActive'] = $true }
    Write-Host ""
    & $dayScript -Usb $destRoot -Date $day -Hash:$Hash -DryRun:$DryRun @extra
    $rc = $LASTEXITCODE
    $results += [pscustomobject]@{ Day = $day; ExitCode = $rc }
    if ($rc -gt $worst) { $worst = $rc }
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  COHORT SUMMARY  $Cohort" -ForegroundColor Cyan
foreach ($r in $results) {
    $txt = switch ($r.ExitCode) { 0 { 'complete' } 1 { 'copied (source had gaps)' } default { 'FAILED - re-run to retry' } }
    $col = switch ($r.ExitCode) { 0 { 'Green' } 1 { 'Yellow' } default { 'Red' } }
    Write-Host ("  {0}  {1}" -f $r.Day, $txt) -ForegroundColor $col
}
Write-Host "==================================================================" -ForegroundColor Cyan
exit $worst
