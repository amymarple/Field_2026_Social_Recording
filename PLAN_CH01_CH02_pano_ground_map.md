# CH01/CH02 (Duo3 panoramas) → field cm: dense ground-map plan — v2

v2 (2026-09-09): merged with GPT's independent plan for the same task. Complies with
[CAMERA_CALIBRATION_AUDIT_PLAN.md](CAMERA_CALIBRATION_AUDIT_PLAN.md) and
[AUDIT_RESPONSE_2026-09-09.md](AUDIT_RESPONSE_2026-09-09.md). CH01/CH02 are the sole
priority. Deliverables per camera: pixel → field-cm mapping, valid-region mask,
independent error report, and an **orthorectified top view**; plus a joint two-camera
top-view mosaic.

Baseline to beat: existing 20-point 2nd-order polys, fit RMSE 55.9 / 51.3 cm
(fit error, not held-out).

## Board (verified) and method

- **ChArUco 12×9 squares, 60 mm square, 45 mm marker — VERIFIED 2026-09-09** by running
  detection on `calibration.png` in this PC's cv env (OpenCV 5.0.0): 54 markers,
  ids 0–53, dictionary **DICT_5X5_100** (smallest containing id 53; 250/1000 are nested
  supersets), all 11×8 = 88 inner corners interpolate, non-legacy pattern. Constructor:
  `cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, getPredefinedDictionary(DICT_5X5_100))`.
  Physical 720×540 mm. **The detection environment exists on the field PC** — no
  analysis-machine prep needed for this step.
- Remaining physical checks: measure 5 consecutive squares in both directions
  (must be 300 mm; if not, use measured pitch); mount thin/rigid/flat/matte; mark the
  origin corner and long-edge direction; record board thickness.
- Method: **taut-line measured coordinates + flat ChArUco placements + regional
  nonlinear ground map.** Not claimed "proven SOTA for Duo3" — chosen because it is the
  only route that validates directly in ground-cm. Whole-image single-lens models don't
  apply to a stitched dual-lens pano (ChArUco locally is fine — the objection is to the
  global central-projection assumption, not to the fiducials). Generic per-pixel models
  remain research-grade for this. **Camera stitching settings are FROZEN** (vendor
  confirms stitch varies with object distance; ghosting/missing possible); any future
  change to stitch settings = new epoch.

## Desk prep (half a day, before the field session)

1. **Residual plots of the existing 20-pt calibs** (CH01/CH02): check landmark
   correspondence, old coordinates, rotation; ~56/51 cm is old fit error, not yet
   attributable to the model.
2. **Lock pixel space**: the exact decode orientation the tracking pipeline uses
   (stored 2160×7680, rotated); save rotation/scale/crop rules; calibration and
   inference must share them, and a scaled image must map the same point to the same
   field coordinate (checked in acceptance).
3. **Record sheet**: per placement — position ID, start/end time, measured board-origin
   field coords, orientation (origin + second long-edge reference point), plane height,
   set membership (train/validation/test).
