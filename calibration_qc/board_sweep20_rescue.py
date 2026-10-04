# -*- coding: utf-8 -*-
r"""Rescue the sweep frames another camera could not decode, with the sweep camera's simultaneous board pose as the
locator (detect-then-decode: locate first, decode second).

Why: during the 2026-09-18 CH03 sweep CH01 decoded 408 of 841 searched frames; classified with CH03's simultaneous
pose, 132 of the rest are edge-on to CH01 (> 65 deg), 120 reach past the canvas edge, and 70 are in view, facing
CH01 (tilt ~46 deg) and inside the crop, yet not decoded: the oblique view squashes the 4.5 cm markers. Here the
sweep camera's board pose (IPPE on its own corners, bundle frame; clock offset applied) predicts the 88 corners in
the target camera. Better than the sweep camera's pose itself (which is off in the panos by 25-57 px: its range
scale disagrees with theirs by 2-6 %) is the target's OWN pose from its nearest decoded frame (within 1.5 s), carried
to the frame by the board's rigid motion as the sweep camera measured it between the two times - a relative motion,
nearly free of that scale error. The panorama around the board is remapped into a virtual pinhole looking at it (so the board is
an exact perspective view), board_detect.decode_rectified decodes it in a frontal warp from the predicted
homography (refined on the markers it finds), and the decoded corners are mapped back to the target's upright
pixels. The prior only says WHERE to look; every stored corner is measured in the target image (method
rect-charuco / rect-chess), except "rect-markers", whose corners are predicted from the target's own decoded markers.

Revision 2026-10-02 evening (the operator, on the failure videos: the boards are clear, the outline is beside them):
the decoder's rectified view keeps only 40 mm around the predicted pattern, so a prior that is off by more than that
cuts the board and nothing decodes. Now (1) the fallback prior is corrected by the systematic offset measured on this
camera's own decoded frames nearby (median rotation of the five nearest), and (2) the board is located before it is
decoded: markers decoded anywhere in the virtual view (ChArUco), then the board found by matching the rendered plate
(the real pattern, at six scales 0.9-1.2) within 350 px of the prior, and the white plate's own silhouette near the prior (corners labelled
by the prior's shape); around each of these the markers are first looked for in a wide rectified view (250 mm
kept around the pattern) and the board re-located from them and decoded there with the full decoder (ChArUco, then
chessboard parity: far boards have markers too small to read but sharp corners), then the prior itself; marker-only
corners last, and those refined to the image's own saddle points where the four squares show (method
rect-refined: a hand-held plate is partly under a hand, and OpenCV's chessboard search needs the whole grid). The
refinement trusts its starting homography's registration to within one square - a slip by an EVEN number of squares
keeps the black/white parity and puts every predicted corner on a real saddle, so it would pass every check with every
id wrong (seen in validation on CH04/CH01 at the canvas corner, from a template match 4-9 squares off) - so it starts
only from the markers' homography (the decoded ids register the board) or from a tracked prior (an own pose <= 0.5 s
away), and its corners must land within 30 mm of that prior. A decode must land within 250 mm of the prior. Frames an earlier run
rescued are kept (--fresh to redo all).
Tracking (same evening): every frame rescued with >= 20 measured corners becomes one of this camera's own poses, so
the next frames start from it (the prior is the nearest own pose within 1.5 s, moved by the sweep camera's measured
motion); up to three passes, each retrying only the frames that now have a nearer own pose. --clicks <manual_quads
.json> (board_sweep20_click_gui.py): the operator's four plate corners give that frame's own pose (which click is which
corner is read off the prediction's shape) - or three, for a plate with one corner cut off (verdict "partial"; which
corner is missing is read off the prediction too, the pose by P3P, the solution nearest the prediction); frames the
operator marked not visible, or partial without corners, are not tried. --validate N:
the refinement checked against the decoder on N frames this camera decoded itself (their own pose hidden).

Usage: python board_sweep20_rescue.py --window CH03 --main CH03 --cam CH01 --offset 0.52 [--ir-shift-main 0.6,-5.6] [--fresh]
                                      [--max-tilt 85] [--min-inside 0.5] [--clicks <manual_quads.json>]
                                      [--debug-dir <dir> --frames a:b] [--validate N]
Output: <qc>\sweep20\<WINDOW>_<CAM>_rescue.json  {frames: [[i, method, n, ids, px, how located], ...]}
"""
import sys, json, time
from pathlib import Path
import numpy as np, cv2
from scipy.ndimage import map_coordinates
from scipy.spatial.transform import Rotation as Rot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, board_detect as bd                    # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
WINDOW, MAIN, CAM = opt("--window"), opt("--main"), opt("--cam")
OFFSET = float(opt("--offset", "0"))
IR_MAIN = np.array([float(v) for v in opt("--ir-shift-main", "0,0").split(",")])
MAX_TILT = float(opt("--max-tilt", "85"))                                 # deg; the failure videos call > 65 edge-on
MIN_INSIDE = float(opt("--min-inside", "0.5"))                            # share of the predicted corners inside the frame
SESSION, _ = qc_paths.resolve(opt("--session"))
SW = qc_paths.QC_ROOT / "sweep20"
cams = pm.load(correct=False)
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]                 # board corners about the board centre, mm
PANO = CAM in ("CH01", "CH02")


