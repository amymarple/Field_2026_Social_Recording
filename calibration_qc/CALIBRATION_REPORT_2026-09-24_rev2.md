# Paddock camera calibration - report for audit, revision 2 (2026-09-24, evening)

Supersedes `CALIBRATION_REPORT_2026-09-24.md` after the independent review
(`AUDIT_CALIBRATION_2026-09-24.md`; point-by-point response in `AUDIT_RESPONSE_2026-09-24.md`).
Every number here comes from the release fit `E:\calibration\qc\camera_fit.npz`
(sha256 `d1b29681e1a54101...`, `fit_manifest.json`) and its companion files, copied into the
repository `calibration_qc/`. Every metric is labelled with what it is: **training** (used by the
fit it scores), **selection** (used to choose a model), **held-out** (scored by a calibration that
never saw it) or **physical** (an independent measurement).

## 1. Setup, data, and what the operator labelled

Unchanged from revision 1, sections 1-2 (paddock 480 x 240 in; seven T-series cords at x = 24 ..
456 in with cones at y = 12 .. 228; 24 V/F cones without cords; one 800 x 600 mm plate with a
12 x 9 ChArUco pattern of 60 mm squares - the operator measured the plate, 23.5 in across, squares
exactly 60 mm; six cameras; sessions 2026-09-18 and -19; operator review of every CH03/CH04
board and sweep frame; cone, cord and wall-foot labels in all six cameras; corrections to labels
recorded in the files with a note). Tape measurements (physical): lens heights above the grass
CH01 2.362 m, CH02 2.337, CH03 2.235, CH04 2.286; positions (236, 92), (249, 160), (112, 128),
(369, 123) in. The operator states the tape reads high if anything, and that the ground under
the grass is the reference.

**Data flow (from the manifest):** 135 camera-placement views assembled -> 5 rejected by the
homography gate (a heuristic trigger: not a proof of wrong ids) + 19 operator outline clicks held
out of the geometry -> 111 -> 1 dropped as not flat in the per-camera plane stage + 4 dropped in
the bundle's second pass -> **106 views, 7,708 corners, 108 cone labels, 64 physical placements**.
The five dropped views are named in the manifest. `rect-markers` frames contribute their measured
marker corners (8 views, 532 corners), never predicted chessboard corners.

## 2. Model

* **Lenses.** Ordinary cameras: pinhole with k1, k2 from the hand-held sweeps, EXCEPT the focal
  length of CH04 and the angular scales of the two panos, which the sweeps and the ground plates
  cannot determine and which were set once from the taped heights (section 6.1): CH04 f = 2960 px
  (sweep gave 3130, CH03 of the same model gives 2949), Duo 3 canvas fu = 2325, fv = 2660 px/rad
  (nominal 2444.6 both; the two panos fitted independently agree to 1 %). These four numbers are
  the only use of the tape in the fit.
* **Plates.** Each plate is (yaw, x, y, tilt_x, tilt_y) with its pattern centre ON z = 6 mm by
  parametrisation and both tilts bounded to +-6 deg by the solver. There is no height freedom.
  A flat 3-DOF plate leaves 7-10 px median residuals; the bounded tilt is an explicit physical
  variable (a plate on grass tilts a few degrees). Achieved: tilt rms 5.2 deg, 24 of 64 at the
  bound.
* **Bundle.** 6 camera poses + 64 plate poses against 7,708 corners, 108 cone labels (cone-top
  height 50 mm, 60 px) and the design station of each plate's cone corner (100 mm), soft-L1 loss
  (f_scale 4 px), lens models frozen, second pass dropping views > max(20 px, 6 x camera median).
  Solver: trust-region reflective with bounds, 8000 evaluations, status "budget reached", cost
  104944.4 - identical to the cost at 4000 evaluations, so the solution is stationary in practice.
* **Ground warp.** Per camera, a 2-D polynomial from the bundle frame to the lattice fitted to
  that camera's cones (points), cords (lines at known x) and straight wall middles (x = 0/480,
  y = 0/240), ridge 8 in per term, degree 3 for the panos (chosen by the placement folds, section
  4.1) and 1 for the others; its verified support (convex hull of its labels + 12 in) is stored
  and enforced. The warp is a ground-plane correction; nothing above the ground was measured.

## 3. Results (training)

