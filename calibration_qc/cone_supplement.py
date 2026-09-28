# -*- coding: utf-8 -*-
r"""Where extra cones help the camera handoffs: the analysis behind CALIB_CONE_SHEET_2026-09-26.html.

From the release fit (paddock_map.load(), ground correction and verified support included), per camera:
which paddock points it SEES (in frame, in front, a cone at least MIN_PX pixels per 10 cm of ground) and
which it can MAP (inside the support frame_correction.py stores: the convex hull of its labels + 12 in).
Then:
  1. candidates = the 46 mid-points of the 2026-09-19 supplement sheet (T-cord mid-points 27 in above
     each tick, V/F-column mid-points half-way between two T cords), ordered greedily by the
     shared-cone coverage they add to every two-camera overlap (a grid point counts as covered within
     R_COVER of a cone both cameras see; a camera's own coverage counts half);
  2. scenarios - what the mid-points, 4 corner cones and the optional new cords (Y39, Y201 along the
     length, X60, X420 across) do to each camera's mapped area and to how many cameras map each point
     at the height of a rat's back;
  3. edge cones on the existing T cords that widen CH03-CH06's mapped area beyond scenario 2;
  4. station cones visible on 2026-09-18 but never labelled;
  5. a ball sweep for a ball moved as a stand-in rat (handoff disagreement at a known height everywhere,
     and the delay between camera streams): lanes along and across the paddock, a lap along the walls;
     how much of every two-camera overlap it passes and how often it crosses each camera's edge.
This is geometry only: a house or pole can still hide a cone, and more coverage does not by itself
mean smaller disagreement between cameras - the new cones first measure that, then the ground
correction is refitted with them.

Usage: python cone_supplement.py [--out <dir>]
Output: <out, default <calibration root>\qc\cone_supplement>\cone_supplement.json (read by cone_sheet.py),
        CONE_SUPPLEMENT.txt, cone_supplement.png
"""
import sys, json, hashlib, itertools
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm                       # noqa: E402

args = sys.argv[1:]
OUT = Path(args[args.index("--out") + 1]) if "--out" in args else qc_paths.QC_ROOT / "cone_supplement"

CONE_Z = 50.0            # mm, top of the disc cone (as frame_correction.py uses)
Z_RAT = 60.0             # mm, a rat's back: the height at which "maps this point" is asked
MIN_PX = 12.0            # a cone must span at least this many pixels per 10 cm of ground to be clickable
R_COVER = 30.0           # in: a grid point counts as covered by a cone within this radius
STEP = 3.0               # in, grid spacing
MID_T_Y = [39, 93, 147, 201]            # 27 in above the ticks 12 / 66 / 120 / 174 of every T cord
MID_VF_Y = [66, 120, 174]               # the V/F columns, half-way between two T cords at a tick's y
CORNERS = {"C1": (12, 12), "C2": (12, 228), "C3": (468, 12), "C4": (468, 228)}   # 12 in outside the end ticks
EDGE = {"E1": (384, 21), "E2": (96, 189)}   # the edge picks of step 3 on 2026-09-26 (CH04, CH05), fixed for the sheet
NEW_CORDS = [("y", 39), ("y", 201), ("x", 60), ("x", 420)]
Z_BALL = 110.0          # mm, centre of a ball ~22 cm across (the route choice barely depends on it)
SWEEP_Y = [12, 39, 66, 93, 120, 147, 174, 201, 228]   # lanes along the length: every tick row and half-way between
SWEEP_X = [24, 60, 96, 132, 168, 204, 240, 276, 312, 348, 384, 420, 456]   # lanes across: every T cord and half-way
WALL_GAP = 8.0          # in: the wall lap keeps the ball centre this far from the wall foot (~20 cm)
R_SWEEP = 14.0          # in: a cell counts as swept within this distance of a lane (about half a lane spacing)

cams = pm.load()
names = sorted(cams)
S, QC = qc_paths.resolve(None)


