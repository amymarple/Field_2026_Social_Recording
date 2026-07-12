<#
.SYNOPSIS
    Snapshot all field-PC recording logs into this repo's logs/ folder (gitignored).

.DESCRIPTION
    Read-only at the source: copies (never moves/deletes) the recorder, thermal, QC, and
    health-report logs into logs/<source>/ so they travel with this repo. logs/ is gitignored,
    so nothing here gets committed. Re-run anytime to refresh (e.g., before evaluating the
    encoder-bitrate experiment). Safe to run while recording — it only reads finished text logs.
#>
[CmdletBinding()]
param(
    [string]$Dest = (Join-Path $PSScriptRoot 'logs')
)

$ErrorActionPreference = 'Stop'

# source glob -> subfolder under logs/
$jobs = @(
    @{ Src = 'E:\Reolink_record\logs';      Sub = 'Reolink_record'; Filters = @('*.log') },
    @{ Src = 'E:\thermal_record\logs';      Sub = 'thermal_record'; Filters = @('*.log','*.txt') },
    @{ Src = 'E:\recording_qc';             Sub = 'recording_qc';   Filters = @('*.txt','*.json') },
    @{ Src = 'E:\recording_health_reports'; Sub = 'health_reports'; Filters = @('*.md','*.csv') }
)

$copied = 0
$lines  = @()
foreach ($j in $jobs) {
    $outDir = Join-Path $Dest $j.Sub
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    if (-not (Test-Path -LiteralPath $j.Src)) {
        Write-Host ("SKIP (missing): {0}" -f $j.Src) -ForegroundColor Yellow
        continue
    }
    foreach ($f in $j.Filters) {
        Get-ChildItem -LiteralPath $j.Src -Filter $f -File -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $outDir -Force
            $copied++
            $lines += ('  {0,10} bytes  logs/{1}/{2}' -f $_.Length, $j.Sub, $_.Name)
        }
    }
    Write-Host ("copied {0} -> logs\{1}\" -f $j.Src, $j.Sub) -ForegroundColor Green
}

# manifest
$man = Join-Path $Dest '_manifest.txt'
@(
    ("Recording-log snapshot: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
    "Read-only copy from field PC -> this repo logs/ (gitignored). Re-run to refresh.",
    "",
    "FILES ($copied):"
) + $lines | Set-Content -LiteralPath $man -Encoding UTF8

Write-Host ("`nDone. {0} files -> {1}" -f $copied, $Dest) -ForegroundColor Cyan
