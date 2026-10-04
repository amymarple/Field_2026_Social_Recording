# -*- coding: utf-8 -*-
r"""Ball detector for the ball sweep, taught by the operator's marks; its output is reviewed in ball_gui.html.

The ball (white with navy and red panels, pushed with a stick whose white tip sits next to it) is found per camera
and frame from four things, the first two learnt from the operator's ball_labels.json:
  colour   a likelihood ratio, ball vs everything else, over HSV (inside the operator's ellipses vs the rest of
           the same frames); cones, grass, people and the stick tip score low;
  size     the radius the calibration predicts for a ball of radius R_BALL at each pixel, times a factor fitted
           to the operator's radii;
  motion   difference from the camera's median background (cones, houses and poles drop out);
  path     a Viterbi pass through time: the ball moves at most a few diameters between two frames, and
           "not in view" is a state of its own.
The chosen blob is refined at full resolution by an ellipse fitted to its outline.
The check against the operator's marks (detection rate, centre error, false alarms on "not in view" / "hidden")
is printed and written beside the output; marks used to learn the colour are scored too, so read it as a
consistency check, and judge the rest by eye in the GUI.

Usage: python ball_detect.py --labels <ball_labels.json> [--ball <qc ball dir>] [--cams CH01,...]
Output: <ball dir>\machine.json (read by ball_gui.py), BALL_DETECT.txt
"""
import sys, json
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
BALL = Path(opt("--ball", str(qc_paths.QC_ROOT / "2026-09-30" / "ball")))
LABELS = json.loads(Path(opt("--labels")).read_text(encoding="utf-8"))
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
CAMS = opt("--cams", ",".join(c["cam"] for c in jobs["cams"])).split(",")
R_BALL = 105.0                       # mm; the factor fitted below absorbs the exact size
DS = 2                               # detection runs at half resolution
HB, SB, VB = 30, 16, 8               # HSV histogram bins
cams = pm.load()
NT = len(jobs["clocks"])


def path_of(cam, k):
    return BALL / cam / f"{cam}_{k:04d}.jpg"


