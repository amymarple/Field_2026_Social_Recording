# -*- coding: utf-8 -*-
r"""Above-ground two-camera check with the 2026-09-18 hand-held sweep boards (board_sweep20_instances.py): the only data
where two cameras see the same object 0.14-0.54 m above the ground - a rat's back and head. A CHECK: the boards are in
no ray fit (they are in the sweep candidate's BUNDLE, release_candidate_2026-10-02c_sweepA).

For every instance, every pair of views (the sweep camera CH03 / CH04 and each pano that saw the board at the same
moment, within half a frame) and every corner both decoded:
  * 3-D gap: the two cameras' rays' closest approach (mm); its midpoint gives the corner's height (reference model);
  * 2-D jump: each camera's pixel mapped to the paddock floor plan AT that height (above the local ground where the
    model has a terrain) and the distance between the two (mm) - what a keypoint at that height jumps by when the
    tracking hands it from one camera to the other. Same heights for every model (from the first --model).
Per camera pair and height band; median / p90 over corners (each view counts its corners).
--px (ray models only) adds the score of the trial's sweep_check.py in the corrected rays: the board's pose from the
sweep camera ALONE (its rays, a rigid board), its corners projected into the pano (numeric inverse of the corrected
rays) and compared with the corners the pano decoded - per view the mean offset (px), the shape rms about it, and
the apparent size observed / predicted along u and v (10-02b, raw bundle: 38 / 69 px; size 0.81-0.95 on some pairs).
--blocks odd|even scores only those 10-s blocks (int(t // 10) % 2), i.e. the boards a --sweep-hold fit did not see.
--own-z maps each model's 2-D jump at ITS OWN triangulated heights (fair when the models disagree on how high the board
was; the default, the first model's heights, then penalises the other models for that height difference).

Usage: python sweep_ray_check.py [--model release|warp|<RAYMAP json>@<camera_fit.npz>] ... [--instances <json>] [--blocks odd|even]
                                 [--own-z] [--px] [--out <txt>]
Default: --model release --model warp; instances <qc root>\trial_sweep\instances_v3.json
"""
import sys, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm, board_detect as bd                    # noqa: E402
from scipy.optimize import least_squares                                 # noqa: E402
from scipy.spatial.transform import Rotation as Rot                       # noqa: E402

args = sys.argv[1:]
SPECS = [args[i + 1] for i, a in enumerate(args) if a == "--model"] or ["release", "warp"]
INST = json.loads(Path(args[args.index("--instances") + 1] if "--instances" in args else
                       qc_paths.QC_ROOT / "trial_sweep" / "instances_v3.json").read_text(encoding="utf-8"))["instances"]
BLOCKS = args[args.index("--blocks") + 1] if "--blocks" in args else None
if BLOCKS:
    INST = [i for i in INST if int(i["t"] // 10) % 2 == {"even": 0, "odd": 1}[BLOCKS]]
PX, OWN_Z = "--px" in args, "--own-z" in args
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
OUT = Path(args[args.index("--out") + 1]) if "--out" in args else None
BANDS = [(0, 200), (200, 350), (350, 500), (500, 900)]


def load(spec):
    if spec == "release":
        return pm.load()
    if spec == "warp":
        return pm.load(rays=None)
    rj, fit = spec.split("@") if "@" in spec else (spec, str(pm.FIT))
    return pm.load(Path(fit), rays=rj)


def gap(Ca, da, Cb, db):
    """closest approach of two ray bundles (row-wise): length (mm) and midpoint."""
    w0 = Ca - Cb; a = (da * da).sum(1); b = (da * db).sum(1); c = (db * db).sum(1); d = (da * w0).sum(1); e = (db * w0).sum(1)
    den = a * c - b * b
    s = (b * e - c * d) / den; t = (a * e - b * d) / den
    P, Q = Ca + s[:, None] * da, Cb + t[:, None] * db
    return np.linalg.norm(P - Q, axis=1), (P + Q) / 2


pairs, full = [], []                                                    # (sweep cam, pano, uv_a, uv_b); (view 0, pano view, common ids)
for ins in INST:
    v0 = ins["views"][0]
    ia = {i: p for i, p in zip(v0["ids"], v0["px"])}
    for v in ins["views"][1:]:
        common = [i for i in v["ids"] if i in ia]
        if len(common) >= 4:
            ib = {i: p for i, p in zip(v["ids"], v["px"])}
            pairs.append((v0["cam"], v["cam"], np.array([ia[i] for i in common], float), np.array([ib[i] for i in common], float)))
            full.append((v0, v, np.array(common, int)))


def kabsch(A, B):
    """R, t with B ~ A R^T + t (proper rotation)."""
    am, bm = A.mean(0), B.mean(0); U, _, Vt = np.linalg.svd((A - am).T @ (B - bm))
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]); R = Vt.T @ D @ U.T
    return R, bm - R @ am


