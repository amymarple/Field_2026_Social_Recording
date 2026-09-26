# -*- coding: utf-8 -*-
"""Full-frame-rate census of the hand-held intrinsics sweeps: usable poses + image coverage.
Usage: python sweep_census.py CH03 2420 2510   (segment-relative seconds in the 15:00 segment)"""
import sys, subprocess, numpy as np, cv2
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
FFMPEG = qc_paths.FFMPEG
SESSION = qc_paths.DEFAULT_SESSION
cam, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
seg = sorted(SESSION.glob(f"{cam}_*15-00-0*_to_*.mp4"))[0]
w, h = 4512, 2512
dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, dic)
dp = cv2.aruco.DetectorParameters(); dp.minMarkerPerimeterRate = 0.005; dp.perspectiveRemovePixelPerCell = 8; dp.errorCorrectionRate = 0.8
det = cv2.aruco.CharucoDetector(board, detectorParams=dp)
cmd = [FFMPEG, "-v", "error", "-ss", f"{t0}", "-t", f"{t1 - t0}", "-i", str(seg), "-vf", "fps=5",
       "-f", "rawvideo", "-pix_fmt", "gray", "-"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=w * h * 4)
frames = []; i = 0
while True:
    buf = proc.stdout.read(w * h)
    if len(buf) < w * h: break
    g = np.frombuffer(buf, np.uint8).reshape(h, w)
    cc, ci, mc, mi = det.detectBoard(g)
    nc = 0 if ci is None else len(ci)
    if nc >= 20:
        pts = cc.reshape(-1, 2); c = pts.mean(0); x0, y0 = pts.min(0); x1, y1 = pts.max(0)
        frames.append((t0 + i / 5.0, nc, c[0], c[1], x1 - x0, y1 - y0))
    i += 1
proc.wait()
print(f"{cam} window {t0:.0f}-{t1:.0f}s: {i} frames at 5 fps, {len(frames)} with >=20 corners")
# distinct poses: new pose when the centre moves > 150 px or the bbox size changes > 15 %
poses = []
for f in frames:
    if poses:
        p = poses[-1]
        if np.hypot(f[2] - p[2], f[3] - p[3]) < 150 and abs(f[4] - p[4]) / max(p[4], 1) < 0.15:
            continue
    poses.append(f)
print(f"distinct poses (>=20 corners): {len(poses)}")
# image coverage: 4x3 grid cells touched by pose centres
cells = set((int(p[2] / (w / 4)), int(p[3] / (h / 3))) for p in poses)
grid = [["." for _ in range(4)] for _ in range(3)]
for cx, cy in cells: grid[cy][cx] = "X"
print("frame coverage (4x3 cells, X = a pose centred there):")
for row in grid: print("   " + " ".join(row))
xs = [p[2] for p in poses]; ys = [p[3] for p in poses]
if poses:
    print(f"pose-centre span: x {min(xs):.0f}-{max(xs):.0f} of {w}, y {min(ys):.0f}-{max(ys):.0f} of {h}; board width {min(p[4] for p in poses):.0f}-{max(p[4] for p in poses):.0f} px")
