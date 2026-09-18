# CH01/CH02 offline ground calibration

Implemented the panorama-first plan as the independent `camera_ground` Python package. It does not control cameras, recorder tasks, IR settings, or live streams.

## Delivered

- Verified the supplied board: 12x9 squares, 54 markers IDs 0-53, 88 internal corners; exact binary-image reconstruction. Smallest matching dictionary DICT_5X5_100; larger shared-prefix dictionaries also match.
- Generated a pending 59-placement field kit (35 train, 12 validation, 12 final test), JSON measurement manifest and SVG layout. Proposed coordinates remain separate from measurements.
- Added bounded explicit closed-video extraction, pixel-transform declarations, reviewed ChArUco/manual observations, repeated-frame aggregation, measured ground-coordinate construction and grouped splits.
- Added normalized polynomial, piecewise-affine and regularized TPS selection. Deployed models share validated forward/inverse meshes with domain/seam masks, overlap/fold rejection and explicit invalid outputs.
- Added frozen validation selection, one-use test registry, position-balanced regional acceptance, residual plots, BEVs, camera-source maps and paired measured-target comparison.
- Added an opt-in adapter in the adjacent analysis checkout's field_coords.py. Original source backed up there; no historical calibration JSON overwritten. The new package must be installed in the analysis Python environment before using the new type.
- Recomputed legacy CH01/CH02 training residuals: 55.8748 / 51.3050 cm. These are not independent accuracy measurements.

## Verification

15 unit/integration tests and one complete two-camera CLI exercise passed on synthetic data, including PTS extraction from a generated closed MP4. Tests exercise unchanged legacy entrypoints, failed/provisional rejection, test reuse rejection, masks, inverse consistency, frame convention and epoch checks. Python compilation and changed-file whitespace checks were run.

## Pending field work

Actual board dimensions/height, current reference images and stitching settings, measured ground placements, independent test data and real-camera BEVs. No new real-world calibration or centimetre accuracy is claimed. Existing unrelated neurologger changes were not edited.
