# -*- coding: utf-8 -*-
"""Numbered cone overlays for operator labelling: 4 full-res tiles per pano camera + a guess list.
Usage: python cone_tiles.py CH01 15:47:30"""
import sys, csv, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2

QC = Path(r"E:\calibration\qc"); SESSION = Path(r"E:\calibration\session_2026-09-18_13-54-34")
FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"
cam, clock = sys.argv[1], sys.argv[2]
t = datetime.strptime(clock, "%H:%M:%S")
seg = off = None
for s in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
    a = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
    b = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
    if a.time() <= t.time() <= b.time(): seg, off = s, (datetime.combine(a.date(), t.time()) - a).total_seconds()
w, h = 2160, 7680
buf = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{off:.1f}", "-i", str(seg), "-frames:v", "1", "-f", "rawvideo",
                      "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
up = cv2.rotate(np.frombuffer(buf, np.uint8).reshape(h, w, 3), cv2.ROTATE_90_COUNTERCLOCKWISE)   # 7680 x 2160 upright
cones = list(csv.DictReader(open(QC / f"cones_{cam}.csv", encoding="utf-8")))
for c in cones:
    x, y = int(float(c["upright_x"])), int(float(c["upright_y"]))
    cv2.circle(up, (x, y), 18, (0, 0, 0), 4); cv2.circle(up, (x, y), 18, (255, 255, 255), 2)
    label = c["idx"]
    cv2.putText(up, label, (x + 22, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 9)
    cv2.putText(up, label, (x + 22, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 255, 255), 3)
W = up.shape[1]; tile_w = W // 4 + 200
for k in range(4):
    x0 = max(0, k * (W // 4) - 100); x1 = min(W, x0 + tile_w)
    tile = up[:, x0:x1]
    cv2.putText(tile, f"{cam} tile {k+1}/4  (x {x0}-{x1})", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 0), 10)
    cv2.putText(tile, f"{cam} tile {k+1}/4  (x {x0}-{x1})", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 3)
    cv2.imwrite(str(QC / f"cones_{cam}_tile{k+1}.jpg"), tile, [cv2.IMWRITE_JPEG_QUALITY, 88])
with open(QC / f"cones_{cam}_labels.txt", "w", encoding="utf-8") as f:
    f.write(f"# {cam} cones at {clock}: one line per numbered cone; replace the guess with the true station ID (T11..T75, V.., F..), or NONE if it is not a cone\n")
    for c in cones:
        f.write(f"{c['idx']}: {c['station'] or '?'}    # {c['colour']}\n")
print(f"{cam}: {len(cones)} numbered cones -> 4 tiles + cones_{cam}_labels.txt")