def regular_times(t_abs):
    i = np.arange(len(t_abs)); b = np.polyfit(i, t_abs, 1)[0]; r = t_abs - b * i
    med = np.array([np.median(r[max(0, j - 200):j + 201]) for j in range(0, len(r), 20)])
    return np.interp(i, np.arange(0, len(r), 20), med) + b * i


def board_pose(cam, ids, px):
    """IPPE in a virtual pinhole along the board's mean ray -> (R board->bundle, board centre in the bundle frame)."""
    return pose_from(cam, OBJ3[ids], px)


def pose_from(cam, obj3, px):
    """the same for any points of the board plane (obj3: board mm about the pattern centre, z = 0)."""
    c = cams[cam]; b = pm.fm.bearings(c.model, c.intr, np.asarray(px, float)); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = np.asarray(obj3, float)[:, :2].astype(np.float64); P = np.c_[P, np.zeros(len(P))]
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    if not n:
        return None
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    Rc = Q.T @ cv2.Rodrigues(rv)[0]; Xc = Q.T @ tv.ravel()
    return c.R.T @ Rc, c.R.T @ (Xc - c.tvec)


def load(window, cam):
    d = json.loads((SW / f"{window}_{cam}.json").read_text(encoding="utf-8"))
    return d, regular_times(np.array([f[2] for f in d["frames"]]))


dm, tm = load(WINDOW, MAIN)
poses = []
for f, t in zip(dm["frames"], tm):
    if f[3] >= 20:
        r = board_pose(MAIN, np.asarray(f[4], int), np.asarray(f[5], float) + IR_MAIN)
        if r is not None:
            poses.append((t, r))
TP = np.array([p[0] for p in poses])
dc, tc = load(WINDOW, CAM)
tc = tc + OFFSET
c = cams[CAM]
TF = {f[0]: t for f, t in zip(dc["frames"], tc)}                          # frame -> time (sweep camera's clock)
PLATE3 = np.c_[bd.PAPER_MM - bd.OBJ_MM.mean(0), np.zeros(4)]
MEASURED = ("charuco", "rect-charuco", "rect-chess", "rect-refined")
OUTF = SW / f"{WINDOW}_{CAM}_rescue.json"
old = json.loads(OUTF.read_text(encoding="utf-8"))["frames"] if OUTF.exists() and "--fresh" not in args else []


def main_pose_at(t):
    j = int(np.argmin(np.abs(TP - t)))
    return poses[j][1] if abs(TP[j] - t) <= 0.05 else None


def kabsch_rot(a, b):
    """rotation R with R a_i ~ b_i (rows are unit vectors)."""
    U, _, Vt = np.linalg.svd(a.T @ b); d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


# This camera's own board poses - decoded (>= 20 corners), rescued by an earlier run, rescued in this run, clicked
# by the operator - each a better prior for the frames around it than the sweep camera's pose (tracking).
own = {}
CORR = {}                    # frame -> the rotation taking the sweep camera's predicted rays to the observed ones


def add_own(i, ids, px):
    t = TF[i]
    own[i] = (t, board_pose(CAM, ids, px))
    if main_pose_at(t) is not None:
        R, X = main_pose_at(t)
        a = (OBJ3[ids] @ R.T + X) @ c.R.T + c.tvec; a /= np.linalg.norm(a, axis=1, keepdims=True)
        CORR[i] = (t, Rot.from_matrix(kabsch_rot(a, pm.fm.bearings(c.model, c.intr, px))).as_rotvec())


for f in dc["frames"]:
    if f[3] >= 20:
        add_own(f[0], np.asarray(f[4], int), np.asarray(f[5], float))
for r in old:
    if r[1] in MEASURED and r[2] >= 20:
        add_own(r[0], np.asarray(r[3], int), np.asarray(r[4], float))


def corr_at(t):
    if not CORR:
        return np.eye(3)
    T_ = np.array([v[0] for v in CORR.values()]); R_ = np.array([v[1] for v in CORR.values()])
    k = np.argsort(np.abs(T_ - t))[:5]
    return Rot.from_rotvec(np.median(R_[k], 0)).as_matrix()


