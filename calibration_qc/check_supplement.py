# -*- coding: utf-8 -*-
r"""Held-out check of the release calibration against the 2026-09-30 cone supplement, and camera stability.

None of these labels was in the release fit, so this is the release scored at new ground points:
  1. CONES - every cone labelled on 2026-09-30 (<qc>\2026-09-30\cone_labels_CHxx.json), mapped through the
     release at z = 50 mm (the top of the cone, where the operator clicks), against where its ID says it
     stands (fit_data.LATTICE for a cone still on its station, fit_data.SUPPLEMENT for the mid-points, corners
     and edge cones). Points outside a camera's verified support are mapped anyway (extrapolated) and listed
     apart. A label whose mapped position is much nearer another candidate position is flagged for the
     operator (column V/F4 was only partly moved).
  2. HANDOFF - the same cone labelled in two cameras: how far apart the two cameras put it (in support).
  3. STABILITY - cones that never moved (labelled on the same station in both sessions): pixel shift of the
     label from 2026-09-18 to 2026-09-30, per camera. A whole camera shifting together means the camera moved;
     one cone alone means that cone was nudged.
  4. CORDS - the new cords Y39 / Y201 (line_labels_CHxx.json) mapped at z = 0: offset from the design y.

Usage: python check_supplement.py --session <dir of session_2026-09-30_...>
Output: <qc>\2026-09-30\SUPPLEMENT_CHECK.txt
"""
import sys, json, itertools
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm                       # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
if not sess:
    raise SystemExit("usage: python check_supplement.py --session <dir of session_2026-09-30_...>")
S30, Q30 = qc_paths.resolve(sess)
S18, Q18 = qc_paths.resolve(None)
MM = 25.4
CONE_Z = 50.0
cams = pm.load()
names = sorted(cams)
POS = {**fd.LATTICE, **fd.SUPPLEMENT}


def to_paddock_any(cam, uv, z):
    """like Camera.to_paddock, but also returns the extrapolated answer outside the verified support."""
    xy, why = cam.to_paddock(np.atleast_2d(uv), z_mm=z, units="in", why=True)
    if why[0] == "outside verified support":
        d = cam.rays(np.atleast_2d(uv))
        s = (z - cam.centre[2]) / d[:, 2]
        X = cam.centre + s[:, None] * d
        xy = pm.fit_to_physical(X[:, :2], cam.correction) / MM
    return xy[0], str(why[0])


L = ["CHECK OF THE RELEASE AGAINST THE 2026-09-30 CONE SUPPLEMENT (held out: none of these labels was in the fit)",
     f"release {pm.FIT}; labels {Q30}", ""]

# ---------------------------------------------------------------- 1. cones vs their positions
rows, per = [], {}
mapped = {}                                         # (cam, id) -> xy in support
for c in names:
    lab = qc_paths.load_cones(Q30, c, S30)
    for st, uv in lab.items():
        if st not in POS:
            rows.append((c, st, None, None, "unknown ID"))
            continue
        xy, why = to_paddock_any(cams[c], uv, CONE_Z)
        if not np.isfinite(xy).all():
            rows.append((c, st, None, None, why))
            continue
        err = float(np.hypot(*(xy - POS[st]))) * MM
        near = min(POS, key=lambda k: np.hypot(*(xy - POS[k])))
        dn = float(np.hypot(*(xy - POS[near]))) * MM
        flag = f"nearer {near} ({dn:.0f} mm)" if near != st and dn < 0.5 * err else ""
        rows.append((c, st, xy, err, why if why != "ok" else flag))
        if why == "ok":
            per.setdefault(c, []).append(err)
            mapped[(c, st)] = xy
L.append("1. CONES: mapped position (z = 50 mm) vs the position of the labelled ID, mm")
L.append("   camera   n in support   median    p90    max     outside support (extrapolated)")
alle = []
for c in names:
    e = np.array(per.get(c, []))
    out = [(st, err) for cc, st, xy, err, why in rows if cc == c and why == "outside verified support"]
    alle += list(e)
    L.append(f"   {c}   {len(e):5d}        " + (f"{np.median(e):6.0f} {np.percentile(e, 90):6.0f} {e.max():6.0f}" if len(e) else "     -      -      -")
             + "     " + (", ".join(f"{st} {err:.0f}" for st, err in out) if out else "-"))
