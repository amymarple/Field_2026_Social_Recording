# -*- coding: utf-8 -*-
# poles at their design positions (10 ft grid) against the operator's pole-edge labels (09-18 reference frames), under a fit:
# per pole and camera, at several heights z on the pole: the pole's width from the L / R edges (-> diameter) and where the
# model puts the pole's axis relative to the design position (lateral error, mm, perpendicular to the line of sight).
import sys, json, glob, os
import numpy as np
sys.path.insert(0, r"G:\Field_2026_Social_Recording\calibration_qc")
import paddock_map as pm
FIT = sys.argv[1] if len(sys.argv) > 1 else pm.FIT
cams = pm.load(FIT)
D = "D:/Documents/GitHub/Field2026_Social_analysis/cv/configs/landmarks/2026c/"
POLES = {f"{r}{i}": (120 * i * 25.4, y * 25.4) for r, y in (("A", 0), ("B", 120), ("C", 240)) for i in range(5)}
ZS = [0, 300, 600, 900, 1200, 1500, 1800, 2100]
rows = []
for f in sorted(glob.glob(D + "landmarks_CH0*_20260918_*.json")):
    d = json.load(open(f, encoding="utf-8")); cam = d["camera"]; c = cams[cam]
    W, H = c.upright_size; fw, fh = d["frame_size_upright"]; sc = np.array([W / fw, H / fh])
    for p, xy in POLES.items():
        L, R = d["landmarks"].get(f"POLE_{p}_L"), d["landmarks"].get(f"POLE_{p}_R")
        if not L or not R:
            continue
        X = pm.physical_to_fit(np.array([xy], float), c.correction)[0]          # design position in the fit frame (mm)
        v = X - c.centre[:2]; rho = np.linalg.norm(v); phi0 = np.arctan2(v[1], v[0])
        def edge(poly):
            r = c.rays(np.asarray(poly[0], float) * sc)
            h = np.hypot(r[:, 0], r[:, 1])
            z = c.centre[2] + rho * r[:, 2] / h                                  # height where the ray passes the pole's distance
            az = np.unwrap(np.arctan2(r[:, 1], r[:, 0]) - phi0)
            az = (az + np.pi) % (2 * np.pi) - np.pi
            o = np.argsort(z)
            return z[o], az[o]
        zl, al = edge(L); zr, ar = edge(R)
        lo, hi = max(zl.min(), zr.min()), min(zl.max(), zr.max())
        for z in ZS:
            if lo <= z <= hi:
                a1, a2 = np.interp(z, zl, al), np.interp(z, zr, ar)
                rows.append((cam, p, z, rho, abs(a2 - a1) * rho, (a1 + a2) / 2 * rho))
print(f"fit {os.path.basename(os.path.dirname(FIT)) or FIT}")
print("cam  pole  dist(m)   z(mm): diameter(mm) / axis lateral offset from design (mm)")
for cam, p in sorted({(r[0], r[1]) for r in rows}):
    rr = [r for r in rows if r[0] == cam and r[1] == p]
    print(f"{cam} {p:4} {rr[0][3] / 1000:5.1f}  " + "  ".join(f"z{r[2]:>4}: {r[4]:4.0f}/{r[5]:+5.0f}" for r in rr))
dia = np.array([r[4] for r in rows])
print(f"\ndiameter over all: median {np.median(dia):.0f} mm (p10 {np.percentile(dia, 10):.0f}, p90 {np.percentile(dia, 90):.0f}); 1 ft = 305 mm")

# triangulate each pole axis at each height from the cameras that see it (position free): where the cameras put it,
# how far from design, and how well they agree (perpendicular residual of each camera's line of sight)
print("\npole  z(mm)  cams: triangulated - design (mm), max camera residual (mm)")
for p in sorted({r[1] for r in rows}):
    for z in ZS:
        rr = [r for r in rows if r[1] == p and r[2] == z]
        if len(rr) < 2:
            continue
        A, b, lines = [], [], []
        for cam, _, _, rho, _, lat in rr:
            c = cams[cam]
            X = pm.physical_to_fit(np.array([POLES[p]], float), c.correction)[0]
            v = X - c.centre[:2]; u = v / np.linalg.norm(v)
            nrm = np.array([-u[1], u[0]])                       # left of the line of sight
            q = X + nrm * lat                                   # the pole axis as this camera sees it
            A.append(nrm); b.append(nrm @ q); lines.append((cam, nrm, q))
        sol = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)[0]
        res = [abs(n @ (sol - q)) for _, n, q in lines]
        Xd = pm.physical_to_fit(np.array([POLES[p]], float), cams[rr[0][0]].correction)[0]
        print(f"{p:4} {z:5}  {'+'.join(r[0][2:] for r in rr):8}: ({sol[0] - Xd[0]:+5.0f}, {sol[1] - Xd[1]:+5.0f})  residual max {max(res):4.0f}")
