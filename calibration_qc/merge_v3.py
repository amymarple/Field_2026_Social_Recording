# -*- coding: utf-8 -*-
"""Station assignment v3: self-refining map.
1. per-camera clusters (every-keyframe run), sweep windows excluded;
2. initial pano positions from the old 20-pt polys;
3. confident matches -> refit a 2nd-order poly per pano camera (px -> field inches);
4. remap everything, greedy unique assignment, iterate.
Outputs coverage_v3.txt, station_assignments.csv, coverage_map_v3.png
"""
import csv, sys
from pathlib import Path
from datetime import datetime, time as dtime
import numpy as np

QC = Path(r"E:\calibration\qc")
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
OFF = np.array([14.2, 10.6])          # board centroid relative to the origin corner (long edge along +x)
stations = {}
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1):
        stations[f"T{li}{si}"] = np.array([x, y], float) + OFF
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1):
        stations[f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}"] = np.array([x, y], float) + OFF
names = list(stations); sxy = np.array([stations[n] for n in names])

SWEEPS = [(dtime(15, 40, 25), dtime(15, 41, 35)), (dtime(15, 41, 40), dtime(15, 45, 45))]   # hand-held board
def in_sweep(t):
    return any(a <= t.time() <= b for a, b in SWEEPS)

def load(cam):
    rows = []
    p = QC / f"{cam}_placements_e1.csv"
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["clock"], "%H:%M:%S")
            if in_sweep(t) or int(r["max_markers"]) < 4:
                continue
            rows.append(dict(cam=cam, t=t, dur=float(r["dur_s"]), corners=int(r["max_corners"]),
                             px=np.array([float(r["px_x"]), float(r["px_y"])]),
                             fx=float(r["field_in_x"]) if r["field_in_x"] else None,
                             fy=float(r["field_in_y"]) if r["field_in_y"] else None))
    return rows

ev = {c: load(c) for c in ["CH01", "CH02", "CH03", "CH04"]}

def poly_feats(px):
    x, y = px[:, 0] / 1000.0, px[:, 1] / 1000.0
    return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], 1)

def fit_poly(px, xy):
    F = poly_feats(px)
    cx, *_ = np.linalg.lstsq(F, xy[:, 0], rcond=None); cy, *_ = np.linalg.lstsq(F, xy[:, 1], rcond=None)
    return np.stack([cx, cy])

def apply_poly(P, px):
    F = poly_feats(np.atleast_2d(px)); return np.stack([F @ P[0], F @ P[1]], 1)

# ---- iteration ----
maps = {"CH01": None, "CH02": None}
for it in range(4):
    # position per pano event
    for cam in ("CH01", "CH02"):
        for e in ev[cam]:
            if maps[cam] is not None:
                e["pos"] = apply_poly(maps[cam], e["px"])[0]
            elif e["fx"] is not None:
                e["pos"] = np.array([e["fx"], e["fy"]])
            else:
                e["pos"] = None
    # cluster pano events across the two cameras by time (<=15 s) and position (<=25 in)
    allev = sorted(ev["CH01"] + ev["CH02"], key=lambda e: e["t"])
    clusters = []
    for e in allev:
        if e["pos"] is None or e["corners"] < 6:
            continue
        placed = False
        for c in clusters[-3:]:
            if abs((e["t"] - c["t_end"]).total_seconds()) <= 15 and np.linalg.norm(e["pos"] - c["pos"]) <= 25:
                n = c["n"]; c["pos"] = (c["pos"] * n + e["pos"]) / (n + 1); c["n"] = n + 1
                c["t_end"] = max(c["t_end"], e["t"]); c["events"].append(e); placed = True; break
        if not placed:
            clusters.append(dict(t=e["t"], t_end=e["t"], pos=e["pos"].copy(), n=1, events=[e]))
    # greedy unique assignment
    thr = 40 if it == 0 else 22
    cand = []
    for ci, c in enumerate(clusters):
        d = np.linalg.norm(sxy - c["pos"], axis=1); o = np.argsort(d)
        c["near"] = [(names[o[k]], float(d[o[k]])) for k in range(3)]
        c["station"] = None
        cand.append((d[o[0]], ci))
    used = {}
    for d, ci in sorted(cand):
        st = clusters[ci]["near"][0][0]
        if d <= thr and st not in used:
            used[st] = ci; clusters[ci]["station"] = st
    # refit pano maps from confident anchors
    for cam in ("CH01", "CH02"):
        px, xy = [], []
        for c in clusters:
            if c["station"] is None or c["near"][0][1] > (25 if it == 0 else 15):
                continue
            for e in c["events"]:
                if e["cam"] == cam and e["corners"] >= 30:
                    px.append(e["px"]); xy.append(stations[c["station"]])
        if len(px) >= 15:
            maps[cam] = fit_poly(np.array(px), np.array(xy))
            res = np.linalg.norm(apply_poly(maps[cam], np.array(px)) - np.array(xy), axis=1)
            print(f"iter {it}: {cam} refit on {len(px)} anchors, rms {np.sqrt((res**2).mean()):.1f} in, max {res.max():.1f} in")
    print(f"iter {it}: {len(clusters)} clusters, {len(used)} stations assigned")

