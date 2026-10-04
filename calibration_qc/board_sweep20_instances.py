# -*- coding: utf-8 -*-
r"""Two-camera board instances from the 2026-09-18 hand-held sweeps at 20 Hz, for a trial bundle (fit_cameras.py
with FIT_SWEEP=<this output>).

Why: the release bundle ties the cameras together only near the ground (plates on the grass, cones). The sweep
board was held off the ground (board centre 0.2-0.55 m, p10-p90 of the instances) in front of CH03 and CH04 while
the panos watched; projected from the sweep
camera's own pose into the panos it lands 10-55 px off the decoded corners, systematically per camera pair (see
README, 2026-10-02). A bundle that also has to explain these views says whether that is the panos' canvas model or
the pinholes' poses.

An instance is one sweep-camera frame (>= MIN_MAIN corners) together with every pano frame of the same moment:
  * same moment = the pano frame's regularised time plus its clock offset (fitted from the board-centre speed
    profiles, sweep_analyze in the 2026-10-02 notes) within HALF_FRAME of the sweep frame's;
  * the board must be nearly still: its fastest corner (sweep camera's IPPE poses one frame either side, release
    bundle) slower than V_MAX, so frame phase + offset error (<= 35 ms) cost < V_MAX * 35 ms;
  * at most one instance per MIN_GAP seconds and window (neighbouring frames are the same measurement twice).
Corners: measured only - the 20 Hz detections (board_sweep20.py, method "charuco") and the rescued frames
(board_sweep20_rescue.py) decoded as rect-charuco / rect-chess, or refined to the image saddles from the markers or a tracked
prior (rect-refined, sigma 1.0 px: against the decoder on 240 frames median 0.5-0.6 px, p99 1.4-2.6); "rect-markers"
corners are predicted and stay out.
Corners inside the burnt-in OSD boxes are dropped. Each view gets fit_data's sigma for its method, raised to its own
homography rms (on the lens-free rays, rotated to a virtual pinhole: a near board spans the distortion) (a view that is no homography above HOM_REJECT is out: wrong ids), doubled for partial views
(< 30 corners or touching the frame edge), as fit_data does for the plates; a pano view also carries the timing
error (T_RMS: frame phase + offset) at the board's speed, as pixels at its range. CH03's sweep was in IR mode: its
corners are moved by the measured 09-18 IR -> colour shift (session_2026-09-18_ir_colour_shift.txt) into the
colour frame its plates were fitted in.

Usage: python board_sweep20_instances.py [--v-max 0.3] [--gap 0.25]
Output: <qc>\sweep20\instances.json  {meta, instances: [{key, window, t, speed_mm_s, views: [{cam, frame, method,
        sigma, ids, px}]}]}  (pixels upright)
"""
import sys, json
from pathlib import Path
import numpy as np, cv2
from scipy.spatial.transform import Rotation as Rot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, board_detect as bd, fit_data as fd     # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
V_MAX = float(opt("--v-max", "0.3")) * 1000.0           # mm/s, fastest corner
MIN_GAP = float(opt("--gap", "0.25"))                     # s
HALF_FRAME, MIN_MAIN, MIN_PANO = 0.025, 20, 12
T_RMS = 0.017                                             # s: uniform +-25 ms frame phase (14 ms rms) and ~10 ms offset
SESSION, _ = qc_paths.resolve(None)                       # 2026-09-18
SW = qc_paths.QC_ROOT / "sweep20"
OFFSETS = {"CH03": {"CH01": 0.52, "CH02": 0.46}, "CH04": {"CH01": -0.35, "CH02": -0.25}}   # pano + offset = sweep camera
IR_SHIFT = {"CH03": np.array([0.6, -5.6])}                # sweep camera in IR mode -> colour px
MEASURED = ("charuco", "rect-charuco", "rect-chess", "rect-refined")
SIGMA = {**fd.SIGMA, "rect-refined": 1.0}                 # refined vs decoded on 240 frames: median 0.5-0.6 px, p99 1.4-2.6
cams = pm.load(correct=False)
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]


def regular_times(t_abs):
    i = np.arange(len(t_abs)); b = np.polyfit(i, t_abs, 1)[0]; r = t_abs - b * i
    med = np.array([np.median(r[max(0, j - 200):j + 201]) for j in range(0, len(r), 20)])
    return np.interp(i, np.arange(0, len(r), 20), med) + b * i


def board_pose(cam, ids, px):
    c = cams[cam]; b = pm.fm.bearings(c.model, c.intr, px); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = OBJ3[ids].astype(np.float64)
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    if not n:
        return None
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    Rc = Q.T @ cv2.Rodrigues(rv)[0]; Xc = Q.T @ tv.ravel()
    return c.R.T @ Rc, c.R.T @ (Xc - c.tvec)


