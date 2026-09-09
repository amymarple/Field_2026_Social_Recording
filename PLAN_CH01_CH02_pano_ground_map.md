# CH01/CH02 (Duo3 panoramas) → field cm: dense ground-map plan

Scope: concrete calibration plan for the two stitched 180° panoramas only.
Complies with [CAMERA_CALIBRATION_AUDIT_PLAN.md](CAMERA_CALIBRATION_AUDIT_PLAN.md)
(placement-level train/validation/test, measured-not-designed coordinates, region
masks, validation-only model selection, test reported once). Baseline to beat: the
existing 20-point 2nd-order polys, fit RMSE 55.9 / 51.3 cm (fit error, not held-out).

New assets this plan is built around:

- **ChArUco board: 9×12 squares, 60 mm square, 45 mm marker, 5-bit dictionary**
  → physical 540×720 mm, 8×11 = 88 chessboard corners, marker dict DICT_5X5_*
  (exact variant to be confirmed from the generator; detector will auto-try 50/100/250/1000).
- Soccer cones (position pre-marking, string anchoring — not clicked as control points).
- Taut ground strings ("拉线") along known pole rows, with pre-marked ticks.

## Why this method (state-of-the-art audit, condensed)

1. **Single-lens models don't apply.** Zhang planar / Kannala-Brandt fisheye /
   Scaramuzza omni all assume one physical lens; the Duo3 output is a proprietary
   software stitch of two lenses. No single (K, D) exists, and the stitch warp is a
   black box.
2. **The actual SOTA for uncalibratable optics is generic/dense models** (per-pixel or
   spline generic camera calibration à la Schöps et al. CVPR 2020, driven by dense
   fiducial observations). Restricted to a single plane — which is all we use — the
   equivalent is: **dense ground control points + a flexible regularized 2D→2D map,
   validated on spatially held-out positions.** That is exactly what a ChArUco board
   laid flat on the ground enables: 88 auto-detected subpixel corners per placement
   instead of one hand-clicked pole base (±2–3 px).
3. **ChArUco over plain checkerboard** is current OpenCV-recommended practice: unique
   marker IDs make partial views and oblique views usable — essential for a flat board
   seen at grazing angle.
4. **Lines are first-class ground control** — the sports-field registration literature
   (broadcast soccer → pitch coordinates) registers cameras primarily on known field
   LINES, not points. Our taut strings along pole rows are exactly such lines: a
   string's image must map to a straight field line, giving a continuous validation
   constraint across the whole field, including far zones where boards are sparse.
5. Fiducial tiles on the floor for ground-truthing camera networks is standard robotics
   practice; per-placement pose (x, y, θ) can be refined inside the fit if anchor
   measurement proves the bottleneck (v2; v1 uses measured anchors directly).

Verdict: dense flat-ChArUco control in the near/mid zone + board-outer-corner targets
and string-line constraints in the far zone + piecewise/regularized map selection on a
placement-level validation set. Per-half lens modeling of the Duo3 is research-grade
effort for no gain on a ground-plane-only task.

## Board detection envelope (estimate — verify on site day 1)

Pixel scale ≈ 42.7 px/° horizontal (7680/180°), ≈ 39 px/° vertical (2160/55°), camera
height ≈ 2.44 m (layout value — verify). A 45 mm marker needs ~14 px on its short
(foreshortened) axis to decode (7 modules × ~2 px):

| Distance from camera | marker px (H × V, flat on ground) | decodes? |
|---|---|---|
| 3 m | ~37 × 21 | yes |
| 4 m | ~25 × 13 | marginal — the empirical boundary |
| 5 m | ~20 × 9 | no |

So: **ChArUco auto-corners work within ~4 m of each pano camera** (both sit near field
center → the union disc covers roughly the central 60–70% of the field). Beyond that,
the board's **outer corners** stay clickable to 8+ m (720 mm ≈ 220 px at 8 m): far
placements contribute 4 manual corners each, on the same flat, metrically known target.
One target type for the whole field; cones only mark where it goes.

