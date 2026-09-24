# Calibration re-audit after the lens-scale and downstream-analysis updates

## Verdict

**60/100, up from 55/100, using the same whole-field scientific floor-tracking readiness criterion with a 50 mm target.** This is a review judgement, not an accuracy probability. For the newer application question, **10 cm-bin place-field analysis is promising for exploration, but has not passed an end-to-end validation**. A bin width is not itself an accuracy specification; downstream stability deserves its own assessment.

| Dimension | Previous / 25 | Current / 25 | Reason for change |
|---|---:|---:|---|
| Data recovery and engineering traceability | 21 | 22 | Added executable downstream sensitivity analysis and documented lens-scale experiments; artifact version binding remains missing. |
| Geometric model and physical consistency | 12 | 15 | Tape-informed lens scales reduce height and tilt inconsistencies, without resolving them. |
| Independent validation and uncertainty | 8 | 8 | New simulations are useful, but use a fixed base camera fit, are stale relative to the new release, and do not constitute independent accuracy or classification validation. |
| Practical ground-mapping readiness | 14 | 15 | Accepted-set disagreement tails improve and sampled warps remain numerically stable; typical disagreement is slightly worse and validity masks remain absent. |
| Total | **55** | **60** | Meaningful improvement, insufficient evidence for whole-field acceptance. |

No new capture is proposed: the supplied audit brief says the field has been demolished. Recommended work uses existing data, recorded measurements and future analysis outputs from existing recordings.

## Scope and reproducible evidence

Reviewed repository HEAD `283020e`, including the preceding downstream-analysis commit `cd8550b`. Read the current report, fitting, data-assembly, mapping and downstream-analysis code. Recomputed short read-only checks from the released fit and existing corner caches; did not rerun bundle adjustment, decode recordings, alter source data, or run the full downstream simulation.

Current artifacts:

- `E:\calibration\qc\camera_fit.npz`: SHA-256 `6faa9e02094e67a8852186ce55ced5d76d58bd27454296380466401798fb9204d`.
- `frame_correction.json`: SHA-256 `7bdacf58fb352d48ab91f22ed944c2391848efea4e624e9de90e7f687be45f1e`.
- `CALIBRATION_FIT.txt`: SHA-256 `a4b31485d2d645576028b26ba361ca4b7aae28700150bec930faf1be39f1ce1c`.
- Repository correction and fit text are byte-identical to their source counterparts.
- New evidence: `audit_release_20260924_v2.json`, `audit_observations_20260924_v2.json`. Original audit JSON files and the original report are preserved.

To reproduce from the repository root with the calibration environment:

```powershell
.\.venv-calibration\Scripts\python.exe calibration_qc\audit_release_20260924.py calibration_qc\audit_release_20260924_v2.json
.\.venv-calibration\Scripts\python.exe calibration_qc\audit_observations_20260924.py calibration_qc\audit_observations_20260924_v2.json
```

## What actually improved

| Quantity | Previous saved fit | Current saved fit |
|---|---:|---:|
| Shared-corner disagreement, median | 64.14 mm | 70.62 mm |
| Shared-corner disagreement, P90 | 146.85 mm | 114.33 mm |
| Shared-corner disagreement, maximum | 301.57 mm | 243.60 mm |
| Shared corners | 2,482 | 2,513 |
| Placements with shared observations | 37 | 36 |
| Fraction of shared corners with disagreement <= 50 mm | 31.7% | 29.0% |
| Fraction with disagreement <= 100 mm | 79.9% | 82.4% |
| Placements whose median disagreement <= 50 mm | 12 / 37 | 10 / 36 |
| Placements whose median disagreement <= 100 mm | 31 / 37 | 32 / 36 |
| Board-centre departure from z = 6 mm, RMS | 99.43 mm | 72.60 mm |
| Board tilt, RMS | 6.79 degrees | 5.64 degrees |

Disagreement is the maximum camera-pair distance for each shared corner, matching `PADDOCK_AGREEMENT.txt`. It is not a single camera's absolute error, and the placements are not independent held-out observations. The downstream file instead pools all pairs, so its overall aggregation is different.

The accepted view sets changed: seven exclusions became six different exclusions. In particular, CH04/T65 is now excluded. Therefore the table demonstrates improvement in the released accepted-set tail, not the isolated causal benefit of the new lens scales on a fixed evaluation population. Compare candidates on fixed common observations and publish exclusion coverage separately.

