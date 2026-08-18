# 2026-07-14 — Cohort manifest + whole-cohort USB copy

## Decision
Cohorts are **date ranges, not folders**, at the capture layer. Capture stays flat/timestamped
(every tool depends on the filename contract and day-based lifecycle; continuous capture spans
cohort boundaries). Cohort structure appears only where humans browse: the **archive**.

## What was added
- **`COHORTS.csv`** — the cohort source of truth: `cohort_id,start_date,end_date,animals,notes`.
  Row 1: `cohort1, 2026-06-28 .. 2026-07-12` (recording stopped 07-12 15:00). Matches the WISER
  backup naming (`1stcohort_2026_*`).
- **`copy_cohort_to_usb.ps1`** — thin wrapper: reads the manifest, loops the cohort's days,
  invokes the untouched `copy_day_to_usb.ps1` per day with destination `<USB>\<cohort_id>\<date>\`.
  Inherits all its guarantees (copy-only, read-only source, verified, resumable, save-log).
  Extras: `-ListOnly`, `-StartFrom`, `-MaxDays`; auto `-IncludeActive` on the cohort's final day
  (cleanly-killed unrenamed segments) only when that day is in the past.
  `Join-Path` avoided for the dest root (PS 5.1 fails on unplugged drives); cohort dir pre-created
  (day script's Resolve-Path requires it).

## Verified
`-ListOnly` resolves all 15 days; one-day `-DryRun` through the full chain: 244 files / 446 GB
found for 06-28 across 12 cameras, completeness report OK, WISER sweep lands in the cohort folder,
worst-exit-code aggregation works. Note: CH07/CH08 report missing hours before 2026-07-07 (cams
were added mid-cohort) → early days exit rc=1 "copied (source had gaps)" — expected, still
recorded as saved.

## Usage
```powershell
powershell -ExecutionPolicy Bypass -File copy_cohort_to_usb.ps1 -Usb G: -Cohort cohort1 -ListOnly
powershell -ExecutionPolicy Bypass -File copy_cohort_to_usb.ps1 -Usb G: -Cohort cohort1
```
Cohort1 total ≈ E: usage ≈ 6.3 TB — the USB needs that much free (or run in stages with
`-StartFrom`/`-MaxDays` across multiple drives).
