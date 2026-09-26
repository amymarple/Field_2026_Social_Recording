# -*- coding: utf-8 -*-
"""Per-placement usability WITHOUT station labels: cluster CH01+CH02 events by time only (the
board is in one place at a time), report max corners per camera per placement."""
import csv
from pathlib import Path
from datetime import datetime, time as dtime

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
QC = qc_paths.QC_ROOT
SWEEPS = [(dtime(15, 40, 25), dtime(15, 41, 35)), (dtime(15, 41, 40), dtime(15, 45, 45))]
events = []
for cam in ("CH01", "CH02"):
    with open(QC / f"{cam}_placements_e1.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["clock"], "%H:%M:%S")
            if any(a <= t.time() <= b for a, b in SWEEPS) or int(r["max_markers"]) < 4:
                continue
            events.append((t, cam, int(r["max_corners"]), float(r["dur_s"]), r["bw_IR"] == "1"))
events.sort()
clusters = []
for t, cam, nc, dur, bw in events:
    if clusters and (t - clusters[-1]["t_end"]).total_seconds() <= 12:
        c = clusters[-1]; c["t_end"] = max(c["t_end"], t)
    else:
        clusters.append(dict(t=t, t_end=t, CH01=0, CH02=0, IR=set()))
        c = clusters[-1]
    c[cam] = max(c[cam], nc)
    if bw: c["IR"].add(cam)
print(f"{'placement window':19s} {'CH01':>5s} {'CH02':>5s}  IR")
for c in clusters:
    print(f"{c['t'].strftime('%H:%M:%S')}-{c['t_end'].strftime('%H:%M:%S')} {c['CH01']:5d} {c['CH02']:5d}  {','.join(sorted(c['IR']))}")
n = len(clusters)
a = sum(c["CH01"] >= 12 for c in clusters); b = sum(c["CH02"] >= 12 for c in clusters)
both = sum(c["CH01"] >= 12 and c["CH02"] >= 12 for c in clusters)
either = sum(c["CH01"] >= 12 or c["CH02"] >= 12 for c in clusters)
print(f"\nplacement clusters (time-only, pano cameras): {n}")
print(f"usable (>=12 corners) in CH01: {a}   in CH02: {b}   in both: {both}   in at least one: {either}")
print(f"seen only with <12 corners in both: {n - either}")
