# -*- coding: utf-8 -*-
r"""Whole-pipeline stability of the pixel -> paddock mapping: how far does a point move when the calibration
is rebuilt without a fifth of the board placements?

The five placement folds of cv_folds_eval.py (<calibration root>\qc\cv\fold<i>\camera_fit.npz, each a full
bundle refit with the fold's placements held out, plus its own ground correction) are alternative
calibrations built by the same pipeline from 80 % of the boards. For every camera, a 6-in grid of paddock
points at height Z (a rat's back) is sent to that camera's pixels through the release and back to the paddock
through each fold; the displacement is how much the answer depends on which boards happened to be there.

This is a precision figure for the whole pipeline (bundle + ground correction), which the warp-only ensemble of
downstream_validation.py is not. It is not an accuracy figure: every fold shares the lattice, the labels and
the ground the boards lay on, so a bias common to all of them does not show.

The frame_correction.json saved next to each fold fit was made with pano degree 4 (the setting of the day);
the release uses degree 3. By default the fold corrections are therefore refitted here, in memory, with the
release's own degree and ridge, so the comparison isolates the boards. --as-saved uses the saved files.

Usage: python fold_stability.py [--z 60] [--as-saved]
Output: <calibration root>\qc\cv\FOLD_STABILITY.txt (FOLD_STABILITY_as_saved.txt with --as-saved)
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, frame_correction as fcorr             # noqa: E402

args = sys.argv[1:]
Z = float(args[args.index("--z") + 1]) if "--z" in args else 60.0
AS_SAVED = "--as-saved" in args
CV = qc_paths.QC_ROOT / "cv"
MM = 25.4

rel = pm.load()
names = sorted(rel)
relc = json.loads((Path(pm.FIT).parent / "frame_correction.json").read_text(encoding="utf-8"))
folds = {}
for i in range(5):
    f = CV / f"fold{i}" / "camera_fit.npz"
    if not f.exists():
        continue
    if AS_SAVED:
        folds[i] = pm.load(f)
    else:
        cams = pm.load(f, correct=False)
        corr = fcorr.fit_warps(f, ridge=relc["ridge_in"], deg_pano=relc["deg_pano"], verbose=False)["cameras"]
        for c in cams:
            cams[c].correction = corr.get(c)
        folds[i] = cams
if not folds:
    raise SystemExit(f"no fold fits under {CV}")

gx, gy = np.meshgrid(np.arange(3, 480, 6.0), np.arange(3, 240, 6.0))
G = np.stack([gx.ravel(), gy.ravel()], 1)


def region(p):
    x, y = p
    end, side = (x < 36 or x > 444), (y < 36 or y > 204)
    return "corner" if end and side else "short-wall end" if end else "long-wall edge" if side else "centre"


REG = np.array([region(p) for p in G])
REGIONS = ("centre", "long-wall edge", "short-wall end", "corner")
L = ["WHOLE-PIPELINE STABILITY OF THE MAPPING  (release vs the 5 placement-fold calibrations)",
     "fold ground corrections: " + ("as saved next to each fold fit" if AS_SAVED else
                                    f"refitted with the release settings (pano degree {relc['deg_pano']}, ridge {relc['ridge_in']} in)"),
     f"points at z = {Z:.0f} mm on a 6-in grid, inside each camera's view and the release's verified support; "
     f"folds found: {sorted(folds)}", "",
     "camera   points   fold-vs-release displacement (mm)      worst fold per point (mm)       unsupported",
     "                   median     p90                         median     p90     max          in a fold"]
by_region = {}
for c in names:
    uv = rel[c].to_paddock_inv(G, z_mm=Z, units="in")
    ok = np.isfinite(rel[c].to_paddock(uv, z_mm=Z, units="in")).all(1) & rel[c].sees(G, z_mm=Z, units="in", margin=10)
    D = np.array([np.linalg.norm(fc[c].to_paddock(uv[ok], z_mm=Z, units="in") - G[ok], axis=1) * MM
                  for fc in folds.values()])
    worst = np.nanmax(D, 0)
    L.append(f"  {c}  {ok.sum():6d}   {np.nanmedian(D):7.1f} {np.nanpercentile(D, 90):7.1f}"
             f"                        {np.nanmedian(worst):7.1f} {np.nanpercentile(worst, 90):7.1f} {np.nanmax(worst):7.1f}"
             f"          {np.isnan(D).any(0).mean():5.1%}")
    for r in REGIONS:
        m = REG[ok] == r
        if m.sum():
            by_region[(c, r)] = (np.nanmedian(worst[m]), np.nanpercentile(worst[m], 90))
L += ["", "worst-fold displacement by region, median / p90 (mm); regions: 36 in from the end walls / side walls:"]
for r in REGIONS:
    L.append(f"  {r:15s} " + "  ".join(f"{c} {by_region[(c, r)][0]:4.0f}/{by_region[(c, r)][1]:4.0f}"
                                         for c in names if (c, r) in by_region))
out = CV / ("FOLD_STABILITY_as_saved.txt" if AS_SAVED else "FOLD_STABILITY.txt")
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", out)
