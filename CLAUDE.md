# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Tooling for a **live 24/7 field recording rig** (2026 social behaviour study: rats in an outdoor
40 x 20 ft paddock) plus the camera-calibration work that maps every camera into one paddock frame.

- **PowerShell side** (repo root): recorders, watchdogs, QC and copy tools. Every `.ps1` is
  standalone Windows PowerShell 5.1, run as `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`.
  No build step, no package manager, no test framework - the `-SelfTest`/`-DryRun` flags below are
  the test surface.
- **Python side**: `camera_ground/` (installable package, `pyproject.toml`, unittest tests) and
  `calibration_qc/` (flat script collection that produced the accepted calibration). See
  "Camera calibration" and "Python commands".

On the field PC, ffmpeg processes launched by Windows scheduled tasks are recording 12 video streams
(8 NVR channels + 2 thermal cameras x 2 streams) and 2 ultrasound mics to `E:` right now.

## Which machine you are on - check before anything else

The field PC checkout is `C:\Users\Cornell\Documents\GitHub\Field_2026_Social_Recording`; its
markers are `E:\Reolink_record`, `E:\calibration`, `E:\recording_qc` and `C:\Users\Cornell`. If they
are absent you are on an analysis PC or laptop clone. That changes three things and nothing else:

- The live-surface rules below still bind wherever those paths are reachable (e.g. via a share),
  but the field-PC git restriction ("outbound only") does not apply to other clones.
