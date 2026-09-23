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

Outputs live in `E:\calibration\qc\` on the field PC (a session other than 2026-09-18 gets its own
subfolder, `--session <dir|YYYY-MM-DD>` on every script); the session summaries are copied here as
`session_<date>_*.{txt,csv}`.

## The physical board (operator spec, 2026-09-21)

Aluminium composite plate **800 x 600 x 6 mm**, checker 60 mm, marker 45 mm, 9 rows x 12 columns,
DICT_5X5_100. So the printed pattern is 720 x 540 mm centred on the plate: margin 40 mm along the
long axis, 30 mm along the short one, and the 88 inner corners span 60..660 x 60..480 mm. The three
rectangles are `OUTLINE_MM` / `PAPER_MM` / `GRID_MM` in `board_detect.py`; a localiser must be told
which one its quad is, or the rectification is off by 11 % (plate taken for pattern) or 20 %
(corner ring taken for pattern). **The 6 mm thickness puts the printed plane 6 mm above whatever the
plate rests on** - that offset, plus the grass under it, is what `plane_height` has to carry.

A board that is located but not decoded still calibrates: the station grid plus the operator's
timeline already fix where the plate is on the ground, so its four outline corners are four
correspondences with known field coordinates. They are support points, not test points - corner
accuracy is a few px at the far field, and their field coordinates assume the placement was exact.

## Workflow - the operator is a required stage, not a fallback

Detection follows the project skill `/detect-then-decode`
(`.claude/skills/detect-then-decode/SKILL.md`); the failure that produced it is
`DETECTION_POSTMORTEM_2026-09-19.md`. Two gates block the pipeline:

| Step | Script | Gate |
|---|---|---|
| 1. corners per camera | `qc_placements.py CHxx --every 1 --session ...` | - |
| 2. re-decode thin windows (locate -> rectify -> decode) | `rescue_boards.py --keyframes` | - |
| 3. station identity | `timeline_gui.py` -> operator's `placement_timeline.txt` | **A: identity comes only from the operator.** Never guess a station from geometry; frame-verified additions go in as comment-marked rows the operator can veto. |
| 4. label + coverage | `label_timeline.py` | - |
| 5. whatever is still missing | `manual_board_gui.py` -> operator clicks 4 outline corners (cone corner first) or Skip -> `manual_boards.py` | **B: "not present" is only the operator's statement.** A Skip makes it a fact; an empty detector result never does. |
| 6. review what WAS found | `annotate_video.py --boards` + `timeline_gui.py --boards` | operator sees every detection (outline, origin corner, station, corners, method) before fitting |

`show_frame.py CHxx HH:MM:SS [--around STATION]` renders any frame with the cone labels and the
cached board outline - use it before writing the word "missing".

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
- **The marker decoder, not the footage, was the limit** (operator objection 2026-09-19, correct):
  on the pano far rows the board is ~20 px/square across the short axis (2.5 px per marker bit)
  and at the 4K cameras' edges the lens bends the marker quads, so 300-600 px boards gave 0-10
  ChArUco corners although the 11x8 corner grid is obvious. `board_detect.py` adds a chessboard-
  corner fallback (orientation from the square-colour parity of the 12x9 board, cross-checked
  against any decoded marker; validated at 0.6-0.7 px vs ChArUco on 88-corner frames), and
  `rescue_boards.py --keyframes` re-decodes every timeline window with < 3 cached frames.
  Rescued on 09-18: CH01 V44/V24/V62/T24/T72/T35/T74, CH02 V51/T73/F63/V13 (+T41 partly behind
  the pole); on 09-19: CH01 F14/T64, CH02 V11, CH03 T12 (324 frames)/V11/F14. CH04/CH06 gained
  nothing (the untouched windows are outside their view). Still physically unreadable: T11-T15
  in CH01 (blind strip), T61/T65 in CH02 (tens of px), 09-19 T63 in CH01 (pole cable across the
  board), T35/V44 09-18 in CH02 (behind the pole).
- Usable stations (settled run: >=3 cached frames over >=3 s, >=12 corners spanning 3x3, <=3 px
  motion), 2026-09-18 after the rescue: CH01 19 (T9/V6/F4), CH02 18 (T11/V4/F3), CH03 7, CH04 9,
  CH05 7, CH06 10 (`session_2026-09-18_station_coverage.txt` has the station x camera matrix).
- The panos still cannot read the board at the T1 cord (CH01) or beyond x ~ 420 in (CH02); their
  ground control there is the labelled cones (39 in CH01, 38 in CH02).
- Board corner on the cone (measured per placement in the panos): (0,540) in 26 placements,
  (0,0) in 11 (the y=228 row T25/T35/T45/T55 and F34/F52/F54/V22/T43), (720,540) in 5 (the T7
  cord T72/T73/T74, plus T53 by house 7); long edge along +x (or -x for the (720,540) cases)
  in every checked placement. The fit must take the per-placement corner from
  `station_coverage.txt`; for stations only seen by CH03/CH04 (T11-T15, T71/T75, T6x) the
  operator's rule applies: wall side -> the corner that keeps the board inside the field.
- `annotate_video.py --boards` burns the cached detections (outline, (0,540) corner, station,
  corner count, method, settled/unsettled) into the timelapse; `timeline_gui.py --boards` scrubs
  those renders (`timeline_gui_boards.html`). `--still HH:MM:SS` writes one frame.
- Return-trip plan: `CALIB_SUPPLEMENT_SHEET_2026-09-19.html` (survey measurements, the 5 missed
  stations + T61-T65 with a station ID card and the operator clear of the sightlines, and a
  46-position mid-point cone set as independent test marks for every camera).

## Session 2026-09-19 (`E:\calibration\session_2026-09-19_12-23-53`, 12:23:56-12:42:28, 12 streams)

Supplement capture: the operator re-placed T11, T12, V11, F14, T23, T35, V44 and the missing
T61-T65 (cords not re-measured, design inches stand; cones untouched, no mid-point set). QC lives
in `E:\calibration\qc\2026-09-19\` (`--session 2026-09-19` on every script). Operator timeline
`session_2026-09-19_placement_timeline_operator.txt` (12 rows) plus three frame-verified
additions marked in the file: T61 settled from 12:29:25 and placed again 12:41:05-12:42:24, T62
from 12:29:39, T65 until 12:34:55 (picked up at 12:35:00 and carried across the field - the
12:35:03-12:35:19 detections in CH01/CH02/CH03 are hand-held and stay unlabelled).
Usable stations: CH01 T23/T35/T62/T64 + V44 + F14; CH02 T63; CH03 T11/T12/T23 + V11 + F14;
CH04 T61-T65; CH06 T61/T64; CH05 nothing. Merged with 09-18 the panos have CH01 T13/V6/F5 and
CH02 T12/V4/F3 settled stations. T63 by house 7 was aligned on a different corner (operator);
T75/T15 (field corners) corner still to be confirmed by the operator.

## The fit (`fit_cameras.py`, 2026-09-22)

`python fit_cameras.py [--split] [--out <dir>]` -> `CALIBRATION_FIT.txt` + `camera_fit.npz`
(`X_cam = Rodrigues(cam_rvec) @ X_field + cam_tvec`, field mm, origin pole A0, z up).

**Nothing about the field is an input.** The board is the metric object (60 mm squares on a
720 x 540 mm pattern on an 800 x 600 x 6 mm plate), so focal length, distortion, the distance and
attitude of every placement, and every camera's position INCLUDING its height are solved for.
Camera height appears at stage 3, before a field frame exists at all: the placements a camera sees
lie on one plane, and the distance from the projection centre to that plane is the height.

Supporting modules: `fit_data.py` (cached corners -> one observation per placement),
`fit_intrinsics.py` (free-pose views -> lens), `fit_models.py` (projection models, pose fitting).

Five things this had to get right, each of which silently ruins the fit:

1. **Intrinsics need non-coplanar views.** Every placement lies on the ground, so all of them
   together carry one plane's homography - which cannot separate focal length from tilt. The
   material that can is already cached: the detections belonging to NO station (the operator
   carrying the board, plus the deliberate sweeps in front of CH03/CH04, 13-242 views per camera).
   Reprojection 0.5-1.4 px, and CH05/CH06 return the same focal length from any starting guess.
2. **The Duo3 pano has no focal length to calibrate.** Solving fu, cu, fv, cv freely on its
   7680 x 2160 upright canvas returns W/pi, (W-1)/2, W/pi, (H-1)/2 to within 0.03 %, from either
   half and either session: the canvas is an exact 180 deg equirectangular image. Splitting it into
   two lens halves with their own poses does not lower the residual, so it is one projection centre.
3. **A homography gate, before anything else.** A flat board must fit a plane-to-plane homography
   to within the lens distortion across it. Seven placements could not, at 4.7-10.2 px - those do
   not have noisy corners, they have wrong ones (orientation resolved a square off). `fit_data`
   rejects them and down-weights the rest by the planarity they actually achieve.
4. **Operator clicks are a rectangle, not a labelling.** The four clicks on the plate edge fix
   where the plate is, but an 800 x 600 rectangle maps onto itself under a 180 deg turn, so which
   corner is which has a twin no single view can tell apart. Measured against the cameras that DO
   decode those boards, the twin was being picked often enough to drag whole cameras metres out of
   place. They are held out of the geometry (4 points each of 7000+) and still count as coverage.
5. **The lens must not be refitted on the placements.** With every board coplanar, a free f/c/k has
   nothing to constrain it and simply absorbs pose error - it moved CH05's principal point 250 px
   and doubled the residual. Stage 1 measures the lens; the bundle leaves it alone.

Result: heights 2.32-2.69 m, a layout that nothing in the fit was told to produce (the two panos
back to back mid-paddock, CH03/CH04 at the ends facing each other along +x/-x, CH05/CH06 near
nadir). Median corner reprojection 2.3 px (CH01) to 8.0 px (CH04); at those working distances
2-8 px is roughly 1-2 cm on the ground.

Open: the paddock frame is only as good as what ties it to the cord grid. The operator's cone
labels sit ~110 mm from the grid the placements imply, which matches his own note that they need
re-labelling; the frame is therefore anchored on the placements (each plate corner to its cone,
median 195 mm) with the cone labels down-weighted to picking the branch. Re-run after the cones are
re-labelled. CH04 is the weakest camera (16 px rms, one 605 px view dropped) - worth a look at its
sweep before trusting it.

## Pixel <-> paddock (`paddock_map.py`, `paddock_agreement.py`)

```python
from paddock_map import load
cams = load()                                       # E:\calibration\qc\camera_fit.npz
x, y  = cams["CH01"].to_paddock((3000, 1500), z_mm=0, units="in")    # pixel -> paddock
u, v  = cams["CH01"].to_paddock_inv((240, 120), z_mm=0, units="in")  # paddock -> pixel
H     = cams["CH03"].homography(z_mm=0)             # 3x3, UNDISTORTED px <- paddock mm
cams["CH03"].sees((240, 120), units="in")           # is that point in frame at all?
```

Pixels are UPRIGHT by default (CH01/CH02: the 7680 x 2160 frame after rotating the stored video
90 deg CCW, which is the space every other tool here uses); pass `space="stored"` for raw video
pixels. Round trip paddock -> pixel -> paddock is exact to 1e-11 mm on all six cameras.

**A pixel is a ray, not a point**, so every conversion has to be told a height. `z_mm=0` is the
ground, 6 the top of the calibration plate, ~60 a rat's back. Get it wrong by dz and the answer
slides by dz / tan(depression): 0.7-0.85 mm per mm on CH01-CH04, so reading a 60 mm-high animal as
if it were on the ground puts it 40-50 mm too far from the camera. CH05/CH06 look almost straight
down and barely care (0.07 mm per mm). For the four ordinary lenses `homography()` is exact but
only after `undistort()` - k1 ~ -0.35 moves a frame-corner pixel by over 100 px. The two panoramas
have no 3x3 at all: an equirectangular canvas is not a projective image, so a plane in it is not a
homography.

`paddock_agreement.py [--z 6] [--plot]` answers "if two cameras see the same spot, how far apart do
they put it?" - measured, not modelled: every ChArUco corner id is one physical point on the ground,
so each camera that decoded it has its own independent paddock position for it. Over 1861 such
points (views the fit itself rejected excluded): **median 116 mm, p90 352 mm**. The two panoramas
agree to 35 mm with no systematic offset; the disagreement is concentrated at the two ends of the
paddock (x < 90 in and x > 390 in), where the only close cameras are CH03/CH04 and the panos are
looking 6-8 m away. CH01-CH04 carries a real -244 mm bias in x. -> `PADDOCK_AGREEMENT.txt`,
`paddock_agreement.png`.

Two errors this number does NOT contain: the height assumption above, and the paddock frame itself
(a common error moves all the cameras together and cancels in a camera-to-camera comparison).

## Where the end-of-paddock disagreement comes from (2026-09-23)

Checked, in this order, after the operator asked whether the CH03/CH04 boards were solved right:

1. **Board labels in CH03/CH04 are consistent.** Every board seen by two cameras was refitted on the
   ground from each camera alone; the plate yaw agrees between cameras to within 8 deg for all 50
   shared boards (a wrong id set or the 180-degree twin would show as ~180). Own-view flatness:
   CH05 1.4 px, CH06 0.8 px, CH03 4.1 px, CH04 4.7 px, panos 5.8-6.6 px.
2. **The station anchors are not distorting the fit.** `FIT_STATION_SIGMA=10000 FIT_CONE_SIGMA=1e6`
   (anchors effectively off) reproduces the same camera positions to 0.1 in and the same agreement
   table. The design grid is a check, not a force.
3. **What remains is the panos' geometry at long range.** Each pano reads the far boards in the
   upper part of its right lens (CH01: T74/T75/T64/T65; CH02: T11/T12/T21/T22/V11) 0.3-1.0 m
   CLOSER than the pinholes and the design grid do, with the plate 15-25 % smaller than a ground
   board should look there; the left lens at the same range is fine (CH02/T71 at 6.3 m: -0.1 m).
   In the joint fit the panos win (more corners) and the nadir cameras, which see their own boards
   coplanar to 1-2 px, are strained to 12-14 px. A free vertical scale / cubic / two-lens pose does
   NOT make the pano boards coplanar, so it is not a smooth lens correction. Open. The operator-
   verified CH03/CH04 boards and the hand-held sweeps (below) are the independent geometry at the
   ends that will decide it.

Two bugs of mine found on the way, both fixed in `fit_data.py`:

* frames of one window were clustered on the centroid of whatever corners each frame decoded, so a
  partly occluded board (different subset each frame) fell apart into single-frame clusters and the
  LAST frame won - at T61/T65 (09-19) that was the frame with the plate in the operator's hands.
  Now frames agree when the corners they SHARE sit within 4 px; a window whose frames never agree
  is flagged `moving` and kept out.
* the second T61 window of 09-19 (12:41:05-12:42:24) is not a T61 placement: the frames show the
  plate set down beside house 7 with no cone at its corner (CH06 12:41:48-12:42:24), and CH06
  cannot see the T61 cone at all. It is listed in `fit_data.EXCLUDE` with that reason; the
  976 mm "T61" line in the previous RESULT 3 was this board. The first T61 window (12:29:25) is
  fine: CH02 puts its plate corner 73 mm from the design point.

### Operator review of CH03/CH04 (`manual_board_gui.py --mode audit --sweep ...`)

`--mode audit` shows, per camera, every window where the machine found something plus every
window whose station the current fit puts inside the frame (so a missing detection is visible as
a frame with no box). `--sweep CH03=15:32:20-15:41:46,CH04=15:41:42-15:45:38 --sweep-step 2` adds
the hand-held distortion sweeps as one frame every 2 s (`SW<HHMMSS>`); on a hand-held plate any
corner may be clicked first. Built into `E:\calibration\qc\manual_ch0304\manual_board_gui.html`:
426 frames (CH03 12 placement windows + 284 sweep frames, CH04 9 + 119). The exported
`manual_quads.json` goes through `manual_boards.py` as before; sweep frames land in the labelled
frames with no station and feed `fit_intrinsics.free_views`.

### Outcome of the CH03/CH04 review (2026-09-23, `manual_quads (2).json` -> `session_2026-09-18_manual_quads.json`)

400 of 426 frames reviewed (26 sweep frames left unreviewed stay out). Placements: CH03 8 machine
boxes accepted, V11 and F14 re-clicked and now decoded (rect-chess, 88 corners), T21/T22 not
visible, T24/T25 partly visible; CH04 all 9 accepted. Sweeps: 250 accepted, 74 re-clicked (138
decoded, 2 windows still nothing), 36 not visible, 16 partial, 1 rejected. `manual_boards.py` then
mapped the plate through `PAPER_MM` for the outline fallback (was `OUTLINE_MM`: every predicted
corner 11 % off), and `fit_intrinsics.free_views` now takes, for a camera whose sweep was
reviewed, only frames inside windows the operator accepted or re-clicked, never outline-predicted
corners.

Lens models from the reviewed sweeps: CH03 f 2990 -> 2949 px, principal point moved 87 px, k1
-0.374 -> -0.393; CH04 f 3101 -> 3130 px, k1 -0.367 -> -0.373. Refit: CH01-CH03 agreement
168 -> 52 mm (CH03 shares two more boards with CH01 now), overall median 122 -> 108 mm;
CH01-CH04 (286 mm, dx -252) and CH02-CH03 (384 mm) unchanged - the boards at the ends are what
the operator confirmed, so the remaining disagreement is on the pano side, as in the section above.

### 12:41 on 09-19 is nothing (operator, 2026-09-23)

The row `12:41:05-12:42:24 T61` in the 09-19 timeline was one of the frame-verified additions of
09-19 (mine, comment-marked "operator may veto"), and the operator vetoed it: "nothing there, I
just set the plate down". Both copies of the timeline now carry the row with the label `NONE` so
those 43 frames are neither a station nor a free lens view; `fit_data.EXCLUDE` keeps the entry as a
guard with the operator's words. T61 on 09-19 is the 12:29:25 window only (CH02 and CH04).

Regenerating the 09-19 labelled-frames table for this also showed the REPO copy had been stale
since the 09-19 manual re-decode: 551 rows vs 845 on E:. Every fit before this one read the repo
copy, so it was missing 295 operator-decoded frames of the 09-19 boards (CH01 T65 44 -> 162
frames, CH02 T12 1 -> 15, CH02 T23 absent). `label_timeline.py` writes to the session QC folder;
the copy into the repo is a separate step and must follow every re-decode.