def hsv_idx(img):
    h = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return (h[..., 0].astype(np.int32) * HB // 180) * SB * VB + (h[..., 1].astype(np.int32) * SB // 256) * VB + h[..., 2].astype(np.int32) * VB // 256


def ell_mask(shape, L, shrink=1.0):
    m = np.zeros(shape, np.uint8)
    e = L.get("ellipse")
    if e:
        cv2.ellipse(m, ((e["cx"], e["cy"]), (2 * e["a"] * shrink, 2 * e["b"] * shrink), np.degrees(e["theta_rad"])), 255, -1)
    elif L.get("r"):
        cv2.circle(m, (int(L["centre"][0]), int(L["centre"][1])), int(L["r"] * shrink), 255, -1)
    return m > 0


# ---------------------------------------------------------------- colour model from the operator's ellipses
balls = [L for L in LABELS["labels"] if L["verdict"] == "ball" and (L.get("ellipse") or L.get("r"))]
hb = np.zeros(HB * SB * VB); hg = np.zeros(HB * SB * VB)
for L in balls:
    img = cv2.imread(str(path_of(L["cam"], L["k"])))
    idx = hsv_idx(img)
    inside = ell_mask(img.shape[:2], L, 0.85)
    outside = ~ell_mask(img.shape[:2], L, 1.3)
    hb += np.bincount(idx[inside], minlength=hb.size)
    sub = idx[outside][::7]
    hg += np.bincount(sub, minlength=hg.size)
pb = (hb + 1) / (hb.sum() + hb.size); pg = (hg + 1) / (hg.sum() + hg.size)
LLR = np.log(pb / pg).astype(np.float32)                                  # per-bin log likelihood ratio


# ---------------------------------------------------------------- predicted radius (px) of the ball at a pixel
def pred_radius(cam, uv):
    """radius in full-res px of a sphere of R_BALL whose centre the pixel looks at (raw bundle frame: a radius
    is a local scale, the ground correction does not change it)."""
    c = cams[cam]
    uv = np.atleast_2d(np.asarray(uv, float))
    d = c.rays(uv)
    s = (R_BALL - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    out = []
    for off in ([R_BALL, 0, 0], [0, R_BALL, 0], [0, 0, R_BALL]):
        q = pm.fm.project(c.model, c.intr, (X + off) @ c.R.T + c.tvec)
        out.append(np.linalg.norm(q - uv, axis=1))
    r = np.mean(out, axis=0)
    r[~((s > 0) & np.isfinite(s))] = np.nan
    return r


ratios = []
for L in balls:
    if L.get("r"):
        p = pred_radius(L["cam"], L["centre"])[0]
        if np.isfinite(p) and p > 0:
            ratios.append(L["r"] / p)
FACTOR = float(np.median(ratios)) if ratios else 1.0


def radius_map(cam, h, w):
    gy, gx = np.mgrid[0:h:16, 0:w:16]
    r = pred_radius(cam, np.stack([gx.ravel() * DS, gy.ravel() * DS], 1)).reshape(gx.shape) * FACTOR / DS
    r = np.where(np.isfinite(r), r, np.nanmedian(r))
    return cv2.resize(r.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


# ---------------------------------------------------------------- detection per camera
def refine(img_full, u, v, r):
    """ellipse fitted to the outline of the ball-coloured, moving blob around (u, v) at full resolution."""
    x0, y0 = int(max(0, u - 2.2 * r)), int(max(0, v - 2.2 * r))
    x1, y1 = int(min(img_full.shape[1], u + 2.2 * r)), int(min(img_full.shape[0], v + 2.2 * r))
    win = img_full[y0:y1, x0:x1]
    if win.size == 0:
        return None
    m = (LLR[hsv_idx(win)] > 0.5).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, int(r / 4)) | 1,) * 2))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    i = 1 + int(np.argmin([np.hypot(*(cen[j] - [u - x0, v - y0])) - 0.02 * st[j, 4] for j in range(1, n)]))
    cnts, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cnts, key=len)
    if len(cnt) < 8:
        return None
    (ex, ey), (A, B), ang = cv2.fitEllipse(cnt)
    a, b = max(A, B) / 2, min(A, B) / 2
    if not (0.45 * r < (a + b) / 2 < 1.6 * r) or a > 2.2 * b:
        return None
    th = np.radians(ang + (90 if B > A else 0))
    return dict(cx=float(ex + x0), cy=float(ey + y0), a=float(a), b=float(b), th=float(th))