def px10(cam, xy, z):
    """local image scale: pixels per 10 cm of ground at height z, the smaller of the x and y directions."""
    xy = np.atleast_2d(np.asarray(xy, float))
    d = 100.0 / 25.4
    u0 = cam.to_paddock_inv(xy, z_mm=z, units="in")
    return np.minimum(np.linalg.norm(cam.to_paddock_inv(xy + [d, 0], z_mm=z, units="in") - u0, axis=1),
                      np.linalg.norm(cam.to_paddock_inv(xy + [0, d], z_mm=z, units="in") - u0, axis=1))


def seen(cam, xy, z=CONE_Z, margin=30):
    """in frame (margin px), in front, and big enough to click."""
    xy = np.atleast_2d(np.asarray(xy, float))
    return cam.sees(xy, z_mm=z, units="in", margin=margin) & (px10(cam, xy, z) >= MIN_PX)


def within(points, grid, r=R_COVER):
    if not len(points):
        return np.zeros(len(grid), bool)
    P = np.asarray(points, float)
    return np.sqrt(((grid[:, None, :] - P[None, :, :]) ** 2).sum(-1)).min(1) <= r


def inflate(h):
    ctr = h.mean(0); v = h - ctr
    return ctr + v * (1 + 12.0 / np.maximum(np.linalg.norm(v, axis=1), 1e-9))[:, None]


def cord_points(axis, val, step=6.0):
    t = np.arange(3, 480 if axis == "y" else 240, step)
    return np.stack([t, np.full_like(t, val)], 1) if axis == "y" else np.stack([np.full_like(t, val), t], 1)


# ---------------------------------------------------------------- existing labels and candidates
labelled = {}
for c in names:
    lab = qc_paths.load_cones(QC, c, S, space="upright")
    labelled[c] = {st: fd.LATTICE[st] for st in lab if st in fd.LATTICE}

cands = {}
for i, x in enumerate(fd.TRAIN_X, 1):
    for j, y in enumerate(MID_T_Y, 1):
        cands[f"T{i}{j}M"] = (x, y, "T cord")
for i, x in enumerate(fd.VT_X, 1):
    for j, y in enumerate(MID_VF_Y, 1):
        cands[f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}M"] = (x, y, "V/F column")

# ---------------------------------------------------------------- 1. greedy order of the mid-points
gx, gy = np.meshgrid(np.arange(6, 480, STEP), np.arange(6, 240, STEP))
G1 = np.stack([gx.ravel(), gy.ravel()], 1)
vis1 = {c: seen(cams[c], G1) for c in names}
pairs = [(a, b) for a, b in itertools.combinations(names, 2) if (vis1[a] & vis1[b]).sum() > 20]

report = {}
for k, (x, y, kind) in cands.items():
    info = {}
    for c in names:
        if seen(cams[c], (x, y))[0]:
            near = min((np.hypot(x - p[0], y - p[1]) for p in labelled[c].values()), default=np.inf)
            uv = cams[c].to_paddock_inv(np.array([x, y], float), z_mm=CONE_Z, units="in")
            inside = bool(np.isfinite(cams[c].to_paddock(uv, z_mm=CONE_Z, units="in")).all())
            info[c] = dict(px10cm=round(float(px10(cams[c], (x, y), CONE_Z)[0]), 1),
                           nearest_label_in=round(float(near), 1), in_support=inside)
    report[k] = dict(x=x, y=y, kind=kind, cams=info)
cand_seen = {k: sorted(report[k]["cams"]) for k in cands}


def shared(a, b):
    return [labelled[a][s] for s in labelled[a] if s in labelled[b]]


pc = {(a, b): within(shared(a, b), G1) & vis1[a] & vis1[b] for a, b in pairs}
oc = {a: within(list(labelled[a].values()), G1) & vis1[a] for a in names}
pair_before = {f"{a}-{b}": float(pc[(a, b)].sum() / max((vis1[a] & vis1[b]).sum(), 1)) for a, b in pairs}
disc = {k: within([cands[k][:2]], G1) for k in cands}
order, remaining = [], [k for k in cands if cand_seen[k]]
while remaining:
    gains = []
    for k in remaining:
        s, D = cand_seen[k], disc[k]
        g = sum((D & vis1[a] & vis1[b] & ~pc[(a, b)]).sum() for a, b in pairs if a in s and b in s)
        g += 0.5 * sum((D & vis1[a] & ~oc[a]).sum() for a in s)
        gains.append((float(g), k))
    gains.sort(reverse=True)
    g, k = gains[0]
    if g <= 0:
        break
    s, D = cand_seen[k], disc[k]
    for a, b in pairs:
        if a in s and b in s:
            pc[(a, b)] |= D & vis1[a] & vis1[b]
    for a in s:
        oc[a] |= D & vis1[a]
    order.append((k, g)); remaining.remove(k)
