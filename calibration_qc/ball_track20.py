# -*- coding: utf-8 -*-
r"""The ball at the native frame rate (~20 Hz) through the whole 2026-09-30 sweep, every camera.

Why: the 2-s grid (ball_gui.py, 261 times) cannot see the short stops between two pushes of the stick, nor the
pushes themselves; on it the ball always moves between two marks, so a camera's clock offset and a position
offset look the same (the CH04 end, RELEASE_2026-10-01.md). At ~20 Hz every push is a sharp change of velocity
seen by every camera that has the ball (a common clock event), and every stop is a still ball (no clock needed).

How: each camera's segment is decoded frame by frame (OpenCV; panos rotated upright exactly as ball_gui.py's
transpose=2). The operator's 2-s marks (drawn, accepted or unchecked machine marks; not-in-view statements and
operator_ranges.json) give a prior for every frame: interpolated between two marks, the nearer mark at an entry
or exit, nothing where the operator says the ball is out of view (those frames are decoded but not searched).
Once the ball is found, the previous frame's position is the prior. One IMGSZ tile around the prior goes through
SAM 3 with the same prompts and gates as ball_sam3.py (white >= 0.3, size 0.5-1.8 x the calibration's
prediction); the candidate nearest the prior within the gate is kept.

Time base: OpenCV's frame time minus the camera's segment offset (jobs.json). The 2-s grid frame k of
ball_gui.py sits at 2k + GRID_OFF s on that scale (measured 2026-10-02 by matching the grid frames 0-3 against
every decoded frame: 0.96-1.00 s for all six cameras, the same within a frame; ffmpeg's fps filter keeps the
last frame of each 2-s bin). So the grid's clock labels run ~1 s early for every camera alike; relative offsets
between cameras are unaffected.

Usage: python ball_track20.py --labels <ball_labels.json> [--cams CH04,CH01] [--ball <qc ball dir>]
Output: <ball dir>\track20\ball20_<CAM>.json  {cam, grid_off_s, frames: [[t_grid_s, t_file_s, prior, det|null], ...]}
"""
import sys, json, time
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
BALL = Path(opt("--ball", str(qc_paths.QC_ROOT / "2026-09-30" / "ball")))
OUT = BALL / "track20"; OUT.mkdir(exist_ok=True)
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
SESSION = Path(opt("--session", r"F:\calibration\session_2026-09-30_15-49-39"))
LABELS = [L for L in json.loads(Path(opt("--labels")).read_text(encoding="utf-8"))["labels"]]
MACHINE = json.loads((BALL / "machine.json").read_text(encoding="utf-8"))["cams"]
RANGES = json.loads((BALL / "operator_ranges.json").read_text(encoding="utf-8"))["not_in_view"]
CAMS = opt("--cams", ",".join(c["cam"] for c in jobs["cams"])).split(",")
NT, STEP = len(jobs["clocks"]), float(jobs["step"])
GRID_OFF = {"CH01": 0.997, "CH02": 0.961, "CH03": 0.968, "CH04": 0.972, "CH05": 0.980, "CH06": 0.971}
IMGSZ, CONF, PROMPT, WHITE_MIN, R_BALL = 1008, 0.1, ["ball", "volleyball"], 0.3, 105.0
cams = pm.load()


def pred_radius(cam, uv):
    c = cams[cam]
    uv = np.atleast_2d(np.asarray(uv, float))
    d = c.rays(uv); s = (R_BALL - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    out = [np.linalg.norm(pm.fm.project(c.model, c.intr, (X + off) @ c.R.T + c.tvec) - uv, axis=1)
           for off in ([R_BALL, 0, 0], [0, R_BALL, 0], [0, 0, R_BALL])]
    r = np.mean(out, axis=0); r[~((s > 0) & np.isfinite(s))] = np.nan
    return r


_rat = [L["r"] / pred_radius(L["cam"], L["centre"])[0] for L in LABELS
        if L["verdict"] == "ball" and L.get("r") and L.get("centre") and not str(L.get("method", "")).startswith("machine")]
FACTOR = float(np.nanmedian(_rat))


def grid_marks(cam):
    """per 2-s step: (u, v) of the ball, "out" (operator: not in view / hidden / off the ground), or None (unknown)."""
    g = [None] * NT
    for k, m in MACHINE.get(cam, {}).items():
        g[int(k)] = (m["cx"], m["cy"])
    for a, b in RANGES.get(cam, []):
        for k in range(a - 1, min(b, NT)):
            g[k] = "out"
    for L in LABELS:
        if L["cam"] != cam:
            continue
        g[L["k"]] = tuple(L["centre"]) if L["verdict"] == "ball" and L.get("centre") else "out"
    return g


def detections(pred, img, x0, y0):
    """SAM 3 on one tile: ellipse, whiteness, best confidence over the two prompts (as in ball_sam3.py)."""
    pred.set_image(img)
    r = pred(text=PROMPT)[0]
    out = []
    if r.boxes is None or not len(r.boxes) or r.masks is None:
        return out
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    for b, cf, poly in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.masks.xy):
        if poly is None or len(poly) < 5:
            continue
        (ex, ey), (A, B), ang = cv2.fitEllipse(np.asarray(poly, np.float32))
        m = np.zeros(img.shape[:2], np.uint8); cv2.fillPoly(m, [np.asarray(poly, np.int32)], 1)
        px = hsv[m > 0]
        white = float(((px[:, 1] < 70) & (px[:, 2] > 140)).mean()) if len(px) else 0.0
        d = dict(cx=float(ex + x0), cy=float(ey + y0), a=float(max(A, B) / 2), b=float(min(A, B) / 2),
                 th=float(np.radians(ang + (90 if B > A else 0))), conf=float(cf), white=white)
        same = next((q for q in out if np.hypot(q["cx"] - d["cx"], q["cy"] - d["cy"]) < 0.3 * (d["a"] + d["b"])), None)
        if same is None:
            out.append(d)
        elif d["conf"] > same["conf"]:
            same.update(d)
    return out


