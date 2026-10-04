# -*- coding: utf-8 -*-
r"""The poles as absolute check points for ONE camera at a time (2026-10-03): where only one camera sees a region,
cross-camera agreement says nothing; a pole whose position the operator taped does. A CHECK, nothing is fitted.

Pole positions: the operator's centre-to-centre tape between neighbouring poles (survey_2026-10-03.json, 22 spans)
solved by least squares with a weak pull to the design 10 ft grid (6 in - the spans alone leave the grid free to shear),
then placed on the design grid by the best rigid move (the calibration's frame is the design lattice).
Per camera and labelled pole (the operator's POLE_<row><col>_L / _R edge labels on the 09-18 frames, analysis repo 2026c,
IR -> colour shift as refit_rays): at the TAPE's height (operator, 2026-10-04: the tape ran just above the wall tops,
about 1.0-1.1 m; survey tape_height_mm, +-Z_BAND) the edge rays' azimuths around the camera give - at that height the
pole's lean does not enter (the poles lean, so a check at another height would include lean x height difference):
  * the axis direction -> its SIDEWAYS miss of the taped pole, mm, perpendicular to the line of sight (what a wrong
    ray direction does to a projected point there);
  * the pole's angular width x the taped distance -> its apparent diameter vs the taped one (perimeter / pi; B1-B3
    measured, others the mean) -> the camera's angular scale there, % (a scale error stretches positions along and
    across the view alike).

Usage: python pole_tape_check.py [--rays release|<json>|warp] [--z-band 100]
Output: <qc root>\pole_tape_check\POLE_TAPE_CHECK.txt (+ .json)
"""
import sys, json, glob
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RAYS = opt("--rays", "release")
cams = pm.load(rays=None if RAYS == "warp" else RAYS)
SV = json.loads((HERE / "survey_2026-10-03.json").read_text(encoding="utf-8"))["poles"]
LM = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c")
IR2COL = {"CH01": (0.68, -0.39), "CH02": (0.90, 0.67), "CH03": (0.55, -5.60), "CH04": (0.03, 0.0)}
OUT = qc_paths.QC_ROOT / "pole_tape_check"; OUT.mkdir(parents=True, exist_ok=True)
IN = 25.4
Z_TAPE, Z_BAND = float(SV.get("tape_height_mm", 1050)), float(opt("--z-band", "100"))
NAMES = [f"{r}{c}" for r in "ABC" for c in range(5)]
DESIGN = {n: np.array([120.0 * int(n[1]), {"A": 0.0, "B": 120.0, "C": 240.0}[n[0]]]) for n in NAMES}
# ---- the tape network -> positions (in)
spans = [(a, b, float(v)) for k, v in SV["spacing"].items() for a, b in [k.split("-")]]
ix = {n: i for i, n in enumerate(NAMES)}
x = np.concatenate([DESIGN[n] for n in NAMES])
for _ in range(20):                                                      # Gauss-Newton: spans (0.5 in) + design pull (6 in)
    J, r = [], []
    for a, b, d in spans:
        pa, pb = x[2 * ix[a]:2 * ix[a] + 2], x[2 * ix[b]:2 * ix[b] + 2]; v = pa - pb; L = np.linalg.norm(v)
        row = np.zeros(2 * len(NAMES)); row[2 * ix[a]:2 * ix[a] + 2] = v / L; row[2 * ix[b]:2 * ix[b] + 2] = -v / L
        J.append(row / 0.5); r.append((L - d) / 0.5)
    for n in NAMES:
        for k in range(2):
            row = np.zeros(2 * len(NAMES)); row[2 * ix[n] + k] = 1 / 6.0; J.append(row); r.append((x[2 * ix[n] + k] - DESIGN[n][k]) / 6.0)
    dx = np.linalg.lstsq(np.array(J), -np.array(r), rcond=None)[0]; x += dx
    if np.abs(dx).max() < 1e-6:
        break
