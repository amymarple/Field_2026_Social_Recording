# calibration_qc — field-session QC for the ChArUco calibration captures

Same-day QC of a `calibration_record.ps1` session: did every station get a usable board
placement, were the intrinsics sweeps adequate, which cameras were in IR mode. Runs in the
`cv` conda env (OpenCV 5.0, numpy, matplotlib) on the field PC; reads only closed `_to_`
segments.

| Script | What it does |
|---|---|
| `id_board_dict.py` | Identifies the ArUco dictionary / board layout from the board artwork (result 2026-09-18: DICT_5X5_100, CharucoBoard((12,9), 60 mm, 45 mm), 88 corners). |
| `qc_placements.py CHxx [seg-filter] [--every N]` | Keyframe-only decode of a camera's segments, ChArUco detection, IR flag, board-region saturation, clustering into placement events, station guess through the old poly calib. Saves decoded corners (`corners/CHxx/<HHMMSS>.npz`, full-frame px + ids) for the fitting stage. **Detector params are NOT OpenCV defaults**: `minMarkerPerimeterRate=0.005` (the default 0.03 is relative to the largest image side and rejects every marker under ~58 px on a 7680-px pano, i.e. every board beyond ~3 m), `perspectiveRemovePixelPerCell=8`, `errorCorrectionRate=0.8`, plus a 3x upscale re-detect of the board crop. Use `--every 1` (every ~2 s keyframe): the 4-s default missed half of the 3–5 s holds. |
| `merge_v3.py` | Cross-camera station assignment: pano positions from the old polys → confident matches → refit a 2nd-order poly per pano camera → remap and reassign (4 iterations, rms ≈ 10 in). Hand-held sweep windows are excluded. Writes `coverage_v3.txt`, `station_assignments.csv`, `coverage_map_v3.png`. |
| `ir_timeline.py` | One frame per 2 min per camera: colour vs IR (mean |U−128|,|V−128| < 2 ⇒ IR) and global saturation. |
| `sweep_census.py CHxx t0 t1` | Full-rate (5 fps) census of a hand-held intrinsics sweep: distinct poses with ≥20 corners and a 4×3 frame-coverage grid. |

Outputs live in `E:\calibration\qc\` on the field PC; the session summaries are copied here as
`session_<date>_*.{txt,csv}`.

## Session 2026-09-18 (`E:\calibration\session_2026-09-18_13-54-34`, 13:54–15:49, 12 streams, 39.7 GB)

- Board placements 15:01–15:40 (origin corner on the cone centre, cones exactly on the cord
  ticks per operator). Refined assignment: **46/59 stations matched**, 9 more have an
  unassigned cluster within 22–34 in (V/T ambiguity at ~10 in map accuracy — resolved at the
  fitting stage from the 88-corner geometry), **3 probably not placed: T33, T43, F63**.
- Intrinsics sweeps: **CH04 15:42:33–15:45:30, 173 poses, 9/12 frame cells — good. CH03
  15:40:27–15:41:30, 62 poses but lower half of the frame only (5/12 cells)** — upper half
  unconstrained; fallback = plumb-line + far-zone ground points, lower confidence there.
- IR/colour: CH01 colour throughout; CH02 IR 15:08–15:24; CH03 IR from 15:40; CH04/05/06
  IR until ~14:35; no frame-level saturation > 9 %. IR frames detect at least as well.
- Thermal 108/109 recorded only from 15:34 (cameras were powered off at session start).

### Corrections after the first pass (same day)

- CH03 sweep verdict corrected: over 15:38:58-15:41:30 (carrying/placing phases count as poses)
  it has **141 poses covering 10/12 frame cells**, x 222-4416 of 4512 - adequate, no re-shoot.
  The earlier "lower half only" came from a too-narrow census window.
- Operator confirms T33 / T43 / F63 WERE placed (occluded near the shelter boxes / centre
  pole). Frames at the guessed times show no board, so the guessed times are wrong, not the
  placements. Identity of those three (and the 9 V/T-ambiguous stations) is resolved at the
  fitting stage from all six cameras' corner sets; fallback = operator clicks the visible
  outline corners on prepared frames.
- CH05/CH06 (nadir shelter cams) decoded ~30 placements each (`session_2026-09-18_CH05/06_*`),
  giving them ground control points of their own.
- NVR OSD clock on 2026-09-18 reads PC - 59 min 25 s (was PC - 60:00 +-1 s on 08-19): the
  NVR clock has drifted ~+35 s. Re-measure before naming any new NVR export.

### Operator timeline and per-camera coverage (2026-09-19)

- Station identity now comes ONLY from the operator's timeline (`timeline_gui.py` export,
  `session_2026-09-18_placement_timeline_operator.txt`: 68 rows after the operator's second pass
  -> 56 windows, 54 stations; T23 confirmed at 15:09:05-15:09:17, CH03 only).
  **T61-T65 were never placed** (operator, 09-19). The operator's added row "T41 15:22:36-15:22:56"
  duplicates the F41 window: the CH02 frame shows the board's origin corner on the F41 cone
  (`frames/CH02_152245.jpg`), so those frames stay F41 and T41 keeps only its 15:19:22-15:20:26
  windows (no readable board in any camera there). The boards at 15:32:30-15:40:20 lie on the
  paved strip along the x=0 wall, not at a station; 15:38:58-15:41:30 is the CH03 hand-held sweep.
- `label_timeline.py` labels every cached corner file from the timeline (no guessing; frames
  outside every window are listed as clusters for the operator), checks each placement against
  the operator's cone labels in the panos (which board corner sits on the cone, long-edge
  direction) and writes `session_2026-09-18_station_coverage.txt`, `..._unlabelled_clusters.txt`,
  `..._labelled_frames.csv`. `show_frame.py CHxx HH:MM:SS [--around STATION]` renders a frame
  with the cone labels and the cached board outline for eyeballing a placement.
- Usable stations (settled run: >=3 cached frames over >=3 s, >=12 corners spanning 3x3, <=3 px
  motion): CH01 15 (T8/V3/F4), CH02 16 (T10/V3/F3), CH03 5, CH04 9, CH05 7, CH06 10. V11, F14,
  T35, V44 and the second T41 window have no detections in any camera (operator in the line of
  sight / board unreadable).
- The panos cannot read the FLAT board beyond x ~ 350 in or below x ~ 60 in (nothing at T1x,
  T7x, F61-V64); their ground control there is the labelled cones (39 in CH01, 38 in CH02).
- Board corner on the cone: (0,540) in 20 placements, (0,0) in 8, (720,540) in 1 (T53); long edge
  along +x in every checked placement. The fit must take the per-placement corner from
  `station_coverage.txt`, never assume the design convention.
- Return-trip plan: `CALIB_SUPPLEMENT_SHEET_2026-09-19.html` (survey measurements, the 5 missed
  stations + T61-T65 with a station ID card and the operator clear of the sightlines, and a
  46-position mid-point cone set as independent test marks for every camera).
