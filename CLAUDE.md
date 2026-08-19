# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

PowerShell tooling for a **live 24/7 field recording rig** (2026 social behavior study). This PC is
the production machine: ffmpeg processes launched by Windows scheduled tasks are recording ~10 video
streams to `E:` right now. There is no build system, package manager, or test framework — every
script is standalone PowerShell 5.1 run via
`powershell -NoProfile -ExecutionPolicy Bypass -File <script>`.

## Live-system safety rules

- **Network topology (verified 2026-08-19): this field PC reaches ONLY the analysis PC**
  (`\\192.168.50.2\audio_in`, direct Ethernet). It has internet + GitHub, but NO route to the lab
  server or BioHPC (`cbsuruizfs1.biohpc.cornell.edu` resolves, ICMP+445 blocked — don't re-probe).
  Field→analysis backups use `copy_to_analysis.ps1 -Dest \\192.168.50.2\audio_in [-Date ...]`;
  cross-machine coordination goes through the `field2026-sync` repo (cloned OUTSIDE this tree).
- **Never kill ffmpeg or stop the recorder scheduled tasks** unless the user explicitly asks.
  Recorders self-heal (supervisor loops restart dropped streams); a stray `Stop-Process ffmpeg`
  interrupts real data collection.
- **Never write to, rename, or delete anything under `E:\Reolink_record` or `E:\thermal_record`.**
  QC/copy tools are deliberately read-only at the source; keep that property in any change.
- To read the size of a file ffmpeg is still writing, open a shared read handle
  (`[IO.File]::Open(..., ReadWrite share)`) — `Get-ChildItem .Length` reports a stale 0. This
  `Get-HandleLen` idiom appears in several scripts; reuse it.
- Retention/auto-delete is **OFF** (`RetentionDays = 0` since 2026-06-29). Nothing deletes footage
  automatically; the only sanctioned deletion path is `copy_day_to_usb.ps1` (writes a save log) →
  `delete_day.ps1` (refuses unless the day is in the save log).
- **PROTECT THE USB FABRIC — capture devices live on it.** Both UltraMics, the neurologger BLE
  dongle, AND the analysis-link USB-GbE ethernet adapter are USB. On 2026-08-19 a sustained file
  transfer through the USB ethernet adapter wedged an entire USB bank ("Port Reset Failed" on
  every port; needed a PC reboot) and killed both mics + the neurologger feed mid-cohort.
  Rules: (1) NEVER start a sustained/bulk transfer over the USB ethernet adapter without the
  user's explicit go-ahead in that moment — a short burst test passing does NOT prove a long
  transfer is safe on marginal hardware; (2) capture devices belong on direct PC root ports —
  no hubs, no passive extensions (a hub failed 3x on 2026-08-19; extensions killed MIC01 twice
  in cohort 1); (3) if a long transfer runs, watch mic growth during the first minutes and be
  ready to kill it; (4) after ANY USB replug/dislodge event, treat the whole USB fabric as
  suspect until devices re-verify.
- **Scheduled tasks execute scripts straight from working trees** — the QC/watchdog tasks from THIS
  repo ($PSScriptRoot defaults in the installers); the main video recorder still runs from the OLD
  pre-rename path `...\Field_2026_Social\reolink_record\` (task never re-registered). Scripts are
  read into memory at process start, so edits take effect on the NEXT restart, not immediately.
  During a live cohort this repo is outbound-only: `git add/commit/push` freely (read-only), but no
  `git pull/checkout/reset/clean` here. Cross-machine file exchange goes through the separate sync
  repo cloned OUTSIDE this tree, never through this one.

## Testing / verification conventions

Scripts share a flag vocabulary — use these instead of running things "for real":

- `-SelfTest` — offline logic test on synthetic data; no disk, no Slack, no ffmpeg.
- `-DryRun` — real inputs, prints what it would do, writes/sends nothing.
- `-TestSlack` — sends one test message to the configured Slack destinations.

Exit-code convention across QC scripts: `0` = pass, `1` = warnings only, `2` = errors.

## Architecture

Three layers, all driven by Windows scheduled tasks (each recorder/check has a matching
`install_*_task_system.ps1` installer that registers a SYSTEM task; run installers from an
elevated PowerShell):

**Recorders** — one supervisor script per camera family, each with its own single-instance
`Global\` mutex and task so they can't interfere with each other:
- `rtsp_record.ps1` — 8 Reolink NVR channels (CH01–CH08), task "Reolink RTSP Recorder" (at logon).
  CH07/08 moved from direct PoE onto the NVR on 2026-07-17; `archive/extra_cam_record.ps1` is the
  retired direct-IP recorder (its config on E: is renamed `.archived` so tools stop importing it).
- `thermal_record.ps1` — EmpireTech cameras 108/109 (thermal + visual streams) → `E:\thermal_record`.
- `failover_recorder.ps1` — dormant watchdog; if `E:` becomes unwritable it stops the primary task
  and records to `D:` (config/ffmpeg/Slack creds mirrored to `D:` by its installer). Failback is manual.

All recorders follow the same pattern: one `ffmpeg -c copy` process per stream (no re-encode),
hourly fragmented-MP4 segments aligned to the clock, a supervisor loop that restarts dead
processes and kills stalled ones (file not growing for ~240 s), and rename-on-close.

**Monitoring / QC** (all read-only; Slack alerts use the token in
`E:\recording_qc\overexposure.config.psd1`):
- `recording_health_check.ps1` — daily 05:00 coverage report from filenames + fs metadata only
  (~1 s; ffprobe only with `-ProbeSuspicious`/`-DeepCheck`) → `E:\recording_health_reports`.
- `recording_alive_check.ps1` — near-real-time "newest file stopped growing" Slack pager.
- `check_recording_continuity.ps1` — daily gap/overlap audit → `E:\recording_qc`.
- `overexposure_check.ps1` — hourly frame-exposure check (overexposed / near-black) with Slack alerts.
- `disk_space_check.ps1` — 50/80/90% full Slack warnings (built but task not installed as of 2026-06-29).
- `check_recording.ps1` — quick interactive status (is each stream growing right now?).

**Data lifecycle**: `copy_day_to_usb.ps1` (day → USB, save log) → `delete_day.ps1` (save-checked
delete); `copy_to_analysis.ps1` (robocopy everything to the analysis machine, copy-only flags
hard-blocked).

## The filename contract

Everything hinges on the segment naming scheme; QC, copy, and delete tools all parse it:

```
<group>_YYYY-MM-DD_HH-MM-SS_to_HH-MM-SS.mp4   finished (supervisor appends _to_<end> on rollover)
<group>_YYYY-MM-DD_HH-MM-SS.mp4               still recording (no "_to_")
```

The active segment must be found by **sorting on Name, not LastWriteTime** (write-time metadata is
lazy for the open file). Any file without `_to_` is treated as open and must never be touched.

## Configs and secrets

All credentials (NVR/camera passwords, Slack bot token) live in `*.config.psd1` files on `E:`
(`E:\Reolink_record\recorder.config.psd1`, `E:\thermal_record\thermal.config.psd1`,
`E:\Reolink_record\extra_cam.config.psd1`, `E:\recording_qc\overexposure.config.psd1`).
`.gitignore` excludes all `*.config.psd1`, `logs/`, and `*.mp4` — keep it that way. The only
config in-repo is `overexposure.config.example.psd1`.

## Repo quirks

- Each subsystem has its own `README_*.md`; read the matching one before changing a script. Some
  READMEs still reference the old path `...\Field_2026_Social\reolink_record\` and old `D:` drive
  roots — the repo now lives at `Field_2026_Social_Recording` and the primary recording drive is
  `E:` (with `D:` as failover); trust the script defaults over README paths.
- `logs/` is a gitignored snapshot of the field-PC operational logs, refreshed by
  `copy_logs_here.ps1` (read-only copy from `E:`); see `logs/_manifest.txt`.
- Ongoing field experiments are tracked in dated `EXPERIMENT_*.md` files at the repo root (currently
  the CH01/CH02 encoder CBR→VBR keyframe-truncation experiment) — check for one before touching
  camera/encoder settings.
- The user runs Windows PowerShell 5.1: no `&&`/`||`, no ternary; scripts must stay 5.1-compatible.
