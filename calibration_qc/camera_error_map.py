# -*- coding: utf-8 -*-
r"""Each camera's OWN error per region, and a map with one primary camera per region (operator, 2026-10-03: in the
south-west corner the tracking would use CH03, not CH02 - so the map should show the primary camera's own error, not
its disagreement with the others). A CHECK on the reviewed 20 Hz ball (z 105 mm above the local ground with the
release's terrain), the same tracks, clocks and exclusions as handoff_map.py.

Two cameras on the same ball disagree by d_ab; with independent errors, d_ab^2 ~ e_a^2 + e_b^2 (e = a camera's own
error at that place). Per 40 in cell and camera pair the median |d_ab| is taken; the unknowns v_c = e_c^2 per camera and
cell solve those equations (weight sqrt(n)) together with a smoothness prior between neighbouring cells of the same
camera (cells seen by only two cameras cannot split their disagreement alone - the split comes from the neighbours
and from the cells three cameras share) - non-negative least squares on v. The primary camera of a cell is the one
with the smallest own error there (among cameras with ball data in the cell; resolution where none). What it cannot
see: an error all cameras share (a scale, a shift of the whole frame) - those are not in any disagreement.

Usage: python camera_error_map.py [--rays release|<json>|warp] [--cell 40] [--smooth 0.5] [--out <dir>]
Output: <out>\CAMERA_ERROR_MAP.txt, camera_error_map.png, camera_error_map.json  (default <qc root>\camera_error)
"""
import sys, json, itertools, collections
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm                                        # noqa: E402  (cv2 first via paddock_map)
from scipy.optimize import lsq_linear                                    # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RAYS = opt("--rays", "release")
cams = pm.load(rays=None if RAYS == "warp" else RAYS)
TRACK = qc_paths.QC_ROOT / "2026-09-30" / "ball" / "track20"
OUT = Path(opt("--out", str(qc_paths.QC_ROOT / "camera_error"))); OUT.mkdir(parents=True, exist_ok=True)
DRIFT = json.loads((HERE / "session_2026-09-30_drift_final.json").read_text(encoding="utf-8"))["cameras"]
CELL, Z, IN, GAP, MIN_N, LAM = float(opt("--cell", "40")), 105.0, 25.4, 0.25, 10, float(opt("--smooth", "0.5"))
RIDGE, FLOOR = float(opt("--ridge", "0.5")), float(opt("--floor", "10"))     # pull toward the camera's level; 10 mm floor
CAMS = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
H = json.loads((TRACK / "held20.json").read_text(encoding="utf-8"))
F = json.loads((TRACK / "ball20_flags.json").read_text(encoding="utf-8")) if (TRACK / "ball20_flags.json").exists() else {"flags": []}
off, held = H["offsets_s"], [(h["t0"], h["t1"]) for h in H["intervals"]]
wrong = {(f["cam"], f["entry"]) for f in F["flags"] if f.get("flag") == "wrong"}


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = DRIFT.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        A = np.asarray(d["affine_30_to_18"], float); return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


def track(cam):
    fr = json.loads((TRACK / f"ball20_{cam}.json").read_text(encoding="utf-8"))["frames"]
    i = np.arange(len(fr)); a, b = np.polyfit(i, [f[0] for f in fr], 1)
    sel = np.array([k for k, f in enumerate(fr) if f[3]])
    c = cams[cam]; uv = to_0918(cam, [[fr[k][3]["cx"], fr[k][3]["cy"]] for k in sel])
    if getattr(c, "terrain", None) is not None:
        xy = c._ground(uv, Z)
    else:
        d = c.rays(uv); s = (Z - c.centre[2]) / d[:, 2]
        xy = pm.fit_to_physical((c.centre + s[:, None] * d)[:, :2], c.correction); xy[~(s > 0)] = np.nan
    t = (a * i + b)[sel] - off[cam]; k = np.isfinite(xy).all(1)
    for t0, t1 in held:
        k &= ~((t >= t0) & (t <= t1))
    k &= np.array([(cam, int(e)) not in wrong for e in sel])
    o = np.argsort(t[k]); return t[k][o], xy[k][o]


