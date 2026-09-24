# Independent review of the September 24 calibration report

## Verdict and score

**55/100 for readiness to support whole-paddock scientific floor trajectories with a 50 mm accuracy target.** This is an explicit engineering judgement, not an estimated accuracy probability.

| Dimension | Score / 25 | Reason |
|---|---:|---|
| Data recovery and engineering traceability | 21 | Operator review, actual plate margins, shared-ID temporal aggregation, readable reports and reproducible ground-agreement results are substantial improvements. |
| Geometric model and physical consistency | 12 | Board height remains inconsistent with the claimed pinned plane; measured camera heights disagree; panorama compensation remains empirical. |
| Independent validation and uncertainty | 8 | Training observations and model-selection observations are described as independent checks; location-level validation and absolute reference accuracy remain insufficient. |
| Practical ground-mapping readiness | 14 | Useful central-region consistency and numerically stable warps, but no supported-domain validity gate and unacceptable tails for a 50 mm target. |
| Total | **55** | Suitable for exploratory, region-restricted analysis after explicit masking; not accepted as a whole-field 50 mm metric calibration. |

The capture is valuable. The current calibration is a six-camera geometric fit followed by camera-specific empirical ground corrections, not a verified metric 3-D reconstruction. Re-acquisition is not proposed: the field has been dismantled.

## What was actually checked

- Read the report, fitting/data assembly/model/mapping/warp/evaluation code and paired text outputs.
- Read the released `E:\calibration\qc\camera_fit.npz` directly. Its SHA-256 is `34a3b8741340f4b9f67642f922ad5d76d58bd27454296380466401798fb9204d`.
- Verified repository `CALIBRATION_FIT.txt` and `frame_correction.json` are byte-identical to their E: counterparts. This is not merely a stale repository copy of those artifacts.
- Reassembled existing small corner caches without writing to the source or decoding videos. Recomputed accepted-set cross-camera agreement using the current mapping.
- Sampled each polynomial warp on 29,161 raw-fit field-grid points for local Jacobian sign and numerical round trip. Tested out-of-image input behavior and local height sensitivity.
- Generated perfect flat synthetic board projections under the released models as a bounded check of the raw-image homography approximation.

No bundle was rerun, no camera settings were changed, and source recordings/labels/fits were not overwritten. The inspection scripts and JSON evidence are `audit_release_20260924.py/.json` and `audit_observations_20260924.py/.json`.

## Findings, ranked by impact

### 1. P1 — The released boards are not pinned to the ground as the report claims

Report section 3.4 describes z = 6 mm with a 1 mm prior. Direct evaluation of `board_pose` at the pattern centre yields:

- centre heights **-339.09 to +125.55 mm**;
- RMS departure from z = 6 mm **99.43 mm**;
- **43/64** boards depart by more than 10 mm, **32/64** by more than 50 mm;
- tilt RMS **6.79 degrees**, against the stated 2-degree prior.

The same 99 mm height RMS is already printed in `CALIBRATION_FIT.txt:86`. `fit_cameras.py:514–518,555` keeps six board degrees of freedom and includes height/tilt priors in the global soft-L1 objective. A soft 1 mm prior is not a hard plane constraint. The saved artifact does not record the actual environment-overridden sigmas, solver status or convergence history, so this review cannot determine whether the mismatch arose from different run parameters, robust prior trade-offs, convergence, or their combination.

**Concrete change:** represent confirmed ground placements with x, y and yaw only on the specified target plane, then refit as a separately versioned candidate. If measured terrain departures must be represented, make them explicit bounded physical variables rather than claiming a hard plane while allowing unrestricted 6-DOF compensation. Save actual priors, solver status and achieved physical residuals with every fit.

This does not prove every current 2-D coordinate is unusable; it invalidates the report's physical explanation and blocks acceptance of camera heights or height-dependent corrections.

### 2. P1 — The reported agreement is not an independent end-to-end accuracy test

`paddock_agreement.py:44–49` uses the same accepted placements as the fit and excludes fit-rejected views. The boards were not used to estimate warp coefficients directly, but they were used by the upstream bundle. Report section 5.1 also compares polynomial degrees on their board agreement and selects degree 4. That makes them model-selection data for the correction as well.

Cones, cords and the selected straight wall sections are correction training constraints, not independent validation after that correction. A shared mapping error can cancel between cameras, so cross-camera agreement is not absolute accuracy. Whole-board corner errors are strongly correlated; 2,482 corners are not 2,482 independent placements.

Recomputed accepted-set results match the report:

| Metric | Result |
|---|---:|
| Shared physical placements | 37 |
| Shared corners | 2,482 |
| Per-corner maximum pairwise distance, median / p90 / maximum | 64.14 / 146.85 / 301.57 mm |
| Shared corners with disagreement <= 50 mm | 31.7% |
| Shared corners with disagreement <= 100 mm | 79.9% |
| Placements whose median disagreement <= 50 mm | 12 / 37 |
| Placements whose median disagreement <= 100 mm | 31 / 37 |

