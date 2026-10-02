# -*- coding: utf-8 -*-
r"""Ball centres refined against the image: the calibration predicts the ball's outline, only its position is searched.

Why: SAM 3's mask (ball_sam3.py) often covers only part of the ball - one panel between two stripes when the ball is
close to a pano, the coloured half when it lies against the white wall or house, the top half when grass hides the
bottom - and an ellipse fitted to a partial mask is too small and off to one side. On the operator's own drawings
(2026-10-01) the machine centre was 6-7 px off on the panos (31 mm on the ground, p90 60 mm), its radius 5-8 % small.

What is known: the ball is a sphere of radius R_BALL whose centre sits R_BALL above the ground. For a candidate
pixel centre, the ray through it meets the plane z = R_BALL at the sphere centre X; the sphere's outline in the
image is then exact for any central lens model: the circle where the rays from the camera centre graze the sphere
(centre X - R^2 v / |v|^2, radius R sqrt(1 - R^2 / |v|^2), v = X - camera centre), projected through the lens. So
the predicted outline is an ellipse of the right size, shape and tilt everywhere, including the panos' stretched
corners, and only (u, v) is free.

Score of a candidate: the outline is sampled at N_OUT points; at each, "grass" is read just outside and just inside
(DELTA x the predicted radius along the normal) and the score is the mean over the whole outline of outside minus
inside. "grass" is the chromatic excess green (2G - R - B) / (R + G + B) pushed through a ramp to 0..1, so the ball's
white, red, blue and black panels are all "not grass" alike: a first version used the raw excess-green gradient,
and the red / blue -> white panel boundaries inside the ball outscored the ball's own edge (CH03 frame 21 moved
28 px off a clean ball). Where the ball's edge is hidden (grass in front: grass on both sides; the white wall or
house behind: not-grass on both sides) a point scores 0 rather than pulling. Search: a grid of +-0.6 r around the
starting centre, then a finer grid around the best. The outline's size may scale by KAPPA (+-10 %): where the
calibration's predicted size is a few per cent off, a fixed size hugs one side of the ball (CH01 frame 135, 7 %
small). SUPPORT = the fraction of outline points with a clear grass-outside / ball-inside step says how much of the
edge actually constrained the answer; grass hiding the ball's bottom makes a false edge that pushes the circle up,
and such marks have low support (CH01 frame 159: 0.26) - below MIN_SUPPORT the starting centre is kept.

The camera model is the bundle's (camera_fit.npz, the same for every ground correction); 09-30 pixels are carried
into the 09-18 pixel frame through the landmark-drift similarity (landmark_drift.json) for the model, and back to
sample the 09-30 image. Every mark is refined: the operator's drawings, the machine marks the operator accepted,
and the unchecked machine marks; starting from the operator's and from the machine's centre separately where both
exist, so the two can be compared.

Result (2026-10-01, session_2026-09-30_ball_refine_check.txt): NOT USED. The refinement is repeatable (from the
machine's start and the operator's it lands within 1 px in 80-100 % of marks) but it moves the operator's centres
up by 4-7 px on CH01-CH03: where grass hides the ball's lower part, the grass line becomes the lower edge, and the
operator, who completes the hidden arc by eye, is closer. Judged by how well cameras agree on the same ball, the
operator's marks (plus the machine marks the operator accepted) give 87 mm, every refined variant 88-109 mm. Kept
because the outline prediction (`outlines`) is right and useful elsewhere: the predicted size matches the operator's
radius within a few per cent on CH03 / CH04 (size factor median 1.00 / 0.99).

Usage: python ball_refine.py --labels <ball_labels.json> [--ball <qc ball dir>] [--drift <landmark_drift.json>]
                             [--z-hide <mm>] [--kappa-lo 0.9] [--kappa-hi 1.1] [--out-name ball_refined]
Output: <ball dir>\ball_refined.json  {cam: {k: {start: {cx, cy, ...}}}}, BALL_REFINE.txt
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
LABELS = json.loads(Path(opt("--labels")).read_text(encoding="utf-8"))["labels"]
DRIFT = Path(opt("--drift", str(BALL.parent / "landmark_drift.json")))
MACHINE = json.loads((BALL / "machine.json").read_text(encoding="utf-8"))["cams"] if (BALL / "machine.json").exists() else {}
R_BALL = 105.0
N_OUT, SIGMA, DELTA = 72, 1.0, 0.12
KAPPA = np.arange(float(opt("--kappa-lo", "0.90")), float(opt("--kappa-hi", "1.10")) + 1e-6, 0.05)   # outline size factors
MIN_SUPPORT = 0.45
Z_HIDE = float(opt("--z-hide", "0"))                 # mm: outline points lower than this are not scored (grass hides them)
OUT_NAME = opt("--out-name", "ball_refined")
GRASS_LO, GRASS_HI = 0.04, 0.14                    # chromatic excess green: <= LO not grass, >= HI grass
cams = pm.load(pm.FIT, correct=False)
drift = json.loads(DRIFT.read_text(encoding="utf-8"))["cameras"] if DRIFT.exists() else {}


def _sim(cam):
    d = drift.get(cam)
    if not d:
        return None
    th = np.radians(d["rot_deg"])
    return (np.asarray(d["centre_px"], float), np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]),
            float(d["scale"]), np.array([d["dx_px"], d["dy_px"]], float))


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); s = _sim(cam)
    if s is None:
        return uv
    c, R, k, t = s
    return c + (uv - c - t) @ R / k


def from_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); s = _sim(cam)
    if s is None:
        return uv
    c, R, k, t = s
    return c + t + k * (uv - c) @ R.T


def outlines(cam, uv18):
    """candidate centres (n, 2) in 09-18 px -> sphere centres X (n, 3) and outlines (n, N_OUT, 2) in 09-18 px."""
    c = cams[cam]
    d = c.rays(uv18)
    s = (R_BALL - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    v = X - c.centre; D2 = (v ** 2).sum(1)
    Q = X - (R_BALL ** 2 / D2)[:, None] * v
    rho = R_BALL * np.sqrt(1 - R_BALL ** 2 / D2)
    w = v / np.sqrt(D2)[:, None]
    helper = np.where(np.abs(w[:, 2:3]) > 0.9, [[1.0, 0.0, 0.0]], [[0.0, 0.0, 1.0]])   # any axis not along the ray
    e1 = np.cross(w, helper); e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
    e2 = np.cross(w, e1)
    ph = np.linspace(0, 2 * np.pi, N_OUT, endpoint=False)
    P = Q[:, None] + rho[:, None, None] * (np.cos(ph)[None, :, None] * e1[:, None] + np.sin(ph)[None, :, None] * e2[:, None])
    uv = pm.fm.project(c.model, c.intr, P.reshape(-1, 3) @ c.R.T + c.tvec).reshape(len(uv18), N_OUT, 2)
    return X, uv, s > 0, P[..., 2]


def grass(img):
    """0..1 grass likelihood from the chromatic excess green, lightly smoothed."""
    f = cv2.GaussianBlur(img.astype(np.float32), (0, 0), SIGMA)
    exg = (2 * f[..., 1] - f[..., 2] - f[..., 0]) / (f.sum(-1) + 30.0)
    return np.clip((exg - GRASS_LO) / (GRASS_HI - GRASS_LO), 0, 1).astype(np.float32)


def score(cam, cand30, G, x0, y0, delta, kappas=(1.0,)):
    """candidate centres in 09-30 px -> (score, support, kappa, X, outline) with the best size factor per candidate:
    grass outside minus grass inside, outline mean."""
    X, out18, ok, zpt = outlines(cam, to_0918(cam, cand30))
    w = (zpt >= Z_HIDE).astype(np.float32)
    w[w.sum(1) < 8] = 1.0                                               # never fewer than 8 points
    out30 = from_0918(cam, out18.reshape(-1, 2)).reshape(out18.shape)
    nrm = np.roll(out30, -1, 1) - np.roll(out30, 1, 1)                 # tangent; outward normal = rotate, sign by centroid
    nrm = np.stack([nrm[..., 1], -nrm[..., 0]], -1)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    ctr = out30.mean(1, keepdims=True)
    nrm *= np.sign(((out30 - ctr) * nrm).sum(-1, keepdims=True))
    def at(p):
        return cv2.remap(G, (p[..., 0] - x0).astype(np.float32), (p[..., 1] - y0).astype(np.float32), cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0.5)
    S, U = [], []
    for k in kappas:
        o = ctr + k * (out30 - ctr)
        d = at(o + delta * nrm) - at(o - delta * nrm)
        S.append((d * w).sum(1) / w.sum(1)); U.append(((d > 0.5) * w).sum(1) / w.sum(1))
    S, U = np.stack(S, 1), np.stack(U, 1)
    j = np.argmax(S, 1); n = np.arange(len(S))
    sc, sup, kap = S[n, j], U[n, j], np.asarray(kappas)[j]
    sc[~ok] = -np.inf
    out30 = ctr + kap[:, None, None] * (out30 - ctr)
    return sc, sup, kap, X, out30


def refine(cam, img, start):
    """start (u, v) in 09-30 px -> dict with the refined centre, the outline ellipse, the score and the shift."""
    _, out, _, _ = outlines(cam, to_0918(cam, [start]))
    r = float(np.mean(np.linalg.norm(out[0] - out[0].mean(0), axis=1)))     # predicted radius at the start
    H, W = img.shape[:2]
    m = int(2 * r + 20)
    x0, y0 = max(0, int(start[0]) - m), max(0, int(start[1]) - m)
    x1, y1 = min(W, int(start[0]) + m), min(H, int(start[1]) + m)
    G = grass(img[y0:y1, x0:x1]); delta = max(2.0, DELTA * r)
    best, kap = np.asarray(start, float), 1.0
    for half, step, ks in ((0.6 * r, max(1.0, r / 20), KAPPA), (2 * max(1.0, r / 20), 0.5, None)):
        ks = ks if ks is not None else kap + np.array([-0.025, -0.0125, 0, 0.0125, 0.025])
        g = np.arange(-half, half + 1e-9, step)
        cand = best + np.stack(np.meshgrid(g, g), -1).reshape(-1, 2)
        sc, sup, kk, X, out30 = score(cam, cand, G, x0, y0, delta, ks)
        i = int(np.argmax(sc)); best, kap = cand[i], float(kk[i])
    sc0, sup0, _, _, _ = score(cam, np.asarray([start], float), G, x0, y0, delta, KAPPA)
    (ex, ey), (A, B), ang = cv2.fitEllipse(out30[i].astype(np.float32))
    return dict(cx=float(best[0]), cy=float(best[1]), X_fit_mm=[float(v) for v in X[i]], r_pred=r,
                ell=dict(cx=float(ex), cy=float(ey), a=float(max(A, B) / 2), b=float(min(A, B) / 2),
                         th=float(np.radians(ang + (90 if B > A else 0)))),
                kappa=kap, score=float(sc[i]), support=float(sup[i]), score_start=float(sc0[0]), support_start=float(sup0[0]),
                shift_px=float(np.hypot(*(best - start))))


if __name__ == "__main__":
    jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
    starts = {}                                                          # (cam, k) -> {source: (u, v)}
    for L in LABELS:
        if L["verdict"] != "ball" or not L.get("centre"):
            continue
        src = L.get("method") if str(L.get("method", "")).startswith("machine") else "operator"
        starts.setdefault((L["cam"], L["k"]), {})[src] = L["centre"]
    for cam, ms in MACHINE.items():                                      # the machine's own centre wherever it has one
        for k, m in ms.items():
            if (cam, int(k)) in starts:
                starts[(cam, int(k))]["machine"] = [m["cx"], m["cy"]]
    out, t0 = {}, time.time()
    for (cam, k), st in sorted(starts.items()):
        img = cv2.imread(str(BALL / cam / f"{cam}_{k:04d}.jpg"))
        runs = {src: dict(refine(cam, img, np.asarray(uv, float)), start=[float(uv[0]), float(uv[1])]) for src, uv in st.items()}
        best = max(runs.values(), key=lambda r: r["score"])
        label = next((src for src in ("operator", "machine-checked", "machine-unchecked") if src in st), None)
        if best["support"] >= MIN_SUPPORT:
            final = dict(cx=best["cx"], cy=best["cy"], how="refined", support=best["support"], kappa=best["kappa"], ell=best["ell"])
        else:                                                            # too little edge: keep the label's own centre
            uv = st[label] if label else st["machine"]
            final = dict(cx=float(uv[0]), cy=float(uv[1]), how="label kept (low support)", support=best["support"])
        out.setdefault(cam, {})[str(k)] = dict(label=label, final=final, runs=runs)
    print(f"{sum(len(v) for v in out.values())} marks refined in {time.time() - t0:.0f} s")

    lines = ["BALL REFINE  outline predicted from the calibration (sphere R %.0f mm, centre at z = R), size free within "
             "%.0f-%.0f %%, centre searched on the grass-outside / ball-inside step over %d outline points; refined centre "
             "used where support >= %.2f" % (R_BALL, 100 * KAPPA[0], 100 * KAPPA[-1], N_OUT, MIN_SUPPORT)]
    for cam in sorted(out):
        v = list(out[cam].values())
        op = [x for x in v if x["label"] == "operator"]
        kept = sum(1 for x in v if x["final"]["how"] != "refined")
        line = f"{cam}: {len(v)} marks, refined {len(v) - kept}, label kept {kept}"
        if op:
            sh = np.array([np.hypot(x["final"]["cx"] - x["runs"]["operator"]["start"][0], x["final"]["cy"] - x["runs"]["operator"]["start"][1])
                           for x in op])
            line += f"; operator drawings moved median {np.median(sh):.1f} px (p90 {np.percentile(sh, 90):.1f})"
            both = [x for x in op if "machine" in x["runs"]]
            if both:
                conv = np.array([np.hypot(x["runs"]["operator"]["cx"] - x["runs"]["machine"]["cx"],
                                          x["runs"]["operator"]["cy"] - x["runs"]["machine"]["cy"]) for x in both])
                line += (f"; from the machine's start and the operator's the refinement lands within 1 px in "
                         f"{(conv < 1).mean() * 100:.0f} % of {len(both)}")
        kap = np.array([x["final"]["kappa"] for x in v if x["final"]["how"] == "refined"])
        if len(kap):
            line += f"; size factor median {np.median(kap):.3f}"
        lines.append(line)
    (BALL / f"{OUT_NAME}.json").write_text(json.dumps(dict(source="ball_refine.py", r_ball_mm=R_BALL, drift=str(DRIFT),
                                                            min_support=MIN_SUPPORT, z_hide_mm=Z_HIDE, kappa=list(map(float, KAPPA)), cams=out)), encoding="utf-8")
    (BALL / f"{OUT_NAME.upper()}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("->", BALL / f"{OUT_NAME}.json")