- `calibration_qc` scripts find their data root through `qc_paths.py` (`$CALIB_ROOT`, then
  `E:\calibration`, then `<repo drive>:\calibration`, then any drive) and ffmpeg likewise
  (`$FFMPEG_DIR`, `E:\Reolink_record\bin`, `<root>\bin`, PATH, winget). The portable drive holds
  `calibration\` (data + `bin\` ffmpeg) next to a clone of this repo, so the calibration work runs from
  the drive on any computer; USING the released calibration (`paddock_map.load()`) also works from the
  committed copy alone. Git on the drive needs a one-time
  `git config --global --add safe.directory <drive>:/Field_2026_Social_Recording`.
- The PreToolUse guard hook does not run: `.claude/settings.json` hard-codes the field-PC path, and
  the override flag lives in `C:\Users\Cornell\.claude\`. The hook's absence is never permission.

## Language of everything written down

All files in this repo - EXPERIMENT files, logs, READMEs, plans, commit messages, code comments - and the field
logs it mirrors (the E: incident log, the field2026-sync notes) are written in **English**. Chinese is only the
chat language with the operator; never write Chinese into a file. (Operator rule, 2026-09-10.) Three files
from 2026-09-09 predate the rule and are in Chinese (`camera_ground/README.md`,
`CAMERA_CALIBRATION_AUDIT_PLAN.md`, `AUDIT_RESPONSE_2026-09-09.md`); anything added to them is still English.

## Field logging (rounds, anchors, probe moves, incidents, behaviour)

Follow the project skill `/field-log` (`.claude/skills/field-log/SKILL.md`). In short: verify from the console
log / telemetry first, write the full entry into `E:\recording_health_reports\incident_log.md` (mirrored into the
sync repo), battery facts into `BATTERY_LOG_cohort3.md`, animal behaviour into the Notion behaviour table plus
`field2026-sync/from-field/behaviour_observations_cohort3.csv`, and only a 4-8 line digest with
`Details → incident_log HH:MM` pointers into the Notion day row. Nothing is deleted from Notion without a verbatim
archive first (`NOTION_OBSERVATION_LOG_ARCHIVE_cohort3.md`). (Operator rule, 2026-09-10.)

## Detection / computer vision on the footage

Follow the project skill `/detect-then-decode` (`.claude/skills/detect-then-decode/SKILL.md`) for any
detection task (board, cone, marker, animal, LED). In short: a detector's silence is a statement about
the detector, never about the field - render the frame and look before writing "not detected", measure
instead of guessing a cause, locate the object before decoding its content, degrade to a weaker
measurement rather than to "absent", and treat the operator as a required stage (identity comes only
from the operator's timeline; "not present" is only ever the operator's statement). The account of the
failure that produced this rule is `calibration_qc/DETECTION_POSTMORTEM_2026-09-19.md`.
(Operator rule, 2026-09-19.)

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
- **LIVE PRODUCER SURFACES ARE NOT ANALYSIS SURFACES — "read-only" is NOT "harmless".**
  Two agent-caused data losses on 2026-08-19 prove it; operator order: never again.
  (1) **Never open the live WISER DB (`D:\Wiser\data\*.sqlite`) — no query, no Read, no
  Get-Content, ever.** It runs in SQLite rollback-journal mode: any reader's SHARED lock
  blocks the wiserex writer's commits, and past its 5 s busy_timeout the fixes are DROPPED
  (a 2-min unindexed query cost 150 s of tracking, 18:26–18:29). Analysis reads go to the
  `E:\Wiser_backup` snapshots (daily 13:00 task); a plain directory listing is the only
  allowed touch. (2) **Never touch an OPEN segment under `E:\Reolink_record` /
  `E:\thermal_record` / `E:\ultramic_record` / `E:\nvr_rescue` / `E:\WILD`** (operator
  order 2026-08-19 evening: "don't read a file that is actively writing"). The filename
  contract identifies them: a `.mp4`/`.wav` **without `_to_`** is still being written — no
  Read, Get-Content, ffprobe, hash, copy, or open-handle probe on it (wildcards like `*.wav`
  sweep it in too). Closed (`_to_`) segments, logs, and configs may be read directly, but
  keep bulk content sweeps short/gentle — a sustained read job starved recorder writes and
  caused the 01:40–03:21 eight-channel outage. **Sole exception:** the user explicitly asks
  for a live stream check in that moment → arm the 15-minute override flag
  (`New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force`), which
  unlocks open-segment reads (incl. Get-HandleLen) but NEVER `D:\Wiser\data`. Both rules are
  mechanically enforced by the PreToolUse hook `.claude/hooks/guard_live_surfaces.ps1` (wired
  in `.claude/settings.json`); it is text-based and cannot see indirect reads through
  scripts, so the rule binds even where the hook is blind — never work around it.
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
  During a live cohort the field-PC checkout is outbound-only: `git add/commit/push` freely
  (read-only), but no `git pull/checkout/reset/clean` there. Cross-machine file exchange goes
  through the separate sync repo cloned OUTSIDE this tree, never through this one.

## Testing / verification conventions (PowerShell)

Scripts share a flag vocabulary — use these instead of running things "for real". Not every script
has every flag; check its `param()` block:

- `-SelfTest` — offline logic test on synthetic data; no disk, no Slack, no ffmpeg (15 scripts).
- `-DryRun` — real inputs, prints what it would do, writes/sends nothing (18 scripts).
- `-TestSlack` — sends one test message to the configured Slack destinations (8 scripts).
- Script-specific: `-Once` (failover), `-Status` (weather listener), `-ListDevices` / `-TestClip N`
  (ultramic), `-Enable` / `-Exclude` (stop_all_recording).

Exit-code convention across QC scripts: `0` = pass, `1` = warnings only, `2` = errors.

## Python commands

The only automated tests in the repo are the `camera_ground` unittest suite (synthetic data only;
run from the repo root):

```powershell
pip install -r camera_ground/requirements.txt      # or: pip install -e .   (package field-camera-ground)
python -m unittest camera_ground.test_calibration camera_ground.test_cli -v
python -m unittest camera_ground.test_calibration.Tests.test_seam_hole_not_bridged -v   # one test
python -m camera_ground --help                     # also installed as the `camera-ground` console script
```

`calibration_qc/` scripts are run from inside that folder (they `sys.path`-import each other) in
the field PC's `cv` conda env or any Python 3.10+ with numpy, scipy, opencv-contrib-python and
matplotlib; every one accepts `--session <dir|YYYY-MM-DD>` (resolved by `qc_paths.py`; default is
the 2026-09-18 session). Never run `fit_cameras.py` without `--out`: its default output is the repo
folder, i.e. the committed release.

```powershell
cd calibration_qc
python qc_placements.py CH03 --every 1 --session 2026-09-19   # corners per camera
python show_frame.py CH03 15:20:00 --around T12               # look before writing "missing"
python fit_cameras.py --out <dir>                             # -> camera_fit.npz + fit_manifest.json + CALIBRATION_FIT.txt
python frame_correction.py --fit <dir>\camera_fit.npz          # -> frame_correction.json next to it; rerun after EVERY refit
python cv_folds_eval.py                                       # the held-out numbers quoted in the report
```

## Architecture

Three PowerShell layers, all driven by Windows scheduled tasks. Each recorder/check has a matching
`install_*_task_system.ps1` that registers a SYSTEM task (run installers from an elevated
PowerShell). Task names follow `Field <Thing>` except the legacy `Reolink RTSP Recorder`,
`EmpireTech Thermal Cameras Recorder` and `Recording Health Check`; the authoritative list is the
`$tasks` array in `stop_all_recording.ps1`, which is also how a cohort is shut down (disable + stop
everything, kill ffmpeg) and brought back (`-Enable`).

**Recorders** — one supervisor script per capture family, each with its own single-instance
`Global\` mutex and task so they can't interfere with each other:
- `rtsp_record.ps1` — 8 Reolink NVR channels (CH01–CH08), task "Reolink RTSP Recorder" (at logon).
  CH07/08 moved from direct PoE onto the NVR on 2026-07-17; `archive/extra_cam_record.ps1` is the
  retired direct-IP recorder (its config on E: is renamed `.archived` so tools stop importing it).
- `thermal_record.ps1` — EmpireTech cameras 108/109 (thermal + visual streams) → `E:\thermal_record`.
- `ultramic_record.ps1` + `ultramic_wasapi_capture.ps1` — Dodotronic UltraMic384K mics. One WASAPI
  capture child per mic (C# embedded in PowerShell; ffmpeg's DirectShow path caps the mic at 96 kHz)
  → hourly WAVs under `E:\ultramic_record\MICxx\`, same filename contract as video.
- `failover_recorder.ps1` — dormant watchdog; if `E:` becomes unwritable it stops the primary task
  and records to `D:` (config/ffmpeg/Slack creds mirrored to `D:` by its installer). Failback is manual.
- `weather_listener.ps1` — HTTP endpoint the Ambient Weather console posts to ("Customized upload",
  Ecowitt or Wunderground protocol) → daily CSVs in the ambientweather.net export schema under
  `D:\weather_data\local` (+ raw JSONL). Task "Field Weather Listener", port 8085, local subnet
  only. Exists because the cloud never backfills a console outage (18 h lost 2026-09-02).
  `README_weather_listener.md` has the console settings.
- `led_sync.ps1` — pulses an LED on a Raspberry Pi Pico (USB serial) at 1 Hz from the PC clock and
  logs every rising edge; the LED is in the cameras' view and wild_console stamps ephys with the
  same clock, so this is the video↔ephys common timebase.
- Not services: `calibration_record.ps1` (one-shot console recorder of all 12 streams to
  `E:\calibration\session_<timestamp>` for calibration sessions, reuses the production configs,
  Ctrl+C to stop) and `interactive_recorder_gui.ps1` (WinForms Start/Stop for ad-hoc recording).

All recorders follow the same pattern: one `ffmpeg -c copy` process per stream (no re-encode),
hourly fragmented-MP4 segments aligned to the clock, a supervisor loop that restarts dead
processes and kills stalled ones (file not growing for `$StallSeconds` = 240), and rename-on-close.

**Monitoring / QC** (all read-only; Slack alerts use the token in
`E:\recording_qc\overexposure.config.psd1`):
- `recording_health_check.ps1` — daily 05:00 coverage report from filenames + fs metadata only
  (~1 s; ffprobe only with `-ProbeSuspicious`/`-DeepCheck`) → `E:\recording_health_reports`.
- `recording_alive_check.ps1` — near-real-time "newest file stopped growing" Slack pager.
- `check_recording_continuity.ps1` — daily gap/overlap audit → `E:\recording_qc`.
- `overexposure_check.ps1` — hourly frame-exposure check (overexposed / near-black) with Slack alerts;
  two tasks, "(Finished)" hourly and "(Sunrise Active)" at 08:10/08:30/08:50.
- `capped_keyframe_check.ps1` — daily ffprobe (packet metadata only) of yesterday's closed CH01/02
  segments for the Duo 3 firmware's ~2 MB keyframe cap that truncated the bottom band in cohort 1.
- `disk_space_check.ps1` — 50/80/90% full Slack warnings.
- `check_recording.ps1` — quick interactive status (is each stream growing right now?).
- Neurologger (CE64X ephys loggers, BLE via wild_console): `neurologger_alive_check.ps1` pages
  "LOGGER MISSING" from wild_console's snapshot CSV and appends the 5-min telemetry history;
  `neurologger_battery_forecast.ps1` (twice daily) reads only that history and forecasts who
  auto-stops when; `neurologger_connected_log.ps1` turns connected-mode heartbeats in
  `ble_messages.csv` into telemetry (FM63 firmware froze advertisement telemetry, 2026-08-31).
- `wiser_alive_check.ps1` — UWB acquisition watchdog: wiserex process + DB LastWriteTime only,
  never opens the DB. `pc_drift_check.ps1` — passive NTP drift log for the sync model; never
  adjusts the clock.
- `analyze_minidump.py` — after a BSOD: names the faulting driver/function from
  `C:\Windows\Minidump\*.dmp` without WinDbg (dbghelp + auto-fetched public PDBs). Copy the
  dumps out of the admin-only folder first; the 2026-09 crashes were the kernel scheduler
  (`nt!KiAbProcessPostContextSwitch`), not a USB driver — see `incident_log.md`.

**Data lifecycle** (which machine runs what matters — the field PC has no route to the lab server):
- Field PC: `copy_day_to_usb.ps1` (day → USB, save log) → `delete_day.ps1` (save-checked delete);
  `copy_cohort_to_usb.ps1` wraps it over a cohort's date range from `COHORTS.csv`;
  `copy_to_analysis.ps1` (robocopy to the analysis machine, copy-only flags hard-blocked, writes a
  `copy_manifest_*.csv`); `extract_labeling_clips.ps1` cuts keyframe-aligned `-c copy` clips from
  closed segments for `ir_identity_labeler.html`.
- Analysis PC: `verify_on_analysis.ps1` checks the local copy against the manifest (no field-PC load).
- Campus PC with `Q:` mapped: `copy_ssd_to_server.ps1` (sneakernet SSD → BioHPC, additive only).

## Camera calibration

Goal: pixel ↔ paddock coordinates for every camera. The paddock frame is origin at corner pole A0,
x along the 40 ft length, y along the 20 ft width, z up. **Units are mixed by design**: the field is
natively imperial (record sheet, cone/cord labels and WISER in inches), the fit stores mm, the
analysis pipeline works in cm, and the board is metric (800 x 600 x 6 mm plate, 12 x 9 ChArUco,
60 mm squares, DICT_5X5_100; the printed plane sits 6 mm above whatever the plate rests on).
Cohort 3 is the last cohort and the paddock is demolished afterwards, so these calibrations are
final (`PRE_TEARDOWN_CAPTURE_CHECKLIST.md`).

Two Python trees of different vintage:

- `camera_ground/` (2026-09-09) — installable package implementing the panorama-first plan
  (`PLAN_CH01_CH02_pano_ground_map.md`): `identify → init → extract → observe/manual → assemble →
  fit → evaluate → bev/combine`, plus `audit-legacy`/`compare`. Tested on synthetic data only; no
  real calibration was ever accepted through it. Superseded in practice by `calibration_qc`.
- `calibration_qc/` (2026-09-18 →) — the pipeline that produced the **release fit** from the two
  field sessions (`E:\calibration\session_2026-09-18_13-54-34` and `..._2026-09-19_12-23-53`,
  ~50 GB of video; cached corner detections in `E:\calibration\qc\corners\`). Order:
  `qc_placements` → `rescue_boards` → `timeline_gui` (operator timeline) → `label_timeline` →
  `manual_board_gui`/`manual_boards` → `fit_cameras` → `frame_correction` → `paddock_map`; review
  with `show_frame`, `annotate_video --boards`, `timeline_gui --boards`. Two gates: station identity
  comes only from the operator's timeline; "not present" is only the operator's Skip.
  `calibration_qc/README.md` is the dated lab notebook of every decision.
  - **Committed release artefacts**: `camera_fit.npz` (poses, lens models, plate poses, frame
    sizes), `frame_correction.json` (per-camera ground warp, sha-bound to the fit — `load()` refuses
    a stale one), `fit_manifest.json` (provenance). `CALIBRATION_REPORT_2026-09-24_rev2.md` is the
    acceptance document; `AUDIT_CALIBRATION_2026-09-24*.md` / `AUDIT_RESPONSE_2026-09-24.md` the
    review trail. Honest accuracy: held-out placements 76 mm median, 137 mm p90; whole-field 50 mm
    is not claimed.
  - **Use it anywhere** (numpy/scipy/cv2 only, falls back to the repo copy when `E:` is absent):
    `sys.path.insert(0, "<repo>/calibration_qc"); from paddock_map import load; cams = load();
    cams["CH01"].to_paddock((u, v), z_mm=0, units="in")`. `to_paddock` returns NaN outside the
    verified support (`why=True` says why).
  - **Conventions that bite**: pixel coordinates are UPRIGHT — the Duo 3 panos are stored rotated
    (2160 x 7680) and every tool works in the 7680 x 2160 frame (`space="stored"` for raw pixels);
    nothing downstream may hard-code frame sizes (`qc_paths.frame_size`). `z_mm` is an assumption
    about height (0.73 mm horizontal error per mm on the panos). Lens scales are pinned in
    `fit_intrinsics.py` (`FOCAL_OVERRIDE`, `PANO_SCALE`, set once from the taped heights) and the
    bundle never refits the lens on coplanar placements. `qc_placements` detector params are
    deliberately not OpenCV defaults.
- Human ledger, in this repo on purpose: `README_camera_calibration.md` (epoch registry and
  physical-event log — whoever touches a camera, wall, pole or shelter fills it in),
  `calibration_record.ps1` + `gen_calib_record_sheet.py` (printable stakeout/record sheet in inches),
  `METHOD_camera_calibration_for_review.md` (self-contained method for an external reviewer).

## The filename contract

Everything hinges on the segment naming scheme; QC, copy, delete and calibration tools all parse it:

```
<group>_YYYY-MM-DD_HH-MM-SS_to_HH-MM-SS.mp4   finished (supervisor appends _to_<end> on rollover)
<group>_YYYY-MM-DD_HH-MM-SS.mp4               still recording (no "_to_")
```

Same scheme for `.wav` (mics). The active segment must be found by **sorting on Name, not
LastWriteTime** (write-time metadata is lazy for the open file). Any file without `_to_` is treated
as open and must never be touched.

## Configs and secrets

All credentials (NVR/camera passwords, Slack bot token) live in `*.config.psd1` files outside the
repo, next to their data roots on `E:` (`E:\Reolink_record\recorder.config.psd1`,
`E:\thermal_record\thermal.config.psd1`, `E:\recording_qc\overexposure.config.psd1`, the ultramic,
weather and GUI-recorder configs likewise). `.gitignore` excludes every `*.config.psd1`, `logs/`,
`CH[0-9][0-9]/`, media (`*.mp4`, `*.wav`, `*.flac`), `.venv-calibration/`, `calibration_sessions/`
and Python build artefacts — keep it that way. The four `*.config.example.psd1` files in the repo
are the templates.

## Repo quirks

- Each subsystem has its own `README_*.md`; read the matching one before changing a script. The root
  `README.md` describes the June 2026 state (six channels, `D:` roots, retention on) and several
  READMEs still reference the old path `...\Field_2026_Social\reolink_record\` — the repo now lives
  at `Field_2026_Social_Recording` and the primary recording drive is `E:` (with `D:` as failover);
  trust the script defaults over README paths. `README_neurologger_daily_resync.md` is superseded
  (the current protocol is on the Notion cohort-3 page).
- `change_log/` holds one dated note per behavioural change to the rig (since 2026-06-25); add one
  when you change what a recorder, watchdog or copy tool does.
- `logs/` is a gitignored snapshot of the field-PC operational logs, refreshed by
  `copy_logs_here.ps1` (read-only copy from `E:`); see `logs/_manifest.txt`.
- `COHORTS.csv` is the cohort registry (dates, notes) that `copy_cohort_to_usb.ps1` reads;
  `EXPERIMENT_END_*.md` record how each cohort was shut down. Open field experiments are dated
  `EXPERIMENT_*.md` files at the root — currently the CH07/CH08 IR identity colour sampling
  (2026-09-09) and the SD-card power bench test (2026-09-02); the CH01/02 encoder CBR→VBR
  experiment (2026-07-09) is history and VBR has been the setting since cohort1_mice. Check for an
  open one before touching camera/encoder settings.
- The user runs Windows PowerShell 5.1: no `&&`/`||`, no ternary; scripts must stay 5.1-compatible.
- The calibration sessions' NVR OSD clock is not the PC clock (PC − ~59 min 25 s on 2026-09-18,
  drifting); re-measure before naming any new NVR export.
