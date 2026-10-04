# Handoff: the hand-held sweep boards as above-ground two-camera data (2026-10-02/04)

For the agent that owns the current release (2026-10-03, ray-space correction, `refit_rays.py`). This work was done
against release 10-02b (bundle 6e4b54e9 + object-space warp 2654a6a6). Its bundle candidate
(`F:\calibration\qc\release_candidate_2026-10-02c_sweepA\`) is OBSOLETE - built on 10-02b, never adopted, and its
"rev c" name collides with 10-03 rev c. What is worth merging is the data, the checks and the findings below.

## 1. What it is

On 2026-09-18 the operator swept the ChArUco plate by hand in front of CH03 (15:40:20-15:41:40) and CH04
(15:42:25-15:45:40) while CH01 and CH02 watched. Every frame (~20 Hz) of all four streams was decoded; frames the
panos could not decode were rescued; the operator clicked 77 hard frames. A board seen at the same moment by the
sweep camera and a pano is a 6-DOF rigid object in the air (0.14-0.54 m above the ground, p10-p90) observed by two
cameras: the only above-ground two-camera data of the calibration besides the wall tops.

## 2. Findings (all against 10-02b)

- Projected from the sweep camera's own board pose (IPPE on its corners) into the panos, the board lands 38 px
  (median; p90 69) off the corners the pano decoded, systematically per pair (CH03->CH01 +16,-12; CH03->CH02 +34,+7;
  CH04->CH01 +5,+35; CH04->CH02 +41,+10 px, observed - predicted). The operator confirmed on video that the outline
  is right (pattern centred on the plate) and the offset real.
- Adding the boards to the bundle (fit_cameras.py FIT_SWEEP, warm start from the release) and re-running the ground
  warp: poses alone take it to 19 px on boards the fit has not seen (odd/even 10-s folds), the panos' canvas scales
  free to 15-16 px; ground checks unchanged (boards 38/85, held-out cones 59/119, ball 61/123 vs 37/86, 62/124,
  61/121). 43 % more views (round 2) changed nothing held out: not data-limited.
- NOT solved by any bundle variant: the board's apparent SIZE in the panos vs the sweep camera's pose (CH03->CH01
  vertical 0.81-0.84, CH04->CH02 horizontal 0.92-0.95). A local scale error of the pano canvas near its ends would do
  this - exactly what a per-pano ray polynomial (10-03) can absorb, given these boards.
- Camera heights moved away from the tape in every variant (bundle has no height information that settles it).
- Error structure (ball 20 Hz, 10-02b and the trial alike): per-pair mean offsets (CH01-CH02 80 mm), a smooth
  position-dependent field (removing each pair's mean per 1 m cell takes the median from 61 to 20 mm), and 2 % gross
  detection outliers (e.g. CH02 at t 61.3-61.5 s, 2.2-2.4 m off - probably the held ball before the 66.6 s interval).
  Boards: per-pair offsets removed, the rest is Gaussian (p90/median 1.80-1.90, Shapiro p 0.6-0.8).

## 3. Data (all under F:\calibration\qc)

| path | what |
|---|---|
| `sweep20\<WIN>_<CAM>.json` | every frame of each stream in the sweep windows (WIN = CH03 / CH04 sweep, CAM = the sweep camera, CH01, CH02): `[i, t_file, t_abs, n, ids, px]`, px UPRIGHT; times bursty - regularise by frame index (`regular_times`) |
| `sweep20\<WIN>_<CAM>_rescue.json` | rescued pano frames `[i, method, n, ids, px, how located]`; methods rect-charuco / rect-chess / rect-refined (measured) and rect-markers (predicted: do not fit). CH03/CH01 172, CH03/CH02 127, CH04/CH01 738, CH04/CH02 1057 frames |
| `sweep20\*_rescue_CONTAMINATED_refine_bug.json` | DO NOT USE (an earlier refinement could slip an even number of squares) |
| `sweep20\click\manual_quads.json` | the operator's 77 clicked frames (4 plate corners, or 3 + verdict partial; crop px + `off`; corner order is NOT fixed - read it off a prediction) |
| `sweep20\instances.json` = `trial_sweep\instances_v3.json` | **the data to use**: 406 two-camera instances, 582 pano views (board slower than 0.3 m/s; one per 0.25 s), sweep-camera px already IR->colour shifted for CH03 (+0.6, -5.6), clock offsets applied (pano + offset = sweep camera: CH03 window CH01 +0.52, CH02 +0.46 s; CH04 window CH01 -0.35, CH02 -0.25 s), per-view sigma (method, homography rms on lens-free rays, partial x2, timing 17 ms at the board's speed) |
| `trial_sweep\instances.json`, `instances_v2.json` | the frozen sets of rounds 1 (268) and 2 (393) |
| `trial_sweep\TRIAL_SWEEP_2026-10-02.md` | the trial report (method, all tables) |
| `trial_sweep\w\`, `w2\` | trial bundles A / B / C (+ odd/even folds, + ground warp and checks in `warp\`) |
| `trial_sweep\SWEEP_CHECK_*.txt`, `release_candidate_*\SWEEP_CHECK.txt` | above-ground scores per bundle |
| `trial_sweep\ball_dist_*.npz` | every aligned 20 Hz ball frame pair's signed difference (10-02b and the trial), for distribution work |
| `sweep20\*_failures*.mp4`, `trial_sweep\w\SWEEP_REVIEW_*.mp4` | review videos (undecoded frames; release vs trial outlines) |

G:\calibration\qc\trial_sweep and \sweep20 hold older copies written before CALIB_ROOT was noticed (rule: F: only);
F: is complete and authoritative.

## 4. Code (G:\Field_2026_Social_Recording\calibration_qc; uncommitted at the time of writing - see git status)

| file | what |
|---|---|
| `board_sweep20.py` | stage A: decode every frame of a sweep window (corner-cache prior, panos upright) |
| `board_sweep20_rescue.py` | rescue: offset-corrected / tracked / clicked priors, virtual pinhole view, locate (markers, rendered-plate template, plate silhouette, wide markers) then decode; `rect-refined` = saddle refinement only from markers or a tracked prior <= 0.5 s, accepted only if the rendered plate (markers, border) correlates best unshifted; `--validate N` (refined vs decoded: median 0.5-0.6 px, p99 1.4-2.6 on 240 frames); `--clicks` |
| `board_sweep20_instances.py` | builds instances.json (selection and weights as in section 3) |
| `board_sweep20_click_gui.py` + `manual_gui_page.py` | the operator's click page (page template moved out of manual_board_gui.py unchanged; `--page-only`, `--keep-first`) |
| `board_sweep20_video.py`, `board_sweep20_failures.py` | review videos |
| `sweep_check.py` | the above-ground score of a bundle: sweep-camera IPPE pose projected into the pano; offset, shape rms, apparent size per pair; in-fit vs held-out by `sweep_keys` |
| `sweep_review_video.py` | release vs trial outlines on every pano view, fold-held-out |
| `fit_cameras.py` | opt-in hooks, default output unchanged: `FIT_SWEEP`, `FIT_SWEEP_NEFF`, `FIT_SWEEP_HOLDOUT`, `FIT_FREE_PANO`, `FIT_INIT` (warm start incl. the init's dropped views), `FIT_MAX_NFEV` |
| `refit_supplement.py` | `--fit` (any bundle) |
| `ball_sync20.py` | `--dump <npz>` |
| (`refit_rays.py --fit` is the ray session's, not this work) |

## 5. Suggested merge

1. Score 10-03 above the ground: `sweep_check.py` uses the raw bundle (`pm.load(fit, correct=False)`, `fm.bearings`,
   `fm.project`); for 10-03 both the sweep camera's pose and the projection into the pano must go through the
   RayCamera's corrected rays. That number (vs 38 / 69 px for 10-02b) says whether the ray release already fixed the
   above-ground mismatch.
2. Use the instances in `refit_rays.py` as constraints: per instance a latent 6-DOF board; every corner of every view
   is a ray that must pass through its board corner (sigma per view from the file; at most ~16 corners' weight per
   view, the views' corners share one pose error); hold out by 10-s blocks (`int(t // 10) % 2`) as in the trial.
3. Check that the boards' apparent size (sweep_check's "size obs/pred") comes to ~1 - the part no bundle fixed.
4. The operator's clicks (`click\manual_quads.json`) are measurements of the plate outline in 77 hard frames; the
   rescue already used them as priors.
