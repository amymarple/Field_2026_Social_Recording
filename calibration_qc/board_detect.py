# -*- coding: utf-8 -*-
r"""Board detection shared by the QC scripts - board first, grid second.

Why: the ChArUco marker codes fail long before the chessboard does. On the far rows of the pano
cameras the board is foreshortened to ~20 px per square across the short axis (~2.5 px per marker
bit) and at the edge of the 4K cameras the lens distortion bends the marker quads; the plain
detector then returns 0-10 corners from a board that is 300-600 px wide and perfectly readable.

Pipeline of detect(gray):
  1. ChArUco on the raw crop (plus a 3x re-detect of the board region). >= 12 corners -> done.
  2. Locate the board: a homography board-mm -> px from the decoded markers (>= 2), else from the
     board's white paper found as a bright convex quadrilateral (both long-side assignments tried).
  3. Rectify the board to a frontal 2 px/mm view (1440x1080 + margin) and decode THERE: ChArUco
     first (ids are certain), else the classic 11x8 chessboard detector with the 180-degree
     ambiguity resolved from the square-colour parity of the 12x9 board.
  4. Map the corners back through the rectification, sub-pixel refine in the original image, and
     accept only if a board-plane homography fits them to < 4 px RMS.
Every path returns the same (ids, px) as OpenCV's CharucoBoard corner numbering (id = row*11+col).
"""
import numpy as np, cv2

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
BOARD = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, DICT)
OBJ = np.asarray(BOARD.getChessboardCorners(), float).reshape(-1, 3)[:, :2]           # metres, id -> (x, y)
OBJ_MM = OBJ * 1000.0
MARKER_MM = {i: np.asarray(BOARD.getObjPoints()[i], float).reshape(-1, 3)[:, :2] * 1000.0 for i in range(len(BOARD.getIds()))}
MARKER_CENTRES = {i: m.mean(0) / 1000.0 for i, m in MARKER_MM.items()}                 # metres (kept for older callers)
OUTLINE_MM = np.array([[0, 0], [720, 0], [720, 540], [0, 540]], float)
RECT_SCALE = 2.0            # px per mm in the rectified view
RECT_MARGIN = 40.0          # mm of surroundings kept around the outline

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
CHARUCO_RECT = cv2.aruco.CharucoDetector(BOARD, detectorParams=detector_params(minMarkerPerimeterRate=0.02, adaptiveThreshWinSizeMax=53))

# ---------------------------------------------------------------- raw detectors
def charuco_detect(gray, refine_scale=3, detector=None):
    """-> (n_corners, px (n,2) or None, ids (n,) or None, markers [(id, quad(4,2)), ...])."""
    det = detector or CHARUCO
    ch_c, ch_ids, mk_c, mk_ids = det.detectBoard(gray)
    if mk_ids is None or len(mk_ids) == 0:
        return 0, None, None, []
    markers = [(int(i), m.reshape(-1, 2)) for i, m in zip(mk_ids.reshape(-1), mk_c)]
    best = (0 if ch_ids is None else len(ch_ids), None if ch_ids is None else ch_c.reshape(-1, 2), None if ch_ids is None else ch_ids.reshape(-1))
    if refine_scale and refine_scale > 1:
        allc = np.concatenate([m for _, m in markers]); x0, y0 = allc.min(0); x1, y1 = allc.max(0)
        pad = 0.35 * max(x1 - x0, y1 - y0) + 20; H, W = gray.shape
        x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad)); x1, y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
        crop = gray[y0:y1, x0:x1]
        if crop.size and max(crop.shape) * refine_scale <= 6000:
            up = cv2.resize(crop, None, fx=refine_scale, fy=refine_scale, interpolation=cv2.INTER_CUBIC)
            c2, i2, m2, mi2 = det.detectBoard(up)
            if i2 is not None and len(i2) > best[0]:
                best = (len(i2), c2.reshape(-1, 2) / refine_scale + np.array([x0, y0], float), i2.reshape(-1))
            if mi2 is not None and len(mi2) > len(markers):
                markers = [(int(i), m.reshape(-1, 2) / refine_scale + np.array([x0, y0], float)) for i, m in zip(mi2.reshape(-1), m2)]
    return best[0], best[1], best[2], markers