# The operator's four plate corners (board_sweep20_click_gui.py export): which click is which plate corner is read
# off the sweep camera's prediction (the labelling, either direction around the plate, whose shape matches it best).
CLICKED, SKIPPED = {}, set()
if opt("--clicks"):
    for j in json.loads(Path(opt("--clicks")).read_text(encoding="utf-8")):
        if j.get("window") != WINDOW or j.get("cam") != CAM:
            continue
        q = np.asarray(j.get("quad") or [], float).reshape(-1, 2)
        if (len(q) == 4 and not j.get("skip")) or (len(q) == 3 and j.get("verdict") == "partial"):
            q = q / float(j.get("scale", 1.0)) + np.asarray(j["off"], float)
            Wc, Hc = (7680, 2160) if PANO else qc_paths.upright_size(SESSION, CAM)
            at_edge = (q[:, 0] < 3) | (q[:, 1] < 3) | (q[:, 0] > Wc - 4) | (q[:, 1] > Hc - 4)
            q = q[~at_edge]                  # a click ON the canvas edge marks where the plate leaves the image, not
            if len(q) >= 3:                  # its corner; dropping one of four leaves three in order around the plate
                CLICKED[int(j["frame"])] = q
        elif j.get("skip"):
            SKIPPED.add(int(j["frame"]))
def pose_p3p(obj3, px, P_prior):
    """the board pose from three plate corners (P3P, up to four solutions): the one whose plate lies nearest the
    prior's (P_prior: the predicted plate corners in the field, mm)."""
    b = pm.fm.bearings(c.model, c.intr, np.asarray(px, float)); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    n, rvs, tvs = cv2.solveP3P(np.asarray(obj3, np.float64), uv, np.eye(3), None, flags=cv2.SOLVEPNP_P3P)
    best = None
    for rv, tv in zip(rvs[:n], tvs[:n]):
        Rf = c.R.T @ (Q.T @ cv2.Rodrigues(rv)[0]); Xf = c.R.T @ (Q.T @ tv.ravel() - c.tvec)
        d = np.linalg.norm((PLATE3 @ Rf.T + Xf) - P_prior, axis=1).mean()
        if best is None or d < best[0]:
            best = (d, (Rf, Xf))
    return None if best is None else best[1]


for i, q in CLICKED.items():
    if main_pose_at(TF[i]) is None:
        continue
    R, X = main_pose_at(TF[i])
    Pc = ((PLATE3 @ R.T + X) @ c.R.T + c.tvec) @ corr_at(TF[i]).T          # predicted plate, camera frame
    pp = pm.fm.project(c.model, c.intr, Pc)
    if len(q) == 4:                    # which click is which plate corner: the labelling whose shape matches best
        cands = [(np.roll(q, k, axis=0), np.arange(4)) for k in range(4)] + [(np.roll(q[::-1], k, axis=0), np.arange(4)) for k in range(4)]
    else:                              # three corners in order around the plate: which one is missing, which direction
        cands = [(np.roll(qq, r, axis=0), np.array([(m + 1) % 4, (m + 2) % 4, (m + 3) % 4]))   # any start, either way
                 for m in range(4) for qq in (q, q[::-1]) for r in range(3)]
    qq, idx = min(cands, key=lambda ci: np.linalg.norm((ci[0] - ci[0].mean(0)) - (pp[ci[1]] - pp[ci[1]].mean(0)), axis=1).sum())
    if len(q) == 4:
        own[i] = (TF[i], pose_from(CAM, PLATE3, qq))
    else:
        pz = pose_p3p(PLATE3[idx], qq, (Pc - c.tvec) @ c.R)
        if pz is not None:
            own[i] = (TF[i], pz)
Wd, Hd = (7680, 2160) if PANO else qc_paths.upright_size(SESSION, CAM)


def prior_at(i):
    """predicted corners (camera frame, mm) for frame i and where they come from: the nearest own pose within 1.5 s
    moved by the sweep camera's measured motion, else the sweep camera's pose corrected by the local offset."""
    t = TF[i]; R, X = main_pose_at(t)
    if own:
        ks = list(own); T_ = np.array([own[k][0] for k in ks]); j = int(np.argmin(np.abs(T_ - t)))
        if abs(T_[j] - t) <= 1.5 and main_pose_at(T_[j]) is not None:
            R0, X0 = main_pose_at(T_[j]); Rp0, Xp0 = own[ks[j]][1]
            Wp = (OBJ3 @ Rp0.T + Xp0 - X0) @ (R @ R0.T).T + X
            how = ("clicked" if ks[j] in CLICKED else "own") + f" {T_[j] - t:+.2f} s"
            return Wp @ c.R.T + c.tvec, how, ks[j], abs(T_[j] - t)
    return ((OBJ3 @ R.T + X) @ c.R.T + c.tvec) @ corr_at(t).T, "corrected", None, None


todo = set()
for f, t in zip(dc["frames"], tc):
    if f[3] >= 12 or main_pose_at(t) is None or f[0] in SKIPPED:
        continue
    R, X = main_pose_at(t)
    los = X - c.centre; los /= np.linalg.norm(los)
    pr = pm.fm.project(c.model, c.intr, (OBJ3 @ R.T + X) @ c.R.T + c.tvec)
    inside = ((pr[:, 0] >= 0) & (pr[:, 0] < Wd) & (pr[:, 1] >= 0) & (pr[:, 1] < Hd)).mean()
    if f[0] in CLICKED or (np.degrees(np.arccos(abs(los @ R[:, 2]))) <= MAX_TILT and inside >= MIN_INSIDE):
        todo.add(f[0])
