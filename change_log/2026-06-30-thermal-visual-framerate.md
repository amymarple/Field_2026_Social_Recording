# Thermal Camera 109 Visual Stream — 30 fps → 1 fps (data-volume fix)

## Date

2026-06-30. Change is currently uncommitted (camera-side setting; no repo code changed).

## Summary

While confirming the field PC's daily data volume, the visual channel of thermal
camera **109** (`192.168.1.109`, channel 1) was found recording at **30 fps** — the
single largest stream on the whole rig at **~84 GB/day**, more than either Duo3
(CH01/CH02 ~77–79 GB/day). Every other thermal-cam stream was already ~1 fps. The
109 visual frame rate was lowered to **1 fps** in the camera web UI to match, cutting
it to **~12.6 GB/day** (**~71 GB/day saved**) with no loss of usable information for
its purpose (it exists only as a time-synced bridge for registering thermal into the
Reolink field frame, not for motion analysis).

## Diagnostic Context

Measured actual on-disk volume on `E:` (filename + filesystem metadata only, no
decode of recording files):

- Whole rig ≈ **397 GB/day** (Reolink 6ch ≈ 301 + thermal_record ≈ 96).
- Within `thermal_record`, the *thermal/IR* streams are trivial (~6.9 GB/day total);
  the **visual** streams are ~93% of that subsystem.
- Per stream (2026-06-29), with resolution / rate from `ffprobe`:

  | Stream | Resolution | fps | GB/day |
  |---|---|---|---|
  | 108_thermal | 1280×960 | ~1 | ~1.0 |
  | 108_visual | 2336×1752 | ~1 | ~5.0 |
  | 109_thermal | 1280×960 | ~1 | ~5.8 |
  | **109_visual** | **2336×1752** | **~30** | **~84.1** |

  108_visual was already at 1 fps; only 109_visual was the outlier.

## What Changed

- **Camera 109, channel 1 (visual) main stream:** frame rate **30 fps → 1 fps**, set
  in the EmpireTech/Dahua camera web UI. Resolution left unchanged at 2336×1752.
- **No repo code changed.** `E:\thermal_record\thermal.config.psd1` still pulls
  `rtsp://…@192.168.1.109:554/cam/realmonitor?channel=1&subtype=0` (main stream) with
  `ffmpeg -c copy`; the recorder just receives fewer frames on the same session.
- **No recorder restart required.** A frame-rate change (unlike a resolution change)
  does not alter SPS/PPS, so the running `ffmpeg -c copy` session picked it up live —
  confirmed by the open file's growth rate dropping immediately (see Verification).

## Data Provenance (effective boundary)

- **`109_visual` becomes an effective ~1 fps time-lapse from ~22:00–22:03 local on
  2026-06-30 onward.** Footage before that boundary is 30 fps; after, ~1 fps.
- Treat 109_visual as a **registration / visual-reference bridge only** — do **not**
  use it for motion, velocity, or CV tracking after the boundary. The thermal channel
  (109_thermal) and its use are unaffected.

## Verification

Live, capture-safe checks (no new RTSP session to the camera; the open recording file
was read via filesystem metadata only, never its content):

- **Before:** `ffprobe` of the last closed 30-fps file
  `109_visual_2026-06-30_21-00-00_to_22-00-00.mp4` → 2336×1752, `avg_frame_rate`
  ≈ **30.05 fps**, bit_rate ≈ **6.88 Mbps** (~3.4 GB/hour).
- **After:** sampled the open file `109_visual_2026-06-30_22-00-00.mp4` growth over
  30 s = 4,718,592 bytes → **~1.2 Mbps ≈ 0.53 GB/hour ≈ ~12.6 GB/day**, a ~5–6× drop,
  consistent with 30→1 fps at `-c copy` (bitrate does not scale linearly with fps).
- **Pending confirmation:** definitive `avg_frame_rate` will read ~1 fps on the first
  fully-closed post-change file (`…22-00-00_to_23-00-00.mp4`) once it finalizes.

## Impact

| | Before | After |
|---|---|---|
| 109_visual | ~84 GB/day | ~12.6 GB/day |
| Whole rig | ~397 GB/day | **~326 GB/day** |
| `E:` fill from ~18.3 TB free | ~43 days | **~56 days** |
| Full season (~150 days) | ~64 TB | **~49 TB** |

Auto-delete remains intentionally OFF, so this directly extends the runway between
USB offloads (`copy_day_to_usb.ps1` → `delete_day.ps1`) and the
`disk_space_check.ps1` 50/80/90% alerts.

## Known Limitations & Follow-ups

- **Resolution deliberately not reduced.** Dropping 109/108 visual from 2336×1752 to
  ~thermal resolution would save only ~12 GB/day (~3% of the total) while degrading
  the landmark detail the visual stream exists for (thermal→field registration).
  Decided to keep resolution and stop at the fps fix. If reduced later, do it in the
  camera UI **and restart the thermal recorder task** — a resolution change alters
  SPS/PPS and will not apply cleanly to a running `-c copy` session.
- Confirm `avg_frame_rate` ≈ 1 on the first closed post-change file (above).
- Consider a QC check that flags any thermal-cam stream whose per-hour size jumps
  (e.g. a camera reverting to 30 fps after a reboot), analogous to the continuity and
  stall alerts.
