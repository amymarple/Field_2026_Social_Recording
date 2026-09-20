---
name: detect-then-decode
description: How to run any detection on this rig's footage - locate the object first, decode it second, degrade to a weaker measurement third, and close the loop with the operator. Use whenever a detector finds nothing or too little (board, cone, marker, animal, LED), before writing "not detected" / "missing" / "no data", and whenever the operator says 识别不出来 / 没检测到 / 看不见 / why did you not find it.
---

# /detect-then-decode - locate first, decode second, operator closes the loop

One rule: **a detector's silence is a statement about the detector, never about the field.**
Until a frame has been rendered and looked at, "not detected" is the only honest phrasing, and it is
a defect report about the code. Born 2026-09-19 from a real failure: 300-600 px calibration boards
were reported to the operator as missing stations, nearly triggering a re-collection trip (the full
account is `calibration_qc/DETECTION_POSTMORTEM_2026-09-19.md`).

## 0. Gate: never write "missing" from an empty result

| You are about to write | Do this first |
|---|---|
| "no detection / not visible / station missing" | render the frame and look at it |
| "too far / too small / too dark" | measure it (below), then quote the number |
| "the operator must re-collect" | operator pass (section 4) on the rendered frames |

Rendering: `python calibration_qc/show_frame.py CHxx HH:MM:SS [--session <date>] [--around STATION]`
(pano cameras come out upright, cone labels and any cached board outline burnt in).

Measure instead of guessing - the numbers that decide which stage can work:

- object size in px (`--around` crop, or the cached outline);
- px per chessboard square = board px / 12 across the long axis;
- **px per marker bit = square_px x 0.75 / 5** (60 mm square, 45 mm marker, 5x5 code). Below ~4 px
  per bit the ArUco code cannot be decoded however good the image is; the corners are unaffected;
- local contrast of the pattern (`gray[roi].std()`, or white-square mean minus black-square mean).

## 1. Locate (coarse) - find the object, not its content

Never ask one detector to solve localisation, perspective and decoding at once. Get a geometric
prior first, cheapest source wins:

1. any decoded markers (>= 2) -> board-mm to px homography (`board_detect.homography_from_markers`);
2. the object's own silhouette - the board's white paper as a bright convex quad
   (`board_detect.find_white_quads`, background-subtracted, both long-side assignments tried);
3. a static-landmark prior - the operator's cone labels, or a local homography from the neighbouring
   cones to the design lattice (`cone_lattice_check.py`, `rescue_boards.expected_px`);
4. the operator's four clicks (section 4).

Then **refine**: rectify, re-detect, re-fit (`board_detect.refine_homography`, 2 rounds). A
homography from a few clustered markers extrapolates badly - one round pulls the whole object in.

## 2. Decode (fine) - in a rectified, frontal view

Warp the object to a canonical scale (`board_detect.rectify`, 2 px/mm, 40 mm margin) and decode
there, easiest decoder first: ChArUco, then the plain 11x8 chessboard with the orientation resolved
from the square-colour parity of the 12x9 board (a half turn flips it) and cross-checked against any
decoded marker. Map the corners back, sub-pixel refine in the ORIGINAL image (window = square/4),
and accept only if a board-plane homography fits them at < 4 px rms.

## 3. Degrade to a weaker measurement, never to "absent"

When the fine decoder cannot work, keep what was measured and say what it is:

| Situation | What still measures | What to store |
|---|---|---|
| Codes unreadable (< 4 px/bit), corners sharp | chessboard corners | 88 ids + px, method `rect-chess` |
| Washed-out frame: the white paper bleeds into the black squares until they no longer touch, so no saddle point exists (verified: every `findChessboardCorners`/SB flag combination fails on a perfectly frontal board) | the marker corners themselves, 24-44 points at ~1 px rms | `mk_ids`/`mk_px` measured + the 88 corners PREDICTED from their homography, method `rect-markers` |
| Part of the object occluded (house, pole, hand, seam) | the visible part | keep a predicted corner only if the four squares meeting there show the expected parity (`board_detect.visible_corners`); T63 kept 39/88 |
| Nothing decodable but the object is visible | the operator's clicks | section 4, method `manual-*` |

Predicted points are correlated with the homography that made them: always store the real
measurements beside them and let the fit weight them.

## 4. The operator loop is mandatory, not a fallback

The operator is the only source of two things the pipeline cannot invent: **object identity**
(which station, which animal) and **ground truth of presence**. Two gates, both blocking:

- **Gate A - identity.** Never guess a station ID from geometry. The operator supplies the timeline
  (`timeline_gui.py` -> `placement_timeline.txt`); `label_timeline.py` labels ONLY inside those
  windows and lists everything else as unlabelled clusters for the operator to extend. Additions
  made from frame evidence go into the timeline file as comment-marked rows the operator can veto.
- **Gate B - presence.** Before any "not present" reaches a report or a re-collection plan, the
  failing windows go through `manual_board_gui.py` (one frame per window x camera, operator clicks
  the four outline corners, cone corner first, or presses Skip = "board not visible"), then
  `manual_boards.py` decodes the whole window from those clicks and records which board corner sat
  on the cone (`manual_cone_corner.json`). Only a Skip makes "not present" a fact, and it is then
  the operator's fact, not the detector's.

Review of what WAS found is part of the loop too: `annotate_video.py --boards` burns every cached
detection (outline, origin corner, station, corner count, method, settled/unsettled) into the
timelapse and `timeline_gui.py --boards` scrubs it, so the operator sees exactly what the machine
believes before anything is fitted.

## 5. Language in reports

- Write "the marker decoder cannot read this board (2.5 px per code bit)", not "no board".
- Write "the operator marked this window as not visible", not "the board was never placed".
- A count of usable positions always carries the method mix and the review state
  (`settled / seen-only / operator-skipped`), never a bare number.

## Failure modes already seen on this footage (2026-09-18/19)

| Symptom | Cause | Fix |
|---|---|---|
| 0 detections beyond ~3 m on an 8K pano | `minMarkerPerimeterRate` default 0.03 is relative to the LARGEST image side | 0.005 + `perspectiveRemovePixelPerCell=8` + `errorCorrectionRate=0.8` |
| 0-10 corners from an obvious board on the far rows | 20 px/square, 2.5 px per code bit | locate + rectify, then chessboard corners |
| Perfectly frontal board still undetectable | overexposure erodes the black squares, corners no longer touch | marker-corner measurement + parity-filtered prediction |
| Corners land on a house roof / the pole | homography extrapolated across an occluder | `visible_corners` parity check |
| Crash `need at least one array to concatenate` | marker ids >= 54 are false positives (dictionary has 100 codes, board uses 0-53) | filter ids to `MARKER_MM` before fitting |
| Detector "worked" but the label was wrong | station identity guessed from geometry | Gate A - operator timeline only |

## Reference

- Code: `calibration_qc/board_detect.py` (stages 1-3), `rescue_boards.py` (re-decode thin windows),
  `manual_board_gui.py` + `manual_boards.py` (gate B), `show_frame.py`, `cone_lattice_check.py`,
  `annotate_video.py --boards/--still`, `timeline_gui.py --boards`.
- Environment: these scripts need OpenCV - `C:\Users\Cornell\miniforge3\envs\cv\python.exe`
  (conda is not on PATH).
- Memory notes behind this skill: `believe-the-operator-check-the-detector`,
  `calibration-session-2026-09-18`.
