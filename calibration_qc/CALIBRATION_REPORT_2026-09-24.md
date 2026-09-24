# Paddock camera calibration - report for audit (2026-09-24)

Six fixed cameras over an outdoor rat paddock were calibrated from one 800 x 600 mm ChArUco
plate placed at 59 designed stations, so that a pixel in any camera can be turned into a paddock
(x, y) and the six cameras agree with each other and with the physical lattice. This document
states what was measured, what was assumed, what was computed, how it was checked, and what
remains unexplained. Everything quoted here is reproducible from the repository
`Field_2026_Social_Recording/calibration_qc` (commit `d8539c7`; addendum at the end supersedes sections 4.1-4.2, 5.5 and 6.1) and the session data on the field
PC (`E:\calibration`).

---

## 1. Setup

**Paddock.** 480 x 240 in (12.2 x 6.1 m) fenced enclosure with corrugated walls and rounded
ends, grass floor. Frame: origin at pole A0, x along the long axis (0-480 in), y across (0-240 in),
z up. Units in the reports are inches for positions on the ground and millimetres for errors; all
code works in millimetres internally.

**Lattice.** Seven "T" cords laid across the paddock at x = 24, 96, 168, 240, 312, 384, 456 in
(each running the full width), with disc cones at y = 12, 66, 120, 174, 228 in along each
(stations T11..T75, 35 in all). A second set of 24 cones ("V"/"F" stations) at x = 60, 132, 204,
276, 348, 420 in and y = 39, 93, 147, 201 in had NO cord; their y positions were measured along
the ground. There were never cords along the length of the paddock. The cords were laid by tape
by the operator; their accuracy was not independently measured.

**Board.** One aluminium-composite plate 800 x 600 x 6 mm carrying a 12 x 9 ChArUco pattern,
60 mm squares, 45 mm markers (DICT_5X5_100), pattern area 720 x 540 mm inside a 40 / 30 mm white
margin. 88 inner corners. Placed flat on the grass with one plate corner touching a station cone;
which corner varied with obstacles and is read off the fit, not assumed.

**Cameras** (all recorded through the same NVR, PC-clock synchronised):

| camera | model | frame | role |
|---|---|---|---|
| CH01, CH02 | Reolink Duo 3 PoE (two lenses stitched to one 180 deg canvas) | stored 2160 x 7680, used upright as 7680 x 2160 | mid-paddock, back to back, looking toward the two long walls |
| CH03, CH04 | Reolink RLC-1212A | 4512 x 2512 | near the two ends, looking along the paddock toward the opposite end |
| CH05, CH06 | Reolink RLC-520A | 2560 x 1920 | near-nadir over the two halves |

**Sessions.** 2026-09-18 13:54-15:49 (53 stations; a hand-held "sweep" of the board in front of
CH03 15:32-15:41 and CH04 15:41-15:45 for lens calibration; empty-paddock frames at 15:47:30) and
2026-09-19 12:23-12:42 (the T61-T65 column that had not been done). The operator's placement
timeline (which station, which clock window) is the only source of station identity.

**Tape measurements by the operator (2026-09-24), camera positions and lens heights:**
CH01 (236, 92) in, 7'9" (2.362 m); CH02 (249, 160) in, 7'8" (2.337 m); CH03 (112, 128) in,
7'4" (2.235 m); CH04 (369, 123) in, 7'6" (2.286 m). None of these were used in the fit.

---

## 2. Data actually used

| item | count | source |
|---|---|---|
| board placements (camera x station x window) with decoded corners | 135 assembled, 24 rejected by the planarity gate, 19 held out as operator outline clicks (coverage only) | `fit_data.py` from the cached corner detections |
| corner observations in the bundle | 7,654 over 64 physical placements, 6 cameras | |
| hand-held sweep views for the lens models | CH03 240 (11 rejected), CH04 125 (5), CH05 13, CH06 29 | operator-reviewed frames only (2026-09-23) |
| cone labels | 108 (CH01 39, CH02 38, CH03 9, CH04 9, CH05 7, CH06 6) | operator, `cone_gui.py` |
| cord and wall-foot points | ~250 (7 cords in the panos, 1-2 in the others; wall foot per side) | operator, `line_gui.py` |

