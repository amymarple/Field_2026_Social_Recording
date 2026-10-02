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

## The far-board disagreement was the fit, not the panos (2026-09-23, evening)

Tested against the ordinary lenses' OWN geometry (each pinhole's boards as rigid 3-D objects in its
frame, one rigid pano pose per pinhole, `scratchpad pano_vs_pinhole.py`): the nominal equirect
explains the shared boards at 6-10 px median once a handful of corrupted boards are set aside,
and no smooth alternative (per-lens rotation, per-lens vertical scale, two rectilinear halves)
does better with physical parameters. The corrupted boards were looked at, not inferred:

* CH01/F52 lies under the burnt-in "Reolink Duo 3 PoE" watermark; CH06/F52 has a cable across it.
* CH04/T65, CH03/F12, CH06/T64 are cut by the frame edge (16-43 corners in the most distorted
  part of the lens).

So the 0.3-1.0 m "far boards closer" readings came from the bundle itself: with a 40 mm height
prior under the robust loss it slid far plates DOWN their rays instead of moving the cameras (the
panos have many more corners than the ordinary lenses). Control runs with the same data:

| plate height prior | cross-camera median | p90 | CH01-CH04 |
|---|---|---|---|
| 40 mm (as before) | 112 mm | 341 mm | 276 mm |
| 10 mm | 104 mm | 212 mm | 159 mm |
| 1 mm (pinned) | 78 mm | 174 mm | 89 mm |

Pinned is now the default (`FLAT_SIGMA_Z = 1`, tilt 2 deg; `FIT_FLAT_SIGMA_Z=40` reproduces the
old fit). Two more guards in `fit_data.py`: corners under the OSD boxes (timestamp, model name)
are dropped before anything else, and a plate cut by the frame edge or with fewer than 30 corners
carries half weight (`partial`). Final: median 87 mm, p90 179 mm, max 279 mm over 2600 shared
corners; worst stations T11/T75/T22 at ~200 mm; CH01-CH02 55 mm; CH01-CH03 59 mm; CH01-CH04 126 mm.

Still open, and what the operator can label: the ends of the paddock are held by few boards.
`cone_gui.py` now works for any camera (`python cone_gui.py CH03 15:20:00`), pages built for
CH03-CH06 (`E:\calibration\qc\cone_gui_CH0[3-6].html`). A cone clicked in an ordinary lens is a
point on that camera's own ground plane at a place the panos see well, so every labelled cone at
the ends is one more tie between a pinhole and a pano where the boards are thin.

## Cone labels from all six cameras, and the frame tied to the cords (2026-09-23, late)

The operator labelled the cones in CH03-CH06 (`cone_labels_CH0[3-6].json`, 31 cones). Two label
errors were found by projection, not judgement, and corrected with a note in the file (operator
may veto): in CH04 the V/F column was mirrored (V64<->F61, V62<->F63: each landed exactly on the
other's station, 1450-3640 px off), and CH02's "F54" is a cone behind CH02 - it sits on V53, which
was already labelled, so it is NONE now. The bundle now uses every camera's cones, at cone-top
height (`CONE_Z = 50 mm`). They change the fit very little (cross-camera median 86 mm), because a
few hundred corners outweigh nine cones; raising their weight to 20 px changes nothing either.

What the cones DO show is that the fitted frame is compressed along x: the x = 24 in cord reads
at 40 in, x = 60 at 69, x = 456 at 448 (the panos read far boards a little too close and CH03/CH04
follow them); the y cords are all within 2 in. An independent check that uses nothing from the
fit: the fit's x = 0 line drawn on the CH03 frame lies on the end wall a hand above its base
(`frames/CH03_walltest.jpg`), while the cones sit 24 in from the wall base as designed.

`frame_correction.py` fits a smooth dx(x) (cubic) and dy(y) (linear) to the per-cord medians of
all 108 cone labels and writes `frame_correction.json` next to the fit; `paddock_map.load()`
applies it on the way out and inverts it on the way in (round trip still 1e-11 mm). After it the
wall base seen by CH03 lands at x = -1..1 in and by CH04 at 476..489 in, and the cone labels sit
4.6 in (median) from their stations. It is a correction of the FRAME, measured on the cords the
operator laid; it does not touch any camera and leaves the cross-camera agreement as it is.

## Cords and wall foot: the frame is now tied per camera (2026-09-24)

The operator labelled the seven T-series cords and the foot of the wall in all six cameras
(`session_2026-09-18_line_labels_CH0*.json`, ~250 points; two wall segments relabelled by
projection with a note: CH02 "WALL_Y240" is the x = 480 end, CH03 "WALL_X480" is the y = 240 corner).
`line_check.py` pushes them onto the ground: every cord came out STRAIGHT (0.1-2 in rms) but
TILTED differently in different cameras - X456 at 0 deg in CH02, 6 deg in CH04, 11 deg in CH01 -
and each camera's cones agreed with its own cords. So the cameras' ground mappings differ from
each other by a smooth, camera-specific warp, largest in the corners of the pano canvas, and no
lens model tried reproduces it.

`frame_correction.py` therefore fits, per camera, a 2-D polynomial warp from the bundle's frame to
the lattice (cones at their stations, cords straight at their x, the straight middles of the wall
at x = 0/480 and y = 0/240), degree 4 for the panos and 1 for the others, with a ridge prior of 8 in
per term. The boards are not used in it and are the acceptance test:

| | cross-camera median | p90 | max | CH01-CH04 | wall foot (CH03 / CH04 side) |
|---|---|---|---|---|---|
| bundle, x-only correction (before) | 84 mm | 179 mm | 275 mm | 122 mm | x = 0 / 480 by construction |
| per-camera warp, panos degree 1-2 | 118-126 mm | 206-248 mm | 336-386 mm | 119-147 mm | fine |
| per-camera warp, panos degree 4, ridge 8 | **64 mm** | **147 mm** | 302 mm | 100 mm | -1 / 478 in |

A low-degree pano warp cannot follow the canvas corners and bends the middle instead (CH01-CH02
went to 140-200 mm); degree 4 with the ridge does both. After it the cords sit within 5 in of
their x with tilts under 3 deg in every camera, the wall foot lands at x = -5..0 / 478..480 and
y = 0 / 240, the cones 3 in (median) from their stations, and the cameras' traces of the same wall
segment agree to 1-4 in. `paddock_map.load()` applies the warp (inverse by Newton, round trip
1e-10 mm); `load(correct=False)` is the raw bundle frame.

## Downstream validation (2026-09-24)

`downstream_validation.py`: an ensemble of legitimate calibrations (warp variants + bootstrap) pushed through 10 cm bins - handoff continuity, bin flip rate, occupancy and simulated place-field robustness, error vector field, distance-to-feature. Results and reading in section 9 of `CALIBRATION_REPORT_2026-09-24.md`; the numbers in `DOWNSTREAM_VALIDATION.txt`.
**Superseded (2026-09-26):** that output predates the release fit, and the ensemble varies only the ground warp
on one bundle; it is not a place-field validation of the release. See `AUDIT_PLACE_FIELD_READINESS_2026-09-26.md`.

## The taped heights fix the lens scales (2026-09-24, evening)

The operator taped the lens heights (grass to lens centre: CH01 2.362 m, CH02 2.337, CH03 2.235,
CH04 2.286; the tape reads high if anything) and measured the plate (23.5 in across, squares
exactly 60 mm). The fit had every camera 8-20 % higher than the tape. Cause, established with the
heights held HARD (camera z fixed by parametrisation, plates on the ground, `scratchpad
flatworld_f.py / flatworld_pano.py`):

* the hand-held sweeps do not determine a pinhole's focal length - CH04's sweep is fitted at
  1.95-2.00 px rms by any f between 2956 and 3173, CH03's at 1.29-1.37 px from 2800 to 3130 (the
  operator stood in one spot; distance and f trade off). CH04's sweep value 3130 was where LM
  wandered; with its height fixed its plates ask for 2964, the ground cones/cords/walls for 2956,
  and CH03 (same camera model) has 2949. CH04 f := 2960.
