# -*- coding: utf-8 -*-
"""QC of calibration-session footage: find ChArUco board placements per camera.

For each closed segment: decode keyframes only (every 2nd -> ~4 s), detect the board
(DICT_5X5_100, 12x9, 60/45 mm), flag IR/B&W frames (low chroma) and saturation inside
the board bbox, cluster consecutive detections into placements, and map each placement
through the OLD 20-pt poly (~50 cm) to the nearest designed station (T/V/F, inches).
Usage: python qc_placements.py CH01 [segment substring filter] [--every N]
"""
import sys, os, re, json, subprocess, threading, time, csv
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, r"C:\Users\Cornell\Documents\GitHub\Field_2026_Social\preprocessing\computer_vision")
import field_coords as fc  # noqa: E402

SESSION = Path(r"E:\calibration\session_2026-09-18_13-54-34")
FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"
FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
CONFIGS = Path(r"C:\Users\Cornell\Documents\GitHub\Field_2026_Social\preprocessing\computer_vision\configs")
OUT = Path(r"E:\calibration\qc")
OUT.mkdir(parents=True, exist_ok=True)

cam = sys.argv[1]
seg_filter = None
every = 2
args = sys.argv[2:]
if "--every" in args:
    i = args.index("--every"); every = int(args[i + 1]); del args[i:i + 2]
if args:
    seg_filter = args[0]

# ---- designed stations (inches), board centroid = origin corner + (14.2, 10.6) in ----
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
stations = []
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1):
        stations.append((f"T{li}{si}", x + 14.2, y + 10.6))
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1):
        s = "V" if (i + j) % 2 == 0 else "F"
        stations.append((f"{s}{i}{j}", x + 14.2, y + 10.6))
st_xy = np.array([[s[1], s[2]] for s in stations])

# ---- old poly calib (pixel space = stored frame) ----
calib = None
cp = CONFIGS / f"{cam}_calib.json"
if cp.exists():
    c = json.loads(cp.read_text(encoding="utf-8-sig"))
    if c.get("type") == "poly":
        calib = np.asarray(c["forward"], float)
        calib_size = c.get("image_size")

frame_wh = [None, None]   # set from the first probed segment; the old calib may be in a scaled pixel space

def px_to_station(px):
    """pixel (x,y) -> (field inch x, y, best station, dist in, 2nd station, dist2)."""
    if calib is None:
        return None
    px = np.array([px], float)
    if calib_size and frame_wh[0] and (calib_size[0] != frame_wh[0] or calib_size[1] != frame_wh[1]):
        px = px * np.array([calib_size[0] / frame_wh[0], calib_size[1] / frame_wh[1]])
    cm = fc._apply_poly(calib, px)[0]
    inch = cm / 2.54
    d = np.hypot(st_xy[:, 0] - inch[0], st_xy[:, 1] - inch[1])
    o = np.argsort(d)
    return inch[0], inch[1], stations[o[0]][0], d[o[0]], stations[o[1]][0], d[o[1]]

# ---- detector ----
dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, dic)
# The OpenCV default minMarkerPerimeterRate=0.03 is relative to the LARGEST image side: on a
# 7680-px pano it rejects every marker under ~58 px, i.e. every board beyond ~3 m. Measured
# 2026-09-18 on a far-zone board: default 0 markers; these params 19 markers on the full frame,
# 33 markers / 47 corners after a 3x upscale of the board crop, at +0.15 s per frame.
dp = cv2.aruco.DetectorParameters()
dp.minMarkerPerimeterRate = 0.005
dp.perspectiveRemovePixelPerCell = 8
dp.errorCorrectionRate = 0.8
det = cv2.aruco.CharucoDetector(board, detectorParams=dp)
REFINE_SCALE = 3
CORNER_DIR = OUT / "corners" / cam
CORNER_DIR.mkdir(parents=True, exist_ok=True)