alle = np.array(alle)
L.append(f"   all      {len(alle):5d}        {np.median(alle):6.0f} {np.percentile(alle, 90):6.0f} {alle.max():6.0f}")
L.append("   largest (in support) and flagged:")
big = sorted([r for r in rows if r[3] is not None and r[4] in ("", ) or (r[4] and r[4].startswith("nearer"))],
             key=lambda r: -(r[3] or 0))[:15]
for c, st, xy, err, why in big:
    L.append(f"     {c} {st:5s} at ({xy[0]:6.1f},{xy[1]:6.1f}) in, design ({POS[st][0]},{POS[st][1]}), off {err:4.0f} mm  {why}")
odd = [r for r in rows if r[4] in ("unknown ID",) or r[2] is None]
if odd:
    L.append("   not mapped: " + ", ".join(f"{c} {st} ({why})" for c, st, xy, err, why in odd))

# ---------------------------------------------------------------- 2. the same cone in two cameras
L.append("\n2. HANDOFF: the same cone labelled in two cameras, distance between the two mapped positions, mm")
pairs = {}
ids = {}
for (c, st), xy in mapped.items():
    ids.setdefault(st, {})[c] = xy
for st, d in ids.items():
    for a, b in itertools.combinations(sorted(d), 2):
        pairs.setdefault(f"{a}-{b}", []).append((st, float(np.hypot(*(d[a] - d[b]))) * MM))
allp = []
for p, v in sorted(pairs.items()):
    e = np.array([x for _, x in v]); allp += list(e)
    worst = max(v, key=lambda t: t[1])
    L.append(f"   {p:10s} n {len(e):3d}  median {np.median(e):5.0f}  p90 {np.percentile(e, 90):5.0f}  max {e.max():5.0f} ({worst[0]})")
if allp:
    allp = np.array(allp)
    L.append(f"   all pairs  n {len(allp):3d}  median {np.median(allp):5.0f}  p90 {np.percentile(allp, 90):5.0f}  max {allp.max():5.0f}")

# ---------------------------------------------------------------- 3. stability: unmoved cones, 09-18 vs 09-30
L.append("\n3. STABILITY: cones on the same station in both sessions, label shift 2026-09-18 -> 2026-09-30 (px, upright)")
for c in names:
    a = qc_paths.load_cones(Q18, c, S18)
    b = qc_paths.load_cones(Q30, c, S30)
    both = sorted(st for st in b if st in a and st in fd.LATTICE)
    if not both:
        L.append(f"   {c}: no cone labelled on the same station in both sessions")
        continue
    d = np.array([np.asarray(b[st]) - np.asarray(a[st]) for st in both])
    L.append(f"   {c}: n {len(both)}  mean shift ({d[:, 0].mean():+.1f}, {d[:, 1].mean():+.1f}) px  "
             f"|shift| median {np.median(np.hypot(d[:, 0], d[:, 1])):.1f} px  max {np.hypot(d[:, 0], d[:, 1]).max():.1f} px")
    L.append("        " + "  ".join(f"{st} ({dx:+.0f},{dy:+.0f})" for st, (dx, dy) in zip(both, d)))

# ---------------------------------------------------------------- 4. the new cords
L.append("\n4. CORDS: traced points of the new cords mapped at z = 0, offset from the design y, mm (+ = toward y 240)")
for c in names:
    f = Q30 / f"line_labels_{c}.json"
    if not f.exists():
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    uw, uh = qc_paths.upright_size(S30, c)
    dw, dh = d.get("frame_size_upright", [uw, uh])
    sc = np.array([uw / float(dw), uh / float(dh)])
    for k, v in d["lines"].items():
        if not v or not k.startswith("Y"):
            continue
        g = cams[c].to_paddock(np.asarray(v, float) * sc, z_mm=0.0, units="in")
        g = g[np.isfinite(g).all(1)]
        if not len(g):
            L.append(f"   {c} {k}: all {len(v)} points outside the verified support"); continue
        off = (g[:, 1] - float(k[1:])) * MM
        L.append(f"   {c} {k}: {len(g):2d}/{len(v):2d} pts in support, x {g[:, 0].min():5.0f}..{g[:, 0].max():5.0f} in  "
                 f"offset mean {off.mean():+5.0f}  |offset| median {np.median(np.abs(off)):4.0f}  max {np.abs(off).max():4.0f}")

out = Q30 / "SUPPLEMENT_CHECK.txt"
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", out)
