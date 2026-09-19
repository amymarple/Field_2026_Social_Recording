# -*- coding: utf-8 -*-
r"""Board detection shared by the QC scripts: ChArUco marker path plus a chessboard-corner fallback.

Why the fallback: the marker codes fail long before the chessboard does. On the far rows of the pano
cameras the board is foreshortened to ~20 px per square across the short axis (~2.5 px per marker bit),
and at the edge of the 4K cameras the lens distortion bends the marker quads; in both cases the
ChArUco detector returns 0-10 corners although the 11x8 corner grid is plainly visible. The classic
chessboard detector finds that grid; its 180-degree ambiguity is resolved from the square colours (a
12x9 board flips black/white parity under a half turn) and cross-checked against any decoded marker.
Both paths return the same (ids, px) as OpenCV's CharucoBoard corner numbering (id = row*11 + col).
"""
import numpy as np, cv2

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
BOARD = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, DICT)
OBJ = np.asarray(BOARD.getChessboardCorners(), float).reshape(-1, 3)[:, :2]           # metres, id -> (x, y)
MARKER_CENTRES = {i: np.asarray(BOARD.getObjPoints()[i], float).reshape(-1, 3)[:, :2].mean(0) for i in range(len(BOARD.getIds()))}

def detector_params(**kw):
    dp = cv2.aruco.DetectorParameters()
    dp.minMarkerPerimeterRate = 0.005          # the default 0.03 is relative to the LARGEST image side (7680 px pano)
    dp.perspectiveRemovePixelPerCell = 8
    dp.errorCorrectionRate = 0.8
    dp.adaptiveThreshWinSizeMax = 73
    for k, v in kw.items():
        setattr(dp, k, v)
    return dp
CHARUCO = cv2.aruco.CharucoDetector(BOARD, detectorParams=detector_params())

def charuco_detect(gray, refine_scale=3):
    """-> (n_corners, px (n,2) or None, ids (n,) or None, markers [(id, quad(4,2)), ...])."""
    ch_c, ch_ids, mk_c, mk_ids = CHARUCO.detectBoard(gray)
    if mk_ids is None or len(mk_ids) == 0:
        return 0, None, None, []
    markers = [(int(i), m.reshape(-1, 2)) for i, m in zip(mk_ids.reshape(-1), mk_c)]
    best = (0 if ch_ids is None else len(ch_ids), None if ch_ids is None else ch_c.reshape(-1, 2), None if ch_ids is None else ch_ids.reshape(-1))
    allc = np.concatenate([m for _, m in markers]); x0, y0 = allc.min(0); x1, y1 = allc.max(0)
    pad = 0.35 * max(x1 - x0, y1 - y0) + 20; H, W = gray.shape
    x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad)); x1, y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
    crop = gray[y0:y1, x0:x1]
    if crop.size and max(crop.shape) * refine_scale <= 6000:
        up = cv2.resize(crop, None, fx=refine_scale, fy=refine_scale, interpolation=cv2.INTER_CUBIC)
        c2, i2, m2, mi2 = CHARUCO.detectBoard(up)
        if i2 is not None and len(i2) > best[0]:
            best = (len(i2), c2.reshape(-1, 2) / refine_scale + np.array([x0, y0], float), i2.reshape(-1))
        if mi2 is not None and len(mi2) > len(markers):
            markers = [(int(i), m.reshape(-1, 2) / refine_scale + np.array([x0, y0], float)) for i, m in zip(mi2.reshape(-1), m2)]
    return best[0], best[1], best[2], markers

def square_black(i, j):
    """Square (column i, row j) of the 12x9 board; (0,0) is black."""
    return (i + j) % 2 == 0

def chessboard_detect(gray, markers=(), scales=(0.5, 1.0, 2.0), fast_check=True):
    """Classic chessboard corners of the 11x8 inner grid.
    -> (px (88,2), ids (88,), note) or None. Orientation from the square-colour parity, checked vs markers."""
    H, W = gray.shape
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | (cv2.CALIB_CB_FAST_CHECK if fast_check else 0)
    found = None
    if max(H, W) > 3000:
        scales = (0.5,)                  # full 4K/8K frames: search at half size only (squares stay >= 10 px), refine at full size below
    elif max(H, W) > 2000:
        scales = (0.5, 1.0)              # nadir 2560x1920 frames: the board is >= 100 px/square, a 2x upscale only costs time
    for sc in scales:
        if sc != 1 and max(H, W) * sc > 6000:
            continue
        img = gray if sc == 1 else cv2.resize(gray, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC if sc > 1 else cv2.INTER_AREA)
        ok, pts = cv2.findChessboardCorners(img, (11, 8), flags)
        if ok:
            found = pts.reshape(-1, 2) / sc
            break
    if found is None:
        return None
    pts = cv2.cornerSubPix(gray, found.reshape(-1, 1, 2).astype(np.float32), (5, 5), (-1, -1),
                           (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)).reshape(-1, 2)
    grid = pts.reshape(8, 11, 2)                       # 8 rows of 11 along the long axis
    def contrast(orient):                              # mean(white squares) - mean(black squares) under this orientation
        blk, wht = [], []
        for r in range(7):
            for c in range(10):
                q = (grid[r, c] + grid[r, c + 1] + grid[r + 1, c + 1] + grid[r + 1, c]) / 4.0     # centre of square (c+1, r+1) in orientation A
                x, y = int(round(q[0])), int(round(q[1]))
                if 0 <= x < W and 0 <= y < H:
                    i, j = (c + 1, r + 1) if orient == "A" else (10 - c, 7 - r)
                    (blk if square_black(i, j) else wht).append(float(gray[y, x]))
        return (np.mean(wht) - np.mean(blk)) if blk and wht else 0.0
    sA, sB = contrast("A"), contrast("B")
    orient = "A" if sA > sB else "B"
    base = np.array([r * 11 + c for r in range(8) for c in range(11)])
    ids = base if orient == "A" else 87 - base
    px = grid.reshape(-1, 2)
    note = f"chessboard orient {orient} (contrast A {sA:.0f} B {sB:.0f})"
    if markers:
        Hm, _ = cv2.findHomography(OBJ[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
        if Hm is not None:
            errs = [float(np.linalg.norm(cv2.perspectiveTransform(MARKER_CENTRES[mid].reshape(-1, 1, 2), Hm).reshape(2) - quad.mean(0)))
                    for mid, quad in markers if mid in MARKER_CENTRES]
            if errs:
                note += f"; {len(errs)} markers agree within median {np.median(errs):.0f}px"
                if np.median(errs) > 40:
                    return None                        # orientation contradicts the decoded markers
    if abs(sA - sB) < 8:
        note += "; WEAK orientation evidence"
        if not markers:
            return None
    return px, ids, note

def detect(gray, markers_min=12):
    """Full pipeline on one (cropped) grey image -> (method, px, ids, note) or (None, ...)."""
    nc, px, ids, markers = charuco_detect(gray)
    if nc >= markers_min:
        return "charuco", px, ids, f"{len(markers)} markers, {nc} corners"
    res = chessboard_detect(gray, markers)
    if res is not None:
        return "chessboard", res[0], res[1], res[2] + f" ({len(markers)} markers decoded)"
    return None, px, ids, f"only {nc} corners, {len(markers)} markers"
