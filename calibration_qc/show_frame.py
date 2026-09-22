# -*- coding: utf-8 -*-
r"""Render one frame of a calibration-session camera at a PC clock, with the operator's cone labels and
the cached board outline (corners/CHxx/<HHMMSS>.npz -> homography -> outline, origin corner marked)
burnt in, so a placement can be eyeballed. Pano cameras are rendered upright.
Usage: python show_frame.py CHxx HH:MM:SS [--session <dir|YYYY-MM-DD>] [--around STATION[,STATION..]]
       [--crop x0,y0,x1,y1] [--scale 0.5]
  default crop = around the cached board outline if there is one, else the full frame at --scale.
Output: <qc>\frames\CHxx_HHMMSS[_tag].jpg  (reads closed source segments only)"""
import sys, re, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"; FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
cam, clock = sys.argv[1], sys.argv[2]
args, sess = qc_paths.pop_session(sys.argv[3:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
scale = float(opt("--scale", "0.5")); around = opt("--around"); crop = opt("--crop")
PANO = cam in ("CH01", "CH02")
board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
OBJ = np.asarray(board.getChessboardCorners(), float).reshape(-1, 3)[:, :2] * 1000.0
OUTLINE = np.array([[0, 0], [720, 0], [720, 540], [0, 540]], float); ORIGIN = 3   # (0,540) corner sits on the cone

t = datetime.strptime(f"{DATE} {clock}", "%Y-%m-%d %H:%M:%S")
seg = None
for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
    a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
    b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
    if a <= t <= b:
        seg, seg_start = p, a
if seg is None:
    sys.exit(f"no closed {cam} segment covers {clock}")
w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                 "stream=width,height", "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
vf = "transpose=2" if PANO else "null"
raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{(t - seg_start).total_seconds():.2f}", "-i", str(seg), "-frames:v", "1",
                      "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, check=True).stdout
W, H = (h, w) if PANO else (w, h)
img = np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy()

def to_upright(px):                       # cached corners are in the stored (rotated) frame for the panos
    return qc_paths.stored_to_upright(px, SESSION, cam)

cones = qc_paths.load_cones(QC, cam, SESSION, space="upright")   # rescaled to this camera's real frame
for name, c in cones.items():
    cv2.circle(img, tuple(int(v) for v in c), 12, (0, 255, 255), 3)
    cv2.putText(img, name, (int(c[0]) + 14, int(c[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)

# cached board outline at this clock (+-1 s)
outline = None; tag = ""
for dt in (0, 1, -1):
    f = QC / "corners" / cam / f"{(t + timedelta(seconds=dt)).strftime('%H%M%S')}.npz"
    if f.exists():
        with np.load(f, allow_pickle=False) as z:
            ids = z["ids"].astype(int).reshape(-1); px = to_upright(z["px"].astype(float).reshape(-1, 2))
        if len(ids) >= 8:
            Hm, _ = cv2.findHomography(OBJ[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
            if Hm is not None:
                outline = cv2.perspectiveTransform(OUTLINE.reshape(-1, 1, 2), Hm).reshape(-1, 2)
                tag = f"{len(ids)} corners, npz {f.name}"
                for p in px:
                    cv2.circle(img, tuple(int(v) for v in p), 3, (0, 0, 255), -1)
        break
if outline is not None:
    cv2.polylines(img, [outline.astype(np.int32).reshape(-1, 1, 2)], True, (255, 0, 255), 3)
    o = outline[ORIGIN]; cv2.circle(img, tuple(int(v) for v in o), 14, (255, 0, 255), 4)
    if cones:
        names = list(cones); d = np.linalg.norm(np.array([cones[n] for n in names]) - o, axis=1); order = np.argsort(d)[:3]
        print("origin corner at", o.round(), "nearest labelled cones:", ", ".join(f"{names[i]} {d[i]:.0f}px" for i in order))
cv2.rectangle(img, (0, 0), (900, 44), (0, 0, 0), -1)
cv2.putText(img, f"{cam} PC {clock}  {tag}", (8, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

# crop
if crop:
    x0, y0, x1, y1 = [int(v) for v in crop.split(",")]
elif around:
    pts = np.array([cones[s.upper()] for s in around.split(",") if s.upper() in cones])
    if not len(pts):
        sys.exit("none of the --around stations is a labelled cone in " + cam)
    x0, y0 = pts.min(0) - 700; x1, y1 = pts.max(0) + 700
elif outline is not None:
    sz = max(np.ptp(outline[:, 0]), np.ptp(outline[:, 1]))
    x0, y0 = outline.min(0) - max(2.5 * sz, 500); x1, y1 = outline.max(0) + max(2.5 * sz, 500)
else:
    x0, y0, x1, y1 = 0, 0, W, H
x0, y0 = max(0, int(x0)), max(0, int(y0)); x1, y1 = min(W, int(x1)), min(H, int(y1))
out = img[y0:y1, x0:x1]
if crop is None and around is None and outline is None:
    out = cv2.resize(out, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
elif max(out.shape[:2]) > 1800:
    s = 1800 / max(out.shape[:2]); out = cv2.resize(out, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
(QC / "frames").mkdir(exist_ok=True)
suffix = ("_" + around.replace(",", "-")) if around else ""
dst = QC / "frames" / f"{cam}_{clock.replace(':', '')}{suffix}.jpg"
cv2.imwrite(str(dst), out, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("->", dst, f"crop {x0},{y0}-{x1},{y1} of {W}x{H}")