def px_score(cams, terr, rows):
    """the sweep camera's own board pose (its corrected rays), projected into the pano: offset, shape, apparent size."""
    out = []
    for (v0, v, common), (a, b, ua, ub, g, M) in zip(full, rows):
        ca, cb = cams[a], cams[b]
        d0 = ca.rays(np.asarray(v0["px"], float)); O0 = OBJ3[np.asarray(v0["ids"], int)]
        R0, t0 = kabsch(OBJ3[common], M)                                 # start: the two-camera triangulation

        def res(x):
            X = O0 @ Rot.from_rotvec(x[:3]).as_matrix().T + x[3:]; w = X - ca.centre
            return (w - (w * d0).sum(1)[:, None] * d0).ravel()
        x = least_squares(res, np.r_[Rot.from_matrix(R0).as_rotvec(), t0], loss="soft_l1", f_scale=5.0).x
        idsb = np.asarray(v["ids"], int); ob = np.asarray(v["px"], float)
        X = OBJ3[idsb] @ Rot.from_rotvec(x[:3]).as_matrix().T + x[3:]
        zl = X[:, 2] - (terr.height(X[:, :2]) if terr is not None else 0.0)
        uv = pm.Camera.to_paddock_inv(cb, X[:, :2], z_mm=float(np.mean(zl)))   # start: the bundle's projection
        for _ in range(12):                                              # Newton on the corrected rays, per-corner height
            f = cb._ground(uv, zl) - X[:, :2]
            fu = cb._ground(uv + [1.0, 0], zl) - X[:, :2] - f; fv = cb._ground(uv + [0, 1.0], zl) - X[:, :2] - f
            det = fu[:, 0] * fv[:, 1] - fu[:, 1] * fv[:, 0]; det = np.where(np.abs(det) < 1e-12, np.nan, det)
            uv = uv - np.stack([(f[:, 0] * fv[:, 1] - f[:, 1] * fv[:, 0]) / det, (fu[:, 0] * f[:, 1] - fu[:, 1] * f[:, 0]) / det], 1)
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(uv).all(1) & (np.hypot(*(cb._ground(uv, zl) - X[:, :2]).T) < 0.5)
        if ok.sum() < 4:
            continue
        pr, o_ = uv[ok], ob[ok]; dd = o_ - pr; mu = dd.mean(0)
        A_, B_ = pr - pr.mean(0), o_ - o_.mean(0); sc = (A_ * B_).sum(0) / np.maximum((A_ * A_).sum(0), 1e-9)
        out.append((a, b, float(np.hypot(*mu)), mu, float(np.sqrt(((dd - mu) ** 2).sum(1).mean())), sc))
    return out
L = [f"SWEEP RAY CHECK  {len(INST)} sweep instances{' (' + BLOCKS + ' 10-s blocks)' if BLOCKS else ''}, {len(pairs)} two-camera views, {sum(len(p[2]) for p in pairs)} shared corners; "
     "3-D gap of the two rays, and the 2-D jump between the two cameras' floor-plan positions at the corner's height", ""]
