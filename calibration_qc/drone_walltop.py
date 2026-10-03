# -*- coding: utf-8 -*-
r"""Wall-top height profiles from the drone (2026-10-03): every wall-top click of the operator's drone labels is a ray
from its registered frame; moved into the paddock frame by the landmark anchor and cut with the wall's design plane
(x = 0 / 480 in, y = 0 / 240 in) it gives (position along the wall, height). The drone looks at the wall tops from
1-2 m up, nearly level, so the exact plane position hardly moves the height. Heights are put on the tape's ground:
the ChArUco plate's scale (drone_board_scale.py) is applied, then the datum offset between the taped lens heights and
the triangulated ones (drone_lens_triangulate.py; the drone's floor plane runs on the grass tops) is added.
Per wall the clicks are binned (12 in) and a robust median kept where >= 2 clicks agree.

Usage: python drone_walltop.py --name 2026-10-02_all [--model 1] [--labels a.json,b.json]
Output: <run>\walltop_profile.json ({wall: [[along_in, z_mm, n], ...]}, datum offset) and WALLTOP_PROFILE.txt
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402
from scipy.spatial.transform import Rotation                             # noqa: E402

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
MODEL = opt("--model", "1")
LABELS = opt("--labels", ",".join([str(HERE / "session_2026-10-02_drone_landmarks.json"),
                                    str(RUN / "landmark_gui_cams" / "drone_landmarks_cams.json")])).split(",")
IN, BIN = 0.0254, 12
WALLS = {"X0": (0, 0.0), "X480": (0, 480 * IN), "Y0": (1, 0.0), "Y240": (1, 240 * IN)}   # axis, plane (m)
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
imgs = {im.name: im for im in rec.images.values()}
A = json.loads((RUN / "anchor" / "anchor.json").read_text(encoding="utf-8"))[MODEL]
s, Rm, t = A["scale"], Rotation.from_rotvec(A["rotvec"]).as_matrix(), np.asarray(A["t"])
k_board = json.loads((RUN / "board_scale.json").read_text(encoding="utf-8"))["mm_per_unit"] / 1000 / s
cc = json.loads((qc_paths.QC_ROOT / "camera_centres_2026-10-03.json").read_text(encoding="utf-8"))
tri = cc.get("drone_tri", {})
both = [c for c in cc["tape"] if c in tri]
datum = float(np.mean([cc["tape"][c]["h_m"] - k_board * tri[c]["z_m"] for c in both])) if both else 0.0

pts = {w: [] for w in WALLS}
for path in LABELS:
    for fr in json.loads(Path(path).read_text(encoding="utf-8"))["frames"]:
        if fr["name"] not in imgs:
            continue
        im = imgs[fr["name"]]; cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
        C = s * Rm @ im.projection_center() + t
        for name, val in fr["points"].items():
            if not name.startswith("wall top "):
                continue
            w = name[9:]; ax, plane = WALLS[w]
            uv = np.atleast_2d(np.asarray(val, float))
            xn = cam.cam_from_img(uv)
            d = (np.c_[xn, np.ones(len(xn))] @ T.rotation.matrix()) @ Rm.T            # model -> paddock directions
            lam = (plane - C[ax]) / d[:, ax]
            X = C + lam[:, None] * d
            for x, l in zip(X, lam):
                if l > 0 and np.isfinite(x).all():
                    pts[w].append((x[1 - ax] / IN, k_board * x[2] * 1000 + datum * 1000, fr["name"]))
out, L = {}, [f"DRONE WALL-TOP PROFILES  run {RUN.name} model {MODEL}: clicks cut with the design wall planes; board scale "
              f"x{k_board:.4f}; datum +{datum * 1000:.0f} mm (taped minus triangulated lens heights, {', '.join(both)})", ""]
for w, P in pts.items():
    if not P:
        continue
    a = np.array([p[0] for p in P]); z = np.array([p[1] for p in P])
    prof = []
    for b in np.arange(np.floor(a.min() / BIN) * BIN, a.max() + BIN, BIN):
        m = (a >= b) & (a < b + BIN)
        if m.sum() < 2:
            continue
        zz = z[m]; med = np.median(zz); keep = np.abs(zz - med) <= max(40.0, 3 * 1.4826 * np.median(np.abs(zz - med)))
        if keep.sum() >= 2:
            prof.append([float(b + BIN / 2), round(float(np.median(zz[keep])), 0), int(keep.sum()), round(float(np.std(zz[keep])), 0)])
    out[w] = prof
    L.append(f"wall top {w}: {len(P)} clicks; along (in): height mm (n, sd)")
    L.append("   " + "; ".join(f"{p[0]:.0f}: {p[1]:.0f} ({p[2]}, {p[3]:.0f})" for p in prof))
(RUN / "walltop_profile.json").write_text(json.dumps(dict(datum_mm=round(datum * 1000, 1), k_board=k_board, bin_in=BIN, walls=out),
                                                     indent=1), encoding="utf-8")
(RUN / "WALLTOP_PROFILE.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
