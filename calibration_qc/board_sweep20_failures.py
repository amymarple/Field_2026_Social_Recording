# -*- coding: utf-8 -*-
r"""Review video of the sweep frames a camera did NOT decode (board_sweep20.py + board_sweep20_rescue.py), for the
operator to look at: where the sweep camera's simultaneous pose says the board is, and what the camera saw there.

Per frame (6 fps, so each lasts a sixth of a second): left = the camera's native pixels around the predicted
board (magenta = predicted outline from the sweep camera's pose, clock offset applied); right = the same region
remapped into a pinhole camera pointed at the predicted board - the panorama's stretching is removed, the board's own tilt is NOT (not a frontal warp) - so blur, occlusion and squashing are
easy to tell apart. Label: why the frame is out - "edge-on" (> 65 deg to this camera), "past the canvas edge"
(> 20 % of the board outside the frame), or "in view, not decoded"; tilt, share inside, time.

Usage: python board_sweep20_failures.py --window CH03 --main CH03 --cam CH01 --offset 0.52 [--ir-shift-main 0.6,-5.6] [--in-view]
Output: <qc>\sweep20\<WINDOW>_<CAM>_failures.mp4 (--in-view: only the "in view, not decoded" frames, ..._failures_inview.mp4)
"""
import sys, json, subprocess
from pathlib import Path
import numpy as np, cv2
from scipy.spatial.transform import Rotation as Rot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, board_detect as bd                    # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
WINDOW, MAIN, CAM = opt("--window"), opt("--main"), opt("--cam")
OFFSET = float(opt("--offset", "0"))
IR_MAIN = np.array([float(v) for v in opt("--ir-shift-main", "0,0").split(",")])
SESSION, _ = qc_paths.resolve(opt("--session"))
SW = qc_paths.QC_ROOT / "sweep20"
cams = pm.load(correct=False); c = cams[CAM]
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
OUTLINE3 = np.c_[bd.PAPER_MM - bd.OBJ_MM.mean(0), np.zeros(4)]
PANO = CAM in ("CH01", "CH02")
IN_VIEW = "--in-view" in args
OUT = SW / f"{WINDOW}_{CAM}_failures{'_inview' if IN_VIEW else ''}.mp4"


def regular_times(t_abs):
    i = np.arange(len(t_abs)); b = np.polyfit(i, t_abs, 1)[0]; r = t_abs - b * i
    med = np.array([np.median(r[max(0, j - 200):j + 201]) for j in range(0, len(r), 20)])
    return np.interp(i, np.arange(0, len(r), 20), med) + b * i


def board_pose(cam, ids, px):
    cc = cams[cam]; b = pm.fm.bearings(cc.model, cc.intr, px); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = OBJ3[ids].astype(np.float64)
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    if not n:
        return None
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    Rc = Q.T @ cv2.Rodrigues(rv)[0]; Xc = Q.T @ tv.ravel()
    return cc.R.T @ Rc, cc.R.T @ (Xc - cc.tvec)


