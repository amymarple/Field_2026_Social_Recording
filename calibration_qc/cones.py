# -*- coding: utf-8 -*-
"""Detect the station cones (static landmarks) in one clean frame per camera and assign them to
the designed stations. Cones are the primary identity anchor: a board placement is labelled by
the nearest cone in the same image, not by a ~10 in map guess.
Usage: python cones.py CH01 15:47:30 [--overlay]"""
import sys, csv, re, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
QC = qc_paths.QC_ROOT; SESSION = qc_paths.DEFAULT_SESSION
FFMPEG = qc_paths.FFMPEG; FFPROBE = qc_paths.FFPROBE
cam, clock = sys.argv[1], sys.argv[2]
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
stations = {}                                   # cone = station origin (the tick), no board offset
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1): stations[f"T{li}{si}"] = np.array([x, y], float)
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1): stations[f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}"] = np.array([x, y], float)
names = list(stations); sxy = np.array([stations[n] for n in names])

def seg_for(t):
    for s in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a.time() <= t.time() <= b.time(): return s, (datetime.combine(a.date(), t.time()) - a).total_seconds()
    raise SystemExit("no segment covers that time")

t = datetime.strptime(clock, "%H:%M:%S"); seg, off = seg_for(t)
w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height", "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
buf = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{off:.1f}", "-i", str(seg), "-frames:v", "1", "-f", "rawvideo",
                      "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
pano = cam in ("CH01", "CH02")
up = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE) if pano else img.copy()   # work upright
H, W = up.shape[:2]
hsv = cv2.cvtColor(up, cv2.COLOR_BGR2HSV); Hh, S, V = cv2.split(hsv)
sat = S.astype(int); val = V.astype(int); hue = Hh.astype(int)
colours = {  # hue ranges (OpenCV 0-180); cones are far more saturated/bright than grass
    "red":    ((hue <= 8) | (hue >= 168)) & (sat > 120) & (val > 90),
    "orange": (hue > 8) & (hue <= 20) & (sat > 130) & (val > 120),
    "yellow": (hue > 20) & (hue <= 36) & (sat > 120) & (val > 150),
    "lime":   (hue > 36) & (hue <= 58) & (sat > 140) & (val > 170),
    "blue":   (hue > 96) & (hue <= 128) & (sat > 110) & (val > 90),
}
# paddock interior (upright full-res coords): excludes the orange fence / netting outside the wall
if pano:
    x0p, x1p, y0p = int(0.215 * W), int(0.915 * W), int(0.13 * H)
else:
    x0p, x1p, y0p = int(0.02 * W), int(0.98 * W), int(0.15 * H)
blobs = []
for cname, m in colours.items():
    mask = m.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    for k in range(1, n):
        x, y, bw, bh, area = stats[k]
        if area < 150 or area > 40000 or bw > 400 or bh > 400: continue
        if x + bw / 2 < x0p or x + bw / 2 > x1p or y + bh / 2 < y0p: continue
        if bw / max(bh, 1) > 4 or bh / max(bw, 1) > 4: continue
        # ground contact = bottom-centre of the blob in the upright view (base edge nearest the camera)
        ys, xs = np.where(lab[y:y+bh, x:x+bw] == k)
        bottom = y + ys.max(); cx = x + xs[ys >= ys.max() - max(2, bh // 6)].mean()
        blobs.append(dict(colour=cname, area=int(area), cx=float(cx), cy=float(bottom), ctr=(float(cent[k][0]), float(cent[k][1])), bw=int(bw), bh=int(bh)))
# merge duplicates (same cone split across colour masks)
blobs.sort(key=lambda b: -b["area"]); keep = []
for b in blobs:
    if all(np.hypot(b["cx"] - k["cx"], b["cy"] - k["cy"]) > 40 for k in keep): keep.append(b)
blobs = keep
colour_counts = ", ".join("%s:%d" % (c, sum(1 for b in blobs if b["colour"] == c)) for c in colours)
print(f"{cam} {clock}: {len(blobs)} cone candidates ({colour_counts})")

def to_stored(px):   # upright -> stored pixel coords (pano only)
    return np.array([W_s - 1 - px[1], px[0]]) if pano else np.array(px)
W_s = w
assign = {}
maps = np.load(QC / "refined_pano_maps.npz") if pano else None
if pano:
    def apply_poly(P, p):
        x, y = p[:, 0] / 1000.0, p[:, 1] / 1000.0
        F = np.stack([np.ones_like(x), x, y, x*x, x*y, y*y], 1); return np.stack([F @ P[0], F @ P[1]], 1)
    P = maps[cam]
    for it in range(3):
        pts = np.array([to_stored((b["cx"], b["cy"])) for b in blobs])
        pos = apply_poly(P, pts)
        D = np.linalg.norm(pos[:, None, :] - sxy[None, :, :], axis=2)
        r, c = linear_sum_assignment(D)
        assign = {int(i): (names[j], float(D[i, j])) for i, j in zip(r, c) if D[i, j] <= (40 if it == 0 else 25)}
        good = [i for i, (n, d) in assign.items() if d <= (25 if it == 0 else 15)]
        if len(good) >= 12:
            src = pts[good]; dst = np.array([stations[assign[i][0]] for i in good])
            x, y = src[:, 0] / 1000.0, src[:, 1] / 1000.0
            F = np.stack([np.ones_like(x), x, y, x*x, x*y, y*y], 1)
            P = np.stack([np.linalg.lstsq(F, dst[:, 0], rcond=None)[0], np.linalg.lstsq(F, dst[:, 1], rcond=None)[0]])
            res = np.linalg.norm(apply_poly(P, src) - dst, axis=1)
            print(f"  iter {it}: {len(assign)} assigned, refit on {len(good)} anchors, rms {np.sqrt((res**2).mean()):.1f} in, max {res.max():.1f} in")
    np.savez(QC / f"cone_map_{cam}.npz", P=P)
    missing = [n for n in names if n not in {v[0] for v in assign.values()}]
    print(f"  stations matched: {len(assign)}/59; missing: {', '.join(missing)}")

with open(QC / f"cones_{cam}.csv", "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f); wr.writerow(["idx", "colour", "area", "upright_x", "upright_y", "stored_x", "stored_y", "station", "dist_in"])
    for i, b in enumerate(blobs):
        s = to_stored((b["cx"], b["cy"])); st, d = assign.get(i, ("", ""))
        wr.writerow([i, b["colour"], b["area"], round(b["cx"], 1), round(b["cy"], 1), round(float(s[0]), 1), round(float(s[1]), 1), st, round(d, 1) if d != "" else ""])

if "--overlay" in sys.argv:
    ov = up.copy()
    for i, b in enumerate(blobs):
        st = assign.get(i, ("?", 0))[0]
        cv2.circle(ov, (int(b["cx"]), int(b["cy"])), 14, (0, 0, 0), 3)
        cv2.circle(ov, (int(b["cx"]), int(b["cy"])), 14, (255, 255, 255), 1)
        cv2.putText(ov, st, (int(b["cx"]) + 16, int(b["cy"]) + 8), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 6)
        cv2.putText(ov, st, (int(b["cx"]) + 16, int(b["cy"]) + 8), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 2)
    scale = 3840 / W
    cv2.imwrite(str(QC / f"cones_{cam}_overlay.jpg"), cv2.resize(ov, None, fx=scale, fy=scale), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"  overlay -> cones_{cam}_overlay.jpg")
