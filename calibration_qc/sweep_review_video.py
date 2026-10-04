# -*- coding: utf-8 -*-
r"""Review video for the operator: does a bundle put the sweep board where the pano sees it?

One frame per pano view of every sweep instance (board_sweep20_instances.py), 3 per second. Both panels show the
same native crop of the pano around the board, with the corners the pano decoded (yellow dots) and the board's
plate outline (800 x 600) where the sweep camera's own pose puts it under a bundle: left the release (magenta),
right the trial (green). With --cv-odd / --cv-even (trial bundles fitted with FIT_SWEEP_HOLDOUT=odd / even) the
right panel draws each instance with the fold that did NOT see it, so the green outline is a held-out prediction;
otherwise the right panel's bundle is --trial (instances in that fit are marked "in fit").

Usage: python sweep_review_video.py --trial <npz> [--cv-odd <npz> --cv-even <npz>] [--release <npz>]
                                    [--instances <json>] [--out <mp4>]
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
SESSION, _ = qc_paths.resolve(None)
SW = qc_paths.QC_ROOT / "sweep20"
INST = json.loads(Path(opt("--instances", str(SW / "instances.json"))).read_text(encoding="utf-8"))["instances"]
REL = pm.load(Path(opt("--release", str(pm.FIT))), correct=False)
TRIAL = Path(opt("--trial"))
CV = {1: opt("--cv-odd"), 0: opt("--cv-even")}                            # 10-s block parity -> fold that left it out
FITS = {"trial": pm.load(TRIAL, correct=False)}
for k, v in CV.items():
    if v:
        FITS[k] = pm.load(Path(v), correct=False)
USED = set(np.load(TRIAL, allow_pickle=False)["sweep_keys"].tolist()) if "sweep_keys" in np.load(TRIAL).files else set()
OUT = Path(opt("--out", str(TRIAL.parent / "SWEEP_REVIEW.mp4")))
OBJ3 = np.c_[bd.OBJ_MM - bd.OBJ_MM.mean(0), np.zeros(88)]
PLATE3 = np.c_[bd.PAPER_MM - bd.OBJ_MM.mean(0), np.zeros(4)]


def board_pose(c, ids, px):
    b = pm.fm.bearings(c.model, c.intr, px); m = b.mean(0); m /= np.linalg.norm(m)
    Q = Rot.align_vectors([[0, 0, 1]], [m])[0].as_matrix(); v = b @ Q.T; uv = (v[:, :2] / v[:, 2:]).astype(np.float64)
    P = OBJ3[ids].astype(np.float64)
    n, rv, tv, e = cv2.solvePnPGeneric(P, uv, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    k = int(np.argmin(np.asarray(e).ravel())); rv, tv = cv2.solvePnPRefineLM(P, uv, np.eye(3), None, rv[k], tv[k])
    Rc = Q.T @ cv2.Rodrigues(rv)[0]; Xc = Q.T @ tv.ravel()
    return c.R.T @ Rc, c.R.T @ (Xc - c.tvec)


def outline(cams, ins, cam):
    """plate outline (closed) and pattern corners in the pano's upright px, from the sweep camera's pose."""
    mv = ins["views"][0]
    R, X = board_pose(cams[mv["cam"]], np.asarray(mv["ids"], int), np.asarray(mv["px"], float))
    c = cams[cam]
    E3 = np.concatenate([np.linspace(PLATE3[i], PLATE3[(i + 1) % 4], 20) for i in range(4)])   # straight in 3-D, curved on the canvas
    edge = pm.fm.project(c.model, c.intr, (E3 @ R.T + X) @ c.R.T + c.tvec)
    return edge, pm.fm.project(c.model, c.intr, (OBJ3 @ R.T + X) @ c.R.T + c.tvec)


jobs = {}                                                 # (window, cam) -> {frame: [(ins, view)]}
for ins in INST:
    for v in ins["views"][1:]:
        jobs.setdefault((ins["window"], v["cam"]), {}).setdefault(v["frame"], []).append((ins, v))
ff = subprocess.Popen([str(qc_paths.FFMPEG), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1440x760",
                       "-r", "3", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", str(OUT)],
                      stdin=subprocess.PIPE)
n_out = 0
for (W, cam), frames in sorted(jobs.items()):
    d = json.loads((SW / f"{W}_{cam}.json").read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(SESSION / d["file"]))
    first = d["frames"][0][1]; cap.set(cv2.CAP_PROP_POS_MSEC, (first - 0.5) * 1000)
    i, last = -1, max(frames)
    while i < last:
        if not cap.grab():
            break
        if i < 0:
            if abs(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 - first) > 1e-3:
                continue
            i = 0
        else:
            i += 1
        if i not in frames:
            continue
        ok, img = cap.retrieve()
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        for ins, v in frames[i]:
            blk = int(ins["t"] // 10.0) % 2
            right = FITS.get(blk, FITS["trial"]); held = blk in FITS
            tag = "held out (other fold)" if held else ("in fit" if ins["key"] in USED else "not in fit")
            eR, cR = outline(REL, ins, cam); eT, cT = outline(right, ins, cam)
            ob = np.asarray(v["px"], float)
            allp = np.concatenate([eR, eT, ob])
            ctr = (allp.min(0) + allp.max(0)) / 2; span = float(np.clip(np.ptp(allp, 0).max() * 1.25, 240, 1400))
            x0 = int(np.clip(ctr[0] - span / 2, 0, 7680 - span)); y0 = int(np.clip(ctr[1] - span / 2, 0, 2160 - span))
            s = int(min(span, 7680 - x0, 2160 - y0)); k = 720 / s
            crop = cv2.resize(img[y0:y0 + s, x0:x0 + s], (720, 720), interpolation=cv2.INTER_CUBIC if s < 720 else cv2.INTER_AREA)
            panels = []
            for e, col, name in ((eR, (255, 0, 255), "release"), (eT, (0, 255, 0), "trial")):
                p = crop.copy()
                for q in ob:
                    cv2.circle(p, (int((q[0] - x0) * k), int((q[1] - y0) * k)), 2, (0, 255, 255), -1, cv2.LINE_AA)
                cv2.polylines(p, [((e - [x0, y0]) * k).astype(np.int32).reshape(-1, 1, 2)], True, col, 2, cv2.LINE_AA)
                cv2.putText(p, name, (8, 708), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(p, name, (8, 708), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)
                panels.append(p)
            frame = np.vstack([np.zeros((40, 1440, 3), np.uint8), np.hstack(panels)])
            dR = np.median(np.linalg.norm(ob - cR[np.asarray(v["ids"], int)], axis=1))
            dT = np.median(np.linalg.norm(ob - cT[np.asarray(v["ids"], int)], axis=1))
            txt = (f"{W} sweep -> {cam}  frame {i}  t {ins['t']:.1f}  board {ins['centre_mm'][2]:.0f} mm up  "
                   f"corner offset release {dR:.0f} px, trial {dT:.0f} px  [{tag}]")
            cv2.putText(frame, txt, (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
            ff.stdin.write(frame.tobytes()); n_out += 1
    print(f"{W}/{cam}: {sum(len(x) for x in frames.values())} views", flush=True)
ff.stdin.close(); ff.wait()
print(f"{n_out} frames -> {OUT}")