**Operator review gates.** Every board detection used for geometry in CH03/CH04 was shown to the
operator with the machine's outline (accept / re-click four corners / not visible / partly
visible); the hand-held sweeps were reviewed frame by frame at 2 s (400 of 426 frames reviewed;
the 26 unreviewed stay out). "Not present" is only ever the operator's statement; a detector's
silence never is (`/detect-then-decode`, `DETECTION_POSTMORTEM_2026-09-19.md`).

**Corrections made to operator labels by projection, each recorded in the file with a note so the
operator can veto:** CH04 cones V64<->F61 and V62<->F63 (mirrored; each landed exactly on the
other's station, 1450-3640 px off); CH02 cone "F54" -> NONE (F54 is behind CH02, the cone sits on
the already-labelled V53); CH02 line "WALL_Y240" -> WALL_X480 and CH03 "WALL_X480" -> WALL_Y240
(the y = 240 side / x = 480 end are behind those cameras; the points land at x ~ 480 / y ~ 240
respectively). One window of the 2026-09-19 timeline ("T61" 12:41:05-12:42:24, added by the
analyst from frame review) was vetoed by the operator ("nothing there, I just set the plate down")
and carries the label NONE.

---

## 3. Method

1. **Corners.** ChArUco detection per keyframe; where the markers do not decode (far, small board
   in the panos) the plate is located first and the chessboard corners are decoded in a rectified
   crop with the 180 deg ambiguity resolved from square-colour parity. Frames of one window are
   merged by the per-corner median over the frames that agree on the corners they SHARE (4 px); a
   window whose frames never agree (plate in motion) is dropped. Corners under the burnt-in OSD
   text (timestamp, model name) are dropped. A placement whose corners cannot be a homography of
   the design grid to 4 px has wrong ids and is rejected.
2. **Lens models.** The pinholes (f, cx, cy, k1, k2; `cv2.calibrateCamera`, aspect fixed, no
   tangential, k3 = 0) come ONLY from the hand-held sweep views: placements on the ground are
   coplanar and cannot determine a focal length. The Duo 3 canvas was tested as a free
   equirectangular model on the free-pose views and returned fu = fv = W/pi = 2444.6 px/rad,
   centre (3839.5, 1079.5), i.e. the nominal 180 deg canvas; it is used as such with nothing to
   fit. The pinhole inverse (pixel -> ray) is an exact Newton solve of the forward model.
3. **Poses.** Per camera, a 6-DOF pose per placement (stage 2), then the common plane of its
   placements (stage 3: the camera height is the distance to that plane), then the paddock frame
   from the panos' cone labels (stage 4), then a bundle adjustment (stage 5) over 6 camera poses
   and 64 plate poses against every corner, every cone label (at the cone-top height, 50 mm, weight
   60 px) and the design station of the plate corner nearest its cone (weight 100 mm), with a
   robust (soft-L1) loss and the lens models frozen. A second pass drops views no camera geometry
   can explain (> max(20 px, 6 x camera median)); the dropped views are listed in the fit file.
4. **Plate height pinned.** Each plate lies on z = 6 mm (1 mm prior) with a 2 deg tilt prior.
   With the earlier 40 mm height prior the bundle slid far plates 0.2-0.5 m down their rays
   instead of moving the cameras, and the cameras disagreed by 0.3-0.5 m at the ends (see 5.1).
5. **Partial plates.** A plate cut by the frame edge or with < 30 corners carries half weight.
6. **Ground warp (frame correction).** After the bundle, each camera receives a 2-D polynomial
   warp from the bundle's frame to the physical lattice, fitted to that camera's own cones (points
   at stations), cords (straight lines at known x) and the straight middles of the wall foot
   (x = 0 / 480, y = 0 / 240): degree 4 for the panos (~130 constraints), 1 for the others, with a
   ridge prior of 8 in per term. Boards are not used in this step (section 5.3).

Two things that were tried and rejected, with the evidence: (a) per-lens pano models (own
rotation, own vertical scale, own angular scale, two rectilinear halves) tested against the
pinholes' own board geometry - none explained the shared boards with physical parameters; (b)
tightening the cone weight to 20 px - no effect on the fit (a few hundred corners outweigh nine
cones).

---

## 4. Results

### 4.1 Camera poses (bundle frame, before the ground warp)

