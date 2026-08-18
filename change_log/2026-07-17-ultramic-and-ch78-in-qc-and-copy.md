# 2026-07-17 — UltraMic + new CH07/08 wired into alive-check and copy tooling; CH07/08 tested live

## CH07/CH08 end-to-end capture test (new NVR-fed cams)
Started GUI-identical ffmpeg captures for both channels (`Preview_07/08_main`, `-c copy`,
hourly fragmented segments): ~5 min each, steady growth (~5–7 Mbps), stopped cleanly,
files play (283.9 s / 284.2 s, ffprobe OK). Frames confirm both are **RLC-520A in-box
sleep cams** (box interiors, numerals visible). OSD clock is the NVR's (~1 h behind PC),
same as CH01–06. Test files kept in `E:\gui_record\CH07|CH08\`.

## recording_alive_check.ps1
- New `-UltramicRoot` (default `E:\ultramic_record`), discovers `MIC*` folders.
- Age check now accepts `.wav`/`.flac` alongside `.mp4`.
- SelfTest extended: fresh MIC01 wav counts as alive, stale MIC02 wav pages — PASS.
- Live DryRun: 13 groups (8 video + 4 thermal + MIC01); MIC01 showed `ok(0.2m)` —
  the UltraMic was actively recording during the test.
- CH07/CH08 needed nothing: folder-driven discovery already covers them.

## copy_day_to_usb.ps1 (inherited by copy_cohort_to_usb.ps1 automatically)
- `SourceRoots` default now includes `E:\ultramic_record`.
- `$Extensions` now `.mp4/.wav/.flac`. The mic's hourly WAV segments follow the same
  filename contract, so verify/completeness/save-log all apply unchanged.

Mirrored to `Field_2026_Social\reolink_record\`. Reinstall note: the alive-check task was
deleted post-experiment — when the next cohort starts, re-run
`install_recording_alive_check_task_system.ps1` and the mic is watched automatically.
