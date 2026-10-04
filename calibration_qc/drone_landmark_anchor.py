# -*- coding: utf-8 -*-
r"""Move each drone_sfm.py model into the paddock frame with the operator's landmark labels (drone_landmark_gui.py),
then read off what the drone measures independently of the rig: the rig cameras' positions and the wall-top heights.

Each click becomes a 3-D point in its model: ground features (pole foot, cord, wall foot) are the click's ray cut
with the model's floor plane (RANSAC); raised features (pole top, beam, wall top, camera lens, tower, roof) take
the median depth of the model's own points seen within NEAR px of the click in that frame. A similarity
(scale, rotation, translation) per model is then fitted, robustly, to what is known in the paddock frame:
  pole foot / top  - on the vertical axis of pole <row><col> (x = 120 col in, y = 0 / 120 / 240 in), anywhere on
                     its rim (radius R_POLE: the clicked base or top is the pole's visible face, not its axis);
                     a foot also at z = 0
  cord Xk / Yk     - x = k or y = k in, z = 0 (cords lie on the grass)
  wall foot        - x = 0 / 480 in or y = 0 / 240 in, z = 0;  beam row / col - y or x of that pole line
  floor            - a sample of the model's floor inliers at z = 0 (fixes the vertical)
The camera lenses, wall tops, towers and roofs are NOT in the fit: they are the check. Poles are taken on the
design 10 ft grid until the operator's tape survey replaces it.

--kinds limits which landmark kinds enter the similarity (default foot,top,cord,wallfoot,beam; the floor always does):
--kinds foot is the lean-free anchor (2026-10-03, operator: the poles lean, so a pole top or a beam is not above its foot,
and the cords were laid by hand). Every run also reports each pole's lean as the drone sees it (median top minus
median foot, horizontal) - the foot clicks sit in the grass, so it is coarse.

Usage: python drone_landmark_anchor.py --name 2026-10-02_anchor --labels <drone_landmarks.json> [--models 1,2,3]
                                       [--kinds foot,top,cord,wallfoot,beam] [--out <dir>]
       (labels are matched by frame name, so labels made on one run's frames anchor any other run that registered them)
Output: <run>\anchor\ANCHOR_REPORT.txt, anchor.json (transforms, landmark positions), paddock_points_<m>.ply
"""
import sys, json, collections
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402
import pycolmap                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_anchor")
LAB = json.loads(Path(opt("--labels", str(RUN / "landmark_gui" / "drone_landmarks.json"))).read_text(encoding="utf-8"))
MODELS = opt("--models", "1,2,3").split(",")
OUT = Path(opt("--out", str(RUN / "anchor"))); OUT.mkdir(parents=True, exist_ok=True)
KINDS = set(opt("--kinds", "foot,top,cord,wallfoot,beam").split(","))
IN, R_POLE, NEAR = 0.0254, 0.15, 25.0                                    # m per in; pole radius m; px
SIG = dict(foot=0.10, top=0.10, cord=0.05, wallfoot=0.12, beam=0.10, floor=0.05)
ROWY = dict(A=0.0, B=120 * IN, C=240 * IN)
cams_rig = pm.load()
RIG = {}
for c, cm in cams_rig.items():
    xy = pm.fit_to_physical(cm.centre[None, :2], cm.correction)[0] / 1000
    RIG[f"{c} lens"] = np.r_[xy, cm.centre[2] / 1000]


def floor_plane(P, C):
    cc = C.mean(0); rad = 3 * np.percentile(np.linalg.norm(C - cc, axis=1), 95)
    Q = P[np.linalg.norm(P - cc, axis=1) < rad]
    L = np.linalg.norm(np.ptp(np.percentile(Q, [2, 98], axis=0), axis=0)); thr = 0.005 * L
    rng = np.random.default_rng(0); best = None
    for _ in range(4000):
        a, b, c = Q[rng.choice(len(Q), 3, replace=False)]
        n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn; inl = np.abs((Q - a) @ n) < thr
        if best is None or inl.sum() > best[0]:
            best = (inl.sum(), n, a, inl)
    _, n, a, inl = best
    if (C - a).mean(0) @ n < 0:
        n = -n
    F = Q[inl]; F0 = F.mean(0); w, V = np.linalg.eigh(np.cov((F - F0).T)); n = V[:, 0] * np.sign(V[:, 0] @ n)   # refit on inliers
    return n, F0, F


def kind(name):
    if name.endswith(" foot") and name[0] in "ABC": return "foot"
    if name.endswith(" top") and name[0] in "ABC" and name[1].isdigit(): return "top"
    if name.startswith("cord "): return "cord"
    if name.startswith("wall foot"): return "wallfoot"
    if name.startswith("wall top"): return "walltop"
    if name.startswith("beam "): return "beam"
    if name.endswith(" lens"): return "lens"
    return "other"


rep, out = [f"DRONE MODELS ANCHORED TO THE PADDOCK  run {RUN.name}; labels: {sum(len(f['points']) for f in LAB['frames'])} landmarks in "
            f"{len(LAB['frames'])} frames; poles on the design 10 ft grid, radius {R_POLE} m", ""], {}
