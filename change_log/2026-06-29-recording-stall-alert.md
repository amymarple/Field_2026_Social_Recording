# Recording-Stall Slack Alert

## Date

2026-06-29. Change is currently uncommitted.

## Plan

Implemented from
[`implementation_plan/2026-06-29-recording-stall-alert.md`](../implementation_plan/2026-06-29-recording-stall-alert.md).

## What Changed

- Added `reolink_record/recording_alive_check.ps1` — near-real-time watchdog that
  Slack-alerts when any recording group stops growing.
  - Signal is **file growth** (newest `*.mp4` `LastWriteTime` age per group), not
    process/task state — so it catches "recorder up but writing nothing" (the
    2026-06-29 NVR-IP outage class).
  - Watches Reolink `CH01–CH06` (`E:\Reolink_record`) and thermal
    `108/109_{thermal,visual}` (`E:\thermal_record`); groups auto-discovered.
  - A group is stalled if its newest file age > `-StaleMinutes` (default 10) or it has
    no files. Sends ONE aggregated alert listing all stalled groups.
  - De-dup/state mirrors `disk_space_check.ps1`: alert on healthy→stalled, re-alert at
    most every `-RealertHours` (default 1) while stalled, recovery note when all healthy.
    State + log under `E:\recording_qc\`.
  - Reuses the Slack creds in `E:\recording_qc\overexposure.config.psd1`
    (`SlackBotToken`, `SlackChannels` = team channel + Hongyu DM, `SendRecovery`).
  - Switches: `-DryRun`, `-TestSlack`, `-SelfTest` (offline synthetic-group logic check).
- Added `reolink_record/install_recording_alive_check_task_system.ps1` — registers a
  SYSTEM task **"Field Recording Alive Check"** running every 5 min (clone of the
  disk-space installer; self-checks elevation).

## Why

The 2026-06-29 outage (NVR IP changed → all 6 Reolink channels stopped for ~2h46m; see
[`2026-06-29-nvr-ip-change-recording-gap.md`](2026-06-29-nvr-ip-change-recording-gap.md))
produced no alert: the recorder stayed "running," and existing QC is daily (continuity
reports) or watches other signals (disk space, overexposure). This adds the missing
near-real-time "recording stopped" alarm.

## Verification

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File reolink_record\recording_alive_check.ps1 -SelfTest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File reolink_record\recording_alive_check.ps1 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File reolink_record\recording_alive_check.ps1 -TestSlack
```

Observed 2026-06-29:

- `-SelfTest`: **PASS** — correctly flagged a synthetic 20-min-stale group + an empty
  group, ignored the fresh one.
- `-DryRun` against live recordings: **0/10 groups stalled**; all six Reolink channels
  and four thermal groups reported ages 0–0.3 min.
- `-TestSlack`: **delivered** to the team channel + DM.

## Known Limitations / Follow-ups

- **Install pending (needs elevation):** run
  `install_recording_alive_check_task_system.ps1` from an **Administrator** PowerShell to
  register the SYSTEM task (this session was non-elevated). Until then the watchdog is not
  yet scheduled.
- Detection latency ≈ 10–15 min after a real stop (5-min task + 10-min stale threshold).
  Raise `-StaleMinutes` if the Sunday NVR reboot ever produces a false alert.
- Alert-only by design — it never touches recordings or the recorder.
- Does not watch WISER UWB liveness (separate subsystem/clock).