These are consistency statistics on the accepted dataset, not the fraction of animals localized accurately. CH02–CH03's 54 mm pair median is supported by only **one** board; it cannot characterize their entire overlap.

**Concrete change:** run spatially grouped, placement-level outer validation of the complete pipeline. Keep all cameras/frames of a held-out placement out of fitting; select warp degree and regularization inside the training folds. Separately hold out whole cones/cords/wall segments to measure generalization of the ground correction. Use placement/landmark-group bootstrap intervals, and report excluded observations and spatial coverage. With these already-examined data, call the result grouped cross-validation, not pristine unseen final testing.

### 3. P1 — Predicted corners are still counted as independent observations

`board_detect.py:354–361` creates `rect-markers` chessboard coordinates by projecting the design grid through a homography fitted to measured marker corners. It correctly saves `mk_ids` and `mk_px`. But `fit_data.py:132–140,184–198` loads/aggregates `ids` and `px`, not those real marker observations; `rect-markers` is not in `WEAK`.

The accepted observations contain **nine majority-rect-markers views, totaling 718 assembled corners**, normally with sigma 1.6 px. These views may contain mixed frame methods; the metadata preserved downstream does not identify the provenance/covariance of each final corner. The issue is not that marker-derived measurements have no value: the fitted homography's many predictions are correlated and cannot be treated as new independent corner measurements. They also favor homography-like geometry by construction.

**Concrete change:** use the measured marker-corner pixels and their actual board coordinates directly as residuals for this path. Keep predicted chessboard corners for display or explicitly covariance-aware estimates, not ordinary independent residuals or independent validation points. Apply the same provenance rule to sweep intrinsics; `fit_intrinsics.free_views` currently excludes outline predictions but does not generally exclude marker-homography predictions.

Excluding the nine majority-marker views from evaluation alone changes the median to 57.64 mm but leaves p90 at 145.37 mm and maximum at 301.57 mm. This changes the sample and is not a valid demonstration of improvement or a substitute for refitting.

### 4. P1 — The public mapping accepts unsupported pixels and extrapolation without a validity result

`paddock_map.Camera.to_paddock` checks forward intersection with the requested horizontal plane. It does not reject out-of-image pixels, seam/occlusion regions, points outside calibration support, or unvalidated spatial regions. Bounded probes returned finite coordinates for out-of-image pixels in all six cameras. `sees()` is a geometric frame-visibility helper, not a calibration-validity mask, and is not called by `to_paddock`.

The fourth-degree corrections have 30 scalar coefficients per panorama. The nominal constraint count overstates independent two-dimensional support: points sampled along the same cord are correlated and constrain only one coordinate. Sampling the entire raw-fit rectangle found panorama displacements as large as 1.24/1.69 m; these can lie outside a camera's useful region and are NOT claimed observed localization errors, but they demonstrate why unchecked extrapolation is inappropriate.

**Concrete change:** return validity/status with coordinates, enforce image bounds plus per-camera verified support and seam masks, and reject unsupported points. Add inverse convergence/residual checks rather than returning a finite answer after a fixed number of Newton iterations. Make the verified domain part of the versioned calibration.

### 5. P1 for height-dependent tracking — A ground warp does not establish a physical 3-D camera model

The tape/fit height discrepancy is 0.17–0.45 m. Applying a different 2-D ground polynomial to each camera's horizontal centre does not recover a single physical 3-D frame or independently validate optical-centre positions. The report's statements that ground mapping is "unaffected" and that the correction is valid "a few centimetres above" the ground are stronger than the evidence supports.

An empirical ground map can still work despite incorrect fitted heights, provided independent ground measurements demonstrate it. That independence has not been established here. `to_paddock` applies the same ground correction for arbitrary `z_mm`; this is an extrapolated 3-D extension, not a validated height correction.

`height_sensitivity()` also mixes a corrected physical point with the uncorrected camera centre and omits the warp Jacobian. For example, at the CH05 image centre it reports 0.0725 mm/mm, while finite differencing the actual current mapping gives 0.0537 mm/mm. The difference is an implementation inconsistency, not evidence either number describes true animal-height error. Sensitivity varies over the image; a single optical-axis number cannot characterize far ground rays.

**Concrete change:** publish this release as ground-plane-only until height behavior is verified; define the animal localization point explicitly. For diagnostics compute the derivative of the actual mapping at each queried pixel, and keep that model derivative distinct from empirically verified height accuracy. Investigate the tape datum and board print scale using existing records/retained artifacts, and use verified measurements as constraints with stated uncertainty in a new physical fit.

### 6. P2 — Report accounting and several categorical claims need correction

