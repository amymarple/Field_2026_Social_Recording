# -*- coding: utf-8 -*-
r"""Did a camera move between two calibration sessions? Measured on the operator's RIGID landmarks.

Cones are no test across sessions (rain and grass growth change how they sit) and whole-image registration fails
across days (grass, light, shadows; the analysis repo's change_log/2026-09-28-cohort3-camera-stability.md). The
operator labels rigid structures - pole edges, the boxes on the poles, wall tops, water towers - on a reference
frame with the analysis repo's cv/cv_field/landmark_gui.py. Here:
  template = the edge pixels of a session-A frame within BAND px of those labels (the frame's own edges, so the
             offset between a click and the true edge cancels);
  target   = the edges of a session-B frame, processed the same way;
  fit      = a similarity transform about the image centre (shift, rotation, scale) minimising the truncated
             distance from the template to the target's edges: dense shift grid, then Nelder-Mead.
Both frames must be in the same colour mode: an IR template against a colour frame of the SAME day gave 10-18 px
for CH03/CH04 (the IR-cut filter moves the image), under 2.5 px for CH01/CH02. So the template is taken from a
COLOUR frame of session A (TEMPLATE below) and the control is another colour frame of session A (CONTROL), where
the camera certainly did not move: it must come out at ~0. Two frames of session B must agree with each other.
The ground effect is what using session-B pixels with the release unchanged would do, at a rat's back (z 60 mm).

Usage: python landmark_drift.py --a <session A dir> --b <session B dir> [--b-times 16:35:10,16:34:40]
                                [--landmarks <dir with landmarks_CHxx_*.json>]
Output: <qc of B>\LANDMARK_DRIFT.txt and landmark_drift.json (the fitted transform per camera, from the first B time)
"""
import sys, json, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
SA, SB = Path(opt("--a")), Path(opt("--b"))
B_TIMES = opt("--b-times", "16:35:10,16:34:40").split(",")
LM = Path(opt("--landmarks", r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c"))
TEMPLATE = {"CH01": "15:20:00", "CH02": "15:35:00", "CH03": "15:30:00", "CH04": "15:47:00"}   # 2026-09-18 colour frames
CONTROL = {"CH01": "15:47:00", "CH02": "15:47:00", "CH03": "15:05:00", "CH04": "15:05:00"}
RIGID = ("POLE_", "BOX_", "WALLTOP_", "TOWER_", "PCBOX")
CAP, BAND, R = 8.0, 10, 60
_, QB = qc_paths.resolve(str(SB))


def frame(session, cam, clock):
    date = session.name.split("_")[1]
    t = datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M:%S")
    for p in sorted(session.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t < b:
            r = subprocess.run([qc_paths.FFMPEG, "-v", "error", "-ss", f"{(t - a).total_seconds():.2f}", "-i", str(p), "-frames:v", "1",
                                "-vf", "transpose=2" if cam in ("CH01", "CH02") else "null", "-f", "image2pipe", "-vcodec", "png", "-"],
                               stdout=subprocess.PIPE)
            return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    raise SystemExit(f"no closed {cam} segment covers {clock} in {session}")


def edges(img):
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(16, 16)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    g = cv2.GaussianBlur(g, (5, 5), 1.2)
    v = np.median(g)
    return cv2.Canny(g, int(max(10, 0.5 * v)), int(min(255, 1.2 * v)))


def warp(P, prm, c):
    dx, dy, th, ls = prm
    s = np.exp(ls); Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return (P - c) @ (s * Rm).T + c + [dx, dy]


def cost(prm, P, dt, c):
    Q = warp(P, prm, c).astype(np.float32)
    d = cv2.remap(dt, Q[:, 0].reshape(-1, 1), Q[:, 1].reshape(-1, 1), cv2.INTER_LINEAR, borderValue=CAP).ravel()
    return float(np.minimum(d, CAP).mean())


def align(P, dt, c):
    best = min(((cost((dx, dy, 0, 0), P, dt, c), (dx, dy)) for dx in range(-R, R + 1, 2) for dy in range(-R, R + 1, 2)))
    x0 = np.array([best[1][0], best[1][1], 0.0, 0.0])
    simplex = np.array([x0, x0 + [1.5, 0, 0, 0], x0 + [0, 1.5, 0, 0], x0 + [0, 0, np.radians(0.05), 0], x0 + [0, 0, 0, 0.001]])
    r = minimize(cost, x0, args=(P, dt, c), method="Nelder-Mead", options=dict(initial_simplex=simplex, xatol=0.02, fatol=1e-5, maxiter=4000))
    return r.x, r.fun


cams = pm.load()
L = [f"LANDMARK DRIFT  {SA.name} -> {SB.name}  (rigid landmarks from {LM}; same colour mode on both sides)", ""]
out = {}
for f in sorted(LM.glob("landmarks_CH0*_*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    cam = d["camera"]
    if cam not in TEMPLATE or not d["time"].startswith(SA.name.split("_")[1]):
        continue
    ia = frame(SA, cam, TEMPLATE[cam])
    h, w = ia.shape[:2]; c = np.array([w / 2, h / 2])
    band = np.zeros((h, w), np.uint8)
    used = []
    for k, pieces in d["landmarks"].items():
        if k.startswith(RIGID):
            for pc in pieces:
                P = np.round(np.asarray(pc, float)).astype(np.int32)
                if len(P) >= 2:
                    cv2.polylines(band, [P.reshape(-1, 1, 2)], d.get("kind", {}).get(k) == "outline" and len(pieces) == 1, 255, 2 * BAND + 1)
                    used.append(k)
    ys, xs = np.nonzero((edges(ia) > 0) & (band > 0))
    T = np.stack([xs, ys], 1).astype(float)
    if len(T) > 12000:
        T = T[np.random.default_rng(0).choice(len(T), 12000, replace=False)]
    gx, gy = np.meshgrid(np.arange(12, 470, 12.0), np.arange(12, 230, 12.0)); G = np.stack([gx.ravel(), gy.ravel()], 1)
    uv = cams[cam].to_paddock_inv(G, z_mm=60, units="in")
    okg = np.isfinite(cams[cam].to_paddock(uv, z_mm=60, units="in")).all(1) & cams[cam].sees(G, z_mm=60, units="in", margin=20)
    L.append(f"{cam}: template = {SA.name.split('_')[1]} {TEMPLATE[cam]} colour frame, {len(T)} edge px within {BAND} px of "
             f"{len(set(used))} rigid landmarks")
    for tag, sess, t in [("control", SA, CONTROL[cam])] + [("B", SB, t) for t in B_TIMES]:
        img = frame(sess, cam, t)
        dt = cv2.distanceTransform(255 - edges(img), cv2.DIST_L2, 3)
        x, fun = align(T, dt, c)
        g = np.linalg.norm(cams[cam].to_paddock(warp(uv[okg], x, c), z_mm=60, units="in") - G[okg], axis=1) * 25.4
        g = g[np.isfinite(g)]
        L.append(f"   {tag:7s} {sess.name.split('_')[1]} {t}: shift ({x[0]:+6.2f},{x[1]:+6.2f}) px  rot {np.degrees(x[2]):+.3f} deg  "
                 f"scale {np.exp(x[3]):.4f}  edge distance {cost((0, 0, 0, 0), T, dt, c):.2f} -> {fun:.2f} px  "
                 f"ground effect median {np.median(g):3.0f} mm, max {g.max():3.0f} mm")
        if tag == "B" and cam not in out:
            out[cam] = dict(b_time=t, dx_px=float(x[0]), dy_px=float(x[1]), rot_deg=float(np.degrees(x[2])), scale=float(np.exp(x[3])),
                            centre_px=c.tolist(), ground_median_mm=float(np.median(g)), ground_max_mm=float(g.max()),
                            note="session-B pixel = centre + scale*R(rot)*(session-A pixel - centre) + (dx, dy)")
    print("\n".join(L[-(len(B_TIMES) + 2):]), flush=True)
(QB / "LANDMARK_DRIFT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(QB / "landmark_drift.json").write_text(json.dumps(dict(a=SA.name, b=SB.name, cameras=out), indent=1), encoding="utf-8")
print("->", QB / "LANDMARK_DRIFT.txt")
