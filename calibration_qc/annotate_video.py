# -*- coding: utf-8 -*-
"""Burn the operator's cone labels (station IDs) + PC-clock timestamp into a pano video.
Default = keyframe timelapse (one frame per ~2 s, played at 10 fps = ~20x); --full = every frame.
Usage: python annotate_video.py CH01 <cone_labels_CH01.json> [--start 15:00:00 --end 15:49:36] [--full]"""
import sys, json, re, subprocess, threading
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2

QC = Path(r"E:\calibration\qc"); SESSION = Path(r"E:\calibration\session_2026-09-18_13-54-34")
FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"
cam, labels_path = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
def opt(name, default):
    return args[args.index(name) + 1] if name in args else default
start = datetime.strptime(opt("--start", "15:00:00"), "%H:%M:%S").time()
end = datetime.strptime(opt("--end", "15:49:36"), "%H:%M:%S").time()
full = "--full" in args
fps_out = float(opt("--fps", "0"))        # --fps 1 = decode every frame, keep 1 per second (playback 10x)
if fps_out: full = True
OUT_W = 1920
labels = json.load(open(labels_path, encoding="utf-8"))
pts = [p for p in labels["points"] if p.get("station") and p["station"] != "NONE"]
FW, FH = labels.get("frame_size_upright", [7680, 2160])
sc = OUT_W / FW; OUT_H = int(round(FH * sc))

segs = []
for s in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
    a = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
    b = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
    if b.time() > start and a.time() < end:
        segs.append((s, a, b))
if not segs:
    sys.exit("no segments in range")
tag = f"{start.strftime('%H%M%S')}-{end.strftime('%H%M%S')}" + (f"_{fps_out:g}fps" if fps_out else ("_full" if full else "_timelapse"))
out_path = QC / f"annotated_{cam}_{tag}.mp4"
enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}",
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
        cv2.rectangle(fr, (0, 0), (330, 34), (0, 0, 0), -1)
        cv2.putText(fr, f"{cam} PC {clock}", (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        enc.stdin.write(fr.tobytes()); i += 1; n_out += 1
        if n_out % 200 == 0: print(f"  {n_out} frames, at {clock}", flush=True)
    dec.wait(); th.join(timeout=2)
enc.stdin.close(); enc.wait()
print(f"{n_out} frames -> {out_path} ({out_path.stat().st_size // (1024*1024)} MB)")
