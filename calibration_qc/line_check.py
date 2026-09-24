# -*- coding: utf-8 -*-
r"""What the operator's cord and wall-foot labels say about the calibration.

A cord is a straight line on the ground at a known x. Its clicked points, pushed through a camera
onto the ground, must come out (a) straight and (b) at that x. The straightness residual is a
model-free test of that camera's rays along the cord (a bend = the rays are wrong there); the
offset from the design x is the frame error at that place. The wall foot is one physical curve seen
by several cameras: where their traces disagree, so do their calibrations, in a place no board was
ever put; the straight middles of the end walls are at x = 0 / 480 and of the long sides at
y = 0 / 240 by design.

Usage: python line_check.py [--fit <camera_fit.npz>] [--no-correction] [--plot]
Output: <fit dir>\LINE_CHECK.txt, line_check.png
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
FIT = Path(args[args.index("--fit") + 1]) if "--fit" in args else pm.FIT
CORRECT = "--no-correction" not in args
MM = 25.4
L = []


def say(s=""):
    print(s, flush=True); L.append(s)


cams = pm.load(FIT, correct=CORRECT)
raw = pm.load(FIT, correct=False)
S, QC = qc_paths.resolve(None)
labels = {}
for c in cams:
    f = QC / f"line_labels_{c}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(S, c); dw, dh = d.get("frame_size_upright", [uw, uh])
        sc = np.array([uw / float(dw), uh / float(dh)])
        labels[c] = {k: np.asarray(v, float) * sc for k, v in d["lines"].items() if len(v) >= 2}


def line_fit(P):
    """total least squares line through 2-D points -> (centre, unit direction, perpendicular residuals)."""
    c = P.mean(0); U, Sv, Vt = np.linalg.svd(P - c)
    d = Vt[0]; n = np.array([-d[1], d[0]])
    return c, d, (P - c) @ n


say("=" * 100)
say(f"CORDS AND WALL FOOT AGAINST THE FIT   ({'frame-corrected' if CORRECT else 'raw fit frame'}; {FIT})")
say("=" * 100)
say("")
say("CORDS: each camera's trace of each cord on the ground. 'bend' = rms perpendicular deviation from a")
say("straight line (the camera's rays along the cord), 'x' = where the trace sits vs the design x, 'tilt' =")
say("the trace's angle from the y axis. Rows = canvas rows spanned (where in the image the cord was).")
say(f"  {'cam':5s} {'cord':6s} {'n':>3s} {'bend rms':>9s} {'max':>6s}   {'x mean':>7s} {'design':>7s} {'offset':>7s} {'raw off':>8s}   {'tilt':>6s}   {'y span':>12s}   rows")
cord_rows = []
for c in sorted(labels):
    for k, uv in sorted(labels[c].items()):
        if not k.startswith("X"):
            continue
        x0 = float(k[1:])
        g = cams[c].to_paddock(uv, z_mm=0.0, units="in"); gr = raw[c].to_paddock(uv, z_mm=0.0, units="in")
        ok = np.isfinite(g).all(1)
        if ok.sum() < 3:
            say(f"  {c:5s} {k:6s} {ok.sum():3d}   (too few points on the ground)"); continue
        g, gr, uvk = g[ok], gr[ok], uv[ok]
        ctr, d, res = line_fit(g)
        tilt = np.degrees(np.arctan2(abs(d[0]), abs(d[1])))
        say(f"  {c:5s} {k:6s} {len(g):3d} {np.sqrt((res**2).mean()):8.1f}in {np.abs(res).max():5.1f}   {g[:,0].mean():7.1f} {x0:7.0f} {g[:,0].mean()-x0:+7.1f} {gr[:,0].mean()-x0:+8.1f}   {tilt:5.1f}d   {g[:,1].min():5.0f}-{g[:,1].max():4.0f}   {uvk[:,1].min():.0f}-{uvk[:,1].max():.0f}")
        cord_rows.append((c, k, g, res, uvk))

say("")
say("  per-point x offset along the cord (design x subtracted; + = toward +x), in the order clicked:")
for c, k, g, res, uvk in cord_rows:
    x0 = float(k[1:])
    say(f"  {c} {k:6s} " + " ".join(f"{v:+5.1f}" for v in (g[:, 0] - x0)) + "   (y: " + " ".join(f"{v:4.0f}" for v in g[:, 1]) + ")")

say("")
say("WALL FOOT: where each camera puts each side, and how the cameras agree where they overlap.")
say(f"  {'cam':5s} {'side':10s} {'n':>3s}   {'along':>16s}   {'across: mean':>12s} {'design':>7s}   {'bend rms':>9s}")
walls = {}
for c in sorted(labels):
    for k, uv in sorted(labels[c].items()):
        if not k.startswith("WALL"):
            continue
        g = cams[c].to_paddock(uv, z_mm=0.0, units="in")
        ok = np.isfinite(g).all(1)
        g = g[ok]
        if len(g) < 2:
            continue
        walls.setdefault(k, []).append((c, g))
        if k in ("WALL_X0", "WALL_X480"):
            design = 0.0 if k == "WALL_X0" else 480.0
            mid = g[(g[:, 1] > 60) & (g[:, 1] < 180)]          # the straight part between the rounded corners
            across = mid[:, 0].mean() if len(mid) else g[:, 0].mean()
            _, _, res = line_fit(mid) if len(mid) >= 3 else (None, None, np.zeros(1))
            say(f"  {c:5s} {k:10s} {len(g):3d}   y {g[:,1].min():5.0f}..{g[:,1].max():5.0f}     x {across:9.1f} {design:7.0f}   {np.sqrt((res**2).mean()):8.1f}in  (straight part: {len(mid)} pts)")
        elif k in ("WALL_Y0", "WALL_Y240"):
            design = 0.0 if k == "WALL_Y0" else 240.0
            mid = g[(g[:, 0] > 100) & (g[:, 0] < 380)]
            across = mid[:, 1].mean() if len(mid) else g[:, 1].mean()
            _, _, res = line_fit(mid) if len(mid) >= 3 else (None, None, np.zeros(1))
            say(f"  {c:5s} {k:10s} {len(g):3d}   x {g[:,0].min():5.0f}..{g[:,0].max():5.0f}     y {across:9.1f} {design:7.0f}   {np.sqrt((res**2).mean()):8.1f}in  (straight part: {len(mid)} pts)")
        else:
            say(f"  {c:5s} {k:10s} {len(g):3d}   x {g[:,0].min():5.0f}..{g[:,0].max():5.0f}  y {g[:,1].min():5.0f}..{g[:,1].max():5.0f}")


def poly_dist(P, Q):
    """distance from each point of P to the polyline Q (in)."""
    out = []
    for p in P:
        best = np.inf
        for a, b in zip(Q[:-1], Q[1:]):
            ab = b - a; t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
            best = min(best, np.linalg.norm(p - (a + t * ab)))
        out.append(best)
    return np.array(out)


say("")
say("  cross-camera: distance from one camera's wall points to another's trace of the same side (only")
say("  where the traces overlap along the wall):")
for k, v in sorted(walls.items()):
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            (ca, ga), (cb, gb) = v[i], v[j]
            ax = 1 if k in ("WALL_X0", "WALL_X480") else 0
            lo, hi = max(ga[:, ax].min(), gb[:, ax].min()), min(ga[:, ax].max(), gb[:, ax].max())
            sel = (ga[:, ax] >= lo) & (ga[:, ax] <= hi)
            if hi <= lo or sel.sum() < 2:
                say(f"  {k:10s} {ca}-{cb}: no overlap"); continue
            d = poly_dist(ga[sel], gb[np.argsort(gb[:, ax])])
            say(f"  {k:10s} {ca}-{cb}: {sel.sum():2d} pts in the overlap, median {np.median(d):5.1f} in, max {d.max():5.1f} in")

out = FIT.parent / "LINE_CHECK.txt"
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n->", out)

if "--plot" in args:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(14, 7.5))
    ax.add_patch(plt.Rectangle((0, 0), 480, 240, fc="none", ec="#999", ls="--", lw=1))
    cols = {"CH01": "#1f77b4", "CH02": "#d62728", "CH03": "#2ca02c", "CH04": "#ff7f0e", "CH05": "#9467bd", "CH06": "#8c564b"}
    for c in sorted(labels):
        for k, uv in sorted(labels[c].items()):
            g = cams[c].to_paddock(uv, z_mm=0.0, units="in"); g = g[np.isfinite(g).all(1)]
            if len(g) < 2:
                continue
            if k.startswith("X"):
                ax.plot(g[:, 0], g[:, 1], "-", color=cols[c], lw=1, alpha=0.8); ax.plot(g[:, 0], g[:, 1], ".", color=cols[c], ms=4)
                ax.axvline(float(k[1:]), color="#ccc", lw=0.6, zorder=0)
            else:
                ax.plot(g[:, 0], g[:, 1], "-", color=cols[c], lw=2.2, alpha=0.9)
    for c in cams.values():
        p = c.centre / MM
        ax.plot(p[0], p[1], "^", ms=9, color=cols[c.name]); ax.annotate(c.name, (p[0], p[1]), textcoords="offset points", xytext=(6, 4), fontsize=8, color=cols[c.name])
    for c, col in cols.items():
        ax.plot([], [], "-", color=col, label=c)
    ax.legend(loc="upper center", ncol=6, fontsize=8)
    ax.set_aspect("equal"); ax.set_xlim(-40, 520); ax.set_ylim(-40, 280)
    ax.set_xlabel("paddock x (in)"); ax.set_ylabel("paddock y (in)")
    ax.set_title("Operator's cord and wall-foot labels pushed onto the ground by each camera" + (" (frame-corrected)" if CORRECT else " (raw fit frame)"))
    fig.tight_layout(); fig.savefig(FIT.parent / "line_check.png", dpi=130)
    print("->", FIT.parent / "line_check.png")
