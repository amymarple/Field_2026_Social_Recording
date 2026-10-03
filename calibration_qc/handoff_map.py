# -*- coding: utf-8 -*-
r"""One primary camera per region of the paddock, and how far a tracked point jumps where the primary changes.
A CHECK on the release (2026-10-02), measured on the operator-reviewed 20 Hz ball (held + wrong frames out).

Why: an animal needs only one camera at a time on the ground (pixel -> paddock at an assumed height); several
cameras matter where it is handed from one to the next. So the useful numbers are (1) each camera's error in each
part of the paddock, to choose who covers it, and (2) the disagreement between the two cameras at every boundary
where the primary changes - the jump a track makes there even if the animal stands still.

(1) Error of camera c in a cell: for every detection of c, the other cameras that saw the ball at the same aligned
instant (ball_sync20.py clocks, held20.json) give a consensus position (their median); c's error is its distance
to that consensus, binned by the consensus position (CELL x CELL in). It is relative - it contains the others'
errors too, and where only two cameras see a cell both get the same number - but it is measured on the moving
ball at 105 mm, close to an animal's back. (2) Primary of a cell (--rule res, default): among the cameras whose
verified support covers the cell centre and that see it at 60 mm, the one with the finest ground resolution (px per
cm, worse axis). --rule err picks the lowest ball error instead (>= MIN_N detections; resolution where none) - it
was tried first and splits the middle into a CH01 / CH02 checkerboard, because two-camera cells cannot tell who is
right. One 3 x 3 majority pass removes single-cell islands. (3) Jump at a boundary A|B: the median
distance between A's and B's positions for the same instant, over ball pairs whose midpoint lies in a cell on
either side of that boundary.

--rays <RAYMAP json | candidate | warp>: a ray correction, or the ground warp (release 10-02b); default the release.

Usage: python handoff_map.py [--cell 40] [--rule res|err] [--fit <camera_fit.npz>] [--rays candidate] [--track <dir>] [--out <dir>]
Output: <out>\HANDOFF_MAP.txt, handoff_map.png, handoff_map.json  (default out: <qc root>\handoff)
"""
import sys, json, itertools, collections
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
FIT = Path(opt("--fit", str(pm.FIT)))
TRACK = Path(opt("--track", str(qc_paths.QC_ROOT / "2026-09-30" / "ball" / "track20")))
OUT = Path(opt("--out", str(qc_paths.QC_ROOT / "handoff"))); OUT.mkdir(parents=True, exist_ok=True)
DRIFT = HERE / "session_2026-09-30_drift_final.json"
CELL, MIN_N, Z, Z_RAT, GAP, IN = float(opt("--cell", "40")), 25, 105.0, 60.0, 0.25, 25.4
CAMS = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
RULE = opt("--rule", "res")
RAYS = opt("--rays", "release")
cams = pm.load(FIT, rays=None if RAYS == "warp" else RAYS)
drift = json.loads(DRIFT.read_text(encoding="utf-8"))["cameras"]
H = json.loads((TRACK / "held20.json").read_text(encoding="utf-8"))
flags_p = TRACK / "ball20_flags.json"
F = json.loads(flags_p.read_text(encoding="utf-8")) if flags_p.exists() else {"flags": []}
off, held = H["offsets_s"], [(h["t0"], h["t1"]) for h in H["intervals"]]
wrong = {(f["cam"], f["entry"]) for f in F["flags"] if f.get("flag") == "wrong"}


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = drift.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        A = np.asarray(d["affine_30_to_18"], float); return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


def load(cam):
    fr = json.loads((TRACK / f"ball20_{cam}.json").read_text(encoding="utf-8"))["frames"]
    i = np.arange(len(fr)); a, b = np.polyfit(i, [f[0] for f in fr], 1)
    sel = np.array([k for k, f in enumerate(fr) if f[3]])
    c = cams[cam]; d = c.rays(to_0918(cam, [[fr[k][3]["cx"], fr[k][3]["cy"]] for k in sel])); s = (Z - c.centre[2]) / d[:, 2]
    xy = pm.fit_to_physical((c.centre + s[:, None] * d)[:, :2], c.correction); xy[~(s > 0)] = np.nan
    t = (a * i + b)[sel] - off[cam]
    k = np.isfinite(xy).all(1)
    for t0, t1 in held:
        k &= ~((t >= t0) & (t <= t1))
    k &= np.array([(cam, int(e)) not in wrong for e in sel])
    o = np.argsort(t[k])
    return t[k][o], xy[k][o]


