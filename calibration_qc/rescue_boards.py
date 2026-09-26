# -*- coding: utf-8 -*-
r"""Rescue board placements that the ChArUco marker decoder missed (see board_detect.py for why).

For every timeline window x camera with fewer than --min-frames cached frames, the frames of the
window (every --step-th) are decoded, cropped around the expected board location (pano cameras: the
operator's cone label of that station, or the lattice prediction from the neighbouring cones; other
cameras: full frame) and run through board_detect.detect(): ChArUco first, chessboard-corner fallback.
Results are written next to the cached corners as corners/CHxx/<HHMMSS>_r<frame>.npz with a 'method'
field, so label_timeline.py picks them up unchanged.
Usage: python rescue_boards.py [--session <dir|date>] [--cams CH01,CH02,...] [--min-frames 3] [--step 5 | --keyframes] [--stations T35,V44]
"""
import sys, re, json, subprocess, threading, time
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths, board_detect as bd  # noqa: E402

FFMPEG = qc_paths.FFMPEG; FFPROBE = qc_paths.FFPROBE
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
CAMS = opt("--cams", "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
MIN_FRAMES = int(opt("--min-frames", "3")); STEP = int(opt("--step", "5"))
KEYFRAMES = "--keyframes" in args        # decode keyframes only (~2 s apart): 5-10x faster, enough for a settled board
if KEYFRAMES and "--step" not in args: STEP = 1
ONLY = set(s.upper() for s in opt("--stations", "").split(",") if s)
TL = QC / "placement_timeline.txt"
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
LATTICE = {f"T{li}{si}": (x, y) for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)}
LATTICE.update({f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}": (x, y) for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)})

# ---------------- timeline ----------------
def clk(s): return datetime.strptime(f"{DATE} {s}", "%Y-%m-%d %H:%M:%S")
wins = []
for ln in TL.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*(\d\d:\d\d:\d\d)-(\d\d:\d\d:\d\d)\s+(\S+)", ln)
    if m:
        a, b = clk(m.group(1)), clk(m.group(2)); wins.append([min(a, b), max(a, b), m.group(3).upper()])
merged = []
for w in sorted(wins, key=lambda w: w[0]):
    same = next((c for c in merged if c[2] == w[2] and w[0] <= c[1] + timedelta(seconds=1) and w[1] >= c[0] - timedelta(seconds=1)), None)
    if same: same[0], same[1] = min(same[0], w[0]), max(same[1], w[1])
    else: merged.append(list(w))
wins = merged

def cached_times(cam):
    out = []
    for p in (QC / "corners" / cam).glob("*.npz"):
        with np.load(p, allow_pickle=False) as z:
            seg = str(z["seg"]); t_rel = float(z["t_rel"])
        m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d\d)-(\d\d)-(\d\d)_to_", seg)
        out.append(datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S") + timedelta(seconds=t_rel))
    return sorted(out)

def cone_map(cam):
    """station -> STORED pixel, rescaled from whatever pixel space the label file declares."""
    return {k: v for k, v in qc_paths.load_cones(QC, cam, SESSION, space="stored").items() if k in LATTICE}
def expected_px(cones, station, K=8):
    if station in cones: return cones[station], "cone"
    names = list(cones); F = np.array([LATTICE[s] for s in names], float); P = np.array([cones[s] for s in names])
    d = np.linalg.norm(F - np.array(LATTICE[station], float), axis=1); order = np.argsort(d)[:K]
    if len(order) < 4: return None, None
    H, _ = cv2.findHomography(F[order].reshape(-1, 1, 2), P[order].reshape(-1, 1, 2), 0)
    if H is None: return None, None
    return cv2.perspectiveTransform(np.array(LATTICE[station], float).reshape(-1, 1, 2), H).reshape(2), "lattice"

def seg_for(cam, t):
    for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t <= b: return p, a
    return None, None

summary = []
for cam in CAMS:
    pano = cam in ("CH01", "CH02")
    cones = cone_map(cam) if pano else {}
    have = cached_times(cam)
    (QC / "corners" / cam).mkdir(parents=True, exist_ok=True)
    for a, b, st in wins:
        if ONLY and st not in ONLY: continue
        n_have = sum(a <= t <= b for t in have)
        if n_have >= MIN_FRAMES: continue
        seg, seg_start = seg_for(cam, a)
        if seg is None: continue
        centre, how = (expected_px(cones, st) if pano else (None, "full frame"))
        if pano and centre is None:
            summary.append((cam, st, "no location prior")); continue
        w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                                         "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
        ss = (a - seg_start).total_seconds(); dur = (b - a).total_seconds() + 0.5
        cmd = [FFMPEG, "-v", "info", "-nostats"] + (["-skip_frame", "nokey"] if KEYFRAMES else []) + \
              ["-ss", f"{ss:.2f}", "-i", str(seg), "-t", f"{dur:.2f}",
               "-vf", f"select=not(mod(n\\,{STEP})),showinfo", "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=w * h * 4)
        pts_list = []
        def rd():
            for line in proc.stderr:
                m = re.search(rb"pts_time:\s*([0-9.]+)", line)
                if m and b"showinfo" in line: pts_list.append(float(m.group(1)))
        th = threading.Thread(target=rd, daemon=True); th.start()
        n = saved = best = 0; notes = {}; t0 = time.time(); R = 800
        while True:
            buf = proc.stdout.read(w * h)
            if len(buf) < w * h: break
            for _ in range(200):
                if len(pts_list) > n: break
                time.sleep(0.005)
            t_rel = ss + (pts_list[n] if len(pts_list) > n else n * STEP / 15.0)
            gray = np.frombuffer(buf, np.uint8).reshape(h, w); n += 1
            if pano:
                cx, cy = int(centre[0]), int(centre[1])
                x0, y0 = max(0, cx - R), max(0, cy - R); x1, y1 = min(w, cx + R), min(h, cy + R)
                crop = gray[y0:y1, x0:x1]; off = np.array([x0, y0], float)
            else:
                crop = gray; off = np.array([0.0, 0.0])
            method, px, ids, note, mk_ids, mk_px, quad = bd.detect(crop)
            if method and (len(ids) >= 12 or method == "located"):
                clock_tag = (seg_start + timedelta(seconds=t_rel)).strftime("%H%M%S")
                extra = {} if mk_ids is None else dict(mk_ids=np.asarray(mk_ids, np.int32), mk_px=np.asarray(mk_px, float) + off)
                if quad is not None:
                    extra["quad"] = np.asarray(quad, float) + off        # board outline, kept even when the grid did not decode
                np.savez_compressed(QC / "corners" / cam / f"{clock_tag}_r{n:04d}.npz", ids=np.asarray(ids, np.int32), px=np.asarray(px, float).reshape(-1, 2) + off,
                                    seg=seg.name, t_rel=float(t_rel), bw=False, method=method, **extra)
                saved += 1; best = max(best, len(ids)); notes[method] = notes.get(method, 0) + 1
        proc.wait(); th.join(timeout=2)
        line = (cam, st, f"{a.strftime('%H:%M:%S')}-{b.strftime('%H:%M:%S')} had {n_have}, tried {n} frames, saved {saved} (best {best} corners) {notes} prior={how} {time.time()-t0:.0f}s")
        summary.append(line); print(*line, flush=True)
print("\n=== rescue summary ===")
for s in summary: print(*s)
