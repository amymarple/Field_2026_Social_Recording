# -*- coding: utf-8 -*-
r"""Ground relief of the paddock from the anchored drone cloud (2026-10-03): the height of the local ground above the
paddock's best ground plane, on a 2 ft grid, for paddock_map / refit_rays to place things on the real ground instead of
the plane z = 0 (the release maps a rat at "60 mm above z = 0"; where the ground lies 5 cm lower that is 1 cm, and on
the panos 0.8 mm of position per mm of height).

Per 24 in cell the 30th percentile of the model-1 points within +-0.4 m of the floor (grass tops and soil; taller things
fall above it), leaving out what is not ground: the two houses (footprints from house_check.py, +15 cm), the poles
(0.2 m radius) and a 0.3 m strip along every wall. The best plane through the cells is removed (the calibration's ground
is that plane: plates and cones lie on it), a 3 x 3 median removes single-cell noise, and holes are filled from the
neighbours. Heights are relative: the drone's floor is the grass tops, but only differences enter.

Usage: python drone_terrain.py [--name 2026-10-02_all] [--model 1]
Output: calibration_qc\terrain_2026-10-02.json (grid in mm, x / y cell centres in inches) and a printed map
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
M = opt("--model", "1")
IN, CELL = 0.0254, 24.0
HOUSES = {"HOUSE_1": ((147.0, 122.0), 90.6), "HOUSE_2": ((341.9, 118.2), 92.8)}   # house_check.py, rev d (in, deg of the ridge)
L2, W2 = 62.55 / 2 + 15, 45.72 / 2 + 15                                   # cm, footprint + 15 cm
P = np.load(RUN / "anchor" / "paddock_points_all.npz")[f"m{M}_xyz"]     # paddock metres
x, y, z = P[:, 0] / IN, P[:, 1] / IN, P[:, 2]
keep = (np.abs(z) < 0.4) & (x > 0.3 / IN) & (x < 480 - 0.3 / IN) & (y > 0.3 / IN) & (y < 240 - 0.3 / IN)
for (cx, cy), th in HOUSES.values():                                     # house footprints (u along the ridge)
    t = np.radians(th); du, dv = (x - cx) * np.cos(t) + (y - cy) * np.sin(t), -(x - cx) * np.sin(t) + (y - cy) * np.cos(t)
    keep &= ~((np.abs(du) < L2 / 2.54) & (np.abs(dv) < W2 / 2.54))
for r, ry in zip("ABC", (0, 120, 240)):                                  # poles at the design grid (0.2 m)
    for c in range(5):
        keep &= np.hypot(x - 120 * c, y - ry) > 0.2 / IN
x, y, z = x[keep], y[keep], z[keep]
ex, ey = np.arange(0, 480 + 1e-6, CELL), np.arange(0, 240 + 1e-6, CELL)
G = np.full((len(ey) - 1, len(ex) - 1), np.nan); N = np.zeros_like(G)
ix, iy = np.digitize(x, ex) - 1, np.digitize(y, ey) - 1
for i in range(G.shape[1]):
    for j in range(G.shape[0]):
        q = z[(ix == i) & (iy == j)]; N[j, i] = len(q)
        if len(q) >= 30:
            G[j, i] = np.percentile(q, 30) * 1000
cx_, cy_ = (ex[:-1] + ex[1:]) / 2, (ey[:-1] + ey[1:]) / 2
X, Y = np.meshgrid(cx_, cy_); ok = np.isfinite(G)
A = np.c_[np.ones(ok.sum()), X[ok], Y[ok]]; pl, *_ = np.linalg.lstsq(A, G[ok], rcond=None)
G = G - (pl[0] + pl[1] * X + pl[2] * Y)                                  # relative to the best plane
Gm = G.copy()
for j in range(G.shape[0]):                                              # 3 x 3 median (ignoring holes), then fill holes
    for i in range(G.shape[1]):
        nb = G[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
        if np.isfinite(nb).sum() >= 3:
            Gm[j, i] = np.nanmedian(nb)
G = Gm
for _ in range(5):
    if np.isfinite(G).all():
        break
    Gf = G.copy()
    for j, i in zip(*np.where(~np.isfinite(G))):
        nb = G[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
        if np.isfinite(nb).any():
            Gf[j, i] = np.nanmean(nb)
    G = Gf
G = np.nan_to_num(G, nan=0.0)
out = dict(note="drone_terrain.py: ground height above the paddock's best ground plane (mm), 24 in cells, from drone model "
                f"{M} of {RUN.name} (30th percentile of floor points, houses / poles / wall strips left out, 3x3 median)",
           cell_in=CELL, x_in=cx_.tolist(), y_in=cy_.tolist(), z_mm=np.round(G, 1).tolist(), points_per_cell_min=int(N[N > 0].min()))
(HERE / "terrain_2026-10-02.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"terrain grid {G.shape[1]} x {G.shape[0]} cells of {CELL:.0f} in; heights p5..p95 {np.percentile(G, 5):.0f} .. {np.percentile(G, 95):.0f} mm, sd {G.std():.0f} mm")
print("   rows y = 228 ... 12 in (top = row C); columns x = 12 ... 468 in")
for j in range(G.shape[0] - 1, -1, -1):
    print(f"   y{cy_[j]:4.0f} " + " ".join(f"{v:4.0f}" for v in G[j]))
