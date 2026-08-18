# 2026-07-17 — CH07/CH08 moved from direct PoE onto the NVR (all 8 channels unified)

## What changed
Two new Reolink cameras were connected to NVR ports 7/8, replacing the previous direct-IP
in-box sleep cams for CH07/CH08. All video now flows through the one NVR:
**CH01–CH08 = `rtsp://<nvr>/Preview_0N_main`**.

- `E:\Reolink_record\recorder.config.psd1`: `Channels = @(1..8)` (backup kept as
  `recorder.config.psd1.bak_pre_ch78`). `rtsp_record.ps1` is fully channel-list-driven —
  zero code change; output continues into the existing `CH07`/`CH08` folders under the same
  filename contract, so every QC/copy/delete tool picks the new feeds up automatically.
- `E:\Reolink_record\extra_cam.config.psd1` → renamed `.archived` (stops the GUI recorder and
  any tool from importing the dead direct-IP URLs; reversible).
- Repo: `extra_cam_record.ps1`, `install_extra_cam_task_system.ps1`, `README_extra_cam.md`
  moved to `archive/` (both repos). The "Field Extra Cam Recorder" task was already deleted
  post-experiment.

## Verified
- ffprobe on the NVR: `Preview_07_main` / `Preview_08_main` both live — **2560×1920 H.264
  @ 20 fps** (5 MP class; small keyframes → no Duo3-style keyframe-cap risk).
- GUI recorder SelfTest: discovers CH01–CH08 all as NVR + 4 thermal streams; no stale EXTRA
  rows; nothing was recording during the swap (0 ffmpeg).

## Consequences to remember
- The NVR is now a single point of failure for ALL eight video channels (weekly Sun ~13:00
  NVR reboot gap now includes CH07/08; NVR uplink carries 8 streams). Thermal 108/109 remain
  direct-IP and independent.
- Recording remains OFF (post-experiment). The next `Start-ScheduledTask 'Reolink RTSP
  Recorder'` (or GUI Start All) records all 8 channels.
- Historical note for analysis: files in `CH07`/`CH08` before 2026-07-12 are the in-box sleep
  cams (Dahua, direct-IP); files after 2026-07-17 are the new NVR-fed Reolink cams — same
  folder, different camera/view.
