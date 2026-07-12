# Capped-keyframe monitor (Duo 3 truncation regression alarm)

`capped_keyframe_check.ps1` — daily, read-only scan of **yesterday's** CH01/CH02 stress
hours (05, 12, 17, 19, 20 — dawn/dusk gain-ramps are the worst, then golden hour) for the
**Duo 3 keyframe cap**: the camera firmware hard-limits
intra keyframes to ~**2,000,090 bytes** and silently truncates bigger ones **bottom-first**,
so the bottom band of the panorama becomes stale/garbage for the whole GOP. Players conceal
it (GPU decoders recycle stale surfaces), so without this check the damage is invisible
until CV trips over phantom data.

Fixed on 2026-07-11 by setting CH01/CH02 main stream to **VBR, max 8192 kbps**
(peak-hour damage fell from ~80% of footage time to ~2–5% of GOPs with only a thin
bottom sliver lost). Full story: `EXPERIMENT_encoder_bitrate_2026-07-09.md` in the
recording repo. This task exists to catch **regression** — firmware updates, settings
drift, or scene complexity creep.

## What it does
- Scans only **closed** `*_to_*.mp4` files (never the open/recording one); ffprobe packet
  metadata, one sequential read pass per file. Handles stall-split hours (sums segments).
- Two detectors per hour: keyframes at exactly the known cap, **plus** generic "pinning"
  (any byte-identical repeated max ≥20×) to catch a *different* cap value after a
  firmware change.
- Appends every result to `E:\recording_qc\capped_kf_history.csv` + `capped_kf_log.txt`.
- **Slack alert when ≥10%** of an hour's keyframes are capped (uses `CappedKfChannels`
  from `E:\recording_qc\overexposure.config.psd1`, falling back to `SlackChannels`).

## Install (elevated Administrator PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\install_capped_keyframe_check_task_system.ps1" -RunNow
```
Registers SYSTEM task **Field Capped Keyframe Check**, daily **05:20** (after the 05:00
health report). `-RunNow` also runs it once immediately for verification.

## Test without side effects
```powershell
.\capped_keyframe_check.ps1 -SelfTest                       # offline logic check
.\capped_keyframe_check.ps1 -DryRun                         # scan yesterday, print only
.\capped_keyframe_check.ps1 -Date 2026-07-10 -Hours 17 -DryRun   # known-bad day -> alert text
.\capped_keyframe_check.ps1 -TestSlack                      # one test DM
```

## If the alert fires
1. Check CH01/CH02 main-stream encode settings: should be **VBR, max 8192 kbps**,
   2160×7680, H.265 (a firmware update or NVR reset may have reverted them).
2. Settings correct but still capping (e.g., seasonal scene complexity)? Step the max
   bitrate down once more: **8192 → 6144** on the affected channel.
3. Resolution reduction is the last resort only — never needed so far.
4. For affected historical footage, CV must mask capped GOPs
   (`find_capped_gops()` / `CAPPEDGOP_` labels) — the bottom band there is phantom data.