* the Duo 3 canvas is not the nominal 180 x 50.6 deg equirect: with the heights fixed, CH01's
  plates ask for fu = 2333, fv = 2711 px/rad and CH02's for 2318 / 2616 (nominal 2444.6 both),
  i.e. ~190 deg across and ~47 deg high. Panos fu := 2325, fv := 2660.

Both live in `fit_intrinsics.py` (`FOCAL_OVERRIDE`, `PANO_SCALE`; `FIT_NOMINAL_LENS=1` restores the
old values). Everything after them got better without touching anything else:

| | before | after |
|---|---|---|
| heights vs tape (CH01/02/03/04) | +0.19 / +0.30 / +0.17 / +0.45 m | +0.00 / +0.06 / +0.11 / +0.17 m |
| bundle positions vs tape (no warp) | 4-10 in off, CH03-CH04 separation 237 vs 257 | 2-8 in off, separation 262 |
| corner residual median (CH03/04/05/06) | 5.8 / 8.8 / 7.0 / 9.5 px | 3.9 / 6.1 / 3.4 / 6.1 px |
| plate corner to its cone | 206 mm | 157 mm |
| cross-camera boards, warped: median / p90 / max | 64 / 147 / 302 mm | 70 / 114 / 243 mm |

CH04 is still 17 cm above its tape height and CH03 11 cm; the panos' scale was set from two
cameras that agree to 1 %, but it is a two-parameter model of a canvas whose corners still need
the ground warp. The tape heights themselves are not in the fit; they were used once, to pick
these four numbers.

## Independent review and revision 2 (2026-09-24, evening)

`AUDIT_CALIBRATION_2026-09-24.md` (external review of the first report) found, correctly, that the
plates were not pinned (soft prior under a robust loss: -339..+126 mm), that the agreement figure
was a training statistic, that `rect-markers` views contributed predicted corners, that the
mapping accepted unsupported pixels, and that provenance was missing. `AUDIT_RESPONSE_2026-09-24.md`
answers each point; `CALIBRATION_REPORT_2026-09-24_rev2.md` is the acceptance document now.

What changed in the code: plates are (yaw, x, y, tilt_x, tilt_y) with the centre ON z = 6 mm and
tilt bounded +-6 deg by the solver (`board_RT`, `bounds=`); marker corners replace predicted
corners on the `rect-markers` path (ids 1000 + 4*marker + k); `fit_manifest.json` with solver
status, constants, overrides, dropped views and input hashes; `frame_correction.json` sha-bound to
its fit and `paddock_map.load()` refuses a missing or stale one; `to_paddock` returns NaN (and a
reason with `why=True`) outside the frame, off the ground, outside the verified support hull or
when the inverse does not converge; `height_sensitivity` differentiates the actual mapping;
`cv_landmarks.py` (leave-one-label-group-out for the warp) and `cv_folds_eval.py` (5 placement
folds, bundle refitted per fold with `FIT_EXCLUDE`, warp degree chosen inside the fold).

What the honest numbers are: held-out placements 76 mm median, 137 mm p90, 256 mm max (7/26
within 50 mm, 18/26 within 100 mm); held-out label groups 65 mm median, 185 mm p90; taped heights
-0.01 / +0.07 / +0.06 / +0.12 m; wall foot within 3 in of x = 0 / 480. Whole-field 50 mm is not
claimed. The pano warp degree is 3 (chosen by the folds), not 4.

## Taking the calibration to another machine (2026-09-24; portable drive 2026-09-25)

The release fit is committed here and is self-contained: `camera_fit.npz` (poses, lens models,
plate poses, dropped views and now the stored frame sizes), `frame_correction.json` (per-camera
ground warp + verified support, sha-bound to that fit) and `fit_manifest.json` (provenance). On any
machine with numpy, scipy and OpenCV:

```python
import sys; sys.path.insert(0, r"<repo>\calibration_qc")
from paddock_map import load
cams = load()            # the data root's qc\camera_fit.npz if a root is found, else the repo copy
cams["CH01"].to_paddock((u, v), z_mm=0, units="in")
```
`paddock_map.py`, `fit_models.py` and `qc_paths.py` are the only modules it imports; no video,
no ffprobe, no E: drive is needed to USE the calibration.

### Where the scripts look for data and tools (`qc_paths.py`)

