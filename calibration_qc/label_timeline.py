# -*- coding: utf-8 -*-
r"""Label every cached board detection (corners/CHxx/<HHMMSS>.npz) with a station ID taken from the
OPERATOR's placement timeline (timeline_gui export, one 'HH:MM:SS-HH:MM:SS  STATION' per line, PC
clock), then report per-camera station coverage. There is NO automatic station guessing: frames
outside every window stay unlabelled and are listed as time clusters for the operator to add to the
timeline (with a nearest-cone suggestion in the pano cameras, clearly marked as a suggestion).

Cross-check (pano cameras CH01/CH02 only): the board outline is projected from the ChArUco corners
through a homography; the outline corner that the operator put on the cone must sit on the cone the
operator labelled with the same station (cone_labels_CHxx.json, static cones, same image, no ground
map involved). Which of the four outline corners is 'the origin corner' is determined from the data
(the corner with the smallest median distance to the same-station cone). Mismatches are flagged,
never corrected.

Settled = the audit's stationary-run criterion (audit_cached_corners.py): >=3 cached frames over
>=3 s, gaps <=5 s, >=12 common corners spanning 3 rows/3 cols, median motion <=3 px vs the first
frame of the run. A station counts as USABLE for a camera when it has a settled run there; SEEN when
only unsettled frames with >=12 corners exist.

Usage: python label_timeline.py [--session <dir|YYYY-MM-DD>] [<timeline.txt>]   (default: <qc>/placement_timeline.txt)
Outputs in the session's QC folder: labelled_frames.csv, station_coverage.txt, unlabelled_clusters.txt
"""
import sys, re, csv, json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess)
TL = Path(args[0]) if args else QC / "placement_timeline.txt"
DAY = qc_paths.session_date(SESSION)
TOL = 1.5          # s: window-edge tolerance (each camera's clock = its own segment start + pts, ~1 s apart)
GAP = 12           # s: splits unlabelled frames into clusters
CAMS = sorted(p.name for p in (QC / "corners").iterdir() if p.is_dir())
PANO = [c for c in ("CH01", "CH02") if c in CAMS]
STATIONS = [f"T{li}{si}" for li in range(1, 8) for si in range(1, 6)] + \
           [f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}" for i in range(1, 7) for j in range(1, 5)]
board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
OBJ = np.asarray(board.getChessboardCorners(), float).reshape(-1, 3)[:, :2] * 1000.0   # id -> board mm
OUTLINE = np.array([[0, 0], [720, 0], [720, 540], [0, 540]], float)                     # board outline, mm
CORNER_NAME = ["(0,0)", "(720,0) +long", "(720,540)", "(0,540) +short"]

def hms(t): return t.strftime("%H:%M:%S")
def clk(s): return datetime.strptime(f"{DAY} {s}", "%Y-%m-%d %H:%M:%S")

# ---------------- operator timeline ----------------
rows = []
for ln in TL.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*(\d\d:\d\d:\d\d)-(\d\d:\d\d:\d\d)\s+(\S+)", ln)
    if m:
        a, b = clk(m.group(1)), clk(m.group(2))
        rows.append([min(a, b), max(a, b), m.group(3).upper()])
rows.sort(key=lambda w: (w[0], w[1]))
notes, wins = [], []
for w in rows:
    same = next((c for c in wins if c[2] == w[2] and w[0] <= c[1] + timedelta(seconds=1) and w[1] >= c[0] - timedelta(seconds=1)), None)
    if same is None:
        wins.append(list(w)); continue
    if (same[0], same[1]) == (w[0], w[1]):
        notes.append(f"duplicate row dropped: {hms(w[0])}-{hms(w[1])} {w[2]}")
    else:
        notes.append(f"same-station rows merged: {hms(w[0])}-{hms(w[1])} + {hms(same[0])}-{hms(same[1])} {w[2]}")
    same[0], same[1] = min(same[0], w[0]), max(same[1], w[1])
