# -*- coding: utf-8 -*-
r"""Leave-one-group-out validation of the ground warp.

The warp is fitted from the operator's ground labels (cones, cords, wall middles). Here each label
GROUP - one cord (X24 ... X456, all its clicks in all cameras), one wall side, or the cones on one
cord - is held out in turn, the warp is refitted from the rest, and the held-out group's residual
under that warp is what the correction does where it was NOT fitted. This is the generalisation
the training residual in frame_correction.json cannot show.

Usage: python cv_landmarks.py [--fit <camera_fit.npz>] [--ridge 8] [--deg-pano 4]
Output: <fit dir>\CV_LANDMARKS.txt
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paddock_map as pm, frame_correction as fc                            # noqa: E402

args = sys.argv[1:]
FIT = Path(args[args.index("--fit") + 1]) if "--fit" in args else pm.FIT
RIDGE = float(args[args.index("--ridge") + 1]) if "--ridge" in args else 8.0
DEG = int(args[args.index("--deg-pano") + 1]) if "--deg-pano" in args else 3
L = []


def say(s=""):
    print(s, flush=True); L.append(s)


cams = pm.load(FIT, correct=False)
data = fc.collect(cams)
groups = sorted({g for cam in data for g in data[cam][3]})
say("=" * 96)
say(f"GROUND WARP, LEAVE-ONE-GROUP-OUT   ({FIT}; ridge {RIDGE} in, pano degree {DEG})")
say("=" * 96)
say("")
say("Each group is held out of the warp fit; its residual under the warp fitted on the rest (in):")
say(f"  {'group':14s} " + " ".join(f"{c:>15s}" for c in sorted(cams)) + "     (n points: median / p90)")
held = {c: [] for c in cams}
train = {c: [] for c in cams}
for g in groups:
    out = fc.fit_warps(FIT, RIDGE, DEG, hold_out=(g,), verbose=False)
    row = f"  {g:14s} "
    for c in sorted(cams):
        v = out["held_out"].get(c)
        if v:
            held[c] += v
            row += f" {len(v):3d}: {np.median(v):4.1f} / {np.percentile(v, 90):4.1f}"
        else:
            row += " " * 15
    say(row)
say("")
say("pooled held-out residual per camera (every label, each predicted by a warp that never saw its group):")
full = fc.fit_warps(FIT, RIDGE, DEG, verbose=False)
for c in sorted(cams):
    v = np.array(held[c])
    if len(v):
        say(f"  {c}: n={len(v):3d}  median {np.median(v):4.1f} in  p90 {np.percentile(v, 90):4.1f}  max {v.max():4.1f}"
            f"    (training residual of the full warp: rms {full['cameras'][c]['rms_after_in']:.1f} in, "
            f"raw fit frame: rms {full['cameras'][c]['rms_before_in']:.1f} in)")
allv = np.concatenate([np.array(held[c]) for c in cams if held[c]])
say("")
say(f"  all cameras: n={len(allv)}  held-out median {np.median(allv):.1f} in ({25.4*np.median(allv):.0f} mm), "
    f"p90 {np.percentile(allv, 90):.1f} in ({25.4*np.percentile(allv, 90):.0f} mm), max {allv.max():.1f} in")
(FIT.parent / "CV_LANDMARKS.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("->", FIT.parent / "CV_LANDMARKS.txt")
