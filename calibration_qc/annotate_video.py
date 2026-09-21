# -*- coding: utf-8 -*-
"""Burn the operator's cone labels (station IDs) + PC-clock timestamp into a pano video.
Default = keyframe timelapse (one frame per ~2 s, played at 10 fps = ~20x); --full = every frame.
Usage: python annotate_video.py CH01 <cone_labels_CH01.json> [--session <dir|YYYY-MM-DD>]
       [--start HH:MM:SS --end HH:MM:SS] [--full | --fps N]
Default range = the camera's closed segments of the session (first start .. last end)."""
import sys, json, re, subprocess, threading
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"
cam, labels_path = sys.argv[1], sys.argv[2]
args, sess = qc_paths.pop_session(sys.argv[3:])
SESSION, QC = qc_paths.resolve(sess)
def opt(name, default):
    return args[args.index(name) + 1] if name in args else default
all_segs = sorted(SESSION.glob(f"{cam}_*_to_*.mp4"))
if not all_segs:
    sys.exit(f"no closed {cam} segments in {SESSION}")
seg_a = lambda s: datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
seg_b = lambda s: datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
start = datetime.strptime(opt("--start", seg_a(all_segs[0]).strftime("%H:%M:%S")), "%H:%M:%S").time()
end = datetime.strptime(opt("--end", seg_b(all_segs[-1]).strftime("%H:%M:%S")), "%H:%M:%S").time()
full = "--full" in args
fps_out = float(opt("--fps", "0"))        # --fps 1 = decode every frame, keep 1 per second (playback 10x)
if fps_out: full = True
boards = "--boards" in args               # overlay the cached board detections (corners/CHxx/*.npz) with their station label
only_boards = "--only-boards" in args     # ... and keep ONLY the frames that have one (a short review reel)
if only_boards: boards = True
still = opt("--still", None)              # --still HH:MM:SS: write one annotated frame as JPG (QC/frames) instead of a video
if still:
    start = datetime.strptime(still, "%H:%M:%S").time()
    end = (datetime.combine(datetime(2000, 1, 1), start) + timedelta(seconds=1)).time()
    full = True
OUT_W = 1920
labels = json.load(open(labels_path, encoding="utf-8"))
pts = [p for p in labels["points"] if p.get("station") and p["station"] != "NONE"]
FW, FH = labels.get("frame_size_upright", [7680, 2160])
sc = OUT_W / FW; OUT_H = int(round(FH * sc))

segs = []
for s in all_segs:
    a, b = seg_a(s), seg_b(s)
    if b.time() > start and a.time() < end:
        segs.append((s, a, b))
if not segs:
    sys.exit("no segments in range")
tag = f"{start.strftime('%H%M%S')}-{end.strftime('%H%M%S')}" + (f"_{fps_out:g}fps" if fps_out else ("_full" if full else "_timelapse")) + ("_onlyboards" if only_boards else ("_boards" if boards else ""))
out_path = QC / f"annotated_{cam}_{tag}.mp4"