4. **Preflight, 3 positions per camera** (near / far / near-seam) from closed footage:
   a placement counts only if ≥12 dispersed corners spanning ≥3 rows AND ≥3 columns
   detect. Where the board fails at range, fall back to **measured large flat cross
   markers clicked manually** (or the board's own outline corners) — do not declare the
   board unusable wholesale. Prior from pixel math: flat-marker decode dies ≈4 m from
   the camera, so pre-mark the log sheet with expected-manual positions.

## Field session — EMPTY FIELD, reserve ~4 h

Operator confirms unrestricted field control time (2026-09-09), so scheduling is free —
pick any day with good daylight and dry weather; the ~4 h budget includes layout,
placements, closure waits, and re-shoots. Both cameras record simultaneously — one
physical session serves both.

**Solo execution is fine** (nothing needs a second pair of hands), with three notes:
(1) anchor the tape end (stake through the ring) for the long edge/diagonal measures —
or better, use a laser distance meter; (2) pre-print the log sheet with IDs/targets/set
assignments and only write deviations — placement timestamps recover from the footage
itself (or phone voice memos, phone-vs-PC clock offset noted once); do NOT use two
identical boards simultaneously (duplicate ids confuse detection); (3) the agent acts
as remote QC: after each batch, it extracts the just-closed segments and verifies
corner counts while the operator is still on site. **The session may be split across
2–3 shorter days** — cameras are fixed, so this is equivalent, provided each day starts
with a fresh-still structure comparison confirming no camera moved, and ends with the
backup verification.

### A. Taut-line field basis (~45–60 min)

Re-verify field edge lengths + diagonals with tape (design grid ≠ measured truth).
Lay **7 lines across the field width** at x = **60, 240, 420, 600, 780, 960, 1140 cm**;
5 stations per line at y = **30, 150, 270, 390, 510 cm** → **35 training placements**.

**Station accuracy comes from a construction chain, not per-station taping**
(operator-simplified 2026-09-09): tape each line's x from the corners along BOTH long
walls (14 numbers, logged) → stretch the line taut at soil level → dab a matte paint
dot on the ground at each pre-marked y tick (the dot IS the station) → lay the board
with its **origin corner on the dot and its 54 cm short edge hugging the line**, which
fixes position AND orientation by construction → checkbox on the sheet. Only a board
that cannot land on its dot (obstruction → moved) gets hand-measured coordinates.
Station IDs are paper bookkeeping only (identification = time + order + position
self-consistency); nothing reflective anywhere on the field (glare/IR blooming kills
nearby corner detection); cones optional, purely for spotting stations from afar.
Strings stay down (straightness validation); a string LOOKING curved in the pano is
expected. The valid region only ever covers ground actually sampled and validated.

### B. Training placements (~60–90 min)

Per station: align board origin AND the second long-edge reference to measured marks →
step clear of both cameras' views → hold **8–10 s** → log ID + time. Extract 3–5 clean
frames per placement and aggregate stable corners; **one placement = one sample**
regardless of frames or corner count. Log board thickness + grass height; where board
height above effective ground makes parallax non-negligible, switch that zone to thin
flat markers rather than forcing z=0.

### C. Validation & final-test placements (~40–60 min)

**24 interleaved positions** between the training grid:
x = **150, 330, 510, 690, 870, 1050**; y = **90, 210, 330, 450** — split alternately
into **12 model-selection validation + 12 final-test** positions; each placement
belongs to exactly one set, shared across both cameras.

Seam extras per camera: one group near / mid / far along each pano's seam. Ghosting,
local stretching, or corner jumps ⇒ sample both sides and treat the seam band as its
own (possibly invalid) region — never force one continuous model across it. Seam and
edge regions each need ≥3 independent test positions; short = add placements. No
extrapolation toward the walls beyond sampled coverage.

### C2. Same-session service for CH03/CH04 (operator-confirmed 2026-09-09)

All cameras record simultaneously, so every ground placement visible to CH03/CH04 is a
free ground control point for them too — same log sheet, same measured coordinates,
same set membership (the audit's shared-assignment rule). The x=60 and x=1140 lines
are each end camera's near zone. The ONLY extra field work for CH03/04 is their
**intrinsics sweep**: hand-held board, 20–30 held poses (1–2 s each) varying
distance/position/tilt (±30–45°), ~10–15 min per camera, slotted into the waits
between placement batches; CH03 first → remote QC on a closed segment → then CH04.
"Step clear" during placements means *do not occlude any camera's line of sight to
the board* (2–3 m to the side suffices) — being in frame elsewhere is harmless.
CH03/04 fitting still follows the audit's order (CH03 pilot) and is not a dependency
of the CH01/02 pipeline.

### D. Before leaving

Only short-window, low-load extraction from `_to_` files that actually exist (top of
the hour guarantees nothing). Check: which stations are usable per camera (occlusion by
the person/structures), far boards resolvable, seam corners trustworthy, all three sets
cover the intended use region. Re-shoot failures on the spot. Optional: static UWB tag
dwells at 3–5 measured positions (10–20 s, tag height + antenna reference logged) —
consistency evidence only.

## Offline: models, top view, interfaces

No dependence on CH03/04; no "flatten the pano first" step.

- Corner field-coords from measured board origin + orientation + measured pitch.
  **Equal total weight per placement** (near boards contribute 88 corners, far ones 4 —
  don't let the near zone dominate).
- Three candidates on identical training data: (1) normalized 2nd-order poly
  (baseline), (2) **piecewise-affine Delaunay — the default, interpretable choice**,
  (3) TPS with smoothing λ from the fixed set {0, 1e-6, 1e-4, 1e-2, 1}, chosen on
  validation positions only. Normalize pixel and field coords first. Reject models with
  folding, multi-valued mapping, or acceptance-region coverage gaps BEFORE comparing;
  then pick by validation position-RMSE; **within 1 cm, prefer piecewise-affine**.
- Seam bands with detected discontinuity become invalid regions; fit each side
  separately. No trusted coordinates outside control coverage — out-of-region queries
  return an explicit invalid value, never a silent number.
- **Top view**: field extent 1219.2×609.6 cm at 1 cm/px (~1220×610 px — a display
  sampling rate, not an accuracy claim), rendered through the SAME validated invertible
  mapping (no separately fitted, unvalidated inverse poly). Deliver per-camera views
  first; the joint mosaic picks the source per region by local validated error and
  keeps source labels + blank invalid regions. Caveat: only the GROUND is rectified —
  rat bodies, poles, box roofs carry parallax.
- **Interface**: keep the existing pixel→field entry point; add model type, valid
  region, and validity in the return. Per camera, archive: source-frame description,
  board definition, measured positions, set split, model, region/seam masks,
  forward+inverse mapping, top view, independent error report, calibration version.
  June parameters are preserved; current results do NOT auto-apply to historical
  footage.

## Acceptance (first-round targets) and failure branches

| Region | Independent final-test requirement |
|---|---|
| Main activity area | position RMSE ≤ 10 cm, max ≤ 20 cm |
| Edges + usable seam neighborhoods | position RMSE ≤ 20 cm, max ≤ 30 cm |
| CH01/CH02 common ground | report both cameras' error vs the SAME measured point (two cameras agreeing ≠ both correct) |

≥12 independent final-test positions per camera, each reported individually and
classified near/mid/far/edge/seam. Final-test is opened only after the model is frozen;
a test-driven model change demotes that test set and requires new test positions.

Engineering checks: wrong board ID/rotation/units must raise, not produce numbers;
scale-invariance of the pixel pipeline; forward/inverse consistency with no triangle
flips; repeated placements/frames never leak across sets; invalid regions and seam
ghosts never enter valid tracks.

Failure triage order: measured coordinates → board height/orientation → pixel
correspondence → spatial coverage → model. Local failures get more points or a smaller
valid region — never averaged away.

Scope: this round accepts DAYTIME geometry under the frozen stitch settings. Night and
historical periods need separate consistency checks. Animal reference-point definition,
cross-camera identity, and body-height parallax belong to trajectory validation, not to
this static calibration's scorecard.
