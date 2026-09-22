# -*- coding: utf-8 -*-
r"""Check the operator's cone labels against the design lattice, and show where unlabelled stations
should be. For every labelled cone a local homography (field inches -> image px) is fitted from the
K nearest OTHER labelled cones; the residual of the cone itself flags a mislabel (or a misplaced cone).
Unlabelled stations are projected the same way (from their K nearest labelled cones). Optionally
renders a frame with labelled cones (yellow), predicted lattice points (cyan) and the cached board
outline (magenta) so a disputed placement can be judged against the lattice.
Usage: python cone_lattice_check.py CHxx [HH:MM:SS] [--session <dir|date>] [--around STATION[,..]] [--k 8]
Output: table on stdout; <qc>\frames\lattice_CHxx[_HHMMSS][_tag].jpg when a clock is given."""
import sys, re, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"; FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
cam = sys.argv[1]
rest = sys.argv[2:]
clock = rest.pop(0) if rest and re.match(r"\d\d:\d\d:\d\d$", rest[0]) else None
args, sess = qc_paths.pop_session(rest)
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
K = int(opt("--k", "8")); around = opt("--around")
PANO = cam in ("CH01", "CH02")

TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
lattice = {f"T{li}{si}": (x, y) for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)}
lattice.update({f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}": (x, y) for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)})

lp = qc_paths.cone_labels(QC, cam)
if lp is None:
    sys.exit(f"no cone labels for {cam}")
cones = qc_paths.load_cones(QC, cam, SESSION, space="upright")   # rescaled to this camera's real frame
bad = [s for s in cones if s not in lattice]
if bad:
    print("labels not in the lattice (ignored):", bad)
names = [s for s in cones if s in lattice]
F = np.array([lattice[s] for s in names], float); P = np.array([cones[s] for s in names], float)

def local_H(field_xy, exclude=None):
    d = np.linalg.norm(F - np.asarray(field_xy, float), axis=1)
    order = [i for i in np.argsort(d) if names[i] != exclude][:K]
    if len(order) < 4:
        return None
    H, _ = cv2.findHomography(F[order].reshape(-1, 1, 2), P[order].reshape(-1, 1, 2), 0)
    return H
def project(H, field_xy):
    return cv2.perspectiveTransform(np.array(field_xy, float).reshape(-1, 1, 2), H).reshape(2)

print(f"{cam} ({lp.name}): {len(names)} labelled cones, local homography from the {K} nearest others")
print(f"{'station':7s} {'field in':>10s} {'labelled px':>16s} {'predicted px':>16s} {'resid px':>8s}")
resid = {}
for s in sorted(names):
    H = local_H(lattice[s], exclude=s)
    if H is None:
        continue
    pred = project(H, lattice[s]); r = float(np.linalg.norm(pred - cones[s])); resid[s] = r
    flag = "   <-- check (mislabelled or misplaced cone?)" if r > 60 else ""
    print(f"{s:7s} {str(lattice[s]):>10s} {cones[s][0]:8.0f},{cones[s][1]:<6.0f} {pred[0]:8.0f},{pred[1]:<6.0f} {r:8.0f}{flag}")
print(f"median residual {np.median(list(resid.values())):.0f} px; > 60 px: {', '.join(s for s, r in resid.items() if r > 60) or 'none'}")
pred_unl = {}
for s in sorted(set(lattice) - set(names)):
    H = local_H(lattice[s])
    if H is not None:
        pred_unl[s] = project(H, lattice[s])
print("unlabelled stations, predicted px:", ", ".join(f"{s} ({p[0]:.0f},{p[1]:.0f})" for s, p in pred_unl.items()))

if clock is None:
    sys.exit(0)
# ---- render ----
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
raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{(t - seg_start).total_seconds():.2f}", "-i", str(seg), "-frames:v", "1",
                      "-vf", "transpose=2" if PANO else "null", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, check=True).stdout
W, H_ = (h, w) if PANO else (w, h)
img = np.frombuffer(raw, np.uint8).reshape(H_, W, 3).copy()
for s, c in cones.items():
    cv2.circle(img, tuple(int(v) for v in c), 12, (0, 255, 255), 3)
    cv2.putText(img, s, (int(c[0]) + 14, int(c[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)
for s, p in pred_unl.items():                                    # predicted lattice points of unlabelled stations
    x, y = int(p[0]), int(p[1])
    cv2.drawMarker(img, (x, y), (255, 255, 0), cv2.MARKER_CROSS, 40, 4)
    cv2.putText(img, s + "?", (x + 14, y + 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 0), 3)
board = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
OBJ = np.asarray(board.getChessboardCorners(), float).reshape(-1, 3)[:, :2] * 1000.0
OUTLINE = np.array([[0, 0], [720, 0], [720, 540], [0, 540]], float)
outline = None
for dt in (0, 1, -1):
    f = QC / "corners" / cam / f"{(t + timedelta(seconds=dt)).strftime('%H%M%S')}.npz"
    if f.exists():
        with np.load(f, allow_pickle=False) as z:
            ids = z["ids"].astype(int).reshape(-1); px = z["px"].astype(float).reshape(-1, 2)
        if PANO:
            px = np.stack([px[:, 1], (H_ - 1) - px[:, 0]], 1)
        Hm, _ = cv2.findHomography(OBJ[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
        if Hm is not None:
            outline = cv2.perspectiveTransform(OUTLINE.reshape(-1, 1, 2), Hm).reshape(-1, 2)
        break
if outline is not None:
    cv2.polylines(img, [outline.astype(np.int32).reshape(-1, 1, 2)], True, (255, 0, 255), 3)
    cv2.circle(img, tuple(int(v) for v in outline[3]), 14, (255, 0, 255), 4)
    allp = {**cones, **pred_unl}
    d = sorted((float(np.linalg.norm(allp[s] - outline[3])), s) for s in allp)
    print("board origin corner nearest to:", ", ".join(f"{s} {r:.0f}px{'?' if s in pred_unl else ''}" for r, s in d[:4]))
cv2.rectangle(img, (0, 0), (760, 44), (0, 0, 0), -1)
cv2.putText(img, f"{cam} {DATE} PC {clock}  yellow=labelled cone, cyan=lattice prediction", (8, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
if around:
    pts = np.array([({**cones, **pred_unl})[s.upper()] for s in around.split(",") if s.upper() in cones or s.upper() in pred_unl])
    x0, y0 = pts.min(0) - 500; x1, y1 = pts.max(0) + 500
else:
    x0, y0, x1, y1 = 0, 0, W, H_
x0, y0 = max(0, int(x0)), max(0, int(y0)); x1, y1 = min(W, int(x1)), min(H_, int(y1))
out = img[y0:y1, x0:x1]
if max(out.shape[:2]) > 1800:
    sc = 1800 / max(out.shape[:2]); out = cv2.resize(out, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
(QC / "frames").mkdir(exist_ok=True)
dst = QC / "frames" / f"lattice_{cam}_{clock.replace(':', '')}{('_' + around.replace(',', '-')) if around else ''}.jpg"
cv2.imwrite(str(dst), out, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("->", dst)
