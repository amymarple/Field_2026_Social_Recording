# -*- coding: utf-8 -*-
r"""The 2026-09-30 drone photo as an independent ground instrument: where are the cones, and where does each camera
put them? A CHECK, not a fit (2026-10-02).

Input: F:\calibration\drone\PTSC_0008.JPG (Potensic Atom 2, near-nadir, 3840 x 2160, no EXIF; taken on 2026-09-30
with the cones in the 09-30 layout) and the operator's 09-30 cone labels (session_2026-09-30_cone_labels_CHxx.json).
1) cones by colour class (red / gold / yellow / lime / blue; thresholds from sampled cones vs grass); 2) assigned to
the 09-30 layout (README "What was actually laid out"; column x = 276 tried on its old and mid stations), starting
from four cones identified by eye (T25, T21M, T65, T61M) and iterated; 3) plane homography + one radial term, cone
vs design; 4) every camera's labelled cone mapped to the paddock at the cone top (z = 50 mm; 09-30 px carried to
09-18 by session_2026-09-30_drift_final.json), the drone's undistorted pixels mapped to the paddock by a robust
homography fitted to all camera marks, and each camera's mark compared with the drone's position.

Caveats: one photo, intrinsics unknown (one radial term); cone tops taken as one plane (terrain +-5 cm at ~14 m
altitude: ~1 cm); the corners and edges are hidden under the shade sails.

Usage: python drone_check.py [--photo <jpg>]   (output under <qc root>\2026-09-30\drone\)
"""
import sys, json
from pathlib import Path
import numpy as np, cv2
from scipy.optimize import least_squares
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paddock_map as pm, qc_paths                                       # noqa: E402
S = qc_paths.QC_ROOT / "2026-09-30" / "drone"; S.mkdir(parents=True, exist_ok=True); S = str(S)
R = str(Path(__file__).resolve().parent)
PHOTO = sys.argv[sys.argv.index("--photo") + 1] if "--photo" in sys.argv else r"F:\calibration\drone\PTSC_0008.JPG"
im = cv2.imread(PHOTO); Hh, Ww = im.shape[:2]
TX = [24, 96, 168, 240, 312, 384, 456]; VX = [60, 132, 204, 276, 348, 420]
LAY = {}
for i, x in enumerate(TX, 1):
    for j, y in enumerate([12, 66, 120, 174], 1):
        LAY[f"T{i}{j}M"] = (x, y + 27)
    LAY[f"T{i}5"] = (x, 228)
for i, x in enumerate(VX, 1):
    for j, y in enumerate([39, 93, 147, 201], 1):
        nm = f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}"
        LAY[nm + "M"] = (x, y + 27)
        if x == 276:
            LAY[nm] = (x, y)                                         # column 4: old station also possible
LAY.update({"C1": (12, 12), "C2": (12, 228), "C3": (468, 12), "C4": (468, 228), "E1": (384, 21), "E2": (96, 189)})
SEED = {"T25": (1138, 583), "T21M": (1120, 1622), "T65": (2728, 563), "T61M": (2800, 1620)}


def proj(H, p):
    q = np.c_[p, np.ones(len(p))] @ H.T
    return q[:, :2] / q[:, 2:]


H0 = cv2.findHomography(np.array([LAY[k] for k in SEED], np.float32), np.array(list(SEED.values()), np.float32), 0)[0]
hsv = cv2.cvtColor(cv2.GaussianBlur(im, (5, 5), 0), cv2.COLOR_BGR2HSV).astype(int)
hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
CLS = {"red": ((hue < 8) | (hue > 165)) & (sat > 100) & (val > 80),
       "gold": (hue >= 12) & (hue < 28) & (sat > 80) & (val > 110),
       "yellow": (hue >= 28) & (hue < 42) & (sat > 100) & (val > 110),
       "lime": (hue >= 42) & (hue < 58) & (sat > 80) & (val > 150),
       "blue": (hue >= 95) & (hue < 115) & (sat > 120) & (val > 80)}
DET = []
for cname, m in CLS.items():
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    nl, lab, st, cen = cv2.connectedComponentsWithStats(m)
    for k in range(1, nl):
        a_, w_, h_ = st[k, cv2.CC_STAT_AREA], st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT]
        if 350 <= a_ <= 4000 and 0.5 < w_ / max(h_, 1) < 2.0 and a_ > 0.45 * w_ * h_:
            DET.append((cen[k, 0], cen[k, 1], cname, a_))
DP = np.array([[d[0], d[1]] for d in DET])
print("colour blobs:", len(DET), {c: sum(1 for d in DET if d[2] == c) for c in CLS})


def locate(H, rad=60):
    out = {}
    pr = proj(H, np.array(list(LAY.values()), float))
    for (n, p), (u, v) in zip(LAY.items(), pr):
        d = np.hypot(DP[:, 0] - u, DP[:, 1] - v); k = int(d.argmin())
        if d[k] < rad:
            out[n] = (DP[k, 0], DP[k, 1], float(d[k]), DET[k][2])
    # one cone, one station: a blob claimed twice goes to the nearer prediction
    by = {}
    for n, v in out.items():
        by.setdefault((round(v[0]), round(v[1])), []).append(n)
    for k, ns in by.items():
        if len(ns) > 1:
            keep = min(ns, key=lambda n: out[n][2])
            for n in ns:
                if n != keep:
                    out.pop(n)
    return out


c0 = np.array([Ww / 2, Hh / 2]); f0 = float(Ww)