| camera | x (in) | y (in) | height (m) | corner residual median / rms (px) | boards |
|---|---|---|---|---|---|
| CH01 | 243.3 | 85.3 | 2.352 | 4.9 / 10.1 | 35 |
| CH02 | 248.8 | 159.4 | 2.409 | 5.1 / 9.6 | 28 |
| CH03 | 117.5 | 124.2 | 2.293 | 5.0 / 23.4 | 12 |
| CH04 | 371.5 | 128.2 | 2.405 | 5.4 / 12.1 | 12 |
| CH05 | 139.3 | 124.8 | 2.315 | 9.5 / 13.7 | 8 |
| CH06 | 346.1 | 129.8 | 2.311 | 13.8 / 16.6 | 11 |

Positions are the bundle frame before the warp. Cone label rms 89 px; plate corner to its cone
149 mm median (this anchor is in the fit; it is an achieved offset, not a check). Warp training
residuals: CH01 7.9 -> 3.7 in rms, CH02 10.0 -> 2.8, CH03 5.7 -> 2.4, CH04 9.2 -> 2.0, CH05 2.0 ->
0.9, CH06 5.7 -> 2.1.

## 4. Validation

### 4.1 Held-out, placement level (the honest expectation for a new plate anywhere)

Five folds of the 64 physical placements. Per fold: bundle refitted with every camera's view of
the held-out placements removed; warp fitted on labels only; pano warp degree chosen on the
training placements inside the fold (3, 3, 3, 4, 3). Held-out placements mapped through that
fold's calibration, all folds pooled (`CV_FOLDS.txt`):

| statistic | value |
|---|---|
| placements scored (seen by 2+ cameras) | 26 of 64 (38 single-camera placements cannot be scored) |
| cross-camera disagreement, per placement (median over its corners): median / p90 / max | **76 / 137 / 256 mm** |
| placements within 50 mm / within 100 mm | 7 / 26 and 18 / 26 |
| per shared corner (correlated within a board): median / p90 / max | 76 / 160 / 286 mm |
| plate corner to its cone, each camera's own reading (held out): median / p90 | 82 / 167 mm |
| the same folds' TRAINING placements, per placement median | 77 mm (no optimism gap) |
| worst held-out placements | T75 256, T74 155, T11 146, T54 128, T22 121 mm |

### 4.2 Held-out, label groups (does the ground warp generalise?)

Each group (one cord in all cameras, one wall side, the cones of one cord) held out of the warp
in turn, residual under the warp fitted on the rest (`CV_LANDMARKS.txt`): all cameras n = 424,
**median 65 mm, p90 185 mm, max 14 in**; per camera medians CH01 3.4 in, CH02 2.1, CH03 1.9,
CH04 2.9, CH05 1.3, CH06 1.9. Worst groups: CH01's X456 and WALL_X0 at ~10 in - the ends of the
pano canvas do not extrapolate; they are mapped only because they were labelled.

### 4.3 Training-set consistency (for comparison with revision 1 only)

Cross-camera disagreement over the 1,364 shared corners of the accepted set, with the release
warp: median 71 mm, p90 153 mm, max 248 mm. This is a training figure (the boards were in the
bundle) and is quoted only to connect to revision 1 (64 / 147 / 302 on a different corner pool).

### 4.4 Physical checks (never used to fit anything they check)

* **Wall foot**, straight middles, through the release mapping: x = -2.6 / -2.3 / -0.5 in (CH01 /
  CH02 / CH03) for the x = 0 end, 479.6 / 477.7 / 478.9 in for x = 480, y = 0.2 and 240.2 for the
  sides. Two cameras' traces of the same segment: 1.5-4.3 in median over the four overlapping
  pairs (WALL_X0 CH01-CH02 3.8, CH01-CH03 4.3, CH02-CH03 1.5; WALL_X480 CH01-CH02 2.4, max 9.2).
  Note the wall middles ARE warp training data; only their agreement between cameras and the
  curved ends are independent of it.
* **Taped camera positions and heights** (not in the fit except the four lens numbers):

