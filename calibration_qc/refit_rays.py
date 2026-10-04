# -*- coding: utf-8 -*-
r"""Ray-space ground correction (raymap.py) refitted on the release's ground labels, with the camera centres held by
the operator's tape and the drone (AUDIT_FABLE_SOTA_2026-10-03.md, recommendation 1 in its ray-space form). The
bundle (camera_fit.npz) is unchanged; its poses are the starting point.

Unknowns: per camera the ray-correction coefficients (raymap.DEG) and a centre shift dC; the cones as shared latent
points held to their design station (SIGMA_LAYOUT in; 09-18 lattice and 09-30 supplement alike, as release 10-02b).
Data (pixels, carried to the 09-18 pixel frame where they are from 09-30): cones (at CONE_Z), the T cords X24..X456,
the straight wall-foot middles, the 09-30 cords Y39 / Y201 (weight CORD_W). Every label goes through its camera's
corrected ray to its height and must land on its target. Priors, all scaled to label inches by OBS_SIGMA:
coefficients towards 0 (SIG_COEF), and frame-free centre constraints - each camera's height and every pair's
horizontal distance from the tape (CH01-CH04, sigma 3 cm) or the drone (pairs with CH05 / CH06, sigma 6 cm; drone
coordinates rescaled by the ground plate, drone_board_scale.py). Soft-L1, f_scale 3, as the release.
With the lenses triangulated over many drone frames (camera_centres 'drone_tri', drone_lens_triangulate.py) every
pair's distance also comes from the drone (sigma 15 mm + 0.5 %) and every pair's height DIFFERENCE (sigma 20 mm; the
drone's floor runs on the grass tops, so only the tape gives absolute heights).
--boards puts the 09-18/19 ChArUco plates in (operator, 2026-10-03: the plate and the houses are the only exact
references): every plate pose gets a free (x, y, theta) on z = 6 mm and its corners - the printed pattern, mirrored in y
(its coordinates are left-handed seen from above) - must land on it in every camera that saw it (every B_STEP-th corner,
weight B_W; 3 = 0.5 in, the plates' own shape scatter). The 09-19 make-up plates are carried to the 09-18 pixels first
(session_2026-09-19_drift.json). Check 1 then holds plates out by station (B_FOLDS folds) and scores the plate shape.
--board-weak adds the operator's 4-corner clicks (the views the detector missed; all 4 corners, half weight) and
--board-seam the pano views across the stitch seam (marked bad only because one homography cannot span the seam).
--ground-datum (with --boards): one vertical datum, the ground the plates lie on, which is also the drone's floor (the
grass tops); the drone wall tops keep their own heights (no tape offset) and the tape heights enter as differences only
- the taped heights are from the soil, ~8 cm below (the plate fit puts every camera 2-8 cm under its taped height).
--terrain (drone_terrain.py) puts the labels on the LOCAL ground (cones at their stations, cords and wall feet where
the release maps them, plate corners 6 mm above it) and maps every check the same way; the RAYMAP names it and
paddock_map then maps "z above the local ground".
--walltop adds the first data above the ground: the operator's wall-top polylines in the cameras (analysis repo,
2026c landmarks, as walltop_check.py) must meet the wall's design plane at the drone's wall-top height there
(drone_walltop.py, on the tape's ground; weight WT_W); --walltop-hold <wall> leaves one wall out for the check.
--sweep <instances.json> (board_sweep20_instances.py; HANDOFF_SWEEP_BOARDS_2026-10-04.md) adds the 2026-09-18 hand-held
sweep boards - the plate in the air (0.14-0.54 m) seen at one moment by the sweep camera (CH03 / CH04) and a pano: per
instance a latent rigid 6-DOF board; every kept corner of every view (at most --sweep-ncorner per view, farthest-point
order, weight --sweep-w x clip(1.4 px / the view's sigma, 0.5, 2)) is a ray that must pass through its corner (the
perpendicular miss, in inches like the other labels). --sweep-hold odd|even leaves those 10-s blocks (int(t // 10) % 2)
out of the fit, for sweep_ray_check.py --blocks to score. --folds 0 skips the cone K-fold.
--drone-cords <json> (drone_line_check.py; operator 2026-10-03: the cords were laid by hand, the poles lean, only the
drone gives absolute positions) puts every cord the drone measured where the drone saw it: a cord label must land on the
drone's line (perpendicular distance) instead of on its design x / y; cords the drone did not measure (X24) and the wall
feet keep their design lines. --cord-folds is the check: every drone-measured cord is held out in turn (all its labels
out of the fit) and its labels, mapped by that fit, are scored across the cord against the drone line - drone model 1
(--cord-ref, default drone_cords_2026-10-02.json) and, if given, a second model (--cord-ref2) moved into model 1's frame
by the best 2-D similarity of the two line sets (the two anchors differ by a few cm; that is frame convention).

Checks (none of them in the fit): boards 09-18/19 (two cameras on the same corner, z 6 mm); a 5-fold over the 09-30
cones (refit without the fold, score its cones); the reviewed 20 Hz ball at 105 mm (fixed clock offsets, held and
wrong frames out); the west wall top cut by CH01 / CH02 / CH03 against each other and the drone profile; the camera
centres against the tape. Each check is computed the same way for the release (bundle + object-space warp).

Usage: python refit_rays.py --out <dir> [--fit <camera_fit.npz>] [--deg 3] [--sig-coef 0.03] [--no-centres] [--old-drone] [--walltop]
                              [--walltop-hold X0] [--wt-w 0.5] [--seam-w-deg 0] [--no-tape-dist] [--boards [--board-w 3]
                              [--board-step 7] [--board-folds 4] [--ground-datum] [--board-weak] [--board-seam]] [--drone-scale plate|anchor] [--height-source tape|drone] [--terrain terrain_2026-10-02.json] [--folds 5]
                              [--drone-cords drone_cords_2026-10-02.json]
                              [--sweep <instances.json> [--sweep-w 1] [--sweep-ncorner 8] [--sweep-hold odd|even]] [--cord-folds [--cord-ref <json>] [--cord-ref2 <json>]]
Output: <out>\RAYMAP.json (coefficients, dC), REFIT_RAYS.txt
"""
import sys, json, itertools, collections, time
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm, frame_correction as fcorr, raymap as rm   # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
OUT = Path(opt("--out")); OUT.mkdir(parents=True, exist_ok=True)
if opt("--fit"):                                                         # another bundle (e.g. a release candidate); its
    pm.FIT = Path(opt("--fit"))                                          # frame_correction.json must sit next to it
rm.DEG = int(opt("--deg", "3"))
rm.SEAM_W = float(opt("--seam-w-deg", "0")) * np.pi / 180      # stitch blend band of the panos (0 = step)
SIG_COEF = float(opt("--sig-coef", "0.03"))
USE_CENTRES = "--no-centres" not in args
FOLDS = int(opt("--folds", "5"))
TERR = pm.Terrain(Path(opt("--terrain"))) if opt("--terrain") else None   # ground relief (drone_terrain.py)
USE_BOARDS, B_W, B_STEP, B_FOLDS = "--boards" in args, float(opt("--board-w", "3")), int(opt("--board-step", "7")), int(opt("--board-folds", "4"))
SWEEP_F, SW_W, SW_N, SW_HOLD = opt("--sweep"), float(opt("--sweep-w", "1")), int(opt("--sweep-ncorner", "8")), opt("--sweep-hold")
USE_WALLTOP, WT_HOLD, WT_W = "--walltop" in args, opt("--walltop-hold"), float(opt("--wt-w", "0.5"))
WALLS = {"X0": (0, 0.0), "X480": (0, 480 * 25.4), "Y0": (1, 0.0), "Y240": (1, 240 * 25.4)}   # axis, design plane (mm)
SIGMA_LAYOUT, CORD_W, OBS_SIGMA, CONE_Z, IN = 4.0, 0.5, 1.5, fcorr.CONE_Z, 25.4
HERE = Path(__file__).resolve().parent
S18, Q18 = qc_paths.resolve(None)
S30, Q30 = qc_paths.resolve("2026-09-30")
cams = pm.load(pm.FIT, correct=False)
rel = pm.load(pm.FIT, rays=None)                                        # release 10-02b (bundle + object-space warp)
names = sorted(cams)
drift = json.loads((HERE / "session_2026-09-30_drift_final.json").read_text(encoding="utf-8"))["cameras"]
POS = {**fd.LATTICE, **fd.SUPPLEMENT}


