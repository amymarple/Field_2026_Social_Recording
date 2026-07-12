# 2026-07-11 — Duo 3 capped-keyframe fix + daily regression monitor

## Problem
Reolink Duo 3 (CH01/CH02, 2160×7680 HEVC panorama) firmware hard-caps intra keyframes at
**2,000,090 bytes** and truncates bigger ones bottom-first: the bottom band of the panorama
becomes stale/phantom for the whole GOP. Worst at golden hour (raking light = max scene
detail): on 2026-07-10 the 17:00 hour had **80.5% of footage time** inside damaged GOPs,
with up to ~23% of frame height lost, GOPs stretched to 78 s. GPU players conceal the damage
with recycled decoder surfaces, so it was invisible in playback; software decode / CV sees it.

## Fix (camera-side; recorder is `-c copy` and cannot repair)
Two steps on CH01+CH02 main stream (resolution/fps/color unchanged), applied on the fly with
zero recording gap:
1. 2026-07-09 ~22:00 — CBR 10044 → **VBR max 12288**: fixed midday, NOT golden hour.
2. 2026-07-11 ~14:52 — VBR max **12288 → 8192**: peak-hour keyframes now mean ~1.5 MB,
   capped GOPs 80.5% → **1.7% (CH01) / 5.4% (CH02)**, residual cuts only ~600 bottom rows
   for ~2 s each. GOP cadence back to steady 2 s. Bonus: ~35% smaller files.
CH03–CH06 scanned (peak hour): max keyframes at 35–63% of the cap, no signature — left unchanged.

## New monitor
`reolink_record/capped_keyframe_check.ps1` (+ `install_capped_keyframe_check_task_system.ps1`,
`README_capped_kf.md`; mirrored into the Field_2026_Social_Recording repo): daily 05:20 SYSTEM
task scans yesterday's CH01/CH02 hours 12/16/17 (closed files only, read-only, packet metadata),
logs to `E:\recording_qc\capped_kf_history.csv`, Slack-alerts at ≥10% capped keyframes.
Also detects a *changed* cap value generically (byte-identical max repeated ≥20×).
Verified: `-SelfTest` PASS; dry-run on 2026-07-10 17:00 correctly alerts (56%); dry-run on
2026-07-11 17:00 correctly quiet (1.7/5.4%); `-TestSlack` DM delivered.

## CV implication
Historical footage (≤2026-07-11 ~14:52, daytime CH01/CH02) must mask capped GOPs
(`find_capped_gops()` / `CAPPEDGOP_` labels): the panorama's bottom band there is phantom data.
Full experiment record: `EXPERIMENT_encoder_bitrate_2026-07-09.md` (recording repo).