For every camera, 29,161 sampled warp-grid points had positive local Jacobian determinant and a numerical round-trip error below 1e-7 mm. This is good numerical evidence; it does not certify global injectivity, visible ground coverage, or physical accuracy. The maximum sampled CH01/CH02 correction is still about 0.915 / 1.036 m over the raw-fit field rectangle, so substantial empirical compensation remains.

## Findings ranked by impact

### 1. P1: The new downstream acceptance statement is unsupported and uses stale output

Evidence: `CALIBRATION_REPORT_2026-09-24.md:312` says the primary criterion is met. Its section 9 reproduces `DOWNSTREAM_VALIDATION.txt`, whose CH01-CH04 count is 481 and CH01-CH02 count is 230. Current `PADDOCK_AGREEMENT.txt` and cache reassembly give 431 and 390 respectively. The downstream file predates the latest saved fit. Different aggregation conventions cannot explain different counts for the same camera pair.

Additionally, `downstream_validation.py:369` simulates only 300 Gaussian place cells, with sigma 100-250 mm and no null-cell population. The output's median spatial information is 7.77 bits/spike, while classification is merely thresholded at 0.5. Zero class changes under this deliberately strong spatial-cell simulation provides little evidence about false positives, weak cells or cells near a decision threshold. The reported peak-shift P90 is 141 mm and centroid maximum is 480 mm; a general claim that changes are below one 100 mm bin is too strong even for the old simulation.

**Concrete change:** replace the acceptance claim with a provisional sensitivity result, then regenerate the analysis from a frozen current artifact bundle. Include null cells, near-threshold cells, realistic baseline activity and sample counts, and the actual planned classifier with its shuffle/significance procedure. Evaluate observed tracks and spikes when available from existing recordings. The current CLI accepts only position CSV columns `x_in,y_in`; it has no real-spike input, and its trajectory handoff helper is not called by that input path. Implement those inputs before saying the script accepts real cells and complete tracks.

### 2. P1: The ensemble measures correction sensitivity, not total calibration uncertainty

Evidence: `downstream_validation.py:71` loads a single raw fit. `fit_warp()` changes only polynomial degree, regularization, constraint-type inclusion and point resampling. `displaced()` at line 162 maps assumed physical coordinates through the default correction's inverse and another correction. It does not simulate measured image points with residual errors, vary camera intrinsics/extrinsics, or propagate uncertainty in measured heights, target layout, board height or animal localization. Shared systematic biases can persist in every member. The modeled seam baseline agrees by construction; empirical board discrepancies are reported separately, not injected into simulated position/spike analyses.

Pointwise bootstrap also treats multiple points along the same surveyed cord or wall as separate resampling units. This cannot capture a shared surveying or labeling offset of that physical feature. Mixtures of hand-picked variants and bootstrap members are sensitivity scenarios, not calibrated confidence intervals.

**Concrete change:** extend the analysis to a documented end-to-end scenario ensemble, with grouped resampling by independent placement / cord / station, plausible measurement uncertainty and camera-model alternatives. Preserve correlated camera/region biases and run each scenario through the same tracking and place-field pipeline. Keep warp-only sensitivity as a clearly named component rather than discarding it.

### 3. P1: The saved board poses still contradict the claimed ground constraint

Evidence: the released `board_pose` array gives centre heights from **-222.11 to +216.87 mm**, height-departure RMS **72.60 mm**, **43/64** boards more than 10 mm from the intended plane and **24/64** more than 50 mm away. `CALIBRATION_FIT.txt` itself prints 73 mm. `fit_cameras.py:539` computes a height-prior residual but still permits full six-degree-of-freedom board poses; `least_squares` robustifies that residual along with image errors. Section 3.4 of the report still says each plate lies on z = 6 mm.

The tape-informed lens update is a reasonable scale experiment and the improvement is real. Nevertheless, CH03/CH04 still finish roughly 11/17 cm above the stated tape heights. Heights used to choose lens scales cannot subsequently serve as independent validation of those scales. A hard-height per-camera exploratory fit also does not make the final joint fit hard-constrained.

**Concrete change:** fit a versioned candidate with ground placements represented by x, y and yaw at the stated plane, or explicitly bounded terrain deviations with a physical rationale. Save actual priors, solver termination and achieved physical residuals. Compare both image residuals and fixed-observation ground consistency before promoting it. Hard constraints are a diagnostic of model incompatibility, not a guarantee of a better model.

### 4. P1: Independent accuracy and mapping validity remain unestablished

Board pixels helped fit the camera geometry and board agreement helped select the warp degree. They are useful consistency diagnostics, but not an independent test of the complete pipeline. Measured camera heights now also participate in model selection. Agreement can remain good while both cameras have the same physical bias.