def detect_refined(gray):
    """Full-frame detection, then re-detect on a 3x upscaled crop of the board region.
    Returns (n_markers, n_corners, marker_corner_array_fullframe, charuco_corners_fullframe, charuco_ids)."""
    ch_c, ch_ids, mk_c, mk_ids = det.detectBoard(gray)
    if mk_ids is None or not len(mk_ids):
        return 0, 0, None, None, None
    allc = np.concatenate([m.reshape(-1, 2) for m in mk_c])
    x0, y0 = allc.min(0); x1, y1 = allc.max(0)
    pad = 0.35 * max(x1 - x0, y1 - y0) + 20
    H, W = gray.shape
    x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad)); x1, y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
    crop = gray[y0:y1, x0:x1]
    if crop.size and max(crop.shape) * REFINE_SCALE <= 6000:
        up = cv2.resize(crop, None, fx=REFINE_SCALE, fy=REFINE_SCALE, interpolation=cv2.INTER_CUBIC)
        c2, i2, m2, mi2 = det.detectBoard(up)
        n2 = 0 if mi2 is None else len(mi2)
        if n2 >= len(mk_ids):
            off = np.array([x0, y0], float)
            mk_full = np.concatenate([m.reshape(-1, 2) for m in m2]) / REFINE_SCALE + off
            ch_full = None if i2 is None else (c2.reshape(-1, 2) / REFINE_SCALE + off)
            return n2, (0 if i2 is None else len(i2)), mk_full, ch_full, (None if i2 is None else i2.reshape(-1))
    ch_full = None if ch_ids is None else ch_c.reshape(-1, 2)
    return len(mk_ids), (0 if ch_ids is None else len(ch_ids)), allc, ch_full, (None if ch_ids is None else ch_ids.reshape(-1))

def probe(path):
    out = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0",
                                   "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)])
    w, h = [int(v) for v in out.decode().strip().split(",")[:2]]
    return w, h

def seg_start(name):
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", name)
    return f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}"

def hms_add(base, secs):
    from datetime import datetime, timedelta
    t = datetime.strptime(base, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=secs)
    return t.strftime("%H:%M:%S")

segs = sorted(p for p in SESSION.glob(f"{cam}_*_to_*.mp4") if (seg_filter is None or seg_filter in p.name))
if not segs:
    sys.exit(f"no closed segments for {cam}")