DEBUG = opt("--debug-dir")                                               # diagnosis: these frames only, images, no file
if DEBUG:
    lo, hi = (int(v) for v in opt("--frames").split(":"))
    todo = {k for k in todo if lo <= k <= hi}
    Path(DEBUG).mkdir(parents=True, exist_ok=True)
todo -= {r[0] for r in old}
print(f"{WINDOW}/{CAM}: {len(todo)} frames to rescue ({len(old)} kept from the earlier run, {len(own)} own poses, "
      f"{len(CLICKED)} clicked, {len(SKIPPED)} marked not visible by the operator)", flush=True)


def virtual_view(gray, Pc):
    """pinhole view looking at the predicted board: (image, map virtual px -> target px, f, size, Q)."""
    m = Pc.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([m], [[0, 0, 1]])[0].as_matrix()                  # virtual -> camera
    v = Pc @ Q                                                              # camera -> virtual (rows)
    xy = v[:, :2] / v[:, 2:]
    size = 1400; f = 500.0 / max(np.ptp(xy, 0).max(), 1e-3)            # the board ~500 px: room for a prior 100s of px off
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    rays = np.stack([(xx - size / 2) / f, (yy - size / 2) / f, np.ones_like(xx)], -1).reshape(-1, 3) @ Q.T
    uv = pm.fm.project(c.model, c.intr, rays * 1000.0).reshape(size, size, 2).astype(np.float32)
    img = cv2.remap(gray, uv[..., 0], uv[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    pred_v = xy * f + size / 2
    return img, uv, pred_v


def shifted(H, dx, dy):
    """the same board moved by (dx, dy) mm in its own plane."""
    return H @ np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], float)


def plausible(r, H0):
    """the decoded corners must sit within 250 mm of where the prior put them (one board in view)."""
    mm = cv2.perspectiveTransform(np.asarray(r[1], float).reshape(-1, 1, 2), np.linalg.inv(H0)).reshape(-1, 2)
    return float(np.median(np.linalg.norm(mm - bd.OBJ_MM[np.asarray(r[2], int)], axis=1))) < 250.0


def quick_charuco(vimg, H, tag):
    """the cheap path of decode_rectified: refine on markers, rectify, ChArUco, sub-pixel check (no chessboard)."""
    H = bd.refine_homography(vimg, H)
    rect, M = bd.rectify(vimg, H)
    nc, cpx, cids, _mk = bd.charuco_detect(rect, refine_scale=0, detector=bd.CHARUCO_RECT)
    if nc < 12:
        return None
    px = cv2.perspectiveTransform(cpx.reshape(-1, 1, 2), M).reshape(-1, 2)
    return bd._finish(vimg, px, cids.astype(int), f"{tag}: rectified charuco", "rect-charuco")


PLATE_IMG = cv2.copyMakeBorder(bd.BOARD.generateImage((720, 540), marginSize=0), 30, 30, 40, 40, cv2.BORDER_CONSTANT,
                               value=255).astype(np.float32)             # the printed plate, 1 px per mm, pattern at (40, 30)
T_PLATE = np.array([[1, 0, -40], [0, 1, -30], [0, 0, 1]], float)        # plate px -> pattern mm


def template_locate(vimg, H0, search=350, blur=4.0):
    """where the board really is, near the prior: the printed plate (real markers) rendered with the prior's
    homography at six scales (the prior's range is off by up to ~15 %), matched (normalised cross-correlation, both
    blurred to forgive the prior's scale and tilt) within +-search px. -> candidates, best first:
    [(homography moved to the match, score, shift px, scale), ...] (the best per scale)."""
    S = cv2.GaussianBlur(vimg.astype(np.float32), (0, 0), blur)
    cands = []
    c0 = cv2.perspectiveTransform(np.array([[[360.0, 270.0]]]), H0).reshape(2)
    for sc in (0.9, 0.96, 1.02, 1.08, 1.14, 1.2):
        A = np.array([[sc, 0, (1 - sc) * c0[0]], [0, sc, (1 - sc) * c0[1]], [0, 0, 1]], float)   # scale about the centre
        Hs = A @ H0
        W = Hs @ T_PLATE
        tpl = cv2.warpPerspective(PLATE_IMG, W, vimg.shape[::-1], flags=cv2.INTER_AREA, borderValue=-1)
        mask = tpl >= 0
        ys, xs = np.nonzero(mask)
        if len(xs) < 1000:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        t = tpl[y0:y1, x0:x1].copy(); m = mask[y0:y1, x0:x1]
        t[~m] = t[m].mean()
        t = cv2.GaussianBlur(t, (0, 0), blur)
        sx0, sy0 = max(0, x0 - search), max(0, y0 - search)
        sx1, sy1 = min(S.shape[1], x1 + search), min(S.shape[0], y1 + search)
        if sx1 - sx0 < t.shape[1] or sy1 - sy0 < t.shape[0]:
            continue
        R = cv2.matchTemplate(S[sy0:sy1, sx0:sx1], t, cv2.TM_CCOEFF_NORMED)
        _, v, _, loc = cv2.minMaxLoc(R)
        dx, dy = sx0 + loc[0] - x0, sy0 + loc[1] - y0
        cands.append((np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], float) @ Hs, float(v), (int(dx), int(dy)), sc))
    cands.sort(key=lambda c: -c[1])
    out = []
    for c in cands:                                                      # distinct places only
        if all(np.hypot(c[2][0] - o[2][0], c[2][1] - o[2][1]) > 20 for o in out):
            out.append(c)
    return out


