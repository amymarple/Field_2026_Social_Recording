# -*- coding: utf-8 -*-
r"""Placement-level outer validation of the whole pipeline (audit 2026-09-24, finding 2).

The physical placements were split into 5 folds (E:\calibration\qc\cv\folds.json). For each fold
the bundle was refitted with every camera's view of the fold's placements held out
(fit_cameras.py with FIT_EXCLUDE -> cv\fold<i>\camera_fit.npz). Here, per fold:
  1. the ground warp is fitted on the fold's fit (labels only, no boards) for pano degrees 2, 3, 4,
     and the degree is chosen on the TRAINING placements' cross-camera agreement (inner selection);
  2. the HELD-OUT placements are mapped through that fold's fit + warp, and their cross-camera
     disagreement and plate-corner-to-cone offset are recorded.
Every placement is therefore scored by a calibration that never saw it. Numbers here are the
honest expectation for a new plate put down anywhere the cameras were calibrated.

Usage: python cv_folds_eval.py
Output: E:\calibration\qc\cv\CV_FOLDS.txt
"""
import sys, json, itertools
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_data as fd, paddock_map as pm, frame_correction as fc, board_detect as bd   # noqa: E402

import qc_paths  # noqa: E402
ROOT = qc_paths.QC_ROOT / "cv"
folds = json.loads((ROOT / "folds.json").read_text(encoding="utf-8"))
P_all = [p for p in fd.all_placements() if not p["bad"] and not p["weak"]]
L = []


def say(s=""):
    print(s, flush=True); L.append(s)


def agreement(cams, plc, dropped):
    """per shared corner: max pairwise distance (mm) between the cameras' ground positions; per
    placement: the median over its corners, and the plate-corner-to-cone offset from each camera."""
    shared = {}
    for p in plc:
        if (p["cam"], p["session"], p["station"], p["win"]) in dropped or p["cam"] not in cams:
            continue
        xy = cams[p["cam"]].to_paddock(p["px"], z_mm=6.0)
        for i, c in zip(p["ids"], xy):
            if np.isfinite(c).all():
                shared.setdefault(((p["session"], p["station"], p["win"]), int(i)), {})[p["cam"]] = c
    per_corner, per_place = [], {}
    for (key, cid), d in shared.items():
        if len(d) < 2:
            continue
        v = max(np.linalg.norm(d[a] - d[b]) for a, b in itertools.combinations(sorted(d), 2))
        per_corner.append(v); per_place.setdefault(key, []).append(v)
    return np.array(per_corner), {k: float(np.median(v)) for k, v in per_place.items()}


def cone_offsets(cams, plc, dropped):
    """each camera's own reading of the plate corner nearest the station, vs the design (mm)."""
    out = []
    for p in plc:
        if (p["cam"], p["session"], p["station"], p["win"]) in dropped or p["cam"] not in cams:
            continue
        xy = cams[p["cam"]].to_paddock(p["px"], z_mm=6.0); ok = np.isfinite(xy).all(1)
        if ok.sum() < 8:
            continue
        obj = p["obj_mm"][ok]; q = xy[ok]
        mo, mq = obj.mean(0), q.mean(0); A, B = obj - mo, q - mq
        U, S, Vt = np.linalg.svd(A.T @ B); R = Vt.T @ U.T; s = S.sum() / (A ** 2).sum()
        plate = s * (bd.PAPER_MM @ R.T) + (mq - s * R @ mo)
        out.append(float(np.min(np.linalg.norm(plate - p["station_mm"], axis=1))))
    return np.array(out)


say("=" * 96)
say("PLACEMENT-LEVEL CROSS-VALIDATION OF THE WHOLE PIPELINE (5 folds, inner warp-degree selection)")
say("=" * 96)
held_corner, held_place, held_cone, chosen = [], {}, [], []
train_place = []
for i in sorted(folds, key=int):
    fit = ROOT / f"fold{i}" / "camera_fit.npz"
    if not fit.exists():
        say(f"  fold {i}: no fit"); continue
    keys = {tuple(k.split("|")) for k in folds[i]}
    z = np.load(fit, allow_pickle=False)
    dropped = {tuple(s.split("|")[:4]) for s in z["dropped_views"]}
    test = [p for p in P_all if (p["session"], p["station"], p["win"]) in keys]
    train = [p for p in P_all if (p["session"], p["station"], p["win"]) not in keys]
    best = None
    for deg in (2, 3, 4):
        corr = fc.fit_warps(fit, 8.0, deg, verbose=False)
        (fit.parent / "frame_correction.json").write_text(json.dumps(corr), encoding="utf-8")
        cams = pm.load(fit)
        tr_c, tr_p = agreement(cams, train, dropped)
        score = np.median(tr_c)
        if best is None or score < best[0]:
            best = (score, deg, cams)
    score, deg, cams = best
    te_c, te_p = agreement(cams, test, dropped)
    co = cone_offsets(cams, test, dropped)
    held_corner += list(te_c); held_place.update(te_p); held_cone += list(co); chosen.append(deg)
    train_place += list(tr_p.values())
    say(f"  fold {i}: {len(keys):2d} placements held out; inner choice pano degree {deg} (training median {score:.0f} mm); "
        f"held-out corners median {np.median(te_c) if len(te_c) else float('nan'):.0f} mm, p90 {np.percentile(te_c, 90) if len(te_c) else float('nan'):.0f}, "
        f"n={len(te_c)}; held-out plate-corner-to-cone median {np.median(co) if len(co) else float('nan'):.0f} mm")
hc = np.array(held_corner); hp = np.array(list(held_place.values())); co = np.array(held_cone)
say("")
say(f"HELD-OUT, all folds pooled: {len(hp)} placements, {len(hc)} shared corners")
say(f"  cross-camera disagreement per corner: median {np.median(hc):.0f} mm, p90 {np.percentile(hc, 90):.0f}, max {hc.max():.0f}")
say(f"  per placement (median over its corners): median {np.median(hp):.0f} mm, p90 {np.percentile(hp, 90):.0f}, max {hp.max():.0f};"
    f" {int((hp <= 50).sum())}/{len(hp)} within 50 mm, {int((hp <= 100).sum())}/{len(hp)} within 100 mm")
say(f"  plate corner to its cone (each camera's own reading): median {np.median(co):.0f} mm, p90 {np.percentile(co, 90):.0f}")
say(f"  pano warp degree chosen per fold: {chosen}")
say(f"  for comparison, TRAINING placements of the same folds: per-placement median {np.median(train_place):.0f} mm")
say("")
say("  worst held-out placements:")
for k, v in sorted(held_place.items(), key=lambda kv: -kv[1])[:8]:
    say(f"    {k[1]:5s} {k[0]}  {v:5.0f} mm")
(ROOT / "CV_FOLDS.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("->", ROOT / "CV_FOLDS.txt")
