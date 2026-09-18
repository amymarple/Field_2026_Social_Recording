# -*- coding: utf-8 -*-
"""Per-camera colour/IR + global saturation timeline over the calibration session (1 frame / 2 min)."""
import sys, re, subprocess, csv
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

SESSION = Path(r"E:\calibration\session_2026-09-18_13-54-34")
FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"
FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
OUT = Path(r"E:\calibration\qc\ir_timeline.csv")
cams = sys.argv[1:] or ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06", "CH07", "CH08"]
STEP = 120

def probe(p):
    o = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height:format=duration", "-of", "csv=p=0", str(p)]).decode().split()
    w, h = [int(v) for v in o[0].split(",")[:2]]
    dur = float(o[-1].split(",")[-1])
    return w, h, dur

rows = []
for cam in cams:
    for seg in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        w, h, dur = probe(seg)
        m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", seg.name)
        base = datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S")
        t = 0.0
        while t < dur - 1:
            buf = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.0f}", "-i", str(seg), "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], capture_output=True).stdout
            if len(buf) >= w * h * 3 // 2:
                y = np.frombuffer(buf, np.uint8, count=w * h)
                uv = np.frombuffer(buf, np.uint8, offset=w * h, count=(w * h) // 2).reshape(2, -1).astype(np.int16)
                chroma = float(max(np.abs(uv[0] - 128).mean(), np.abs(uv[1] - 128).mean()))
                sat = float((y >= 250).mean()); mean_y = float(y.mean())
                rows.append([cam, (base + timedelta(seconds=t)).strftime("%H:%M:%S"), round(chroma, 2),
                             "IR" if chroma < 2.0 else "color", round(100 * sat, 2), round(mean_y, 1)])
            t += STEP
    print(f"{cam} done", flush=True)

with open(OUT, "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["cam", "clock", "chroma", "mode", "sat_pct", "mean_y"]); wr.writerows(rows)
# compact summary per camera: mode runs
for cam in cams:
    r = [x for x in rows if x[0] == cam]
    if not r: continue
    runs = []; cur = None
    for x in r:
        if cur and cur[0] == x[3]: cur[2] = x[1]
        else:
            if cur: runs.append(cur)
            cur = [x[3], x[1], x[1]]
    if cur: runs.append(cur)
    sat_max = max(x[4] for x in r)
    print(f"{cam}: " + "; ".join(f"{a} {b}-{c}" for a, b, c in runs) + f"   max global sat {sat_max:.1f}%")
print(f"csv -> {OUT}")
