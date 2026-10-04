# -*- coding: utf-8 -*-
r"""Above-ground check of a bundle with the 2026-09-18 hand-held sweep boards (board_sweep20_instances.py).

For every instance the sweep camera's own corners give the board's pose (planar PnP in a virtual pinhole along the
mean ray, the bundle's lens and camera pose); the 88 corners of that pose are projected into each pano that saw the
board at the same moment and compared with the corners it decoded. This is the displacement the operator saw in the
failure videos (the predicted outline beside the board): per view its mean offset (du, dv), its rms about that
mean (the shape), in upright pano pixels, and the board's apparent size observed / predicted along u and v (a range
or canvas-scale error shows there). A bundle fitted with FIT_SWEEP lists the instances it used (sweep_keys);
the others are held out and reported apart. No ground warp is involved: the boards are in the air.

Usage: python sweep_check.py --fit <camera_fit.npz> [--fit <another> ...] [--instances <instances.json>] [--out <file.txt>]
"""
import sys, json
from pathlib import Path
import numpy as np, cv2
from scipy.spatial.transform import Rotation as Rot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, board_detect as bd                    # noqa: E402

args = sys.argv[1:]
FITS = [Path(args[i + 1]) for i, a in enumerate(args) if a == "--fit"] or [pm.FIT]
OUT = Path(args[args.index("--out") + 1]) if "--out" in args else None
INST_FILE = Path(args[args.index("--instances") + 1]) if "--instances" in args else qc_paths.QC_ROOT / "sweep20" / "instances.json"
INST = json.loads(INST_FILE.read_text(encoding="utf-8"))["instances"]
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
L = []


def say(s=""):
    print(s, flush=True); L.append(s)


def board_pose(c, ids, px):
    b = pm.fm.bearings(c.model, c.intr, px); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = OBJ3[ids].astype(np.float64)
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    Rc = Q.T @ cv2.Rodrigues(rv)[0]; Xc = Q.T @ tv.ravel()
    return c.R.T @ Rc, c.R.T @ (Xc - c.tvec)


def check(fit):
    cams = pm.load(fit, correct=False)
    z = np.load(fit, allow_pickle=False)
    used = set(z["sweep_keys"].tolist()) if "sweep_keys" in z.files else set()
    rows = []
    for ins in INST:
        mv = ins["views"][0]; c0 = cams[mv["cam"]]
        R, X = board_pose(c0, np.asarray(mv["ids"], int), np.asarray(mv["px"], float))
        for v in ins["views"][1:]:
            c = cams[v["cam"]]; ids = np.asarray(v["ids"], int)
            pr = pm.fm.project(c.model, c.intr, (OBJ3[ids] @ R.T + X) @ c.R.T + c.tvec)
            ob = np.asarray(v["px"], float)
            d = ob - pr                                               # observed - predicted
            mu = d.mean(0)
            a, b = pr - pr.mean(0), ob - ob.mean(0)                   # apparent size, observed / predicted, per axis
            sc = (a * b).sum(0) / np.maximum((a * a).sum(0), 1e-9)
            rows.append((ins["window"], v["cam"], ins["key"] in used, mu[0], mu[1],
                         float(np.sqrt(((d - mu) ** 2).sum(1).mean())), X[2], sc[0], sc[1]))
    return rows


def table(rows, tag):
    say(f"  {tag}")
    say(f"    {'sweep -> pano':14s} {'views':>5s} {'|offset| med':>12s} {'p90':>6s} {'mean (du, dv) px':>18s} {'shape rms':>9s}"
        f" {'size obs/pred u, v':>19s}")
    for w in ("CH03", "CH04"):
        for cam in ("CH01", "CH02"):
            g = [r for r in rows if r[0] == w and r[1] == cam]
            if not g:
                continue
            du = np.array([r[3] for r in g]); dv = np.array([r[4] for r in g]); n = np.hypot(du, dv)
            say(f"    {w} -> {cam:6s} {len(g):5d} {np.median(n):12.1f} {np.percentile(n, 90):6.1f} "
                f"   ({du.mean():+6.1f}, {dv.mean():+6.1f}) {np.median([r[5] for r in g]):9.2f}"
                f"      {np.median([r[7] for r in g]):.3f}, {np.median([r[8] for r in g]):.3f}")
    n = np.array([np.hypot(r[3], r[4]) for r in rows])
    if len(n):
        say(f"    all            {len(n):5d} {np.median(n):12.1f} {np.percentile(n, 90):6.1f}")


say("SWEEP CHECK - the sweep camera's board pose projected into the panos (observed - predicted, upright px)")
say(f"  {len(INST)} instances from {INST_FILE}")
for fit in FITS:
    rows = check(fit)
    say("")
    say(f"{fit}")
    ins = [r for r in rows if r[2]]; out = [r for r in rows if not r[2]]
    if ins and out:
        table(ins, "instances IN this fit")
        table(out, "instances HELD OUT of this fit")
    else:
        table(rows, "all instances" + (" (all in this fit)" if ins else " (none in this fit)"))
if OUT:
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