| camera | x (in) | y (in) | height (m) | looks toward (deg from +x) | depression (deg) | boards | corner residual median / rms (px) |
|---|---|---|---|---|---|---|---|
| CH01 | 240.4 | 90.6 | 2.551 | 104.7 | 53.4 | 33 | 3.21 / 5.30 |
| CH02 | 245.6 | 152.8 | 2.635 | -77.8 | 53.8 | 26 | 3.07 / 8.58 |
| CH03 | 121.8 | 123.7 | 2.406 | -176.2 | 48.8 | 13 | 5.75 / 14.97 |
| CH04 | 358.7 | 131.1 | 2.738 | -8.4 | 47.8 | 14 | 8.84 / 19.19 |
| CH05 | 144.5 | 122.4 | 2.371 | near-nadir | 83.6 | 8 | 6.96 / 13.38 |
| CH06 | 336.6 | 131.6 | 2.340 | near-nadir | 83.6 | 10 | 9.52 / 16.75 |

Each camera's own placements alone (stage 2, free poses) fit at 0.3-2.4 px median; the joint
solution strains the ordinary lenses to 6-10 px median. That strain is the residual
inconsistency between the panos' ray model and the pinholes' geometry discussed in section 6.

### 4.2 Lens models

| camera | model | parameters | sweep rms |
|---|---|---|---|
| CH01, CH02 | equirect 7680 x 2160 | fu = fv = 2444.6 px/rad, centre (3839.5, 1079.5) - nominal | - |
| CH03 | pinhole 4512 x 2512 | f 2948.6, c (2177.2, 1273.6), k1 -0.3928, k2 +0.1109, HFOV 74.8 deg | 0.78 px (240 views) |
| CH04 | pinhole 4512 x 2512 | f 3129.9, c (2319.0, 1173.8), k1 -0.3726, k2 +0.0913, HFOV 71.6 deg | 1.44 px (125 views) |
| CH05 | pinhole 2560 x 1920 | f 2011.1, c (1207.3, 868.4), k1 -0.3593, k2 +0.0938 | 0.68 px (13 views) |
| CH06 | pinhole 2560 x 1920 | f 1995.5, c (1270.8, 888.4), k1 -0.3374, k2 +0.0834 | 0.52 px (29 views) |

### 4.3 Ground warp (`frame_correction.json`)

| camera | constraints | degree | residual before -> after (in rms) |
|---|---|---|---|
| CH01 | 39 cones, 75 cord/end-wall, 13 side-wall points | 4 | 9.6 -> 3.2 |
| CH02 | 38, 64, 7 | 4 | 8.5 -> 2.6 |
| CH03 | 9, 16, 0 | 1 | 11.1 -> 1.8 |
| CH04 | 9, 14, 0 | 1 | 8.2 -> 2.2 |
| CH05 | 7, 11, 0 | 1 | 1.6 -> 1.0 |
| CH06 | 6, 10, 0 | 1 | 2.4 -> 2.3 |

---

## 5. Validation

### 5.1 Cross-camera agreement on the boards (the primary figure of merit)

Every ChArUco corner has an id, so a corner decoded by two cameras is one physical spot; each
camera maps its own pixel of it to the ground (z = 6 mm) and the distance between the answers is
measured, with nothing modelled in between. 2,482 corners seen by 2+ cameras, fit-rejected views
excluded. The boards are NOT used by the ground warp, so this is an independent check of it.

| configuration | median | p90 | max |
|---|---|---|---|
| bundle with 40 mm plate-height prior (first fit, 2026-09-22) | 116 mm | 352 mm | 470 mm |
| plates pinned to the ground | 87 mm | 179 mm | 279 mm |
| + all cameras' cones, x-only frame correction | 84 mm | 179 mm | 275 mm |
| + per-camera ground warp, panos degree 1-2 (rejected) | 118-126 mm | 206-248 mm | 336-386 mm |
| **+ per-camera ground warp, panos degree 4, ridge 8 (current)** | **64 mm** | **147 mm** | **302 mm** |