rows = []   # per-sample records
t_start_all = time.time()
for seg in segs:
    w, h = probe(seg)
    frame_wh[0], frame_wh[1] = w, h
    base = seg_start(seg.name)
    frame_bytes = w * h * 3 // 2
    cmd = [FFMPEG, "-v", "info", "-nostats", "-skip_frame", "nokey", "-i", str(seg),
           "-vf", f"select=not(mod(n\\,{every})),showinfo", "-vsync", "0",
           "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=frame_bytes * 4)
    pts = []
    def rd():
        for line in proc.stderr:
            m = re.search(rb"pts_time:\s*([0-9.]+)", line)
            if m and b"showinfo" in line:
                pts.append(float(m.group(1)))
    th = threading.Thread(target=rd, daemon=True); th.start()
    n = 0; t0 = time.time(); ndet = 0
    while True:
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        # wait for this frame's pts to arrive from stderr
        for _ in range(200):
            if len(pts) > n: break
            time.sleep(0.005)
        t_rel = pts[n] if len(pts) > n else n * every * 2.0
        y = np.frombuffer(buf, np.uint8, count=w * h).reshape(h, w)
        uv = np.frombuffer(buf, np.uint8, offset=w * h).reshape(2, h // 2, w // 2)
        # IR/B&W = both chroma planes sit at 128; a colour frame of plain grass has U,V offset
        # from 128 even when their std is small, so use mean |U-128|, |V-128|, not std
        chroma_std = float(max(np.abs(uv[0].astype(np.int16) - 128).mean(), np.abs(uv[1].astype(np.int16) - 128).mean()))
        bw = chroma_std < 2.0
        nm, nc, allc, ch_full, ch_id = detect_refined(y)
        cx = cy = sat = None; bbox = None
        if nm:
            cx, cy = allc.mean(0)
            if nc >= 12:   # keep the decoded corners (full-frame px + ids) for the calibration fit
                clock_tag = hms_add(base, t_rel).replace(":", "")
                np.savez_compressed(CORNER_DIR / f"{clock_tag}.npz", ids=ch_id, px=ch_full,
                                    seg=seg.name, t_rel=t_rel, bw=bw)
            x0, y0 = np.floor(allc.min(0)).astype(int); x1, y1 = np.ceil(allc.max(0)).astype(int)
            pad = int(0.15 * max(x1 - x0, y1 - y0)) + 5
            x0, y0 = max(0, x0 - pad), max(0, y0 - pad); x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
            roi = y[y0:y1, x0:x1]
            sat = float((roi >= 250).mean())
            bbox = (x0, y0, x1, y1)
            ndet += 1
        rows.append(dict(seg=seg.name, t_rel=t_rel, clock=hms_add(base, t_rel), bw=bw, chroma=chroma_std,
                         n_markers=nm, n_corners=nc, cx=cx, cy=cy, sat=sat, bbox=bbox))
        n += 1
        if n % 100 == 0:
            print(f"  {seg.name}: {n} samples, {ndet} with board, {time.time()-t0:.0f}s", flush=True)
    proc.wait(); th.join(timeout=2)
    print(f"{seg.name}: {n} samples, {ndet} with board, {time.time()-t0:.0f}s", flush=True)

# ---- cluster into placements ----
placements = []
cur = None
for r in rows:
    if r["n_markers"] == 0:
        if cur is not None and (r["t_rel"] - cur["t_end"] > 12 or r["seg"] != cur["seg"]):
            placements.append(cur); cur = None
        continue
    if cur is not None and r["seg"] == cur["seg"] and r["t_rel"] - cur["t_end"] <= 12 \
            and np.hypot(r["cx"] - cur["cx"], r["cy"] - cur["cy"]) < 60:
        cur["t_end"] = r["t_rel"]; cur["n"] += 1
        cur["max_markers"] = max(cur["max_markers"], r["n_markers"]); cur["max_corners"] = max(cur["max_corners"], r["n_corners"])
        cur["sat"] = max(cur["sat"], r["sat"]); cur["bw"] = cur["bw"] or r["bw"]
        cur["cx"] = (cur["cx"] * (cur["n"] - 1) + r["cx"]) / cur["n"]; cur["cy"] = (cur["cy"] * (cur["n"] - 1) + r["cy"]) / cur["n"]
    else:
        if cur is not None: placements.append(cur)
        cur = dict(seg=r["seg"], t_start=r["t_rel"], t_end=r["t_rel"], clock=r["clock"], n=1,
                   max_markers=r["n_markers"], max_corners=r["n_corners"], sat=r["sat"], bw=r["bw"], cx=r["cx"], cy=r["cy"])
if cur is not None: placements.append(cur)
# a lone 1-2 marker hit is a false positive (grass/wall texture), not a board
placements = [p for p in placements if p["max_markers"] >= 4]

# ---- report ----
csv_path = OUT / f"{cam}_placements_e{every}.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["idx", "clock", "dur_s", "samples", "max_markers", "max_corners", "bw_IR", "sat_frac",
                 "px_x", "px_y", "field_in_x", "field_in_y", "station", "dist_in", "station2", "dist2_in"])
    print(f"\n=== {cam}: {len(placements)} placements ===")
    print(f"{'#':>3} {'clock':>8} {'dur':>4} {'smp':>3} {'mk':>3} {'crn':>3} {'IR':>3} {'sat%':>5} {'px':>12} {'field in':>13}  station (dist)  alt (dist)")
    for i, p in enumerate(placements, 1):
        m = px_to_station((p["cx"], p["cy"]))
        fx = fy = st = d = st2 = d2 = ""
        if m:
            fx, fy, st, d, st2, d2 = m
        print(f"{i:>3} {p['clock']:>8} {p['t_end']-p['t_start']:>4.0f} {p['n']:>3} {p['max_markers']:>3} {p['max_corners']:>3} "
              f"{'IR' if p['bw'] else '':>3} {100*p['sat']:>5.1f} {p['cx']:>6.0f},{p['cy']:<5.0f} "
              f"{(f'{fx:6.0f},{fy:5.0f}' if m else ''):>13}  {st}({d:.0f})  {st2}({d2:.0f})" if m else
              f"{i:>3} {p['clock']:>8} {p['t_end']-p['t_start']:>4.0f} {p['n']:>3} {p['max_markers']:>3} {p['max_corners']:>3} "
              f"{'IR' if p['bw'] else '':>3} {100*p['sat']:>5.1f} {p['cx']:>6.0f},{p['cy']:<5.0f}")
        wr.writerow([i, p["clock"], round(p["t_end"] - p["t_start"], 1), p["n"], p["max_markers"], p["max_corners"],
                     int(p["bw"]), round(p["sat"], 3), round(p["cx"]), round(p["cy"]),
                     round(fx, 1) if m else "", round(fy, 1) if m else "", st, round(d, 1) if m else "", st2, round(d2, 1) if m else ""])
# station coverage
if calib is not None:
    hit = {}
    for p in placements:
        m = px_to_station((p["cx"], p["cy"]))
        if m and m[3] < 40:
            hit.setdefault(m[2], []).append(p["clock"])
    missing = [s[0] for s in stations if s[0] not in hit]
    print(f"\nstations with a matched placement (<40 in): {len(hit)}/{len(stations)}")
    print("MISSING (no placement mapped within 40 in): " + (", ".join(missing) if missing else "none"))
# IR / saturation summary
n_bw = sum(1 for r in rows if r["bw"]); print(f"\nIR/B&W samples: {n_bw}/{len(rows)}")
sat_bad = [p for p in placements if p["sat"] > 0.15]
print(f"placements with >15% saturated pixels in board box: {len(sat_bad)}")
print(f"csv -> {csv_path}   total {time.time()-t_start_all:.0f}s")