**On-site check is mandatory:** after the first 3 placements, extract the closed
segment and count decoded corners before committing to the full pattern.

## Field procedure (~45–60 min of the audit's half-day visit, two people ideal)

**Prep (indoors, before the day):** confirm the board's dictionary variant; mount the
board rigid + matte; measure the ACTUAL square pitch after mounting; prepare 3 strings
with ticks every 61 cm (measured, taped); print the placement log sheet with
pre-assigned sets.

1. **Strings (15–20 min):** stretch taut ground strings along pole rows A, B, C
   (known lines y = 0 / 304.8 / 609.6). Cones anchor ends and pre-mark the ~32
   placement spots. Strings STAY DOWN for the whole session (they double as
   validation lines and are recorded continuously).
2. **Placements (~25–40 min):** one board moved through **~32 stops**, 8–10 s flat and
   stable per stop (press into grass, weight corners if windy):
   - 25 = 5×5 audit sketch grid (10/30/50/70/90% of length × width);
   - 4 = field corners, ~1 m in from the walls;
   - 3–4 extra straddling each pano's **stitch-seam band** (the ground line along each
     camera's aim direction, at ~1.5 / 3 / 5 m from the camera).
   Per stop, log: sequence ID, PC-clock time (hh:mm:ss), measured anchor coordinates
   (distance-along-string tick + perpendicular offset by rigid stick/tape, target
   ≤ 2 cm), board orientation reference. **Position, not design, is the recorded
   truth** (audit rule). Sets are pre-assigned per stop — 12 train / 6 validation /
   6 final-test per camera, assignment shared across both cameras (no leakage).
3. **Before leaving:** wait for segments to close, extract, verify: decode counts in
   the near zone, outer corners resolvable at the far stops, strings visible
   end-to-end in both panos. Re-shoot failures immediately.

## Offline pipeline (new script: `charuco_ground_map.py` in the CV folder)

1. **Extract** one frame per placement from the logged time (median over the hold);
   record source file, PTS, and rotation handling so the pixel space provably matches
   the tracking pipeline's decode orientation (Duo3 stored rotated 90°).
2. **Detect**: ChArUco corners near-zone; manual 4-corner clicks far-zone (tool
   prompts per placement). Output a control table:
   `placement_id, set, corner_id, u, v, X_cm, Y_cm`.
3. **Fit on train only**, three candidates:
   (a) normalized 2nd-order poly — the recomputed baseline;
   (b) **piecewise-affine on a Delaunay triangulation** of control points (audit's
   suggestion);
   (c) thin-plate spline over a regularization-λ grid.
4. **Select on validation** (placement-level). Freeze. **Report final test once.**
   If the test drives a model change, it demotes to validation and a new test set is
   collected (audit rule).
5. **Region mask** = control-point coverage; the seam band and pano edges are separate
   regions with their own numbers. **String report**: click ~15 points along each
   imaged string, map, fit a line, report perpendicular residuals along the full
   length — continuous far-field evidence between placements.
6. Session-folder outputs per audit §4.5: raw labeled points, model params, masks,
   error-arrow map, string residual curves, epoch entry in the README ledger.

## Acceptance (audit §5 thresholds)

| Region | Final-test target |
|---|---|
| Mid-field (dense ChArUco zone) | RMSE ≤ 10 cm |
| Pano edges & seam band (each region) | RMSE ≤ 20 cm, max error reported |

≥ 3 independent test positions per claimed region; regions that fail get a mask
(published as unvalidated), never a relaxed threshold. Beat-the-baseline check: the
current 20-point polys (55.9 / 51.3 cm fit RMSE) must be exceeded by a wide margin in
the covered region or something is wrong with the pipeline.

## Bonus (out of scope here, note for CH03/04)

The same ChArUco board improves the CH03/04 intrinsics session: partial views are
usable, so image-edge coverage no longer requires the whole board in frame — the
"can't reach the top corners from the ground" limitation largely dissolves. Requires a
ChArUco-aware path in `intrinsics.py` (small addition, same detector as this plan).