# ---- cached board detections -> outline (upright, scaled) + station label per detection time ----
dets = []                                  # (t_seconds_since_midnight, outline(4,2) scaled upright px, label, colour)
if boards:
    import csv
    station_of = {}
    lf = QC / "labelled_frames.csv"
    if lf.exists():
        with open(lf, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["cam"] == cam:
                    station_of[r["file"]] = (r["station"], r.get("settled_run", ""))
    board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
    OBJ = np.asarray(board.getChessboardCorners(), float).reshape(-1, 3)[:, :2]
    OUTLINE = np.array([[0, 0], [0.72, 0], [0.72, 0.54], [0, 0.54]], float)
    for p in sorted((QC / "corners" / cam).glob("*.npz")):
        with np.load(p, allow_pickle=False) as z:
            ids = z["ids"].astype(int).reshape(-1); px = z["px"].astype(float).reshape(-1, 2); seg_name = str(z["seg"]); t_rel = float(z["t_rel"])
            method = str(z["method"]) if "method" in z.files else "charuco"
            quad = z["quad"].astype(float).reshape(-1, 2) if "quad" in z.files else None
        a0 = datetime.strptime(seg_name.split("_")[1] + " " + seg_name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        t_abs = (a0 - a0.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() + t_rel
        if len(ids) >= 8:
            Hm, _ = cv2.findHomography(OBJ[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
            if Hm is None:
                continue
            ol = cv2.perspectiveTransform(OUTLINE.reshape(-1, 1, 2), Hm).reshape(-1, 2)
        elif quad is not None and len(quad) == 4:
            ol = quad                                    # board located, grid not decoded
        else:
            continue
        up = np.stack([ol[:, 1], (FH - 1) - ol[:, 0]], 1) if cam in ("CH01", "CH02") else ol      # stored -> upright
        st, run = station_of.get(p.name, ("?", ""))
        if len(ids) < 8:
            label = f"{st} LOCATED (grid not decoded)"; col = (0, 128, 255)                        # orange
        else:
            label = f"{st} {len(ids)}c {method[:5]}" + ("" if run else " (unsettled)" if st != "?" else "")
            col = (255, 0, 255) if method == "charuco" else (255, 255, 0)
            if st == "?":
                col = (0, 255, 255)
        dets.append((t_abs, up * sc, label, col))
    dets.sort(key=lambda d: d[0]); det_t = np.array([d[0] for d in dets])
    print(f"{len(dets)} cached detections to overlay ({sum(1 for d in dets if d[2].startswith('?'))} unlabelled)")
enc = None if still else subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}",
                        "-r", "10" if fps_out else ("20" if full else "10"), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-pix_fmt", "yuv420p", str(out_path)], stdin=subprocess.PIPE)

overlay = np.zeros((OUT_H, OUT_W, 3), np.uint8); mask = np.zeros((OUT_H, OUT_W), np.uint8)
for p in pts:
    x, y = int(p["x"] * sc), int(p["y"] * sc)
    cv2.circle(overlay, (x, y), 7, (0, 255, 255), 2); cv2.circle(mask, (x, y), 7, 255, 2)
    (tw, th), _ = cv2.getTextSize(p["station"], cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.rectangle(overlay, (x + 8, y - th - 6), (x + 8 + tw + 4, y + 2), (0, 0, 0), -1); cv2.rectangle(mask, (x + 8, y - th - 6), (x + 8 + tw + 4, y + 2), 255, -1)
    cv2.putText(overlay, p["station"], (x + 10, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
m3 = mask[:, :, None] > 0
n_out = 0
for seg, a, b in segs:
    ss = max(0.0, (datetime.combine(a.date(), start) - a).total_seconds())
    to = (datetime.combine(a.date(), end) - a).total_seconds()
    dec_args = [FFMPEG, "-v", "info", "-nostats"] + ([] if full else ["-skip_frame", "nokey"]) + \
               ["-ss", f"{ss:.1f}", "-i", str(seg), "-t", f"{max(0, to - ss):.1f}",
                "-vf", (f"fps={fps_out:g}," if fps_out else "") + f"transpose=2,scale={OUT_W}:{OUT_H},showinfo", "-vsync", "0",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    dec = subprocess.Popen(dec_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=OUT_W * OUT_H * 3 * 8)
    times = []
    def rd():
        for line in dec.stderr:
            m = re.search(rb"pts_time:\s*([0-9.]+)", line)
            if m and b"showinfo" in line: times.append(float(m.group(1)))
    th = threading.Thread(target=rd, daemon=True); th.start()
    i = 0
    while True:
        buf = dec.stdout.read(OUT_W * OUT_H * 3)
        if len(buf) < OUT_W * OUT_H * 3: break
        for _ in range(200):
            if len(times) > i: break
            threading.Event().wait(0.005)
        t_rel = times[i] if len(times) > i else i * 2.0
        clock = (a + timedelta(seconds=ss + t_rel)).strftime("%H:%M:%S")   # -ss resets pts to 0
        fr = np.frombuffer(buf, np.uint8).reshape(OUT_H, OUT_W, 3).copy()
        fr[m3.repeat(3, axis=2)] = overlay[m3.repeat(3, axis=2)]
        if boards and len(dets):
            t_abs = (a - a.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() + ss + t_rel
            lo = np.searchsorted(det_t, t_abs - 1.1); hi = np.searchsorted(det_t, t_abs + 1.1)
            if only_boards and hi <= lo:
                i += 1; continue                                   # no detection at this frame - skip it
            drawn = set()
            for k in range(lo, hi):
                _, ol, label, col = dets[k]
                if label in drawn:
                    continue
                drawn.add(label)
                cv2.polylines(fr, [ol.astype(np.int32).reshape(-1, 1, 2)], True, col, 3)
                cv2.circle(fr, tuple(int(v) for v in ol[3]), 7, col, 3)                      # (0,540) corner = design origin
                tx, ty = int(ol[:, 0].min()), int(ol[:, 1].min()) - 8
                (tw, t_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)   # not 'th': that is the reader thread
                ty = max(t_h + 4, ty)
                cv2.rectangle(fr, (tx - 2, ty - t_h - 4), (tx + tw + 4, ty + 4), (0, 0, 0), -1)
                cv2.putText(fr, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        cv2.rectangle(fr, (0, 0), (520, 34), (0, 0, 0), -1)
        cv2.putText(fr, f"{cam} {a.strftime('%Y-%m-%d')} PC {clock}", (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        if still:
            (QC / "frames").mkdir(exist_ok=True)
            dst = QC / "frames" / f"still_{cam}_{clock.replace(':', '')}{'_boards' if boards else ''}.jpg"
            cv2.imwrite(str(dst), fr, [cv2.IMWRITE_JPEG_QUALITY, 92]); print("->", dst)
            dec.kill(); sys.exit(0)
        enc.stdin.write(fr.tobytes()); i += 1; n_out += 1
        if n_out % 200 == 0: print(f"  {n_out} frames, at {clock}", flush=True)
    dec.wait(); th.join(timeout=2)
enc.stdin.close(); enc.wait()
print(f"{n_out} frames -> {out_path} ({out_path.stat().st_size // (1024*1024)} MB)")
