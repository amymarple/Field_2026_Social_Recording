# -*- coding: utf-8 -*-
r"""Operator ground truth for the sweep frames the machine could not decode (board_sweep20.py + board_sweep20_rescue.py).

Why: on the failure videos the operator sees every board clearly; what fails is the locating (the sweep camera's
pose misses the board in the pano by tens of px, and the decoder only keeps 40 mm around its hypothesis). Four
clicks on the plate's corners put the board exactly where it is; board_sweep20_rescue.py --clicks then decodes
that frame from them and carries the board to the frames around it (the clicked frame's pose, moved by the sweep
camera's measured motion, as for a decoded frame).

Which frames: per camera pair, the frames still undecoded, in view (the sweep camera's pose puts the board at
<= MAX_TILT deg to this camera and >= MIN_INSIDE of its corners inside the frame), grouped into runs of consecutive
frames; from each run its first frame and then one every STEP frames (1 s), since one click serves the frames
within 1.5 s around it. The page is manual_board_gui's (manual_gui_page.py): zoom, pan, magnifier, "s" = board
not visible, "p" = visible but cannot be outlined (also a board cut by the canvas edge); the frame is a native-
resolution crop of the upright pano (3x the predicted board, 1000-2160 px) centred on where the sweep camera predicts
the board (corrected by the offset measured on this camera's decoded frames). Export writes manual_quads.json (crop px
+ the crop's offset; the rescue converts). The browser keeps clicks per file name in crop pixels: never re-crop a page
that is being clicked. --keep-first K re-generates keeping the first K frames' crops.

Usage: python board_sweep20_click_gui.py [--step 20] [--max-tilt 70] [--min-inside 0.8] [--keep-first K] [--page-only]
Output: <qc>\sweep20\click\  (board_sweep20_click_gui.html, frames, jobs.json)
"""
import sys, json
from pathlib import Path
import numpy as np, cv2
from scipy.spatial.transform import Rotation as Rot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm, board_detect as bd                    # noqa: E402
from manual_gui_page import PAGE                                           # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
STEP = int(opt("--step", "20"))
MAX_TILT = float(opt("--max-tilt", "70"))
MIN_INSIDE = float(opt("--min-inside", "0.8"))
SESSION, _ = qc_paths.resolve(None)
SW = qc_paths.QC_ROOT / "sweep20"
OUT = SW / "click"; OUT.mkdir(exist_ok=True)
PAIRS = [("CH03", "CH01", 0.52), ("CH03", "CH02", 0.46), ("CH04", "CH01", -0.35), ("CH04", "CH02", -0.25)]   # pano + offset = sweep camera
IR_SHIFT = {"CH03": np.array([0.6, -5.6])}
cams = pm.load(correct=False)
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
PLATE3 = np.c_[bd.PAPER_MM - bd.OBJ_MM.mean(0), np.zeros(4)]


def regular_times(t_abs):
    i = np.arange(len(t_abs)); b = np.polyfit(i, t_abs, 1)[0]; r = t_abs - b * i
    med = np.array([np.median(r[max(0, j - 200):j + 201]) for j in range(0, len(r), 20)])
    return np.interp(i, np.arange(0, len(r), 20), med) + b * i


def board_pose(c, ids, px):
    b = pm.fm.bearings(c.model, c.intr, px); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = OBJ3[ids].astype(np.float64)
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    return c.R.T @ (Q.T @ cv2.Rodrigues(rv)[0]), c.R.T @ (Q.T @ tv.ravel() - c.tvec)


def kabsch_rot(a, b):
    U, _, Vt = np.linalg.svd(a.T @ b); d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


KEEP = int(opt("--keep-first", "0"))            # re-generating: keep the first K jobs as they are (clicks already made on them)
old_jobs = json.loads((OUT / "jobs.json").read_text(encoding="utf-8"))[:KEEP] if KEEP and (OUT / "jobs.json").exists() else []
kept = {(j["window"], j["cam"], j["frame"]): j for j in old_jobs}
def sweep_page():
    """manual_gui_page for the sweep: no cone, any corner first; a plate with one corner cut off (canvas edge, washed
    out) is outlined by its three visible corners in order around the plate, then "p" - the three are kept."""
    return (PAGE.replace("ctx.fillText(k===0?'cone':(k+1)", "ctx.fillText((k+1)")
            .replace("Order: the plate corner next to the cone first, then along the LONG edge, then the diagonal, then back.",
                     "HAND-HELD SWEEP: start at any plate corner and go around the plate (either direction). One corner "
                     "cut off: click the THREE visible corners in order around the plate, then p. Fewer: just p.")
            .replace("function partial(){quads[JOBS[i].file]={pts:[],skip:true,verdict:'partial'};",
                     "function partial(){quads[JOBS[i].file]={pts:(pts.length===3?pts.slice():[]),skip:true,verdict:'partial'};")
            .replace("partial:['BOARD PARTLY VISIBLE - cannot outline','#a60']",
                     "partial:['BOARD PARTLY VISIBLE (3 corners kept if clicked)','#a60']")
            .replace(">partly visible, cannot outline (p)</button>", ">partly visible: 3 corners then p, or just p</button>"))


if "--page-only" in args:
    jobs = json.loads((OUT / "jobs.json").read_text(encoding="utf-8"))
    (OUT / "board_sweep20_click_gui.html").write_text(sweep_page().replace("__JOBS__", json.dumps(jobs))
                                                     .replace("__DATE__", "sweep20_2026-09-18"), encoding="utf-8")
    raise SystemExit(f"page rebuilt from {len(jobs)} jobs (crops untouched)")