def track(pred, cam):
    job = next(c for c in jobs["cams"] if c["cam"] == cam)
    W, H, pano, off = job["w"], job["h"], job["pano"], float(job["offset_s"]) + GRID_OFF[cam]
    g = grid_marks(cam)
    cap = cv2.VideoCapture(str(SESSION / job["file"]))
    cap.set(cv2.CAP_PROP_POS_MSEC, (off - 1.5) * 1000)
    frames, last, t_start, n_search = [], None, time.time(), 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t_file = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        t = t_file - off                                            # seconds on the 2-s grid's scale
        if t < -1.0:
            continue
        if t > STEP * (NT - 1) + 1.0:
            break
        kf = t / STEP; k0 = int(np.floor(kf)); k1 = k0 + 1
        m0 = g[k0] if 0 <= k0 < NT else None; m1 = g[k1] if 0 <= k1 < NT else None
        p0 = m0 if isinstance(m0, tuple) else None; p1 = m1 if isinstance(m1, tuple) else None
        if last is not None and t - last[0] <= 0.3:
            prior, src, gate_extra = np.array(last[1]), "previous", 0.0
        elif p0 and p1:
            f = kf - k0
            prior, src = (1 - f) * np.array(p0) + f * np.array(p1), "interp"
            gate_extra = 0.75 * float(np.hypot(*(np.array(p1) - np.array(p0))))
        elif p0 or p1:
            prior, src = np.array(p0 or p1), "near-mark"
            gate_extra = 0.0
        else:
            frames.append([round(t, 4), round(t_file, 4), None, None])
            continue
        ok, img = cap.retrieve()
        if not ok:
            break
        if pano:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        x0 = int(np.clip(prior[0] - IMGSZ / 2, 0, W - IMGSZ)); y0 = int(np.clip(prior[1] - IMGSZ / 2, 0, H - IMGSZ))
        dets = detections(pred, np.ascontiguousarray(img[y0:y0 + IMGSZ, x0:x0 + IMGSZ]), x0, y0)
        n_search += 1
        best = None
        for d in dets:
            rp = pred_radius(cam, (d["cx"], d["cy"]))[0] * FACTOR
            rr = (d["a"] + d["b"]) / 2
            if not (np.isfinite(rp) and 0.5 * rp < rr < 1.8 * rp and d["a"] < 2.2 * d["b"] and d["white"] >= WHITE_MIN):
                continue
            dist = float(np.hypot(d["cx"] - prior[0], d["cy"] - prior[1]))
            gate = (4 * rp) if src == "previous" else (max(6 * rp, 4 * rp + gate_extra))
            if dist < gate and (best is None or dist < best[0]):
                best = (dist, dict(d, r_pred=float(rp)))
        det = None
        if best:
            det = {k: round(v, 3) for k, v in best[1].items()}
            last = (t, (det["cx"], det["cy"]))
        frames.append([round(t, 4), round(t_file, 4), src, det])
        if n_search % 200 == 0:
            found = sum(1 for f in frames if f[3])
            print(f"{cam}: t {t:6.1f} s, {n_search} searched, {found} found, {time.time() - t_start:.0f} s", flush=True)
        if n_search % 1000 == 0:
            save(cam, frames, final=False)
    save(cam, frames, final=True)
    found = sum(1 for f in frames if f[3])
    print(f"{cam}: done - {len(frames)} frames, {n_search} searched, {found} with the ball, {time.time() - t_start:.0f} s", flush=True)


def save(cam, frames, final):
    (OUT / f"ball20_{cam}.json").write_text(json.dumps(dict(cam=cam, grid_off_s=GRID_OFF[cam], factor=FACTOR, final=final,
                                                            frames=frames)), encoding="utf-8")


if __name__ == "__main__":
    from ultralytics.models.sam import SAM3SemanticPredictor
    from huggingface_hub import hf_hub_download
    pred = SAM3SemanticPredictor(overrides=dict(conf=CONF, task="segment", mode="predict", model=hf_hub_download("facebook/sam3", "sam3.pt"),
                                                imgsz=IMGSZ, half=True, save=False, verbose=False))
    for cam in CAMS:
        track(pred, cam)
