# Methods audit against the state of the art - paddock multi-camera calibration (2026-10-03)

Auditor: Claude (Fable 5.1). Read-only; nothing in either repository or data root was changed. Audited tree:
`G:\Field_2026_Social_Recording` at `77b22a4` (canonical) plus the uncommitted in-flight work read as such
(`fit_cameras.py` FIT_FREE_PANO / FIT_SWEEP / FIT_INIT, `refit_supplement.py --fit`, `ball_sync20.py --dump`,
`board_sweep20*.py`, `sweep_check.py`, and the trial outputs under `F:\calibration\qc\trial_sweep\` and
`F:\calibration\qc\release_candidate_2026-10-02c_sweepA\`). Release = 10-02b (`camera_fit.npz` `6e4b54e9...`,
`frame_correction.json` `2654a6a6...`). No video or image was opened; the one computation I ran reads the release
`.npz` / `.json` only (`C:\Users\Cornell\AppData\Local\Temp\fable_audit\geom_check.py`, output `geom_check.out`).
Below, **Q/** = `calibration_qc\`, **F/** = `F:\calibration\qc\`. Line numbers refer to the G: working tree as read
today (the in-flight `fit_cameras.py`). Expected gains are engineering estimates from the rig's own numbers, not
measured effects. I build on `AUDIT_ASTRA_2026-10-02.md` and `AUDIT_FABLE_2026-10-02.md` (their experiments A/B and
E1(a) were run and adopted as release 10-02; E1(b), the board-taught canvas field, failed its gate - `Q/README.md:795-802`)
and do not repeat them.

## Executive summary

1. **Make the Duo 3 canvas model honest where the data say it is wrong, with the camera centres held.** The release
   treats each pano as one centre + two constant angular scales. The rig's own data refute constant scales at
   |azimuth| > 60 deg: raw far-cord offsets of 13-14 in (`Q/LINE_CHECK.txt`, "raw off") are a 1.2-1.3 deg elevation
   error at the canvas corners that the ground warp hides at z = 0 and that returns as the 20 cm wall-top error at
   z = 1 m; the air boards' apparent size is 7-18 % off (`F/release_candidate_2026-10-02c_sweepA/SWEEP_CHECK.txt`).
   Change: per lens half, azimuth-dependent scales fu(az), fv(az) (4-6 parameters per half) in the bundle, together
   with tape/drone camera centres as frame-free constraints (inter-camera distances and heights, sigma 2-3 cm), fitted
   on ground plates + air boards + the level west wall top, scored on held-out sweep instances by SHAPE and on the
   wall tops. Expected: wall tops 20 cm -> 3-5 cm; far-west CH01-CH02 on the ball 93-125 -> 50-70 mm; above-ground
   (0.1-0.5 m) handoffs 15-19 px -> 6-10 px. Desk, 2-3 days; the hooks already exist.
2. **Mask the stitch seams and the canvas bottom edge in the pano supports and in the handoff map.** The three
   worst CH01-CH02 ball cells (182-186 mm, x 200-280 in) sit on CH01's seam (|u - W/2| = 98 px), on CH02's seam
   (96 px) and at both canvases' bottom edge (`geom_check.out`); the Duo 3 stitches for one distance (default 8 m,
   Reolink support) so a 1-2 m object at the seam is parallax-shifted or ghosted. Expected: CH01|CH02 handoff jump
   93 / 197 -> ~50 / 110 mm; CH01-CH02 ball 85 -> ~65 mm. Desk, half a day; needs one look at a seam frame.
3. **Use tomorrow's drone photos as the survey instrument the rig never had, and register the rig cameras into
   that model ("infrastructure-based calibration").** Pre-calibrate the drone lens on the ChArUco photos and fix it;
   fly nadir + oblique + low passes; break the paddock's symmetry with unique markers and reject image pairs whose
   two-view rotation contradicts the XMP gimbal yaw; scale from the laser pole distances with 30 held-out check
   points; then localise each rig camera's frame in the model (feature matches, PnP; cube-map faces for the panos).
   Yields camera centres to 1-2 cm, a floor height map (the unknown both audits flagged), the wall-top profile, and
   thousands of 3-D points across every canvas - the only data that make a richer pano model identifiable above
   0.5 m. Field 1-2 h, desk 2-3 days.

Then (section 6): sigma maps per camera and cell, a ground-plane Kalman filter with per-camera covariance and the
measured clock offsets, primary camera with hysteresis and a consistency gate; blending only where the two cameras
agree within their sigmas.

## 1. Architecture vs SOTA

**Verdict: sound for what it had to do, but it is two half-models stacked; the second (an object-space polynomial)
is where SOTA differs and where the rig's remaining errors live.**

What the pipeline is (`Q/fit_cameras.py`): stage 1 pinhole intrinsics from free-pose views (`Q/fit_intrinsics.py:79-103`),
pano canvas fixed to an equirect with two pinned scales (`:105-112`, `PANO_SCALE` `:32`); stages 2-4 per-camera
plane fits and registration; stage 5 a sparse robust bundle (soft-L1, f_scale 4 px) over 6 poses + 64 plates
(5 DOF each, centre on z = 6 mm, tilt bounded +-6 deg, `:526-538`), with station anchors and cone labels
(`:689-724`), numeric Jacobian, 8000 evaluations, stopping at budget (`:793-794`, `Q/CALIBRATION_FIT.txt` "status 0").
Then a per-camera polynomial warp in paddock inches, degree 3 (panos) / 2, ridge 8 in, fitted to cones (now latent),
cords and the wall foot (`Q/frame_correction.py:40-52, 110-156`; `Q/refit_supplement.py:183-254`), applied to the
ray-plane intersection at any z (`Q/paddock_map.py:98-104`).

Against SOTA (Kalibr-style factor graphs; multi-camera rigs with fiducial, line, plane and prior factors, e.g.
[A Factor Graph Approach to Multi-Camera Extrinsic Calibration](https://arxiv.org/pdf/1811.01254); generic camera
models [Schöps et al., CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Schops_Why_Having_10000_Parameters_in_Your_Camera_Model_Is_Better_CVPR_2020_paper.pdf)):

* **Right:** robust sparse BA; plates parametrised on the ground (identifiability); lens not refit on coplanar data;
  station identity from the operator; latent cones with a layout prior; held-out checks by placement and by cone ID;
  support hulls; provenance hashes. The 09-24 report's labelling of every metric (training / selection / held-out /
  physical) is better practice than most published calibrations.
* **Not SOTA, and it costs accuracy:** the correction layer is in object space. Photogrammetry puts systematic
  corrections in image/ray space ("additional parameters", Brown-type or spline), because a ray-angle error maps to
  a different ground displacement at every height and range. The release applies one xy displacement at every z
  (`Q/paddock_map.py:104`). Proof it matters here: `Q/LINE_CHECK.txt` "raw off" (bundle, no warp) puts the x = 24
  cord at 10.6 in for CH02 and the x = 456 cord at 470.2 in for CH01 - both far ends 34-36 cm too far. From
  CH02 at (248.8, 159.4) in, h 2.409 m: atan(2.409/5.71 m) - atan(2.409/6.05 m) = 1.17 deg; for CH01: 1.33 deg.
  That is a ~55 px elevation error at fv = 2660 px/rad in the canvas corners (|az| 60-80 deg, el +14..+22 deg,
  `geom_check.out`), where the bundle has NO decoded boards - CH02/T11, T12, T13, T14, V11, F12 and CH01/T12, T13, T15
  are operator clicks held out of the geometry (`Q/CALIBRATION_FIT.txt` lines 15-22). The warp removes the 35 cm on
  the ground and nothing above it: `F/WALLTOP_CHECK_WALLTOP_X0.txt` has CH02 rising +19 mm/ft to +225 mm against
  CH01 at y 144-168 in - exactly CH02's canvas right edge (az +83..+91 deg, `geom_check.out`; y > 168 in is outside
  its canvas). The 20 cm wall error and the 35 cm raw cord error are the same 1.2 deg.
* **Two layers hide which is wrong.** The bundle trades camera position against orientation (fact 4: centres 9.7 in
  rms off the tape while the ground mapping holds; `Q/README.md:964-968`), and the warp absorbs the rest. A joint
  estimate with the lattice (latent cones, cords and wall foot as line factors, wall top as a line at surveyed
  height), the camera centres as priors and the pano canvas parameters in one problem would attribute the error to
  the parameter that owns it. The in-flight FIT_SWEEP trial is the first step in that direction and shows the
  trade-off directly: adding 393 air-board instances with lenses fixed moves CH01 from x 243.3 to 249.7 in and
  CH03 from 117.5 to 120.5 in - away from the tape (236, 112) - and lifts/lowers heights by 8-12 cm
  (`F/release_candidate_2026-10-02c_sweepA/CALIBRATION_FIT.txt` RESULT 1; `F/trial_sweep/TRIAL_SWEEP_2026-10-02.md`
  heights table), while the ground checks do not move (the warp re-absorbs). The solver is buying agreement on the
  air boards with camera position because the canvas model cannot supply it.
* **Solver:** a numeric-Jacobian trust-region fit that stops at its budget (`Q/fit_cameras.py:793-794`; "cold start
  ~20 h" with the sweep, `TRIAL_SWEEP_2026-10-02.md`) cannot deliver the covariance a downstream sigma map needs.
  SOTA is analytic Jacobians in a sparse Schur solver (Ceres / pyceres / GTSAM): minutes instead of hours, converged,
  and J^T J gives per-camera, per-pixel ground uncertainty for free.

**The single change that most reduces the cross-camera disagreement, CH01-CH02 included:** hold the camera centres
(tape + drone, as relative constraints, section 2) and give each pano half azimuth-dependent angular scales
(section 3), fitted on ground plates + air boards + the level west wall top. Evidence it is the lever: the far-west
and canvas-edge regions are exactly where the panos disagree with everyone (fact 2; `Q/HANDOFF_MAP.txt` cells x 0-40:
CH01 85-113 vs CH03 22-48), the sweep shape residual (0.81-0.84 vertical, 0.92-0.95 horizontal) is untouched by
poses alone, and the wall-top slope is CH02's canvas edge. Expected on the ground: far west 93-125 -> 50-70 mm;
CH01-CH02 overall 85 -> 60-65 mm (the rest is the seam, section 1 item 2 of the summary); above ground: wall top
20 -> 3-5 cm; sweep held-out 19 -> 6-10 px. Cost: 2-3 desk days (the hooks FIT_FREE_PANO / FIT_SWEEP / FIT_HEIGHT_PRIOR
exist; add an xy-distance prior and per-half az-dependent scales to `fm.project`/`bearings`). Risks: identifiability
if centres are not held (trial B lifted every camera 7-16 cm, `TRIAL_SWEEP_2026-10-02.md`); over-fitting the ends
with few air boards - score only on held-out sweep instances and wall tops, never on training residual.

## 2. Camera centres: how to use the tape and the drone

**Verdict: use them as frame-free constraints with realistic sigmas, not as hard pins and not as absolute positions
in the bundle frame.**

Facts: drone agrees with tape to 2.0 in rms after a common (+1.6, -5.0) in shift (`Q/README.md:957-968`,
`F/camera_centres_2026-10-03.json`); the bundle is 9.7 in rms off (CH03 +11 in, CH04 -8, CH01 +7/-12); heights agree
within 5-12 cm. Two reasons not to pin:

* **Frame.** The bundle frame is defined by the lattice through the warp; the tape frame is the operator's cord grid;
  the drone frame is anchored on the DESIGN pole grid (`Q/drone_landmark_anchor.py:9-15, 117-123`) which the panos'
  own pole check puts 10-30 cm off at B1, A4, C0 (`Q/README.md:750-753`). The (+1.6, -5.0) in common shift is that
  ambiguity. Absolute xy priors in the bundle would fight the warp's frame. Inter-camera DISTANCES (CH01-CH02 74 in,
  CH03-CH04 257 in, CH01-CH03, ...) and heights are frame-free and measured to ~2 in / ~3 cm: constrain those.
* **Datum.** "Lens centre" on a Duo 3 is two entrance pupils a few cm apart (the baseline is unmeasured - a ruler on
  the housing settles it, 1 min); grass vs soil moves the height datum 2-5 cm. A 1 cm sigma would push that error
  into plate tilts (24/64 already at the +-6 deg bound, `Q/CALIBRATION_FIT.txt` stage 5) or into the lens.

Recommendation: `FIT_HEIGHT_PRIOR` exists (`Q/fit_cameras.py:424-436`, sigma 0.03 m) - use it with the tape heights
and add pairwise-distance residuals with sigma 5 cm (tape 2 in rms) and, optionally, absolute xy with a shared
translation nuisance (gauge) so only the shape of the camera network is constrained. Run it WITH the air boards and
the richer canvas (section 3); without them the centres and the canvas error will still trade.

Expected effect: on the ground at rat height almost nothing - a centre error dC compensated on the ground displaces a
point at height h by dC * h / H: 250 mm centre error -> 6 mm at 60 mm, 11 mm at the ball, 106 mm at the 1 m wall top
(`geom_check.out`). So the centres matter for walls, climbing animals, the houses' roofs and for identifying the lens
model, not for a rat on the grass. Over-constraining risk: the CH04 end (tape +0.12 m above the fit in both drone and
bundle, fact 4) may be a real datum difference (housing vs lens; the drone's single model) - give CH04's height a wider
sigma (5 cm) and report the plate-tilt histogram and the sweep shape ratios after every refit as the over-constraint
alarm.

## 3. The Duo 3 pano model

**Verdict: the equirect-with-two-scales canvas is under-parametrised and demonstrably non-uniform; a two-lens-half model
with azimuth-dependent scales is identifiable now; a generic (B-spline) ray model becomes identifiable only with the
drone model; an explicit two-fisheye + stitch model is not worth building.**

What the canvas is, from the vendor: the Duo 3 stitches two lens images with a user-settable **stitching Distance
(default 8 m, range 2-20 m)** and Horizontal / Vertical overlap offsets; "the stitched area may be affected by the
distance of objects being monitored", with ghosting or missing objects when the distance is wrong
([Reolink support: image stitching](https://support.reolink.com/hc/en-us/articles/9156003952025-How-to-Set-up-Image-Stitching-via-Reolink-App)).
Consequences for a 1-7 m paddock stitched for 8 m: (i) within the blend band at the seam, an object at range d is
displaced by about b (1 - d / 8 m) along the baseline (b = lens separation) - near the full baseline for a ball at
1-2 m - and can be doubled; (ii) outside the band each half is one fisheye re-projected by the vendor's warp, so each
half has its own centre (offset by b/2) and its own residual distortion. Please record the three stitching values
from the app for both Duo 3s before teardown (read, do not change: the live footage must keep its canvas).

Evidence in the data (new, from `geom_check.out` on the release fit):

| where the panos fail | canvas position | reading |
|---|---|---|
| CH01-CH02 ball cell x 200-240, y 120-160: 186 mm (`Q/HANDOFF_MAP.txt`) | CH01 az -2.4 deg, 98 px from its seam (u 3742); CH02 at its bottom edge (el +26, v 2293) | seam / edge |
| cell x 200-240, y 80-120: 182 mm | CH01 233 px from the seam at the bottom edge (el +28, v 2365); CH02 az +22, el +6 | seam + edge |
| cell x 240-280, y 120-160: 85-89 mm | CH02 96 px from its seam, bottom edge (v 2390) | seam / edge |
| far west x 0-40, y 80-120: CH01 79-87 mm vs CH03 22-48 | CH01 az -61, el +14 (upper-left corner); CH02 az +72, el +1 (right edge) | canvas corner / edge |
| east x 360-400, y 40-80: 16-18 mm | CH01 az +80, el +23 (!); CH02 az -40, el -4 | fine where CH02 is mid-canvas |
| west wall top, CH02 +19 mm/ft (`F/WALLTOP_CHECK_WALLTOP_X0.txt`) | CH02 az +66..+91 deg (right edge), beyond the canvas for y > 168 in | edge |
| sweep boards: CH03->CH01 vertical size 0.81-0.84, CH04->CH02 horizontal 0.92-0.95 (`SWEEP_CHECK.txt`) | |az| 58-65 deg | local scales 7-18 % below the global fu / fv |
| raw far-cord offsets 13-14 in (`Q/LINE_CHECK.txt`) | corners, |az| 60-80 | 1.2-1.3 deg elevation |

The seams: CH01's runs on the ground from (219, 244) to (226, 112) in, CH02's from (261, -2) to (258, 128)
(`geom_check.out`), i.e. through the middle of the paddock where the CH01|CH02 primary boundary runs. The fact-2
statement "not SAM mask truncation" stands; this is a different mechanism (stitch parallax / ghosting at the seam),
and it is testable without a fit: the operator looks at one CH01 frame with the ball or a cone crossing u ~ 3840.

What is identifiable with what exists:

* **Per lens half: pose + fu(az), fv(az) as low-order even polynomials in az (and optionally a cu offset per half):**
  identifiable from ground plates + the 559 pano views of air boards (board centre 0.14-0.54 m) + the level west
  wall top + pole plumb lines, PROVIDED the centres are held (section 2). The FIT_FREE_PANO trial already shows the
  direction (B: fu 2386 / 2383, fv 2800 / 2706, k1 -0.045 / +0.022 - opposite signs for two identical cameras, which
  is what a whole-canvas k1 does when the halves differ). The earlier `--split` test (`Q/fit_cameras.py:62-64`) is not
  evidence against two halves: it assigned whole boards by median u, dropped straddlers, had no air boards, and on
  coplanar data a per-half pose can absorb a scale error anyway (as `AUDIT_ASTRA_2026-10-02.md` section 2 said).
* **Generic / non-parametric (B-spline over (u, v), per-pixel rays)** - the SOTA for odd optics
  ([Schöps et al. 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Schops_Why_Having_10000_Parameters_in_Your_Camera_Model_Is_Better_CVPR_2020_paper.pdf);
  [review of wide-angle calibration](https://arxiv.org/pdf/2306.09014)) - needs dense, non-coplanar 2-D/3-D
  correspondences over the whole canvas. Boards alone could not teach it (`Q/README.md:795-802`, the canvas gate);
  the drone model (section 4) can: it puts thousands of matched 3-D points at all heights across each canvas. Build
  it AFTER the drone model exists, as a coarse B-spline correction (daz, del)(u, v) on ~12 x 5 knots per half with a
  smoothness prior, validated on held-out poles / wall segments / sweep instances.
* **Explicit two-fisheye + stitch model:** not identifiable from the stitched output (blend band, unknown vendor warp,
  depth-dependent stitch), and not needed - the per-half model plus a seam exclusion band captures what matters.

What I would build, in order: (a) seam band and bottom-edge band removed from each pano's verified support (start
+-300 px about u = W/2 and the last ~150 rows; tune on the ball cells), and the handoff map recomputed - half a day;
(b) per-half az-dependent scales with centres held, scored on held-out sweep shape, wall tops, and the far-west ball
cells - 2-3 days; (c) B-spline correction from the drone model - after section 4. Expected gains: (a) CH01|CH02 jump
93 / 197 -> ~50 / 110 mm, CH01-CH02 ball 85 -> ~65; (b) far ends 50-70 mm on the ground, wall tops 3-5 cm, above-ground
handoffs 2-3x better; (c) whatever (b) leaves, validated densely. Risks: (a) loses coverage under the cameras where no
third camera looks (x 200-280, y 80-160) - keep the band as narrow as the ghosting allows and prefer the pano whose
seam is farther; (b) few air boards at the far east for CH01 - report per-half parameter uncertainties.

## 4. The drone as the survey instrument; pipeline for tomorrow's photos

**Verdict: right instrument, right time. The 10-02 experience (ghost copy, pieces that do not reconnect) is the textbook
symmetric-scene failure; it is solved by capture design plus three processing rules, not by a different SfM engine.**

SOTA, briefly: global SfM ([GLOMAP, ECCV 2024](https://arxiv.org/abs/2407.20219v1)) matches COLMAP's accuracy orders of
magnitude faster but "still struggles with scenes containing ambiguous structures, such as symmetries and repetitive
facades" unless a view-graph disambiguation module is used; learned doppelganger classifiers
([Doppelgangers](https://ar5iv.labs.arxiv.org/html/2309.02420), [Doppelgangers++, CVPR 2025](https://arxiv.org/html/2412.05826v2))
filter the twin pairs; feed-forward 3-D ([MASt3R-SfM](https://arxiv.org/abs/2409.19152v1), VGGT) is robust but less
accurate than COLMAP on metric blocks (RTE 3.3-8.8 deg vs 2.6, and an [aerial-block evaluation](https://arxiv.org/pdf/2507.14798)
finds the same) - use them for initialisation or disambiguation, not as the survey. Flat-terrain nadir blocks with
self-calibrated lenses dome ([James & Robson 2014](https://discovery.ucl.ac.uk/id/eprint/1443475/)); pre-calibration
plus oblique images reduce the error by up to two orders of magnitude. Registering fixed cameras into a prior map is
"infrastructure-based calibration" ([Heng et al., ICRA 2014](https://www.comp.nus.edu.sg/~leegh/papers/infrastructure_based_calibration_icra2014.pdf);
[JFR 2015](https://www.cvlibs.net/projects/autonomous_vision_survey/literature/Heng2015JFR.pdf);
[radial projections, 2020](https://ar5iv.labs.arxiv.org/html/2007.15330)). Accuracy reporting: independent check points
from a source 3x more accurate, minimum 30 ([ASPRS Positional Accuracy Standards, Ed. 2](https://www.asprs.org/wp-content/uploads/2024/03/October2023_HLA-Positional_Accuracy_Standards.pdf)).

Concrete plan for the photo session (overcast, zoom 1.0):

Field (1-2 h, in this order):
1. **Break the symmetry before the first photo.** Four alike walls and alike cones are what produced the 24-deg ghost.
   Put 6-8 unique, large, asymmetric markers on the ground and on poles (the ChArUco board, printed numbers / letters
   on A3, coloured tape in a non-repeating pattern on poles A0, A4, C0, C4, B2), photograph the layout sketch. People
   out of the paddock during passes.
2. **ChArUco for the drone lens**: 25-40 photos in PHOTO mode at zoom 1.0 (the mode the survey uses; photos and video
   have different crops - never one COLMAP camera for both), board 1/3-1/2 of the frame, tilts +-30-45 deg, all frame
   corners covered. Also leave the board flat on the ground in the nadir block (scale bar + check point).
3. **Nadir block** at ~15 m, 80 % forward / 70 % side overlap, two perpendicular line directions (cross-hatch).
4. **Oblique ring(s)** at 30-45 deg off nadir, 8-12 m, looking inward from above each wall (this is the anti-doming
   geometry and ties the wall tops, poles and camera housings to the floor).
5. **Low passes** at 2-4 m along each wall and each pole row; each rig camera housing from 4+ directions at 1.5-3 m
   with the lens visible; the houses; the two towers.
6. **Survey ties during the same hour**: the laser pole-to-pole distances of the survey sheet (keep ~30 % as check
   points), the taped camera heights, the Duo 3 lens separation, the wall-top heights at the 24 points.

Desk (2-3 days):
1. Intrinsics: calibrate the photo-mode lens on the ChArUco set (OpenCV, OPENCV or OPENCV_FISHEYE model as the
   residual dictates); fix them in COLMAP (`--ImageReader.camera_params`, no refinement) - this removes the doming
   degree of freedom. Note the Atom 2 may apply in-camera distortion correction to JPEGs; the ChArUco set measures
   whatever is left, which is exactly what is needed.
2. Features: SIFT 8192 worked at 0.7 px on the videos; add SuperPoint / ALIKED + LightGlue through hloc for the
   low-texture grass and for cross-camera matching (current practice, e.g. [IMC 2025 pipelines](https://github.com/yangyefd/IMC2025);
   [LightGlue in hloc](https://awesome.ecosyste.ms/projects/github.com%2Fcvg%2Flightglue)).
3. **View-graph disambiguation with the XMP you already have.** Photos carry gimbal pitch and yaw and relative altitude
   (`Q/README.md:933-937`). For every verified pair, compare the two-view relative rotation in `database.db` with the
   rotation implied by the two gimbal (yaw, pitch) readings; reject pairs disagreeing by > 15-20 deg. A 24-deg or
   180-deg twin cannot pass. This is cheaper and more decisive than Doppelgangers for a scene whose symmetry is
   rotational. COLMAP also accepts position priors (`pose_prior_mapper`, per-axis std; GPS-free use with large xy std
   and the XMP altitude as a z prior is possible - [COLMAP FAQ](https://codegraph.jelmer.uk/colmap/4.1.1-1/doc/faq.rst))
   and gravity priors from orientation tags.
4. Map with the incremental mapper (fixed intrinsics), cross-check with GLOMAP; expect ONE model if 1 and 3 hold.
5. Scale and frame: `model_aligner`-style similarity on the laser-measured pole network (not the design grid), the
   board squares as a scale check; hold out >= 30 check distances / points and report their RMSE, median, p90 by region.
6. Products: dense MVS or at least a floor point cloud -> **floor height map** on a 0.5 m grid (the term both 10-02
   audits called the largest unmeasured one); pole feet / tops; wall-top profile (settles the ~45 mm sag); camera
   lens centres to 1-2 cm from the multi-view clicks.
7. **Register the rig cameras directly.** Pinholes CH03-CH06: match one daytime colour frame per camera (same day, same
   cones) to the drone photos with LightGlue / RoMa, lift matches to the model's 3-D points, PnP + refinement with the
   rig lens -> pose in the metric model and hundreds of 3-D/2-D residuals across the frame (a direct test of k1, k2 at
   the corners CH03's poles complain about). Panos: render the canvas to cube-map faces, match each face, then fit
   pose + canvas parameters (per-half scales now; B-spline later) to the 3-D points. This is the pipeline the SfM-on-360
   literature uses for equirectangular inputs (perspective sub-views; see e.g. the hloc/SphereGlue variants cited in
   [ORBIT++](https://arxiv.org/pdf/2608.22039)). Expected: centres to 1-2 cm, and the first above-ground, whole-canvas
   validation of the panos.

Risks: wind/light change between passes (overcast helps); JPEG in-camera corrections differing between photo and video
modes (keep modes separate); the design grid creeping back in as control (use measured distances only); over-trusting
MASt3R/VGGT outputs for metric scale.

## 5. Validation: soundness, circularity, what is missing

Check by check:

| check | sound? | circularity / caveat | fix |
|---|---|---|---|
| boards two-camera (`Q/paddock_agreement.py`), 37 / 86 mm | yes as a WARP check | boards are bundle training data; the warp was selected on them (RELEASE 10-02 "Selection"); corners within a board are one measurement (effective n = 31 stations) | keep; quote station-level medians (astra's 50 / 99) |
| held-out supplement cones, 62 / 124 | yes | folds random over space; cords and the 09-18 lattice stay in; shared cameras correlated | spatial block folds (astra 4) |
| 20 Hz ball with fitted clocks (`Q/ball_sync20.py:129-153`), 61 / 121 | yes, the best check so far | clocks fitted on the same data (sharp minima, +-0.2 s doubles the error, so little slack); a unidirectional pass confounds a y-offset with tau (README 09-30); ball height assumed (sensitivity sweep done) | the +y/-y pass with stops; score the return pass with clocks from the out pass |
| drone cones (`Q/drone_check.py:149-154`), 21-74 mm | partly | the drone-to-paddock homography G is fitted to the CAMERAS' marks, so the check inherits their common frame and scale; one photo, unknown intrinsics | tomorrow's model, anchored on surveyed distances, replaces it |
| wall tops (`Q/walltop_check.py`), differences only | yes | IR->colour step applied (`:35`); the wall's true profile unknown | survey heights make it an absolute check |
| camera centres vs tape / drone | yes, independent | drone anchored on the design grid (common shift) | relative distances; the surveyed network |
| placement folds (`Q/CV_FOLDS.txt`), 76 / 137 | the only bundle-independent number | stale (09-24 warp) | rerun once per release (the release notes say so too) |

What SOTA evaluation is missing:

1. **A true independent ground truth**: >= 30 check points of known 3-D position never used in any fit - cone tops,
   board corners and pole feet located in tomorrow's drone model (anchored on laser distances, not the cameras), and a
   few targets at measured heights (the ball on a box, the board on a crate) - scored per camera as ABSOLUTE error on
   the ground and at 0.1-0.3 m, by region, with bootstrap intervals over points. This is the ASPRS pattern and the
   only test that catches a common frame or scale error, which every camera-to-camera comparison cancels
   (`Q/paddock_agreement.py:14-19` says so itself).
2. **Uncertainty, not just error**: covariance from an analytic-Jacobian bundle, propagated per pixel to the ground
   (plus the fold / variant ensemble), giving sigma_c(x, y) maps - the input section 6 needs.
3. **A fused-track test**: a held-out traverse (the return pass) run through the final tracking rule (section 6) and
   scored against the drone / survey positions at the stops; i.e. validate the product, not only the mapping.
4. **Report scope honestly**: the pano support hull is a convex hull + 12 in (`Q/frame_correction.py:143-146`) that
   bridges unsampled space and includes seam cells; after section 3(a) the support should be a per-cell validity mask.

## 6. Tracking across cameras with 3-9 cm biases

**Verdict: biases of this size are not removed by fusion; they are managed by choosing the right camera per cell,
blending only where cameras agree, and estimating the state in one filter that knows each camera's covariance and
clock. Implement in this order.**

1. **Sigma maps.** Per camera and 20-40 in cell: sigma from the ball consensus error (`Q/HANDOFF_MAP.txt` already has
   it), inflated by the height-sensitivity vector x the keypoint-height uncertainty (0.85 mm/mm on the panos,
   `Q/PADDOCK_AGREEMENT.txt` tail) and by the fold/variant spread (`Q/FOLD_STABILITY.txt`: CH03 corners 107 / 170 mm).
   Set sigma = infinity in the seam / edge bands and outside support. One day.
2. **Primary camera with hysteresis** (`Q/handoff_map.py:100-121` chooses by resolution; keep that, but exclude cells
   where sigma > 60 mm when another camera has < 40): switch only after 0.5 s and 1 cell of margin. Removes flicker,
   not bias.
3. **Blend with a consistency gate**: in a trusted overlap, inverse-variance weights; if |p1 - p2| > 2.5 *
   sqrt(s1^2 + s2^2), do not average - keep the primary and flag (astra 6.3's point about (p1 - p2) dw/dt
   manufacturing velocity holds; blend weights must change slowly). Expected: handoff steps of 26-58 mm become ramps
   below a 10 cm bin; the CH01|CH02 93 mm step becomes ~50 after section 3(a).
4. **Ground-plane Kalman filter (constant velocity, 2-D) with per-camera measurement covariance and the measured
   per-file clock lines** (`field2026-sync/from-lab/2026-10-02_cameras-calibration-and-timing.md` section 2-3): each
   detection is a measurement at its own corrected time, so asynchronous cameras need no interpolation, and the
   filter's innovation test is the consistency gate of step 3. This is the standard ground-plane multi-camera design
   ([planar homographic occupancy, Khan & Shah](https://ieeexplore.ieee.org/document/4497204);
   [Kalman ground-plane fusion, BMVC 2009](https://www.bmva-archive.org.uk/bmvc/2009/Papers/Paper261/Paper261.pdf);
   trajectory-based sub-frame sync, [ECCV 2010](https://faculty.runi.ac.il/moses/papers/ECCV-2010.pdf)). Two days.
5. **Factor-graph smoothing with per-day, per-camera bias terms** learned from simultaneous same-animal detections
   (the Fable 10-02 audit's point 3): later, after the drone-based model, because learned biases on top of a wrong
   lens model only make the cameras agree for the wrong reason.

Height convention (both 10-02 audits): one keypoint, one z per keypoint, never 0 for a body point - 60 mm read at the
ground is a 51-64 mm BIAS on CH01-CH04 (`Q/PADDOCK_AGREEMENT.txt`).

## Do not do

* Do not change any Reolink setting (stitching Distance / Horizontal / Vertical, mode) on the live cameras; read and
  record them only. A changed stitch is a new canvas and a new epoch for every frame after it.
* Do not adopt FIT_FREE_PANO variant B (or any free canvas scale) without camera-centre constraints: it lifted every
  camera 7-16 cm above the tape (`TRIAL_SWEEP_2026-10-02.md`).
* Do not fit a dense per-pixel / B-spline ray field on boards alone (the canvas gate already failed); wait for the
  drone model's dense 3-D points.
* Do not fly nadir-only with a self-calibrated lens (doming); do not mix photo and video frames in one COLMAP camera;
  do not use the design pole grid as control once laser distances exist.
* Do not read the drone-cone check (`Q/drone_check.py`) as independent of the cameras' frame - its homography is fitted
  to the camera consensus.
* Do not average two panos' detections within the seam bands or across the CH01|CH02 boundary without a consistency
  gate; do not let blend weights change faster than ~1 s.
* Do not derive clock offsets from a single-direction pass or from PTS; do not transfer the 09-30 offsets to cohort
  files (fit per hourly file against CH02, as the lab note says).
* Do not use MASt3R / VGGT / DUSt3R as the metric survey; COLMAP (+ GLOMAP cross-check) with fixed, pre-calibrated
  intrinsics and surveyed scale is the accurate route; the learned tools are for matching and disambiguation.
* Do not quote whole-field accuracy from camera-to-camera agreement alone; the absolute number waits for the
  survey-anchored check points.

## Sources

Rig: `Q/fit_models.py`, `Q/fit_intrinsics.py`, `Q/fit_cameras.py` (in-flight), `Q/frame_correction.py`,
`Q/refit_supplement.py`, `Q/paddock_map.py`, `Q/ball_sync20.py`, `Q/handoff_map.py`, `Q/walltop_check.py`,
`Q/drone_check.py`, `Q/drone_sfm.py`, `Q/drone_landmark_anchor.py`, `Q/landmark_track_drift.py`,
`Q/paddock_agreement.py`, `Q/fit_data.py`, `Q/board_sweep20_instances.py`, `Q/sweep_check.py`; `Q/README.md` 141-969;
`Q/RELEASE_2026-10-02.md`; `Q/CALIBRATION_REPORT_2026-09-24_rev2.md`; `Q/AUDIT_ASTRA_2026-10-02.md`;
`Q/AUDIT_FABLE_2026-10-02.md`; `Q/BALL_SYNC20.txt`, `Q/HANDOFF_MAP.txt`, `Q/LINE_CHECK.txt`, `Q/PADDOCK_AGREEMENT.txt`,
`Q/CALIBRATION_FIT.txt`, `Q/CV_FOLDS.txt`, `Q/FOLD_STABILITY.txt`, `Q/DRONE_ANCHOR_2026-10-02.txt`,
`Q/session_2026-09-30_drone_check.txt`, `Q/session_2026-09-30_landmark_track_drift.txt`; `F/WALLTOP_CHECK_*.txt`,
`F/drone_sfm/*/SFM_REPORT.txt`, `F/camera_centres_2026-10-03.json`, `F/trial_sweep/TRIAL_SWEEP_2026-10-02.md`,
`F/release_candidate_2026-10-02c_sweepA/*`; `D:\Documents\GitHub\field2026-sync\from-lab\2026-10-02_cameras-calibration-and-timing.md`;
`C:\Users\Cornell\AppData\Local\Temp\fable_audit\geom_check.py` / `.out`.

Literature (relied on above):
[Reolink image stitching settings](https://support.reolink.com/hc/en-us/articles/9156003952025-How-to-Set-up-Image-Stitching-via-Reolink-App);
[Schöps, Larsson, Pollefeys, Sattler, CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Schops_Why_Having_10000_Parameters_in_Your_Camera_Model_Is_Better_CVPR_2020_paper.pdf);
[Geometric wide-angle camera calibration: review](https://arxiv.org/pdf/2306.09014);
[Factor-graph multi-camera extrinsic calibration](https://arxiv.org/pdf/1811.01254);
[Heng et al., infrastructure-based calibration, ICRA 2014](https://www.comp.nus.edu.sg/~leegh/papers/infrastructure_based_calibration_icra2014.pdf);
[Heng et al., JFR 2015](https://www.cvlibs.net/projects/autonomous_vision_survey/literature/Heng2015JFR.pdf);
[Infrastructure-based calibration using radial projections](https://ar5iv.labs.arxiv.org/html/2007.15330);
[GLOMAP: Global Structure-from-Motion Revisited, ECCV 2024](https://arxiv.org/abs/2407.20219v1);
[Doppelgangers, 2023](https://ar5iv.labs.arxiv.org/html/2309.02420);
[Doppelgangers++, CVPR 2025](https://arxiv.org/html/2412.05826v2);
[MASt3R-SfM](https://arxiv.org/abs/2409.19152v1);
[Evaluation of DUSt3R/MASt3R/VGGT on aerial blocks](https://arxiv.org/pdf/2507.14798);
[James & Robson 2014, doming in UAV topography](https://discovery.ucl.ac.uk/id/eprint/1443475/);
[COLMAP FAQ: pose priors](https://codegraph.jelmer.uk/colmap/4.1.1-1/doc/faq.rst);
[LightGlue / hloc](https://awesome.ecosyste.ms/projects/github.com%2Fcvg%2Flightglue);
[IMC 2025 matching pipeline](https://github.com/yangyefd/IMC2025);
[ORBIT++: SfM with 360 video](https://arxiv.org/pdf/2608.22039);
[ASPRS Positional Accuracy Standards, Ed. 2](https://www.asprs.org/wp-content/uploads/2024/03/October2023_HLA-Positional_Accuracy_Standards.pdf);
[Khan & Shah, multiple scene planes, TPAMI](https://ieeexplore.ieee.org/document/4497204);
[Kalman ground-plane multi-camera fusion, BMVC 2009](https://www.bmva-archive.org.uk/bmvc/2009/Papers/Paper261/Paper261.pdf);
[Trajectory-based video synchronisation, ECCV 2010](https://faculty.runi.ac.il/moses/papers/ECCV-2010.pdf).
