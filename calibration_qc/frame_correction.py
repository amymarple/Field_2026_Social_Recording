# -*- coding: utf-8 -*-
r"""Tie each camera's ground mapping to the physical lattice, using everything the operator labelled
on the ground: cones (a point at a known station), the seven T-series cords (a straight line at a
known x) and the foot of the wall (a straight line at x = 0 / 480 or y = 0 / 240 on its straight
middle; the rounded corners are left out).

Why: the bundle fixes the cameras' relative geometry to < 0.1 m, but the panos' ray model is off in
the corners of their canvas (the far ends of the paddock seen at the bottom and top of the
picture): pushed onto the ground, the same cord comes out tilted 0 deg in one camera, 6 deg in
another and 11 deg in a third, and the fit's x = 0 line sat on the end wall a hand above its base.
No smooth lens model tried explained it, so the correction is made where it is measured: on the
ground, per camera. Each camera gets a 2-D polynomial warp (x, y)_fit -> (x, y)_lattice fitted to
its own labels; its degree follows how many labels it has (affine for the nadir cameras with a
handful of points, degree 4 for the panos with ~130). The lattice - cones on the cord crossings as
designed, cords straight, walls where they were built - IS the paddock frame by definition, so
after this every camera agrees with it and hence with every other camera. paddock_map applies the
warp on the way out and inverts it on the way in.

The warp is kept gentle: --ridge (default 8) is a prior of that many inches per polynomial term
pulling every coefficient toward zero, so terms the labels do not constrain (a camera's y warp
from nine cones, the panos' corners) stay near the identity; --deg-pano (default 3, the degree the placement folds chose in 4 of 5, cv_folds_eval.py) caps the panos'
degree. The boards, which are NOT used here, are the independent check: paddock_agreement.py
after this must not get worse anywhere.

Usage: python frame_correction.py [--fit <camera_fit.npz>] [--ridge 8] [--deg-pano 3]
       -> <fit dir>\frame_correction.json
"""
import sys, json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm                        # noqa: E402

CONE_Z = 50.0                 # the hole the operator clicks is the top of a ~5 cm disc cone
MM = 25.4


def terms(p, deg):
    """monomials up to degree deg in (x, y) scaled to ~[-1, 1] over the paddock."""
    x, y = (p[:, 0] - 240.0) / 240.0, (p[:, 1] - 120.0) / 120.0
    cols = [np.ones_like(x)]
    for d in range(1, deg + 1):
        for i in range(d + 1):
            cols.append(x ** (d - i) * y ** i)
    return np.stack(cols, 1)


def warp(p, coef, deg):
    T = terms(p, deg)
    return p + np.stack([T @ coef[0], T @ coef[1]], 1)


def collect(cams, hold_out=()):
    """-> {cam: (pts, tgt, kind, group)}: every ground label of every camera in the FIT frame (inches),
    with its target (a station point, or a line x = X / y = Y) and its GROUP name (the cone's cord
    "cones@x=24", the cord "X24", the wall side "WALL_X0"...). Groups in hold_out are left out."""
    S, QC = qc_paths.resolve(None)
    out = {}
    for cam in sorted(cams):
        c = cams[cam]
        pts, tgt, kind, grp = [], [], [], []
        for st, uv in qc_paths.load_cones(QC, cam, S, space="upright").items():
            if st in fd.LATTICE:
                g = c.to_paddock(uv, z_mm=CONE_Z, units="in")
                if np.isfinite(g).all() and np.linalg.norm(g - fd.LATTICE[st]) < 40:
                    pts.append(g); tgt.append(fd.LATTICE[st]); kind.append("p"); grp.append(f"cones@x={fd.LATTICE[st][0]:.0f}")
        lf = QC / f"line_labels_{cam}.json"
        if lf.exists():
            d = json.loads(lf.read_text(encoding="utf-8"))
            uw, uh = qc_paths.upright_size(S, cam); dw, dh = d.get("frame_size_upright", [uw, uh])
            sc = np.array([uw / float(dw), uh / float(dh)])
            for k, v in d["lines"].items():
                g = c.to_paddock(np.asarray(v, float) * sc, z_mm=0.0, units="in")
                g = g[np.isfinite(g).all(1)]
                if k.startswith("X"):
                    x0 = float(k[1:])
                    for q in g:
                        if abs(q[0] - x0) < 40 and -10 < q[1] < 250:
                            pts.append(q); tgt.append((x0, np.nan)); kind.append("x"); grp.append(k)
                elif k in ("WALL_X0", "WALL_X480"):
                    x0 = 0.0 if k.endswith("X0") else 480.0
                    for q in g:
                        if 60 < q[1] < 180 and abs(q[0] - x0) < 40:
                            pts.append(q); tgt.append((x0, np.nan)); kind.append("x"); grp.append(k)
                elif k in ("WALL_Y0", "WALL_Y240"):
                    y0 = 0.0 if k.endswith("Y0") else 240.0
                    for q in g:
                        if 100 < q[0] < 380 and abs(q[1] - y0) < 40:
                            pts.append(q); tgt.append((np.nan, y0)); kind.append("y"); grp.append(k)
        keep = np.array([g not in hold_out for g in grp], bool) if grp else np.zeros(0, bool)
        out[cam] = (np.array(pts)[keep] if len(pts) else np.zeros((0, 2)), np.array(tgt, float)[keep] if len(pts) else np.zeros((0, 2)),
                    np.array(kind)[keep], np.array(grp)[keep])
    return out