gain = dict(order)
pair_after = {f"{a}-{b}": float(pc[(a, b)].sum() / max((vis1[a] & vis1[b]).sum(), 1)) for a, b in pairs}

# ---------------------------------------------------------------- 2. scenarios at the rat's height
gx, gy = np.meshgrid(np.arange(1.5, 480, STEP), np.arange(1.5, 240, STEP))
G = np.stack([gx.ravel(), gy.ravel()], 1)
see = {c: cams[c].sees(G, z_mm=Z_RAT, units="in", margin=10) for c in names}
hull0 = {c: np.asarray(cams[c].correction["support"], float) for c in names}
mids = [cands[k][:2] for k in cands]
mids_t = [cands[k][:2] for k in cands if cands[k][2] == "T cord"]
SCEN = [("today", [], []),
        ("+28 T-cord mid-points", mids_t, []),
        ("+18 V/F mid-points +4 corners", mids + list(CORNERS.values()), []),
        ("+cords Y39, Y201", mids + list(CORNERS.values()), NEW_CORDS[:2]),
        ("+cords X60, X420", mids + list(CORNERS.values()), NEW_CORDS)]
scen, scen_maps, hulls = [], {}, {}
for sname, pts, cords in SCEN:
    nmap = np.zeros(len(G), int); per = {}; hulls[sname] = {}
    for c in names:
        new = [p for p in pts if seen(cams[c], p)[0]]
        for axis, val in cords:
            q = cord_points(axis, val); new += [tuple(p) for p in q[seen(cams[c], q, z=0.0)]]
        P = np.vstack([hull0[c]] + ([np.asarray(new, float)] if new else []))
        hull = inflate(P[ConvexHull(P).vertices]) if new else hull0[c]
        hulls[sname][c] = hull
        m = see[c] & MPath(hull).contains_points(G)
        per[c] = dict(new_points=len(new), mapped=float(m.mean()), seen=float(see[c].mean()))
        nmap += m.astype(int)
    scen.append(dict(name=sname, per_cam=per, mapped_by_0=float((nmap == 0).mean()),
                     mapped_by_1=float((nmap == 1).mean()), mapped_by_2plus=float((nmap >= 2).mean())))
    scen_maps[sname] = nmap

# ---------------------------------------------------------------- 3. edge cones for the small cameras
ticks = set(fd.TRAIN_Y) | set(MID_T_Y)
edge_cands = [(x, float(y)) for x in fd.TRAIN_X for y in range(3, 240, 6) if y not in ticks]
base = mids + list(CORNERS.values())
edge = {}
for c in ("CH03", "CH04", "CH05", "CH06"):
    cam = cams[c]
    P = np.vstack([hull0[c], np.asarray([p for p in base if seen(cam, p, margin=60)[0]], float).reshape(-1, 2)])

    def area(Q):
        return float((see[c] & MPath(inflate(Q[ConvexHull(Q).vertices])).contains_points(G)).mean())
    a0 = area(P)
    cc = [p for p in edge_cands if seen(cam, p, margin=60)[0]]
    picks = []
    for _ in range(3):
        if not cc:
            break
        best = max(cc, key=lambda p: area(np.vstack([P, [p]])))
        a1 = area(np.vstack([P, [best]]))
        if a1 - a0 < 0.002:
            break
        P = np.vstack([P, [best]]); cc.remove(best)
        picks.append(dict(x=best[0], y=best[1], gain=a1 - a0,
                          also_seen_by=[o for o in names if o != c and seen(cams[o], best)[0]]))
        a0 = a1
    edge[c] = dict(mapped_after=a0, picks=picks)