def model(x, P):
    Hm = np.r_[x[:8], 1.0].reshape(3, 3); q = proj(Hm, P); r = (q - c0) / f0; rr = (r ** 2).sum(1, keepdims=True)
    return c0 + r * (1 + x[8] * rr) * f0


def undist(x, px):                                                    # image px -> undistorted px (iterate)
    r_d = (px - c0) / f0; r = r_d.copy()
    for _ in range(20):
        rr = (r ** 2).sum(1, keepdims=True); r = r_d / (1 + x[8] * rr)
    return c0 + r * f0


H = H0
for it in range(3):
    meas = locate(H, rad=70 if it == 0 else 40)
    N = list(meas); D = np.array([LAY[n] for n in N], float); P = np.array([meas[n][:2] for n in N])
    H = cv2.findHomography(D.astype(np.float32), P.astype(np.float32), cv2.RANSAC, 12.0)[0]
x0 = np.r_[(H / H[2, 2]).ravel()[:8], 0]
sol = least_squares(lambda x: (model(x, D) - P).ravel(), x0, loss="soft_l1", f_scale=4.0)
res = model(sol.x, D) - P
Jx = model(sol.x, D + [1, 0]) - model(sol.x, D); Jy = model(sol.x, D + [0, 1]) - model(sol.x, D)
off_in = np.array([np.linalg.solve(np.c_[Jx[i], Jy[i]], -res[i]) for i in range(len(N))])   # cone - design, inches
pxin = np.median(np.hypot(*Jx.T))
print(f"drone: {len(N)} cones located; {pxin:.2f} px/in; distortion k1 {sol.x[8]:+.3f}; fit residual median {np.median(np.hypot(*res.T)):.1f} px")
print(f"  cone vs design after the best plane fit: median {np.median(np.hypot(*off_in.T)):.2f} in, p90 {np.percentile(np.hypot(*off_in.T), 90):.2f} in")
print("  column x = 276 found at: " + ", ".join(f"{n}" for n in N if n[1] == "4" and n[0] in "VF"))
# drone px -> undistorted -> paddock frame of the CAMERAS (homography fitted to their consensus below)
U = undist(sol.x, P)
drift = json.loads(open(R + r"\session_2026-09-30_drift_final.json", encoding="utf-8").read())["cameras"]


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = drift.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        A = np.asarray(d["affine_30_to_18"], float); return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ Rm / d["scale"]


cams = pm.load()
camxy = {}
for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06"):
    L = json.load(open(R + rf"\session_2026-09-30_cone_labels_{c}.json", encoding="utf-8"))["points"]
    for p in L:
        st = p.get("station")
        if st in meas:
            xy = cams[c].to_paddock(to_0918(c, [p["x"], p["y"]]), z_mm=50.0, units="in")[0]
            if np.isfinite(xy).all():
                camxy.setdefault(st, {})[c] = xy
idx = {n: i for i, n in enumerate(N)}
pairs = [(n, c, xy) for n, d in camxy.items() for c, xy in d.items()]
print(f"camera marks on drone-located cones: {len(pairs)} ({len(camxy)} cones)")
src = np.array([U[idx[n]] for n, c, xy in pairs], np.float32); dst = np.array([xy for n, c, xy in pairs], np.float32)
G, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
for _ in range(3):                                                    # robust refit on all marks
    e = np.hypot(*(proj(G, src) - dst).T); w = e < max(3 * np.median(e), 2.0)
    G = cv2.findHomography(src[w], dst[w], 0)[0]
dxy = {n: proj(G, U[idx[n]:idx[n] + 1])[0] for n in camxy}
print("\neach camera's cone position minus the drone's (paddock inches; drone frame fitted to all cameras):")
for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06"):
    rows = [(n, camxy[n][c] - dxy[n]) for n in camxy if c in camxy[n]]
    if not rows:
        continue
    e = np.array([r[1] for r in rows]); dist = np.hypot(*e.T) * 25.4
    reg = {}
    for (n, v), d in zip(rows, dist):
        x = dxy[n][0]; reg.setdefault("x<120" if x < 120 else "x>360" if x > 360 else "120-360", []).append((d, v))
    print(f"  {c}: n {len(rows)}, median {np.median(dist):4.0f} mm, p90 {np.percentile(dist, 90):4.0f} mm; mean offset "
          f"({e[:, 0].mean() * 25.4:+4.0f}, {e[:, 1].mean() * 25.4:+4.0f}) mm | " +
          " | ".join(f"{k}: {np.median([a for a, b in v]):3.0f} mm ({np.mean([b[0] for a, b in v]) * 25.4:+3.0f},{np.mean([b[1] for a, b in v]) * 25.4:+3.0f}) n{len(v)}"
                     for k, v in sorted(reg.items())))
json.dump(dict(cones={n: dict(px=list(map(float, P[idx[n]])), design_in=list(LAY[n]), drone_in=list(map(float, dxy.get(n, [np.nan, np.nan]))))
                      for n in N}, model=sol.x.tolist(), G=G.tolist()), open(S + r"\drone_vs_cams.json", "w"), indent=0)
vis = im.copy()
for i, n in enumerate(N):
    p = P[i].astype(int); cv2.circle(vis, tuple(p), 24, (255, 255, 255), 3)
    cv2.putText(vis, n, (p[0] + 26, p[1] + 8), 0, 0.8, (255, 255, 255), 2)
cv2.imwrite(S + r"\drone_vs_cams_vis.jpg", cv2.resize(vis, (1920, 1080), interpolation=cv2.INTER_AREA))