P = {n: x[2 * ix[n]:2 * ix[n] + 2] for n in NAMES}
A = np.array([P[n] for n in NAMES]); B = np.array([DESIGN[n] for n in NAMES])
am, bm = A.mean(0), B.mean(0); U, _, Vt = np.linalg.svd((B - bm).T @ (A - am))
R = U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt
P = {n: (R @ (P[n] - am) + bm) * IN for n in NAMES}                     # mm, on the design grid
span_res = [abs(np.linalg.norm(P[a] - P[b]) / IN - d) for a, b, d in spans]
perim = SV.get("perimeter", {}); dmean = np.mean(list(perim.values())) / np.pi * IN
DIAM = {n: (perim[n] / np.pi * IN if n in perim else dmean) for n in NAMES}

rows = []
for f in sorted(LM.glob("landmarks_CH0*_20260918_*.json")):
    d = json.loads(f.read_text(encoding="utf-8")); cam = d["camera"]
    if cam not in cams:
        continue
    c = cams[cam]; W, H = c.upright_size; fw, fh = d["frame_size_upright"]; sc = np.array([W / fw, H / fh])
    for n in NAMES:
        Lp, Rp = d["landmarks"].get(f"POLE_{n}_L"), d["landmarks"].get(f"POLE_{n}_R")
        if not Lp or not Rp:
            continue
        v = P[n] - c.centre[:2]; rho = np.linalg.norm(v); phi0 = np.arctan2(v[1], v[0])

        def edge(pieces):
            pts = np.concatenate([np.asarray(q, float).reshape(-1, 2) for q in pieces]) * sc + IR2COL.get(cam, (0, 0))
            rr = c.rays(pts); h = np.hypot(rr[:, 0], rr[:, 1])
            z = c.centre[2] + rho * rr[:, 2] / h                          # height where the ray passes the pole's distance
            az = (np.arctan2(rr[:, 1], rr[:, 0]) - phi0 + np.pi) % (2 * np.pi) - np.pi
            o = np.argsort(z); return z[o], az[o]
        zl, al = edge(Lp); zr, ar = edge(Rp)
        lo = max(zl.min(), zr.min(), Z_TAPE - Z_BAND); hi = min(zl.max(), zr.max(), Z_TAPE + Z_BAND)   # around the tape's height
        if hi <= lo + 50:
            continue
        zs = np.linspace(lo, hi, 5)
        a1, a2 = np.interp(zs, zl, al), np.interp(zs, zr, ar)
        lat = np.median((a1 + a2) / 2) * rho; wid = np.median(np.abs(a2 - a1)) * rho
        rows.append(dict(cam=cam, pole=n, dist_m=round(rho / 1000, 2), z_mm=[round(lo), round(hi)], sideways_mm=round(float(lat), 1),
                         diam_mm=round(float(wid), 1), diam_true_mm=round(float(DIAM[n]), 1), measured=n in perim,
                         scale_err_pct=round(100 * (wid / DIAM[n] - 1), 1)))
L = [f"POLE TAPE CHECK  cameras: {RAYS}; pole positions from the operator's tape (22 spans fitted to {np.median(span_res):.2f} in median, "
     f"max {np.max(span_res):.2f}), rigidly on the design grid; the tape's height {Z_TAPE:.0f} +- {Z_BAND:.0f} mm; labels {LM} (09-18)", "",
     "camera pole  dist m  heights mm   sideways miss mm   apparent / taped diameter mm   angular scale %"]
for r in sorted(rows, key=lambda r: (r["cam"], r["pole"])):
    L.append(f"  {r['cam']}  {r['pole']}   {r['dist_m']:5.2f}   {r['z_mm'][0]:4d}-{r['z_mm'][1]:4d}   {r['sideways_mm']:+8.0f}         "
             f"{r['diam_mm']:6.0f} / {r['diam_true_mm']:4.0f}{'' if r['measured'] else '*'}         {r['scale_err_pct']:+6.1f}")
for cam in sorted({r["cam"] for r in rows}):
    s = [abs(r["sideways_mm"]) for r in rows if r["cam"] == cam]
    L.append(f"  {cam}: sideways miss median {np.median(s):.0f} mm, max {np.max(s):.0f} (n {len(s)} poles)")
L.append("  (* diameter not taped: the mean of B1-B3 used; the angular scale is then only indicative)")
(OUT / "POLE_TAPE_CHECK.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / "pole_tape_check.json").write_text(json.dumps(dict(poles_mm={n: P[n].round(1).tolist() for n in NAMES}, rows=rows), indent=1), encoding="utf-8")
print("\n".join(L))