# ---- report ----
out = []
out.append(f"{'clock':>8}-{'end':<8} n  CH01 CH02   field(in)   station  dist  alternates")
for c in clusters:
    pc = {}
    for e in c["events"]: pc[e["cam"]] = max(pc.get(e["cam"], 0), e["corners"])
    alt = ", ".join(f"{n}({d:.0f})" for n, d in c["near"][1:])
    out.append(f"{c['t'].strftime('%H:%M:%S')}-{c['t_end'].strftime('%H:%M:%S')} {c['n']:>2} {pc.get('CH01',0):>4} {pc.get('CH02',0):>4}   {c['pos'][0]:4.0f},{c['pos'][1]:3.0f}   {c['station'] or '-':<5}  {c['near'][0][1]:4.0f}  {c['near'][0][0]}: {alt}")
missing = [n for n in names if n not in used]
out.append(f"\nstations assigned: {len(used)}/59")
out.append("MISSING: " + ", ".join(missing))
for m in missing:
    d = [(np.linalg.norm(c["pos"] - stations[m]), c) for c in clusters if c["station"] is None]
    d.sort(key=lambda x: x[0])
    if d and d[0][0] < 40:
        c = d[0][1]; out.append(f"   {m}: nearest unassigned cluster {c['t'].strftime('%H:%M:%S')} at {d[0][0]:.0f} in (pos {c['pos'][0]:.0f},{c['pos'][1]:.0f})")
    else:
        out.append(f"   {m}: no unassigned cluster within 40 in -> probably not placed")
txt = "\n".join(out); print(txt)
(QC / "coverage_v3.txt").write_text(txt, encoding="utf-8")
with open(QC / "station_assignments.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["station", "design_x_in", "design_y_in", "clock_start", "clock_end", "mapped_x_in", "mapped_y_in", "dist_in", "CH01_corners", "CH02_corners"])
    for c in clusters:
        if c["station"]:
            pc = {}
            for e in c["events"]: pc[e["cam"]] = max(pc.get(e["cam"], 0), e["corners"])
            s = stations[c["station"]] - OFF
            w.writerow([c["station"], s[0], s[1], c["t"].strftime("%H:%M:%S"), c["t_end"].strftime("%H:%M:%S"),
                        round(c["pos"][0], 1), round(c["pos"][1], 1), round(c["near"][0][1], 1), pc.get("CH01", 0), pc.get("CH02", 0)])
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(13, 7))
ax.add_patch(plt.Rectangle((0, 0), 480, 240, fill=False, lw=2))
for n, xy in stations.items():
    col = "green" if n in used else "red"
    ax.scatter(xy[0], xy[1], s=140, facecolors="none", edgecolors=col, lw=2)
    ax.annotate(n, xy, xytext=(0, 9), textcoords="offset points", ha="center", fontsize=8, color=col)
for c in clusters:
    ax.scatter(c["pos"][0], c["pos"][1], s=12 + c["n"] * 3, c="k" if c["station"] else "orange", alpha=0.6)
ax.set_xlim(-20, 500); ax.set_ylim(-20, 260); ax.set_aspect("equal"); ax.set_xlabel("x (in)"); ax.set_ylabel("y (in)")
ax.set_title(f"2026-09-18 session, refined map: green=matched {len(used)}/59, red=missing; black=assigned cluster, orange=unassigned")
fig.tight_layout(); fig.savefig(QC / "coverage_map_v3.png", dpi=130)
print("map -> coverage_map_v3.png")
