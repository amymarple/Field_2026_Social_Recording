# Release 2026-10-02 revision c (DRAFT, not yet adopted): the hand-held sweep boards in the bundle

Candidate chosen by the operator on 2026-10-02 ("round 2, A") after the review videos of the trial
(`F:\calibration\qc\trial_sweep\TRIAL_SWEEP_2026-10-02.md`). Files in this folder; nothing in `calibration_qc\` or
`F:\calibration\qc\` is replaced until the operator says so.

## What changes

Both release files. **Bundle** `camera_fit.npz` sha256 `3798c377b6cccac5...` (was `6e4b54e9264a3675...`, the
2026-09-24 bundle): the release bundle continued (fit_cameras.py `FIT_INIT` = the release, `FIT_MAX_NFEV` 1000, the
release's own second-pass drops) with the 2026-09-18 hand-held sweep boards added (`FIT_SWEEP`, 393 two-camera
instances, 559 pano views, board 0.14-0.54 m above the ground, `sweep_instances.json`); lenses unchanged (variant A:
camera poses only). **Ground warp** `frame_correction.json` sha256 `047f238c345cccd2...` (was `2654a6a6...`): the
revision-b recipe re-run on the new bundle (frame_correction.py, then refit_supplement.py --soft-lattice 4 --deg
CH03..06=2 --drift session_2026-09-30_drift_final.json --fit/--rel this bundle).

Without the sweep the same continuation stays exactly on the release (W0, 1000 and 3000 more steps: every check and
the mapping identical), so every change below is the sweep boards'.

## Evidence (same data and scripts for both; mm unless px)

| check | release (rev. b) | **rev. c** |
|---|---|---|
| sweep boards, pano views NOT in the fit (odd/even 10-s folds), offset median / p90 | 38 / 69 px | **19 / 37-46 px** |
| boards 09-18/19, all shared corners (`PADDOCK_AGREEMENT.txt`) | 37 / 86 | 38 / 85 |
| supplement cones, 5-fold held out (`REFIT_SUPPLEMENT.txt` 2) | 62 / 124 | 59 / 119 |
| ball 20 Hz, all pairs aligned (`BALL_SYNC20.txt`) | 61 / 121 | 61 / 123 |
| ball, CH01-CH02 / the CH04 end | 85 / 49 | 83 / 49 |
| ball 2-s marks, all pairs (`BALL_CHECK.txt`) | 94 / 278 | 100 / 283 |

Sweep per pair, held out (median px): CH03->CH01 18-28, CH03->CH02 17-23, CH04->CH01 13-23, CH04->CH02 18
(`SWEEP_CHECK.txt`; release 29 / 32 / 38 / 52 on all views). The ground mapping moves against revision b by a
median of 3-7 mm per camera (max 50 mm, CH03, at its support's edge).

## Known limits

1. **Shape.** The sweep board's apparent size in the panos still disagrees with the sweep camera's pose (CH03->CH01
   vertical 0.81-0.84, CH04->CH02 horizontal 0.92-0.95); no variant fixed it (pano canvas scales free, pinhole focal
   lengths free). The remaining 15-20 px above ground is that, not missing data: 43 % more sweep views (round 2)
   changed nothing held out.
2. **Heights.** Camera centre height - tape: CH01 -96, CH02 -15, CH03 +113, CH04 +23 mm (revision b: -10, +72, +58,
   +119). The bundle has no height information that settles this.
3. **Ground unchanged.** The sweep adds no ground information; ground accuracy is revision b's. What improves is the
   cameras' agreement on a point 0.1-0.5 m above the ground (a rat's back and head), i.e. the hand-off between cameras
   for anything that is not on the grass.
4. Everything in RELEASE_2026-10-02.md "Known limits" still holds (absolute frame unverified, selection, no
   bundle-independent CV number, keypoint height).

## Adopting it (when the operator says so)

Back up revision b to `F:\calibration\qc\release_2026-10-02b\`; copy `camera_fit.npz`, `frame_correction.json`,
`fit_manifest.json` to `F:\calibration\qc\` and `calibration_qc\`; RELEASE_2026-10-02.md gets a "Revision c" section
from this draft; README dated entry; commit and push (the analysis repo then pulls).
