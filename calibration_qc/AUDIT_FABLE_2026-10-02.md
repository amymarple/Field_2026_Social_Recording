# Independent audit of the 2026-10-01 calibration release (ground correction refit)

Auditor: Claude (Fable 5.1), 2026-10-02. Read-only: nothing in either repository or data root was modified.
Audited tree: `G:\Field_2026_Social_Recording` at `9e5486a` (two untracked files, `calibration_qc/ball_detect.py` and
`camera_drift.py`, not audited). Release artefacts: `camera_fit.npz` sha `6e4b54e9...`, `frame_correction.json` sha
`a9601ee2...`. Scripts I wrote and their outputs are in `C:\Users\Cornell\AppData\Local\Temp\claude\fable_audit\`
(`resid_by_session.py`, `frames_mode.py`, `mode_timeline.py`, `osd_rollover.py`, the OSD crops and small frame
thumbnails). All checks read closed segments or cached frames only.

## Executive summary

1. The release is a sound step and its three checks agree (boards 71 -> 52 mm, held-out cones 78 -> 61, held-out
   balls 117 -> 88); quote them, with the sample-size caveats of section 4 (per-pair board numbers rest on 1-7
   boards; CH02-CH03 is one board).
2. Error budget of the remaining ~52 mm on boards: (i) local pano ray error at the canvas position, 15-25 mm in the
   middle, 35-60 at the ends - direct evidence is per-board pano residuals of 10-20 px in the bundle where corners
   are 1 px; (ii) the 09-18 lattice used as hard truth by six INDEPENDENT warps, 25-35 mm for pano-small pairs
   (the refit itself estimates the cones 87 mm median off design); (iii) floor height, 0-50 mm, unmeasured. Balls
   add marks, clock and ball height (section 1). The CH04 end is NOT mainly a clock problem: the boards there
   disagree by 78 mm with no clock involved, and the burnt-in OSD clocks put CH04 within 0.1 s of CH03, not 0.8 s.
3. Highest-leverage desk action (1 day): let the flexible layer learn from the precise data. Treat the 09-18
   lattice cones as latent points with the 4 in prior (as the supplement cones are) and fit a per-pano canvas-space
   residual correction on 4/5 of the boards, checked on the held-out 1/5. Expected: boards 52 -> 35-40 mm,
   pano-nadir 40 -> ~25 mm. This is also the experiment that separates terms (i) and (ii).
4. Highest-leverage field action (30-60 min, irreversible): a floor-height map - every station and still-ball spot
   against one level reference (water level, line laser or rotating laser), plus the wall-top heights. The panos
   turn each cm of floor error into 2.3-2.5 cm at the far end and nothing in the data constrains it today.
5. Second field action (3 min, irreversible): with everything static, switch all cameras IR <-> colour twice during
   the survey. The IR-cut shift is 10-18 px in CH03/CH04 (2-5 cm at night) and no chain applies it; its
   repeatability is unknown. Keep the still ball (26 spots) and the +y pass; both are cheap and right.
6. Epoch chain: the supplement chain (09-30 colour -> 09-18 colour -> paddock) is implemented correctly and is
   mode-consistent (verified: all four 09-18 cone/line label frames are colour, the drift templates are colour).
   The cohort chain is not yet correct: all four landmark_track references are IR frames (verified, chroma 0),
   so day frames need a colour reference and night frames need a per-camera IR -> colour transform. Both can be
   measured from the 09-18 session itself (each camera has both modes within one hour, static).
7. Clock: new evidence from the OSD seconds rollover (frame-level) - CH03 and CH04 roll ~0.35 s before CH02 and
   within 0.1 s of each other; CH01/CH05/CH06 within +-0.1 s of CH02. The ball fit's CH04 = +0.82 s vs CH03 = +0.06 s
   is not reproduced. Camera OSD phases are not proven sub-second synchronised, so the decisive test is a
   physical common event: ball kicks at native frame rate (1-2 h), or the 1 Hz sync LED if it is in view.
8. Pano model: the single-centre equirect is not refuted as a stitch problem - both panos read x = 480 "closer"
   and x = 0 "further" although those are opposite lens halves, so the asymmetry is in the world (floor) or in
   CH03/CH04, not in the halves. A non-parametric canvas correction is the remaining lever: realistic gain 1-2 cm
   middle, 3-4 cm ends. A height-aware model buys little for rats (z <= 10 cm); the pole bands fix the vertical
   scale, the wall top the far-end band.
9. Evidence quality: the held-out schemes are honest in design; the numbers have wide intervals (cones 61 +- ~15,
   balls 88 +- ~25 mm at the segment level) and the 09-24 fold CV is the only test independent of the bundle and
   is stale - rerun it with the new warp; weight selection on the evaluation data is harmless because all three
   weights lie within noise, which also means the ball term is unproven.
10. Downstream: fixed per-keypoint height (prefer ground-contact points; a 60 mm back read at z = 0 is a 5 cm bias
    on four cameras), inverse-variance blending with hysteresis in overlaps, simultaneous rat detections as
    per-day tie points for a per-camera translation/affine and clock, clock per hourly segment (OSD rollover or
    LED). Do not refit the lens on coplanar data, free plate heights, add random cones, or refine ball outlines.

## What I did

* Read `RELEASE_2026-10-01.md`, `README.md` from "Session 2026-09-30" to the end and the 09-23/09-24 sections,
  `CLAUDE.md`, the 09-24/09-26 audits and response, `refit_supplement.py`, `frame_correction.py`, `paddock_map.py`,
  `landmark_drift.py`, `fit_models.py`, `fit_intrinsics.py`, `fit_data.py`, `fit_cameras.py` (header, pano
  handling), `survey_sheet.py`, the analysis repo's `landmark_track.py` docstring and landmark label metadata,
  and every check output listed in the brief.
* Computed (short, read-only):
  (a) `resid_by_session.py`: reprojection residual of the release bundle per board and camera, split by session
      (uses `fit_data.all_placements()` and the stored board poses);
  (b) `frames_mode.py` / `mode_timeline.py`: IR-or-colour mode of CH01-CH04 every 4 min through 09-18, every 2 min
      through 09-19, at every board-placement window, at the four landmark_track reference times and the four
      landmark_drift template times;
  (c) `osd_rollover.py`: at nominal PC times 16:26:00 and 16:29:30 inside the ball sweep, ~3.2 s of each camera
      at native frame rate (19.6-20.8 fps), OSD band cropped, frames where the glyphs change = seconds rollover.
* Did not run `fit_cameras.py`, `refit_supplement.py`, `cv_folds_eval.py` or any GPU job.

## 1. Error budget

### 1.1 Boards (two cameras on one corner, z = 6 mm): median 52 mm, p90 108, worst pairs CH01-CH04 78 / CH02-CH04 83

Verdict on the release's own reading ("model ceiling ... camera models cannot represent the cameras better"):
**partly confirmed**. The ceiling is real but it has two parts, and the second is removable without new data.

| term | evidence | contribution (median, mm) |
|---|---|---|
| (i) pano ray model, local (what a degree-3 warp cannot absorb) | bundle residuals per board in the panos: typical 2-6 px, but CH01 T33 (-16, -1), T72 (-15, +10), V62 (-18, -10), V53 (+10, -6); CH02 T53 (-4, +23), T12 (-15, -1), T62 (-12, +3) px - with 88 corners at ~1 px per board (`resid_by_session.py`). Plumb lines bend 4-10 px (`session_2026-09-18_pole_check.txt`). Ground sensitivity: far end (slant 6.6 m) 6.8 mm per px of elevation, 2.8 mm per px of azimuth; mid-field (slant 3.5 m) 2.0 / 1.5 mm per px. | 15-25 middle, 35-60 at x < 60 and x > 420 |
| (ii) the 09-18 lattice as hard truth in six independent warps | warp rms on its own 09-18 labels 3.7 in (CH01), 2.8 (CH02), 1.4-2.1 (others) (`REFIT_SUPPLEMENT`); the refit estimates the 09-30 cones 87 mm median, p90 153, off design; CH05/CH06 warps rest on 6-8 cones each. Two cameras that see the SAME cones share the error (CH01-CH02: 27 mm); cameras seeing different cones do not (CH01-CH05 41, CH01-CH04 78). The nadir cameras, with 0.5-0.7 px lens fits, are strained to 10-27 px per board in the bundle (CH05 T24 (-26, +6), F21 (+13, +10); CH06 F41 (+13, +6), F54 (+13, -5)) = 11-31 mm on the ground: that is the plate-level pano-nadir disagreement; the rest of the 41-45 mm board figure for those pairs (sqrt(41^2 - 25^2) ~ 32 mm) is the two independent warps. | 25-35 for pano-small pairs, ~10 pano-pano |
| (iii) floor height (the fit's one plane vs the real ground) | unmeasured. 24/64 plates sit at the +-6 deg tilt bound (`fit_manifest.json`); the systematic offsets are "far end closer to the panos" in BOTH panos (CH01-CH04 dx -74, CH02-CH04 dx -71 mm; wall foot x = 480 read at 479.1 / 477.5 in by CH01 / CH02) while x = 0 reads "further" (-3.4 / -1.4 in). x = 480 is CH01's right lens and CH02's left lens, so this is not a lens-half effect; a floor 2-3 cm lower at the +x end than the plane through the plates reproduces the sign and about 60 % of the size (pano 2.4 mm/mm vs CH04 0.94 mm/mm, both looking from -x). | 0-50; unknown until the floor is measured |
| epoch inside the bundle (09-18 vs 09-19 one pose; IR frames) | **checked, small**: the 09-19 boards show no per-camera pixel offset except CH04's three PARTIAL frame-edge boards T61/T62/T65 (-25 / -41 / -86 px; T63/T64 are within 6 px) - lens-edge, not motion. CH02 captured 15 of its 23 boards in IR mode (15:08-15:24; the camera hunted between modes six times in 20 min) - the pano IR shift is < 2.5 px, so <= 1 cm. CH01/CH03/CH04 boards all colour. | < 10 |
| corner noise | ~1 px | < 5 |
| clock | none | 0 |

Quadrature: sqrt(20^2 + 30^2 + 25^2 + 10^2) ~ 45 mm in the middle, ~70 at the ends - consistent with 52 / 108.

### 1.2 Balls in the fit 75 mm (held-out blocks 88), on top of the above

| term | evidence | mm |
|---|---|---|
| mark centre | machine vs operator 31 mm on the panos (partial masks), 5-16 elsewhere; operator repeatability not measured | 20-30 |
| clock residual after the fitted offsets | 0.1 s x 0.18-0.42 m/s; the linearisation B_k + tau v_k ignores acceleration, and the ball was kicked | 20-40 |
| ball-centre height | 105 mm assumed; cameras agree best 80-105; +-15 mm x 0.9-2.4 mm/mm | 15-35 |
| 09-30 -> 09-18 transform | CH01/CH02/CH03 two frames agree to 0.5-2 px; CH04 14 px / 0.5 deg | 5 (panos) to 30-50 (CH04) |

Quadrature with 52: ~75 mm. The budget closes; nothing large is missing from the ball figure.

### 1.3 The CH04 end (balls CH0x-CH04 200-290 mm after a fitted +0.82 s)

Verdict: **the release's "clock and y confounded" is confirmed, but the 20-29 cm is not mainly clock.**
Evidence: (1) boards at x > 400 disagree by 78-83 mm with no clock involved; (2) the OSD rollovers (section
1.5) put CH04 within 0.1 s of CH03, whose fitted offset is +0.06 s; (3) with |tau| = 0.8 s, one kick (a ~ 1-2 m/s2)
makes the second-order term 0.5 a tau^2 = 0.3-0.6 m, so CH04's ball residuals are unreliable at that offset
whatever the geometry; (4) the ball sat in grass at the far end - a 4 cm height error there is 10 cm in the panos.
So: ~8 cm geometry (terms i-iii), the rest an artefact of fitting a clock on two -y passes of a kicked ball.
The fix is the still ball (survey step 2), not more sweep marks.

### 1.4 The two decisive experiments on existing data

**E1 - swap the roles of boards and cones in the warp layer (desk, ~1 day; separates (i) from (ii)).**
(a) Refit `refit_supplement.py` with the 09-18 LATTICE cones as latent points under the same 4 in prior as the
supplement cones (cords and wall foot stay hard lines). Read the boards (`paddock_agreement.py`). If boards drop
52 -> <= 40 mm, term (ii) dominates: more cones will not help, but latent treatment and the already-labelled cones
do. (b) From the bundle's per-corner residuals of CH01/CH02 (`resid_by_session.py` has them per board), fit a
smooth canvas-space correction (du, dv)(u, v) per pano - thin-plate or 12 x 5 B-spline - on 4/5 of the boards,
score on the held-out 1/5 in px and re-score pano-nadir board agreement. If held-out residual halves (5 -> 2.5
px median), term (i) is coherent and the correction is worth building into `paddock_map` (apply to pixels before
`rays()`). Decision rule: whichever of (a)/(b) moves the boards most is the lever; both may. The CH05/CH06
strain (10-27 px per board) is the cleanest readout for (b) because those lenses are known to 0.7 px.

**E2 - floor vs ray model at the ends (desk 2-3 h, needs survey step 5 to interpret).** Map the operator's
WALLTOP_* labels (landmark files, IR frames: panos only until the IR -> colour shift is known) through the release
at z = 978 mm and compare their trace with the wall foot's (x, y). Along each wall, a systematic drift between top
and foot is the vertical ray-scale error profile; a shared drift is floor or pose. With the surveyed ground-to-top
heights (step 5) and ONE level reference the two separate; without a level reference they do not.

Clock (cheap, 1-2 h): native-frame-rate ball kicks visible in CH04 and CH01/CH02 (steps 243-260 of the sweep), kick
frame by position time series -> offset to +-1 frame. Or the sync LED (`led_sync.ps1`, 1 Hz, PC-clock logged) if
it is in CH04's and a pano's view on 09-30 - check one frame.

### 1.5 New measurement: OSD seconds rollover (not in the release)

At 16:26:00 and 16:29:30 nominal, first rollover after the nominal time (file pts, s): CH01 0.744 / 0.687,
CH02 0.830 / 0.687, CH03 0.276 / 0.306, CH04 0.449 / 0.348, CH05 0.879 / 0.873, CH06 0.897 / (unusable, people).
Relative to CH02 (positive = that camera's content runs ahead, the fit's tau sign): CH01 +0.09 / 0.00,
CH03 +0.55 or +0.36 / +0.38, CH04 +0.38 / +0.34, CH05 -0.05 / -0.19, CH06 -0.07 / -. Ball fit: CH01 -0.30,
CH03 +0.06, CH04 +0.82, CH05 +0.12, CH06 -0.15. Agreement +-0.35 s for five cameras; CH04 differs by 0.5-1.2 s
(mod 1). Two identical cameras on the same NVR with the same sync path (CH03, CH04) have OSD phases 0.1 s apart;
for the ball fit to be right their camera clocks would have to differ by 0.7 s in exactly the compensating
direction. I rate the +0.82 s as probably spurious, but the OSD is only a sub-second clock if the camera clocks
are synchronised to better than a frame, which is **unverified**.

## 2. Pano model

* **Single centre vs two lenses: refuted as the binding limit.** `fit_cameras.py --split` (one pose per half) did
  not reduce residuals (README 2026-09-23 evening; code comment at `fit_cameras.py:62`); per-lens rotation and
  vertical scale were tried likewise. The end asymmetry in 1.1 (iii) sits on opposite halves of the two panos and
  therefore is not a half effect. Lens-centre parallax (a few cm) is <= 2 cm anywhere and is absorbed by a per-half
  pose, which was tested.
* **What remains is local**: per-board offsets of 10-20 px at specific canvas positions (1.1), plumb-line curvature
  5-13 arcmin over 30-40 deg of elevation (mostly above the ground band - an upper bound for it). This is the
  vendor's stitch/distortion residual. The degree-3 ground warp, fitted on cones of 7-9 cm scatter, cannot learn
  3-5 cm features; the boards (1 px) can, which is E1(b).
* **Non-parametric canvas correction**: identifiable from the existing 35 + 28 pano boards over the canvas,
  validated by held-out boards. Realistic gain: 1-2 cm mid-field, 3-4 cm at the ends (it removes the coherent part
  of (i); T33's -16 px is not shared by its neighbours T34/F23/V24, so part of (i) is incoherent and stays).
* **Height-aware correction**: the rat lives at z = 0-10 cm; the error is 0.73-2.5 mm per mm of height ASSUMPTION,
  not of model. A 5 % error in the elevation scale changes a 60 mm height correction by 3 mm. Not worth a model
  for rats; worth it only for carried/climbing animals. The pole bands (1.2 / 2.0 m) fix the elevation scale near
  the horizon row; the wall top (0.98 m, far walls at -12 deg) is the above-ground constraint nearest the far-end
  ground band and is already labelled (WALLTOP_*).
* **Plumb lines alone cannot identify it**: they constrain roll/elevation per azimuth above the band; with the
  surveyed pole positions and bands they become 3-D control, which is what a true lens refit needs (section 5).
* Pole thickness: the fit's 144 mm median is a nominal 6 x 6 post (140 mm); "1 ft" is likely the base. Step 3
  (circumference) settles it in a minute and, if 14 cm, validates the fit's scale at the poles.

## 3. Epoch chain

**Supplement refit (09-30 -> 09-18 colour -> paddock): confirmed correct.** `refit_supplement.to_0918` inverts
`landmark_drift`'s convention (B = c + s R (A - c) + d) exactly; the drift templates (CH01 15:20, CH02 15:35,
CH03 15:30, CH04 15:47 on 09-18) are colour and the label frames (15:47:30; CH03 15:20:00) are colour
(`frames_mode.py`, `mode_timeline.py`); 09-30 16:35:10 and the sweep are colour (OSD crops). Weak points:
a 4-DoF similarity for a camera rotation is adequate at 7-46 px; CH04's two frames disagree by 14 px / 0.5 deg
with six rigid landmarks - fit CH04 on 5+ frames spread over 15:50-16:35 and take the median, and add landmarks;
if the transform varies within the session, CH04 sways and needs a per-minute transform for the sweep.

**Cohort footage: the present chain is not right yet.** Verified facts: all four landmark_track references
(CH01 13:57:30, CH02 15:22:30, CH03 15:45:00, CH04 14:32:30) are IR frames; cameras switched modes within 09-18
(CH01 IR until ~14:00; CH04 IR until ~14:37; CH02 IR 15:08-15:24 with six flips; CH03 IR from ~15:41); CH03 was
IR at 12:24:30 on 09-19. The IR-cut shift is 10-18 px in CH03/CH04 (README) = 2-5 cm on the ground. Correct chain:

    cohort pixel (time t, mode m)
      -> A_c,m(t): landmark_track affine against a reference of the SAME mode m
      -> reference pixel (mode m, 09-18)
      -> if m = IR: S_c (IR -> colour, one similarity per camera, 09-18)
      -> 09-18 colour pixel = the pixel space of the cone/line labels and the boards
      -> bundle + warp (paddock_map)

What must be measured, all from existing footage: S_c for CH01-CH04 (and CH05/CH06 if they go IR at night -
unverified) from 09-18 frames minutes apart in the two modes with the camera static (`landmark_drift.py` with an
IR frame as B already does this); its REPEATABILITY from the six CH02 flips on 09-18 and the two daily
transitions in cohort footage - if the IR-cut repositions to a few px each time, S_c is a constant; if not, night
frames must be tracked against an IR reference (as now) and day frames against a colour reference, with S_c
measured per night from the first hour after dusk. Add colour references = the 15:47:30 label frames themselves.
Nothing here needs field time, but the survey should include two static IR <-> colour toggles (section 5) so the
final epoch has the same measurement with the bands in view.

## 4. Evidence quality

* **Boards in the bundle, not in the warp**: honest for the WARP; not independent of the bundle, which minimised
  their joint reprojection (and holds the shared plate poses). The only check independent of the bundle is the
  placement fold CV (`CV_FOLDS.txt`: 76 / 137 mm, 26 placements) and it is for the 09-24 warp. Rerun
  `cv_folds_eval.py` with the refit warp (1-2 h compute): that is the number to quote for "a new ground point".
* **Effective samples.** Boards: 2075 corners but 31 stations x 9 pairs with 1-7 boards per pair; disagreement is
  a per-board offset (the "systematic offset" column and the per-board residual means), so the unit is the board
  pair, ~45 of them. Station-level median of the worst pair is 50 mm, so 52 / 108 is fair; "CH02-CH03 60 mm" is
  one board. Cones: 61 pairs from 58 cones (<= 3 cameras each) -> ~45 independent; median 95 % CI ~ +-15 mm:
  61 (46-76) vs 78 (63-93) - supported mainly by the independent boards (71 -> 52). Balls: 172 pairs in ~100
  steps, consecutive steps 0.36 m apart in the same pair -> ~15-20 independent segments; +-25 mm; the five block
  medians are the honest unit and are not printed - print them. The cone-vs-cone+ball difference (89 vs 88) is
  noise.
* **Weight selection**: harmless (0.3 / 0.5 / 1 give 90 / 88 / 89 held-out balls, 63 / 61 / 60 cones, 51 / 52 / 54
  boards - all within noise), which also means the balls' benefit is unproven; keep 0.5 or drop them, same result.
* **Within-pass correlation in the ball folds**: contiguous blocks are the right design; the clock offsets refitted
  on training balls each time is right. The remaining optimism: ball velocity V0 comes from the release warps and
  is shared across folds (small).
* **Downstream (DOWNSTREAM_VALIDATION 1(b)+)**: correctly declared invalid; its bin-flip 59 % is release-vs-old,
  not uncertainty. An ensemble from `refit_supplement.py` variants (sigma 3/4/6 in, cord weight, degree, ball
  weight, bootstrap of cones) is the right replacement; 1-2 h.

## 5. Before teardown (irreversible)

The checklist's own argument dominates: cohorts 1-2 footage can only be calibrated retrospectively from permanent
structures (`PRE_TEARDOWN_CAPTURE_CHECKLIST.md` C), so every structure measurement is worth its time whatever
sections 1-3 say about cohort 3. Within that:

| item | verdict | why / what it buys |
|---|---|---|
| Pole bands at ~120 / ~200 cm, nine seen poles | keep (1 h) | the only above-ground 3-D points for the panos' vertical scale and a future lens refit; useless without the pole positions below, so do both or neither |
| Pole-to-pole distances (17 first-rank pairs) | keep (1 h) | an absolute frame independent of the cones (grid is off 10-30 cm); required for the historical bridge |
| Pole circumference and lean | keep (10 min) | resolves 14 cm vs 1 ft; lean turns the plumb-line tilts into model residuals |
| Wall-top heights, 24 points | keep, with a level reference (see below) | far-end vertical band (WALLTOP labels exist); doubles as the floor profile along the perimeter if the top is referenced to one level |
| House base size, corner heights, corners to poles | keep (20 min) | eight 3-D corners under CH05/CH06 and in both panos; needed for the historical bridge |
| Camera lens heights and pole offsets | keep (15 min) | the fit sits 6 / 12 cm above the tape for CH03 / CH04 and the pano scales were pinned from the tape - a second measurement decides whether the tape or the model is wrong |
| 26 still-ball spots | keep (30-40 min), but hold 8-10 s per spot, not 4 (2 s sampling plus up to 1 s of unknown offset leaves no margin at 4 s) | the clock-free check of the far end and the x = 0 end; the only fix for 1.3 that does not depend on the clock; far-end spots first |
| +y push along T7 with 3 s stops | keep (3 min) | the stops make it clock-free; the direction breaks the confound |
| **MISSING: floor-height map** | add (30-60 min) | ground height at the 35 stations, the 26 ball spots and house corners against one level (clear-hose water level, line laser on a tripod, or rotating laser + staff). The panos convert each cm into 2.3-2.5 cm at the ends and the fit assumes one plane; 24/64 plates at the tilt bound and the end asymmetry both point here. Without it the term stays 0-5 cm forever |
| **MISSING: IR <-> colour toggles** | add (3 min, twice) | everyone out of view, all cameras to IR for 60 s, back, repeat at the end of the survey: measures S_c and its repeatability at the final epoch with the bands in view |
| **MISSING: ball at a second height** | add (5 min) | the ball on a box of measured height (20-30 cm) at 5 far-end spots and 3 near CH05/CH06: a direct test of the elevation scale at rat-plus heights, clock-free |
| **MISSING: a common clock event** | add (2 min) | if the sync LED is not in view, a single flash/clap visible to all six cameras at a written PC time (a phone torch swept past each lens is NOT common; use one event seen by all, e.g. a person's jump at the centre) - frame-level offsets for the survey session; also photograph the PC clock in a camera's view once to tie PC time to the OSD |
| Photos with tape | keep | cheap insurance |

Not worth field time: more sweep marks of a moving ball; more cones on the design lattice; anything that
repeats the board placements (the boards are already the best data and are under-used, section 1.4).

## 6. Downstream rules that reduce handoff jumps

1. **Height convention per keypoint, fixed and documented**: prefer ground-contact points (paws, nose when down,
   tail base ~ 30 mm) over the back; use z = 60 mm for a back centroid, 30 mm for the snout, never z = 0 for a body
   point (0.85-1.03 mm/mm on CH01-CH04: a 60 mm back read at the ground is a 5-6 cm bias, and it is a bias, not
   noise, so it moves place fields). Nadir cameras (0.09-0.10 mm/mm) are indifferent; use them as the arbiter.
2. **Blend, do not switch**, where two cameras see the animal: weighted mean with weights 1 / sigma_c(x, y)^2 from
   per-camera held-out error maps (nadir < CH03/CH04 < pano far field), plus hysteresis (switch the dominant camera
   only after 0.5 s and 10 cm of margin). Expected: handoff jumps of 5-8 cm become ramps over ~1 s, below the
   5-10 cm bin at ordinary speeds.
3. **Simultaneous two-camera detections as tie points**: yes, this is the ball sweep done by the animals with
   millions of samples. Per day and per camera, fit a translation (or affine) residual and a clock offset to
   the paired detections of ONE animal (identity certain), after the epoch transform and height convention; use
   them to monitor (and, if stable over days, to correct) the epoch chain. Do not refit the warp on them.
4. **Clock per hourly segment**: segment names are +-1 s (and cut at a keyframe); estimate each camera's offset per
   segment from the OSD rollover (frame-level, automatic: digit-change detection as in `osd_rollover.py`), the
   LED edges, or the rat tie points; carry a per-segment table, not one constant.
5. **Report a per-bin uncertainty map** (from the error maps and the ensemble of section 4) with every place-field
   figure; mask bins where sigma > bin size / 2 (today: CH01's far field, the +x end, the corners).

## Do not do

* Refit the lens models or free the pano scales on the ground data (coplanar; identifiability is the problem
  the taped heights solved).
* Free the plate heights again, or widen the tilt bound (tested: no gain; the plates absorb model error).
* Label more cones at design positions as hard targets; the lattice is 9 cm off and adding it adds bias.
* Refine ball outlines (`ball_refine.py`, tested and rejected) or mark more moving-ball frames in CH04.
* Add a CH04 clock from the 09-30 sweep alone, or trust +0.82 s.
* Spend survey time on all 44 pole pairs if the 17 first-rank ones are done; or on wall heights beyond 12 points
  unless a level reference is available.
* Re-open the 09-19 session as an epoch problem: checked, the offsets are partial frame-edge boards.

## Agreement and disagreement with the astra audit (`AUDIT_ASTRA_2026-10-02.md`)

**Agree (and the two audits reinforce each other):** the supplement chain is algebraically correct and
mode-consistent, the cohort chain is not yet usable without a per-camera IR -> colour bridge; the old lattice as
hard targets is a structural constraint and the latent-cone comparison is the right desk experiment (their B =
my E1(a)); per-pair board numbers rest on 1-5 placements and the honest unit is the station/placement (their
50 / 99 mm and 44-68 mm bootstrap interval match my station-level 50 mm and +-15 mm); the ball-weight choice is
harmless and the 88 vs 89 difference is noise; the pole check is mode-confounded for CH03/CH04 (IR labels into
colour rays; the panos' curvature stands at < 2.5 px); the floor datum, low-height targets, IR/colour capture and
the still ball are the field priorities; the 60 mm keypoint convention, hysteresis, per-segment clocks and all of
"Do not do". Three of their findings I had missed and accept: all 13 CH04 ball marks lie in block 5, so the
held-out CH04 figures (428 / 345 mm) are scored with tau_CH04 forced to the prior, not learned; the support hull
now includes single-camera ball marks and so bridges unsampled space; and `refit_supplement.py` loads the adjacent
(now promoted) warp as its baseline, so the historical comparison needs the 09-24 warp pinned. Their 8-10 s
still-ball hold and the velocity artefact of fast blending ((p1 - p2) dw/dt) are better than my 4 s / "ramp over
1 s"; adopt them. Their point that `landmark_track` does not persist the full per-frame affine and does not gate
on an unreliable tie is plausible and important; I did not read that code and cannot confirm it.

**Disagree, with reasons:**

1. *"The budget cannot be allocated; binding limit unknown."* It can be, further than they went, because the bundle
   carries per-board, per-camera residual VECTORS that neither audit's headline numbers use: 10-20 px on specific
   pano boards with 1 px corners, and 10-27 px of strain on the nadir cameras whose lenses are known to 0.7 px
   (section 1.1). Those are per-camera measurements of the ray term, not pooled medians, and they put it at
   15-25 mm mid-field and 35-60 at the ends. Together with the sign pattern (both panos read x = 480 closer on
   opposite lens halves) they also settle what astra leaves open: the two-lens-centre hypothesis is not the
   limit; a local canvas correction may be.
2. *Sequencing: "do not fit a ray field before modes, datum and CH04 timing are resolved."* The board-based canvas
   test (E1(b)) uses 09-18/19 colour boards inside the bundle: no epoch, no mode, no clock enters it. It can run
   first, in a day, with held-out boards as the gate. Their Experiment A (re-verify landmarks by hand, epoch
   first) is right for the cohort chain but is not the first experiment for the calibration's own accuracy: I
   checked the epoch term inside the boards (09-19 boards show no per-camera offset; CH02's 15 IR boards cost
   <= 1 cm) and it is small.
3. *The board-tilt "confound".* They read the fitted tilts (median 5.1 deg, corners up to 53 mm off z = 6) as a
   reason the 52 mm is not ray error. I read the same numbers the other way: plates on grass do not tilt 5 deg
   median and 24/64 sit at the bound - the tilt is the bundle absorbing ray and floor error, so it is a symptom
   of terms (i)/(iii), not an independent cause. Their proposed model-height re-score is still worth doing
   (7-20 mm at the far end) as a diagnostic, as they say.
4. *CH04's +0.82 s.* They treat it as a parameter of that recording; I rate it as probably spurious, on two pieces
   of evidence they did not use: the OSD seconds rollover puts CH04 within 0.1 s of CH03 (fitted +0.06 s), and
   with |tau| = 0.8 s the ignored acceleration term of a kicked ball is 0.3-0.6 m, so the ball cannot adjudicate
   CH04 at all. The decisive test is kicks at native frame rate or the LED, then the still ball.
5. *Mode-bridge capture.* They say measure it in the field if existing frames do not suffice. They do: every
   camera has both modes within one hour of 09-18 with the camera static (CH01 13:59 / 14:03, CH02 six flips
   15:06-15:25, CH03 15:39 / 15:43, CH04 14:35 / 14:39), so S_c and a first repeatability estimate are a desk job
   today; the field toggles buy the final-epoch value and repeatability, not the first measurement.

**What astra missed:** the per-board residual evidence above; that the cameras hunted between IR and colour inside
the board session (15 of CH02's 23 boards are IR frames); that all four landmark_track references are IR while
all label frames are colour (verified by frame chroma, not inferred); the OSD clock as an independent clock
source; the 09-19 epoch check; the lens-half sign argument; the kick-acceleration argument; the 6 x 6 post
reading of the 144 mm pole width; and the checklist's section C rationale that the structure survey is owed to
cohorts 1-2 whatever its value for cohort 3.

## Not verified / limits of this audit

* Camera OSD clocks' sub-second synchronisation (the 1.5 inference rests on it being either synchronised or equal
  for CH03/CH04); CH06's 16:29:30 band had people in it.
* Whether CH05/CH06 switch to IR at night, and the mode of the 16:35:10 label frames (operator says colour; the
  16:26 frames are).
* The cause of CH04's 14 px two-frame disagreement (sway vs fit) and of CH01 T33's 16 px board residual.
* The operator's own repeatability of ball marks; the floor profile; whether the sync LED is in any camera's view
  on 09-30.
* Nothing in the untracked `ball_detect.py` / `camera_drift.py`.