allpts = []
for m in MODELS:
    rec = pycolmap.Reconstruction(str(RUN / "sparse" / m))
    imgs = {im.name: im for im in rec.images.values()}
    C = np.array([im.projection_center() for im in imgs.values()])
    P3 = {pid: p.xyz for pid, p in rec.points3D.items()}
    P = np.array(list(P3.values())); n, f0, F = floor_plane(P, C)
    obs = []                                                             # (landmark, kind, model point)
    for fr in LAB["frames"]:
        if fr["name"] not in imgs:                                      # labels belong to frames: any model of this run that has it
            continue
        im = imgs[fr["name"]]; cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
        Rm, tv = T.rotation.matrix(), T.translation; Cc = im.projection_center()
        kp = np.array([np.asarray(p.xy() if callable(p.xy) else p.xy, float) for p in im.points2D]); kid = np.array([p.point3D_id if p.has_point3D() else -1 for p in im.points2D])
        for name, val in fr["points"].items():
            clicks = val if isinstance(val[0], list) else [val]
            k = kind(name)
            for u, v in clicks:
                xn = cam.cam_from_img(np.array([[u, v]], float))[0]
                d = Rm.T @ np.r_[xn, 1.0]; d /= np.linalg.norm(d)
                if k in ("foot", "cord", "wallfoot"):
                    den = d @ n
                    if abs(den) < 1e-6:
                        continue
                    s = ((f0 - Cc) @ n) / den
                    if s <= 0:
                        continue
                    X = Cc + s * d
                else:
                    near = (np.hypot(*(kp - [u, v]).T) < NEAR) & (kid >= 0)
                    if not near.any():
                        continue
                    depth = np.median([(P3[i] - Cc) @ d for i in kid[near] if i in P3])
                    X = Cc + depth * d
                obs.append((name, k, X, fr["name"]))
    # initial similarity from pole feet (axis = the foot click, close enough to start)
    init = [(X, np.r_[120 * int(nm[1]) * IN, ROWY[nm[0]], 0.0]) for nm, k, X, _ in obs if k == "foot"]
    A = np.array([a for a, b in init]); B = np.array([b for a, b in init])
    if len(init) < 3:
        rep.append(f"model {m}: only {len(init)} pole feet - not anchored"); continue
    am, bm = A.mean(0), B.mean(0); H = (A - am).T @ (B - bm); U, S_, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]); R0 = Vt.T @ D @ U.T
    s0 = np.sqrt(((B - bm) ** 2).sum() / ((A - am) ** 2).sum()); t0 = bm - s0 * R0 @ am
    rng = np.random.default_rng(1); FS = F[rng.choice(len(F), min(300, len(F)), replace=False)]

    def tf(x, X):
        return np.exp(x[0]) * (np.atleast_2d(X) @ Rotation.from_rotvec(x[1:4]).as_matrix().T) + x[4:7]

    def res(x):
        r = []
        for nm, k, X, _ in obs:
            if k not in KINDS:
                continue
            Y = tf(x, X)[0]
            if k in ("foot", "top"):
                ax = np.r_[120 * int(nm[1]) * IN, ROWY[nm[0]]]
                r.append((np.hypot(*(Y[:2] - ax)) - R_POLE) / SIG[k])
                if k == "foot":
                    r.append(Y[2] / SIG["floor"])
            elif k == "cord":
                ax, val = (0, int(nm[6:]) * IN) if nm[5] == "X" else (1, int(nm[6:]) * IN)
                r += [(Y[ax] - val) / SIG["cord"], Y[2] / SIG["floor"]]
            elif k == "wallfoot":
                w = nm.split()[-1]; ax = 0 if w[0] == "X" else 1
                r += [(Y[ax] - int(w[1:]) * IN) / SIG["wallfoot"], Y[2] / SIG["floor"]]
            elif k == "beam":
                part = nm.split()
                r.append(((Y[1] - ROWY[part[2]]) if part[1] == "row" else (Y[0] - 120 * int(part[2]) * IN)) / SIG["beam"])
        r += list(tf(x, FS)[:, 2] / SIG["floor"])
        return np.array(r)

    x0 = np.r_[np.log(s0), Rotation.from_matrix(R0).as_rotvec(), t0]
    sol = least_squares(res, x0, loss="soft_l1", f_scale=2.0)
    x = sol.x; s_m = np.exp(x[0])
    by = collections.defaultdict(list)
    for nm, k, X, fr in obs:
        Y = tf(x, X)[0]
        if k in ("foot", "top"):
            e = abs(np.hypot(*(Y[:2] - [120 * int(nm[1]) * IN, ROWY[nm[0]]])) - R_POLE)
        elif k == "cord":
            e = abs(Y[0 if nm[5] == "X" else 1] - int(nm[6:]) * IN)
        elif k == "wallfoot":
            w = nm.split()[-1]; e = abs(Y[0 if w[0] == "X" else 1] - int(w[1:]) * IN)
        elif k == "beam":
            part = nm.split(); e = abs((Y[1] - ROWY[part[2]]) if part[1] == "row" else (Y[0] - 120 * int(part[2]) * IN))
        else:
            continue
        by[k].append(e)
    rep.append(f"model {m}: {len(imgs)} frames, {len(obs)} labelled clicks with a 3-D point; scale {s_m:.4f} m per model unit; "
               f"fitted to {', '.join(sorted(KINDS))} + floor")
    rep.append("  fit residuals (horizontal, mm; median / p90 / n): " + "; ".join(
        f"{k} {1000 * np.median(v):.0f} / {1000 * np.percentile(v, 90):.0f} / {len(v)}" for k, v in sorted(by.items())))
    zf = tf(x, FS)[:, 2]; rep.append(f"  floor sample z: median {1000 * np.median(zf):+.0f} mm, spread (p10-p90) {1000 * np.ptp(np.percentile(zf, [10, 90])):.0f} mm")
    # the checks: lenses, wall tops, beams' and pole tops' heights, towers / roofs
    lm = collections.defaultdict(list)
    for nm, k, X, fr in obs:
        lm[nm].append(tf(x, X)[0])
    for nm in sorted(lm):
        if kind(nm) == "lens":
            Y = np.median(lm[nm], 0); ref = RIG.get(nm)
            rep.append(f"  CHECK {nm}: drone ({Y[0]:.3f}, {Y[1]:.3f}, {Y[2]:.3f}) m"
                       + (f"; calibration ({ref[0]:.3f}, {ref[1]:.3f}, {ref[2]:.3f}); difference {1000 * np.linalg.norm(Y - ref):.0f} mm "
                          f"(dx {1000 * (Y[0] - ref[0]):+.0f}, dy {1000 * (Y[1] - ref[1]):+.0f}, dz {1000 * (Y[2] - ref[2]):+.0f}), clicks {len(lm[nm])}" if ref is not None else ""))
    for nm in sorted(lm):
        if kind(nm) == "walltop":
            Y = np.array(lm[nm]); w = nm.split()[-1]; along = 1 if w[0] == "X" else 0
            o = np.argsort(Y[:, along])
            rep.append(f"  CHECK {nm}: height {1000 * np.median(Y[:, 2]):.0f} mm median over {len(Y)} clicks; along-wall profile (in: mm) "
                       + ", ".join(f"{Y[i, along] / IN:.0f}: {1000 * Y[i, 2]:.0f}" for i in o))
    for nm in sorted(lm):
        if kind(nm) in ("top", "beam", "other"):
            Y = np.array(lm[nm]); rep.append(f"  {nm}: ({np.median(Y[:, 0]) / IN:.0f}, {np.median(Y[:, 1]) / IN:.0f}) in, height {1000 * np.median(Y[:, 2]):.0f} mm, n {len(Y)}")
    for row in "ABC":                                                    # each pole's lean: top minus foot, horizontal
        for col in range(5):
            ft, tp = lm.get(f"{row}{col} foot"), lm.get(f"{row}{col} top")
            if ft and tp:
                F_, T_ = np.median(ft, 0), np.median(tp, 0); d_ = T_[:2] - F_[:2]; h_ = T_[2] - F_[2]
                rep.append(f"  LEAN {row}{col}: top - foot ({1000 * d_[0]:+.0f}, {1000 * d_[1]:+.0f}) mm over {1000 * h_:.0f} mm = "
                           f"{np.degrees(np.arctan2(np.hypot(*d_), h_)):.1f} deg (feet {len(ft)}, tops {len(tp)} clicks)")
    rep.append("")
    out[m] = dict(scale=s_m, rotvec=x[1:4].tolist(), t=x[4:7].tolist(), n_obs=len(obs),
                  landmarks={nm: np.median(v, 0).tolist() for nm, v in lm.items()})
    Pp = tf(x, P); keep = (np.abs(Pp[:, 0] - 6.1) < 9) & (np.abs(Pp[:, 1] - 3.05) < 7) & (Pp[:, 2] > -0.6) & (Pp[:, 2] < 3.5)
    col = np.array([p.color for p in rec.points3D.values()], np.uint8)[keep]
    allpts.append((m, Pp[keep], col))
    arr = np.zeros(keep.sum(), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    arr["x"], arr["y"], arr["z"] = Pp[keep].T; arr["r"], arr["g"], arr["b"] = col.T
    with open(OUT / f"paddock_points_{m}.ply", "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\ncomment drone model {m} in the paddock frame (m; x along the length from "
                 f"pole A0, y across, z up)\nelement vertex {len(arr)}\nproperty float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode()); f.write(arr.tobytes())
(OUT / "ANCHOR_REPORT.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")
(OUT / "anchor.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
np.savez_compressed(OUT / "paddock_points_all.npz", **{f"m{m}_xyz": a for m, a, c in allpts}, **{f"m{m}_rgb": c for m, a, c in allpts})
print("\n".join(rep)); print("->", OUT)