def interp(T, P, t):
    j = np.searchsorted(T, t); ok = (j > 0) & (j < len(T)); j = np.clip(j, 1, len(T) - 1)
    t0, t1 = T[j - 1], T[j]; ok &= (t1 - t0) <= GAP
    w = np.where(t1 > t0, (t - t0) / np.maximum(t1 - t0, 1e-9), 0.0)
    out = P[j - 1] + w[:, None] * (P[j] - P[j - 1]); out[~ok] = np.nan; return out


tr = {c: track(c) for c in CAMS}
NX, NY = int(np.ceil(480 / CELL)), int(np.ceil(240 / CELL))
pairs = {}                                                               # (a, b, i, j) -> (median |d|, n)
seen = collections.defaultdict(int)                                      # (cam, i, j) -> ball samples
for c, (T, P) in tr.items():
    ii, jj = np.clip((P[:, 0] / IN // CELL).astype(int), 0, NX - 1), np.clip((P[:, 1] / IN // CELL).astype(int), 0, NY - 1)
    for i, j in zip(ii, jj):
        seen[(c, i, j)] += 1
for a, b in itertools.combinations(CAMS, 2):
    Ta, Pa = tr[a]; pb = interp(tr[b][0], tr[b][1], Ta); ok = np.isfinite(pb).all(1)
    mid = (Pa[ok] + pb[ok]) / 2 / IN; d = np.hypot(*(Pa[ok] - pb[ok]).T)
    ii, jj = np.clip((mid[:, 0] // CELL).astype(int), 0, NX - 1), np.clip((mid[:, 1] // CELL).astype(int), 0, NY - 1)
    for i in range(NX):
        for j in range(NY):
            m = (ii == i) & (jj == j)
            if m.sum() >= MIN_N:
                pairs[(a, b, i, j)] = (float(np.median(d[m])), int(m.sum()))
# Pairwise disagreements alone cannot say which of TWO cameras is wrong. So: the primary camera of a cell is the one
# with the finest ground resolution (px per cm at 60 mm, as handoff_map.py - CH03 in the south-west corner); where
# three or more cameras saw the ball there, its own error follows exactly from the three pair medians
# ("three-cornered hat": e_P^2 = (d_PA^2 + d_PB^2 - d_AB^2) / 2, best pair of partners); where only two did, only a
# bound: if the primary is the better of the two, e_P <= d / sqrt(2).
cx_, cy_ = (np.arange(NX) + 0.5) * CELL * IN, (np.arange(NY) + 0.5) * CELL * IN
centres = np.array([[cx_[i], cy_[j]] for j in range(NY) for i in range(NX)])
res, cover = {}, {}
for c in CAMS:
    cm = cams[c]
    u0 = cm.to_paddock_inv(centres, z_mm=60.0); ux = cm.to_paddock_inv(centres + [10, 0], z_mm=60.0); uy = cm.to_paddock_inv(centres + [0, 10], z_mm=60.0)
    res[c] = np.minimum(np.hypot(*(ux - u0).T), np.hypot(*(uy - u0).T))
    cover[c] = cm.sees(centres, z_mm=60.0) & np.isfinite(cm.to_paddock(u0, z_mm=60.0)).all(1)
def pm_(a, b, i, j):
    return pairs.get((a, b, i, j), pairs.get((b, a, i, j), (None, 0)))[0]
prim = np.full((NY, NX), "", object); pe = np.full((NY, NX), np.nan); kind = np.full((NY, NX), "", object); E = {}
for i in range(NX):
    for j in range(NY):
        k = j * NX + i; cand = [c for c in CAMS if cover[c][k]]
        if not cand:
            continue
        P_ = max(cand, key=lambda c: res[c][k]); prim[j, i] = P_
        others = [c for c in CAMS if c != P_ and pm_(P_, c, i, j) is not None]
        best = None
        for A_, B_ in itertools.combinations(others, 2):
            dab = pm_(A_, B_, i, j)
            if dab is None:
                continue
            e2 = (pm_(P_, A_, i, j) ** 2 + pm_(P_, B_, i, j) ** 2 - dab ** 2) / 2
            e = float(np.sqrt(max(e2, 10.0 ** 2)))
            if best is None or e < best:
                best = e
        if best is not None:
            pe[j, i], kind[j, i] = best, "est"
        elif others:
            pe[j, i], kind[j, i] = min(pm_(P_, c, i, j) for c in others) / np.sqrt(2), "bound"
ncam = collections.Counter()
var = []
L = [f"CAMERA ERROR MAP  cameras: {RAYS}; reviewed 20 Hz ball at {Z:.0f} mm above the ground; cells {CELL:.0f} in; "
     f"{len(pairs)} (pair, cell) medians; primary = finest resolution; its own error by the three-cornered hat (3+ cameras) or <= d / sqrt(2) (2 cameras, primary the better)",
     "", "primary camera and its own error, mm (e = estimate, < = bound), per cell (x along the length, rows from y 240 at the top):"]
for j in reversed(range(NY)):
    L.append(f"  y {j * CELL:3.0f}-{min(240, (j + 1) * CELL):3.0f} " + " ".join((f"{prim[j, i][2:]:>2s}:{'e' if kind[j, i] == 'est' else '<'}{pe[j, i]:3.0f}" if np.isfinite(pe[j, i]) else f"{prim[j, i][2:]:>2s}:  - ") if prim[j, i] else "  ----- " for i in range(NX)))
vals = pe[np.isfinite(pe)]
L += ["", f"primary camera's own error over the cells with ball data: median {np.median(vals):.0f} mm, p90 {np.percentile(vals, 90):.0f}, max {vals.max():.0f}",
      f"cells with an estimate (3+ cameras): {int((kind == 'est').sum())}, with a bound only (2 cameras): {int((kind == 'bound').sum())}, no ball data: {int(((kind == '') & (prim != '')).sum())}"]
(OUT / "CAMERA_ERROR_MAP.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / "camera_error_map.json").write_text(json.dumps(dict(cell_in=CELL, primary=prim.tolist(), primary_err_mm=np.where(np.isfinite(pe), pe, -1).round(0).tolist(),
                                                          kind=kind.tolist()), indent=1), encoding="utf-8")
print("\n".join(L))
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    col = dict(zip(CAMS, ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#9c755f"]))
    fig, ax = plt.subplots(figsize=(13, 7))
    for j in range(NY):
        for i in range(NX):
            c = prim[j, i]
            ax.add_patch(plt.Rectangle((i * CELL, j * CELL), CELL, CELL, fc=col.get(c, "#eee"), ec="white", alpha=0.75))
            if c:
                e = pe[j, i]
                n_p = seen.get((c, i, j), 0); n_o = sum(v for (cc, ii, jj), v in seen.items() if (ii, jj) == (i, j) and cc != c)
                if np.isfinite(e):
                    lab = f"{c[2:]}\n" + ("" if kind[j, i] == "est" else "<= ") + f"{e:.0f} mm"
                elif n_p:                                                # the ball was there; no other camera saw enough of it
                    lab = f"{c[2:]}\nonly {c[2:]}\n({n_p} balls)"
                elif n_o and not n_p:
                    lab = f"{c[2:]}\nmissed by {c[2:]}\n(others {n_o})"
                else:
                    lab = f"{c[2:]}\nno ball"
                ax.text((i + 0.5) * CELL, (j + 0.5) * CELL, lab, ha="center", va="center", fontsize=8.5,
                        fontweight="bold" if np.isfinite(e) and e >= 50 else "normal",
                        color="k" if kind[j, i] == "est" else "#444")
    for c in CAMS:
        p = cams[c].centre / IN; ax.plot(p[0], p[1], "k^", ms=9); ax.text(p[0] + 4, p[1] + 4, c, fontsize=9)
    ax.set_xlim(-10, 490); ax.set_ylim(-10, 250); ax.set_aspect("equal"); ax.set_xlabel("x (in)"); ax.set_ylabel("y (in)")
    ax.set_title("primary camera per cell (finest resolution) and its OWN error on the ball, mm" + chr(10) + "black: 3+ cameras (estimate);  <=: 2 cameras (bound);  only CHxx: one camera saw the ball, nothing to compare", fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "camera_error_map.png", dpi=110)
except Exception as e:                                                   # the text report is the result
    print("plot skipped:", e)