def square_black(i, j):
    """Square (column i, row j) of the 12x9 board; (0,0) is black."""
    return (i + j) % 2 == 0

def chessboard_detect(gray, markers=(), scales=(0.5, 1.0, 2.0), fast_check=True):
    """Classic chessboard corners of the 11x8 inner grid on an image where the board is roughly upright.
    -> (px (88,2), ids (88,), note) or None. Orientation from the square-colour parity, checked vs markers."""
    H, W = gray.shape
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | (cv2.CALIB_CB_FAST_CHECK if fast_check else 0)
    found = None
    if max(H, W) > 3000:
        scales = (0.5,)
    elif max(H, W) > 2000:
        scales = (0.5, 1.0)
    for sc in scales:
        img = gray if sc == 1 else cv2.resize(gray, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC if sc > 1 else cv2.INTER_AREA)
        ok, pts = cv2.findChessboardCorners(img, (11, 8), flags)
        if ok:
            found = pts.reshape(-1, 2) / sc
            break
    if found is None:
        return None
    pts = cv2.cornerSubPix(gray, found.reshape(-1, 1, 2).astype(np.float32), (5, 5), (-1, -1),
                           (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)).reshape(-1, 2)
    grid = pts.reshape(8, 11, 2)
    def contrast(orient):
        blk, wht = [], []
        for r in range(7):
            for c in range(10):
                q = (grid[r, c] + grid[r, c + 1] + grid[r + 1, c + 1] + grid[r + 1, c]) / 4.0
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
        Hm, _ = cv2.findHomography(OBJ_MM[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
        if Hm is not None:
            errs = [float(np.linalg.norm(cv2.perspectiveTransform(MARKER_MM[mid].mean(0).reshape(-1, 1, 2), Hm).reshape(2) - quad.mean(0)))
                    for mid, quad in markers if mid in MARKER_MM]
            if errs:
                note += f"; {len(errs)} markers agree within median {np.median(errs):.0f}px"
                if np.median(errs) > 40:
                    return None
    if abs(sA - sB) < 8:
        note += "; WEAK orientation evidence"
        if not markers:
            return None
    return px, ids, note

# ---------------------------------------------------------------- board localisation
def homography_from_markers(markers, min_markers=2):
    """board mm -> image px from decoded marker corners (RANSAC). -> (H, n_inliers) or (None, 0).
    Ids >= 54 are false positives: the dictionary holds 100 codes, the board uses 0-53."""
    markers = [(i, q) for i, q in markers if i in MARKER_MM]
    if len(markers) < min_markers:
        return None, 0
    obj = np.concatenate([MARKER_MM[i] for i, _ in markers]).reshape(-1, 1, 2)
    img = np.concatenate([q for _, q in markers]).reshape(-1, 1, 2)
    if len(obj) < 8:
        return None, 0
    H, mask = cv2.findHomography(obj.astype(np.float32), img.astype(np.float32), cv2.RANSAC, 4.0)
    if H is None:
        return None, 0
    n_in = int(mask.sum())
    return (H if n_in >= 6 else None), n_in

def order_quad(q):
    """4 points -> clockwise starting top-left (in image coordinates)."""
    q = np.asarray(q, float)
    c = q.mean(0)
    ang = np.arctan2(q[:, 1] - c[1], q[:, 0] - c[0])
    q = q[np.argsort(ang)]
    start = int(np.argmin(q[:, 0] + q[:, 1]))
    return np.roll(q, -start, axis=0)

def find_white_quads(gray, min_area=1500, max_area=None, max_candidates=6):
    """Bright convex quadrilaterals (the board's white paper) in a grey crop, largest first."""
    H, W = gray.shape
    max_area = max_area or 0.5 * H * W
    small = 2 if max(H, W) > 1200 else 1                       # the paper is hundreds of px; search at half size
    g = gray if small == 1 else cv2.resize(gray, None, fx=1 / small, fy=1 / small, interpolation=cv2.INTER_AREA)
    blur = cv2.GaussianBlur(g, (5, 5), 0)
    bg = cv2.blur(blur, (151 // small | 1, 151 // small | 1))
    min_area, max_area = min_area / small ** 2, max_area / small ** 2
    quads = []
    for delta in (25, 40):
        mask = ((blur.astype(np.int16) - bg.astype(np.int16)) > delta).astype(np.uint8) * 255
        for k in (5 // small | 1, 15 // small | 1, 31 // small | 1):
            m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
            contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                hull = cv2.convexHull(c); a = cv2.contourArea(hull)
                if a < min_area or a > max_area:
                    continue
                peri = cv2.arcLength(hull, True)
                approx = None
                for eps in (0.02, 0.04, 0.06, 0.09):
                    ap = cv2.approxPolyDP(hull, eps * peri, True)
                    if len(ap) == 4:
                        approx = ap; break
                if approx is None:
                    approx = cv2.boxPoints(cv2.minAreaRect(hull)).reshape(-1, 1, 2)
                q = order_quad(approx.reshape(4, 2))
                if cv2.contourArea(c) / max(1.0, cv2.contourArea(q.astype(np.float32))) < 0.45:
                    continue
                if any(np.linalg.norm(q - p).max() < 0.05 * np.sqrt(a) for _, p in quads):   # duplicate
                    continue
                quads.append((a, q))
    quads.sort(key=lambda t: -t[0])
    return [q * small for _, q in quads[:max_candidates]]

def find_grid_quads(gray, min_points=40, max_candidates=4):
    """Locate the board by its CORNER DENSITY, not by its paper: the checkerboard is the only thing in
    the scene with a dense cluster of X-junctions. Robust where the white margin is broken by shadow,
    grass or an occluder, which is what defeats find_white_quads.
    -> list of 4-point quads (image px), largest cluster first."""
    H, W = gray.shape
    small = 2 if max(H, W) > 1200 else 1
    g = gray if small == 1 else cv2.resize(gray, None, fx=1 / small, fy=1 / small, interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    resp = cv2.cornerMinEigenVal(np.float32(g) / 255.0, 5, 3)          # X-junctions score high
    thr = max(float(np.percentile(resp, 99.5)), 1e-4)
    pts = np.argwhere(resp >= thr)[:, ::-1].astype(np.float32)          # (x, y)
    if len(pts) < min_points:
        return []
    mask = np.zeros(g.shape, np.uint8)
    mask[pts[:, 1].astype(int), pts[:, 0].astype(int)] = 255
    k = max(3, int(round(min(g.shape) / 60)) | 1)
    dil = cv2.dilate(mask, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dil, 8)
    out = []
    for i in range(1, n):
        sel = pts[lab[pts[:, 1].astype(int), pts[:, 0].astype(int)] == i]
        if len(sel) < min_points:
            continue
        rect = cv2.minAreaRect(sel)
        (w_, h_) = rect[1]
        if min(w_, h_) < 12 or max(w_, h_) / max(1.0, min(w_, h_)) > 6:
            continue
        hull = cv2.convexHull(sel.reshape(-1, 1, 2).astype(np.float32))   # a perspective board is a trapezoid,
        peri = cv2.arcLength(hull, True); quad = None                      # so minAreaRect distorts the mapping
        for eps in (0.02, 0.04, 0.06, 0.09, 0.13):
            ap = cv2.approxPolyDP(hull, eps * peri, True)
            if len(ap) == 4:
                quad = ap.reshape(4, 2); break
        if quad is None:
            quad = cv2.boxPoints(rect)
        out.append((len(sel), order_quad(quad) * small))
    out.sort(key=lambda t: -t[0])
    return [q for _, q in out[:max_candidates]]

def homographies_from_quad(quad, all_rotations=True):
    """Board-mm -> px homographies for a quad. All four corner rotations are tried by default: under
    strong foreshortening the board's 720 mm side can be the SHORTER one in the image, so picking the
    long image side is not safe (it produced a 4:3-stretched rectification that decoded as nothing)."""
    q = order_quad(quad)
    s01 = np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[3] - q[2]); s12 = np.linalg.norm(q[2] - q[1]) + np.linalg.norm(q[0] - q[3])
    if s01 < s12:                                          # long image side first - most likely, tried first
        q = np.roll(q, -1, axis=0)
    rolls = (0, 2, 1, 3) if all_rotations else (0, 2)
    out = []
    for r in rolls:
        qq = np.roll(q, r, axis=0)
        H, _ = cv2.findHomography(OUTLINE_MM.reshape(-1, 1, 2).astype(np.float32), qq.reshape(-1, 1, 2).astype(np.float32), 0)
        if H is not None:
            out.append(H)
    return out

# ---------------------------------------------------------------- rectified decoding
def rectify(gray, H_mm2px):
    """Warp the board to a frontal view. -> (rect image, M_rect2img 3x3)."""
    s, m = RECT_SCALE, RECT_MARGIN
    T = np.array([[1 / s, 0, -m], [0, 1 / s, -m], [0, 0, 1]], float)          # rect px -> mm (margin included)
    M_rect2img = H_mm2px @ T
    Wr, Hr = int((720 + 2 * m) * s), int((540 + 2 * m) * s)
    rect = cv2.warpPerspective(gray, np.linalg.inv(M_rect2img), (Wr, Hr), flags=cv2.INTER_CUBIC)
    return rect, M_rect2img

def _finish(gray, px_img, ids, note, method):
    """Sub-pixel refine in the original image and validate with a board-plane homography."""
    Hm, _ = cv2.findHomography(OBJ_MM[ids].reshape(-1, 1, 2), px_img.reshape(-1, 1, 2), 0)
    if Hm is None:
        return None
    # square size in the image -> refinement window
    a, b, c = cv2.perspectiveTransform(np.array([[[360, 270]], [[420, 270]], [[360, 330]]], float), Hm).reshape(-1, 2)
    sq = float(min(np.linalg.norm(a - b), np.linalg.norm(a - c)))
    win = int(np.clip(sq / 4, 2, 9))
    H_, W_ = gray.shape
    inside = (px_img[:, 0] > win + 1) & (px_img[:, 1] > win + 1) & (px_img[:, 0] < W_ - win - 2) & (px_img[:, 1] < H_ - win - 2)
    px_ref = px_img.copy()
    if inside.any():
        px_ref[inside] = cv2.cornerSubPix(gray, px_img[inside].reshape(-1, 1, 2).astype(np.float32), (win, win), (-1, -1),
                                          (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.02)).reshape(-1, 2)
    moved = np.linalg.norm(px_ref - px_img, axis=1)
    px_ref[moved > max(2.0, sq / 3)] = px_img[moved > max(2.0, sq / 3)]                    # refinement ran off -> keep the mapped point
    Hm2, _ = cv2.findHomography(OBJ_MM[ids].reshape(-1, 1, 2), px_ref.reshape(-1, 1, 2), 0)
    if Hm2 is None:
        return None
    res = np.linalg.norm(cv2.perspectiveTransform(OBJ_MM[ids].reshape(-1, 1, 2), Hm2).reshape(-1, 2) - px_ref, axis=1)
    rms = float(np.sqrt(np.mean(res ** 2)))
    if rms > 4.0:
        return None
    keep = res < 3 * max(1.0, rms)
    return method, px_ref[keep], ids[keep], note + f"; {keep.sum()} corners, plane rms {rms:.2f}px, square {sq:.0f}px", None, None

DEBUG_DIR = None            # set to a directory to dump every rectified view (debug_<tag>.jpg)

def refine_homography(gray, H_mm2px, rounds=2):
    """Re-estimate the board->image homography from markers decoded in the rectified view.
    A homography from a few clustered markers extrapolates badly across the board; one or two
    rectify-and-redetect rounds pull the whole board into the frame."""
    for _ in range(rounds):
        rect, M = rectify(gray, H_mm2px)
        _, _, _, mk = charuco_detect(rect, refine_scale=0, detector=CHARUCO_RECT)
        mk = [(i, q) for i, q in mk if i in MARKER_MM]
        if len(mk) < 4:
            return H_mm2px
        img_pts = np.concatenate([cv2.perspectiveTransform(q.reshape(-1, 1, 2), M).reshape(-1, 2) for _, q in mk])
        obj_pts = np.concatenate([MARKER_MM[i] for i, _ in mk])
        if len(obj_pts) != len(img_pts) or len(obj_pts) < 8:
            return H_mm2px
        H2, mask = cv2.findHomography(obj_pts.reshape(-1, 1, 2).astype(np.float32), img_pts.reshape(-1, 1, 2).astype(np.float32), cv2.RANSAC, 4.0)
        if H2 is None or mask.sum() < 8:
            return H_mm2px
        H_mm2px = H2
    return H_mm2px

def marker_observations(gray, H_mm2px):
    """Marker corners measured in the rectified view, mapped back: (mk_ids (n,), mk_px (n,4,2), rms).
    These are REAL measurements with known board-mm coordinates - the fallback when the chessboard
    corners cannot be found at all (washed-out frames erode the black squares until they no longer
    touch at the corners, which is exactly what the saddle-point detectors need)."""
    rect, M = rectify(gray, H_mm2px)
    _, _, _, mk = charuco_detect(rect, refine_scale=0, detector=CHARUCO_RECT)
    mk = [(i, q) for i, q in mk if i in MARKER_MM]
    if len(mk) < 4:
        return None
    ids = np.array([i for i, _ in mk], int)
    px = np.stack([cv2.perspectiveTransform(q.reshape(-1, 1, 2), M).reshape(4, 2) for _, q in mk])
    obj = np.concatenate([MARKER_MM[i] for i in ids]).reshape(-1, 1, 2).astype(np.float32)
    H2, mask = cv2.findHomography(obj, px.reshape(-1, 1, 2).astype(np.float32), cv2.RANSAC, 3.0)
    if H2 is None or mask.sum() < 12:
        return None
    res = np.linalg.norm(cv2.perspectiveTransform(obj, H2).reshape(-1, 2) - px.reshape(-1, 2), axis=1)
    return ids, px, float(np.sqrt(np.mean(res ** 2))), H2

def decode_rectified(gray, H_mm2px, tag, refine=True, allow_markers_only=True):
    if refine:
        H_mm2px = refine_homography(gray, H_mm2px)
    rect, M = rectify(gray, H_mm2px)
    if DEBUG_DIR:
        import re as _re
        cv2.imwrite(str(DEBUG_DIR / ("debug_" + _re.sub(r"[^A-Za-z0-9]+", "_", tag)[:60] + ".jpg")), rect)
    nc, cpx, cids, markers = charuco_detect(rect, refine_scale=0, detector=CHARUCO_RECT)
    if nc >= 12:
        px_img = cv2.perspectiveTransform(cpx.reshape(-1, 1, 2), M).reshape(-1, 2)
        r = _finish(gray, px_img, cids.astype(int), f"{tag}: rectified charuco {len(markers)} markers", "rect-charuco")
        if r is not None:
            return r
    res = chessboard_detect(rect, markers, scales=(0.5, 1.0), fast_check=False)
    if res is not None:
        px, ids, note = res
        px_img = cv2.perspectiveTransform(px.reshape(-1, 1, 2), M).reshape(-1, 2)
        r = _finish(gray, px_img, ids.astype(int), f"{tag}: rectified {note}", "rect-chess")
        if r is not None:
            return r
    if allow_markers_only:                       # no chessboard corners: keep the marker corners themselves
        mo = marker_observations(gray, H_mm2px)
        if mo is not None and len(mo[0]) >= 6 and mo[2] <= 3.0:
            mk_ids, mk_px, rms, H2 = mo
            ch_px = cv2.perspectiveTransform(OBJ_MM.reshape(-1, 1, 2), H2).reshape(-1, 2)
            ch_ids = np.arange(88)
            vis = visible_corners(gray, H2)
            return ("rect-markers", ch_px[vis], ch_ids[vis],
                    f"{tag}: {len(mk_ids)} markers only ({4 * len(mk_ids)} measured corners, rms {rms:.2f}px) -> "
                    f"{int(vis.sum())}/88 chessboard corners PREDICTED from the marker homography (occluded ones dropped)",
                    mk_ids, mk_px)
    return None

def visible_corners(gray, H_mm2px, min_contrast=12.0):
    """Which of the 88 corners are actually visible: the four squares meeting at the corner must show
    the expected black/white parity. Drops corners that fall on an occluder (house roof, pole, hand)."""
    H_, W_ = gray.shape
    ok = np.zeros(88, bool)
    # corner id k (row r=k//11, col c=k%11) sits between squares (c, r), (c+1, r), (c, r+1), (c+1, r+1)
    for k in range(88):
        r, c = divmod(k, 11)
        cen_mm, want = [], []
        for dc in (0, 1):
            for dr in (0, 1):
                i, j = c + dc, r + dr
                cen_mm.append([i * 60 + 30, j * 60 + 30]); want.append(square_black(i, j))
        pts = cv2.perspectiveTransform(np.array(cen_mm, float).reshape(-1, 1, 2), H_mm2px).reshape(-1, 2)
        vals = []
        for (x, y) in pts:
            xi, yi = int(round(x)), int(round(y))
            if not (1 <= xi < W_ - 1 and 1 <= yi < H_ - 1):
                vals = None; break
            vals.append(float(gray[yi - 1:yi + 2, xi - 1:xi + 2].mean()))
        if vals is None:
            continue
        blk = [v for v, w in zip(vals, want) if w]; wht = [v for v, w in zip(vals, want) if not w]
        if blk and wht and (np.mean(wht) - np.mean(blk)) >= min_contrast:
            ok[k] = True
    return ok

def detect(gray, markers_min=12, quad_hint=None, area_hint=None):
    """Full pipeline on one (cropped) grey image.
    -> (method, px, ids, note, mk_ids, mk_px, quad)
    method 'located' means the BOARD WAS FOUND BUT THE GRID DID NOT DECODE: px/ids are empty and `quad`
    holds the four outline points. Localisation is kept even when decoding fails - a board that is
    visibly there must never disappear from the output just because its code is unreadable (operator
    rule 2026-09-21). method None means the board was not found at all.
    mk_ids/mk_px are the measured marker corners when the corners had to be predicted from them.
    quad_hint: 4 image points of the board outline (manual clicks); area_hint: expected board area in px^2."""
    def outline_of(px_, ids_):
        Hm, _ = cv2.findHomography(OBJ_MM[ids_].reshape(-1, 1, 2), np.asarray(px_, float).reshape(-1, 1, 2), 0)
        return None if Hm is None else cv2.perspectiveTransform(OUTLINE_MM.reshape(-1, 1, 2), Hm).reshape(-1, 2)
    def done(r):
        return (*r, outline_of(r[1], r[2]))
    nc, px, ids, markers = charuco_detect(gray)
    if nc >= 60:
        return "charuco", px, ids, f"{len(markers)} markers, {nc} corners", None, None, outline_of(px, ids)
    tried = []; located = None
    H, n_in = homography_from_markers(markers)
    if H is not None:
        located = cv2.perspectiveTransform(OUTLINE_MM.reshape(-1, 1, 2), refine_homography(gray, H)).reshape(-1, 2)
        r = decode_rectified(gray, H, f"{len(markers)} markers ({n_in} inlier corners)")
        if r and len(r[2]) > max(nc, 11):
            return done(r)
        tried.append(f"markers({len(markers)})")
    if nc >= markers_min:
        return "charuco", px, ids, f"{len(markers)} markers, {nc} corners (rectified path did not add corners)", None, None, outline_of(px, ids)
    if quad_hint is not None:
        located = np.asarray(quad_hint, float)
        for H in homographies_from_quad(quad_hint):
            r = decode_rectified(gray, H, "manual quad")
            if r: return done(r)
        tried.append("manual quad")
    gquads = find_grid_quads(gray, max_candidates=2)     # corner-density cluster: survives a broken white margin
    for k, q in enumerate(gquads):
        if located is None and k == 0:
            located = np.asarray(q, float)
        for pad in (1.09,):                              # the cluster spans the INNER grid; 660x480 mm -> outline 720x540
            for H in homographies_from_quad(q * pad - (pad - 1) * q.mean(0)):
                r = decode_rectified(gray, H, f"grid cluster #{k + 1} of {len(gquads)} pad {pad}")
                if r: return done(r)
    if gquads:
        tried.append(f"grid clusters({len(gquads)})")
    lo = (0.3 * area_hint) if area_hint else 1500
    hi = (4.0 * area_hint) if area_hint else None
    quads = find_white_quads(gray, min_area=lo, max_area=hi)
    for k, q in enumerate(quads):
        for H in homographies_from_quad(q):
            r = decode_rectified(gray, H, f"white quad #{k + 1} of {len(quads)}")
            if r: return done(r)
    if quads:
        tried.append(f"white quads({len(quads)})")
    res = chessboard_detect(gray, markers)
    if res is not None:
        px2, ids2, note = res
        return "chessboard", px2, ids2, note + f" ({len(markers)} markers decoded)", None, None, outline_of(px2, ids2)
    note = f"only {nc} corners, {len(markers)} markers; tried " + (", ".join(tried) or "nothing else")
    if located is not None and plausible_board_quad(gray, located):
        return "located", np.zeros((0, 2)), np.zeros(0, int), "BOARD LOCATED, GRID NOT DECODED - " + note, None, None, located
    return None, px, ids, note, None, None, None

def plausible_board_quad(gray, quad, min_side=20, aspect=(1.05, 5.0), min_bright=6.0):
    """Cheap sanity check on a 'located but not decoded' quad: board-like shape, and brighter inside than
    around it (the board is white paper). Keeps grass texture and dark clutter out; a white house corner
    can still pass, which is why 'located' is review-only and never counts as a measurement."""
    q = np.asarray(quad, float)
    if q.shape != (4, 2) or not np.isfinite(q).all():
        return False
    sides = [float(np.linalg.norm(q[(i + 1) % 4] - q[i])) for i in range(4)]
    if min(sides) < min_side:
        return False
    a, b = (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2
    r = max(a, b) / max(1.0, min(a, b))
    if not (aspect[0] <= r <= aspect[1]):
        return False
    H_, W_ = gray.shape
    inner = np.zeros((H_, W_), np.uint8)
    cv2.fillConvexPoly(inner, q.astype(np.int32), 255)
    if inner.sum() < 255 * 200:
        return False
    k = max(5, int(0.25 * min(a, b)) | 1)
    outer = cv2.dilate(inner, np.ones((k, k), np.uint8)) - inner
    return float(gray[inner > 0].mean() - gray[outer > 0].mean()) >= min_bright
