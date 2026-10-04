# Trial bundle with the hand-held sweep boards (2026-10-02) - NOT a release

The release (`camera_fit.npz` 6e4b54e9 + `frame_correction.json` 2654a6a6, RELEASE_2026-10-02 revision b) is
untouched. Everything here is under `F:\calibration\qc\trial_sweep\` (see "Data root").

## Why

Projected from the sweep camera's own board pose (IPPE on its corners, release bundle) into the panos, the 2026-09-18
hand-held sweep boards land 25-57 px (median per pair) off the corners the panos decoded, systematically per pair
(`sweep_check.py`). The operator confirmed on the failure videos that the board is centred on its plate (the outline is
right) and that the offset is real. The release ties the cameras together only near the ground (plates, cones); the
sweep boards are the only above-ground two-camera data of the calibration.

## Data

`board_sweep20_instances.py` -> `instances.json` (frozen copy here; 268 instances, 391 pano views, board centre
0.21-0.54 m above the ground, p10-p90): one sweep-camera frame (>= 20 corners) plus every pano frame within half a frame
after the clock offsets (CH03 window: CH01 +0.52, CH02 +0.46 s; CH04 window: CH01 -0.35, CH02 -0.25 s), the board's
fastest corner slower than 0.3 m/s, at most one instance per 0.25 s. Measured corners only (ChArUco, rescued
rect-charuco / rect-chess); homography gate on the lens-free rays; fit_data's sigmas, doubled for partial views; a pano
view also carries the timing error (17 ms rms at the board's speed). CH03's sweep was in IR mode: shifted by the
measured IR -> colour step (+0.6, -5.6 px). The CH04 rescue was still running when the file was frozen (36 more
instances exist now; they are in no fit).

## Method

`fit_cameras.py` (same pipeline as the release, new opt-in hooks; with none of them set it reproduces the release:
`base\`, camera centres within 0.2 mm, warp coefficients within 0.006 in, every check identical):
- `FIT_SWEEP=<instances>`: each instance is a free 6-DOF board seen by the sweep camera and the pano(s); a view counts as
  at most 16 corners (thinned in farthest-point order, sigma unchanged).
- `FIT_INIT=<release npz>` + `FIT_MAX_NFEV=1000`: start from the release (its camera poses, plate poses and its
  second-pass drops) - from a cold start a sweep fit needs ~20 h; the warm start without the sweep (`w\W0`, 1000 and
  3000 more steps) stays exactly on the release, so every change below is the sweep's.
- Variants: **A** lens fixed (poses only); **B** + the panos' canvas scales fu, fv and k1 free (`FIT_FREE_PANO`);
  **C** + CH03/CH04 focal length free (`FIT_FREE_F`). A300 = A with 300 steps (A1000 gives the same to < 1 mm).
- Held out: each variant also fitted on the even / odd 10-s blocks of the sweeps only (`FIT_SWEEP_HOLDOUT`), and each
  instance scored with the fold that did not see it.
- Ground: for each bundle the release recipe re-run (frame_correction.py, then refit_supplement.py --soft-lattice 4
  --deg CH03..06=2 --drift session_2026-09-30_drift_final.json, now with `--fit`), then the release's checks on the same
  data snapshot (ball tracks copied to `track20_snapshot\`).

## Results (`w\<variant>\`, ground checks in `w\<variant>\warp\`)

| | sweep, in fit (px) | **sweep, held out (px)** | boards (mm) | held-out cones | ball 20 Hz | CH01-CH02 ball | CH04 end ball | ground map moved vs release (median per camera) |
|---|---|---|---|---|---|---|---|---|
| release | 46 / 71 | 46 / 71 | 37 / 86 | 62 / 124 | 61 / 121 | 85 | 49 | - |
| A (poses) | 15 / 38 | **19 / 44** | 38 / 83 | 59 / 118 | 61 / 123 | 83 | 49 | 3-7 mm (max 36) |
| B (+ pano scales) | 12 / 24 | **15 / 28** | 37 / 83 | 63 / 126 | 62 / 126 | 88 | 50 | 4-14 mm (max 88) |
| C (+ CH03/04 f) | 9 / 30 | **17 / 38** | 37 / 83 | 59 / 124 | 61 / 135 | 87 | 49 | 4-27 mm (max 192) |

Sweep = median / p90 of each pano view's mean offset, observed - predicted from the sweep camera's pose. Per pair,
held out (median px): A 19 / 17 / 24 / 17, B 12 / 15 / 15 / 18, C 22 / 22 / 13 / 17 (CH03->CH01, CH03->CH02,
CH04->CH01, CH04->CH02).

Camera heights against the operator's tape (CH01 2.362, CH02 2.337, CH03 2.235, CH04 2.286 m), height - tape:

| | CH01 | CH02 | CH03 | CH04 |
|---|---|---|---|---|
| release | -10 mm | +72 | +58 | +119 |
| A | -80 | +14 | +121 | +33 |
| B (fu 2386 / 2383, fv 2800 / 2706, k1 -0.045 / +0.022) | +67 | +120 | +159 | +66 |
| C (CH03 f 2747, CH04 f 2778) | +84 | +167 | +79 | -11 |

## Reading

- The sweep inconsistency is mostly a camera-pose matter: poses alone (A) take it from 46 to 19 px on boards the fit
  has not seen; the ground checks do not move (the ground warp absorbs the bundle change; the mapping moves 3-7 mm).
- Freeing the pano scales (B) is best on the held-out boards (15 px) but lifts every camera 7-16 cm above its taped
  height; freeing the pinhole focal lengths too (C) does not help held out and moves CH03's ground mapping by up to
  19 cm. Neither is supported by the tape.
- Not solved: the board's SHAPE. Observed / predicted apparent size stays the same in every variant (e.g. CH03->CH01
  vertical 0.81, CH04->CH02 horizontal 0.92-0.94; `w\SWEEP_CHECK_folds.txt`): the predicted outline is often a size
  too large in the review videos. Either the panos' canvas model near its ends/edges or the sweep camera's estimate of
  the board's tilt; the variants cannot tell.
- The ground checks are not better either: the sweep boards add no ground information.

## For the operator's review

`w\SWEEP_REVIEW_A.mp4`, `w\SWEEP_REVIEW_B.mp4` (and `_small` copies): every pano view of the 268 instances, 3 per second;
left the release's predicted plate outline (magenta), right the trial's (green) from the fold that did NOT see that
instance; yellow dots = the corners the pano decoded; the header gives both corner offsets. Look at whether the outline
sits on the plate - position and, separately, size and tilt.

## Data root

The operator's rule (2026-10-02): all calibration data and outputs on F:\calibration (`CALIB_ROOT`), nothing new on
G:\calibration; G:\calibration\qc was synced to F: at 18:32 (`F:\calibration\qc\sync_from_G_2026-10-02.log`). This
work's shell had been started before CALIB_ROOT was set and fell back to G:, so part of it was first written to
G:\calibration\qc\trial_sweep and \sweep20 and copied here afterwards (robocopy /XO, `copy_from_G.log` in both folders;
the G: copies are left until the operator decides). The trial fits read the plates and cones from F: (the 18:32 copy,
identical: W0 reproduces the release). Rescue files written to F: by detached runs that used a refinement with a known
flaw (an even-square slip; see board_sweep20_rescue.py) are renamed `sweep20\*_rescue_CONTAMINATED_refine_bug.json`.

## Reproduce

    set FIT_INIT=<root>\qc\camera_fit.npz & set FIT_MAX_NFEV=1000 & set FIT_SWEEP=<root>\qc\trial_sweep\instances.json
    [set FIT_FREE_PANO=CH01,CH02] [set FIT_FREE_F=CH03,CH04] [set FIT_SWEEP_HOLDOUT=odd|even]
    python fit_cameras.py --out <dir>
    python frame_correction.py --fit <dir>\camera_fit.npz
    python refit_supplement.py --session <09-30 session> --out <dir>\warp --fit <dir>\camera_fit.npz --rel <dir>\frame_correction.json ^
        --deg CH03=2,CH04=2,CH05=2,CH06=2 --soft-lattice 4 --drift session_2026-09-30_drift_final.json
    python sweep_check.py --instances <root>\qc\trial_sweep\instances.json --fit <dir>\camera_fit.npz
    python sweep_review_video.py --trial <A npz> --cv-odd <A_odd npz> --cv-even <A_even npz> --instances <...>

## Round 2 (same evening): the rescued frames added (`w2\`, `instances_v2.json`)

The rescue (board_sweep20_rescue.py with offset-corrected priors, locating by template / plate silhouette / wide
markers, tracking, and saddle refinement checked against the decoder on 240 decoded frames: median 0.5-0.6 px, p99
1.4-2.6 px) brought the panos' decoded + rescued sweep frames to CH03/CH01 155, CH03/CH02 65, CH04/CH01 695, CH04/CH02
1025 rescued. Instances rebuilt the same way (rect-refined corners at sigma 1.0 px): 393 instances, 559 pano views
(v1: 268 / 391); 155 instances are new. All numbers below on all 393 instances (`trial_summary` on instances_v2):

| | sweep in fit | **sweep held out** | boards | held-out cones | ball 20 Hz | CH01-CH02 ball | moved (median) |
|---|---|---|---|---|---|---|---|
| release | 38 / 69 | 38 / 69 | 37 / 86 | 62 / 124 | 61 / 121 | 85 | - |
| round 1 A | 15 / 39 | **19 / 42** | 38 / 83 | 59 / 118 | 61 / 123 | 83 | 3-7 mm |
| round 1 B | 13 / 33 | **16 / 30** | 37 / 83 | 63 / 126 | 62 / 126 | 88 | 4-14 mm |
| round 2 A | 14 / 38 | **19 / 43** | 38 / 85 | 59 / 119 | 61 / 123 | 83 | 3-7 mm |
| round 2 B | 12 / 29 | **16 / 31** | 38 / 84 | 63 / 126 | 62 / 126 | 87 | 4-16 mm |

Round-1 fits scored on the 155 instances none of them had seen: A 16 / 39, B 16 / 36 px (release on the same views:
CH04->CH02 37-45 -> A 6-20, CH04->CH01 17-22 -> A 12-15, but CH03->CH01 (24 rescued views) 34 -> A 33 / B 36: no
gain there). Round 2, which fits those views, changes little: the result is not data-limited; what is left (15-19 px
held out, and the boards' apparent size) is the model. Heights - tape, round 2: A CH01 -96, CH02 -15, CH03 +113,
CH04 +23 mm; B +62, +95, +139, +62 mm.