- Actual data flow is **135 assembled -> 5 bad + 19 weak excluded -> 111 -> 7 fit-rejected -> 104 retained camera-views / 7,654 corners**. The report says 24 planarity rejects plus 19 outline views; the code prints 24 by combining both categories, then prints the 19 again. Section 6.3 says six rejected views; the fit stores seven.
- `CALIBRATION_FIT.txt` describes design-grid placement offsets as a check whose grid "was never given to the fit", but `fit_cameras.py:513` includes station residuals and cone landmarks. This is not an independent station-placement measurement under the current default settings.
- Section 5.2's wall agreement summary of 1–4 inches omits listed pairs with medians 4.8 and 8.1 inches. Some comparisons involve curved ends or little overlap; report the subset and its limitations rather than a universal summary.
- A raw-image homography is not a camera-model-free planarity test. Equirectangular projection and radial distortion need not map a plane by a homography. Our limited perfect-ground-board simulations under the released models stayed below 4 px (maxima 1.86–2.69 px), so this audit does NOT demonstrate that the five rejected real views were good. It demonstrates that the report's universal inference "not homography => wrong IDs under any camera" is unjustified. Treat it as a heuristic trigger for model-aware review.
- Round-trip numerical agreement demonstrates inverse consistency, not measurement accuracy.
- The current entry point fixes nominal panorama intrinsics; it does not reproduce the historical free-fit/per-lens comparison simply by running the commands in section 8. Preserve those experiments and their configurations if claiming full reproducibility of those conclusions.

**Concrete change:** generate counts and numerical claims from one immutable run manifest and classify every metric as training fit, model selection, held-out consistency, or independent physical measurement. Correct the report before using it as an acceptance document.

### 7. P2 — Artifact provenance and fallback behavior can silently mix calibrations

The fit artifact lacks source/config hashes, actual environment overrides, solver success/status and explicit valid-domain metadata. The correction only records a fit path. `paddock_map.load(correct=True)` silently returns uncorrected mappings if the correction JSON is missing, and does not check that a present correction belongs to the loaded fit. Re-running the bundle can therefore leave a stale correction silently attached to a new fit.

`fit_data.py` chooses a majority method via `max(set(base), key=base.count)`. Ties depend on Python set ordering; two audit processes assigned one mixed-method view differently. Pixel aggregation and the reproduced agreement were unchanged in this check, but method-dependent sigma selection should not be nondeterministic.

**Concrete change:** publish a manifest-bound bundle of fit, correction, coordinate conventions, support masks and validation metrics. Fail explicitly on missing/stale required correction files and use a deterministic, provenance-aware method/covariance rule.

## Positive results worth retaining

- Correct physical plate margins are represented separately from the printed pattern.
- Operator identity/review and explicit OSD exclusions are meaningful improvements over geometry-guessed station identities.
- Shared-ID temporal clustering avoids the previous visible-marker-centroid failure.
- The reported 64/147/302 mm agreement is numerically reproducible from the released inputs.
- On the 29,161-point raw-fit rectangle grid per camera, no sampled warp Jacobian had a nonpositive determinant. Panorama determinant ranges were approximately 0.84–2.17 and 0.64–2.33. This is positive evidence against local folding on that grid, not a proof of global injectivity or correct ground geometry.
- Tested warp round trips were below approximately 1.1e-8 mm. Numerical inversion is working on the sampled domain; it is not the main demonstrated accuracy bottleneck.

All 64 saved board rotations have negative `R[2,2]`. This alone is NOT labeled a face-down failure: the sign of the physical printed-face normal depends on the chosen board-coordinate convention. Any signed-normal fix must explicitly establish that convention first.

## Prioritized recovery plan without new field acquisition

1. Freeze the current release and correct its report/manifest. Retain all original labels and record analyst-proposed relabels with explicit operator approval state.
2. Replace pseudo-corner residuals with real marker observations, and implement the physical ground-plane constraint as an actual parameterization. Save achieved board-plane residuals and optimizer state.
3. Refit a pinhole-first reference and check the shared-observation graph and cross-session consistency. Use the tape measurements only after their datum and uncertainty are established. Do not force a disconnected reference graph together with unverified precision.
4. Refit camera-specific ground corrections with placement/landmark-group outer validation and inner model selection. Equalize influence by physical feature/placement, not by how many clicks lie along one cord. Degree 4 is a candidate, not a proven optimum.
5. Publish per-region accuracy evidence, tails and valid masks. In weak panorama end regions prefer the camera with better held-out performance, or mark the area unvalidated. Do not average a biased camera into a better one merely for coverage.

Until those steps are completed, exploratory coarse occupancy analysis may be defensible within explicitly reviewed regions and an error-aware binning scheme. Whole-field 50 mm positions, fine inter-animal distances and unvalidated height-corrected tracks are not supported by this release's evidence.