def plate_locate(vimg, H0, reach=450):
    """the white plate's own silhouette (a bright convex quad, board_detect.find_white_quads) near the prior, with
    its corners labelled by the prior's: the cyclic order that best matches the predicted plate's shape once both
    are centred. Unlike the rendered pattern it does not care how far the prior's tilt and range are off.
    -> [(homography, note)], nearest quad first."""
    P = cv2.perspectiveTransform(bd.PAPER_MM.reshape(-1, 1, 2), H0).reshape(-1, 2)
    area = cv2.contourArea(P.astype(np.float32))
    out = []
    quads = bd.find_white_quads(vimg, min_area=0.25 * area, max_area=4.0 * area, max_candidates=8)
    quads = sorted(quads, key=lambda q: np.linalg.norm(q.mean(0) - P.mean(0)))
    for q in quads[:2]:
        if np.linalg.norm(q.mean(0) - P.mean(0)) > reach:
            continue
        q = bd.order_quad(q)
        best = min((np.roll(q, k, axis=0) for k in range(4)),
                   key=lambda qq: np.linalg.norm((qq - qq.mean(0)) - (P - P.mean(0)), axis=1).sum())
        H, _ = cv2.findHomography(bd.PAPER_MM.reshape(-1, 1, 2).astype(np.float32), best.reshape(-1, 1, 2).astype(np.float32), 0)
        if H is not None:
            d = best.mean(0) - P.mean(0)
            out.append((H, f"plate {d[0]:+.0f},{d[1]:+.0f} px"))
    return out


def wide_markers(vimg, H, margin=250.0, scale=2.0):
    """markers found in a WIDE rectified view around a hypothesis (250 mm kept around the pattern instead of the
    decoder's 40 mm, so a hypothesis 100-200 mm off still holds the whole board) -> board homography from them."""
    M = H @ np.array([[1 / scale, 0, -margin], [0, 1 / scale, -margin], [0, 0, 1]], float)
    size = (int((720 + 2 * margin) * scale), int((540 + 2 * margin) * scale))
    rect = cv2.warpPerspective(vimg, np.linalg.inv(M), size, flags=cv2.INTER_CUBIC)
    _, _, _, mk = bd.charuco_detect(rect, refine_scale=0, detector=bd.CHARUCO_RECT)
    mk = [(i, cv2.perspectiveTransform(q.reshape(-1, 1, 2).astype(np.float64), M).reshape(-1, 2)) for i, q in mk]
    return bd.homography_from_markers(mk)[0]


