# Experiment END — all recording stopped (2026-07-12 15:00)

**When:** 2026-07-12 ~15:00 field-PC local time (recorders killed, verified, ~15:14).
**Action:** Field experiment ended *for now*. All RTSP video recording stopped and every
alert/QC task disabled.

## What was done (in order)

1. **Disabled all alert/QC Slack tasks first** — recording-alive (RECORDING STOPPED), disk-space,
   overexposure, continuity, daily health check, and the WISER coverage alert — so stopping the
   recorders would not trigger a "RECORDING STOPPED" Slack flood.
2. **Stopped + disabled the 3 RTSP recorder tasks:** Reolink RTSP Recorder (CH01–06),
   EmpireTech Thermal Cameras Recorder (108/109), Field Extra Cam Recorder (CH07/CH08).
3. **Killed all ffmpeg** — 12 → **0**. Verified: streaming stopped, per-channel files frozen.
4. Tasks are **DISABLED, not deleted** — reversible for a future experiment.

## State at stop

- Last file per channel is the in-progress (no `_to_`) segment, closed cleanly by the kill —
  fragmented MP4 survives an abrupt stop, so they are valid/playable. When backing up the final
  day (2026-07-12), use `copy_day_to_usb.ps1 -IncludeActive` to include those.
- All recorded data intact on `E:\Reolink_record` and `E:\thermal_record`.
- **WISER data acquisition was NOT stopped** (separate, non-RTSP system); only its coverage
  *alert* was silenced.

## To resume for a future experiment

Re-enable + start the recorder tasks (`Enable-ScheduledTask` + `Start-ScheduledTask` on each),
re-enable the alert tasks, or simply re-run the `install_*_task_system.ps1` installers.

## Notes

- `Field_2026_Social_Recording` is now the **main repository for the recording/capture subsystem**;
  the recording change-logs live under `change_log/` here. Field-PC operational logs are snapshotted
  into the git-ignored `logs/` via `copy_logs_here.ps1` (not committed by design).
