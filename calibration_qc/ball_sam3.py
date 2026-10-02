# -*- coding: utf-8 -*-
r"""Ball marks for the ball sweep from SAM 3 (text prompts "ball" + "volleyball"), checked against the operator's marks.

SAM 3 (Meta, `facebook/sam3`, gated on HuggingFace; run through ultralytics' SAM3SemanticPredictor) segments every
instance of a text concept. It sees an image at IMGSZ x IMGSZ, so every camera goes in as full-resolution IMGSZ tiles
over the part of the frame where the paddock floor is (overlapping by a quarter, so the ball is always whole in one
of them; 28 per pano frame, 12-18 per small camera).

History (2026-10-01). v1 sent CH03-CH06 in whole and asked only for "volleyball" at conf >= 0.2: a 4512-px frame
shrunk to 1008 px leaves the ball ~20 px across, and the operator reported many misses. On the missed frames a
full-resolution tile found the ball at "volleyball" 0.15 but "ball" 0.8. "ball" also fires on the disc cones at
0.3-0.8; the colour separates them: the ball's mask is 40-60 % white (low saturation, bright), a cone's 0-4 %.
v1's pano tiles were placed over what moved against the median background; over the 9-minute sweep the light
changed across the whole pano, every tile went to the left edge, and CH02's ball was never looked at. Tiles now
come from the calibration alone.

Frames the operator has said are out of view (operator_ranges.json next to jobs.json, and "not visible" / "hidden" /
"off ground" verdicts in the labels file) are not searched and the path is held at "not in view" there.

Per detection: the mask outline -> fitted ellipse (centre more exact than the box), kept if its size is 0.5-1.8 x
the radius the calibration predicts for the ball there (scaled by the operator's radii) and its mask is at least
WHITE_MIN white; its confidence is the higher of the two prompts'. A spot that holds a detection in a quarter or more
of a camera's searched frames is a fixed object (on CH03 a blue cone at conf 0.85 in 50 of 67 frames, on CH06 a
white pipe cap) and is dropped: the ball is pushed across the field and never sits that long. Per camera, a Viterbi pass
through time picks one detection or "not in view" per frame. Frames are --step (2 s) apart, so the ball can move
a few metres between them: a jump costs no more than leaving and coming back, and the costs lean to recall (the
operator rejects a wrong mark with one key, a missed one has to be drawn).

Usage: python ball_sam3.py --labels <ball_labels.json> [--ball <qc ball dir>] [--cams CH01,...] [--conf 0.1]
       python ball_sam3.py --labels <ball_labels.json> --from-raw      (path choice + check only, no SAM 3)
Needs: ultralytics with SAM 3, and sam3.pt (huggingface_hub: hf_hub_download("facebook/sam3", "sam3.pt") after
`hf auth login` with an account that has access).
Output: <ball dir>\sam3_raw_<CAM>.json (every size-checked detection, per camera, before the path choice);
machine.json, BALL_SAM3.txt over every camera that has a raw file.
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
LABELS = json.loads(Path(opt("--labels")).read_text(encoding="utf-8"))
LABELS["labels"] = [L for L in LABELS["labels"] if L.get("method") != "machine-unchecked"]   # the page exports these too
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
ALL_CAMS = [c["cam"] for c in jobs["cams"]]
CAMS = opt("--cams", ",".join(ALL_CAMS)).split(",")
FROM_RAW = "--from-raw" in args
CONF = float(opt("--conf", "0.1"))
IMGSZ = 1008
PROMPT = ["ball", "volleyball"]
RAW_WHITE, WHITE_MIN = 0.2, 0.3          # kept in the raw file / used for the path (operator's balls >= 0.30, median 0.6)
R_BALL = 105.0
NT = len(jobs["clocks"])
cams = pm.load()


def path_of(cam, k):
    return BALL / cam / f"{cam}_{k:04d}.jpg"


def pred_radius(cam, uv):
    c = cams[cam]
    uv = np.atleast_2d(np.asarray(uv, float))
    d = c.rays(uv)
    s = (R_BALL - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    out = [np.linalg.norm(pm.fm.project(c.model, c.intr, (X + off) @ c.R.T + c.tvec) - uv, axis=1)
           for off in ([R_BALL, 0, 0], [0, R_BALL, 0], [0, 0, R_BALL])]
    r = np.mean(out, axis=0)
    r[~((s > 0) & np.isfinite(s))] = np.nan
    return r


ratios = [L["r"] / pred_radius(L["cam"], L["centre"])[0] for L in LABELS["labels"]
          if L["verdict"] == "ball" and L.get("r") and L.get("centre")]
ratios = [x for x in ratios if np.isfinite(x)]
FACTOR = float(np.median(ratios)) if ratios else 1.0

OUT_OF_VIEW = {cam: set() for cam in ALL_CAMS}                         # frames k the operator says the ball is not seen in
_rf = BALL / "operator_ranges.json"
for cam, rngs in (json.loads(_rf.read_text(encoding="utf-8"))["not_in_view"].items() if _rf.exists() else []):
    for a, b in rngs:
        OUT_OF_VIEW[cam].update(range(a - 1, b))
for L in LABELS["labels"]:
    if L["verdict"] in ("not visible", "hidden", "off ground") and L["cam"] in OUT_OF_VIEW:
        OUT_OF_VIEW[L["cam"]].add(L["k"])


def paddock_tiles(cam, W, H):
    """Full-resolution IMGSZ tiles (x0, y0) over every part of the frame where the paddock floor is, at ball height."""
    c = cams[cam]
    gx, gy = np.meshgrid(np.arange(-12, 493, 6), np.arange(-12, 253, 6))
    P = np.c_[gx.ravel(), gy.ravel()]
    uv = c.to_paddock_inv(P[c.sees(P, z_mm=R_BALL, units="in")], z_mm=R_BALL, units="in")
    step = IMGSZ * 3 // 4
    xs = sorted(set(list(range(0, W - IMGSZ, step)) + [W - IMGSZ]))
    ys = sorted(set(list(range(0, H - IMGSZ, step)) + [H - IMGSZ]))
    return [(x, y) for x in xs for y in ys
            if ((uv[:, 0] >= x + 30) & (uv[:, 0] < x + IMGSZ - 30) & (uv[:, 1] >= y + 30) & (uv[:, 1] < y + IMGSZ - 30)).any()]


def detections(pred, img, x0=0, y0=0):
    """every mask for either prompt in one tile; the same object found by both prompts is one detection."""
    pred.set_image(img)
    r = pred(text=PROMPT)[0]
    out = []
    if r.boxes is None or not len(r.boxes):
        return out
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    polys = r.masks.xy if r.masks is not None else [None] * len(r.boxes)
    for b, cf, cl, poly in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy(), polys):
        if poly is not None and len(poly) >= 5:
            (ex, ey), (A, B), ang = cv2.fitEllipse(np.asarray(poly, np.float32))
            a, bb = max(A, B) / 2, min(A, B) / 2
            th = np.radians(ang + (90 if B > A else 0))
            m = np.zeros(img.shape[:2], np.uint8)
            cv2.fillPoly(m, [np.asarray(poly, np.int32)], 1)
            px = hsv[m > 0]
            white = float(((px[:, 1] < 70) & (px[:, 2] > 140)).mean()) if len(px) else 0.0
        else:
            ex, ey = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            a = bb = max(b[2] - b[0], b[3] - b[1]) / 2; th = 0.0; white = 0.0
        d = dict(cx=float(ex + x0), cy=float(ey + y0), a=float(a), b=float(bb), th=float(th), white=white,
                 **{f"conf_{PROMPT[int(cl)]}": float(cf)})
        same = next((q for q in out if np.hypot(q["cx"] - d["cx"], q["cy"] - d["cy"]) < 0.3 * (a + bb)), None)
        if same is None:
            out.append(d)
        else:
            for p in PROMPT:
                same[f"conf_{p}"] = max(same.get(f"conf_{p}", 0.0), d.get(f"conf_{p}", 0.0))
    for d in out:
        d["conf"] = max(d.get(f"conf_{p}", 0.0) for p in PROMPT)
    return out


def run_sam3(pred, cam):
    """Every size- and colour-checked detection per frame -> sam3_raw_<cam>.json."""
    W, H = next((c["w"], c["h"]) for c in jobs["cams"] if c["cam"] == cam)
    tiles = paddock_tiles(cam, W, H)
    todo = [k for k in range(NT) if k not in OUT_OF_VIEW[cam]]
    print(f"{cam}: {len(tiles)} tiles per frame, {len(todo)}/{NT} frames (the rest the operator says are out of view)", flush=True)
    found, t0 = {}, time.time()
    for n, k in enumerate(todo):
        img = cv2.imread(str(path_of(cam, k)))
        dets = []
        for x0, y0 in tiles:
            dets += detections(pred, img[y0:y0 + IMGSZ, x0:x0 + IMGSZ], x0, y0)
        keep = []
        for d in dets:                                       # size check against the calibration, then de-duplicate
            rp = pred_radius(cam, (d["cx"], d["cy"]))[0] * FACTOR
            rr = (d["a"] + d["b"]) / 2
            if np.isfinite(rp) and 0.5 * rp < rr < 1.8 * rp and d["a"] < 2.2 * d["b"] and d["white"] >= RAW_WHITE:
                if all(np.hypot(d["cx"] - q["cx"], d["cy"] - q["cy"]) > 0.5 * rr or d["conf"] > q["conf"] for q in keep):
                    keep = [q for q in keep if np.hypot(d["cx"] - q["cx"], d["cy"] - q["cy"]) > 0.5 * rr] + [dict(d, r_pred=float(rp))]
        found[str(k)] = sorted(keep, key=lambda q: -q["conf"])[:6]
        if n % 20 == 0:
            print(f"{cam}: frame {n}/{len(todo)}, {time.time() - t0:.0f} s", flush=True)
    print(f"{cam}: SAM3 on {len(todo)} frames ({len(tiles)} tiles each) in {time.time() - t0:.0f} s", flush=True)
    (BALL / f"sam3_raw_{cam}.json").write_text(json.dumps(dict(prompt=PROMPT, imgsz=IMGSZ, conf=CONF, factor=FACTOR,
                                                               white_min=RAW_WHITE, frames=found)), encoding="utf-8")


def drop_static(C, n_searched):
    """detections at a spot that holds one in >= max(6, 25 % of the searched frames) frames -> removed; returns C, spots."""
    flat = [(k, d) for k, dets in enumerate(C) for d in dets]
    spots, need = [], max(6, 0.25 * n_searched)
    for k, d in flat:
        near = {k2 for k2, d2 in flat if np.hypot(d2["cx"] - d["cx"], d2["cy"] - d["cy"]) < 0.5 * max(d["r_pred"], 5)}
        if len(near) >= need and all(np.hypot(d["cx"] - x, d["cy"] - y) >= 0.5 * max(d["r_pred"], 5) for x, y, _ in spots):
            spots.append((d["cx"], d["cy"], len(near)))
    is_static = lambda d: any(np.hypot(d["cx"] - x, d["cy"] - y) < 0.5 * max(d["r_pred"], 5) for x, y, _ in spots)
    return [[d for d in dets if not is_static(d)] for dets in C], spots


def choose_path(C):
    """Viterbi over 'not in view' + the detections of each frame; returns the chosen index (0 = none) per frame."""
    ABSENT, SWITCH, MOVE = -np.log(0.12), 0.15, 0.001      # a run is taken from conf 0.12, a lone frame from ~0.16 (0.2 -> 0.12: pano recall 41 -> 45 of 49, no mark on an operator-out frame)
    emis = lambda d: -np.log(min(d["conf"], 0.95))
    cost, back = [[ABSENT] + [SWITCH + emis(d) for d in C[0]]], []
    for k in range(1, len(C)):
        row, bk = [], []
        o0 = [cost[-1][0]] + [cost[-1][i + 1] + SWITCH for i in range(len(C[k - 1]))]
        j = int(np.argmin(o0)); row.append(o0[j] + ABSENT); bk.append(j)
        for d in C[k]:
            o = [cost[-1][0] + SWITCH]
            for i, p in enumerate(C[k - 1]):
                dist = np.hypot(d["cx"] - p["cx"], d["cy"] - p["cy"]) / max(d["r_pred"], 5)
                o.append(cost[-1][i + 1] + min(MOVE * dist ** 2, 2 * SWITCH))
            j = int(np.argmin(o)); row.append(o[j] + emis(d)); bk.append(j)
        cost.append(row); back.append(bk)
    s = int(np.argmin(cost[-1])); path = [s]
    for k in range(len(C) - 1, 0, -1):
        s = back[k - 1][s]; path.append(s)
    return path[::-1]


if not FROM_RAW:
    from ultralytics.models.sam import SAM3SemanticPredictor          # noqa: E402
    from huggingface_hub import hf_hub_download                        # noqa: E402
    pred = SAM3SemanticPredictor(overrides=dict(conf=CONF, task="segment", mode="predict", model=hf_hub_download("facebook/sam3", "sam3.pt"),
                                                imgsz=IMGSZ, half=True, save=False, verbose=False))
    for cam in CAMS:
        run_sam3(pred, cam)

machine, report = {}, []
for cam in ALL_CAMS:
    f = BALL / f"sam3_raw_{cam}.json"
    if not f.exists():
        continue
    raw = json.loads(f.read_text(encoding="utf-8"))["frames"]
    C = [[] if k in OUT_OF_VIEW[cam] else [d for d in raw.get(str(k), []) if d.get("white", 1.0) >= WHITE_MIN]
         for k in range(NT)]
    C, spots = drop_static(C, NT - len(OUT_OF_VIEW[cam]))
    path = choose_path(C)
    machine[cam] = {str(k): dict(C[k][s - 1], score=C[k][s - 1]["conf"], method="sam3") for k, s in enumerate(path) if s}
    hit, err, nb, fa, nn = 0, [], 0, 0, 0                  # check against the operator
    for L in LABELS["labels"]:
        if L["cam"] != cam:
            continue
        m = machine[cam].get(str(L["k"]))
        if L["verdict"] == "ball" and L.get("centre"):
            nb += 1
            rr = L["r"] or (m and (m["a"] + m["b"]) / 2) or 40
            if m and np.hypot(m["cx"] - L["centre"][0], m["cy"] - L["centre"][1]) < 0.6 * rr:
                hit += 1; err.append(np.hypot(m["cx"] - L["centre"][0], m["cy"] - L["centre"][1]))
        else:
            nn += 1; fa += int(m is not None)
    line = (f"{cam}: marks in {len(machine[cam])}/{NT - len(OUT_OF_VIEW[cam])} frames not ruled out by the operator; "
            f"operator's balls found {hit}/{nb}"
            + (f", centre error median {np.median(err):.1f} px, p90 {np.percentile(err, 90):.1f} px" if err else "")
            + f"; marks where the operator said not in view / hidden: {fa}/{nn}"
            + (f"; fixed objects dropped at {[(round(x), round(y), n) for x, y, n in spots]} (x, y, frames)" if spots else ""))
    report.append(line); print(line, flush=True)

head = (f"BALL SAM3  prompts {PROMPT}, imgsz {IMGSZ}, conf >= {CONF}, mask white >= {WHITE_MIN}, "
        f"size factor {FACTOR:.3f} x calibration")
print(head)
(BALL / "machine.json").write_text(json.dumps(dict(source="ball_sam3.py", factor=FACTOR, cams=machine), indent=0), encoding="utf-8")
(BALL / "BALL_SAM3.txt").write_text("\n".join([head] + report) + "\n", encoding="utf-8")
print("->", BALL / "machine.json")
