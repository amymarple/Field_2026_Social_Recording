# -*- coding: utf-8 -*-
r"""The drone as the absolute reference where only ONE camera sees the ground (2026-10-03; operator: the poles lean, so
only the drone can give absolute positions). The long cords Y39 / Y201 run through the strips that only CH02 / CH01 see,
the cross cords X24 ... X456 through both. A cord is a taut straight line: the operator's clicks on it in several drone
frames are rays from the registered poses, and the ONE 3-D line closest to all of them is the cord (no ground height and
no design position assumed). Moved into the paddock frame by the landmark anchor (design-grid scale).

Each camera's labels of the same cords (09-30 line labels carried to the 09-18 pixels, 09-18 T cords) are mapped onto
the local ground with the release and compared with the drone's line: the perpendicular distance, per 24 in along the
cord. Where only one camera sees a cord stretch, that is that camera's absolute ground error there (across the cord).

The json also keeps each line's clicked extent (in, along the cord): refit_rays.py --drone-cords takes these lines as the
cords' true positions (drone_cords_<date>.json in this folder is the copy it reads).

Usage: python drone_line_check.py [--rays release|<json>|warp] [--name 2026-10-02_all] [--model 1] [--out <dir>]
Output: <out, default <qc root>\drone_line_check>\DRONE_LINE_CHECK.txt (+ drone_line_check.json)
"""
import sys, json, re
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm                                        # noqa: E402  (cv2 first)
import pycolmap                                                          # noqa: E402
from scipy.optimize import least_squares                                 # noqa: E402
from scipy.spatial.transform import Rotation                             # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RAYS = opt("--rays", "release")
cams = pm.load(rays=None if RAYS == "warp" else RAYS)
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all"); M = opt("--model", "1")
OUT = Path(opt("--out", qc_paths.QC_ROOT / "drone_line_check")); OUT.mkdir(parents=True, exist_ok=True)
IN = 25.4
rec = pycolmap.Reconstruction(str(RUN / "sparse" / (M + "_ch04" if (RUN / "sparse" / (M + "_ch04")).exists() else M)))
imgs = {im.name: im for im in rec.images.values()}
A = json.loads((RUN / "anchor" / "anchor.json").read_text(encoding="utf-8"))[M]
s, Rm, t = A["scale"], Rotation.from_rotvec(A["rotvec"]).as_matrix(), np.asarray(A["t"])
LABELS = [HERE / "session_2026-10-02_drone_landmarks.json", RUN / "landmark_gui_cams" / "drone_landmarks_cams.json",
          RUN / "landmark_gui_ch04" / "drone_landmarks_ch04.json"]
rays = {}                                                                # cord -> list of (C, d) in paddock mm
for f in LABELS:
    if not f.exists():
        continue
    for fr in json.loads(f.read_text(encoding="utf-8"))["frames"]:
        if fr["name"] not in imgs:
            continue
        im = imgs[fr["name"]]; cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
        C = (s * Rm @ im.projection_center() + t) * 1000
        for name, val in fr["points"].items():
            if not name.startswith("cord "):
                continue
            uv = np.atleast_2d(np.asarray(val, float)); xn = cam.cam_from_img(uv)
            d = (np.c_[xn, np.ones(len(xn))] @ T.rotation.matrix()) @ Rm.T; d /= np.linalg.norm(d, axis=1, keepdims=True)
            rays.setdefault(name[5:], []).extend((C, di, fr["name"]) for di in d)


def fit_line(R):
    """the 3-D line closest to all rays (robust): point p0 and unit direction u."""
    C = np.array([r[0] for r in R]); D = np.array([r[1] for r in R])
    lam = -C[:, 2] / D[:, 2]; G = C + lam[:, None] * D                   # start: where the rays meet z = 0
    g0 = G.mean(0); _, _, Vt = np.linalg.svd(G - g0); u0 = Vt[0]

    def res(x):
        p0, u = x[:3], x[3:] / np.linalg.norm(x[3:]); n = np.cross(u, D)
        return np.einsum("ij,ij->i", C - p0, n) / np.linalg.norm(n, axis=1)
    sol = least_squares(res, np.r_[g0, u0], loss="soft_l1", f_scale=20.0)
    p0, u = sol.x[:3], sol.x[3:] / np.linalg.norm(sol.x[3:])
    lam = (p0[2] - C[:, 2]) / D[:, 2]; t = (C + lam[:, None] * D - p0) @ u   # where the clicks are along the line
    return p0, u, np.abs(res(sol.x)), (p0 + t.min() * u, p0 + t.max() * u)