| camera | tape (x, y) in / h m | bundle (x, y) / h | warped (x, y) | delta xy (in) | delta h |
|---|---|---|---|---|---|
| CH01 | (236, 92) / 2.362 | (243.3, 85.3) / 2.352 | (244.2, 81.7) | (+8, -10) | -0.01 m |
| CH02 | (249, 160) / 2.337 | (248.8, 159.4) / 2.409 | (245.5, 161.6) | (-4, +2) | +0.07 m |
| CH03 | (112, 128) / 2.235 | (117.5, 124.2) / 2.293 | (119.1, 124.1) | (+7, -4) | +0.06 m |
| CH04 | (369, 123) / 2.286 | (371.5, 128.2) / 2.405 | (368.9, 131.3) | (0, +8) | +0.12 m |

  (The warp is defined for ground points; applying it to a camera's plumb point is indicative.)
* **Cones vs design** through the release mapping: median 2.9 in, p90 8.0 in (training for the
  warp; listed for completeness).

## 5. What the release supports

* Ground-plane positions from any of the six cameras inside each camera's verified support,
  with an expected cross-camera disagreement of about 8 cm (median) and 14 cm (p90) for a new
  point, worse at the two ends of the paddock (the +x end seen by CH01 is the worst region:
  T75/T74 at 15-26 cm held out). Whole-field 50 mm is NOT supported: 7 of 26 held-out placements
  reach it.
* Nothing above the ground. A pixel is a ray; the height assumed for an animal enters at
  0.85-1.0 mm per mm for the panos and CH03/CH04 (finite difference of the actual mapping at the
  frame centre) and 0.1 mm/mm for the nadir cameras.
* The frame is the lattice the operator laid (cords, cones, wall) by definition; the wall and the
  tape are the only absolute checks and agree to 3-10 in.

## 6. Open items

### 6.1 Heights and lens scales (resolved to 0.1 m, stated)

The hand-held sweeps do not determine focal length (CH04's sweep is fitted at 1.95-2.00 px rms by
any f between 2956 and 3173; CH03's at 1.29-1.37 px from 2800 to 3130) and plates on the ground
cannot either. With the taped heights held hard in a per-camera plane fit, the plates' apparent
size fixes the scale: CH04 f = 2964 (ground labels: 2956; CH03 same model: 2949) -> 2960; panos
fu = 2333 / 2318, fv = 2711 / 2616 -> 2325 / 2660 (the canvas is ~190 x 47 deg, not 180 x 50.6).
Residual after this: CH04 +0.12 m and CH02 +0.07 m against the tape. The tape datum (grass vs
soil, lens centre) is the operator's statement.

### 6.2 The panos' canvas corners

The residual inconsistency lives in the upper corners of the pano canvases (the far ends of the
paddock). No smooth per-lens model tried removes it; the degree-3 ground warp absorbs it on the
ground where labels exist and returns NaN outside its support. Held-out X456 / WALL_X0 residuals
of ~10 in for CH01 (4.2) quantify what remains.

### 6.3 Other

* 38 placements are seen by one camera only and cannot be scored for disagreement.
* Solver status is "evaluation budget reached" with a stationary cost; tolerances 1e-14 are never
  met by a numeric-Jacobian trust-region fit of this size.
* The historical experiments (free pano fit, per-lens models, two rectilinear halves, height
  priors) live in the session scratchpad scripts (`pano_vs_pinhole.py`, `pano_halves.py`,
  `flatworld*.py`, `tape_test.py`) and are not reproducible from the release commands.

## 7. Using the release

```python
from paddock_map import load
cams = load()                       # refuses a missing or stale frame_correction.json
xy, why = cams["CH01"].to_paddock((3000, 1500), z_mm=0, units="in", why=True)   # NaN + reason if unsupported
cams["CH01"].to_paddock_inv((240, 120), z_mm=0, units="in")
cams["CH01"].height_sensitivity((240, 120), units="in")                          # model derivative, mm/mm
```
Pixels are UPRIGHT (`space="stored"` for raw pano video). Lengths in the fit file are mm.

## 8. Reproduction

```
python fit_cameras.py --out E:\calibration\qc      # -> camera_fit.npz, fit_manifest.json, CALIBRATION_FIT.txt
python frame_correction.py                          # -> frame_correction.json (sha-bound to the fit)
python paddock_agreement.py --plot                  # training consistency
python line_check.py --plot                         # cords and wall foot
python cv_landmarks.py                              # held-out label groups
python cv_folds_eval.py                             # after the 5 fold fits (fit_cameras.py with FIT_EXCLUDE per cv\folds.json)
```
Environment `C:\Users\Cornell\miniforge3\envs\cv` (OpenCV 5.0, numpy 2.4, scipy 1.17). Inputs and
their sha256 are listed in `fit_manifest.json`; all label files, tables and reports are in the
repository under `calibration_qc/`.