machine, report = {}, []
for cam in CAMS:
    files = [path_of(cam, k) for k in range(NT)]
    small = [cv2.resize(cv2.imread(str(f)), None, fx=1 / DS, fy=1 / DS, interpolation=cv2.INTER_AREA) for f in files]
    h, w = small[0].shape[:2]
    bg = np.median(np.stack(small[::3]), axis=0).astype(np.uint8)
    bglab = cv2.cvtColor(bg, cv2.COLOR_BGR2LAB).astype(np.int16)
    rmap = radius_map(cam, h, w)
    sig_levels = np.array([3, 5, 8, 12, 18, 26, 36], float)
    choose = np.argmin(np.abs(sig_levels[None, None, :] - (rmap[..., None] * 0.6)), axis=2)
    cands = []
    for k, im in enumerate(small):
        fg = np.abs(cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.int16) - bglab).max(axis=2) > 18
        S = np.clip(LLR[hsv_idx(im)], 0, None) * fg
        resp = np.zeros((h, w), np.float32)
        for j, sg in enumerate(sig_levels):
            sel = choose == j
            if sel.any():
                resp[sel] = cv2.GaussianBlur(S, (0, 0), sg)[sel]
        mx = cv2.dilate(resp, np.ones((9, 9), np.uint8))
        ys, xs = np.nonzero((resp == mx) & (resp > 0.15))
        order = np.argsort(-resp[ys, xs])[:6]
        cands.append([(float(xs[i]), float(ys[i]), float(resp[ys[i], xs[i]])) for i in order])
    # Viterbi: state 0 = not in view, then up to 6 candidates per frame
    INF = 1e9
    def emis(c):
        return -np.log(min(c[2], 3.0) / 3.0 + 1e-3)
    ABSENT, SWITCH = 2.0, 2.5
    cost = [[ABSENT] + [emis(c) for c in cands[0]]]
    back = []
    for k in range(1, NT):
        prev, cur = cands[k - 1], cands[k]
        row, bk = [], []
        opts0 = [cost[-1][0]] + [cost[-1][i + 1] + SWITCH for i in range(len(prev))]
        j0 = int(np.argmin(opts0)); row.append(opts0[j0] + ABSENT); bk.append(j0)
        for c in cur:
            r = float(rmap[int(c[1]), int(c[0])])
            opts = [cost[-1][0] + SWITCH]
            for i, p in enumerate(prev):
                dist = np.hypot(c[0] - p[0], c[1] - p[1]) / max(r, 2.0)
                opts.append(cost[-1][i + 1] + 0.08 * dist ** 2 if dist < 12 else INF)
            j = int(np.argmin(opts)); row.append(opts[j] + emis(c)); bk.append(j)
        cost.append(row); back.append(bk)
    s = int(np.argmin(cost[-1])); path = [s]
    for k in range(NT - 1, 0, -1):
        s = back[k - 1][s]; path.append(s)
    path = path[::-1]
    machine[cam] = {}
    for k, s in enumerate(path):
        if s == 0:
            continue
        u, v, sc = cands[k][s - 1]
        r = float(rmap[int(v), int(u)]) * DS
        e = refine(cv2.imread(str(files[k])), u * DS, v * DS, r)
        machine[cam][k] = dict(e, score=sc, method="machine-ellipse") if e else \
            dict(cx=u * DS, cy=v * DS, a=r, b=r, th=0.0, score=sc, method="machine-blob")
    # check against the operator
    mine = [L for L in LABELS["labels"] if L["cam"] == cam]
    hit, err, miss, fa, n_b, n_n = 0, [], 0, 0, 0, 0
    for L in mine:
        m = machine[cam].get(L["k"])
        if L["verdict"] == "ball" and L.get("centre"):
            n_b += 1
            rr = L["r"] or float(rmap[int(L["centre"][1] / DS), int(L["centre"][0] / DS)]) * DS
            if m and np.hypot(m["cx"] - L["centre"][0], m["cy"] - L["centre"][1]) < 0.6 * rr:
                hit += 1; err.append(np.hypot(m["cx"] - L["centre"][0], m["cy"] - L["centre"][1]))
            else:
                miss += 1
        elif L["verdict"] in ("not visible", "hidden"):
            n_n += 1; fa += int(m is not None)
    line = (f"{cam}: machine marks in {len(machine[cam])}/{NT} frames;  against the operator: balls found {hit}/{n_b}"
            + (f", centre error median {np.median(err):.1f} px, max {max(err):.1f} px" if err else "")
            + f";  marks where the operator said not in view / hidden: {fa}/{n_n}")
    report.append(line); print(line, flush=True)

head = [f"BALL DETECT  colour model from {len(balls)} operator ellipses, size factor {FACTOR:.3f} x calibration "
        f"(R_BALL {R_BALL:.0f} mm, {len(ratios)} radii)"]
print(head[0])
(BALL / "machine.json").write_text(json.dumps(dict(factor=FACTOR, cams={c: {str(k): v for k, v in d.items()} for c, d in machine.items()}),
                                              indent=0), encoding="utf-8")
(BALL / "BALL_DETECT.txt").write_text("\n".join(head + report) + "\n", encoding="utf-8")
print("->", BALL / "machine.json")