extras = {}
for k, xy in {**CORNERS, **EDGE}.items():
    extras[k] = dict(x=xy[0], y=xy[1], cams={c: round(float(px10(cams[c], xy, CONE_Z)[0]), 1)
                                              for c in names if seen(cams[c], xy)[0]})

# ---------------------------------------------------------------- 4. visible but never labelled
unlabelled = {}
for c in names:
    miss = [st for st, xy in sorted(fd.LATTICE.items())
            if st not in labelled[c] and seen(cams[c], xy, margin=60)[0]]
    if miss:
        unlabelled[c] = miss

# ---------------------------------------------------------------- 5. ball sweep over the whole paddock
# A ball of known size moved as a stand-in rat. Every frame in which two cameras map it gives the handoff
# disagreement at a known height at that spot; the lag that aligns two cameras' tracks is the delay between the
# streams. The error field is wanted everywhere a rat can go, so the ball covers the paddock in lanes (a person
# wandering at random over-samples the middle and misses the corners and walls), then a lap along the walls,
# then free wandering. Camera edges are those of the calibration refitted with the cones.
BALL_HULLS = hulls[SCEN[2][0]]
seeb = {c: cams[c].sees(G, z_mm=Z_BALL, units="in", margin=10) & MPath(BALL_HULLS[c]).contains_points(G) for c in names}
bpairs = [(a, b) for a, b in itertools.combinations(names, 2) if (seeb[a] & seeb[b]).sum() > 20]
lanes = [("y", float(y)) for y in SWEEP_Y] + [("x", float(x)) for x in SWEEP_X]
W = WALL_GAP
dist = np.full(len(G), np.inf)
for axis, v in lanes + [("y", W), ("y", 240 - W), ("x", W), ("x", 480 - W)]:     # lanes, then the wall lap
    dist = np.minimum(dist, np.abs(G[:, 1] - v) if axis == "y" else np.abs(G[:, 0] - v))
near = dist <= R_SWEEP
ball_pairs = {f"{a}-{b}": float((seeb[a] & seeb[b] & near).sum() / (seeb[a] & seeb[b]).sum()) for a, b in bpairs}
ball_cams = {c: float((seeb[c] & near).sum() / max(seeb[c].sum(), 1)) for c in names}
edge_x = {c: 0 for c in names}            # how often the lanes cross each camera's edge
for axis, v in lanes:
    t = np.arange(6.0, (480 if axis == "y" else 240) - 6.0 + 1e-9, 1.0)
    P = np.stack([t, np.full_like(t, v)], 1) if axis == "y" else np.stack([np.full_like(t, v), t], 1)
    for c in names:
        on = seen(cams[c], P, z=Z_BALL) & MPath(BALL_HULLS[c]).contains_points(P)
        edge_x[c] += int(np.abs(np.diff(on.astype(int))).sum())
path_in = (len(SWEEP_Y) * (480 - 2 * W) + len(SWEEP_X) * (240 - 2 * W) + 2 * (2 * (480 - 2 * W) + 2 * (240 - 2 * W)))
ball = dict(z_mm=Z_BALL, lanes_y=SWEEP_Y, lanes_x=SWEEP_X, wall_gap_in=W, r_sweep_in=R_SWEEP,
            path_m=round(path_in * 0.0254, 1), pair_coverage=ball_pairs, camera_coverage=ball_cams,
            edge_crossings=edge_x, max_gap_in=float(dist.max()))

# ---------------------------------------------------------------- write
OUT.mkdir(parents=True, exist_ok=True)
res = dict(fit=str(pm.FIT), fit_sha256=hashlib.sha256(Path(pm.FIT).read_bytes()).hexdigest(),
           params=dict(CONE_Z=CONE_Z, Z_RAT=Z_RAT, MIN_PX_PER_10CM=MIN_PX, R_COVER_IN=R_COVER, STEP_IN=STEP),
           labelled={c: sorted(labelled[c]) for c in names},
           positions={k: dict(**report[k], gain=round(gain.get(k, 0.0), 1)) for k in cands},
           order=[k for k, _ in order], no_gain=[k for k in cands if k not in gain],
           pairs_shared_cone_coverage={p: dict(before=pair_before[p], after=pair_after[p]) for p in pair_before},
           scenarios=scen, edge=edge, extras=extras, unlabelled=unlabelled,
           ball=ball)
