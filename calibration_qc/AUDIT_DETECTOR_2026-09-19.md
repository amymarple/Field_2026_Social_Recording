# Board detector audit — 2026-09-19

## Conclusion

The poor detection is reproducible. It combines a marker-decoding bottleneck in difficult field images with avoidable pipeline losses. The board definition is correct on the supplied artwork. Do not classify footage as requiring re-acquisition solely because this QC pipeline has fewer than 12 cached corners.

This was an audit and bounded diagnostic experiment. Production detector files and source caches were not modified by this audit. New diagnostic files are confined to the repository. The directory changed during review: a shared `board_detect.py` appeared and `rescue_boards.py` was refactored to use it. The final rescue diagnostic records the inspected shared-module SHA-256. Earlier diagnostic observations were rechecked against that module.

## Reproduction

Runtime: existing `.venv-calibration`, OpenCV 5.0.0, one OpenCV thread. Main comparison directly executes the existing `detect_refined` function extracted without running the script's video job. The four difficult inputs below are existing diagnostic JPEG crops, not a representative success-rate sample.

| Existing crop | Main refined path: markers / corners | Shared chessboard fallback: candidate corners |
|---|---:|---:|
| CH01 15:06:20 | 3 / 0 | 0 |
| CH01 15:16:45 | 10 / 3 | 0 |
| CH01 15:24:10 | 8 / 3 | 88 |
| CH02 15:04:20 | 0 / 0 | 0 |

- Original `calibration.png`: 54 markers, all 88 ChArUco corners. Dictionary/layout mismatch is not the cause demonstrated here.
- Lossless grayscale frames decoded directly from the closed 15:00 source segments at CH01 15:16:45 and CH02 15:04:20 also return 10/3 and 0/0. Failure at these two times is not merely a JPEG-preview artifact.
- Increasing the adaptive threshold maximum from 23 to 73, or disabling `checkMarkers`, does not materially recover these difficult cases. Disabling the check is not a recommended fix.
- Approximate manual outline rectification of three difficult crops does not reach 12 ChArUco corners; the best tested CH01 15:16:45 variant reaches 6. This experiment used approximate outlines and is not evidence that all rectification approaches fail.
- On the successful CH01 15:24:10 chessboard fallback, the one corner ID shared with the direct ChArUco pass agrees within approximately 0.018 pixels in this diagnostic crop. The overlay shows a coherent grid. One shared ID does not certify all 88 identities or independent metric accuracy.
- Easier examples still work: CH01 handling crop yields 41 corners; CH02 monochrome crop yields 15. IR is not, by itself, a demonstrated cause of failure.

Evidence: `audit_detector_benchmark.json`, `audit_rescue_diagnostic.json`, `audit_chessboard_detect_test_CH01_152410_crop.jpg`. Reproduction scripts are `audit_detector_benchmark.py` and `audit_rescue_diagnostic.py`; source frames remain read-only.

## Actionable findings

### P1 — Main detector has no recovery route when the initial marker pass returns zero

`qc_placements.py:91–92` returns before any crop refinement. Its crop is otherwise inferred only from already-decoded markers, so partial detections can also restrict the search to one board portion. A failed seed cannot be rescued by its advertised 3x crop stage. The newer `board_detect.charuco_detect` retains this marker-path limitation, although `board_detect.detect` adds a separate chessboard fallback. The main QC script still has its own detector and does not use that shared fallback.

Fix: use the common detector from every QC entry point; support an independently located ROI from verified placement/time annotations or reviewed outlines even when zero markers decode. For unknown board locations use bounded overlapping tiles or temporal ROI proposals. A cone/model prediction is a search prior, not ground-truth correspondence.

### P1 — Main refinement selects by marker count instead of usable ChArUco corners

