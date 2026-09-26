# -*- coding: utf-8 -*-
"""Give every board placement its station ID from the operator's cone labels: the board's
origin-side corner is matched to the nearest labelled cone IN THE SAME CAMERA IMAGE (pixels,
static cones), no ground map involved. Then propagate IDs to the other cameras by time.
Usage: python label_placements.py CH01 E:\calibration\qc\cone_labels_CH01.json"""
import sys, csv, json
from pathlib import Path
from datetime import datetime, time as dtime, timedelta
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
QC = qc_paths.QC_ROOT
cam, labels_path = sys.argv[1], sys.argv[2]
SWEEPS = [(dtime(15, 40, 25), dtime(15, 41, 35)), (dtime(15, 41, 40), dtime(15, 45, 45))]
lab = json.load(open(labels_path, encoding="utf-8"))
FW = lab.get("frame_size_upright", [7680, 2160])[0]; SW = 2160   # stored frame width
cones = []
for p in lab["points"]:
    if p.get("station") and p["station"] != "NONE":
        # upright (x right, y down) -> stored (rotated) pixel coords used by the QC CSVs / npz
        cones.append((p["station"], np.array([SW - 1 - p["y"], p["x"]], float)))
cxy = np.array([c[1] for c in cones]); cname = [c[0] for c in cones]

def anchor_px(clock_tag, fallback):
    f = QC / "corners" / cam / f"{clock_tag}.npz"
    if f.exists():
        d = np.load(f, allow_pickle=True); ids = d["ids"]; px = d["px"]
        k = int(np.argmin(ids))                     # lowest corner id = nearest the board origin corner
        return px[k], int(ids[k]), len(ids)
    return np.array(fallback), None, 0

events = []
with open(QC / f"{cam}_placements_e1.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        t = datetime.strptime(r["clock"], "%H:%M:%S")
        if any(a <= t.time() <= b for a, b in SWEEPS) or int(r["max_corners"]) < 6:
            continue
        px, cid, n = anchor_px(r["clock"].replace(":", ""), (float(r["px_x"]), float(r["px_y"])))
        d = np.linalg.norm(cxy - px, axis=1); o = np.argsort(d)
        events.append(dict(t=t, corners=int(r["max_corners"]), px=px, station=cname[o[0]], d1=float(d[o[0]]),
                           alt=cname[o[1]], d2=float(d[o[1]]), anchor_id=cid))
events.sort(key=lambda e: e["t"])
# cluster by time (<=12 s) -> placements; station by corner-weighted vote
placements = []
for e in events:
    if placements and (e["t"] - placements[-1]["t_end"]).total_seconds() <= 12:
        c = placements[-1]; c["t_end"] = e["t"]; c["ev"].append(e)
    else:
        placements.append(dict(t=e["t"], t_end=e["t"], ev=[e]))
rows = []
for c in placements:
    votes = {}
    for e in c["ev"]:
        votes[e["station"]] = votes.get(e["station"], 0) + e["corners"]
    st = max(votes, key=votes.get); best = max(c["ev"], key=lambda e: e["corners"])
    conf = votes[st] / sum(votes.values())
    ratio = min(e["d2"] / max(e["d1"], 1) for e in c["ev"] if e["station"] == st)
    rows.append(dict(start=c["t"].strftime("%H:%M:%S"), end=c["t_end"].strftime("%H:%M:%S"), station=st,
                     max_corners=best["corners"], n_samples=len(c["ev"]), vote_frac=round(conf, 2),
                     px_dist=round(min(e["d1"] for e in c["ev"] if e["station"] == st)), alt=best["alt"], sep_ratio=round(ratio, 2)))
with open(QC / f"placements_labelled_{cam}.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"{'start':>8}-{'end':<8} {'station':7s} {'corners':>7} {'smp':>3} {'vote':>5} {'px':>5} {'ratio':>5}  alt")
for r in rows:
    flag = "" if r["sep_ratio"] >= 1.5 and r["vote_frac"] >= 0.7 else "   <-- check"
    print(f"{r['start']}-{r['end']} {r['station']:7s} {r['max_corners']:7d} {r['n_samples']:3d} {r['vote_frac']:5.2f} {r['px_dist']:5d} {r['sep_ratio']:5.2f}  {r['alt']}{flag}")
seen = {}
for r in rows:
    if r["max_corners"] >= 12:
        seen.setdefault(r["station"], []).append(r["start"])
print(f"\n{cam}: {len(rows)} placements; stations with >=12-corner placement: {len(seen)} -> {', '.join(sorted(seen))}")
multi = {k: v for k, v in seen.items() if len(v) > 1}
if multi: print("stations hit more than once (re-placed or split cluster): " + "; ".join(f"{k}@{','.join(v)}" for k, v in multi.items()))
never = [c for c in cname if c not in seen]
print(f"labelled cones with no >=12-corner placement in {cam}: {', '.join(never) if never else 'none'}")