wins.sort(key=lambda w: w[0])
for i in range(1, len(wins)):
    if wins[i][0] < wins[i - 1][1]:
        notes.append(f"OVERLAP between different stations: {hms(wins[i-1][0])}-{hms(wins[i-1][1])} {wins[i-1][2]} and {hms(wins[i][0])}-{hms(wins[i][1])} {wins[i][2]}")
unknown = sorted({w[2] for w in wins if w[2] not in STATIONS})
if unknown:
    notes.append("station names not in the design grid: " + ", ".join(unknown))
listed = {w[2] for w in wins}
missing = [s for s in STATIONS if s not in listed]
multi = {s: [w for w in wins if w[2] == s] for s in listed if sum(w[2] == s for w in wins) > 1}

# ---------------- cached corners ----------------
def load_cam(cam):
    out = []
    for p in sorted((QC / "corners" / cam).glob("*.npz")):
        with np.load(p, allow_pickle=False) as z:
            ids = z["ids"].astype(int).reshape(-1); px = z["px"].astype(float).reshape(-1, 2)
            seg = str(z["seg"]); t_rel = float(z["t_rel"]); bw = bool(z["bw"])
        m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d\d)-(\d\d)-(\d\d)_to_", seg)
        t = datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S") + timedelta(seconds=t_rel)
        spread = len(ids) >= 12 and len(set(ids % 11)) >= 3 and len(set(ids // 11)) >= 3
        out.append(dict(cam=cam, t=t, ids=ids, px=px, bw=bw, spread=bool(spread), file=p.name, n=len(ids),
                        station="", win=None, edge=False, run=""))
    return out
frames = {cam: load_cam(cam) for cam in CAMS}

def outline_px(fr):
    """Board outline corners in image px from a homography board-mm -> px (local pinhole approximation)."""
    if fr["n"] < 8 or not fr["spread"]:
        return None
    H, _ = cv2.findHomography(OBJ[fr["ids"]].reshape(-1, 1, 2), fr["px"].reshape(-1, 1, 2), 0)
    if H is None:
        return None
    return cv2.perspectiveTransform(OUTLINE.reshape(-1, 1, 2), H).reshape(-1, 2)

# ---------------- assign frames to windows ----------------
tol = timedelta(seconds=TOL)
for cam in CAMS:
    for fr in frames[cam]:
        inside = [i for i, w in enumerate(wins) if w[0] <= fr["t"] <= w[1]]
        near = [i for i, w in enumerate(wins) if w[0] - tol <= fr["t"] <= w[1] + tol]
        if inside:
            i = inside[0]
        elif near:
            i = min(near, key=lambda j: min(abs((fr["t"] - wins[j][0]).total_seconds()), abs((fr["t"] - wins[j][1]).total_seconds())))
            fr["edge"] = True
        else:
            continue
        fr["win"] = i; fr["station"] = wins[i][2]

# ---------------- settled runs (audit criterion) ----------------
def stationary(fs, tolerance=3.0):
    runs, run = [], []
    def finish():
        if len(run) >= 3 and (run[-1]["t"] - run[0]["t"]).total_seconds() >= 3:
            runs.append(list(run))
    for f in fs:
        ok = False
        if run and f["spread"] and (f["t"] - run[-1]["t"]).total_seconds() <= 5:
            ids, a, b = np.intersect1d(run[0]["ids"], f["ids"], return_indices=True)
            if len(ids) >= 12 and len(set(ids % 11)) >= 3 and len(set(ids // 11)) >= 3:
                d = np.linalg.norm(run[0]["px"][a] - f["px"][b], axis=1)
                ok = np.median(d) <= tolerance and np.quantile(d, .9) <= 2 * tolerance
        if not ok:
            finish(); run = []
        if f["spread"]:
            run.append(f)
    finish()
    return runs

def pose_distance(f, g):
    ids, a, b = np.intersect1d(f["ids"], g["ids"], return_indices=True)
    if len(ids) < 6:
        return np.inf
    return float(np.median(np.linalg.norm(f["px"][a] - g["px"][b], axis=1)))

win_cam = {}      # (win index, cam) -> summary
for i, w in enumerate(wins):
    for cam in CAMS:
        fs = [f for f in frames[cam] if f["win"] == i]
        runs = stationary(fs)
        for k, r in enumerate(runs, 1):
            for f in r:
                f["run"] = f"{cam}-w{i+1}-r{k}"
        poses = []
        for r in runs:                      # distinct settled poses within one window (a re-placed board, or a missed transition)
            if all(pose_distance(r[0], p[0]) > 10 for p in poses):
                poses.append(r)
        win_cam[(i, cam)] = dict(n=len(fs), spread=sum(f["spread"] for f in fs), settled=sum(len(r) for r in runs),
                                 runs=len(runs), poses=len(poses), maxc=max((f["n"] for f in fs), default=0),
                                 bw=sum(f["bw"] for f in fs))

# ---------------- cone cross-check (pano cameras) ----------------
cones = {}
for cam in PANO:
    p = qc_paths.cone_labels(QC, cam)          # the session's own labels, else the 2026-09-18 ones
    if p is None:
        continue
    lab = json.load(open(p, encoding="utf-8"))
    SW = lab.get("frame_size_upright", [7680, 2160])[1]          # stored (rotated) frame width = upright height
    cones[cam] = [(q["station"].upper(), np.array([SW - 1 - q["y"], q["x"]], float))
                  for q in lab["points"] if q.get("station") and q["station"].upper() != "NONE"]
origin_corner, cone_report, suggestions = {}, {}, {}
for cam in cones:
    names = [c[0] for c in cones[cam]]; cxy = np.array([c[1] for c in cones[cam]])
    # 1) which outline corner did the operator put on the cone? median distance per corner over labelled frames
    per_corner = [[] for _ in range(4)]
    for f in frames[cam]:
        if not f["station"] or f["station"] not in names or f["edge"]:
            continue
        o = outline_px(f)
        if o is None:
            continue
        c = cxy[names.index(f["station"])]
        for k in range(4):
            per_corner[k].append(np.linalg.norm(o[k] - c))
    med = [float(np.median(v)) if v else np.inf for v in per_corner]
    k_best = int(np.argmin(med)) if per_corner[0] else 3        # no labelled frames yet -> design convention (0,540)
    origin_corner[cam] = (k_best, med, len(per_corner[0]))
    # 2) per window: nearest cone to that corner (majority over the window's frames), plus WHICH outline corner
    #    actually sits on the operator's cone and the long-edge direction in the upright image
    #    (CH01: field +x = image right = 0 deg; CH02: field +x = image left = 180 deg)
    SH = 2160                                   # stored frame height (= upright width)... stored (sx,sy) -> upright (sy, SH-1-sx)
    def upright(p): return np.stack([p[:, 1], (SH - 1) - p[:, 0]], 1)
    for i, w in enumerate(wins):
        votes, dist_op, dist_near = {}, [], []
        dists = [[] for _ in range(4)]; angs = []
        for f in frames[cam]:
            if f["win"] != i or f["edge"]:
                continue
            o = outline_px(f)
            if o is None:
                continue
            d = np.linalg.norm(cxy - o[k_best], axis=1); j = int(np.argmin(d))
            votes[names[j]] = votes.get(names[j], 0) + 1; dist_near.append(d[j])
            if w[2] in names:
                c = cxy[names.index(w[2])]; dist_op.append(d[names.index(w[2])])
                for k in range(4):
                    dists[k].append(np.linalg.norm(o[k] - c))
            u = upright(o); v = u[1] - u[0]
            angs.append(np.arctan2(v[1], v[0]))
        if votes:
            best = max(votes, key=votes.get)
            r = dict(nearest=best, frac=votes[best] / sum(votes.values()), d_near=float(np.median(dist_near)),
                     d_op=float(np.median(dist_op)) if dist_op else None, labelled=w[2] in names, n=len(angs))
            r["ang"] = float(np.degrees(np.arctan2(np.median(np.sin(angs)), np.median(np.cos(angs)))))
            exp = 0.0 if cam == "CH01" else 180.0
            r["ang_off"] = abs((r["ang"] - exp + 180) % 360 - 180)
            if dists[0]:
                med = [float(np.median(x)) for x in dists]; k = int(np.argmin(med))
                r["corner"] = k; r["corner_d"] = med[k]
            cone_report[(i, cam)] = r

# ---------------- unlabelled frames -> clusters ----------------
left = sorted((f for cam in CAMS for f in frames[cam] if f["win"] is None), key=lambda f: f["t"])
clusters = []
for f in left:
    if clusters and (f["t"] - clusters[-1]["end"]).total_seconds() <= GAP:
        clusters[-1]["end"] = f["t"]; clusters[-1]["fs"].append(f)
    else:
        clusters.append(dict(start=f["t"], end=f["t"], fs=[f]))
for c in clusters:
    c["per_cam"] = {cam: sum(f["cam"] == cam for f in c["fs"]) for cam in CAMS}
    c["maxc"] = {cam: max((f["n"] for f in c["fs"] if f["cam"] == cam), default=0) for cam in CAMS}
    c["suggest"] = {}
    for cam in cones:
        names = [q[0] for q in cones[cam]]; cxy = np.array([q[1] for q in cones[cam]]); k = origin_corner[cam][0]
        votes, dd = {}, {}
        for f in c["fs"]:
            if f["cam"] != cam:
                continue
            o = outline_px(f)
            if o is None:
                continue
            d = np.linalg.norm(cxy - o[k], axis=1); j = int(np.argmin(d))
            votes[names[j]] = votes.get(names[j], 0) + 1; dd.setdefault(names[j], []).append(d[j])
        if votes:
            best = max(votes, key=votes.get)
            c["suggest"][cam] = (best, votes[best] / sum(votes.values()), float(np.median(dd[best])))

# ---------------- outputs ----------------
with open(QC / "labelled_frames.csv", "w", newline="", encoding="utf-8") as fh:
    wr = csv.writer(fh)
    wr.writerow(["cam", "clock", "file", "station", "window_start", "window_end", "edge", "n_corners", "spread", "bw_IR", "settled_run"])
    for cam in CAMS:
        for f in frames[cam]:
            w = wins[f["win"]] if f["win"] is not None else None
            wr.writerow([cam, f["t"].strftime("%H:%M:%S.%f")[:-5], f["file"], f["station"], hms(w[0]) if w else "", hms(w[1]) if w else "",
                         int(f["edge"]), f["n"], int(f["spread"]), int(f["bw"]), f["run"]])

L = []
L.append(f"Operator timeline: {TL}  ({len(rows)} rows -> {len(wins)} windows, {len(listed)} distinct stations of {len(STATIONS)})")
for n in notes:
    L.append("  note: " + n)
if multi:
    L.append("  stations with more than one window (re-placed): " + "; ".join(f"{s} x{len(v)}" for s, v in sorted(multi.items())))
L.append("  stations NOT in the timeline: " + (", ".join(missing) if missing else "none"))
L.append(("  timeline span " + (f"{hms(wins[0][0])}-{hms(wins[-1][1])}" if wins else "EMPTY (no windows yet)")) + "; cached detections span "
         + ", ".join(f"{cam} {hms(frames[cam][0]['t'])}-{hms(frames[cam][-1]['t'])}" for cam in CAMS if frames[cam]))
L.append("")
L.append("Cone cross-check (pano cameras): outline corner nearest the same-station cone, median px distance per corner, frames used")
for cam, (k, med, nfr) in origin_corner.items():
    L.append(f"  {cam}: origin corner = outline {CORNER_NAME[k]}; median distance per corner "
             f"{[round(x) if np.isfinite(x) else None for x in med]} px over {nfr} frames" + ("" if nfr else " (none labelled yet -> design convention assumed)"))
L.append("")
L.append("Per window: station, PC-clock window, then per camera  frames/settled/maxcorners  (p2 = two distinct settled poses in the window)")
hdr = f"{'#':>3} {'station':7s} {'window':17s} " + " ".join(f"{cam:>11s}" for cam in CAMS) + "   cone check (pano)"
L.append(hdr)
flags = []
for i, w in enumerate(wins):
    cells = []
    for cam in CAMS:
        s = win_cam[(i, cam)]
        cell = f"{s['n']}/{s['settled']}/{s['maxc']}" if s["n"] else "-"
        if s["poses"] > 1:
            cell += "p2"
        cells.append(f"{cell:>11s}")
    chk = []
    for cam in PANO:
        r = cone_report.get((i, cam))
        if r is None:
            continue
        dirtxt = f" dir{r['ang']:+.0f}" + ("!" if r["ang_off"] > 60 else "")
        if "corner" in r:
            k = r["corner"]
            chk.append(f"{cam} cone@{CORNER_NAME[k].split()[0]} {r['corner_d']:.0f}px" + ("" if k == 3 and r["corner_d"] <= 150 else " *") + dirtxt)
            if k != 3 or r["corner_d"] > 150:
                flags.append(f"window {i+1} {hms(w[0])}-{hms(w[1])} {w[2]}: {cam} cone sits at outline corner {CORNER_NAME[k]} "
                             f"({r['corner_d']:.0f}px), not (0,540) -> record the offset for the fit")
        elif r["nearest"] != w[2]:
            chk.append(f"{cam} no {w[2]} cone label; nearest {r['nearest']} {r['d_near']:.0f}px" + dirtxt)
        else:
            chk.append(f"{cam} ok({r['d_near']:.0f}px)" + dirtxt)
        if r["ang_off"] > 60:
            flags.append(f"window {i+1} {hms(w[0])}-{hms(w[1])} {w[2]}: {cam} long edge points {r['ang']:+.0f} deg in the upright image "
                         f"(expected {'0' if cam == 'CH01' else '180'}) -> board rotated?")
    L.append(f"{i+1:>3} {w[2]:7s} {hms(w[0])}-{hms(w[1])} " + " ".join(cells) + "   " + "; ".join(chk))
L.append("")
L.append("Cone cross-check summary (pano cameras): 'cone@(x,y)' = the board outline corner (board mm) that sits on the operator's cone;")
L.append("  the design convention is (0,540) on the cone with the long edge along +x ('dir' = long-edge direction in the upright image).")
tally = {}
for (i, cam), r in cone_report.items():
    if "corner" in r:
        tally[(cam, r["corner"])] = tally.get((cam, r["corner"]), 0) + 1
for cam in PANO:
    L.append(f"  {cam}: " + ", ".join(f"{CORNER_NAME[k].split()[0]} x{tally.get((cam, k), 0)}" for k in range(4)) + " windows with a labelled same-station cone")
if flags:
    L.append("Placements that deviate from the convention (verify in show_frame.py before fitting):")
    L.extend("  " + x for x in flags)
else:
    L.append("All checked placements follow the convention.")
L.append("")
# station x camera matrix
usable = {cam: {} for cam in CAMS}; seen = {cam: {} for cam in CAMS}
for (i, cam), s in win_cam.items():
    st = wins[i][2]
    if s["settled"]:
        usable[cam][st] = max(usable[cam].get(st, 0), s["settled"])
    elif s["spread"]:
        seen[cam][st] = max(seen[cam].get(st, 0), s["maxc"])
L.append("Station x camera: S<n> = settled frames (usable), s<c> = seen only (max corners, no settled run), - = nothing cached")
L.append(f"{'station':7s} " + " ".join(f"{cam:>6s}" for cam in CAMS))
for st in STATIONS:
    if st not in listed:
        L.append(f"{st:7s} " + " ".join(f"{'?':>6s}" for _ in CAMS) + "   not in timeline")
        continue
    cells = []
    for cam in CAMS:
        if st in usable[cam]:
            cells.append(f"S{usable[cam][st]}")
        elif st in seen[cam]:
            cells.append(f"s{seen[cam][st]}")
        else:
            cells.append("-")
    L.append(f"{st:7s} " + " ".join(f"{c:>6s}" for c in cells))
L.append("")
# The operator's timeline already vouches that the board was ON THE GROUND at that station during the
# window (gate A of /detect-then-decode), so a detection inside the window is a usable observation; the
# settled run is a stricter, motion-based confirmation, not the admission criterion.
have12 = {cam: {} for cam in CAMS}; have30 = {cam: {} for cam in CAMS}
for (i, cam), s in win_cam.items():
    st = wins[i][2]
    if s["maxc"] >= 12:
        have12[cam][st] = max(have12[cam].get(st, 0), s["maxc"])
    if s["maxc"] >= 30:
        have30[cam][st] = max(have30[cam].get(st, 0), s["maxc"])
L.append("Stations per camera, three thresholds (a station counts once, whichever of its windows is best):")
L.append(f"{'camera':7s} {'>=12 corners':>13s} {'>=30 corners':>13s} {'settled run':>12s}   (T / V / F of 35 / 12 / 12)")
for cam in CAMS:
    def by_set(d):
        return "/".join(str(sum(1 for k in d if k[0] == s)) for s in "TVF")
    L.append(f"{cam:7s} {len(have12[cam]):13d} {len(have30[cam]):13d} {len(usable[cam]):12d}   "
             f"{by_set(have12[cam])}  |  {by_set(have30[cam])}  |  {by_set(usable[cam])}")
L.append("")
for cam in CAMS:
    L.append(f"  {cam} stations with >=12 corners ({len(have12[cam])}): " + (", ".join(sorted(have12[cam])) or "none"))
    miss = [st for st in listed if st not in have12[cam]]
    L.append(f"      no detection at all in {cam} ({len(miss)}): " + (", ".join(sorted(miss)) or "none"))
L.append("")
L.append("Usable stations per camera (settled run) / seen-only, by set  (T = training 35, V = validation 12, F = final test 12)")
for cam in CAMS:
    parts = []
    for s in "TVF":
        u = sorted(k for k in usable[cam] if k[0] == s); v = sorted(k for k in seen[cam] if k[0] == s)
        parts.append(f"{s}: {len(u)} usable (+{len(v)} seen-only)")
    L.append(f"  {cam}: " + "; ".join(parts))
    for s in "TVF":
        u = sorted(k for k in usable[cam] if k[0] == s); v = sorted(k for k in seen[cam] if k[0] == s)
        L.append(f"      {s} usable: {', '.join(u) if u else 'none'}" + (f"   seen-only: {', '.join(v)}" if v else ""))
L.append("")
tot = sum(len(frames[c]) for c in CAMS); lab_n = sum(f['win'] is not None for c in CAMS for f in frames[c])
L.append(f"Frames: {tot} cached, {lab_n} inside a timeline window, {tot - lab_n} unlabelled -> unlabelled_clusters.txt ({len(clusters)} clusters)")
(QC / "station_coverage.txt").write_text("\n".join(L) + "\n", encoding="utf-8")

U = [f"Unlabelled cached detections (outside every timeline window +-{TOL}s), clustered with gaps > {GAP}s.",
     "Per camera: frames(max corners). Suggestion = cone nearest the board's origin corner in that pano image (operator's cone labels);",
     "it is a SUGGESTION for the operator to confirm in timeline_gui, not a label.", ""]
U.append(f"{'#':>3} {'start':8s}-{'end':8s} {'dur':>4s} " + " ".join(f"{cam:>9s}" for cam in CAMS) + "   suggestion")
for j, c in enumerate(clusters, 1):
    cells = " ".join(f"{(str(c['per_cam'][cam]) + '(' + str(c['maxc'][cam]) + ')') if c['per_cam'][cam] else '-':>9s}" for cam in CAMS)
    sug = "; ".join(f"{cam} {s[0]} ({s[1]:.0%}, {s[2]:.0f}px)" for cam, s in c["suggest"].items())
    U.append(f"{j:>3} {hms(c['start'])}-{hms(c['end'])} {(c['end']-c['start']).total_seconds():>4.0f} {cells}   {sug}")
(QC / "unlabelled_clusters.txt").write_text("\n".join(U) + "\n", encoding="utf-8")
print("\n".join(L)); print(); print("\n".join(U))
print("\n->", QC / "labelled_frames.csv", "|", QC / "station_coverage.txt", "|", QC / "unlabelled_clusters.txt")