def load(cam, rescue=False):
    p = SW / (f"{WINDOW}_{cam}_rescue.json" if rescue else f"{WINDOW}_{cam}.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


dm = load(MAIN); tm = regular_times(np.array([f[2] for f in dm["frames"]]))
poses = [(t, board_pose(MAIN, np.asarray(f[4], int), np.asarray(f[5], float) + IR_MAIN)) for f, t in zip(dm["frames"], tm) if f[3] >= 20]
poses = [p for p in poses if p[1] is not None]
TP = np.array([p[0] for p in poses])
dc = load(CAM); tc = regular_times(np.array([f[2] for f in dc["frames"]])) + OFFSET
rescued = {r[0] for r in (load(CAM, True) or {"frames": []})["frames"]}
Wd, Hd = (7680, 2160) if PANO else qc_paths.upright_size(SESSION, CAM)
fail = {}
for f, t in zip(dc["frames"], tc):
    if f[3] >= 12 or f[0] in rescued:
        continue
    j = int(np.argmin(np.abs(TP - t)))
    if abs(TP[j] - t) > 0.05:
        continue
    R, X = poses[j][1]
    los = X - c.centre; los /= np.linalg.norm(los)
    tilt = float(np.degrees(np.arccos(abs(los @ R[:, 2]))))
    Pc = (OBJ3 @ R.T + X) @ c.R.T + c.tvec; Oc = (OUTLINE3 @ R.T + X) @ c.R.T + c.tvec
    pr = pm.fm.project(c.model, c.intr, Pc)
    inside = float(((pr[:, 0] >= 0) & (pr[:, 0] < Wd) & (pr[:, 1] >= 0) & (pr[:, 1] < Hd)).mean())
    why = "edge-on" if tilt > 65 else ("past the canvas edge" if inside < 0.8 else "in view, not decoded")
    if IN_VIEW and why != "in view, not decoded":
        continue
    fail[f[0]] = (t, tilt, inside, why, Pc, Oc)
print(f"{WINDOW}/{CAM}: {len(fail)} undecoded frames with a simultaneous {MAIN} pose", flush=True)

ff = subprocess.Popen([str(qc_paths.FFMPEG), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1440x720",
                       "-r", "6", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", str(OUT)],
                      stdin=subprocess.PIPE)
cap = cv2.VideoCapture(str(SESSION / dc["file"]))
first = dc["frames"][0][1]; cap.set(cv2.CAP_PROP_POS_MSEC, (first - 0.5) * 1000)
i, n = -1, 0
last_i = max(fail) if fail else -1
while fail and i < last_i:
    if not cap.grab():
        break
    tf = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    if i < 0:
        if abs(tf - first) > 1e-3:
            continue
        i = 0
    else:
        i += 1
    if i not in fail:
        continue
    t, tilt, inside, why, Pc, Oc = fail[i]
    ok, img = cap.retrieve()
    if PANO:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    po = pm.fm.project(c.model, c.intr, Oc)
    ctr = pm.fm.project(c.model, c.intr, Pc).mean(0)
    span = float(np.clip(np.ptp(po, 0).max() * 1.6, 300, 1600))
    x0 = int(np.clip(ctr[0] - span / 2, 0, max(0, Wd - span))); y0 = int(np.clip(ctr[1] - span / 2, 0, max(0, Hd - span)))
    s = int(min(span, Wd - x0, Hd - y0))
    left = cv2.resize(img[y0:y0 + s, x0:x0 + s], (720, 720), interpolation=cv2.INTER_CUBIC if s < 720 else cv2.INTER_AREA)
    k = 720 / s
    cv2.polylines(left, [((po - [x0, y0]) * k).astype(np.int32).reshape(-1, 1, 2)], True, (255, 0, 255), 2, cv2.LINE_AA)
    m = Pc.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([m], [[0, 0, 1]])[0].as_matrix(); v = Pc @ Q; xy = v[:, :2] / v[:, 2:]
    fv = 450.0 / max(np.ptp(xy, 0).max(), 1e-3)
    yy, xx = np.mgrid[0:720, 0:720].astype(np.float64)
    rays = np.stack([(xx - 360) / fv, (yy - 360) / fv, np.ones_like(xx)], -1).reshape(-1, 3) @ Q.T
    uv = pm.fm.project(c.model, c.intr, rays * 1000.0).reshape(720, 720, 2).astype(np.float32)
    right = cv2.remap(img, uv[..., 0], uv[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
    frame = np.hstack([left, right])
    txt = f"{CAM} frame {i}  t {t:.2f}  {why}  tilt {tilt:.0f} deg  inside {inside * 100:.0f}%"
    cv2.putText(frame, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(frame, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2, cv2.LINE_AA)
    ff.stdin.write(frame.tobytes()); n += 1
ff.stdin.close(); ff.wait()
cnt = {}
for v in fail.values():
    cnt[v[3]] = cnt.get(v[3], 0) + 1
print(f"{WINDOW}/{CAM}: {n} frames -> {OUT}  {cnt}")
