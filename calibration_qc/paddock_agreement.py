# -*- coding: utf-8 -*-
r"""How far apart do two cameras put the SAME physical point on the paddock floor?

This is the number that matters for using the calibration: not the reprojection residual in
pixels, but how many millimetres two cameras disagree by once each has mapped its own pixels to
paddock (x, y).

It is measured on real measurements only. Every ChArUco corner has an id, so corner 37 of the
board at T53 is one physical spot on the ground; each camera that decoded it has its own pixel for
it. Push those pixels through each camera's own pixel -> paddock map at the height of the printed
plane (6 mm) and the spread between the answers is the disagreement, with nothing modelled or
assumed in between.

Two things it does NOT measure, both of which matter more in use:
  * height. A pixel is a ray; the map has to be told how high the thing is. Here we know (6 mm).
    For an animal you do not, and paddock_map.height_sensitivity() is the penalty.
  * the paddock frame itself. Every camera is being compared with every other in ONE frame, so a
    common error in that frame (see the cone-label note in CALIBRATION_FIT.txt) cancels here and
    would move all the cameras together.

Usage: python paddock_agreement.py [--z 6] [--plot]
"""
import sys, itertools
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_data as fd, paddock_map as pm                                   # noqa: E402

args = sys.argv[1:]
Z_MM = float(args[args.index("--z") + 1]) if "--z" in args else 6.0
OUT = Path(r"E:\calibration\qc")
MM_PER_IN = 25.4
L = []


def say(s=""):
    print(s, flush=True)
    L.append(s)


cams = pm.load()
P = [p for p in fd.all_placements() if not p["bad"] and not p["weak"]]
# views the fit itself refused (a plate that is not flat where the others are, or that no camera
# geometry could explain). Including them here would measure those, not the calibration.
_z = np.load(pm.FIT, allow_pickle=False)
DROPPED = {tuple(s.split("|")[:4]) for s in _z["dropped_views"]} if "dropped_views" in _z else set()
P = [p for p in P if (p["cam"], p["session"], p["station"], p["win"]) not in DROPPED]
if DROPPED:
    say_later = (f"  {len(DROPPED)} camera-views excluded because the fit itself rejected them: "
                 + ", ".join(sorted(f"{d[0]}/{d[2]}" for d in DROPPED)))
else:
    say_later = "  (no views were rejected by the fit)"

# --------------------------------------------------------------- one physical point per corner id
shared = {}
for p in P:
    if p["cam"] not in cams:
        continue
    key = (p["session"], p["station"], p["win"])
    xy = cams[p["cam"]].to_paddock(p["px"], z_mm=Z_MM)          # paddock mm, per corner
    for i, c in zip(p["ids"], xy):
        if np.isfinite(c).all():
            shared.setdefault((key, int(i)), {})[p["cam"]] = c

pairs = {}
per_point = []
for (key, cid), d in shared.items():
    if len(d) < 2:
        continue
    names = sorted(d)
    ctr = np.mean([d[n] for n in names], 0)
    per_point.append((key, cid, ctr, max(np.linalg.norm(d[a] - d[b])
                                         for a, b in itertools.combinations(names, 2))))
    for a, b in itertools.combinations(names, 2):
        pairs.setdefault((a, b), []).append((np.linalg.norm(d[a] - d[b]), d[a] - d[b], ctr))

say("=" * 96)
say(f"CROSS-CAMERA AGREEMENT ON THE PADDOCK FLOOR   (points taken at z = {Z_MM:.0f} mm)")
say("=" * 96)
say("")
say(f"  {len(shared)} board corners mapped; {len(per_point)} of them were decoded by two or more")
say("  cameras, so each has two or more independent paddock positions for one physical spot.")
say(say_later)
say("")
say(f"  {'pair':15s} {'n pts':>6s} {'boards':>7s} {'median':>8s} {'p90':>8s} {'max':>8s}"
    f"   {'systematic offset (dx, dy)':>28s}")