Z = None
for spec in SPECS:
    cams = load(spec)
    terr = next((c.terrain for c in cams.values() if getattr(c, "terrain", None) is not None), None)
    rows = []
    for a, b, ua, ub in pairs:
        ca, cb = cams[a], cams[b]
        g, M = gap(np.broadcast_to(ca.centre, (len(ua), 3)), ca.rays(ua), np.broadcast_to(cb.centre, (len(ub), 3)), cb.rays(ub))
        rows.append((a, b, ua, ub, g, M))
    if Z is None or OWN_Z:                                               # the heights: the first model's (default) or each its own
        Z = [M[:, 2] for *_, M in rows]; XY = [M[:, :2] for *_, M in rows]
    L.append(f"model {spec}" + (" (terrain: z above the local ground)" if terr is not None else ""))
    allg, allj = [], []
    per = {}
    for (a, b, ua, ub, g, M), z, xy in zip(rows, Z, XY):
        zl = z - (terr.height(xy) if terr is not None else 0.0)
        pa, pb = cams[a].to_paddock(ua, zl), cams[b].to_paddock(ub, zl)
        j = np.hypot(*(pa - pb).T); ok = np.isfinite(j) & np.isfinite(g)
        per.setdefault((a, b), []).append((g[ok], j[ok], z[ok]))
        allg.append(g[ok]); allj.append(j[ok])
    allg, allj = np.concatenate(allg), np.concatenate(allj)
    L.append(f"  all: 3-D gap {np.median(allg):.0f} / {np.percentile(allg, 90):.0f} mm, 2-D jump {np.median(allj):.0f} / {np.percentile(allj, 90):.0f} mm (n {len(allj)})")
    for (a, b), v in sorted(per.items()):
        g = np.concatenate([x[0] for x in v]); j = np.concatenate([x[1] for x in v]); z = np.concatenate([x[2] for x in v])
        bands = "; ".join(f"z {lo}-{hi}: {np.median(j[(z >= lo) & (z < hi)]):.0f} ({((z >= lo) & (z < hi)).sum()})"
                          for lo, hi in BANDS if ((z >= lo) & (z < hi)).sum() >= 20)
        L.append(f"  {a}-{b}: views {len(v):3d}, 3-D gap {np.median(g):3.0f} / {np.percentile(g, 90):3.0f}, 2-D jump {np.median(j):3.0f} / "
                 f"{np.percentile(j, 90):3.0f}; 2-D jump by height (mm): {bands}")
    if PX:
        if not hasattr(next(iter(cams.values())), "_ground"):
            L.append("  (--px: not a ray model, skipped)")
        else:
            S = px_score(cams, terr, rows)
            L.append("  px score (pose from the sweep camera alone -> the pano): pair, views, |mean offset| median / p90 px, mean (du, dv), "
                     "shape rms, size obs/pred u, v")
            for pa in sorted({(r[0], r[1]) for r in S}):
                g_ = [r for r in S if (r[0], r[1]) == pa]; n_ = np.array([r[2] for r in g_]); mu_ = np.mean([r[3] for r in g_], 0)
                L.append(f"    {pa[0]}->{pa[1]}: {len(g_):3d}  {np.median(n_):5.1f} / {np.percentile(n_, 90):5.1f}  ({mu_[0]:+5.1f}, {mu_[1]:+5.1f})  "
                         f"{np.median([r[4] for r in g_]):5.1f}   {np.median([r[5][0] for r in g_]):.3f}, {np.median([r[5][1] for r in g_]):.3f}")
            n_ = np.array([r[2] for r in S]); L.append(f"    all: {len(S)} views, {np.median(n_):.1f} / {np.percentile(n_, 90):.1f} px")
    L.append("")
zz = np.concatenate(Z)
L.append(f"corner heights (first model): median {np.median(zz):.0f} mm, p10-p90 {np.percentile(zz, 10):.0f}-{np.percentile(zz, 90):.0f}")
if OUT:
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