def refine_from_H(vimg, H, note=""):
    """measured corners from a board homography that is already close (markers, or a prior / template within a few
    px): each corner whose four squares show the board's black/white parity (so it is not under the operator's hand
    or washed out against a bright wall) is moved to the image's own saddle point (cornerSubPix, a quarter-square
    window); a corner is kept only if it converged within a third of a square of the prediction (first round) and a
    fifth (later rounds), the homography is refitted from the kept ones, and the set must be one plane (rms < 1.5 px,
    >= 20 corners). A whole-square slip is impossible: one square along a row flips the parity, a diagonal one is
    1.4 squares away. OpenCV's chessboard search needs the whole grid; this needs only the corners that show."""
    for rnd in range(3):
        vis = bd.visible_corners(vimg, H)
        ids = np.arange(88)[vis]
        if len(ids) < 20:
            return None
        pr = cv2.perspectiveTransform(bd.OBJ_MM[ids].reshape(-1, 1, 2), H).reshape(-1, 2)
        a, b, c_ = cv2.perspectiveTransform(np.array([[[360, 270]], [[420, 270]], [[360, 330]]], float), H).reshape(-1, 2)
        sq = float(min(np.linalg.norm(a - b), np.linalg.norm(a - c_)))
        win = int(np.clip(sq / 4, 2, 9))
        H_, W_ = vimg.shape
        inside = (pr[:, 0] > win + 1) & (pr[:, 1] > win + 1) & (pr[:, 0] < W_ - win - 2) & (pr[:, 1] < H_ - win - 2)
        ids, pr = ids[inside], pr[inside]
        if len(ids) < 20:
            return None
        ref = cv2.cornerSubPix(vimg, pr.reshape(-1, 1, 2).astype(np.float32), (win, win), (-1, -1),
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)).reshape(-1, 2).astype(float)
        ok = np.linalg.norm(ref - pr, axis=1) < max(1.5, sq / (3 if rnd == 0 else 5))
        ids, ref = ids[ok], ref[ok]
        if len(ids) < 20:
            return None
        H2, _m = cv2.findHomography(bd.OBJ_MM[ids].reshape(-1, 1, 2), ref.reshape(-1, 1, 2), cv2.RANSAC, 2.0)
        if H2 is None:
            return None
        H = H2
    res = np.linalg.norm(cv2.perspectiveTransform(bd.OBJ_MM[ids].reshape(-1, 1, 2), H).reshape(-1, 2) - ref, axis=1)
    keep = res < 2.0
    if keep.sum() < 20 or float(np.sqrt(np.mean(res[keep] ** 2))) > 1.5:
        return None
    ok, sc = registration_ok(vimg, ids[keep], ref[keep])
    if not ok:
        return None
    return ("rect-refined", ref[keep], ids[keep], note + f"; {int(keep.sum())} corners refined to the image saddles, "
            f"registration ncc {sc[0]} vs {sc[1]} shifted", None, None)


SHIFTS_MM = [(dx, dy) for dx in (-30, -15, 0, 15, 30) for dy in (-30, -15, 0, 15, 30)] + \
            [(dx, dy) for dx in (-120, -60, 0, 60, 120) for dy in (-120, -60, 0, 60, 120) if max(abs(dx), abs(dy)) >= 60]


def registration_ok(vimg, ids, px, margin=0.04):
    """is the board registered where the refined corners say? The printed plate (real markers and white border)
    rendered with their homography is correlated with the view, and so is the same render moved in the board plane
    by a quarter / half square and by one and two squares. Saddle refinement from a hypothesis half a square off can
    lock onto the markers' own edges (the whole board then sits half a square off, consistently, and passes the plane
    test), and one an even number of squares off lands on real saddles with every id wrong; the pattern with its
    markers and border is unambiguous where it shows. Accept only if the unshifted render is the best by `margin`
    (normalised cross-correlation) over every shift of a quarter square or more."""
    H, _ = cv2.findHomography(bd.OBJ_MM[ids].reshape(-1, 1, 2), np.asarray(px, float).reshape(-1, 1, 2), 0)
    if H is None:
        return False, None
    Q = cv2.perspectiveTransform(bd.PAPER_MM.reshape(-1, 1, 2), H).reshape(-1, 2)
    x0, y0 = np.floor(Q.min(0) - 40).astype(int); x1, y1 = np.ceil(Q.max(0) + 40).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, vimg.shape[1]), min(y1, vimg.shape[0])
    if x1 - x0 < 20 or y1 - y0 < 20:
        return False, None
    img = vimg[y0:y1, x0:x1].astype(np.float32)
    S = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], float)
    sc = {}
    for dx, dy in SHIFTS_MM:
        W = S @ H @ np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], float) @ T_PLATE
        t = cv2.warpPerspective(PLATE_IMG, W, (x1 - x0, y1 - y0), flags=cv2.INTER_AREA, borderValue=-1)
        m = (t >= 0) & (img > 0)                                             # black = outside the pano canvas
        if m.sum() < 500:
            sc[(dx, dy)] = -1.0; continue
        a = t[m] - t[m].mean(); b = img[m] - img[m].mean()
        sc[(dx, dy)] = float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9))
    best_other = max(v for k, v in sc.items() if k != (0, 0))
    return sc[(0, 0)] - best_other >= margin, (round(sc[(0, 0)], 3), round(best_other, 3))