Per pair (current): CH01-CH02 63 mm, CH01-CH03 45, CH02-CH03 54, CH02-CH04 71, CH01-CH04 100,
CH01-CH05 69, CH02-CH05 67, CH01-CH06 46, CH02-CH06 57 (medians). Worst stations: T75 237 mm and
T65 220 mm (the +x end, top-right corner of CH01's canvas); the middle band is 20-70 mm.

### 5.2 Cords and wall foot

Pushed onto the ground with the current mapping, every cord is straight (0.1-2.3 in rms
perpendicular deviation), within 5 in of its design x and tilted < 3 deg in every camera. Before
the per-camera warp the same cords were straight but tilted differently per camera (X456: 0 deg in
CH02, 6 deg in CH04, 11 deg in CH01), each camera agreeing with its own cones - the evidence that
the cameras' ground mappings differ by a smooth camera-specific warp rather than by wrong labels.
The wall foot lands at x = -5..0 (three cameras) and 478..480 (three), y = 0.3 and 240.2 on the
straight middles; two cameras' traces of the same wall segment agree to 1-4 in (median).

### 5.3 Cones

Median distance of a labelled cone from its design station, through the current mapping: 2.8 in
(p90 6.7 in), over 108 labels in six cameras.

### 5.4 The wall as an independent check, before any ground warp

The bundle's x = 0 line drawn on the CH03 frame sat on the end wall about 15 in above its foot,
while the cones sat 24 in from the foot as designed (`frames/CH03_walltest.jpg`): the bundle's
frame was compressed along x at that end by ~0.4 m (and ~0.15 m at the +x end). The warp removes
this; the wall was not used to fit it beyond its straight middle.

### 5.5 Tape measurements versus the fit (not used anywhere in the fit)

| camera | tape (x, y) in / height m | fit, warp applied (x, y) in | delta (in) | fit height m | delta height |
|---|---|---|---|---|---|
| CH01 | (236, 92) / 2.362 | (238.1, 92.2) | (+2, +0) | 2.551 | +0.19 m (+8 %) |
| CH02 | (249, 160) / 2.337 | (248.0, 151.2) | (-1, -9) | 2.635 | +0.30 m (+13 %) |
| CH03 | (112, 128) / 2.235 | (117.2, 125.1) | (+5, -3) | 2.406 | +0.17 m (+8 %) |
| CH04 | (369, 123) / 2.286 | (366.3, 133.3) | (-3, +10) | 2.738 | +0.45 m (+20 %) |

Positions agree to 1-10 in (the CH03-CH04 separation: tape 257 in, bundle 237 in, warped 249 in).
**Heights do not: the fit is 8-20 % higher than the tape for all four.** See 6.1.

---

## 6. Open items and known limitations

### 6.1 Fitted heights exceed the measured ones by 0.17-0.45 m (unexplained)

Each camera's own placements alone put it at 2.29-2.67 m (stage 3), the bundle at 2.34-2.74 m,
the tape at 2.24-2.36 m. For a single camera the height is (range to a plate from its apparent
size) x sin(depression), so a uniform overestimate would mean the plates look smaller than the
model expects (a smaller physical square than the 60 mm assumed would inflate every range and
height by the same factor - but it would also inflate the camera separations, and those come out
SMALLER than the tape, not larger). A vertical angular scale of the panos different from the
nominal would move their heights but not the pinholes'. Neither explanation fits all four cameras.
Possibilities to check: how the heights were measured (lens centre vs bracket vs pole top, and
from which ground - the pole base may sit higher than the paddock's mean ground plane), and the
printed square size of the actual plate (a caliper on the pattern would settle the scale
question). Until this is resolved, the ground mapping is unaffected (it is tied to the lattice by
the warp), but anything that depends on the absolute height - the parallax of an object above the
ground, the 3-D position of a raised point - carries this uncertainty.

### 6.2 The panos' ray model at long range / canvas corners

The Duo 3 canvas is modelled as an exact 180 deg equirectangular projection, which the near-field
free-pose views support. At the ends of the paddock (upper corners of the canvas, 5-6.5 m) the
panos place things a few percent closer than the ordinary lenses do, and no smooth per-lens model
tried removes it. The per-camera ground warp absorbs the effect on the ground; it is empirical,
valid for points on (or a few centimetres above) the ground, and re-derived whenever the fit is
re-run. The residual CH01-CH04 disagreement (100 mm median, 245 mm p90) lives there.

### 6.3 Other

* Cord and cone positions are the design values; the operator laid them by tape and their true
  accuracy is unknown. The frame is the lattice by definition.
* Partial plates (frame edge, few corners) and plates under the OSD text or a cable were the
  largest single-board outliers before the guards were added; six views are still rejected by
  the second pass (listed in `dropped_views` in the fit file).
* The ground warp's inverse is numerical (Newton); round trip paddock -> pixel -> paddock is exact
  to 1e-10 mm.
* A pixel is a ray: every pixel -> paddock conversion assumes a height. At the panos' 53 deg
  depression the answer slides 0.7 mm per mm of height error (a 60 mm-high back read as ground is
  4-5 cm off); at the nadir cameras 0.07 mm/mm.

---

## 7. Using the calibration

```python
import sys; sys.path.insert(0, r"...\calibration_qc")
from paddock_map import load
cams = load()                                       # E:\calibration\qc\camera_fit.npz + frame_correction.json
x_in, y_in = cams["CH01"].to_paddock((3000, 1500), z_mm=0, units="in")     # upright pixel -> paddock
u, v      = cams["CH01"].to_paddock_inv((240, 120), z_mm=0, units="in")   # paddock -> upright pixel
cams["CH03"].homography(z_mm=0)      # 3x3 for the ordinary lenses only, undistorted pixels, bundle frame
load(correct=False)                  # the raw bundle frame, no ground warp
```

Pixels are UPRIGHT (for the panos: the stored 2160 x 7680 video rotated 90 deg CCW);
`space="stored"` takes raw video pixels. Lengths in the fit file are millimetres.

---

## 8. Reproduction

```
python fit_cameras.py --out E:\calibration\qc          # stages 1-5 -> camera_fit.npz, CALIBRATION_FIT.txt
python frame_correction.py                              # -> frame_correction.json
python paddock_agreement.py --plot                      # -> PADDOCK_AGREEMENT.txt, paddock_agreement.png
python line_check.py --plot                             # -> LINE_CHECK.txt, line_check.png
```
Environment: `C:\Users\Cornell\miniforge3\envs\cv` (OpenCV 5.0, numpy 2.4, scipy 1.17).
Inputs on the field PC: `E:\calibration\session_2026-09-18_13-54-34`, `..._2026-09-19_12-23-53`
(video), `E:\calibration\qc` (cached corners, labels, fit). Copies of every operator label file,
the labelled-frame tables and all reports are in the repository under `calibration_qc/`
(`session_2026-09-1[89]_*.json`, `*_labelled_frames.csv`, `CALIBRATION_FIT.txt`,
`PADDOCK_AGREEMENT.txt`, `LINE_CHECK.txt`, `frame_correction.json`). The narrative of every
decision and dead end is in `calibration_qc/README.md`; the detection rules in
`.claude/skills/detect-then-decode/SKILL.md`.

---

## 9. Downstream validation for the place-field analysis (added 2026-09-24)

The auditor's brief asked not for landmark millimetres but for what the analysis would see:
`downstream_validation.py` builds an ensemble of 27 legitimate calibrations (the default warp,
degree/ridge neighbours, the warp without cords, without wall foot, and 20 bootstrap resamples of
the constraint points per camera), pushes 120,000 positions through each (synthetic occupancy:
50 % uniform, 30 % wall-following, 20 % shelter-centred - real tracks plug in with `--positions`),
and reports, with 10 cm bins and identical smoothing everywhere (`DOWNSTREAM_VALIDATION.txt`,
`downstream_validation.png`):

| metric | result |
|---|---|
| 1. handoff continuity (boards, never used by the warp) | 63 mm median, 144 mm p90, 199 mm p95 between cameras; per pair 45-100 mm median; worst CH01-CH04 (100 / 245 mm), i.e. the +x end; centre 62, corners 74 mm. Ensemble seam jump 42 / 114 / 156 mm. |
| 2. bin flip rate (10 cm) | 37 % of samples change bin under another legitimate calibration (centre 32 %, corners 48 %); only 2.6 % move by more than one bin; the ensemble displacement is 27 mm median, 81 mm p90 (corners 44 mm). These are boundary flips of a few centimetres, not relocations. |
| 3. occupancy robustness | Pearson r 0.988 median, 0.950 minimum; Spearman 0.957 / 0.893; normalised abs difference 0.065 / 0.117 max; JSD 0.002 / 0.0075 bits max; per-bin CV 5 % centre, 12 % corners. |
| 4. place-field robustness (300 simulated cells, sigma 10-25 cm) | centroid shift 25 mm median, 75 mm p90 (max 480 mm); peak bin unchanged for 64 % of cell x calibration, one bin for 32 %; rate-map correlation 0.994 median (p10 0.963); area change 4 % median; classification (SI > 0.5) unchanged for every cell in every member. |
| 5. error vs position | Ensemble displacement is centred (mean vector < 10 mm everywhere): no region is pushed one way. On the boards, the per-camera bias relative to the other cameras is < 25 mm in the centre; the largest is CH04 vs CH01 at the +x short-wall end / corner (+46, -48 mm and +28, -58 mm) - a local seam bias, not a whole-region one. |
| 6. distance to feature | change of the distance to the nearest wall 11 mm median / 47 mm p90; to either shelter 13-15 / ~50 mm. |

Reading, in the brief's priority order: place-field peaks and centroids move by a quarter of a
bin and no cell changes class (primary criterion met); occupancy maps correlate at r > 0.95 under
every alternative (met); camera handoff is 6 cm median with the 10-15 cm tail confined to the +x
end (CH01-CH04), the only place a further calibration effort would still pay; raw landmark error
is no longer the limiting quantity. Metrics 1 (trajectory-extrapolation form), 3 and 4 should be
re-run on real tracks and real cells when they exist; the script takes them as input.

---

## Addendum (2026-09-24, evening): the taped heights resolve the height discrepancy

Section 6.1 above is resolved. The operator confirmed the tape values are grass-to-lens-centre
(and would read high, not low, if anything) and measured the plate: 23.5 in across, squares
exactly 60 mm - the plate scale is right. With the heights held HARD in a per-camera plane fit
(camera z fixed by parametrisation, plates on the ground), the plates' apparent size fixes the
lens scale, and two things came out:

1. **The hand-held sweeps do not determine a pinhole's focal length.** CH04's sweep is fitted at
   1.95-2.00 px rms by any f from 2956 to 3173; CH03's at 1.29-1.37 px from 2800 to 3130 (one
   standing spot: distance and f trade off). The sweep's CH04 value (3130) was arbitrary. With its
   height fixed, CH04's plates ask for f = 2964; the ground cones, cords and wall at its taped
   height ask for 2956; CH03, the same camera model, has 2949. **CH04 f := 2960.**
2. **The Duo 3 canvas is not the nominal 180 x 50.6 deg equirect.** With the heights fixed, CH01's
   plates ask for fu = 2333, fv = 2711 px/rad and CH02's for 2318 / 2616 (nominal 2444.6 for both):
   about 190 deg across and 47 deg high. **Panos fu := 2325, fv := 2660.**

These four numbers are the only place the tape enters (`fit_intrinsics.py`, `FIT_NOMINAL_LENS=1`
restores the old values). Re-running sections 3-5 with them (`CALIBRATION_FIT.txt`,
`PADDOCK_AGREEMENT.txt`, `LINE_CHECK.txt`, `frame_correction.json` in the repository are now
these):

| camera | tape (x, y) in / h m | bundle, no warp (x, y) / h | delta h | corner residual median (px) |
|---|---|---|---|---|
| CH01 | (236, 92) / 2.362 | (244.0, 85.4) / 2.366 | +0.00 m | 2.46 |
| CH02 | (249, 160) / 2.337 | (248.9, 160.1) / 2.397 | +0.06 m | 2.96 |
| CH03 | (112, 128) / 2.235 | (112.5, 123.0) / 2.348 | +0.11 m | 3.87 |
| CH04 | (369, 123) / 2.286 | (374.3, 128.4) / 2.455 | +0.17 m | 6.11 |
| CH05 | - | (139.1, 126.4) / 2.292 | - | 3.35 |
| CH06 | - | (344.1, 126.9) / 2.318 | - | 6.13 |

The bundle's positions now match the tape to 2-8 in with no correction (CH03-CH04 separation
262 in vs 257 taped); the plate corners sit 157 mm (median) from their cones (was 206); the
ordinary lenses' residuals fell from 5.8-9.5 px to 3.4-6.1 px. Cross-camera agreement on the
boards, with the ground warp re-fitted: **median 70 mm, p90 114 mm, max 243 mm** (was 64 / 147 /
302); cones 2.8 in median from their stations; wall foot at x = 1..12 (CH03) and 473..481 (CH04),
y = 0.2 / 240.2. Sections 4.1-4.2 and 5.5 above describe the superseded fit; the tables in this
addendum are current. Remaining: CH04 +17 cm and CH03 +11 cm against the tape, and the panos'
two-parameter scale still needs the ground warp for the canvas corners (section 6.2 stands).