(OUT / "cone_supplement.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

L = ["CONE SUPPLEMENT - where extra cones help the camera handoffs", f"fit {pm.FIT}  sha256 {res['fit_sha256'][:16]}", ""]
L.append("shared-cone coverage of each two-camera overlap (within %.0f in), today -> after the 46 mid-points:" % R_COVER)
L += [f"  {p:10s} {v['before']:4.0%} -> {v['after']:4.0%}" for p, v in res["pairs_shared_cone_coverage"].items()]
L.append("\nmid-points in greedy order (gain = overlap cells newly covered; cameras with px per 10 cm):")
for k in res["order"] + res["no_gain"]:
    r = res["positions"][k]
    L.append(f"  {k:6s} ({r['x']:3.0f},{r['y']:3.0f}) gain {r['gain']:6.1f}  " +
             ", ".join(f"{c}[{v['px10cm']:.0f}{'' if v['in_support'] else ', outside support'}]" for c, v in r["cams"].items()))
L.append("\nscenarios (paddock share mapped at z = %.0f mm by 0 / 1 / 2+ cameras; per camera mapped / seen):" % Z_RAT)
for s in scen:
    L.append(f"  {s['name']:32s} {s['mapped_by_0']:5.1%} {s['mapped_by_1']:5.1%} {s['mapped_by_2plus']:5.1%}   " +
             "  ".join(f"{c} {v['mapped']:5.1%}/{v['seen']:5.1%}" for c, v in s["per_cam"].items()))
L.append("\nedge cones on the T cords beyond the mid-points and corners:")
for c, e in edge.items():
    L.append(f"  {c}: maps {e['mapped_after']:.1%}; " + ("; ".join(
        f"({p['x']:.0f},{p['y']:.0f}) +{p['gain']:.1%} also seen by {p['also_seen_by']}" for p in e["picks"]) or "no pick"))
L.append("\ncorner and edge cones: " + "; ".join(f"{k} ({v['x']},{v['y']}) {sorted(v['cams'])}" for k, v in extras.items()))
L.append(f"\nball sweep: {len(SWEEP_Y)} lanes along + {len(SWEEP_X)} across + a wall lap each way = "
         f"{ball['path_m']} m; every cell within {ball['max_gap_in']:.0f} in of the path")
L.append("  share of each overlap within %.0f in: " % R_SWEEP + "  ".join(f"{p} {v:.0%}" for p, v in ball_pairs.items()))
L.append("  lane crossings of each camera's edge: " + "  ".join(f"{c} {n}" for c, n in edge_x.items()))
L.append("visible on 2026-09-18 but never labelled: " + "; ".join(f"{c} {', '.join(v)}" for c, v in unlabelled.items()))
(OUT / "CONE_SUPPLEMENT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))

import matplotlib                                                         # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                           # noqa: E402
fig, axs = plt.subplots(len(scen_maps), 1, figsize=(10, 4.2 * len(scen_maps)))
for ax, (k, m) in zip(axs, scen_maps.items()):
    sc = ax.scatter(G[:, 0], G[:, 1], c=m, s=5, marker="s", cmap="viridis", vmin=0, vmax=4)
    for st, (x, y) in fd.LATTICE.items():
        ax.plot(x, y, "k+" if st[0] == "T" else "kx", ms=4)
    ax.set_title(f"{k}: cameras that can map each point (z = {Z_RAT:.0f} mm)")
    ax.set_xlim(0, 480); ax.set_ylim(0, 240); ax.set_aspect("equal")
    plt.colorbar(sc, ax=ax, fraction=0.02)
fig.savefig(OUT / "cone_supplement.png", dpi=90, bbox_inches="tight")
print(f"-> {OUT}")
