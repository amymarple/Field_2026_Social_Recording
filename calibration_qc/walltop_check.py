# -*- coding: utf-8 -*-
r"""Wall tops as a cross-camera check: the same physical wall top, seen by several cameras, must come out at the same
height. A CHECK, not a fit (2026-10-02).

The operator's rigid-landmark labels on the 2026-09-18 reference frames (analysis repo, cv/configs/landmarks/2026c,
polyline WALLTOP_<side>) are carried from the IR reference into the colour-mode calibration pixels (the 09-18 IR ->
colour shift measured by landmark_track_drift.py), densified along each labelled piece, and each pixel's ray is cut
with the vertical wall plane (physical paddock frame: x = 0 / 480 in or y = 0 / 240 in, through the release ground
warp exactly as the ball check maps points; --nowarp uses the bundle alone). Binned along the wall, the cameras'
heights are compared. The wall plane's exact position cancels to first order (moving it moves every camera's height
alike for cameras at similar distance); the wall's true height profile is unknown until the survey, so only the
DIFFERENCES between cameras are evidence.

Why: the boards seen by both CH01 and CH02 are 4 stations, none on the far west half; the wall tops at the far ends
are seen by both panos and by CH03 / CH04, at a height (~1 m) and image region (above the ground support) the boards
never reached.

Usage: python walltop_check.py [--wall WALLTOP_X0] [--fit <camera_fit.npz>] [--nowarp] [--offset-mm 0]
Output: stdout and <fit dir>\WALLTOP_CHECK_<wall>.txt
"""
import sys, json, glob
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paddock_map as pm                                                  # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
WALL = opt("--wall", "WALLTOP_X0")
FIT = Path(opt("--fit", str(pm.FIT)))
OFFSET = float(opt("--offset-mm", "0"))                                   # move the wall plane (mm, along its axis)
LM = Path(opt("--landmarks", r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c"))
IR2COL = {"CH01": (0.68, -0.39), "CH02": (0.90, 0.67), "CH03": (0.55, -5.60), "CH04": (0.03, 0.0)}   # 09-18 IR -> colour px
IN = 25.4
AXIS, POS = {"X0": (0, 0.0), "X480": (0, 480 * IN), "Y0": (1, 0.0), "Y240": (1, 240 * IN)}[WALL.split("_")[1]]
POS += OFFSET
cams = pm.load(FIT, correct="--nowarp" not in args)


def labels(cam):
    f = sorted(LM.glob(f"landmarks_{cam}_20260918_*.json"))
    if not f:
        return None
    pieces = json.loads(f[-1].read_text(encoding="utf-8"))["landmarks"].get(WALL)
    if not pieces:
        return None
    pts = []
    for p in pieces:                                                     # densify each piece, never across pieces
        p = np.asarray(p, float)
        for a, b in zip(p[:-1], p[1:]):
            n = max(2, int(np.hypot(*(b - a)) / 10))
            pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
        pts.append(p[-1])
    return np.array(pts) + IR2COL.get(cam, (0.0, 0.0))


def cut(cam, uv):
    """(position along the wall, height) in mm where each pixel's ray meets the wall plane."""
    c = cams[cam]; d = c.rays(uv); s = np.linspace(0, 16000, 4001); out = []
    for di in d:
        X = c.centre + s[:, None] * di
        ph = pm.fit_to_physical(X[:, :2], c.correction)
        f = ph[:, AXIS] - POS
        k = np.where(np.sign(f[:-1]) != np.sign(f[1:]))[0]
        if not len(k):
            out.append((np.nan, np.nan)); continue
        k = k[0]; w = f[k] / (f[k] - f[k + 1])
        out.append(((1 - w) * ph[k, 1 - AXIS] + w * ph[k + 1, 1 - AXIS], (1 - w) * X[k, 2] + w * X[k + 1, 2]))
    return np.array(out)


prof = {}
for c in cams:
    uv = labels(c)
    if uv is not None:
        prof[c] = cut(c, uv)
names = list(prof)
span = 480 if AXIS == 1 else 240
L = [f"WALL TOP CHECK {WALL}: plane {'xy'[AXIS]} = {POS / IN:+.1f} in, fit {FIT}, {'bundle only (no ground warp)' if '--nowarp' in args else 'release ground warp'}",
     "height (mm) where each camera's rays meet the wall plane, binned along the wall; only differences are evidence", "",
     f"  {'along (in)':>11s}" + "".join(f"{c:>8s}" for c in names)
     + "".join(f"{a + '-' + b:>11s}" for i, a in enumerate(names) for b in names[i + 1:])]
for p0 in range(0, span, 24):
    r = []
    for c in names:
        P = prof[c]; k = (P[:, 0] / IN >= p0) & (P[:, 0] / IN < p0 + 24)
        r.append(np.median(P[k, 1]) if k.sum() >= 3 else np.nan)
    r = np.array(r)
    if np.isfinite(r).sum() >= 2:
        L.append(f"  {p0:4d}-{p0 + 24:4d} " + "".join(f"{v:8.0f}" for v in r)
                 + "".join(f"{r[i] - r[j]:+11.0f}" for i in range(len(r)) for j in range(i + 1, len(r))))
L.append("")
for c in names:
    P = prof[c]; g = np.isfinite(P[:, 1])
    if g.sum() >= 3:
        slope = np.polyfit(P[g, 0] / IN, P[g, 1], 1)[0] * 12
        L.append(f"  {c}: {g.sum()} points along {np.nanmin(P[:, 0]) / IN:.0f}-{np.nanmax(P[:, 0]) / IN:.0f} in; height median "
                 f"{np.nanmedian(P[:, 1]):.0f} mm, slope {slope:+.0f} mm per ft along the wall")
OUT = FIT.parent / f"WALLTOP_CHECK_{WALL}{'_nowarp' if '--nowarp' in args else ''}.txt"
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L)); print("->", OUT)