def interp(T, P, t):
    j = np.searchsorted(T, t); ok = (j > 0) & (j < len(T)); j = np.clip(j, 1, len(T) - 1)
    t0, t1 = T[j - 1], T[j]; ok &= (t1 - t0) <= GAP
    w = np.where(t1 > t0, (t - t0) / np.maximum(t1 - t0, 1e-9), 0.0)
    out = P[j - 1] + w[:, None] * (P[j] - P[j - 1]); out[~ok] = np.nan
    return out


tr = {c: load(c) for c in CAMS}
NX, NY = int(np.ceil(480 / CELL)), int(np.ceil(240 / CELL))
cell = lambda xy: (np.clip((xy[:, 0] / IN // CELL).astype(int), 0, NX - 1), np.clip((xy[:, 1] / IN // CELL).astype(int), 0, NY - 1))
# (1) per camera, per cell: distance to the other cameras' consensus
err = collections.defaultdict(list)
for c, (T, P) in tr.items():
    others = np.stack([interp(tr[o][0], tr[o][1], T) for o in CAMS if o != c])          # (5, n, 2)
    n_ok = np.isfinite(others[..., 0]).sum(0)
    with np.errstate(all="ignore"):
        cons = np.nanmedian(others, axis=0)
    k = n_ok >= 1
    e = np.hypot(*(P[k] - cons[k]).T); ix, iy = cell(cons[k])
    for a, b, v in zip(ix, iy, e):
        err[(c, a, b)].append(v)
# resolution (px per cm at the animal height) and coverage per camera and cell
centres = np.array([[(a + 0.5) * CELL * IN, (b + 0.5) * CELL * IN] for b in range(NY) for a in range(NX)])
res, cover = {}, {}
for c in CAMS:
    cm = cams[c]
    fit_xy = pm.physical_to_fit(centres, cm.correction)
    cover[c] = cm.in_support(fit_xy) & cm.sees(centres, z_mm=Z_RAT)
    u0 = cm.to_paddock_inv(centres, z_mm=Z_RAT); ux = cm.to_paddock_inv(centres + [10, 0], z_mm=Z_RAT); uy = cm.to_paddock_inv(centres + [0, 10], z_mm=Z_RAT)
    res[c] = np.minimum(np.hypot(*(ux - u0).T), np.hypot(*(uy - u0).T))        # px per cm, worse axis
prim = np.full((NY, NX), "", object); why = {}
for b in range(NY):
    for a in range(NX):
        k = b * NX + a
        cand = [c for c in CAMS if cover[c][k]]
        scored = [(np.median(err[(c, a, b)]), c) for c in cand if len(err[(c, a, b)]) >= MIN_N] if RULE == "err" else []
        if RULE == "res" and cand:
            c = max(cand, key=lambda c: res[c][k]); prim[b, a] = c
            why[(a, b)] = f"{np.median(err[(c, a, b)]):.0f}" if len(err[(c, a, b)]) >= MIN_N else f"r{res[c][k]:.0f}"
        elif scored:
            v, c = min(scored); prim[b, a] = c; why[(a, b)] = f"{v:.0f}"
        elif cand:
            c = max(cand, key=lambda c: res[c][k]); prim[b, a] = c; why[(a, b)] = "res"
# one majority pass against single-cell islands
P2 = prim.copy()
for b in range(NY):
    for a in range(NX):
        nb = [prim[j, i] for j in range(max(0, b - 1), min(NY, b + 2)) for i in range(max(0, a - 1), min(NX, a + 2)) if (i, j) != (a, b) and prim[j, i]]
        cnt = collections.Counter(nb)
        if nb and cnt[prim[b, a]] == 0 and cover[cnt.most_common(1)[0][0]][b * NX + a]:
            P2[b, a] = cnt.most_common(1)[0][0]; why[(a, b)] = "island"
prim = P2
# (3) jumps at boundaries
bnd = collections.defaultdict(set)
for b in range(NY):
    for a in range(NX):
        for da, db in ((1, 0), (0, 1)):
            a2, b2 = a + da, b + db
            if a2 < NX and b2 < NY and prim[b, a] and prim[b2, a2] and prim[b, a] != prim[b2, a2]:
                key = tuple(sorted((prim[b, a], prim[b2, a2])))
                bnd[key] |= {(a, b), (a2, b2)}
L = [f"HANDOFF MAP  fit {FIT}{'; cameras: ' + RAYS}; reviewed 20 Hz ball at z = {Z:.0f} mm (held and wrong frames out); cells {CELL:.0f} in; primary by {RULE}",
     "", "primary camera per cell (x along the length, west x 0 on the left; rows from y 240 at the top to y 0):"]
for b in reversed(range(NY)):
    L.append(f"  y {b * CELL:3.0f}-{min(240, (b + 1) * CELL):3.0f} " + " ".join(f"{(prim[b, a] or '----')[2:]:>2s}:{why.get((a, b), '-'):>4s}" for a in range(NX)))
L.append("  (CHxx:number = that camera's ball error vs the others' consensus, mm; rN = no ball there, resolution N px/cm; island = smoothed)")
L += ["", "ground resolution at 60 mm, px per cm (worse axis), per cell, cameras covering it:"]
for b in reversed(range(NY)):
    L.append(f"  y {b * CELL:3.0f}-{min(240, (b + 1) * CELL):3.0f} " + " | ".join(
        ",".join(f"{c[2:]}:{res[c][b * NX + a]:.0f}" for c in CAMS if cover[c][b * NX + a]) or "-" for a in range(NX)))
L += ["", "camera error by cell (median mm, n) for every camera with >= %d detections in it:" % MIN_N]
for b in reversed(range(NY)):
    for a in range(NX):
        row = [f"{c} {np.median(err[(c, a, b)]):3.0f} ({len(err[(c, a, b)])})" for c in CAMS if len(err[(c, a, b)]) >= MIN_N]
        if row:
            L.append(f"  x {a * CELL:3.0f}-{(a + 1) * CELL:3.0f} y {b * CELL:3.0f}-{(b + 1) * CELL:3.0f}: " + ", ".join(row))
L += ["", "JUMP at each boundary where the primary changes (same instant, two cameras; median / p90 mm, n pairs):"]
jumps = {}
for (A, B), cells in sorted(bnd.items()):
    TA, PA = tr[A]; TB, PB = tr[B]
    pb = interp(TB, PB, TA); ok = np.isfinite(pb).all(1)
    mid = (PA[ok] + pb[ok]) / 2; ix, iy = cell(mid)
    m = np.array([(i, j) in cells for i, j in zip(ix, iy)], bool)
    d = np.hypot(*(PA[ok][m] - pb[ok][m]).T)
    jumps[f"{A}|{B}"] = dict(n=int(len(d)), median=float(np.median(d)) if len(d) else None, p90=float(np.percentile(d, 90)) if len(d) else None,
                             cells=sorted(cells))
    L.append(f"  {A} | {B}: " + (f"median {np.median(d):4.0f} mm, p90 {np.percentile(d, 90):4.0f}, n {len(d)}" if len(d) >= 20 else
                                   f"NOT MEASURED (n {len(d)} ball pairs on that boundary)") + f"; boundary cells {len(cells)}")
(OUT / "HANDOFF_MAP.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / "handoff_map.json").write_text(json.dumps(dict(cell_in=CELL, primary=prim.tolist(), jumps=jumps), indent=1), encoding="utf-8")
print("\n".join(L))
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    col = dict(zip(CAMS, ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#9c755f"]))
    fig, ax = plt.subplots(figsize=(13, 7))
    for b in range(NY):
        for a in range(NX):
            c = prim[b, a]
            ax.add_patch(plt.Rectangle((a * CELL, b * CELL), CELL, CELL, fc=col.get(c, "#eee"), ec="white", alpha=0.75))
            ax.text((a + 0.5) * CELL, (b + 0.5) * CELL, f"{c[2:] if c else ''}\n{why.get((a, b), '')}", ha="center", va="center", fontsize=8)
    for c in CAMS:
        p = cams[c].centre / IN; ax.plot(p[0], p[1], "k^", ms=9); ax.text(p[0] + 4, p[1] + 4, c, fontsize=9)
    for k, v in jumps.items():
        if v["median"] is not None and v["n"] >= 20:
            cc = np.mean([[(i + 0.5) * CELL, (j + 0.5) * CELL] for i, j in v["cells"]], 0)
            ax.text(cc[0], cc[1] - 8, f"{k}: {v['median']:.0f} mm", fontsize=8, ha="center", color="k",
                    bbox=dict(fc="white", ec="none", alpha=0.8))
    ax.set_xlim(-10, 490); ax.set_ylim(-10, 250); ax.set_aspect("equal"); ax.set_xlabel("x (in)"); ax.set_ylabel("y (in)")
    ax.set_title("primary camera per cell (number = its error vs the other cameras, mm) and the jump at each handoff")
    fig.tight_layout(); fig.savefig(OUT / "handoff_map.png", dpi=110)
except Exception as e:                                                   # the text report is the result
    print("plot skipped:", e)
print("->", OUT / "HANDOFF_MAP.txt")