def residual_of(w, tgt, kind):
    r = []
    for q, t, k in zip(w, tgt, kind):
        if k == "p":
            r += [q[0] - t[0], q[1] - t[1]]
        elif k == "x":
            r.append(q[0] - t[0])
        else:
            r.append(q[1] - t[1])
    return np.array(r)


def fit_warps(fit_path, ridge=8.0, deg_pano=3, hold_out=(), verbose=True):
    """-> the frame_correction dict for one fit (not written). hold_out: label group names left out
    of the fit (cross-validation); their residual under the fitted warp is returned in
    out["held_out"][cam] as a list of absolute residuals (inches)."""
    fit_path = Path(fit_path)
    cams = pm.load(fit_path, correct=False)
    data = collect(cams)
    import hashlib
    out = {"fit_sha256": hashlib.sha256(fit_path.read_bytes()).hexdigest(),
           "note": "per-camera warp from the bundle's frame to the physical lattice, in INCHES: "
                   "xy_lattice = xy_fit + [T(xy_fit) @ cx, T(xy_fit) @ cy], T = monomials of degree <= deg in "
                   "((x-240)/240, (y-120)/120), order 1, x, y, x^2, xy, y^2, x^3, x^2y, xy^2, y^3 ...",
           "fit": str(fit_path), "ridge_in": ridge, "deg_pano": deg_pano, "held_out_groups": list(hold_out),
           "cameras": {}, "held_out": {}}
    lines = []
    for cam, (pts_all, tgt_all, kind_all, grp_all) in data.items():
        keep = np.array([g not in hold_out for g in grp_all], bool)
        pts, tgt, kind = pts_all[keep], tgt_all[keep], kind_all[keep]
        n = len(pts); npt = int((kind == "p").sum())
        if n < 6:
            lines.append(f"  {cam}: {n} constraints - no warp"); continue
        deg = deg_pano if n >= 90 else 1
        nt = terms(pts[:1], deg).shape[1]

        def resid(x, prior=True):
            r = residual_of(warp(pts, x.reshape(2, nt), deg), tgt, kind)
            return np.concatenate([r, x / ridge]) if prior else r

        x0 = np.zeros(2 * nt)
        before = resid(x0, prior=False)
        r = least_squares(resid, x0, loss="soft_l1", f_scale=3.0)
        after = resid(r.x, prior=False)
        coef = r.x.reshape(2, nt)
        from scipy.spatial import ConvexHull
        hull = pts[ConvexHull(pts).vertices]
        ctr = hull.mean(0); vec = hull - ctr
        hull = ctr + vec * (1 + 12.0 / np.maximum(np.linalg.norm(vec, axis=1), 1e-9))[:, None]
        out["cameras"][cam] = dict(deg=deg, cx=[float(v) for v in coef[0]], cy=[float(v) for v in coef[1]],
                                   support=[[round(float(a), 2), round(float(b), 2)] for a, b in hull],
                                   n_points=npt, n_cord=int((kind == "x").sum()), n_wall_y=int((kind == "y").sum()),
                                   rms_before_in=float(np.sqrt((before ** 2).mean())), rms_after_in=float(np.sqrt((after ** 2).mean())))
        if (~keep).any():
            ho = residual_of(warp(pts_all[~keep], coef, deg), tgt_all[~keep], kind_all[~keep])
            out["held_out"][cam] = [float(abs(v)) for v in ho]
        lines.append(f"  {cam}: {npt} cones, {int((kind == 'x').sum())} cord/end-wall points, {int((kind == 'y').sum())} side-wall points"
                     f" -> degree {deg} warp, residual {np.sqrt((before ** 2).mean()):.1f} -> {np.sqrt((after ** 2).mean()):.1f} in rms"
                     f" (p90 {np.percentile(np.abs(after), 90):.1f} in)")
    if verbose:
        print("\n".join(lines))
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    FIT = Path(args[args.index("--fit") + 1]) if "--fit" in args else pm.FIT
    RIDGE = float(args[args.index("--ridge") + 1]) if "--ridge" in args else 8.0
    DEG_PANO = int(args[args.index("--deg-pano") + 1]) if "--deg-pano" in args else 3
    out = fit_warps(FIT, RIDGE, DEG_PANO)
    out.pop("held_out", None)
    (FIT.parent / "frame_correction.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("->", FIT.parent / "frame_correction.json")