def cord_line(L_, name):
    """a drone cord line (drone_line_check.py json entry, mm) as (n_x, n_y, c) in inches: n . xy - c is the signed
    distance across the cord, + towards larger x (X cords) / larger y (Y cords)."""
    v = np.asarray(L_["u"][:2], float); v /= np.linalg.norm(v); n = np.array([-v[1], v[0]])
    n *= np.sign(n[0 if name.startswith("X") else 1]); return np.r_[n, n @ np.asarray(L_["p0"][:2], float) / IN]


DCORDS = json.loads(Path(opt("--drone-cords")).read_text(encoding="utf-8"))["lines"] if opt("--drone-cords") else None
CORD_FOLDS = "--cord-folds" in args


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = drift.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        A = np.asarray(d["affine_30_to_18"], float); return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


# ---------------------------------------------------------------- labels in pixels: (cam, uv, z, kind, target, id, weight)
OBS = []
for cam in names:
    c = cams[cam]
    for st, uv in qc_paths.load_cones(Q18, cam, S18, space="upright").items():
        if st in fd.LATTICE:
            g = rel[cam].to_paddock(uv, z_mm=CONE_Z, units="in")
            if np.isfinite(g).all() and np.linalg.norm(g - fd.LATTICE[st]) < 40:
                OBS.append((cam, np.asarray(uv, float), CONE_Z, "cone", None, st + "@0918", 1.0))
    lf = Q18 / f"line_labels_{cam}.json"
    if lf.exists():
        d = json.loads(lf.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(S18, cam); dw, dh = d.get("frame_size_upright", [uw, uh]); sc = np.array([uw / float(dw), uh / float(dh)])
        for k, v in d["lines"].items():
            uvs = np.asarray(v, float) * sc
            g = c.to_paddock(uvs, z_mm=0.0, units="in")                      # bundle only, for the release's selection rule
            for q, u in zip(g, uvs):
                if not np.isfinite(q).all():
                    continue
                if k.startswith("X") and abs(q[0] - float(k[1:])) < 40 and -10 < q[1] < 250:
                    OBS.append((cam, u, 0.0, "x", float(k[1:]), k, 1.0))
                elif k in ("WALL_X0", "WALL_X480") and 60 < q[1] < 180 and abs(q[0] - (0.0 if k.endswith("X0") else 480.0)) < 40:
                    OBS.append((cam, u, 0.0, "x", 0.0 if k.endswith("X0") else 480.0, k, 1.0))
                elif k in ("WALL_Y0", "WALL_Y240") and 100 < q[0] < 380 and abs(q[1] - (0.0 if k.endswith("Y0") else 240.0)) < 40:
                    OBS.append((cam, u, 0.0, "y", 0.0 if k.endswith("Y0") else 240.0, k, 1.0))
    for st, uv in qc_paths.load_cones(Q30, cam, S30).items():
        if st in POS:
            OBS.append((cam, to_0918(cam, uv)[0], CONE_Z, "cone", None, st, 1.0))
    f = Q30 / f"line_labels_{cam}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(S30, cam); dw, dh = d.get("frame_size_upright", [uw, uh])
        for k, v in d["lines"].items():
            if k.startswith("Y") and v:
                for u in to_0918(cam, np.asarray(v, float) * [uw / float(dw), uh / float(dh)]):
                    OBS.append((cam, u, 0.0, "y", float(k[1:]), k + "@0930", CORD_W))
LM = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c")
IR2COL = {"CH01": (0.68, -0.39), "CH02": (0.90, 0.67), "CH03": (0.55, -5.60), "CH04": (0.03, 0.0)}   # 09-18 IR -> colour px
_WTJ = json.loads((qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all" / "walltop_profile.json").read_text(encoding="utf-8"))
WT = _WTJ["walls"]
if opt("--drone-scale", "plate") == "anchor":                            # wall tops back to the anchor scale and its own datum
    _cc = json.loads((qc_paths.QC_ROOT / "camera_centres_2026-10-03.json").read_text(encoding="utf-8"))
    _dat = 1000 * np.mean([v["h_m"] - _cc["drone_tri"][c]["z_m"] for c, v in _cc["tape"].items() if c in _cc["drone_tri"]])
    WT = {w: [[a, (z - _WTJ["datum_mm"]) / _WTJ["k_board"] + _dat, *r] for a, z, *r in v] for w, v in WT.items()}
if "--ground-datum" in args:                                             # one ground for everything: the plates' / drone floor's
    WT = {w: [[a, z - _WTJ["datum_mm"], *r] for a, z, *r in v] for w, v in WT.items()}   # (the tape's soil datum is ~8 cm lower)


def wall_pts(c, wall, step=10):
    fs = sorted(LM.glob(f"landmarks_{c}_20260918_*.json"))
    if not fs:
        return np.zeros((0, 2))
    pts = []
    for p in json.loads(fs[-1].read_text(encoding="utf-8"))["landmarks"].get(f"WALLTOP_{wall}", []):
        p = np.asarray(p, float)
        for a, b in zip(p[:-1], p[1:]):
            n = max(2, int(np.hypot(*(b - a)) / step)); pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
        pts.append(p[-1])
    return np.array(pts).reshape(-1, 2) + IR2COL.get(c, (0.0, 0.0))


def wt_target(wall, along_in):
    """drone wall-top height (mm) at a position along the wall (in); clamped at the profile's ends."""
    P = np.asarray(WT[wall], float)
    return np.interp(along_in, P[:, 0], P[:, 1])


def wall_cut(C, d, wall):
    ax, pl = WALLS[wall]
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = (pl - C[ax]) / d[:, ax]
    X = C + lam[:, None] * d; X[~(lam > 0)] = np.nan
    return X


WT_OBS = []                                                              # every wall-top pixel with a drone height there
for cam in names:
    for wall in WALLS:
        if wall not in WT:
            continue
        uv = wall_pts(cam, wall, step=30)
        if not len(uv):
            continue
        X = wall_cut(cams[cam].centre, cams[cam].rays(uv), wall)        # bundle only, for the selection
        a_in = X[:, 1 - WALLS[wall][0]] / IN; lo, hi = WT[wall][0][0] - 12, WT[wall][-1][0] + 12
        ok = np.isfinite(X).all(1) & (a_in > lo) & (a_in < hi) & (X[:, 2] > 400) & (X[:, 2] < 1800)
        for u in uv[ok]:
            WT_OBS.append((cam, u, 0.0, "wtop", wall, "WT_" + wall, WT_W))
if USE_WALLTOP:
    OBS += [o for o in WT_OBS if o[4] != WT_HOLD]
if DCORDS is not None:                                                   # cords where the drone measured them (hand-laid, not on design)
    OBS = [(o[0], o[1], o[2], "line", cord_line(DCORDS[o[5].split("@")[0]], o[5]), *o[5:])
           if o[3] in ("x", "y") and o[5].split("@")[0] in DCORDS else o for o in OBS]
if TERR is not None:                                                     # labels sit on the LOCAL ground: cones at their design
    _o2 = []                                                             # station, cords / wall feet where the release maps them
    for o in OBS:
        if o[3] == "cone":
            g_ = np.asarray(POS[o[5].replace("@0918", "")], float) * IN
        elif o[3] in ("x", "y", "line"):
            g_ = rel[o[0]].to_paddock(np.atleast_2d(o[1]), z_mm=o[2])
            g_ = g_[0] if np.isfinite(g_).all() else cams[o[0]].to_paddock(np.atleast_2d(o[1]), z_mm=o[2])[0]
        else:
            _o2.append(o); continue
        _o2.append((o[0], o[1], o[2] + float(TERR.height(g_)[0]), *o[3:]))
    OBS = _o2
Q = {c: [] for c in names}
for i, o in enumerate(OBS):
    Q[o[0]].append(i)
BASE = {c: rm.base_coords(cams[c], np.array([OBS[i][1] for i in Q[c]])) for c in names}
TERMS = {c: rm.terms(c, BASE[c]) for c in names}
NT = {c: rm.n_terms(c) for c in names}

# ---------------------------------------------------------------- centre constraints (frame-free)
cc = json.loads((qc_paths.QC_ROOT / "camera_centres_2026-10-03.json").read_text(encoding="utf-8"))
bs = json.loads((qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all" / "board_scale.json").read_text(encoding="utf-8"))
an = json.loads((qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all" / "anchor" / "anchor.json").read_text(encoding="utf-8"))["1"]
k_drone = bs["mm_per_unit"] / (1000 * an["scale"])                      # drone anchor metres -> board-scaled metres
if opt("--drone-scale", "plate") == "anchor":                            # the operator's pole tape (2026-10-03): rows A / C 480.25 /
    k_drone = 1.0                                                        # 480.0 in = the design grid; the plate's scale is local
TAPE = {c: np.array([v["x_in"] * IN, v["y_in"] * IN, v["h_m"] * 1000]) for c, v in cc["tape"].items()}
DRONE = {c: np.array([v["x_m"], v["y_m"], v["z_m"]]) * 1000 * k_drone for c, v in cc["drone"].items()}
TRI = {} if "--old-drone" in args else {c: np.array([v["x_m"], v["y_m"], v["z_m"]]) * 1000 * k_drone for c, v in cc.get("drone_tri", {}).items()}
DIST, HDIFF = [], []
if TRI:                                                                  # tape heights; drone distances and height differences
    HEIGHT = {c: (TAPE[c][2], 30.0) for c in names if c in TAPE}
    if opt("--height-source", "tape") == "drone":                        # operator: the cameras cannot be taped - the drone's lens
        HEIGHT = {c: (TRI[c][2], 40.0) for c in names if c in TRI}       # heights (its floor = the grass tops, a few cm above the plates)
    if "--ground-datum" in args:                                         # the tape's heights are from the soil: differences only
        HEIGHT = {}
        for a, b in itertools.combinations([c for c in names if c in TAPE], 2):
            HDIFF.append((a, b, TAPE[a][2] - TAPE[b][2], 30.0))
    for a, b in itertools.combinations(names, 2):
        if a in TAPE and b in TAPE and "--no-tape-dist" not in args:      # a long tape run sags / bends (operator)
            DIST.append((a, b, np.hypot(*(TAPE[a][:2] - TAPE[b][:2])), 30.0))
        if a in TRI and b in TRI:
            d = np.hypot(*(TRI[a][:2] - TRI[b][:2])); DIST.append((a, b, d, 15.0 + 0.005 * d))
            HDIFF.append((a, b, TRI[a][2] - TRI[b][2], 20.0))
else:
    HEIGHT = {c: (TAPE[c][2], 30.0) if c in TAPE else (DRONE[c][2], 60.0) for c in names if c in TAPE or c in DRONE}
    for a, b in itertools.combinations(names, 2):
        if a in TAPE and b in TAPE:
            DIST.append((a, b, np.hypot(*(TAPE[a][:2] - TAPE[b][:2])), 30.0))
        elif a in DRONE and b in DRONE:
            DIST.append((a, b, np.hypot(*(DRONE[a][:2] - DRONE[b][:2])), 60.0))


# ---------------------------------------------------------------- the ChArUco plates (rigid; operator: the exact references)
# every board view of 09-18/19 (the bundle's own placements, same filters as check 1); corners subsampled (index % B_STEP).
# The printed pattern's coordinates (obj_mm) are left-handed seen from above (y runs down the print): MIRROR y.
FLIP = np.array([1.0, -1.0])
import fit_data as _fd
DRIFT19 = json.loads((HERE / "session_2026-09-19_drift.json").read_text(encoding="utf-8"))["cameras"]


def placements19():
    """the bundle's plate views, the 09-19 make-up session carried into the 09-18 pixels (landmark_track_drift.py)."""
    out = []
    for p_ in _fd.all_placements():
        d_ = DRIFT19.get(p_["cam"]) if str(p_["session"]) == "2026-09-19" else None
        if d_:
            A_ = np.asarray(d_["affine_30_to_18"], float); p_ = dict(p_); p_["px"] = np.asarray(p_["px"], float) @ A_[:, :2].T + A_[:, 2]
        out.append(p_)
    return out


_zf = np.load(pm.FIT, allow_pickle=False)
_DROP = {tuple(s_.split("|")[:4]) for s_ in _zf["dropped_views"]} if "dropped_views" in _zf else set()
def _seam_split(p_):                                                     # a pano view across the stitch seam: "bad" only because
    if p_["cam"] not in rm.PANO:                                         # one homography cannot fit a board split over the two
        return False                                                     # lens halves (all 5 such views, 4-10 px)
    u_ = np.asarray(p_["px"], float)[:, 0]; W_ = cams[p_["cam"]].upright_size[0]
    return u_.min() < W_ / 2 < u_.max()


PB = [p_ for p_ in placements19() if (p_["cam"], p_["session"], p_["station"], p_["win"]) not in _DROP
      and (not p_["bad"] or ("--board-seam" in args and _seam_split(p_)))
      and (not p_["weak"] or "--board-weak" in args)]
def _order_clicks(PB):
    """The operator's 4-corner clicks are exact positions but not always in the same order around the plate (09-18 T12:
    CH01 went round the other way - its first edge is the 600 mm side). Each clicked view gets the corner order (4 starts
    x 2 directions) whose rigid plate fits its own mapped corners best and, where the same placement has detected views,
    agrees with their plate pose."""
    def rigid(A_, B_):
        am, bm = A_.mean(0), B_.mean(0); U_, _, Vt_ = np.linalg.svd((B_ - bm).T @ (A_ - am))
        R_ = U_ @ np.diag([1, np.sign(np.linalg.det(U_ @ Vt_))]) @ Vt_
        return R_, bm - R_ @ am
    det = collections.defaultdict(list)
    for p_ in PB:
        if not p_["weak"]:
            g_ = rel[p_["cam"]].to_paddock(np.asarray(p_["px"], float), z_mm=6.0, units="in"); ok_ = np.isfinite(g_).all(1)
            det[(p_["session"], p_["station"], p_["win"])].append((np.asarray(p_["obj_mm"], float)[ok_] * FLIP / IN, g_[ok_]))
    out, n_fix = [], 0
    for p_ in PB:
        if not p_["weak"] or len(p_["ids"]) != 4:
            out.append(p_); continue
        g_ = rel[p_["cam"]].to_paddock(np.asarray(p_["px"], float), z_mm=6.0, units="in")
        if not np.isfinite(g_).all():
            g_ = cams[p_["cam"]].to_paddock(np.asarray(p_["px"], float), z_mm=6.0, units="in")
        obj = np.asarray(p_["obj_mm"], float); best = None
        D_ = det.get((p_["session"], p_["station"], p_["win"]))
        if D_:
            Rd, td = rigid(np.concatenate([a for a, b in D_]), np.concatenate([b for a, b in D_]))
        for k in range(4):
            for sgn in (1, -1):
                o_ = np.roll(obj[::sgn], k, axis=0); A_ = o_ * FLIP / IN
                if not np.isfinite(g_).all():
                    continue
                R_, t_ = rigid(A_, g_); e_ = np.sqrt(((A_ @ R_.T + t_ - g_) ** 2).sum(1).mean())
                if D_:
                    e_ += np.sqrt(((A_ @ Rd.T + td - g_) ** 2).sum(1).mean())
                if best is None or e_ < best[0]:
                    best = (e_, o_)
        if best is not None and not np.allclose(best[1], obj):
            p_ = dict(p_); p_["obj_mm"] = best[1]; n_fix += 1
        out.append(p_)
    return out, n_fix


if "--board-weak" in args:
    PB, N_REORDER = _order_clicks(PB)
else:
    N_REORDER = 0
BKEYS = sorted({(p_["session"], p_["station"], p_["win"]) for p_ in PB})
BCAM = {c: dict(px=[], obj=[], key=[], w=[]) for c in names}
for p_ in PB:
    k_ = (np.arange(len(p_["ids"])) % B_STEP == 0) if len(p_["ids"]) > 12 else np.ones(len(p_["ids"]), bool)   # clicks: all 4
    BCAM[p_["cam"]]["w"] += [0.5 if p_["weak"] else 1.0] * int(k_.sum())                             # clicks: half weight
    BCAM[p_["cam"]]["px"].append(np.asarray(p_["px"], float)[k_]); BCAM[p_["cam"]]["obj"].append(np.asarray(p_["obj_mm"], float)[k_] * FLIP / IN)
    BCAM[p_["cam"]]["key"] += [(p_["session"], p_["station"], p_["win"])] * int(k_.sum())
for c in names:
    b_ = BCAM[c]
    b_["px"] = np.concatenate(b_["px"]) if b_["px"] else np.zeros((0, 2)); b_["obj"] = np.concatenate(b_["obj"]) if b_["obj"] else np.zeros((0, 2))
    b_["key"] = np.array([BKEYS.index(k_) for k_ in b_["key"]], int); b_["w"] = np.array(b_["w"], float)
    b_["q"] = rm.base_coords(cams[c], b_["px"]) if len(b_["px"]) else np.zeros((0, 2)); b_["T"] = rm.terms(c, b_["q"]) if len(b_["q"]) else None


# ---------------------------------------------------------------- the hand-held sweep boards (2026-09-18): the plate in the air
SW_I, SKEYS = [], []
SCAM = {c: dict(px=[], obj=[], key=[], w=[]) for c in names}
if SWEEP_F:
    import board_detect as bd
    from scipy.spatial.transform import Rotation as Rot
    import cv2
    OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
    SW_I = json.loads(Path(SWEEP_F).read_text(encoding="utf-8"))["instances"]

    def _fps(P_, n_):                                                    # farthest-point order (deterministic)
        k_ = [0]; d_ = np.linalg.norm(P_ - P_[0], axis=1)
        while len(k_) < min(n_, len(P_)):
            j_ = int(np.argmax(d_)); k_.append(j_); d_ = np.minimum(d_, np.linalg.norm(P_ - P_[j_], axis=1))
        return np.array(k_)
    for si, ins in enumerate(SW_I):
        for v in ins["views"]:
            ids_ = np.asarray(v["ids"], int); px_ = np.asarray(v["px"], float); k_ = _fps(OBJ3[ids_, :2], SW_N)
            sc_ = SCAM[v["cam"]]
            sc_["px"].append(px_[k_]); sc_["obj"].append(OBJ3[ids_[k_]]); sc_["key"] += [si] * len(k_)
            sc_["w"] += [float(np.clip(1.4 / max(v["sigma"], 1e-3), 0.5, 2.0))] * len(k_)
    for c in names:
        s_ = SCAM[c]
        s_["px"] = np.concatenate(s_["px"]) if s_["px"] else np.zeros((0, 2)); s_["obj"] = np.concatenate(s_["obj"]) if s_["obj"] else np.zeros((0, 3))
        s_["key"] = np.array(s_["key"], int); s_["w"] = np.array(s_["w"], float)
        s_["q"] = rm.base_coords(cams[c], s_["px"]) if len(s_["px"]) else np.zeros((0, 2)); s_["T"] = rm.terms(c, s_["q"]) if len(s_["q"]) else None
    SBLOCK = np.array([int(ins["t"] // 10) % 2 for ins in SW_I])
    SKEYS = [i for i in range(len(SW_I)) if SW_HOLD is None or SBLOCK[i] != {"even": 0, "odd": 1}[SW_HOLD]]

    def sweep_init():
        """each board's pose from its sweep camera alone (planar PnP in a virtual pinhole along the mean ray, raw bundle
        - the fit's starting point), as sweep_check.py: rotvec (3) and centre (mm, 3) per instance."""
        out_ = np.zeros((len(SW_I), 6))
        for si, ins in enumerate(SW_I):
            v = ins["views"][0]; c = cams[v["cam"]]; ids_ = np.asarray(v["ids"], int)
            b = c.rays(np.asarray(v["px"], float)) @ c.R.T                # camera-frame bearings
            m = b.mean(0); m /= np.linalg.norm(m)
            Qm = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); vv = b @ Qm.T; uv = (vv[:, :2] / vv[:, 2:]).astype(np.float64)
            P3 = OBJ3[ids_].astype(np.float64)
            _, rv, tv, e = cv2.solvePnPGeneric(P3, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
            k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P3, uv, np.eye(3), None, rv[k], tv[k])
            Rc = Qm.T @ cv2.Rodrigues(rv)[0]; Xc = Qm.T @ tv.ravel()
            out_[si, :3] = Rot.from_matrix(c.R.T @ Rc).as_rotvec(); out_[si, 3:] = c.R.T @ (Xc - c.tvec)
        return out_
else:                                                                    # no sweep: empty arrays, so fit() needs no special case
    for c in names:
        SCAM[c] = dict(px=np.zeros((0, 2)), obj=np.zeros((0, 3)), key=np.zeros(0, int), w=np.zeros(0), q=np.zeros((0, 2)), T=None)


def plate_init():
    """each plate pose (x, y in, theta) from the release's mapping of its corners (rigid 2-D Procrustes, all its views)."""
    out = np.zeros((len(BKEYS), 3))
    for i, key in enumerate(BKEYS):
        A_, B_ = [], []
        for p_ in PB:
            if (p_["session"], p_["station"], p_["win"]) == key:
                g_ = rel[p_["cam"]].to_paddock(np.asarray(p_["px"], float), z_mm=6.0, units="in")
                if not np.isfinite(g_).all(1).any():
                    g_ = cams[p_["cam"]].to_paddock(np.asarray(p_["px"], float), z_mm=6.0, units="in")
                ok_ = np.isfinite(g_).all(1); A_.append(np.asarray(p_["obj_mm"], float)[ok_] * FLIP / IN); B_.append(g_[ok_])
        A_, B_ = np.concatenate(A_), np.concatenate(B_)
        am, bm = A_.mean(0), B_.mean(0); U_, _, Vt_ = np.linalg.svd((B_ - bm).T @ (A_ - am))
        R_ = U_ @ np.diag([1, np.sign(np.linalg.det(U_ @ Vt_))]) @ Vt_
        th = np.arctan2(R_[1, 0], R_[0, 0]); out[i] = [*(bm - R_ @ am), th]
    return out


def plate_xy(pp, obj):
    ct, st = np.cos(pp[:, 2]), np.sin(pp[:, 2])
    return np.stack([pp[:, 0] + ct * obj[:, 0] - st * obj[:, 1], pp[:, 1] + st * obj[:, 0] + ct * obj[:, 1]], 1)


def map_obs(rc, idx, q, T):
    """paddock points (mm) of observations idx: ground labels at their height, wall tops on their wall plane."""
    d = rc.rays_q(q, T); C = rc.centre; X = np.full((len(idx), 3), np.nan)
    kinds = np.array([OBS[i][3] for i in idx]); zs = np.array([OBS[i][2] for i in idx], float)
    g = kinds != "wtop"
    if g.any():
        with np.errstate(divide="ignore", invalid="ignore"):
            lam = (zs[g] - C[2]) / d[g, 2]
        Xg = C + lam[:, None] * d[g]; Xg[~(lam > 0)] = np.nan; X[g] = Xg
    wl = np.array([OBS[i][4] if OBS[i][3] == "wtop" else "" for i in idx], dtype=object)
    for wall in WALLS:
        m = wl == wall
        if m.any():
            X[m] = wall_cut(C, d[m], wall)
    return X


def unpack(x, ids, nb=0, ns=0):
    o, coef, dC = 0, {}, {}
    for c in names:
        coef[c] = x[o:o + 2 * NT[c]].reshape(2, NT[c]); o += 2 * NT[c]
        dC[c] = x[o:o + 3]; o += 3
    P = x[o:o + 2 * len(ids)].reshape(-1, 2); o += 2 * len(ids)
    PP = x[o:o + 3 * nb].reshape(-1, 3); o += 3 * nb
    return coef, dC, P, PP, x[o:o + 6 * ns].reshape(-1, 6)


def fit(use, ids, bkeys=None, skeys=None):
    """use: boolean mask over OBS; ids: the latent cone ids; bkeys: plate poses in the fit (indices into BKEYS);
    skeys: sweep boards in the fit (indices into SW_I; default SKEYS)."""
    bkeys = (list(range(len(BKEYS))) if USE_BOARDS else []) if bkeys is None else list(bkeys)
    skeys = list(SKEYS) if skeys is None else list(skeys)
    sx = {k: i for i, k in enumerate(skeys)}; ns = len(skeys)
    ssel = {c: np.isin(SCAM[c]["key"], skeys) for c in names}
    spi = {c: np.array([sx[k] for k in SCAM[c]["key"][ssel[c]]], int) for c in names}
    bx = {k: i for i, k in enumerate(bkeys)}; nb = len(bkeys)
    bsel = {c: np.isin(BCAM[c]["key"], bkeys) for c in names}
    bpi = {c: np.array([bx[k] for k in BCAM[c]["key"][bsel[c]]], int) for c in names}
    jx = {j: i for i, j in enumerate(ids)}
    design = np.array([POS[j.replace("@0918", "")] for j in ids], float).reshape(-1, 2)
    nx = sum(2 * NT[c] + 3 for c in names) + 2 * len(ids) + 3 * nb + 6 * ns
    x0 = np.zeros(nx); o0 = sum(2 * NT[c] + 3 for c in names)
    x0[o0:o0 + 2 * len(ids)] = design.ravel() if ids else []
    if nb:
        x0[o0 + 2 * len(ids):o0 + 2 * len(ids) + 3 * nb] = PINIT[bkeys].ravel()
    if ns:
        x0[o0 + 2 * len(ids) + 3 * nb:] = SINIT[skeys].ravel()
    per = {c: [i for i in Q[c] if use[i]] for c in names}
    loc = {c: np.array([Q[c].index(i) for i in per[c]], int) for c in names}

    def resid(x):
        coef, dC, P, PP, SP = unpack(x, ids, nb, ns)
        r = []
        for c in names:
            if not len(per[c]):
                r.append(coef[c].ravel() * OBS_SIGMA / SIG_COEF); continue
            rc = rm.RayCam(cams[c], coef[c], dC[c])
            q, T = BASE[c][loc[c]], TERMS[c][loc[c]]
            X = map_obs(rc, per[c], q, T)
            g = np.nan_to_num(X / IN, nan=1e4)
            for k, i in enumerate(per[c]):
                _, _, _, kind, tgt, j, w = OBS[i]
                if kind == "cone":
                    r += list((g[k, :2] - P[jx[j]]) * w)
                elif kind == "x":
                    r.append((g[k, 0] - tgt) * w)
                elif kind == "y":
                    r.append((g[k, 1] - tgt) * w)
                elif kind == "line":                                     # across the drone's cord line
                    r.append((g[k, 0] * tgt[0] + g[k, 1] * tgt[1] - tgt[2]) * w)
                else:                                                    # wall top: height where the ray meets the wall plane
                    r.append((g[k, 2] - wt_target(tgt, g[k, 1 - WALLS[tgt][0]]) / IN) * w)
            r = r if isinstance(r, list) else list(r)
            r += list(coef[c].ravel() * OBS_SIGMA / SIG_COEF)
        if ids:
            r += list(((P - design) * OBS_SIGMA / SIGMA_LAYOUT).ravel())
        if USE_CENTRES:
            C = {c: cams[c].centre + dC[c] for c in names}
            for c, (h, s) in HEIGHT.items():
                r.append((C[c][2] - h) * OBS_SIGMA / s)
            for a, b, d, s in DIST:
                r.append((np.hypot(*(C[a][:2] - C[b][:2])) - d) * OBS_SIGMA / s)
            for a, b, d, s in HDIFF:
                r.append((C[a][2] - C[b][2] - d) * OBS_SIGMA / s)
        for c in names:                                                  # the plates: corners at z 6 mm on a rigid board
            if nb and bsel[c].any():
                rc = rm.RayCam(cams[c], coef[c], dC[c])
                X = rc.to_plane_q(BCAM[c]["q"][bsel[c]], BCAM[c]["z"][bsel[c]], BCAM[c]["T"][bsel[c]])
                g = np.nan_to_num(X[:, :2] / IN, nan=1e4)
                r += list(((g - plate_xy(PP[bpi[c]], BCAM[c]["obj"][bsel[c]])) * B_W * BCAM[c]["w"][bsel[c]][:, None]).ravel())
        for c in names:                                                  # the sweep boards: each kept corner's ray through its corner
            if ns and ssel[c].any():
                rc = rm.RayCam(cams[c], coef[c], dC[c]); s_ = SCAM[c]
                d = rc.rays_q(s_["q"][ssel[c]], s_["T"][ssel[c]])
                Xs = np.einsum("nij,nj->ni", Rot.from_rotvec(SP[spi[c], :3]).as_matrix(), s_["obj"][ssel[c]]) + SP[spi[c], 3:]
                v = Xs - rc.centre; perp = v - (v * d).sum(1)[:, None] * d
                r += list((perp / IN * SW_W * s_["w"][ssel[c]][:, None]).ravel())
        return np.array(r, float)

    # sparsity: a camera's parameters touch its own label rows, its prior rows and the centre rows
    r0 = resid(x0); J = lil_matrix((len(r0), nx), dtype=bool)
    row, col = 0, 0
    cols = {}
    for c in names:
        cols[c] = np.arange(col, col + 2 * NT[c] + 3); col += 2 * NT[c] + 3
    pcol = col
    jx_rows = []
    for c in names:
        for i in per[c]:
            kind, j = OBS[i][3], OBS[i][5]
            n = 2 if kind == "cone" else 1
            for k in range(n):
                J[row + k, cols[c]] = True
                if kind == "cone":
                    J[row + k, pcol + 2 * jx[j] + k] = True
            row += n
        for k in range(2 * NT[c]):
            J[row + k, cols[c][k]] = True
        row += 2 * NT[c]
    for i in range(len(ids)):
        J[row, pcol + 2 * i] = True; J[row + 1, pcol + 2 * i + 1] = True; row += 2
    if USE_CENTRES:
        for c, _ in HEIGHT.items():
            J[row, cols[c][-1]] = True; row += 1
        for a, b, _, _ in DIST:
            J[row, cols[a][-3:-1]] = True; J[row, cols[b][-3:-1]] = True; row += 1
        for a, b, _, _ in HDIFF:
            J[row, cols[a][-1]] = True; J[row, cols[b][-1]] = True; row += 1
    bcol = pcol + 2 * len(ids)
    for c in names:
        if nb and bsel[c].any():
            for pi in bpi[c]:
                for k in range(2):
                    J[row, cols[c]] = True; J[row, bcol + 3 * pi:bcol + 3 * pi + 3] = True; row += 1
    scol = bcol + 3 * nb
    for c in names:
        if ns and ssel[c].any():
            for pi in spi[c]:
                for k in range(3):
                    J[row, cols[c]] = True; J[row, scol + 6 * pi:scol + 6 * pi + 6] = True; row += 1
    assert row == len(r0), (row, len(r0))
    sol = least_squares(resid, x0, jac_sparsity=J, loss="soft_l1", f_scale=3.0, x_scale="jac", max_nfev=200)
    coef, dC, P, PP, SP = unpack(sol.x, ids, nb, ns)
    FIT_SP.clear(); FIT_SP.update({k: SP[i] for k, i in sx.items()})
    return {c: rm.RayCam(cams[c], coef[c], dC[c]) for c in names}, dict(zip(ids, P)), sol


PINIT = plate_init() if USE_BOARDS else None
SINIT = sweep_init() if SWEEP_F else None
FIT_SP = {}                                                              # the last fit's sweep-board poses
for c in names:                                                          # plate corner heights: 6 mm above the local ground
    if USE_BOARDS and len(BCAM[c]["q"]):
        BCAM[c]["z"] = 6.0 + (TERR.height(plate_xy(PINIT[BCAM[c]["key"]], BCAM[c]["obj"]) * IN) if TERR is not None else 0.0)
    else:
        BCAM[c]["z"] = np.zeros(0)
ALL = np.ones(len(OBS), bool)
IDS = sorted({o[5] for o in OBS if o[3] == "cone"})
t0 = time.time()
RC, PJ, sol = fit(ALL, IDS)
L = [f"RAY-SPACE GROUND CORRECTION  bundle {pm.FIT} (unchanged); degree {rm.DEG}, coefficient prior {SIG_COEF}, "
     f"seam {'step' if rm.SEAM_W == 0 else f'ramp over {np.degrees(rm.SEAM_W):.0f} deg'}; "
     f"{'terrain ' + Path(opt('--terrain')).name + '; ' if TERR is not None else ''}{'ground datum = plates / drone floor; ' if '--ground-datum' in args else ''}drone scale {opt('--drone-scale', 'plate')}; heights {opt('--height-source', 'tape')}; centre constraints {(('triangulated drone lenses only (distances, heights, height differences)' if opt('--height-source', 'tape') == 'drone' and '--no-tape-dist' in args else 'tape heights + triangulated drone lenses' if '--no-tape-dist' in args else 'tape + triangulated drone lenses') if TRI else 'tape + drone (distances, heights)') if USE_CENTRES else 'none'}; "
     f"boards {('in the fit (weight ' + str(B_W) + ', every ' + str(B_STEP) + 'th corner, ' + str(len(BKEYS)) + ' plate poses, ' + str(len(PB)) + ' views' + (', + operator clicks (' + str(N_REORDER) + ' re-ordered)' if '--board-weak' in args else '') + (', + seam-split views' if '--board-seam' in args else '') + ')') if USE_BOARDS else 'not in the fit'}; "
     f"wall tops {('in the fit (weight ' + str(WT_W) + (', ' + WT_HOLD + ' held out' if WT_HOLD else '') + ')') if USE_WALLTOP else 'not in the fit'}; "
     f"sweep boards {(str(len(SKEYS)) + ' of ' + str(len(SW_I)) + ' instances in the fit (weight ' + str(SW_W) + ', ' + str(SW_N) + ' corners per view' + (', ' + SW_HOLD + ' 10-s blocks held out' if SW_HOLD else '') + ')') if SWEEP_F else 'not in the fit'}",
     f"{len(OBS)} labels ({collections.Counter(o[3] for o in OBS)}), {len(IDS)} latent cones; fit {time.time() - t0:.0f} s, "
     f"cost {sol.cost:.0f}, status {sol.status}", ""]
lab_res = collections.defaultdict(list)
for c in names:
    rc = RC[c]
    for i in Q[c]:
        _, uv, z, kind, tgt, j, w = OBS[i]
        if kind == "wtop":
            Xw = wall_cut(rc.centre, rc.rays(np.atleast_2d(uv)), tgt)[0]
            lab_res[(c, kind)].append(abs(Xw[2] - wt_target(tgt, Xw[1 - WALLS[tgt][0]] / IN)) / IN); continue
        g = rc.to_paddock(uv, z, units="in")[0]
        e = (np.hypot(*(g - PJ[j])) if kind == "cone" else abs(g[0] - tgt) if kind == "x" else abs(g[1] - tgt) if kind == "y"
             else abs(g @ tgt[:2] - tgt[2]))
        lab_res[(c, kind)].append(e)
L.append("label residuals (in, median / p90): " + "; ".join(f"{c} {k} {np.median(v):.1f}/{np.percentile(v, 90):.1f}" for (c, k), v in sorted(lab_res.items())))
if SWEEP_F:                                                              # sweep corners in the fit: the rays' miss of the fitted board
    _sw = collections.defaultdict(list)
    for c in names:
        s_ = SCAM[c]; m_ = np.isin(s_["key"], SKEYS)
        if m_.any():
            d = RC[c].rays(s_["px"][m_]); Ps = np.array([FIT_SP[k] for k in s_["key"][m_]])
            Xs = np.einsum("nij,nj->ni", Rot.from_rotvec(Ps[:, :3]).as_matrix(), s_["obj"][m_]) + Ps[:, 3:]
            v = Xs - RC[c].centre; _sw[c] = np.linalg.norm(v - (v * d).sum(1)[:, None] * d, axis=1)
    L.append("sweep corners in the fit, the ray's miss of its fitted board (mm, median / p90): " + "; ".join(f"{c} {np.median(v):.1f}/{np.percentile(v, 90):.1f}" for c, v in _sw.items()))
L.append("camera centres (in, tape-frame-free): " + "; ".join(f"{c} dC ({RC[c].dC[0] / IN:+.1f}, {RC[c].dC[1] / IN:+.1f}, {RC[c].dC[2] / IN:+.1f})" for c in names))
for a, b, d, s in DIST:                                                  # sigma 30 = a tape pair, otherwise the drone
    L.append(f"  distance {a}-{b}: {'tape' if s == 30.0 else 'drone'} {d / IN:.1f} in"
             + (f" (tape {np.hypot(*(TAPE[a][:2] - TAPE[b][:2])) / IN:.1f}, not in the fit)" if s != 30.0 and a in TAPE and b in TAPE
                and "--no-tape-dist" in args else "")
             + f"; release {np.hypot(*(cams[a].centre[:2] - cams[b].centre[:2])) / IN:.1f}; ray fit {np.hypot(*(RC[a].centre[:2] - RC[b].centre[:2])) / IN:.1f}")
L.append("  heights (m): " + ", ".join(f"{c} release {cams[c].centre[2] / 1000:.3f} fit {RC[c].centre[2] / 1000:.3f} target {HEIGHT[c][0] / 1000:.3f}" for c in names if c in HEIGHT))
L.append("")

# ---------------------------------------------------------------- check 1: boards (two cameras on the same corner, z 6 mm)
P = [p for p in placements19() if not p["bad"] and not p["weak"]]
_z = np.load(pm.FIT, allow_pickle=False)
DROP = {tuple(s.split("|")[:4]) for s in _z["dropped_views"]} if "dropped_views" in _z else set()
P = [p for p in P if (p["cam"], p["session"], p["station"], p["win"]) not in DROP]


def board_check(mapfn):
    sh = {}
    for p in P:
        xy = mapfn(p["cam"], p["px"], 6.0)
        for i, q in zip(p["ids"], xy):
            if np.isfinite(q).all():
                sh.setdefault(((p["session"], p["station"], p["win"]), int(i)), {})[p["cam"]] = q
    d = collections.defaultdict(list)
    for k, v in sh.items():
        for a, b in itertools.combinations(sorted(v), 2):
            d[f"{a}-{b}"].append(np.hypot(*(v[a] - v[b])))
    allv = np.concatenate([np.array(v) for v in d.values()])
    return allv, d


rel_map = lambda c, uv, z: rel[c].to_paddock(uv, z_mm=z)
def tmap(rc, uv, z):
    """a RayCam's mapping at height z above the LOCAL ground (iterated on the terrain), or above z = 0 without one."""
    xy = rc.to_paddock(uv, z)
    if TERR is not None:
        for _ in range(5):
            xy = rc.to_paddock(uv, z + TERR.height(np.nan_to_num(xy)))
    return xy


ray_map = lambda c, uv, z: tmap(RC[c], uv, z)


def shape_check(mapfn, views):
    """per view: rms of the mapped corners about the best rigid 2-D fit of the printed plate (mm) - scale and shape."""
    out = []
    for p_ in views:
        g_ = mapfn(p_["cam"], np.asarray(p_["px"], float), 6.0); ok_ = np.isfinite(g_).all(1)
        if ok_.sum() < 8:
            continue
        A_, B_ = np.asarray(p_["obj_mm"], float)[ok_] * FLIP, g_[ok_]
        am, bm = A_.mean(0), B_.mean(0); U_, _, Vt_ = np.linalg.svd((B_ - bm).T @ (A_ - am))
        R_ = U_ @ np.diag([1, np.sign(np.linalg.det(U_ @ Vt_))]) @ Vt_
        out.append(np.sqrt(((B_ - bm - (A_ - am) @ R_.T) ** 2).sum(1).mean()))
    return np.array(out)


VIEWS_HO = []


def held_views(mapfn, views, fold):
    """per held-out plate view: where it is, how far its mapped corners leave the rigid printed pattern (shape rms) and
    how much bigger / smaller it maps (similarity scale - 1), plus, per placement, the other cameras' corners."""
    byk = collections.defaultdict(dict)
    for p_ in views:
        g_ = mapfn(p_["cam"], np.asarray(p_["px"], float), 6.0); ok_ = np.isfinite(g_).all(1)
        if ok_.sum() < 8:
            continue
        A_, B_ = np.asarray(p_["obj_mm"], float)[ok_] * FLIP, g_[ok_]
        am, bm = A_.mean(0), B_.mean(0); U_, S_, Vt_ = np.linalg.svd((B_ - bm).T @ (A_ - am))
        D_ = np.diag([1, np.sign(np.linalg.det(U_ @ Vt_))]); R_ = U_ @ D_ @ Vt_
        sc_ = np.trace(np.diag(S_) @ D_) / ((A_ - am) ** 2).sum()
        rms = float(np.sqrt(((B_ - bm - (A_ - am) @ R_.T) ** 2).sum(1).mean()))
        key = (str(p_["session"]), p_["station"], p_["win"])
        for i_, q_ in zip(np.asarray(p_["ids"])[ok_], B_):
            byk[key].setdefault(int(i_), {})[p_["cam"]] = q_
        VIEWS_HO.append(dict(fold=fold, session=str(p_["session"]), station=p_["station"], cam=p_["cam"], n=int(ok_.sum()),
                             x_in=round(float(bm[0] / IN), 1), y_in=round(float(bm[1] / IN), 1),
                             shape_rms_mm=round(rms, 1), scale_err_pct=round(100 * (sc_ - 1), 2)))
    for key, cor in byk.items():                                         # two cameras on the same held-out corner
        pairs_ = collections.defaultdict(list)
        for i_, v_ in cor.items():
            for a_, b_ in itertools.combinations(sorted(v_), 2):
                pairs_[(a_, b_)].append(float(np.hypot(*(v_[a_] - v_[b_]))))
        for (a_, b_), d_ in pairs_.items():
            VIEWS_HO.append(dict(fold=fold, session=key[0], station=key[1], pair=f"{a_}-{b_}", n=len(d_), median_mm=round(float(np.median(d_)), 1)))


L.append("CHECK boards (mm, median / p90 of two cameras on the same corner)" + (" - boards IN the fit:" if USE_BOARDS else ":"))
for nm, f in (("release", rel_map), ("ray fit", ray_map)):
    a, d = board_check(f)
    L.append(f"  {nm:8s} all {np.median(a):.0f} / {np.percentile(a, 90):.0f} (n {len(a)}); " + ", ".join(f"{k} {np.median(v):.0f}" for k, v in sorted(d.items()) if len(v) >= 20))
for nm, f in (("release", rel_map), ("ray fit", ray_map)):
    sc = shape_check(f, P)
    L.append(f"  plate shape, rms about the rigid printed pattern ({nm}): median {np.median(sc):.1f} mm, p90 {np.percentile(sc, 90):.1f} (n {len(sc)} views)")
if USE_BOARDS and B_FOLDS > 1:                                           # honest version: plates held out by station
    stations = sorted({k[1] for k in BKEYS}); rngb = np.random.default_rng(1); permb = rngb.permutation(stations)
    pa, ps, pr = [], [], []
    for k in range(B_FOLDS):
        hold = set(permb[k::B_FOLDS]); keep = [i for i, key in enumerate(BKEYS) if key[1] not in hold]
        RCb, _, _ = fit(ALL, IDS, keep)
        Ph = [p_ for p_ in P if p_["station"] in hold]
        P_save = P; P = Ph
        a_, _ = board_check(lambda c, uv, z: tmap(RCb[c], uv, z)); pa.append(a_)
        a2, _ = board_check(rel_map); pr.append(a2)
        P = P_save
        ps.append(shape_check(lambda c, uv, z: tmap(RCb[c], uv, z), Ph))
        held_views(lambda c, uv, z: tmap(RCb[c], uv, z), Ph, k)
    pa, pr, ps = np.concatenate(pa), np.concatenate(pr), np.concatenate(ps)
    L.append(f"  HELD OUT by station ({B_FOLDS} folds): ray fit {np.median(pa):.0f} / {np.percentile(pa, 90):.0f} (n {len(pa)}), "
             f"release on the same corners {np.median(pr):.0f} / {np.percentile(pr, 90):.0f}; held-out plate shape median {np.median(ps):.1f} mm, p90 {np.percentile(ps, 90):.1f}")

# ---------------------------------------------------------------- check 2: the reviewed 20 Hz ball at 105 mm
TR = qc_paths.QC_ROOT / "2026-09-30" / "ball" / "track20"
H = json.loads((TR / "held20.json").read_text(encoding="utf-8"))
FL = json.loads((TR / "ball20_flags.json").read_text(encoding="utf-8")) if (TR / "ball20_flags.json").exists() else {"flags": []}
held = [(h["t0"], h["t1"]) for h in H["intervals"]]
wrong = {(f["cam"], f["entry"]) for f in FL["flags"] if f.get("flag") == "wrong"}


def ball_tracks(mapfn):
    out = {}
    for c in names:
        fr = json.loads((TR / f"ball20_{c}.json").read_text(encoding="utf-8"))["frames"]
        i = np.arange(len(fr)); a, b = np.polyfit(i, [f[0] for f in fr], 1)
        sel = np.array([k for k, f in enumerate(fr) if f[3]])
        uv = to_0918(c, [[fr[k][3]["cx"], fr[k][3]["cy"]] for k in sel])
        xy = mapfn(c, uv, 105.0); t = (a * i + b)[sel] - H["offsets_s"][c]
        k = np.isfinite(xy).all(1)
        for t0, t1 in held:
            k &= ~((t >= t0) & (t <= t1))
        k &= np.array([(c, int(e)) not in wrong for e in sel])
        o = np.argsort(t[k]); out[c] = (t[k][o], xy[k][o])
    return out


def interp(T, Pp, t, gap=0.25):
    j = np.searchsorted(T, t); ok = (j > 0) & (j < len(T)); j = np.clip(j, 1, len(T) - 1)
    t0, t1 = T[j - 1], T[j]; ok &= (t1 - t0) <= gap
    w = np.where(t1 > t0, (t - t0) / np.maximum(t1 - t0, 1e-9), 0.0)
    o = Pp[j - 1] + w[:, None] * (Pp[j] - Pp[j - 1]); o[~ok] = np.nan
    return o


def ball_check(mapfn):
    tr = ball_tracks(mapfn); d = collections.defaultdict(list)
    for a, b in itertools.combinations(names, 2):
        pb = interp(tr[b][0], tr[b][1], tr[a][0]); ok = np.isfinite(pb).all(1)
        if ok.sum() >= 20:
            d[f"{a}-{b}"] = list(np.hypot(*(tr[a][1][ok] - pb[ok]).T))
    allv = np.concatenate([np.array(v) for v in d.values()])
    return allv, d


rel_map_phys = lambda c, uv, z: rel[c].to_paddock(uv, z_mm=z)
L.append("CHECK 20 Hz ball at 105 mm (mm, median / p90 of two cameras at the aligned time; clocks of held20.json):")
for nm, f in (("release", rel_map_phys), ("ray fit", ray_map)):
    a, d = ball_check(f)
    L.append(f"  {nm:8s} all {np.median(a):.0f} / {np.percentile(a, 90):.0f} (n {len(a)}); " + ", ".join(f"{k} {np.median(v):.0f}" for k, v in sorted(d.items())))

# ---------------------------------------------------------------- check 3: west wall top (x = 0) seen by CH01 / CH02 / CH03, against the drone
def wall_profile(c, raycam=None):
    """heights (mm) where each pixel's ray meets x = 0, binned per 24 in along y."""
    uv = wall_pts(c, "X0")
    if raycam is not None:
        d = raycam.rays(uv); C = raycam.centre
        s = (0.0 - C[0]) / d[:, 0]; X = C + s[:, None] * d
        y, z = X[:, 1], X[:, 2]
    else:
        cm = rel[c]; d = cm.rays(uv); s_ = np.linspace(0, 16000, 4001)
        y, z = [], []
        for di in d:
            Xs = cm.centre + s_[:, None] * di; ph = pm.fit_to_physical(Xs[:, :2], cm.correction)
            f = ph[:, 0]; k = np.where(np.sign(f[:-1]) != np.sign(f[1:]))[0]
            if not len(k):
                y.append(np.nan); z.append(np.nan); continue
            k = k[0]; w = f[k] / (f[k] - f[k + 1]); y.append((1 - w) * ph[k, 1] + w * ph[k + 1, 1]); z.append((1 - w) * Xs[k, 2] + w * Xs[k + 1, 2])
        y, z = np.array(y), np.array(z)
    return {b: float(np.nanmedian(z[(y / IN >= b) & (y / IN < b + 24)])) for b in range(0, 240, 24) if ((y / IN >= b) & (y / IN < b + 24)).sum() >= 3}


dr = json.loads((qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all" / "anchor" / "anchor.json").read_text(encoding="utf-8"))
L.append("CHECK wall tops against the drone profile (camera minus drone, mm, median / n per camera and wall"
         + (f"; {WT_HOLD} held out of the fit" if WT_HOLD else "") + ("; the other walls are IN the fit" if USE_WALLTOP else "") + "):")
for nm, mk in (("release", None), ("ray fit", 1)):
    parts = []
    for c in names:
        for wall in WALLS:
            sel = [o for o in WT_OBS if o[0] == c and o[4] == wall]
            if not sel:
                continue
            uv = np.array([o[1] for o in sel])
            if mk is None:
                Xs = []
                for di in rel[c].rays(uv):                               # release: step along the ray through the ground warp
                    s_ = np.linspace(0, 16000, 4001); Xr = rel[c].centre + s_[:, None] * di
                    ph = pm.fit_to_physical(Xr[:, :2], rel[c].correction); ax, pl = WALLS[wall]
                    f = ph[:, ax] - pl; k = np.where(np.sign(f[:-1]) != np.sign(f[1:]))[0]
                    if not len(k):
                        Xs.append([np.nan] * 3); continue
                    k = k[0]; w = f[k] / (f[k] - f[k + 1]); qq = (1 - w) * ph[k] + w * ph[k + 1]
                    Xs.append([qq[0], qq[1], (1 - w) * Xr[k, 2] + w * Xr[k + 1, 2]])
                Xs = np.array(Xs)
            else:
                Xs = wall_cut(RC[c].centre, RC[c].rays(uv), wall)
            ok = np.isfinite(Xs).all(1)
            e = Xs[ok, 2] - wt_target(wall, Xs[ok, 1 - WALLS[wall][0]] / IN)
            parts.append(f"{c} {wall} {np.median(e):+.0f}/{ok.sum()}")
    L.append(f"  {nm:8s} " + "; ".join(parts))
L.append("CHECK west wall top (x = 0): height (mm) per 24 in along y")
for nm, maker in (("release", lambda c: None), ("ray fit", lambda c: RC[c])):
    prof = {c: wall_profile(c, maker(c)) for c in ("CH01", "CH02", "CH03")}
    bins = sorted({b for p in prof.values() for b in p})
    L.append(f"  {nm}:  y " + " ".join(f"{b:>5d}" for b in bins))
    for c, p in prof.items():
        L.append(f"     {c}: " + " ".join(f"{p.get(b, np.nan):5.0f}" for b in bins))
    spread = [np.ptp([prof[c][b] for c in prof if b in prof[c]]) for b in bins if sum(b in prof[c] for c in prof) >= 2]
    L.append(f"     spread between cameras per bin: median {np.median(spread):.0f} mm, max {np.max(spread):.0f} mm")
L.append("")

# ---------------------------------------------------------------- check 4: held-out 09-30 cones (K-fold)
supp = sorted({o[5] for o in OBS if o[3] == "cone" and not o[5].endswith("@0918")})
rng = np.random.default_rng(0); perm = rng.permutation(supp); folds = [set(perm[k::FOLDS]) for k in range(FOLDS)]   # --folds 0: none
pair_ray, pair_rel = [], []
for k, fold in enumerate(folds):
    use = np.array([not (o[3] == "cone" and o[5] in fold) for o in OBS])
    RCk, _, _ = fit(use, [j for j in IDS if j not in fold])
    pos_ray, pos_rel = collections.defaultdict(dict), collections.defaultdict(dict)
    for i, o in enumerate(OBS):
        if o[3] == "cone" and o[5] in fold:
            pos_ray[o[5]][o[0]] = tmap(RCk[o[0]], np.atleast_2d(o[1]), CONE_Z)[0]
            pos_rel[o[5]][o[0]] = rel[o[0]].to_paddock(o[1], z_mm=CONE_Z)
    for pos, out in ((pos_ray, pair_ray), (pos_rel, pair_rel)):
        for d in pos.values():
            for a, b in itertools.combinations(sorted(d), 2):
                if np.isfinite(d[a]).all() and np.isfinite(d[b]).all():
                    out.append(np.hypot(*(d[a] - d[b])))
if FOLDS > 0:
    L.append(f"CHECK held-out 09-30 cones ({FOLDS}-fold, two cameras on the same unseen cone, mm): ray fit {np.median(pair_ray):.0f} / "
             f"{np.percentile(pair_ray, 90):.0f} (n {len(pair_ray)}); release {np.median(pair_rel):.0f} / {np.percentile(pair_rel, 90):.0f} IN its fit "
             f"(10-02b was fitted on these cones; its own 5-fold held-out figure is 62 / 124, RELEASE_2026-10-02.md)")
if CORD_FOLDS:                                                           # check 6: each drone-measured cord held out, against the drone
    REFS, EXT = {}, {}
    for nm_, p_ in (("drone model 1", opt("--cord-ref", str(HERE / "drone_cords_2026-10-02.json"))), ("drone model 0", opt("--cord-ref2"))):
        if p_:
            _lj = json.loads(Path(p_).read_text(encoding="utf-8"))["lines"]
            REFS[nm_] = {k: cord_line(v, k) for k, v in _lj.items()}; EXT[nm_] = {k: v["extent_in"] for k, v in _lj.items()}
    SIM = {"drone model 1": lambda g_: np.atleast_2d(g_)}
    if "drone model 0" in REFS:                                          # model 1 frame -> model 0 frame: 2-D similarity, point to line
        m1, m0 = REFS["drone model 1"], REFS["drone model 0"]; c0 = np.array([240.0, 120.0]); smp = []
        for k_ in sorted(set(m1) & set(m0)):
            ax = 0 if k_.startswith("Y") else 1; n1 = m1[k_]
            lo, hi = max(EXT["drone model 1"][k_][0], EXT["drone model 0"][k_][0]), min(EXT["drone model 1"][k_][1], EXT["drone model 0"][k_][1])
            for a_ in np.linspace(lo, hi, 5):                            # points on the model-1 line at a_ along the cord
                q_ = np.zeros(2); q_[ax] = a_; q_[1 - ax] = (n1[2] - n1[ax] * a_) / n1[1 - ax]; smp.append((q_, m0[k_]))

        def _sim(x_, g_):
            R_ = np.array([[np.cos(x_[1]), -np.sin(x_[1])], [np.sin(x_[1]), np.cos(x_[1])]])
            return c0 + (1 + x_[0]) * (np.atleast_2d(g_) - c0) @ R_.T + x_[2:]
        xs = least_squares(lambda x_: [(_sim(x_, q_)[0] @ l_[:2] - l_[2]) for q_, l_ in smp], np.zeros(4), loss="soft_l1", f_scale=1.0).x
        SIM["drone model 0"] = lambda g_, xs=xs: _sim(xs, g_)
        L.append(f"CHECK cords held out one at a time, across the cord against the drone (mm; model 0 moved into model 1's frame: scale "
                 f"{100 * xs[0]:+.2f} %, rotation {np.degrees(xs[1]):+.2f} deg, shift ({xs[2] * IN:+.0f}, {xs[3] * IN:+.0f}) mm; its "
                 f"lines then differ from model 1's by {np.median([abs(_sim(xs, q_)[0] @ l_[:2] - l_[2]) for q_, l_ in smp]) * IN:.0f} mm median)")
    else:
        L.append("CHECK cords held out one at a time, across the cord against the drone (mm)")
    held_c, held_xy = collections.defaultdict(list), collections.defaultdict(list)   # (ref, cam, cord) -> signed offsets mm, where (in)
    for k_ in sorted({o[5].split("@")[0] for o in OBS if o[3] in ("x", "y", "line")} & set(REFS["drone model 1"])):
        use = np.array([o[5].split("@")[0] != k_ for o in OBS])
        RCk, _, _ = fit(use, IDS)
        for o in OBS:
            if o[5].split("@")[0] == k_:
                g_ = tmap(RCk[o[0]], np.atleast_2d(o[1]), 0.0)[0] / IN
                if np.isfinite(g_).all():
                    for ref in SIM:
                        if k_ in REFS[ref]:
                            l_ = REFS[ref][k_]; held_c[(ref, o[0], k_)].append(float((SIM[ref](g_)[0] @ l_[:2] - l_[2]) * IN))
                            held_xy[(ref, o[0], k_)].append([round(float(g_[0]), 1), round(float(g_[1]), 1)])
    for ref in SIM:
        allc = [abs(np.median(v)) for (r_, c_, k_), v in held_c.items() if r_ == ref and len(v) >= 3]
        allp = [abs(x_) for (r_, c_, k_), v in held_c.items() if r_ == ref for x_ in v]
        L.append(f"  vs {ref}: per camera and cord |median| {np.median(allc):.0f} mm (p90 {np.percentile(allc, 90):.0f}, n {len(allc)}); "
                 f"every label |offset| median {np.median(allp):.0f}, p90 {np.percentile(allp, 90):.0f} (n {len(allp)})")
        L.append("     " + "; ".join(f"{c_} {k_} {np.median(v):+.0f}/{len(v)}" for (r_, c_, k_), v in sorted(held_c.items(), key=lambda t: (t[0][1], t[0][2])) if r_ == ref))
    (OUT / "cord_heldout.json").write_text(json.dumps({f"{r_}|{c_}|{k_}": dict(offset_mm=[round(x_, 1) for x_ in v], xy_in=held_xy[(r_, c_, k_)]) for (r_, c_, k_), v in held_c.items()}, indent=0), encoding="utf-8")
seam = []                                                                # check 5: the pano's ground position across its stitch seam
for c in rm.PANO:
    W, Hh = qc_paths.upright_size(S18, c); vs = np.linspace(0.55, 0.95, 9) * Hh
    a_ = RC[c].to_paddock(np.c_[np.full(9, W / 2 - 1.0), vs], 60.0); b_ = RC[c].to_paddock(np.c_[np.full(9, W / 2 + 1.0), vs], 60.0)
    j = np.hypot(*(a_ - b_).T)
    seam.append(f"{c} max {np.nanmax(j):.0f} mm, median {np.nanmedian(j):.0f} mm over v 0.55-0.95 H")
L.append("CHECK stitch seam, ground jump at z 60 mm between the columns either side of u = W / 2: " + "; ".join(seam))
if VIEWS_HO:
    (OUT / "board_heldout.json").write_text(json.dumps(VIEWS_HO, indent=1), encoding="utf-8")
(OUT / "RAYMAP.json").write_text(json.dumps(dict(note="raymap.py ray-space correction on the release bundle; refit_rays.py",
                                                 bundle=str(pm.FIT), terrain=(Path(opt("--terrain")).name if TERR is not None else None), fit_sha256=__import__('hashlib').sha256(Path(pm.FIT).read_bytes()).hexdigest(), drone_cords=(Path(opt("--drone-cords")).name if DCORDS is not None else None), sweep=(Path(SWEEP_F).name + (" (" + SW_HOLD + " blocks held out)" if SW_HOLD else "") if SWEEP_F else None), deg=rm.DEG, sig_coef=SIG_COEF, centres=USE_CENTRES,
                                                 cameras={c: RC[c].todict() for c in names}), indent=1), encoding="utf-8")
(OUT / "REFIT_RAYS.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L)); print("->", OUT)
