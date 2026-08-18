# Interactive GUI recorder (click Start / click Stop)

`interactive_recorder_gui.ps1` — a WinForms desktop app (PowerShell 5.1, no dependencies) that
records RTSP security cameras interactively. **Not a system service**: it runs in your session,
one click starts recording for every discovered camera, one click stops. Built after the
2026-07-12 experiment end as the manual/ad-hoc counterpart to the scheduled-task recorders.

## Camera architecture (cross-checked 2026-07-14)

The rig has **two kinds of camera plumbing** — some streams are *bridged through the NVR*,
others are pulled *directly from the camera's own IP*:

| cameras | path | RTSP source | config |
|---|---|---|---|
| CH01–CH06 (Reolink paddock) | **NVR-bridged** | `rtsp://<nvr>:554/Preview_0N_main` (single NVR IP serves all 6) | `E:\Reolink_record\recorder.config.psd1` |
| CH07/CH08 (in-box sleep cams) | **direct-IP** | `rtsp://<cam-ip>:554/cam/realmonitor?...` (Dahua format, one IP each) | `E:\Reolink_record\extra_cam.config.psd1` |
| 108/109 (EmpireTech, thermal+visual = 4 streams) | **direct-IP** | `rtsp://<cam-ip>:554/cam/realmonitor?channel=1|2...` | `E:\thermal_record\thermal.config.psd1` |

The GUI auto-imports **all 12 streams** from those three configs (plus any custom cameras you
add to `gui_recorder.config.psd1`). Practical difference: if the NVR is down, CH01–06 all drop
together while CH07/08 and 108/109 keep working — the GUI shows that per row.

## Launch

Double-click `launch_gui_recorder.cmd`, or:
```powershell
powershell -STA -ExecutionPolicy Bypass -File .\interactive_recorder_gui.ps1            # open GUI
powershell -STA -ExecutionPolicy Bypass -File .\interactive_recorder_gui.ps1 -AutoStart # open + Start All
.\interactive_recorder_gui.ps1 -SelfTest                                                # headless check, no GUI
```

## What it does
- **Start All / Stop All / per-camera Start/Stop (select rows)**. One `ffmpeg -c copy` per
  stream (no re-encode), RTSP over TCP, hourly fragmented-MP4 segments split on the clock
  hour — same proven recipe as the production recorders.
- Output: `E:\gui_record\<Camera>\<Camera>_YYYY-MM-DD_HH-MM-SS.mp4` + per-camera ffmpeg logs
  under `E:\gui_record\logs\`. Deliberately **separate** from `E:\Reolink_record` so the
  QC/copy/delete tooling never mixes GUI footage with production footage (GUI files have no
  `_to_` finalize-rename).
- Live status every 5 s: RECORDING (green), STALLED (orange, auto-restarts — uncheckable),
  SERVICE (blue), STOPPED. Shows current file + size.
- Closing the window asks: stop GUI recordings, or leave them running detached.

## Safety against the production recorders
- A camera already recorded by a scheduled-task recorder shows **SERVICE (blue)** and the GUI
  **skips Start and refuses Stop** for it — it never double-pulls a stream (double-pulling
  doubles camera/NVR load) and never kills service-owned ffmpeg.
- Service detection works without admin rights: it checks for a freshly-modified mp4 in the
  camera's production folder (SYSTEM process command lines are invisible to a user session),
  plus process command-line matching when visible.
- Single-instance mutex: a second GUI copy refuses to open.

## Config (optional)
Defaults work out of the box. To customize (add security cams, change output root), copy
`gui_recorder.config.example.psd1` → `gui_recorder.config.psd1` (gitignored — custom camera
URLs contain credentials) and edit.