def view(cam, frame, method, ids, px, timing_px=0.0):
    """one camera's corners of one instance, gated and weighted as fit_data does for the plates; None = unusable."""
    ids = np.asarray(ids, int); px = np.asarray(px, float).reshape(-1, 2)
    up = (7680, 2160) if cam in ("CH01", "CH02") else qc_paths.upright_size(SESSION, cam)
    keep = ~fd.in_osd(px, up, cam)
    ids, px = ids[keep], px[keep]
    if len(ids) < MIN_PANO:
        return None
    c = cams[cam]                                         # the homography gate on the lens-free view: a near board
    b = pm.fm.bearings(c.model, c.intr, px); m = b.mean(0); m /= np.linalg.norm(m)   # spans the distortion, a far one the canvas
    v = b @ Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix().T
    hr = fd.hom_rms(bd.OBJ_MM[ids], v[:, :2] / v[:, 2:] * c.intr[0])
    if hr > fd.HOM_REJECT:
        return None
    sigma = max(SIGMA[method], hr)
    edge = 0.02
    if len(ids) < 30 or bool(((px[:, 0] < edge * up[0]) | (px[:, 0] > (1 - edge) * up[0]) |
                              (px[:, 1] < edge * up[1]) | (px[:, 1] > (1 - edge) * up[1])).any()):
        sigma *= 2.0
    sigma = float(np.hypot(sigma, timing_px))
    return dict(cam=cam, frame=int(frame), method=method, sigma=round(float(sigma), 3), hom_rms=round(float(hr), 3),
                ids=[int(v) for v in ids], px=np.round(px, 2).tolist())


instances, report = [], []
for W, offs in OFFSETS.items():
    d = json.loads((SW / f"{W}_{W}.json").read_text(encoding="utf-8"))
    tm = regular_times(np.array([f[2] for f in d["frames"]]))
    main = {}
    for f, t in zip(d["frames"], tm):
        if f[3] >= MIN_MAIN:
            px = np.asarray(f[5], float) + IR_SHIFT.get(W, 0.0)
            p = board_pose(W, np.asarray(f[4], int), px)
            if p is not None:
                main[f[0]] = (t, p, f[4], px)
    idx = sorted(main)
    T = np.array([main[i][0] for i in idx])
    speed = np.full(len(idx), np.inf)                     # fastest corner, mm/s, from the frames either side
    for j in range(1, len(idx) - 1):
        a, b = main[idx[j - 1]], main[idx[j + 1]]
        if idx[j + 1] - idx[j - 1] != 2:
            continue
        Pa = OBJ3 @ a[1][0].T + a[1][1]; Pb = OBJ3 @ b[1][0].T + b[1][1]
        speed[j] = np.linalg.norm(Pb - Pa, axis=1).max() / (b[0] - a[0])
    pano = {}
    for cam, off in offs.items():
        dc = json.loads((SW / f"{W}_{cam}.json").read_text(encoding="utf-8"))
        tc = regular_times(np.array([f[2] for f in dc["frames"]])) + off
        rescued = {}
        rp = SW / f"{W}_{cam}_rescue.json"
        if rp.exists():
            rj = json.loads(rp.read_text(encoding="utf-8"))
            rescued = {r[0]: r for r in rj["frames"] if r[1] in MEASURED}
        for f, t in zip(dc["frames"], tc):
            if f[3] >= MIN_PANO:
                pano.setdefault(cam, []).append((t, f[0], "charuco", f[4], f[5]))
            elif f[0] in rescued:
                r = rescued[f[0]]
                pano.setdefault(cam, []).append((t, f[0], r[1], r[3], r[4]))
    n_pair = {c: 0 for c in offs}; last_t = -1e9; n_fast = 0
    for j, i in enumerate(idx):
        t = T[j]
        views = []
        for cam in offs:
            L = pano.get(cam, [])
            if not L:
                continue
            tt = np.array([x[0] for x in L]); k = int(np.argmin(np.abs(tt - t)))
            if abs(tt[k] - t) <= HALF_FRAME:
                c = cams[cam]; rng = np.linalg.norm(main[i][1][1] - c.centre)
                tpx = (speed[j] if np.isfinite(speed[j]) else 0.0) * T_RMS / rng * c.intr[0]
                v = view(cam, L[k][1], L[k][2], L[k][3], L[k][4], tpx)
                if v is not None:
                    views.append(v)
        if not views:
            continue
        if speed[j] > V_MAX:
            n_fast += 1
            continue
        if t - last_t < MIN_GAP:
            continue
        mv = view(W, i, "charuco", main[i][2], main[i][3])
        if mv is None:
            continue
        for v in views:
            n_pair[v["cam"]] += 1
        R, X = main[i][1]
        instances.append(dict(key=f"SWEEP|{W}|{i}", window=W, t=round(float(t), 3), speed_mm_s=round(float(speed[j]), 1),
                              centre_mm=np.round(X, 1).tolist(), views=[mv] + views))
        last_t = t
    report.append(f"{W}: {len(idx)} sweep-camera poses; {n_fast} two-camera moments faster than {V_MAX:.0f} mm/s; "
                  f"{sum(1 for x in instances if x['window'] == W)} instances (" +
                  ", ".join(f"{c} {n}" for c, n in n_pair.items()) + ")")
meta = dict(v_max_mm_s=V_MAX, timing_rms_s=T_RMS, min_gap_s=MIN_GAP, half_frame_s=HALF_FRAME, offsets_s=OFFSETS,
            ir_shift_px={k: v.tolist() for k, v in IR_SHIFT.items()}, methods=MEASURED, bundle=str(pm.FIT),
            note="pano time + offset = sweep-camera time; pixels upright; sweep-camera px already IR->colour shifted")
(SW / "instances.json").write_text(json.dumps(dict(meta=meta, instances=instances)), encoding="utf-8")
for s in report:
    print(s)
z = np.array([x["centre_mm"][2] for x in instances])
print(f"{len(instances)} instances -> {SW / 'instances.json'}; board centre height p10-p90 {np.percentile(z, 10):.0f}-{np.percentile(z, 90):.0f} mm")