Nothing else in this folder hard-codes a drive letter any more. `qc_paths.ROOT` is the first of
these that holds a `qc\` folder: `$CALIB_ROOT`, the field PC's `E:\calibration`,
`<drive this repo is on>:\calibration`, then every other drive letter. `qc_paths.FFMPEG` /
`FFPROBE` are the first of: `$FFMPEG_DIR`, the field PC's pinned `E:\Reolink_record\bin`,
`<ROOT>\bin`, `PATH`, the winget `Gyan.FFmpeg` install. Without any ffprobe, `frame_size()` reads the
header with OpenCV instead. `qc_placements.py`'s old-poly station guess (`field_coords` from the
analysis repo) is optional: it is skipped where that repo is absent.

### The portable drive (2026-09-25)

`E:\calibration` was copied whole to an external drive (`F:` on the laptop; the letter may differ
elsewhere) and the repo cloned next to it, so the drive carries everything:

```
<drive>:\calibration\session_*\            the 12-stream captures (closed _to_ segments only)
<drive>:\calibration\qc\                   corners\, 2026-09-19\, frames\, labels, the release fit
<drive>:\calibration\bin\                  ffmpeg.exe + ffprobe.exe (Gyan.FFmpeg 9.0.2)
<drive>:\Field_2026_Social_Recording\       this repo (origin = GitHub)
```
The `qc\camera_fit.npz` / `frame_correction.json` / `fit_manifest.json` on the drive are the committed
release (the 14:50 pre-portable copies, identical numbers without `stored_size`, are kept beside them
as `*.pre-portable`). On a new computer: install Python 3.10+ with `numpy scipy
opencv-contrib-python matplotlib`, and run once
`git config --global --add safe.directory <drive>:/Field_2026_Social_Recording` (the drive's file
system records no owner, so git refuses it otherwise). The field-PC copy stays canonical: plugged
into the field PC, the scripts still find `E:\calibration` first.

To RE-RUN the fit you need `qc\corners\` (20 MB of cached corner detections) and the label files
(all in this repository); only rendering frames or re-detecting needs the session videos (50 GB).

### Reproduction on the laptop (2026-09-25)

`fit_cameras.py --out F:\calibration\qc\repro_2026-09-25` from the drive, Python 3.14 / numpy 2.4.4 / scipy 1.18 / OpenCV 4.13 (the release: OpenCV 5.0, scipy 1.17), 135 min. Stage 1 reproduces the lens
to 1e-6. The bundle does not reproduce bit for bit - it stops at its evaluation budget (section 6.3 of
the report) so the endpoint follows the start, and the start differs with the OpenCV version: the
2026-09-19 T65 view in CH04 fails the flatness gate at 62 px on the field PC and passes here, to be
dropped by the bundle at 42 px instead (the five dropped views are the same set). The difference is a
near-rigid shift of the whole bundle frame, (-42, +4.5, 0) mm, with 1-5 mm per-camera scatter left
after removing it; `frame_correction.py` absorbs that shift by construction. Through each fit's own
frame correction the pixel -> paddock mapping differs by at most 1.1 mm on CH01/02/04/05/06 and
2.2 mm median / 7.7 mm max on CH03, with the same support; paddock agreement, line check and the
held-out label groups agree to the last digit or one. `compare_fits.py <release npz> <other npz>`
runs this comparison for any pair of fits. `fit_manifest.json` now records the package versions.
The 5 fold refits for `cv_folds_eval.py` were not repeated (5 x 135 min).

### Reproduction on the lab PC (2026-09-26)

Lab PC DESKTOP-HUA1FJN, the drive mounted as `G:`, `fit_cameras.py --out G:\calibration\qc\repro_2026-09-26_labpc`
in the `cv` conda env: Python 3.11 / numpy 2.4.4 / scipy 1.17.1 / OpenCV 5.0.0 - the release's library
versions - 24 min (12-core i9-10920X). With the same versions the fit reproduces the release: the same five
dropped views (T65 in CH04 fails the flatness gate at 62 px, as on the field PC), camera centres within
0.1 mm, lens within 1.4e-6, the same 8000-evaluation stop at a cost of 104944.42 vs 104944.37; the pixel -> paddock
mapping through each fit's own frame correction agrees to 0.0 mm on all six cameras with identical support,
and PADDOCK_AGREEMENT / LINE_CHECK / CV_LANDMARKS are identical to the last digit. The only differences are
in the last digits of 16 of the 200 numbers in CALIBRATION_FIT.txt (largest: CH04 reprojection rms 13.73 vs
13.66 px, CH04 height 2.234 vs 2.236 m; `compare_vs_release.txt` in that folder). So the
laptop's 42 mm frame shift came from the OpenCV 4.13 start, not from the drive or the data.

## Cone supplement and place-field readiness (2026-09-26)

* `cone_supplement.py`: which paddock points each camera sees and can map (inside its verified support), the
  46 mid-point cones of the 2026-09-19 plan ordered by the shared coverage they add to every two-camera
  overlap, scenarios with corner cones and optional new cords, edge cones for CH03-CH06, and the station
  cones visible on 2026-09-18 but never labelled -> `qc\cone_supplement\` (JSON, text, map).
  `cone_sheet.py --out <html>` writes the field sheet from that JSON; the committed sheet is
  `CALIB_CONE_SHEET_2026-09-26.html` in the repository root (52 cones, tape from the T-cord ticks only).
* `fold_stability.py`: how far a point at rat height moves between the release and the five placement-fold
  calibrations (whole pipeline, fold ground corrections refitted with the release settings) ->
  `qc\cv\FOLD_STABILITY.txt`. Panos: 1-3 mm median, 21 mm max; CH03 53 mm median, 203 mm max; the degree-4
  pano warp instead of degree 3 moves CH01 by 49 mm median.
* `AUDIT_PLACE_FIELD_READINESS_2026-09-26.md`: what can be said about mapping every camera onto one paddock
  map for place fields, what the old downstream validation does not show, the error sources outside the
  calibration numbers (tracked-point height, ground between labels, camera time offsets, the lattice), and
  what would validate it.

## Plate tilt bound 10 deg instead of 6: no gain, the release keeps 6 (2026-09-28)

24 of the 64 plates sat at the +-6 deg tilt bound in the release, and the operator confirmed plates tilt on
grass, so the whole pipeline was rerun with `FIT_TILT_MAX_DEG=10` into `<root>\qc\variants\tilt10\` (the
release in the repo untouched): the bundle, its ground correction, PADDOCK_AGREEMENT / LINE_CHECK /
CV_LANDMARKS, and the five placement folds (same `folds.json`) scored by `cv_folds_eval.py --cv <dir>`.

| | release (6 deg) | 10 deg |
|---|---|---|
| plates at the bound | 24 | 6 |
| tilt rms / max | 5.2 / 8.5 deg | 6.0 / 11.8 deg |
| weighted corner rms | 7.05 sigma | 7.01 sigma |
| training agreement, every shared corner | 71 / 153 / 248 mm | 72 / 152 / 252 mm |
| held-out per placement median / p90 / max | 76 / 137 / 256 mm | 77 / 140 / 269 mm |
| held-out within 50 / 100 mm | 7 / 18 of 26 | 6 / 18 of 26 |

Mapping through each fit's own frame correction (`compare_vs_release.txt` in that folder): within 1.5 mm on
CH01, CH02, CH03, CH05, CH06 and 4 mm median / 16 mm max on CH04; the bundle frame moves up to 28 mm and the
frame correction takes it back out. The per-fold held-out medians move by 0-5 mm. Freeing the tilt lets the
plates absorb a little more of the image residual without predicting unseen placements any better; a
10 deg tilt of the 800 mm plate is a 139 mm rise of one edge, which grass does not produce, so the extra
freedom is fitting model error, not ground. The 6 deg bound stays.

## Session 2026-09-30 (`session_2026-09-30_15-49-39`, 15:49:46-16:35:26, 12 streams, 18.2 GB)

The return trip of `CALIB_CONE_SHEET_2026-09-26.html`, recorded on the field PC with `calibration_record.ps1`.
The session folder lives on the lab PC's `F:\calibration` (the Field_video_backup drive), not on the portable
drive: pass it explicitly, `--session F:\calibration\session_2026-09-30_15-49-39`; its QC goes to
`<root>\qc\2026-09-30\`. Cameras not moved since 2026-09-18 (operator). Sunny with hard shadows, not the
overcast the sheet asked for.

What was actually laid out (operator, 2026-10-01; differs from the sheet):

* T cords: the cones on ticks y 12 / 66 / 120 / 174 moved 27 in toward y = 240, to T?1M..T?4M (y 39 / 93 /
  147 / 201). The y = 228 cones had no tick above them and stayed on T15..T75.
* V/F columns: all FOUR cones moved 27 in, to y 66 / 120 / 174 / 228 (the sheet planned three and a spare);
  the fourth row is F14M, V24M, F34M, V44M, F54M, V64M on the old T?5 line.
* Column V/F4 (x = 276) was only partly moved: F41M and V42M are where they should be, the other two are
  uncertain (operator). The labelling page offers both its old stations and its mid-points; the label decides.
* Long cords Y39 and Y201 laid along the length (blue in the frames). Corner and edge cones as labelled.
* So T15..T75 never moved (plus any V/F4 cone labelled on its old station): the same physical points as on
  2026-09-18. Labelled in both sessions they test whether a camera moved: CH01 has seven of them labelled on
  09-18, CH02, CH03 and CH04 one each (T15, T15, T75), CH05 and CH06 none (F43 / V44 add to CH01, F41 / V42
  would add to CH02, if they turn out unmoved).
* Field clear of people at the end of the recording; the label frame is 16:35:10.

Ball sweep 16:22:40-16:31:20 (CH02 file offset 22:40-31:20): a white volleyball with red and blue panels,
pushed with a stick, among the cones (they were not picked up), people in view. Too patterned for a colour
detector, so it is marked by hand: `ball_gui.py --session ... --window 16:22:40-16:31:20 --step 2` extracts
every camera at full resolution every 2 s (261 times x 6 cameras, 6.6 GB under `qc\2026-09-30\ball\`) and
writes `ball_gui.html`: the operator marks the visible edge (3+ clicks, circle fit), a diameter (2) or the
centre (1), or says "not in view" / "hidden"; export `ball_labels.json`.

Timing: segment names resolve their start to 1 s (CH03/CH04's 16:00 segment is named 16-00-01, the others
16-00-00) and the files carry no absolute time, so the streams' relative offsets are unknown to ~1 s until the
ball tracks measure them.

Labelling pages built at 16:35:10 with `--supplement` (new in `cone_gui.py` and `line_gui.py`):
`qc\2026-09-30\cone_gui_CHxx.html` shows the mid-points (orange), C1-C4 / E1-E2 (purple), the unmoved cones
with their station IDs (and both choices for column V/F4) and every other old station as a grey dot; it now autosaves in the browser, draws a
small circle with a cross at the clicked point (click the centre of the hole on top of the cone, 50 mm above
the ground) and zooms to 300 %. `qc\2026-09-30\line_gui_CHxx.html` offers Y39 and Y201 (and X60 / X420) with
guides from the release fit. Before these labels can enter a fit, `fit_data.LATTICE` needs the new IDs.

### First look at the 2026-09-30 labels (`check_supplement.py`, held out: none of them is in the release fit)

The operator's cone and cord labels (16:35:10) are in the repository as `session_2026-09-30_cone_labels_CHxx.json`
and `session_2026-09-30_line_labels_CHxx.json` (106 cones in six cameras, cords Y39 / Y201 in four each), and
in `qc\2026-09-30\` under the names the tools read. Result: `session_2026-09-30_supplement_check.txt`.

* Cones against the position of their ID, through the release at z = 50 mm: 94 in support, median 104 mm,
  p90 217 mm, max 296 mm. This is an upper bound on the calibration error, not a measure of it: several
  cones are put at the same off-design place by every camera that sees them (T32M at y 101-103 in by CH01,
  CH02 and CH05, design 93; T72M at y 84-85 by CH01 and CH02, design 93). The operator checked the cones after
  the ball sweep: they were in place. So the gap is the layout itself (ticks, cords, cones on grass) or a bias the
  cameras share through the 2026-09-18 lattice they were all tied to; the labels cannot tell which.
* The same cone in two cameras (the handoff, independent of where the cone really is): 49 pairs, median
  84 mm, p90 167 mm; CH01-CH02 65 / 104, CH01-CH04 160 / 223 (the known worst pair), CH02-CH05 26 / 38.
  In line with the held-out placements of the release (76 / 137 mm).
* Camera stability cannot come from the cones: between 2026-09-18 and 2026-09-30 it rained and the grass grew,
  so a cone that was never touched still sits differently (the T15..T75 and column V/F4 labels shifted 10-67 px
  in every direction, CH01 median 33 px; operator). Image registration on static structure (`camera_drift.py`, not committed) shows CH05 and CH06
  unmoved (0.13 / 0.15 px over 88 / 121 matches); for CH01-CH04 the light changed too much between the two
  days for automatic matching. Stability is judged instead from RIGID landmarks the operator labels - pole
  edges, wall tops, water towers, the boxes on the poles, the PC box - with the analysis repo's
  `cv/cv_field/landmark_gui.py` (`D:\Documents\GitHub\Field2026_Social_analysis`; pages in
  `D:\Field2026_analysis_out\2026c\cv_field_landmarks\`, exports in that repo's `cv/configs/landmarks/2026c/`;
  09-18 reference frames CH01 13:57:30, CH02 15:22:30, CH03 15:45:00, CH04 14:32:30). The same structures labelled
  on a 2026-09-30 frame answer whether a camera moved between the sessions; that tool reads other dates only from
  `F:\3rd_rat`, so it needs a session option for 09-30 first.
* Cords: Y39 maps to within 1-6 cm of y = 39 on average (CH02 -2.3, CH04 -1.4, CH03 +6.1 cm); Y201 maps
  6-18 cm toward y = 240 in all four cameras that see it (CH04 +6, CH03 +11, CH05 +15, CH01 +18 cm). The
  operator measured Y201 at 201 in; a cord on grass is not a rigid straight line (it sags, bends round tufts),
  so part of that is the cord.

What this means for using them: the layout is known to roughly 5-20 cm, not to the tape's millimetres. A cone
or cord seen by two cameras is a tie point whatever its true position - both cameras must put it in the same
place - and that is what the handoffs need. So in a refit the supplement cones enter as positions estimated
jointly from every camera that sees them, held to their design position only by a prior of that size, and the
cords as lines with the same allowance; the old stations keep their role as the frame.

`ball_gui.py` fits a tilted ellipse when 5 or more edge points are marked and lets the operator set one by
hand (centre, long-axis and short-axis handles): on a 180 deg arc of a 40 x 25 px ellipse a circle fit puts the
centre 8-16 px off, the ellipse fit within 1 px (synthetic test).

### The cameras moved a little between 2026-09-18 and 2026-09-30 (`landmark_drift.py`)

Measured on the operator's rigid landmarks (pole edges, the boxes on the poles, wall tops, water towers; labelled on
the 09-18 reference frames with the analysis repo's `landmark_gui.py`, exports in its
`cv/configs/landmarks/2026c/`). The template is the 09-18 frame's own edges within 10 px of those labels; it is
fitted onto the 09-30 frame's edges with a similarity transform. Both sides must be in the same colour mode: an IR
template against a colour frame of the same day already gave 10-18 px in CH03/CH04 (the IR-cut filter moves the
image), under 2.5 px in CH01/CH02. With colour frames on both sides, a second 09-18 frame (control) comes out at
0-0.5 px in every camera. Result `session_2026-09-30_landmark_drift.txt` / `.json`, picture
`session_2026-09-30_camera_motion_poles.jpg` (the 09-18 pole edges drawn at the same pixels on both days).

| camera | 09-18 -> 09-30 (two 09-30 frames) | if the release were used unchanged on 09-30 pixels (z 60 mm) |
|---|---|---|
| CH01 | +7.2 / +7.5 px along x, rotation -0.03 deg | 24 mm median, 57-62 mm max |
| CH02 | -10.1 / -9.6 px, rotation +0.15 deg | 39-40 mm median, 115 mm max |
| CH03 | -22.7 / -20.6 px along y, rotation +0.27-0.29 deg | 37-38 mm median, 79-87 mm max |
| CH04 | (-46, -26) / (-32, -29) px, rotation +0.27 / +0.79 deg - the two frames disagree, size uncertain | 62-71 mm median, 168-176 mm max |
| CH05, CH06 | unmoved (`camera_drift.py`: 0.13 / 0.15 px over 88 / 121 static matches) | - |

Consistent with the analysis repo's finding that every camera shifts a little from day to day. Consequences:
the 2026-09-30 labels (cones, cords, the ball) are in 09-30 pixels and must be carried into the 09-18 pixel frame
through these transforms (or the refit gives CH01-CH04 a pose of their own for 09-30) before they meet the release;
the handoff numbers of `check_supplement.py` above include this motion and are to be recomputed after that. CH04's
transform needs more landmarks before it is trusted (six rigid ones, two frames 14 px / 0.5 deg apart).

### The ball sweep: machine marks and the operator's review (2026-10-01)

Marking 261 times x 6 cameras by hand was too slow, so `ball_sam3.py` proposes marks and the operator reviews
them in `ball_gui.py` (cyan dashed = machine mark with its score; `a` accept, `m` next machine mark, `s` not in
view, `S` not in view for a range of frames, `h` hidden, `l` seen but off the ground - carried or lifted, its
height unknown, kept out of the ground fit). SAM 3 (`facebook/sam3`, text prompts "ball" + "volleyball") runs on
full-resolution 1008-px tiles over the part of each frame where the paddock floor is; a detection is kept if its
size is 0.5-1.8 x what the calibration predicts there and its mask is >= 30 % white (the ball's masks: median
60 %, lowest 30 %; the disc cones 0-25 %); a spot that holds a detection in a quarter of a camera's frames is a fixed object (a blue cone in CH03, a
pipe cap in CH06) and is dropped; a Viterbi pass per camera picks one detection or "not in view" per frame. A first
version sent the small cameras in whole (the ball ~20 px across after the shrink to 1008 px) with "volleyball"
alone at conf 0.2, and the operator reported many misses; its pano tiles followed "motion", which over 9 minutes of
changing light was the whole frame. Frames the operator rules out (`session_2026-09-30_ball_operator_ranges.json`:
CH03 69-261, CH04 1-243, CH05 140-261, CH06 1-165 and 238-261, GUI numbering) are not searched.

Against the operator's marks (`session_2026-09-30_ball_sam3.txt`): found CH01 22/23, CH02 23/26, CH03 52/54,
CH04 13/14, CH05 18/18, CH06 10/12; none on a frame the operator called not in view or hidden. The operator then
reviewed every camera (`session_2026-09-30_ball_labels.json`, 21:51 export): accepted 112 machine marks, drew
the rest, rejected 37 pano marks as the ball carried off the ground. Machine centres against the operator's own
drawings, on the ground: 5-16 mm median on CH03-CH06, 31 mm (p90 60-67) on the panos, where SAM 3's mask often
covers only part of the ball (one panel close to the camera, the coloured half against the white wall or house,
the top half above the grass).

`ball_refine.py` tried to do better by fitting the outline the calibration predicts for a 105 mm sphere to the
grass / not-grass edge. It is repeatable but biased: where grass hides the ball's lower part it lifts the centre
4-7 px, and the cameras agree less on the same ball with it (88-109 mm) than with the operator's marks (87 mm;
`session_2026-09-30_ball_refine_check.txt`). Not used; the operator's marks stand.

Every mark goes to the ground at the ball-centre height, 105 mm (09-30 pixels carried to 09-18 by
`landmark_drift`). Sweeping that assumed height, the cameras agree best at 80-105 mm (median 86 / 85 mm, 97 at
130, 117 at 160), so the ball sat on the soil, not on top of the grass. Camera clocks: the file names resolve
the start to 1 s, so each camera's offset is a free parameter, fitted from the ball tracks: CH01 -0.3 s,
CH03 +0.1, CH04 +0.8, CH05 +0.1, CH06 -0.15 (against CH02). CH04's is confounded with its position: both of the
sweep's passes through CH04's view ran in -y, so a clock offset and a y offset look the same there, and its
pixel drift between the sessions is itself uncertain (above).

### Ground correction refitted with the supplement cones and the ball sweep (2026-10-01; candidate, NOT the release)

`refit_supplement.py` refits the per-camera ground warp (the bundle is unchanged) for all six cameras jointly:
the 2026-09-18 labels as in the release; every 2026-09-30 cone as a tie point held to its design position by a
4 in prior; cords Y39 / Y201 as lines (weight 0.5); and with `--balls`, every time step two or more cameras saw
the ball as a free tie point, with a clock offset per camera (weight 0.5). Warp degree 3 for the panos as in
the release, 2 for CH03-CH06 (they now have enough points). Outputs under `<root>\qc\refit_2026-10-01_*`
(load with `paddock_map.load(<dir>\camera_fit.npz)`); summaries in the repository:
`session_2026-09-30_refit_cones.txt` / `_cones_boards.txt` (cones only) and `session_2026-09-30_refit_cones_balls.txt`
/ `_cones_balls_boards.txt` (cones + balls, weight 0.5). Three independent checks:

| | boards 09-18/19, two cameras on one corner (median / p90) | held-out cones (5 folds) | held-out balls (5 blocks of the sweep) | balls in the fit |
|---|---|---|---|---|
| release | 71 / 153 mm | 78 / 160 mm | 117 mm | 109 mm |
| cones | 51 / 108 | 69 / 131 | 89 | 85 |
| cones + balls, ball weight 0.3 | 51 / 108 | 63 / 125 | 90 | 81 |
| cones + balls, ball weight 0.5 | 52 / 108 | 61 / 119 | 88 | 75 |
| cones + balls, ball weight 1 | 54 / 109 | 60 / 102 | 89 | 63 |

The cones do most of the work; the balls add tie points where the sweep went and help the held-out cones, but a
held-out block of the sweep (a region the fit saw no balls in) does not improve over the cones alone, and at
weight 1 the boards start to get worse. Weight 0.5 is the candidate. Per camera pair on the balls (weight 0.5 fit,
each fit's own clock offsets; `session_2026-09-30_refit_ball_pairs.txt`, the last column of the table): CH02-CH03
34 mm, CH01-CH06 46, CH02-CH05 47, CH02-CH06 56, CH01-CH03 74, CH01-CH05 77, CH01-CH02 88, CH0x-CH04 201-293. The CH04 end (x > 400 in) remains the weak handoff: clock and position are confounded there (above),
CH04's drift transform is uncertain, and the panos see that end at the corners of their canvas with 2.3-2.5 mm of
horizontal error per mm of height error. What would settle it before teardown: the ball (or anything with a known
height) held STILL for ~3 s at 10-15 spots across CH04's view and the panos' far end - a still object needs no
clock - and a pass in +y as well as -y.

### Poles, plumb lines and the pre-teardown survey (2026-10-01)

Every observation the calibration has used lies on or near the ground (boards 6 mm, cones 50 mm, balls 105 mm),
so the fit cannot tell a wrong lens model from a wrong pose or an uneven floor; the ground warp absorbs all three
on the ground. The operator's rigid-landmark labels (pole edges, house corners on the 09-18 reference frames) test
it above the ground (`plumb_check.py`, `pole_check.py`; output `session_2026-09-18_pole_check.txt`):

* Plumb lines: the long pole edges in the panos (30-40 deg of view) bend by 5-13 arcmin rms (4-10 px) and stand
  0.5-4 deg off vertical; CH03's corner poles A0 / C0 10-19 deg (image corners, unconstrained by any ground data),
  CH04's A4 4-5 deg. A wooden pole may lean 1-2 deg and a label is good to 1-2 px; these are larger.
* Pole size: from the left / right edge labels at the design distances, 144 mm across (p10 114, p90 170).
* Pole positions: two cameras' lines of sight put B1, A4 and C0 about 30 cm from the 10 ft grid point, B3 and B4
  about 10 cm (the operator: the grid is good to about a foot). Two-camera intersections have no redundancy and
  are ill-conditioned where the sight lines are near parallel (B0 from both panos, B2 from either side). So the
  design grid cannot serve as control; straightness and verticality can, without any measurement.

`survey_sheet.py` -> `PRETEARDOWN_SURVEY_SHEET_2026-10-01.html` (repository root) is the field sheet for what
must be measured before the teardown: tape bands at measured heights (~120 / ~200 cm) on the poles, pole
circumference and lean, 44 pole-to-pole laser distances (17 between the nine poles the cameras see first), wall
top height at 24 points, both houses (base size, corner heights, corners to the nearby B and A poles), camera
lens heights, and 26 still-ball spots each seen by two or more cameras (a still ball needs no clock), plus a
+y push along T7. Entries are kept in the browser and copied out as text.

## Release 2026-10-01: ground correction with the supplement cones and the ball sweep

Adopted by the operator after the comparison above (ball weight 0.5). Only `frame_correction.json` changes; the
bundle is the 2026-09-24 one, byte for byte. Boards between cameras 52 / 108 mm (was 71 / 153), held-out cones
61 / 119 (78 / 160), held-out balls 88 (117). `PADDOCK_AGREEMENT.txt`, `LINE_CHECK.txt` and
`DOWNSTREAM_VALIDATION.txt` are regenerated (the latter's ensemble sections compare against the old method and
are not valid for this release). Provenance, reproduction, the evidence and the open points for the audit:
`RELEASE_2026-10-01.md`. The previous warp: git `c3b5cef`, and `<root>\qc\release_2026-09-24\`.

## Release 2026-10-02: the 09-18 lattice cones as latent points

Both audits (`AUDIT_ASTRA_2026-10-02.md`, `AUDIT_FABLE_2026-10-02.md`) pointed at the 2026-09-18 lattice being used
as exact truth in six independent warps. `refit_supplement.py --soft-lattice 4` makes every 09-18 station one shared
unknown position with a 4 in design prior (cords and wall foot stay exact lines); `--rel` pins the baseline warp.
Boards between cameras 52 / 108 -> 39 / 87 mm (CH01-CH04 78 -> 38); the prior's value hardly matters (2 / 4 / 8 in:
41 / 39 / 39). Adding the balls took the boards back to 46, so the balls are left out of the fit and scored instead
by `ball_check.py` (the sweep as a stand-in rat: 81 mm with fitted clocks, CH04 end ~250 mm). Adopted by the
operator; evidence, reproduction and open points in `RELEASE_2026-10-02.md`. Two corrections to earlier sections of
this notebook, from the audits: the pole and plumb-line numbers for CH03/CH04 fed IR-frame labels into colour-mode
rays (10-18 px mode shift; the pano numbers stand), and "model ceiling" was not shown - the lattice term was the
larger removable part.

### IR vs colour on 2026-09-18, measured with landmark_track (2026-10-02)

`ir_colour_shift.py` (output `session_2026-09-18_ir_colour_shift.txt`) runs the analysis repo's `landmark_track`
(NCC on the operator's rigid landmarks, affine, leave-one-landmark-out error) from each camera's labelled IR
reference frame to colour frames of the same day, camera static. Colour vs IR: CH04 (0, -0.2) / (0, -1.8) /
(0, -1.0) px at 14:41 / 15:05 / 15:47 (held-out 1.0-1.3 px), i.e. none to speak of; CH03 (+0.2..+0.7, -5.4..-5.8) px
at three times, a consistent ~5.6 px vertical shift; CH01 / CH02 under 1.6 px. The "10-18 px for CH03/CH04" in the
landmark_drift section above came from edge-template matching across modes and is wrong for CH04 (the periodic
wall corrugation lets an edge template lock one period off; frames minutes apart gave 0 and 18 px). So the cohort
chain's last step (09-18 IR reference px -> the colour-mode boards) is about 5.6 px for CH03 and negligible elsewhere.

### A canvas-space correction for the panos does not pass its gate (2026-10-02)

The Fable audit's E1(b): if the panos' leftover bundle error were a smooth field over the canvas, a correction
learned from some boards would predict the others. `canvas_gate.py` (output `session_2026-09-18_canvas_gate.txt`),
leave-one-board-out, thin-plate field at three smoothings: held-out board residual CH01 5.9 -> 6.3 px, CH02 6.0 ->
7.0 px, worse at every smoothing, better on only 14-47 % of boards; the small and end cameras likewise. The residual
is board-specific (neighbouring boards disagree; the plate poses already absorb each board's mean, 1.9 / 3.8 px
median), not a fixed distortion the boards can teach. Not built.

### Release 2026-10-02 revision b: the 09-30 transforms of CH03 and CH04 were wrong

`landmark_drift.py`'s edge templates lock one corrugation period off on CH03/CH04's walls (CH03 ~25 px; CH04
reported (-46, -26) px but did not move). `landmark_track_drift.py` replaces them (analysis repo `landmark_track` +
the 09-18 IR -> colour step; CH04 through a pre-shift grid), checked by eye on overlays. Refitted with them
(`session_2026-09-30_drift_final.json`): boards 39 / 87 -> 37 / 86 mm, held-out cones 66 / 135 -> 62 / 124,
CH02-CH04 76 -> 53, CH02-CH03 44 -> 24, CH01-CH03 42 -> 71 mm. Adopted; details in `RELEASE_2026-10-02.md`. The CH04
end's ~250 mm on the balls does not change with CH04's transform and is a property of the ball data there.

### The ball sweep at 20 Hz: the CH04 end is fine; frame timestamps are bursty (2026-10-02)

Another session tracked the ball in every frame of every camera (`ball_track20.py`, outputs in
`<root>\qc\2026-09-30\ball\track20\`). `ball_sync20.py` fits one clock offset per camera from the stick's pushes and
compares every frame pair at its aligned time (`BALL_SYNC20.txt`): all pairs 63 / 125 mm, the CH04 end 49 mm,
CH02-CH04 41 mm. The 2-s grid's ~250 mm at the CH04 end was the grid: the recordings' frame timestamps are bursty
(frames arrive in clumps; 0.04-0.09 s rms and up to 0.57 s off a steady 20 fps clock), and frame index / frame rate
is the better time base (63 vs 65 mm). For tracking: time frames by their index within a segment, not by their
stored timestamp. Clock offsets vs CH02 (index base): CH01 +0.20, CH03 -0.07, CH04 -0.55, CH05 -0.11, CH06 +0.15 s.
Frame rate per camera against the PC clock (frame index vs timestamp over the 9-minute sweep): CH01/CH02/CH05/CH06
19.997-20.001 fps, CH03/CH04 19.983-19.985 (~0.08 % slower, ~3 s per hour). So a camera's time within an hourly
file is a line fitted per file (frame index -> PC time, slope and intercept, from its own timestamps), and the
offset to CH02 (which sees the sync LED) is then fitted from simultaneous detections in the overlap. The PC's own
drift (25 ppm since 09-04, `field2026-sync/from-field/*pc-drift*`) is common to every camera and does not enter.

Review and held ball (2026-10-02). `ball20_gui.py` builds a review page of every searched frame (crop around the
ball with the ellipse, stepped or played at 20 fps; flags wrong / missed). The operator's verdict: the tracks are
good, every ball found, the ellipse sometimes loose, and frames with the ball in the hand must go. `ball_sync20.py`
now drops held frames before comparing: intervals seeded at the operator's 2-s "off ground" marks (and stretches
where a camera sees the ball > 1.25x its predicted ground size for >= 0.5 s), grown until the size ratio is back
under 1.10 or an operator on-ground mark, padded 0.15 s. Evidence never comes from comparing cameras, which would
remove the disagreements being measured; the cameras' triangulated height is shown on the review page only. Note
the triangulated height of on-ground frames: 104 mm median (p10-p90 48-181) against the ball centre's 105 mm.
Result: 13 intervals, 94 s, 688 detections dropped, all pairs 62 / 122 mm (was 63 / 125). Operator edits on the
page (h = held from/to, u = not held) are applied with `ball_sync20.py --flags <ball20_flags.json>`.

The operator also saw loose ellipses where grass hides the ball's lower part. Measured against the operator's own
drawings on the 2-s frames (SAM 3 20 Hz detection on the same frame, operator-drawn marks only): the SAM centre
sits 2.5-4.7 px high on CH01-CH04 and its radius is 4-9 % small, while the calibration's predicted radius matches
the operator's within 4 %. A parameter-free fix - keep SAM's top edge and horizontal centre, take the radius from
the calibration where the ellipse is shorter (`--centre top`) - removes most of the vertical offset (CH01 +3.3 ->
-0.4 px) but not the scatter (6.5 -> 6.3 px median), and the cameras agree less with it: all pairs 65 / 134 mm,
CH01-CH02 91 (SAM centres: 62 / 122, 85). Not used. So the CH01-CH02 ball residual is not the grass masks either.

First operator pass on the page (CH01, `session_2026-09-30_ball20_flags.json`, applied with `--flags`): 2 wrong
detections, 15 missed frames, 4 held ranges added (three extend automatic ones by 0.1-0.2 s; 316-331 s extends one
by 8 s and covers CH02's accepted 2-s marks k162-165, a disagreement with the 2-s review left for the operator).
Numbers unchanged: 62 / 122 mm, n 6411 -> 6409. Instead of stepping all ~16,000 frames, the page now lists what is
worth a look (key s): detections > 250 mm from the other cameras at the aligned time, one-frame jumps > 150 mm off
the camera's own track, or a size ratio outside 0.7-1.35 - 615 frames in 88 stretches (CH01 29, CH02 40, others
4-5). The list only steers the operator's eye; a detection leaves the comparison only when flagged wrong from the
image.

Full pass (same day, every camera, same file): 82 detections flagged wrong (CH01 32, CH02 39, CH03 2, CH04 2, CH05 3,
CH06 4), 15 missed, one more held range (507.2-508.0 s). All pairs 61 / 121 mm (n 6324), per camera 42-73 mm, CH04
end 49 / 112, CH01-CH02 85 - the residual between the two panos is not wrong detections either. This is the
operator-reviewed ball check of release 10-02b.

Ball size / height (2026-10-02): the release assumes the ball centre at 105 mm; the operator's ball is a 26 in
(660 mm) circumference volleyball (Franklin, bought at Target), i.e. radius 105.1 mm. The cameras measure it themselves - triangulated centre height 104 mm median - and sweeping the assumed
height 0-250 mm per camera pair, most pairs agree best at 90-130 mm and CH01-CH02 at 105 (85 mm; 87 at 90, 89 at
130). So the ball's true size changes nothing measurable, and the CH01-CH02 residual is sideways, not a height
effect. Per pair (mm at Z = 0 / 60 / 105 / 160 / 250): CH01-CH02 113 / 93 / 85 / 102 / 164, CH01-CH03 136 / 69 / 75 /
141 / 264, CH02-CH03 185 / 104 / 50 / 69 / 189, CH02-CH06 121 / 61 / 28 / 52 / 143.

### Where CH01 and CH02 disagree, and what the wall tops say (2026-10-02)

The two panos hang either side of pole B2 (CH01 at x 243 / y 85 in, CH02 at x 249 / y 159, h 2.35-2.41 m) and
share most of the paddock, yet disagree most on the ball (85 mm). Not CH01's 09-30 transform: landmark_track flips
between three solutions over the sweep (x-scale 1.0007 / 1.0046 / 1.0068); re-tracked at eight times and swapped
in, the release one (A-type) is best everywhere, B and C worse even in the minutes they were measured (CH01-CH02
83 / 98 / 111 mm), so they are tracking ambiguities, not camera motion. By position (60 x 60 in cells, reviewed
20 Hz detections, all inside both supports): east side x 360-420 in 21-26 mm; the far west x 0-60 in 93-125 mm;
around and between the two cameras x 180-300 in 86-186 mm. The offset is systematic: CH01 minus CH02 median
(+75, -14) mm, spread around it 66 mm. The boards cannot show this: CH01 and CH02 share only 4 board stations
(T12, T33, F23, T53); at T12 (x 0-60) they agree to 19 mm where the ball, 11 days later, disagrees by 108.

`walltop_check.py` (rigid-landmark labels, 09-18): the west wall top (WALLTOP_X0) is seen by CH01, CH02 and CH03.
Cut with the plane x = 0, CH01 reports a level wall top (995-1045 mm along y 0-168 in, slope 0 mm/ft), CH03 agrees
with CH01 within 55 mm there and then rises (to 1176 at y 216-240), CH02 rises from 1000 to 1225 mm (+19 mm/ft):
CH01-CH02 +44 -> -199 mm along the wall. With the bundle alone (`--nowarp`) all three tilt more (CH01 970-1137,
CH02 957-1350). The wall's true profile is unknown until the survey, so only the differences count: at ~1 m on
the far wall - above the ground the boards covered - the panos' models disagree by up to 20 cm, most of it CH02.
The other walls give too little overlap (Y240: CH01 and CH03 only at x 0-24, 996 vs 958 mm; Y0: CH02-CH04 -126 mm
at x 432-480). With the surveyed wall-top heights and pole positions these labels become calibration inputs (known
lines the cameras must reproduce, where the ground support is thinnest); without them, a refit could only make the
cameras agree with each other on them.

Operator (2026-10-02): the west wall top is level, one height along its whole length; corrected the same evening
after looking at it: it sags a little in the middle, otherwise level. CH01's profile has exactly that shape (1044
mm at y 0-24 in, 995-1000 at y 96-144, 1035-1040 at y 192-240: a ~45 mm dip in the middle, no slope), so on the
wall CH01 is right and CH02 (rising monotonically +19 mm/ft, up to 20 cm high at y 144-168 in) and CH03 beyond
y 168 in (+12 mm/ft) are not; the drone model can measure the sag itself once it is tied to the paddock. On the ground the vote goes the other way: per 60 x 60 in cell at the far west (x 0-60 in), CH02-CH03 48-52 mm
while CH01-CH02 97-125 and CH01-CH03 51-92 for y 0-180 in; CH01 sits +x of both (+22..+105 mm). So both panos are
off at the far west end, in different image regions: CH01 on the ground, CH02 at wall height - the pano lens
models are extrapolated beyond the boards there, and the level wall top is the first non-coplanar constraint on
them.

### The 2026-09-30 drone photo (2026-10-02)

The operator flew a Potensic Atom 2 over the paddock on 2026-09-30 with the cones in the 09-30 layout
(`F:\calibration\drone\PTSC_0005/0008/0009.JPG`, 3840 x 2160, no EXIF; 0008 near-nadir, the others oblique).
`drone_check.py` finds 42 cones in 0008 by colour, assigns them to the layout and fits a plane homography with one
radial term: cones sit 2.4 in median (p90 4.5) off their design spots after the best plane fit. Column x = 276 is
on F41M, V42, F43, V44 - only F41M moved (the README account had V42M moved too). Against the drone (its pixels
mapped to the paddock by one homography fitted to all camera marks), each camera's labelled cone at z = 50 mm
(`session_2026-09-30_drone_check.txt`): CH03 21 mm median (n 6), CH05 27, CH06 37, CH01 61 (middle 75), CH02 64
(east end 85), CH04 74. An independent instrument puts the two panos and CH04 at 6-7 cm and the other three at 2-4,
as the ball check did. One photo with unknown intrinsics and the sails over the corners limits it; a planned
flight (nadir sets at two heights, overlap for 3D, the ChArUco board photographed by the drone for its lens) would
give cone, pole, wall-top and camera positions to ~1 cm.

### One camera per region, and the jump at each handoff (2026-10-02)

An animal on the ground needs one camera at a time; several matter only where it is handed on. `handoff_map.py`
gives each 40 x 40 in cell a primary camera - the one whose verified support covers it with the finest ground
resolution at 60 mm (choosing by ball error instead was tried first and gives a CH01 / CH02 checkerboard: where
only two cameras see a cell they get the same error) - and measures on the reviewed 20 Hz ball how far the two
cameras put the same instant apart on each boundary where the primary changes (`HANDOFF_MAP.txt`,
`<qc root>\handoff\handoff_map.png`). Regions: CH03 the west 80 in, CH04 the east 80 in, CH05 and CH06 around
their houses, CH01 the y > 120 half and CH02 the y < 120 half of the rest (each pano covers the far half, at 2-3
px/cm along the far walls). Jumps (median / p90 mm): CH02|CH03 26 / 129, CH02|CH06 30 / 50, CH01|CH05 33 / 67,
CH02|CH04 40 / 63, CH02|CH05 42 / 84, CH01|CH04 45 / 112, CH01|CH06 56 / 113, CH01|CH03 58 / 100, CH01|CH02
93 / 197 - the last on the boundary under the two panos (x 200-320 in), which only they see and where both
disagree with everything (186 / 98 mm cells). CH04|CH06 has no ball pairs (not measured).

### Drone footage inside the paddock: first 3-D model (2026-10-02)

The operator flew the Atom 2 inside the paddock at 1-2 m on 2026-10-02 17:37-17:58 (F:\ATOM_001\DCIM\PTSC_0011-0018,
4K 29.97 fps, zoom 1.0x; 0018 was not finalised - "moov atom not found" - and does not open; AUXF holds only 1080p
proxies and thumbnails). What the drone records: the SD-card PHOTOS carry XMP with gimbal pitch / yaw / roll,
aircraft attitude, relative altitude to the cm, focal length 4.73 mm (24 mm equivalent) and a time with zone (the
09-30 "nadir" photo PTSC_0008 was at gimbal pitch -76.65 deg, 14.70 m); the VIDEOS only carry the SRT (altitude in
whole metres, no gimbal angles); app exports strip everything. Gimbal roll reads exactly 0.000 on every photo, so it
is a set value, not a measurement.

`drone_sfm.py` (COLMAP 4.2.1 CUDA build in <root>in; SIFT 414 frames at 1 fps in 17 s and exhaustive matching in
9 min on the RTX 5070 Ti; the incremental mapper ran 42 min on the CPU - GPU bundle adjustment is now the default)
registered 404 of 414 frames from PTSC_0012 / 0014 / 0016 / 0017 into one model: 97,916 points, 0.69 px mean
reprojection error, one camera (f 1473 px at 1920 wide, i.e. 66 deg across; k1 0.075). Seen against its own ground
plane the paddock floor, the wall tops (the orange flagging) and the top frame stand out; its scale and orientation
are arbitrary until known points tie it to the paddock (`<qc root>\drone_sfm6-10-02\`).
