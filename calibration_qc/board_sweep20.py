# -*- coding: utf-8 -*-
r"""The 2026-09-18 hand-held board sweeps at the native frame rate (~20 Hz), in every camera that saw them.

Why: the sweeps (CH03 15:40:27-15:41:30, CH04 15:42:33-15:45:30) were only ever used for CH03 / CH04's own
lenses, and alone they cannot fix those lenses' focal length (the operator stood in one spot, distance and f
trade off; README 2026-09-24). The panoramas saw the same board at the same time (corner cache, 2-s sampling:
CH01 11 / 20 and CH02 14 / 36 views within 1 s of a CH03 / CH04 view). A board held in the air at many heights and
tilts, seen by two cameras at once, is the only above-ground two-camera data of the whole calibration.

Stage A (this script, CPU): every frame of the window is decoded (panos rotated upright); a crop around the
board's expected position - the 2-s corner cache interpolated, or the previous frame's board - goes through
board_detect.charuco_detect (the pipeline's detector parameters, 3x refinement crop). Frames without a prior
are recorded as such and not searched.

Pixels: UPRIGHT (the panos' corner cache from qc_placements is in stored pixels and is converted for the prior).

Usage: python board_sweep20.py --window CH03|CH04 --cam CH01 [--session <09-18 dir>]
Output: <qc>\sweep20\<WINDOW>_<CAM>.json  {window, cam, file, frames: [[i, t_file_s, t_abs_s, n_corners, ids, px], ...]}
        (t_file = the frame's timestamp in its segment; t_abs = segment start from the file name + t_file, seconds
        of the day; both carry the recorder's arrival jitter - regularise by frame index before any timing use.)
"""
import sys, json, glob, os, time
from pathlib import Path
from datetime import datetime
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, board_detect as bd                                       # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
WINDOW, CAM = opt("--window"), opt("--cam")
SESSION, _QC = qc_paths.resolve(opt("--session"))                     # default: the 2026-09-18 session
CACHE = qc_paths.QC_ROOT / "corners" / CAM
OUT = qc_paths.QC_ROOT / "sweep20"; OUT.mkdir(exist_ok=True)
hms = lambda s: sum(int(x) * f for x, f in zip(s.split(":"), (3600, 60, 1)))
WINDOWS = {"CH03": (hms("15:40:20"), hms("15:41:40")), "CH04": (hms("15:42:25"), hms("15:45:40"))}
T0, T1 = WINDOWS[WINDOW]
PANO = CAM in ("CH01", "CH02")


def seg_start(name):
    p = os.path.basename(name).split("_")
    d = datetime.strptime(p[1] + " " + p[2], "%Y-%m-%d %H-%M-%S")
    return d.hour * 3600 + d.minute * 60 + d.second


# the 2-s cache: board centre and size per cached view near the window
cache = []
for f in glob.glob(str(CACHE / "15[34]*.npz")):
    z = np.load(f, allow_pickle=True)
    if len(z["ids"]) < 12:
        continue
    t = seg_start(str(z["seg"])) + float(z["t_rel"])
    if T0 - 6 <= t <= T1 + 6:
        px = np.asarray(z["px"], float)
        if PANO:                                     # qc_placements cached the panos in STORED (rotated) pixels
            px = qc_paths.stored_to_upright(px, SESSION, CAM)
        cache.append((t, px.mean(0), float(np.ptp(px, 0).max())))
cache.sort(key=lambda c: c[0])
seg = next(p for p in sorted(SESSION.glob(f"{CAM}_2026-09-18_*_to_*.mp4")) if seg_start(p.name) <= T0 and
           hms(p.name.split("_to_")[1][:8].replace("-", ":")) >= T1)
S0 = seg_start(seg.name)


def prior(t, last):
    """expected board centre and size at absolute time t: previous detection (<= 0.5 s), else the cache."""
    if last is not None and t - last[0] <= 0.5:
        return last[1], last[2]
    before = [c for c in cache if c[0] <= t and t - c[0] <= 3]
    after = [c for c in cache if c[0] > t and c[0] - t <= 3]
    if before and after:
        a, b = before[-1], after[0]; f = (t - a[0]) / max(b[0] - a[0], 1e-6)
        return (1 - f) * a[1] + f * b[1], max(a[2], b[2])
    if before or after:
        c = (before or after)[-1 if before else 0]
        return c[1], c[2]
    return None


cap = cv2.VideoCapture(str(seg))
cap.set(cv2.CAP_PROP_POS_MSEC, (T0 - S0 - 1.0) * 1000)
frames, last, i, t_start, n_search = [], None, 0, time.time(), 0
while True:
    if not cap.grab():
        break
    t_file = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000; t = S0 + t_file
    if t < T0:
        continue
    if t > T1:
        break
    pr = prior(t, last)
    if pr is None:
        frames.append([i, round(t_file, 4), round(t, 4), -1, [], []]); i += 1
        continue
    ok, img = cap.retrieve()
    if PANO:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    side = int(np.clip(3.0 * pr[1], 600, 2400))
    x0 = int(np.clip(pr[0][0] - side / 2, 0, max(0, W - side))); y0 = int(np.clip(pr[0][1] - side / 2, 0, max(0, H - side)))
    nc, px, ids, markers = bd.charuco_detect(gray[y0:y0 + side, x0:x0 + side])
    n_search += 1
    if px is not None and nc >= 4:
        px = px + np.array([x0, y0], float)
        if nc >= 12:
            last = (t, px.mean(0), float(np.ptp(px, 0).max()))
        frames.append([i, round(t_file, 4), round(t, 4), int(nc), [int(v) for v in ids], np.round(px, 2).tolist()])
    else:
        frames.append([i, round(t_file, 4), round(t, 4), 0, [], []])
    i += 1
    if n_search % 200 == 0:
        print(f"{WINDOW}/{CAM}: t {t - T0:6.1f} s, {n_search} searched, {sum(1 for f in frames if f[3] >= 12)} with >= 12 corners, "
              f"{time.time() - t_start:.0f} s", flush=True)
(OUT / f"{WINDOW}_{CAM}.json").write_text(json.dumps(dict(window=WINDOW, cam=CAM, file=seg.name, seg_start_s=S0, frames=frames)),
                                         encoding="utf-8")
good = sum(1 for f in frames if f[3] >= 12)
print(f"{WINDOW}/{CAM}: done - {len(frames)} frames, {n_search} searched, {good} with >= 12 corners, {time.time() - t_start:.0f} s")
