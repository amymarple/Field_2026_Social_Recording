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
