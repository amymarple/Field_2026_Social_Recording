# 2026-07-14 — Interactive GUI recorder (click Start / click Stop)

## What
`interactive_recorder_gui.ps1` (+ `launch_gui_recorder.cmd`, `gui_recorder.config.example.psd1`,
`README_gui_recorder.md`) — a WinForms interactive recorder, the manual counterpart to the
scheduled-task recorders now that the experiment ended (see `EXPERIMENT_END_2026-07-12.md`).
Also mirrored in `Field_2026_Social\reolink_record\`.

## Cross-checked camera architecture (per user request)
Two plumbing kinds, three configs, 12 streams total:
- **NVR-bridged**: CH01–CH06 → `rtsp://<nvr>/Preview_0N_main` (recorder.config.psd1; one NVR IP
  serves all six — NVR down = all six down together)
- **direct-IP**: CH07/CH08 sleep cams (extra_cam.config.psd1, Dahua URL format)
- **direct-IP**: 108/109 EmpireTech thermal+visual = 4 streams (thermal.config.psd1)
The GUI auto-imports all three configs plus custom cameras from its own (gitignored) config.

## Behavior
One `ffmpeg -c copy` per stream, RTSP/TCP, hourly fragmented-MP4 clock-aligned segments (the
production recipe) to `E:\gui_record\<Name>\` (separate from production roots so QC/copy/delete
tooling never sees GUI footage; no `_to_` rename). 5 s status timer (file growth, size), stalled
recordings auto-restart, close-dialog offers stop-all vs leave-running.

## Safety
- Never double-pulls: a camera recorded by a service task shows SERVICE and is skipped/locked.
  Detection is file-activity in the production folder (newest mp4 < 150 s old) because SYSTEM
  ffmpeg command lines are invisible to a non-admin session; command-line match is used when visible.
- Stop All only kills GUI-owned ffmpeg (matched by GUI output path in the command line).
- Single-instance mutex `Global\FieldGuiRecorder`.

## Verified
`-SelfTest` (both repo copies): ffmpeg found; **12 cameras discovered** (6 NVR + 2 EXTRA +
4 THERMAL) with correct URLs (creds masked in display); output root writable; all streams
correctly classified STOPPED in the post-experiment state. GUI itself not click-tested yet —
user will double-click `launch_gui_recorder.cmd`.
