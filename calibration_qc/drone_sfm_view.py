# -*- coding: utf-8 -*-
r"""A 3-D view of a drone_sfm.py model: the points near the paddock, levelled on the floor (RANSAC plane, z = 0), the
long axis along x, and scaled so the floor is 40 ft long - an APPROXIMATE metric scale until surveyed points tie
the model to the paddock. Writes a self-contained HTML viewer (three.js, rotate / zoom with mouse or fingers) and a
binary PLY for desktop point-cloud software (CloudCompare, MeshLab).

Usage: python drone_sfm_view.py [--name 2026-10-02] [--model 1] [--max-err 1.5]
Output: <qc root>\drone_sfm\<run>\paddock_3d.html, paddock_points.ply
"""
import sys, json, base64
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02")
MODEL, MAX_ERR, FLOOR_M = opt("--model", "1"), float(opt("--max-err", "1.5")), 480 * 0.0254
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
pts = [p for p in rec.points3D.values() if p.error < MAX_ERR]
P = np.array([p.xyz for p in pts]); C = np.array([p.color for p in pts], np.uint8)
ims = sorted(rec.images.values(), key=lambda im: im.name)
cam = np.array([im.projection_center() for im in ims])
# floor plane: RANSAC on all points, normal towards where the drone flew
rng = np.random.default_rng(0); scale = np.linalg.norm(np.ptp(np.percentile(P, [2, 98], axis=0), axis=0)); best = None
for _ in range(4000):
    a, b, c = P[rng.choice(len(P), 3, replace=False)]
    n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
    if nn < 1e-12:
        continue
    n /= nn; k = int((np.abs((P - a) @ n) < 0.004 * scale).sum())
    if best is None or k > best[0]:
        best = (k, n, a)
_, n, a = best
if (cam - a).mean(0) @ n < 0:
    n = -n
u = np.cross(n, [1.0, 0, 0]); u /= np.linalg.norm(u); v = np.cross(n, u)
X = np.c_[(P - a) @ u, (P - a) @ v, (P - a) @ n]; K = np.c_[(cam - a) @ u, (cam - a) @ v, (cam - a) @ n]
# keep the paddock (near the flight), floor axes by PCA, origin at the floor centre
cc = K[:, :2].mean(0); rad = 3.0 * np.percentile(np.hypot(*(K[:, :2] - cc).T), 95)
keep = np.hypot(*(X[:, :2] - cc).T) < rad
X, C = X[keep], C[keep]
g = X[np.abs(X[:, 2]) < 0.004 * scale][:, :2]; gm = g.mean(0)
w, V = np.linalg.eigh(np.cov((g - gm).T)); R = V[:, ::-1].T
X[:, :2] = (X[:, :2] - gm) @ R.T; K[:, :2] = (K[:, :2] - gm) @ R.T
# approximate scale: floor length along x from the density of floor points (walls stop the floor)
gx = (g - gm) @ R.T
hist, edges = np.histogram(gx[:, 0], bins=200); dense = np.where(hist > 0.2 * np.median(hist[hist > 0]))[0]
L = edges[dense[-1] + 1] - edges[dense[0]]
s = FLOOR_M / L
X *= s; K *= s
m = (X[:, 2] > -0.6) & (X[:, 2] < 3.5) & (np.abs(X[:, 0]) < 9) & (np.abs(X[:, 1]) < 7)    # the paddock and its walls
X, C = X[m], C[m]
print(f"{len(pts)} points with error < {MAX_ERR}px, {len(X)} near the paddock; floor length {L:.2f} model units -> scale {s:.3f} m/unit")
# PLY (levelled, approximate metres)
Xk = X.astype(np.float32)
with open(RUN / "paddock_points.ply", "wb") as f:
    f.write((f"ply\nformat binary_little_endian 1.0\ncomment drone_sfm {RUN.name} model {MODEL}: floor z = 0, long axis x, "
             f"approximate metres (floor scaled to 40 ft)\nelement vertex {len(Xk)}\nproperty float x\nproperty float y\n"
             "property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
    rec_arr = np.zeros(len(Xk), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec_arr["x"], rec_arr["y"], rec_arr["z"] = Xk.T; rec_arr["r"], rec_arr["g"], rec_arr["b"] = C.T
    f.write(rec_arr.tobytes())
data = dict(n=len(X), pos=base64.b64encode(np.round(X * 1000).astype("<i2").tobytes()).decode(),
            col=base64.b64encode(C.astype(np.uint8).tobytes()).decode(),
            path=np.round(K, 3).tolist(), frames=len(ims), points_total=len(rec.points3D),
            reproj=round(rec.compute_mean_reprojection_error(), 2), run=RUN.name, scale=round(s, 4))
html = (Path(__file__).resolve().parent / "drone_sfm_view_template.html").read_text(encoding="utf-8")
(RUN / "paddock_3d.html").write_text(html.replace("__DATA__", json.dumps(data)), encoding="utf-8")
print("->", RUN / "paddock_3d.html", "and", RUN / "paddock_points.ply")
