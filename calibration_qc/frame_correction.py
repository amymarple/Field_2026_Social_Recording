# -*- coding: utf-8 -*-
r"""Tie the fitted paddock frame to the physical cords, using the operator's cone labels from every
camera.

The bundle fixes the cameras' RELATIVE geometry well (cross-camera median < 0.1 m) but its
absolute frame is compressed along the long axis: the panos read far boards a little too close
and CH03/CH04 follow them, so the x = 24 in cord lands at x ~ 40 in and the x = 456 in cord at
~448 in, and the fit's x = 0 line sits on the end wall a hand above its base (CH03/CH04 frames
with the lines drawn, 2026-09-23). The cones sit on the cord crossings, so their labels in all six
cameras measure this directly: push each label through its camera onto the ground (cone-top
height), compare with the design station, and fit a smooth offset dx(x) (cubic) and dy(y) (linear)
to the cord medians. paddock_map applies the correction on the way out and inverts it on the way
in. It is an empirical correction of the FRAME, not of any camera; the cross-camera numbers are
unchanged by it, and the wall (never used here) is the independent check.

Usage: python frame_correction.py [--fit <camera_fit.npz>]   -> <fit dir>\frame_correction.json
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm                        # noqa: E402

args = sys.argv[1:]
FIT = Path(args[args.index("--fit") + 1]) if "--fit" in args else pm.FIT
CONE_Z = 50.0
MM = 25.4

cams = pm.load(FIT, correct=False)
S, QC = qc_paths.resolve(None)
by_x, by_y, rows = {}, {}, []
for c in cams:
    for st, uv in qc_paths.load_cones(QC, c, S, space="upright").items():
        if st not in fd.LATTICE:
            continue
        g = cams[c].to_paddock(uv, z_mm=CONE_Z, units="in")
        d = g - np.array(fd.LATTICE[st], float)
        if not np.isfinite(d).all() or np.linalg.norm(d) > 40:      # a wrong label, not a frame error
            continue
        x0, y0 = fd.LATTICE[st]
        by_x.setdefault(x0, []).append(d[0]); by_y.setdefault(y0, []).append(d[1])
        rows.append((c, st, x0, y0, d[0], d[1]))

xs = np.array(sorted(by_x)); mx = np.array([np.median(by_x[x]) for x in xs]); nx = np.array([len(by_x[x]) for x in xs])
ys = np.array(sorted(by_y)); my = np.array([np.median(by_y[y]) for y in ys])
# offsets are in the FIT frame (where the cone was read); the correction maps fit -> physical
px = np.polyfit(xs + mx, mx, 3, w=np.sqrt(nx))          # dx as a function of fit-frame x
py = np.polyfit(ys + my, my, 1)
resx = mx - np.polyval(px, xs + mx)
print(f"{len(rows)} cone labels from {len(cams)} cameras")
print("cord      design x   read at   offset   after correction")
for x0, m, n, r in zip(xs, mx, nx, resx):
    print(f"  x cord   {x0:6.0f}   {x0 + m:7.1f}   {m:+6.1f}    {r:+5.1f} in   (n={n})")
for y0, m in zip(ys, my):
    print(f"  y cord   {y0:6.0f}   {y0 + m:7.1f}   {m:+6.1f}    {m - np.polyval(py, y0 + m):+5.1f} in")
print(f"\n  x correction at fit x = 0 / 240 / 480 in: {np.polyval(px, 0):+.1f} / {np.polyval(px, 240):+.1f} / {np.polyval(px, 480):+.1f} in")
out = dict(note="paddock_fit_to_physical: x_phys = x_fit - polyval(dx_coef, x_fit); y_phys = y_fit - polyval(dy_coef, y_fit); inches",
           fit=str(FIT), dx_coef=[float(v) for v in px], dy_coef=[float(v) for v in py],
           cords_x=[dict(design=float(x0), read=float(x0 + m), n=int(n)) for x0, m, n in zip(xs, mx, nx)],
           cords_y=[dict(design=float(y0), read=float(y0 + m)) for y0, m in zip(ys, my)],
           residual_in=dict(x_rms=float(np.sqrt((resx ** 2).mean())), n_labels=len(rows)))
(FIT.parent / "frame_correction.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("->", FIT.parent / "frame_correction.json")
