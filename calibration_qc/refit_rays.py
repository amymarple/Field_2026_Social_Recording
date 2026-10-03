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
--walltop adds the first data above the ground: the operator's wall-top polylines in the cameras (analysis repo,
2026c landmarks, as walltop_check.py) must meet the wall's design plane at the drone's wall-top height there
(drone_walltop.py, on the tape's ground; weight WT_W); --walltop-hold <wall> leaves one wall out for the check.

Checks (none of them in the fit): boards 09-18/19 (two cameras on the same corner, z 6 mm); a 5-fold over the 09-30
cones (refit without the fold, score its cones); the reviewed 20 Hz ball at 105 mm (fixed clock offsets, held and
wrong frames out); the west wall top cut by CH01 / CH02 / CH03 against each other and the drone profile; the camera
centres against the tape. Each check is computed the same way for the release (bundle + object-space warp).

Usage: python refit_rays.py --out <dir> [--deg 3] [--sig-coef 0.03] [--no-centres] [--old-drone] [--walltop]
                              [--walltop-hold X0] [--wt-w 0.5] [--seam-w-deg 0] [--folds 5]
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
rm.DEG = int(opt("--deg", "3"))
rm.SEAM_W = float(opt("--seam-w-deg", "0")) * np.pi / 180      # stitch blend band of the panos (0 = step)
SIG_COEF = float(opt("--sig-coef", "0.03"))
USE_CENTRES = "--no-centres" not in args
FOLDS = int(opt("--folds", "5"))
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
WT = json.loads((qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all" / "walltop_profile.json").read_text(encoding="utf-8"))["walls"]


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
TAPE = {c: np.array([v["x_in"] * IN, v["y_in"] * IN, v["h_m"] * 1000]) for c, v in cc["tape"].items()}
DRONE = {c: np.array([v["x_m"], v["y_m"], v["z_m"]]) * 1000 * k_drone for c, v in cc["drone"].items()}
TRI = {} if "--old-drone" in args else {c: np.array([v["x_m"], v["y_m"], v["z_m"]]) * 1000 * k_drone for c, v in cc.get("drone_tri", {}).items()}
DIST, HDIFF = [], []
if TRI:                                                                  # tape heights; drone distances and height differences
    HEIGHT = {c: (TAPE[c][2], 30.0) for c in names if c in TAPE}
    for a, b in itertools.combinations(names, 2):
        if a in TAPE and b in TAPE:
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


def unpack(x, ids):
    o, coef, dC = 0, {}, {}
    for c in names:
        coef[c] = x[o:o + 2 * NT[c]].reshape(2, NT[c]); o += 2 * NT[c]
        dC[c] = x[o:o + 3]; o += 3
    P = x[o:o + 2 * len(ids)].reshape(-1, 2)
    return coef, dC, P


def fit(use, ids):
    """use: boolean mask over OBS; ids: the latent cone ids. -> (RayCams, P per id, solution)"""
    jx = {j: i for i, j in enumerate(ids)}
    design = np.array([POS[j.replace("@0918", "")] for j in ids], float).reshape(-1, 2)
    nx = sum(2 * NT[c] + 3 for c in names) + 2 * len(ids)
    x0 = np.zeros(nx); x0[-2 * len(ids):] = design.ravel() if ids else []
    per = {c: [i for i in Q[c] if use[i]] for c in names}
    loc = {c: np.array([Q[c].index(i) for i in per[c]], int) for c in names}

    def resid(x):
        coef, dC, P = unpack(x, ids)
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
    assert row == len(r0), (row, len(r0))
    sol = least_squares(resid, x0, jac_sparsity=J, loss="soft_l1", f_scale=3.0, x_scale="jac", max_nfev=200)
    coef, dC, P = unpack(sol.x, ids)
    return {c: rm.RayCam(cams[c], coef[c], dC[c]) for c in names}, dict(zip(ids, P)), sol


ALL = np.ones(len(OBS), bool)
IDS = sorted({o[5] for o in OBS if o[3] == "cone"})
t0 = time.time()
RC, PJ, sol = fit(ALL, IDS)
L = [f"RAY-SPACE GROUND CORRECTION  bundle {pm.FIT} (unchanged); degree {rm.DEG}, coefficient prior {SIG_COEF}, "
     f"seam {'step' if rm.SEAM_W == 0 else f'ramp over {np.degrees(rm.SEAM_W):.0f} deg'}; "
     f"centre constraints {('tape + triangulated drone lenses' if TRI else 'tape + drone (distances, heights)') if USE_CENTRES else 'none'}; "
     f"wall tops {('in the fit (weight ' + str(WT_W) + (', ' + WT_HOLD + ' held out' if WT_HOLD else '') + ')') if USE_WALLTOP else 'not in the fit'}",
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
        e = np.hypot(*(g - PJ[j])) if kind == "cone" else abs(g[0] - tgt) if kind == "x" else abs(g[1] - tgt)
        lab_res[(c, kind)].append(e)
L.append("label residuals (in, median / p90): " + "; ".join(f"{c} {k} {np.median(v):.1f}/{np.percentile(v, 90):.1f}" for (c, k), v in sorted(lab_res.items())))
L.append("camera centres (in, tape-frame-free): " + "; ".join(f"{c} dC ({RC[c].dC[0] / IN:+.1f}, {RC[c].dC[1] / IN:+.1f}, {RC[c].dC[2] / IN:+.1f})" for c in names))
for a, b, d, s in DIST:
    if a in TAPE and b in TAPE:
        L.append(f"  distance {a}-{b}: tape {d / IN:.1f} in; release {np.hypot(*(cams[a].centre[:2] - cams[b].centre[:2])) / IN:.1f}; "
                 f"ray fit {np.hypot(*(RC[a].centre[:2] - RC[b].centre[:2])) / IN:.1f}")
for a, b, d, s in DIST:
    if a in TRI and b in TRI and not (a in TAPE and b in TAPE):
        L.append(f"  distance {a}-{b}: drone {d / IN:.1f} in; release {np.hypot(*(cams[a].centre[:2] - cams[b].centre[:2])) / IN:.1f}; "
                 f"ray fit {np.hypot(*(RC[a].centre[:2] - RC[b].centre[:2])) / IN:.1f}")
L.append("  heights (m): " + ", ".join(f"{c} release {cams[c].centre[2] / 1000:.3f} fit {RC[c].centre[2] / 1000:.3f} target {HEIGHT[c][0] / 1000:.3f}" for c in names if c in HEIGHT))
L.append("")

# ---------------------------------------------------------------- check 1: boards (two cameras on the same corner, z 6 mm)
P = [p for p in fd.all_placements() if not p["bad"] and not p["weak"]]
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
ray_map = lambda c, uv, z: RC[c].to_paddock(uv, z)
L.append("CHECK boards (mm, median / p90 of two cameras on the same corner):")
for nm, f in (("release", rel_map), ("ray fit", ray_map)):
    a, d = board_check(f)
    L.append(f"  {nm:8s} all {np.median(a):.0f} / {np.percentile(a, 90):.0f} (n {len(a)}); " + ", ".join(f"{k} {np.median(v):.0f}" for k, v in sorted(d.items()) if len(v) >= 20))

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
rng = np.random.default_rng(0); perm = rng.permutation(supp); folds = [set(perm[k::FOLDS]) for k in range(FOLDS)]
pair_ray, pair_rel = [], []
for k, fold in enumerate(folds):
    use = np.array([not (o[3] == "cone" and o[5] in fold) for o in OBS])
    RCk, _, _ = fit(use, [j for j in IDS if j not in fold])
    pos_ray, pos_rel = collections.defaultdict(dict), collections.defaultdict(dict)
    for i, o in enumerate(OBS):
        if o[3] == "cone" and o[5] in fold:
            pos_ray[o[5]][o[0]] = RCk[o[0]].to_paddock(o[1], CONE_Z)[0]
            pos_rel[o[5]][o[0]] = rel[o[0]].to_paddock(o[1], z_mm=CONE_Z)
    for pos, out in ((pos_ray, pair_ray), (pos_rel, pair_rel)):
        for d in pos.values():
            for a, b in itertools.combinations(sorted(d), 2):
                if np.isfinite(d[a]).all() and np.isfinite(d[b]).all():
                    out.append(np.hypot(*(d[a] - d[b])))
L.append(f"CHECK held-out 09-30 cones ({FOLDS}-fold, two cameras on the same unseen cone, mm): ray fit {np.median(pair_ray):.0f} / "
         f"{np.percentile(pair_ray, 90):.0f} (n {len(pair_ray)}); release {np.median(pair_rel):.0f} / {np.percentile(pair_rel, 90):.0f} IN its fit "
         f"(10-02b was fitted on these cones; its own 5-fold held-out figure is 62 / 124, RELEASE_2026-10-02.md)")
seam = []                                                                # check 5: the pano's ground position across its stitch seam
for c in rm.PANO:
    W, Hh = qc_paths.upright_size(S18, c); vs = np.linspace(0.55, 0.95, 9) * Hh
    a_ = RC[c].to_paddock(np.c_[np.full(9, W / 2 - 1.0), vs], 60.0); b_ = RC[c].to_paddock(np.c_[np.full(9, W / 2 + 1.0), vs], 60.0)
    j = np.hypot(*(a_ - b_).T)
    seam.append(f"{c} max {np.nanmax(j):.0f} mm, median {np.nanmedian(j):.0f} mm over v 0.55-0.95 H")
L.append("CHECK stitch seam, ground jump at z 60 mm between the columns either side of u = W / 2: " + "; ".join(seam))
(OUT / "RAYMAP.json").write_text(json.dumps(dict(note="raymap.py ray-space correction on the release bundle; refit_rays.py",
                                                 bundle=str(pm.FIT), fit_sha256=__import__('hashlib').sha256(Path(pm.FIT).read_bytes()).hexdigest(), deg=rm.DEG, sig_coef=SIG_COEF, centres=USE_CENTRES,
                                                 cameras={c: RC[c].todict() for c in names}), indent=1), encoding="utf-8")
(OUT / "REFIT_RAYS.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L)); print("->", OUT)
