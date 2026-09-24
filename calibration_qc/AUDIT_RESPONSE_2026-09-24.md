# Response to the independent review of 2026-09-24 (`AUDIT_CALIBRATION_2026-09-24.md`)

Every finding is accepted as stated unless noted. What changed, with the evidence, finding by
finding; the revised acceptance document is `CALIBRATION_REPORT_2026-09-24_rev2.md`. The release
reviewed had fit sha `34a3b874...`; the release described here is sha `d1b29681...`
(`fit_manifest.json`, commit noted there).

## 1 (P1) - plates were not pinned: accepted, fixed by parametrisation

Correct. `FLAT_SIGMA_Z = 1 mm` was a soft prior under a soft-L1 loss and the released plates sat
at -339..+126 mm with 99 mm rms; the report's "pinned" claim was false. The plates are now
parametrised, not penalised: (yaw, x, y, tilt_x, tilt_y) with the pattern centre at z = 6 mm
exactly and both tilts bounded to +-6 deg by the solver (`board_RT` in `fit_cameras.py`,
`bounds=` in `least_squares`). A pure 3-DOF flat plate was tried first: it leaves 7-10 px median
residuals everywhere, i.e. the plates on grass are not flat to the pixel, so the bounded tilt is
kept as an explicit, bounded physical variable as the review suggested. Achieved: tilt rms 5.2 deg,
24 of 64 plates at the bound. The manifest records the sigmas, bounds, environment overrides, solver
status and cost (`solver.status 0 = evaluation budget reached`; the cost at 8000 evaluations equals
the cost at 4000 to 1e-6, so the solution is stationary in practice - stated, not hidden).

Consequence for the numbers: the ordinary lenses' residuals rose (CH05 3.4 -> 9.5 px median, CH06
6.1 -> 13.8), which is the real inconsistency between the cameras' models that the sinking plates
had been absorbing. Cross-camera agreement barely moved (see rev2 table).

## 2 (P1) - agreement was not independent: accepted, held-out validation added

Two validations that never see what they score:

* `cv_folds_eval.py`: the 64 physical placements in 5 folds; per fold the bundle is refitted with
  every camera's view of the fold's placements held out (`FIT_EXCLUDE`), the ground warp is
  fitted on labels only, and the pano warp degree is chosen INSIDE the fold on the training
  placements. Held out, all folds pooled: **per-placement median 76 mm, p90 137 mm, max 256 mm;
  7/26 placements within 50 mm, 18/26 within 100 mm**; the same folds' training placements: 77 mm
  - no optimism gap. The inner selection chose degree 3 in four folds and 4 in one; the release
  now uses 3 (the earlier choice of 4 was made on the same boards, as the review said).
* `cv_landmarks.py`: each label group (one cord in all cameras, one wall side, the cones of one
  cord) held out of the warp: **held-out median 65 mm, p90 185 mm** (n = 424 labels); the two
  worst groups are CH01's X456 and WALL_X0 (10 in), i.e. the ends of the pano canvas depend on
  the labels there and do not extrapolate.

Only 26 of the 64 placements are seen by two or more cameras; 38 single-camera placements cannot
be scored for disagreement and are not. Whole-board corner errors are correlated; the placement-
level figures are the ones to quote. CH02-CH03's pair median rests on one board and is marked so.

## 3 (P1) - predicted corners as observations: accepted, fixed

`rect-markers` frames now contribute the MEASURED marker corners (ids 1000 + 4*marker + k, board
coordinates from the ArUco layout) and nothing predicted; frames without saved marker corners are
dropped; `fit_intrinsics.free_views` excludes outline- and marker-predicted frames. Nine views /
718 predicted corners became 8 views / 532 measured marker corners. Marker corners only match
across cameras that both used markers, so the shared-corner pool for the agreement statistic
shrank (2,482 -> 1,364 corners); the placement-level numbers are unaffected in kind.

## 4 (P1) - unsupported pixels: accepted, fixed

`paddock_map.Camera.to_paddock` returns NaN, and with `why=True` a status, for a pixel outside the
frame, a ray that does not reach the plane, a point outside the camera's verified support (the
convex hull of the labels its warp was fitted to, widened 12 in, stored per camera in
`frame_correction.json`), or a warp inverse that did not converge (checked, not assumed).
`load()` refuses a missing correction and a correction made for another fit (sha256 in both files).

## 5 (P1) - ground warp is not a 3-D model: accepted

The release is declared ground-plane-only. `height_sensitivity()` now differentiates the actual
mapping at the queried pixel (finite difference over 10 mm of plane height) and is documented as a
model derivative, not a verified height accuracy. The tape/fit height discrepancy was traced
(rev2 section 6.1): the hand-held sweeps do not determine focal length, and the Duo 3 canvas is not
the nominal 180 x 50.6 deg; with the taped heights used once to set CH04's f and the panos'
angular scales, the fitted heights are now -0.01 / +0.07 / +0.06 / +0.12 m from the tape. The tape
is used for those four numbers only and is stated as such.

## 6 (P2) - accounting and categorical claims: accepted, corrected

rev2 gives the data flow from one manifest (135 -> 5 bad + 19 clicks -> 111 -> 1 not flat +
4 unexplained -> 106 views, 7,708 corners, 108 cones); the fit's RESULT 3 header no longer calls
the station grid "never given to the fit" (it is a 100 mm anchor); the wall table lists every pair;
the homography gate is described as a heuristic trigger for review, not a proof of wrong ids; the
round trip is described as inverse consistency; the historical free-fit / per-lens experiments are
listed with their scripts in the scratchpad and are not claimed reproducible from the release
commands.

## 7 (P2) - provenance: accepted, fixed

`fit_manifest.json` (git commit, every `FIT_*` override, the effective constants and bounds, lens
sources, counts, dropped views, solver status/cost/optimality, sha256 of every input label file and
of the fit itself) is written with each fit; `frame_correction.json` carries the fit's sha256 and
`paddock_map.load()` checks it. The method majority is now a deterministic tie-break.

## Not changed, with reasons

* The design lattice remains the definition of the frame; its absolute accuracy is the operator's
  tape work and is not independently known. The wall foot (not used to fit the warp beyond its
  straight middle) and the taped camera positions are the only absolute checks and are reported.
* The bounded-tilt plate is a modelling choice, not a measurement; the bound (6 deg) is stated
  and the count at the bound (24/64) is reported so it can be judged.
* Whole-field 50 mm is not claimed. rev2 states what the held-out numbers support.