`paddock_map.py:81` rejects rays that do not intersect the requested plane in front of the camera but does not enforce image bounds, a validated ground support region or seam masks. Every camera still returned finite coordinates for at least one deliberately out-of-image probe. `sees()` checks modeled image visibility, not validation support or occlusion. The saved correction is still not bound to its source fit by a checked manifest.

**Concrete change:** publish a per-camera supported ground mask and explicit invalidity reasons at the mapping interface. Evaluate complete held-out placements and spatial blocks by rerunning all affected fit stages; keep board consistency distinct from absolute error. Reserve any unused existing measured references for the latter. If no independent measured references survive, state that limitation explicitly instead of manufacturing a test set from already selected observations.

### 5. P2: Marker-derived pseudo-observations and overstated sample counts persist

`board_detect.py:354` can derive all chessboard corners from a marker-fitted homography and returns the real marker corners as `mk_ids,mk_px`. `fit_data.py` still reads the derived chessboard points and does not consume those measured marker arrays. The current accepted set has **10 views classified predominantly as `rect-markers`, containing 767 aggregated chessboard-corner observations**, generally assigned sigma 1.6 px. This does not mean 767 independently observed corner locations; mixed-frame aggregation further complicates their provenance.

Current totals are 135 assembled views, five bad non-weak views, 19 weak-only views, 111 eligible views, six saved exclusions, **105 accepted views / 7,813 corners**. The report's early table still says 24 planarity rejections plus 19 weak views, double-counting the weak category. These counts need updating alongside the addendum.

**Concrete change:** fit the observed marker corners directly with their known board coordinates and retain point-level provenance; use generated chessboard locations for visualization only. Publish placement-level counts and summaries alongside corner statistics. Audit the fit after the measurement representation changes rather than treating a smaller residual as automatic improvement.

### 6. P2: The focal-length override retains an RMS from a different lens model

`fit_intrinsics.py:124` obtains a fitted parameter vector and its RMS, then changes only CH04's focal length to 2960 at line 126. The returned RMS is not recomputed. `fit_cameras.py:188` prints that old RMS beside the overridden focal length. This does not invalidate the subsequently computed bundle residuals, but misrepresents the evidence for the new intrinsic vector.

**Concrete change:** label the original sweep-fit RMS separately, and recompute sweep residuals with the fixed new focal length, reoptimizing board poses and any explicitly allowed nuisance parameters. Save the focal-length profile experiment and measurement inputs used to justify the chosen value.

The addendum's explanation that a hand-held sweep at one standing spot cannot determine focal length is too categorical. Varied board orientations can constrain intrinsics; weak identifiability must be demonstrated for these views rather than inferred from the operator's standing position. The report's stated flat residual profile is relevant evidence if its computation and settings are preserved. See the primary method description in [Zhang, A Flexible New Technique for Camera Calibration](https://www.microsoft.com/en-us/research/publication/a-flexible-new-technique-for-camera-calibration/). Likewise, the fitted panorama scales imply an effective angular span inside the chosen model; they do not independently prove the physical Duo 3 projection or manufacturer field of view.

## Recommended next work, in order

1. Freeze and identify the current fit/correction/label set with hashes and exact settings. Consolidate the report so current and historical tables cannot be confused. Remove the downstream acceptance language until current outputs exist.
2. Correct measurement provenance and board-plane parameterization in a separate candidate. Recompute intrinsic residuals after overrides. Compare candidates on common observations plus rejection/coverage summaries; do not reward rejection alone.
3. Add support and seam masks, version checks, and failure reasons to mapping. Review T75 (218 mm placement-median disagreement), T64 (173 mm), T74 (119 mm) and the CH01-CH04 transition first. These locations identify review priorities, not an already certified mask boundary.
4. Run grouped spatial/placement validation using existing data, then a current downstream sensitivity analysis with null and marginal cells and the actual classification rule. Report sensitivity to 10 / 15 / 20 cm bins and the planned smoothing choices as candidate analysis settings, not as a claim that larger bins solve the geometry.
5. When extracted animal trajectories and spikes exist, test actual camera switches, speed/path-length artifacts, occupancy and place-field conclusions on the same observations under all retained scenarios. Ground-only calibration does not validate body-height corrections; use a consistently defined tracking point and treat height as a separate uncertainty source.

The present release is useful work and supports continued analysis development. Its defensible claim is improved multi-camera ground consistency with unresolved spatial and physical uncertainty, not verified 50 mm whole-field accuracy or completed place-field validation.
