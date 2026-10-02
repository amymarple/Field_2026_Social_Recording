# -*- coding: utf-8 -*-
# B2 gate: is the panos' bundle residual a coherent field over the canvas? Leave-one-board-out: a smooth (du, dv)(u, v)
# fitted on the other boards' corner residuals predicts the held-out board's; compare held-out |residual| before/after.
import sys, collections
sys.path.insert(0, r"G:\Field_2026_Social_Recording\calibration_qc")
import numpy as np
from scipy.interpolate import RBFInterpolator
import fit_data as fd, fit_models as fm, paddock_map as pm

z = np.load(pm.FIT, allow_pickle=False)
cams = pm.load(correct=False)
keys = {str(k): i for i, k in enumerate(z["board_keys"])}
bp = z["board_pose"]
boards = collections.defaultdict(list)                     # cam -> [(key, px (n,2), e (n,2))]
for p in fd.all_placements():
    key = f"{p['session']}|{p['station']}|{p['win']}"
    if key not in keys or p["weak"] or p["bad"]:
        continue
    X = fm.board_points(bp[keys[key]], p["obj_mm"])
    c = cams[p["cam"]]
    uv = fm.project(c.model, c.intr, X @ c.R.T + c.tvec)
    boards[p["cam"]].append((key, np.asarray(p["px"], float), uv - np.asarray(p["px"], float)))

W, H = 7680.0, 2160.0
def feat(P):                                               # normalised canvas coordinates (upright px)
    return np.c_[P[:, 0] / W, P[:, 1] / H * (H / W)]

for cam in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06"):
    B = boards[cam]
    if not B:
        continue
    print(f"{cam}: {len(B)} boards, {sum(len(b[1]) for b in B)} corners; |residual| median {np.median(np.hypot(*np.concatenate([b[2] for b in B]).T)):.2f} px")
    for smooth in (1e-4, 1e-3, 1e-2):
        before, after, bmean, amean = [], [], [], []
        for i, (k, P, E) in enumerate(B):
            # training: the other boards' corners, thinned to <= 30 per board (corners within a board are correlated)
            tr = [(Pj[:: max(1, len(Pj) // 30)], Ej[:: max(1, len(Pj) // 30)]) for j, (kj, Pj, Ej) in enumerate(B) if j != i]
            Ptr = np.concatenate([t[0] for t in tr]); Etr = np.concatenate([t[1] for t in tr])
            f = RBFInterpolator(feat(Ptr), Etr, kernel="thin_plate_spline", smoothing=smooth * len(Ptr), degree=1)
            Ec = E - f(feat(P))                            # residual left after the correction
            before.append(np.median(np.hypot(*E.T))); after.append(np.median(np.hypot(*Ec.T)))
            bmean.append(np.hypot(*E.mean(0))); amean.append(np.hypot(*Ec.mean(0)))
        print(f"   smoothing {smooth:g}: held-out board |residual| median {np.median(before):.2f} -> {np.median(after):.2f} px "
              f"(p90 {np.percentile(before, 90):.2f} -> {np.percentile(after, 90):.2f}); board-mean offset {np.median(bmean):.2f} -> {np.median(amean):.2f} px; "
              f"improved on {np.mean(np.array(after) < np.array(before)) * 100:.0f} % of boards")