lines = {}
for name, R in rays.items():
    if len({r[2] for r in R}) >= 2 and len(R) >= 6:
        p0, u, r, ends = fit_line(R)
        ax = 0 if name.startswith("Y") else 1                            # a Y cord runs along x, an X cord along y
        ext = sorted(e[ax] / IN for e in ends)
        lines[name] = (p0, u, float(np.median(r)), len(R), len({r_[2] for r_ in R}), ext)
# camera labels of the same cords
DRIFT = json.loads((HERE / "session_2026-09-30_drift_final.json").read_text(encoding="utf-8"))["cameras"]
S18, Q18 = qc_paths.resolve(None); S30, Q30 = qc_paths.resolve("2026-09-30")


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = DRIFT.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        Am = np.asarray(d["affine_30_to_18"], float); return uv @ Am[:, :2].T + Am[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    Rr = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ Rr / d["scale"]


cam_pts = {}                                                             # (cam, cord) -> mapped points (mm)
for cam in cams:
    for sess, Q, carry in ((S18, Q18, False), (S30, Q30, True)):
        f = Q / f"line_labels_{cam}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(sess, cam); dw, dh = d.get("frame_size_upright", [uw, uh]); sc = np.array([uw / float(dw), uh / float(dh)])
        for k, v in d["lines"].items():
            if not re.fullmatch(r"[XY]\d+", k) or not v:
                continue
            uv = np.asarray(v, float).reshape(-1, 2) * sc
            uv = to_0918(cam, uv) if carry else uv
            g = cams[cam].to_paddock(uv, 0.0)
            g = g[np.isfinite(g).all(1)]
            if len(g):
                cam_pts.setdefault((cam, k), []).append(g)
L = [f"DRONE LINE CHECK  cameras: {RAYS}; drone {RUN.name} model {M}, anchor scale {s:.4f}; cords triangulated as 3-D lines from the "
     "operator's drone clicks; camera labels mapped onto the local ground", "",
     "drone cords: name, rays / frames, rays' miss of the fitted line (median mm), height (mm, middle), direction (deg from x), "
     "clicked extent along the cord (in), offset from design at the extent's ends (mm, + = larger x / y)"]
for name, (p0, u, r, n, nf, ext) in sorted(lines.items()):
    ax = 0 if name.startswith("Y") else 1; tgt = float(name[1:]) * IN
    off = [(p0[1 - ax] + (e * IN - p0[ax]) / u[ax] * u[1 - ax]) - tgt for e in ext]
    L.append(f"  {name:5s} {n:3d} / {nf:2d}   {r:5.1f}   z {p0[2]:+5.0f}   {np.degrees(np.arctan2(u[1], u[0])) % 180:6.1f}   "
             f"{ext[0]:4.0f} - {ext[1]:4.0f}   {off[0]:+5.0f} / {off[1]:+5.0f}")
L += ["", "camera minus drone, perpendicular to the cord in the ground plane (mm), median per 48 in along the cord (n points):"]
out = {}
for (cam, k), G in sorted(cam_pts.items()):
    if k not in lines:
        continue
    G = np.concatenate(G); p0, u = lines[k][0], lines[k][1]
    u2 = u[:2] / np.linalg.norm(u[:2]); nrm = np.array([-u2[1], u2[0]])
    along = (G - p0[:2]) @ u2; perp = (G - p0[:2]) @ nrm
    if k.startswith("Y"):                                                # report along x, signed in +y
        sgn = np.sign(nrm[1]); pos = G[:, 0] / IN
    else:
        sgn = np.sign(nrm[0]); pos = G[:, 1] / IN
    perp = perp * sgn
    bins = np.arange(0, 481, 48) if k.startswith("Y") else np.arange(0, 241, 48)
    parts = []
    for b0, b1 in zip(bins[:-1], bins[1:]):
        m = (pos >= b0) & (pos < b1)
        if m.sum() >= 3:
            parts.append(f"{b0:3.0f}-{b1:3.0f}: {np.median(perp[m]):+5.0f} ({m.sum()})")
    out[f"{cam} {k}"] = dict(median_mm=float(np.median(perp)), n=int(len(perp)))
    L.append(f"  {cam} {k:5s} all {np.median(perp):+5.0f} mm (|median| {np.median(np.abs(perp)):.0f}, n {len(perp)})  along: " + "; ".join(parts))
(OUT / "DRONE_LINE_CHECK.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / "drone_line_check.json").write_text(json.dumps(dict(
    source=f"drone_line_check.py, drone run {RUN.name} model {M}, anchor scale {s:.4f}; paddock frame mm (landmark anchor)",
    lines={k: dict(p0=v[0].round(1).tolist(), u=v[1].round(5).tolist(), miss_mm=round(v[2], 1), n=v[3], frames=v[4],
                   extent_in=[round(e, 1) for e in v[5]]) for k, v in lines.items()}, cameras=out), indent=1), encoding="utf-8")
print("\n".join(L))