for (a, b), v in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
    dist = np.array([x[0] for x in v])
    off = np.median(np.array([x[1] for x in v]), 0)
    say(f"  {a}-{b:9s} {len(v):6d} {len({tuple(k[0]) for k, dd in shared.items() if a in dd and b in dd}):7d}"
        f" {np.median(dist):6.0f}mm {np.percentile(dist,90):6.0f}mm {dist.max():6.0f}mm"
        f"   {off[0]:+9.0f},{off[1]:+9.0f} mm")

allpts = np.array([x[3] for x in per_point])
say("")
say(f"  over every shared corner: median {np.median(allpts):.0f} mm, p90 {np.percentile(allpts, 90):.0f} mm,"
    f" max {allpts.max():.0f} mm")
say(f"  ({np.median(allpts)/MM_PER_IN:.1f} in / {np.percentile(allpts,90)/MM_PER_IN:.1f} in)")

# --------------------------------------------------------------- where the disagreement lives
say("")
say("  by station (worst pair at that station, median over its corners):")
by_st = {}
for key, cid, ctr, d in per_point:
    by_st.setdefault((key[1], key[0][-5:]), []).append((d, ctr))
rows = [(st, s, np.median([x[0] for x in v]), np.mean([x[1] for x in v], 0), len(v))
        for (st, s), v in by_st.items()]
say(f"  {'station':9s} {'session':9s} {'x,y (in)':>16s} {'n corners':>10s} {'disagreement':>13s}")
for st, s, d, ctr, n in sorted(rows, key=lambda r: -r[2]):
    say(f"  {st:9s} {s:9s} {ctr[0]/MM_PER_IN:7.1f},{ctr[1]/MM_PER_IN:7.1f} {n:10d} {d:10.0f} mm")

# --------------------------------------------------------------- what a wrong height costs
say("")
say("  for comparison, the error from assuming the wrong HEIGHT (a pixel is a ray, not a point):")
say(f"  {'camera':8s} {'mm slide per mm of height':>26s} {'a 60 mm-high back read as ground':>34s}")
for c in cams.values():
    s = c.height_sensitivity()
    say(f"  {c.name:8s} {s:22.2f} {60*s:30.0f} mm")

(OUT / "PADDOCK_AGREEMENT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n->", OUT / "PADDOCK_AGREEMENT.txt")

if "--plot" in args:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.add_patch(plt.Rectangle((0, 0), 480, 240, fc="#f4f4ef", ec="#999"))
    for st, (x, y) in fd.LATTICE.items():
        ax.plot(x, y, "o", ms=3, mfc="none", mec="#bbb", zorder=1)
    pts = np.array([x[2] for x in per_point]) / MM_PER_IN
    val = np.array([x[3] for x in per_point])
    sc = ax.scatter(pts[:, 0], pts[:, 1], c=val, s=14, cmap="viridis",
                    vmin=0, vmax=np.percentile(val, 95), zorder=3)
    plt.colorbar(sc, ax=ax, label="disagreement between cameras (mm)")
    for c in cams.values():
        p = c.centre / MM_PER_IN
        ax.plot(p[0], p[1], "^", ms=11, color="#c0392b", zorder=5)
        ax.annotate(f"{c.name}\n{c.centre[2]/1000:.2f} m", (p[0], p[1]), textcoords="offset points",
                    xytext=(8, -4), fontsize=8, color="#c0392b")
    ax.set_xlim(-20, 500); ax.set_ylim(-20, 260); ax.set_aspect("equal")
    ax.set_xlabel("paddock x (inches from pole A0)"); ax.set_ylabel("paddock y (inches)")
    ax.set_title(f"Where the cameras are, and how far apart they put the same point (z = {Z_MM:.0f} mm)")
    fig.tight_layout()
    fig.savefig(OUT / "paddock_agreement.png", dpi=130)
    print("->", OUT / "paddock_agreement.png")