def refine_from_markers(vimg, r):
    """a marker-only decode (corners PREDICTED from the markers' homography) -> measured corners (refine_from_H)."""
    ids, px = np.asarray(r[2], int), np.asarray(r[1], float)
    H, _ = cv2.findHomography(bd.OBJ_MM[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
    return refine_from_H(vimg, H, r[3]) if H is not None else None


CLOSE_S = 0.5                    # s: a prior from an own pose this close may seed the saddle refinement on its own


def near(r, H0, tol=30.0):
    """the refined corners within half a square (30 mm, board plane) of where the prior put them."""
    mm = cv2.perspectiveTransform(np.asarray(r[1], float).reshape(-1, 1, 2), np.linalg.inv(H0)).reshape(-1, 2)
    return float(np.median(np.linalg.norm(mm - bd.OBJ_MM[np.asarray(r[2], int)], axis=1))) < tol


def locate_decode(vimg, pred_v, tag, close_prior=False):
    """locate first, decode second (detect-then-decode): the markers decoded anywhere in the view (ChArUco), then the
    board located by matching the rendered plate around the prior (full decoder: ChArUco, then chessboard parity),
    then the prior itself; marker-only corners last. A decode must land within 250 mm of the prior."""
    H0, _ = cv2.findHomography(bd.OBJ_MM.reshape(-1, 1, 2), pred_v.reshape(-1, 1, 2), 0)
    if H0 is None:
        return None
    _, _, _, mk = bd.charuco_detect(vimg, refine_scale=0, detector=bd.CHARUCO_RECT)
    Hm, _n = bd.homography_from_markers(mk)
    if Hm is not None:
        r = quick_charuco(vimg, Hm, tag)
        if r and len(r[2]) >= 12 and plausible(r, H0):
            return r, "markers"
    tl = template_locate(vimg, H0)
    tries = ([(f"template {c[2][0]:+d},{c[2][1]:+d} px x{c[3]:.2f} ncc {c[1]:.2f}", c[0]) for c in tl[:1]]
             + [(n, H) for H, n in plate_locate(vimg, H0)] + [("prior", H0)])
    if close_prior:                                                      # tracked prior (own pose <= 0.5 s away):
        rf = refine_from_H(vimg, H0, tag)                                # the corners that show, refined - fast
        if rf and near(rf, H0):
            return rf, "prior + refined"
    for name, H in tries:                                                # markers in a wide view around each place
        Hw = wide_markers(vimg, H)
        if Hw is not None:
            r = bd.decode_rectified(vimg, Hw, tag, allow_markers_only=False)
            if r and len(r[2]) >= 12 and plausible(r, H0):
                return r, name + " + wide markers"
    for name, H in tries:
        r = bd.decode_rectified(vimg, H, tag, allow_markers_only=False)
        if r and len(r[2]) >= 12 and plausible(r, H0):
            return r, name
    for name, H in tries[:1]:                                            # nothing measured: the marker corners,
        r = bd.decode_rectified(vimg, H, tag)                            # refined to measured corners where they show
        if r and len(r[2]) >= 12 and plausible(r, H0):
            rf = refine_from_markers(vimg, r) if r[0] == "rect-markers" else None
            return (rf, name + " + markers + refined") if rf else (r, name)
    return None


VALIDATE = int(opt("--validate", "0"))
if VALIDATE:
    # Does the saddle refinement (rect-refined) measure the same corners as the decoder? On frames this camera decoded
    # itself (ChArUco, >= 30 corners), its own pose is hidden, the prior is built from the neighbouring frames as in a
    # rescue, the corners are refined from it (template first, then the prior) and compared with the decoded ones.
    cand = [f for f in dc["frames"] if f[3] >= 30 and main_pose_at(TF[f[0]]) is not None]
    pick = {cand[k][0]: cand[k] for k in np.linspace(0, len(cand) - 1, min(VALIDATE, len(cand))).astype(int)}
    cap = cv2.VideoCapture(str(SESSION / dc["file"]))
    first = dc["frames"][0][1]; cap.set(cv2.CAP_PROP_POS_MSEC, (first - 0.5) * 1000)
    i, d_all, rows = -1, [], []
    while pick and i < max(pick):
        if not cap.grab():
            break
        if i < 0:
            if abs(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 - first) > 1e-3:
                continue
            i = 0
        else:
            i += 1
        if i not in pick:
            continue
        hidden = own.pop(i, None)
        Pc, how, src, dt = prior_at(i)
        if hidden is not None:
            own[i] = hidden
        ok, img = cap.retrieve()
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE) if PANO else img
        vimg, uvmap, pred_v = virtual_view(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), Pc)
        H0, _ = cv2.findHomography(bd.OBJ_MM.reshape(-1, 1, 2), pred_v.reshape(-1, 1, 2), 0)
        tl = template_locate(vimg, H0)
        rf = None
        rf = refine_from_H(vimg, H0, "validate") if dt is not None and dt <= CLOSE_S else None
        rf = rf if rf and near(rf, H0) else None
        if not rf:
            rows.append((i, how, None)); continue
        vpx = np.asarray(rf[1], float)
        px = np.stack([map_coordinates(uvmap[..., k], [vpx[:, 1], vpx[:, 0]], order=1) for k in (0, 1)], 1)
        f = pick[i]; ref = dict(zip(f[4], np.asarray(f[5], float)))
        d = np.array([np.linalg.norm(q - ref[k]) for k, q in zip(rf[2], px) if k in ref])
        d_all.append(d); rows.append((i, how, d))
        print(f"  validate frame {i} ({how} prior): {len(rf[2])} refined, {len(d)} shared with the decode, "
              f"difference median {np.median(d):.2f} px, max {d.max():.2f}", flush=True)
    d = np.concatenate(d_all) if d_all else np.zeros(0)
    print(f"{WINDOW}/{CAM} VALIDATION: {len(pick)} decoded frames, refinement succeeded on {len(d_all)}; "
          f"{len(d)} corners, refined - decoded: median {np.median(d):.2f} px, p90 {np.percentile(d, 90):.2f}, "
          f"p99 {np.percentile(d, 99):.2f}, max {d.max():.2f}; corners > 5 px off: {int((d > 5).sum())}")
    raise SystemExit