jobs = []
for W, CAM, OFF in PAIRS:
    c = cams[CAM]
    dm = json.loads((SW / f"{W}_{W}.json").read_text(encoding="utf-8"))
    tm = regular_times(np.array([f[2] for f in dm["frames"]]))
    poses = [(t, board_pose(cams[W], np.asarray(f[4], int), np.asarray(f[5], float) + IR_SHIFT.get(W, 0.0)))
             for f, t in zip(dm["frames"], tm) if f[3] >= 20]
    TP = np.array([p[0] for p in poses])

    def main_at(t):
        j = int(np.argmin(np.abs(TP - t)))
        return poses[j][1] if abs(TP[j] - t) <= 0.05 else None
    dc = json.loads((SW / f"{W}_{CAM}.json").read_text(encoding="utf-8"))
    tc = regular_times(np.array([f[2] for f in dc["frames"]])) + OFF
    rp = SW / f"{W}_{CAM}_rescue.json"
    rescued = {r[0]: r for r in json.loads(rp.read_text(encoding="utf-8"))["frames"]} if rp.exists() else {}
    corr = []                                    # the predicted -> observed rotation on every decoded / rescued frame
    for f, t in zip(dc["frames"], tc):
        ids, px = (f[4], f[5]) if f[3] >= 12 else ((rescued[f[0]][3], rescued[f[0]][4]) if f[0] in rescued else (None, None))
        if ids is None or main_at(t) is None:
            continue
        R, X = main_at(t); ids = np.asarray(ids, int)
        a = (OBJ3[ids] @ R.T + X) @ c.R.T + c.tvec; a /= np.linalg.norm(a, axis=1, keepdims=True)
        corr.append((t, Rot.from_matrix(kabsch_rot(a, pm.fm.bearings(c.model, c.intr, np.asarray(px, float)))).as_rotvec()))
    TC = np.array([x[0] for x in corr]); RC = np.array([x[1] for x in corr]).reshape(-1, 3)
    cand = {}
    for f, t in zip(dc["frames"], tc):
        if f[3] >= 12 or f[0] in rescued or main_at(t) is None:
            continue
        R, X = main_at(t)
        los = X - c.centre; los /= np.linalg.norm(los)
        if np.degrees(np.arccos(abs(los @ R[:, 2]))) > MAX_TILT:
            continue
        P = (PLATE3 @ R.T + X) @ c.R.T + c.tvec
        if len(TC):
            k = np.argsort(np.abs(TC - t))[:5]; P = P @ Rot.from_rotvec(np.median(RC[k], 0)).as_matrix().T
        pr = pm.fm.project(c.model, c.intr, (OBJ3 @ R.T + X) @ c.R.T + c.tvec)
        if ((pr[:, 0] >= 0) & (pr[:, 0] < 7680) & (pr[:, 1] >= 0) & (pr[:, 1] < 2160)).mean() < MIN_INSIDE:
            continue
        cand[f[0]] = (t, pm.fm.project(c.model, c.intr, P))
    keys = sorted(cand); pick = []
    run = []
    for k in keys + [None]:
        if run and (k is None or k - run[-1] > 3):
            pick += run[::STEP]
            run = []
        if k is not None:
            run.append(k)
    print(f"{W}/{CAM}: {len(keys)} undecoded in-view frames, {len(pick)} to click", flush=True)
    want = set(pick)
    cap = cv2.VideoCapture(str(SESSION / dc["file"]))
    first = dc["frames"][0][1]; cap.set(cv2.CAP_PROP_POS_MSEC, (first - 0.5) * 1000)
    i, last = -1, max(want) if want else -1
    while i < last:
        if not cap.grab():
            break
        if i < 0:
            if abs(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 - first) > 1e-3:
                continue
            i = 0
        else:
            i += 1
        if i not in want:
            continue
        if (W, CAM, i) in kept:
            jobs.append(kept[(W, CAM, i)]); continue
        ok, img = cap.retrieve()
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        t, pl = cand[i]
        ctr = (pl.min(0) + pl.max(0)) / 2; side = int(np.clip(3 * np.ptp(pl, 0).max(), 1000, 2160))
        x0 = int(np.clip(ctr[0] - side / 2, 0, 7680 - side)); y0 = int(np.clip(ctr[1] - side / 2, 0, 2160 - side))
        name = f"sw_{W}_{CAM}_{i:05d}.jpg"
        cv2.imwrite(str(OUT / name), img[y0:y0 + side, x0:x0 + side], [cv2.IMWRITE_JPEG_QUALITY, 92])
        hh = int(t // 3600); mm = int(t % 3600 // 60); ss = t % 60
        clock = f"{hh:02d}:{mm:02d}:{ss:05.2f}"
        jobs.append(dict(file=name, cam=CAM, station=f"SW {W} f{i}", window=W, frame=int(i), t=round(float(t), 3), clock=clock,
                         win=[clock, clock], off=[x0, y0], scale=1.0, w=side, h=side, pano=True, machine=None,
                         machine_method=None, machine_corners=None))
(OUT / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
(OUT / "board_sweep20_click_gui.html").write_text(sweep_page().replace("__JOBS__", json.dumps(jobs)).replace("__DATE__", "sweep20_2026-09-18"),
                                                 encoding="utf-8")
print(f"{len(jobs)} frames -> {OUT / 'board_sweep20_click_gui.html'}")
