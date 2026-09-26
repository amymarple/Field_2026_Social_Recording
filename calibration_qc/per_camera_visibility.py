# -*- coding: utf-8 -*-
"""Per-camera station visibility: for CH01 and CH02 separately, the best corner count seen at
each designed station (events mapped through the refined pano maps, sweep windows excluded).
Answers 'does each camera have >=12 usable test/validation positions' for camera_ground."""
import csv
from pathlib import Path
from datetime import datetime, time as dtime
import numpy as np

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
QC = qc_paths.QC_ROOT
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
OFF = np.array([14.2, 10.6])
stations = {}
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1):
        stations[f"T{li}{si}"] = np.array([x, y], float) + OFF
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1):
        stations[f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}"] = np.array([x, y], float) + OFF
names = list(stations); sxy = np.array([stations[n] for n in names])
SWEEPS = [(dtime(15, 40, 25), dtime(15, 41, 35)), (dtime(15, 41, 40), dtime(15, 45, 45))]
maps = np.load(QC / "refined_pano_maps.npz")

def apply_poly(P, px):
    x, y = px[:, 0] / 1000.0, px[:, 1] / 1000.0
    F = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], 1)
    return np.stack([F @ P[0], F @ P[1]], 1)

best = {n: {"CH01": 0, "CH02": 0, "CH01_t": "", "CH02_t": ""} for n in names}
for cam in ("CH01", "CH02"):
    P = maps[cam]
    with open(QC / f"{cam}_placements_e1.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["clock"], "%H:%M:%S").time()
            if any(a <= t <= b for a, b in SWEEPS) or int(r["max_markers"]) < 4:
                continue
            pos = apply_poly(P, np.array([[float(r["px_x"]), float(r["px_y"])]]))[0]
            d = np.linalg.norm(sxy - pos, axis=1); k = int(np.argmin(d))
            if d[k] <= 25 and int(r["max_corners"]) > best[names[k]][cam]:
                best[names[k]][cam] = int(r["max_corners"]); best[names[k]][cam + "_t"] = r["clock"]

print(f"{'station':7s} {'CH01':>5s} {'CH02':>5s}   time(CH01)  time(CH02)")
for n in names:
    b = best[n]
    flag = "" if (b["CH01"] >= 12 or b["CH02"] >= 12) else "   <-- not usable in either pano"
    print(f"{n:7s} {b['CH01']:5d} {b['CH02']:5d}   {b['CH01_t']:>8s}  {b['CH02_t']:>8s}{flag}")
for cam in ("CH01", "CH02"):
    for s in ("T", "V", "F"):
        ok = [n for n in names if n.startswith(s) and best[n][cam] >= 12]
        print(f"{cam} {s}: {len(ok)} positions with >=12 corners: {', '.join(ok)}")