out, t0 = list(old), time.time()
tried = {}                                                               # frame -> the own pose its last attempt used
for pas in range(1, 4):                                                  # each pass reaches 1.5 s further from the poses
    cap = cv2.VideoCapture(str(SESSION / dc["file"]))                    # found in the one before
    first = dc["frames"][0][1]
    cap.set(cv2.CAP_PROP_POS_MSEC, (first - 0.5) * 1000)
    i, n_new = -1, 0
    last_i = max(todo) if todo else -1
    while todo and i < last_i:
        if not cap.grab():
            break
        tf = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if i < 0:
            if abs(tf - first) > 1e-3:
                continue
            i = 0
        else:
            i += 1
        if i not in todo:
            continue
        Pc, how, src, dt = prior_at(i)
        if i in tried and (src is None or src == tried[i]):
            continue                                                     # nothing new to try here
        tried[i] = src
        ok, img = cap.retrieve()
        if PANO:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        vimg, uvmap, pred_v = virtual_view(gray, Pc)
        tf0 = time.time()
        rr = locate_decode(vimg, pred_v, f"rescue {WINDOW}/{CAM} frame {i}", dt is not None and dt <= CLOSE_S)
        if DEBUG:
            H0, _ = cv2.findHomography(bd.OBJ_MM.reshape(-1, 1, 2), pred_v.reshape(-1, 1, 2), 0)
            tl = template_locate(vimg, H0)
            tl = tl[0] if tl else None
            pl = plate_locate(vimg, H0)
            dbg = cv2.cvtColor(vimg, cv2.COLOR_GRAY2BGR)
            for H, col in ((H0, (255, 0, 255)), (tl[0] if tl else None, (0, 255, 0)), (pl[0][0] if pl else None, (0, 165, 255))):
                if H is not None:
                    q = cv2.perspectiveTransform(bd.PAPER_MM.reshape(-1, 1, 2), H).astype(np.int32)
                    cv2.polylines(dbg, [q], True, col, 2)
            cv2.putText(dbg, f"frame {i} {how} ncc {tl[1] if tl else 0:.2f} shift {tl[2] if tl else None} x{tl[3] if tl else 0}",
                        (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.imwrite(str(Path(DEBUG) / f"{WINDOW}_{CAM}_{i}.jpg"), dbg)
            np.savez_compressed(Path(DEBUG) / f"{WINDOW}_{CAM}_{i}.npz", vimg=vimg, H0=H0, uv=uvmap)
        print(f"  pass {pas} frame {i}: {(rr[0][0] + ' ' + str(len(rr[0][2])) + ' corners, located by ' + rr[1]) if rr else 'not decoded'}"
              f" ({how} prior), {time.time() - tf0:.1f} s", flush=True)
        if rr:
            r, located = rr
            vpx = np.asarray(r[1], float)
            px = np.stack([map_coordinates(uvmap[..., k], [vpx[:, 1], vpx[:, 0]], order=1) for k in (0, 1)], 1)
            ids = np.asarray(r[2], int)
            out.append([i, r[0], int(len(ids)), [int(v) for v in ids], np.round(px, 2).tolist(), f"{how} prior, {located}"])
            todo.discard(i); n_new += 1
            if r[0] in MEASURED and len(ids) >= 20:                     # tracking: the next frames start from here
                add_own(i, ids, px)
            if len(out) % 20 == 0 and not DEBUG:                         # partial save: a killed run keeps its work
                OUTF.write_text(json.dumps(dict(window=WINDOW, main=MAIN, cam=CAM, offset_s=OFFSET, partial=True, last_frame=i,
                                                frames=out)), encoding="utf-8")
    print(f"{WINDOW}/{CAM}: pass {pas} rescued {n_new}, {len(out)} in the file, {time.time() - t0:.0f} s", flush=True)
    if not n_new:
        break
if not DEBUG:
    OUTF.write_text(json.dumps(dict(window=WINDOW, main=MAIN, cam=CAM, offset_s=OFFSET, frames=out)), encoding="utf-8")
new = out[len(old):]
meth, loc = {}, {}
for o in new:
    meth[o[1]] = meth.get(o[1], 0) + 1
    k = o[5].split(" prior, ")[1].split(" ")[0]; loc[k] = loc.get(k, 0) + 1
print(f"{WINDOW}/{CAM}: done - {len(new)} newly rescued {meth}, located by {loc}; {len(todo)} left; {len(out)} in the file, "
      f"{time.time() - t0:.0f} s")
