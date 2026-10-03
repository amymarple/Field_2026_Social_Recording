# -*- coding: utf-8 -*-
r"""Metric scale of a drone_sfm.py model from the ChArUco plate the operator laid on the ground and filmed
(2026-10-02): board_detect.detect (the calibration's own detector) on the model's frames, each corner triangulated
from every registered frame that decoded it (linear least squares on the model's own camera poses), then a
similarity fitted between the triangulated corners and the printed pattern (60 mm squares). Its scale is mm per
model unit, independent of the design pole grid that drone_landmark_anchor.py uses; the residual says how well the
model reproduces a flat 720 x 540 mm pattern.

Usage: python drone_board_scale.py --name 2026-10-02_all [--model 1] [--frames <json of frame names>]
Output: <run>\board_scale.json and printed report
"""
import sys, json
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, board_detect as bd                                       # noqa: E402
import pycolmap                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
MODEL = opt("--model", "1")
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
imgs = {im.name: im for im in rec.images.values()}
cand = json.loads(Path(opt("--frames", str(RUN / "board_frames.json"))).read_text(encoding="utf-8"))
obs = {}                                                                 # corner id -> list of (centre, unit ray)
used = []
for short in sorted(cand):
    name = next((n for n in imgs if n.endswith(short)), None)
    if name is None:
        continue
    g = cv2.imread(str(RUN / "images" / name), cv2.IMREAD_GRAYSCALE)
    r = bd.detect(g)
    if not r or r[0] in (None, "located") or len(r[2]) < 8:
        continue
    method, px, ids = r[0], np.asarray(r[1], float), np.asarray(r[2], int)
    im = imgs[name]; cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
    R, C = T.rotation.matrix(), im.projection_center()
    xn = cam.cam_from_img(px)
    d = np.c_[xn, np.ones(len(xn))] @ R; d /= np.linalg.norm(d, axis=1, keepdims=True)
    for i, di in zip(ids, d):
        obs.setdefault(int(i), []).append((C, di))
    used.append((name, method, len(ids)))
X, ID = [], []
for i, rays in obs.items():
    if len(rays) < 3:
        continue
    A = np.zeros((3, 3)); b = np.zeros(3)
    for C, d in rays:
        P = np.eye(3) - np.outer(d, d); A += P; b += P @ C
    base = max(np.linalg.norm(rays[a][0] - rays[c][0]) for a in range(len(rays)) for c in range(len(rays)))
    if base < 1e-6:
        continue
    X.append(np.linalg.solve(A, b)); ID.append(i)
X = np.array(X); ID = np.array(ID)
O = np.c_[bd.OBJ_MM[ID], np.zeros(len(ID))]
# similarity O (mm) -> X (model units): X = s R O + t
om, xm = O.mean(0), X.mean(0)
U, S, Vt = np.linalg.svd((X - xm).T @ (O - om))
D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]); Rs = U @ D @ Vt
s = np.trace(np.diag(S) @ D) / ((O - om) ** 2).sum()
res = X - (s * (O - om) @ Rs.T + xm)
mm_per_unit = 1.0 / s
rms_mm = float(np.sqrt((res ** 2).sum(1).mean()) * mm_per_unit)
L = [f"BOARD SCALE  run {RUN.name} model {MODEL}: {len(used)} frames decoded ("
     + ", ".join(f"{Path(n).stem} {k}" for n, m, k in used) + f"), {len(ID)} corners triangulated from >= 3 frames",
     f"  scale {mm_per_unit:.1f} mm per model unit; flatness / shape residual {rms_mm:.1f} mm rms over the 720 x 540 mm pattern"]
an = RUN / "anchor" / "anchor.json"
if an.exists():
    A = json.loads(an.read_text(encoding="utf-8")).get(MODEL)
    if A:
        L.append(f"  landmark anchor (design 10 ft pole grid) scale {1000 * A['scale']:.1f} mm per unit -> the grid is "
                 f"{100 * (A['scale'] * 1000 / mm_per_unit - 1):+.2f} % against the board (a {480 * 25.4 * (A['scale'] * 1000 / mm_per_unit - 1):+.0f} mm "
                 f"difference over the 40 ft length)")
(RUN / "board_scale.json").write_text(json.dumps(dict(mm_per_unit=mm_per_unit, rms_mm=rms_mm, n_corners=len(ID),
                                                      frames=[u[0] for u in used]), indent=1), encoding="utf-8")
print("\n".join(L))