`qc_placements.py:103` replaces the first result whenever the crop finds at least as many markers, even if it finds fewer or zero ChArUco corners. Conversely, it can discard a crop with more useful corners and fewer markers. This is a code-level regression path; the current sample does not measure how often it occurs. The newer shared detector compares corner counts and avoids this particular selection bug.

Fix: retain all candidates and select by valid, distributed corner support and consistency. At minimum never replace a usable initial result with fewer valid corners merely because marker count rises.

### Resolved during review — Incorrect square sampling location in an intermediate revision

An intermediate `board_detect.py` revision used `grid[r,c] + grid[r,c+1] + grid[r+1,c] + grid[r+1,c]`: the bottom-left corner was counted twice and the bottom-right was absent. The final source reread shows this has been corrected by a concurrent edit. It is not an outstanding finding against that final version. It did not explain initial ArUco decoding failures.

The remaining design issue is single-pixel centre sampling: replace it with robust samples of known white margins around the printed marker, compared with black squares; test both orientations against decoded marker identities. The centre of a nominally white square contains ArUco code bits and is not reliably white. Preserve ambiguous orientation as a rejected/review-required candidate.

### P2 — Fallback acceptance can look more confident than its evidence warrants

The shared fallback accepts a full 88-corner grid with a fixed 40-pixel median marker-centre tolerance, independent of grid spacing or image scale. The weak-colour branch treats a nonempty marker list as supporting evidence even if no in-board marker was actually checked. A global homography also cannot capture all panorama-local distortion. There is no explicit neighboring-frame ID consistency gate before saving recovered corners.

Fix: require actually checked in-board IDs, compare both possible orderings with scale-relative residuals and a clear winning margin, validate grid topology and local corner evidence, and check independent settled frames. Store the decision metrics and reason for rejection. Do not loosen thresholds just to obtain 88 corners.

### P2 — Sampling and reporting discard evidence and can resemble detector failure

- Main `every=2` samples roughly every four seconds when keyframes are two seconds apart. Short holds can fall between samples; `--every 1` improves this but is not fixed-rate dense sampling.
- Caches retain only frames with at least 12 corners. Missing cache files cannot distinguish no board, partial board, ambiguous identity, or a skipped frame.
- Placement clustering uses the mean of visible marker corners. That mean moves as different markers become visible even for a stationary board, splitting one placement or merging neighboring placements.
- Timestamp fallback assumes a keyframe period (or 15 fps in rescue). Missing PTS should be a reported failure, not silently converted into a plausible station time.
- Rescue skips a time window once it has three cached timestamps without checking whether those are distinct, settled, well-spread observations of the intended placement.

Fix: densely sample only operator-confirmed short windows, retain per-frame failure reasons and candidate diagnostics, use shared-ID motion rather than visible-marker centroid motion, and require actual decoded timestamps. Keep detection success separate from field-station labeling and ground-plane validity.

## Recommended implementation order

1. Consolidate main QC and rescue on one pure detector with diagnostics. Correct main-path candidate selection and retain the square-centre correction already present in the latest shared module.
2. Rerun verified placement windows from original-resolution closed recordings, with explicit ROIs and several settled frames. Do not reprocess all recordings on the production machine.
3. Add a guarded chessboard fallback (classic and, after benchmarking, sector-based detector), validated orientation, and original-image corner refinement. Keep recovered candidates separate from accepted calibration points.
4. Produce paired overlays and a per-placement report separating detected grid, verified IDs, settled pose, station identity, and metric acceptance. Use that report to identify actual remaining acquisition gaps.

An increase in detected corners alone is not a centimetre-accuracy claim. The present audit supports recovering and validating existing footage before issuing a detector-based reshoot list.

## Reference

OpenCV's [ChArUco detection documentation](https://docs.opencv.org/4.13.0/df/d4a/tutorial_charuco_detection.html) explains that marker detection precedes ChArUco interpolation and that uncalibrated interpolation uses local homographies sensitive to distortion. The installed runtime was tested directly; no claim of OpenCV-version regression is established by this audit.
