# Postmortem - "the station is missing" was a detector bug (2026-09-19)

## What happened

Reviewing the 2026-09-18 calibration capture I reported to the operator that several stations
(V11, F14, T35, V44, T12, T21, F32, ...) had **no usable detection in any camera**, listed them as
gaps, and built a return-trip plan around re-placing them. The operator pushed back twice:

> 大哥我为啥我看见但机器读不出来你没有想过是你算法的问题
> 你这个大部分没解出我建议你先检测板子之后再解格子

Both objections were correct. The boards are 300-600 px wide and plainly readable in the frames.
After rewriting the detector board-first, stations I had declared invisible came back with 80-88
corners: T12 in CH01 (0 -> 25 frames), T14, F12, V13, F14, T63, T64, T21, V44, T35. No re-collection
was needed for them.

## The three errors, in the order they did damage

### 1. A detector's silence was reported as data absence

`qc_placements.py` returned 0-10 corners for those windows, and I wrote that up as "no detections in
any camera - operator in the line of sight / board unreadable". That sentence is a claim about the
field. The evidence only supported a claim about the code. The cost of the wrong framing is real: a
re-collection trip, and the operator's time spent arguing with a number instead of checking data.

**Rule:** "not detected" is a defect report. Nothing may be called missing until a frame has been
rendered and looked at, and if the object is visible there, the finding is a bug, stated as one.

### 2. Conclusions before measurement

I explained the failure as "the board is too far / too small" without measuring anything. The actual
numbers, once taken:

| Quantity | Far rows of the pano | Consequence |
|---|---:|---|
| board width | 300-600 px | plainly visible |
| px per chessboard square (short axis) | ~20 px | corners perfectly locatable |
| px per ArUco code bit | ~2.5 px | **code undecodable at any exposure** |

So the marker layer was dead while the geometry layer was fine. That distinction decides which
algorithm can work, and it took three rounds to compute because I reasoned about the image instead
of measuring it.

**Rule:** quote a number, or do not offer a cause. For this board: px per bit = square_px x 0.75 / 5;
below ~4 px per bit the code is gone and only corner-based methods can work.

### 3. The pipeline ran fine-to-coarse

The original code asked one detector (`CharucoDetector.detectBoard`) to solve localisation,
perspective and decoding simultaneously on the raw 8K frame. That is the fragile order. The
operator's suggestion - find the board first, then solve the grid - is coarse-to-fine with a
geometric prior, and it is now the pipeline (`board_detect.py`):

1. **Locate** the board: homography from any decoded markers (>= 2), else the white paper as a
   bright convex quad, else a lattice prior from the labelled cones, else operator clicks.
2. **Refine** the homography by rectify-and-redetect (a homography from a few clustered markers
   extrapolates badly across the board).
3. **Decode** in a frontal 2 px/mm rectification: ChArUco, then the 11x8 chessboard with the
   orientation resolved by square-colour parity and cross-checked against the decoded markers.
4. **Validate**: map back, sub-pixel refine in the original image, accept at < 4 px plane rms.

A fourth finding came out of this rewrite: in washed-out frames the white paper bleeds into the
black squares until they no longer touch at the corners. No saddle point exists, so **no**
chessboard detector can work - verified by running every `findChessboardCorners` and
`findChessboardCornersSB` flag combination on a perfectly frontal rectified board, all False. There
the marker corners themselves are the measurement (24-44 points at ~1 px rms) and the 88 chessboard
corners are predicted from their homography, each kept only if the four squares meeting at it show
the expected black/white parity - which also removes corners hidden behind the house or the pole
(T63: 39/88 kept).

## What changed in the repo

- `calibration_qc/board_detect.py` - the board-first pipeline, the marker-corner fallback, the
  occlusion parity filter, marker-id sanity (ids >= 54 are false positives).
- `calibration_qc/rescue_boards.py` - re-decodes every timeline window with < 3 cached frames.
- `calibration_qc/manual_board_gui.py` + `manual_boards.py` - the operator clicks four outline
  corners; the window is decoded from that hint; the clicked cone corner is recorded.
- `.claude/skills/detect-then-decode/SKILL.md` - the logic above as a project skill, including the
  two blocking operator gates (identity, presence).
- Memory: `believe-the-operator-check-the-detector`.

## The standing rule this produced

The operator is not a fallback for the detector; the operator is a required stage of it. Identity
comes only from the operator's timeline, and "not present" is only ever the operator's statement,
made by skipping a frame in the manual GUI after seeing it. Everything the machine did find is
reviewed the same way, by burning the detections into the timelapse (`annotate_video.py --boards`)
before any of it is fitted.
