# -*- coding: utf-8 -*-
r"""The ground correction refitted with the 2026-09-30 cone supplement - the bundle (camera_fit.npz) is unchanged.

The release's per-camera warp (frame_correction.py: fit-frame inches -> lattice inches, degree 3 for the panos, 1 for
the others, ridge 8 in per term) is refitted for all six cameras JOINTLY, because the new cones are shared unknowns:
  * the 2026-09-18 labels as in the release (cones on stations, cords X24..X456, the straight wall middles);
  * every cone labelled on 2026-09-30 is a TIE POINT: its true position P_j is estimated from all the cameras that
    see it, held to its design position (fit_data.SUPPLEMENT, or LATTICE for a cone left on its station) only by a
    prior of SIGMA_LAYOUT (the layout is known to 5-20 cm: ticks, cones on grass; operator 2026-10-01);
  * the new long cords Y39 / Y201 are lines at their design y with weight CORD_W (a cord on grass bends).
The 2026-09-30 pixels are first carried into the 2026-09-18 pixel frame through each camera's landmark-drift
transform (landmark_drift.py, measured on the same 16:35:10 frame the labels were made on); CH05 / CH06 did not move.
Residuals are inches under soft-L1 (f_scale 3), as in frame_correction.py; OBS_SIGMA scales the priors.

With --balls (the ball sweep, ball_gui.py's export: the operator's marks and the machine marks the operator
accepted), every time step at which two or more cameras saw the ball is a further TIE POINT with no layout prior: the
ball's position B_k at that time is a free unknown, and each camera's mark, pushed to the ground at the ball-centre
height (R_BALL above the ground) and through its warp, must land on it. The cameras' clocks are not known to better
than ~1 s (file names), and the ball moves ~0.2 m/s (p90 0.4), so each camera also gets a time offset tau_c (CH02 is
the reference): its mark at step k is the ball at B_k + tau_c * v_k, v_k the ball's velocity from a first pass with
the release warps. Ball residuals are inches with weight BALL_W, under the same soft-L1.

Checks written beside the result: without the supplement the joint fit must reproduce the release; and a K-fold
over the supplement cones, each fold refitted without its cones, scores those cones (how far apart two cameras put
the same unseen cone, and how far from its design position) against the release on the same cones. With --balls,
a second K-fold over the ball time steps in contiguous blocks (so a held-out block is a stretch of the sweep, i.e. a
region of the paddock the fit has not seen balls in) scores how far apart two cameras put the held-out ball, for
the release, the cone-only refit and the cone+ball refit (each with its own clock offsets fitted on the training
balls).

Usage: python refit_supplement.py --session <09-30 session dir> --out <dir> [--drift <landmark_drift.json>]
                                  [--sigma-layout 4] [--cord-weight 0.5] [--folds 5] [--deg CH03=2,...] [--no-supplement]
                                  [--balls <ball_labels.json>] [--ball-weight 1] [--soft-lattice <in>] [--rel <frame_correction.json>]
--soft-lattice S (2026-10-02, both audits): the 2026-09-18 lattice cones also become shared latent points held to
their design station by a prior of S inches, like the supplement cones, instead of exact targets in each camera's
warp; cords and wall foot stay lines. --rel: the warp used as the starting point and as the "release" baseline in
the checks (default: the one next to the bundle, which after 2026-10-01 is that release; pass
<root>\qc\release_2026-09-24\frame_correction.json to reproduce the historical comparison).
Output: <out>\camera_fit.npz (a copy of the release bundle), frame_correction.json (the refitted warps, loadable
with paddock_map.load(<out>\camera_fit.npz)), REFIT_SUPPLEMENT.txt
"""
import sys, json, shutil, hashlib, itertools, collections
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import ConvexHull

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm, frame_correction as fcorr   # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
if not sess or not opt("--out"):
    raise SystemExit("usage: python refit_supplement.py --session <09-30 dir> --out <dir> [--drift ...]")
S30, Q30 = qc_paths.resolve(sess)
OUT = Path(opt("--out")); OUT.mkdir(parents=True, exist_ok=True)
DRIFT = Path(opt("--drift", str(Q30 / "landmark_drift.json")))
SIGMA_LAYOUT = float(opt("--sigma-layout", "4"))          # in
CORD_W = float(opt("--cord-weight", "0.5"))
FOLDS = int(opt("--folds", "5"))
NO_SUPP = "--no-supplement" in args                       # control: the same model fitted on the 09-18 labels only
BALLS = opt("--balls")
SOFT18 = float(opt("--soft-lattice", "0"))                # in; 0 = the 09-18 cones are exact targets (release)
BALL_W = float(opt("--ball-weight", "1"))
R_BALL, BALL_STEP, TAU_REF, TAU_SIGMA = 105.0, 2.0, "CH02", 2.0   # mm; s between ball frames; reference clock; s prior
OBS_SIGMA = 1.5                                           # in: the scale of a label residual, for the priors
CONE_Z = fcorr.CONE_Z
POS = {**fd.LATTICE, **fd.SUPPLEMENT}

REL = json.loads(Path(opt("--rel", str(Path(pm.FIT).parent / "frame_correction.json"))).read_text(encoding="utf-8"))
cams = pm.load(pm.FIT, correct=False)
names = sorted(cams)
DEG = {c: REL["cameras"][c]["deg"] for c in names}
for item in (opt("--deg", "") or "").split(","):          # e.g. --deg CH03=2,CH04=2: a more flexible warp where a camera now has more points
    if item.strip():
        cc, dd = item.split("="); DEG[cc.strip().upper()] = int(dd)
RIDGE = REL["ridge_in"]
NT = {c: fcorr.terms(np.zeros((1, 2)), DEG[c]).shape[1] for c in names}
base = fcorr.collect(cams)
drift = json.loads(DRIFT.read_text(encoding="utf-8"))["cameras"]


def to_0918(cam, uv):
    """2026-09-30 upright px -> 2026-09-18 upright px (inverse of the landmark-drift similarity)."""
    uv = np.atleast_2d(np.asarray(uv, float))
    d = drift.get(cam)
    if not d:
        return uv
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


# ---------------------------------------------------------------- 2026-09-30 observations in the fit frame (inches)
cone_obs = []                                             # (cam, id, xy_fit_in)
cord_obs = {c: ([], []) for c in names}                   # cam -> (points, target y)
for cam in names:
    for st, uv in qc_paths.load_cones(Q30, cam, S30).items():
        if st in POS:
            g = cams[cam].to_paddock(to_0918(cam, uv)[0], z_mm=CONE_Z, units="in")
            if np.isfinite(g).all():
                cone_obs.append((cam, st, np.asarray(g, float)))
    f = Q30 / f"line_labels_{cam}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(S30, cam); dw, dh = d.get("frame_size_upright", [uw, uh])
        for k, v in d["lines"].items():
            if k.startswith("Y") and v:
                g = cams[cam].to_paddock(to_0918(cam, np.asarray(v, float) * [uw / float(dw), uh / float(dh)]), z_mm=0.0, units="in")
                g = g[np.isfinite(g).all(1)]
                cord_obs[cam][0].extend(g.tolist()); cord_obs[cam][1].extend([float(k[1:])] * len(g))


# ---------------------------------------------------------------- the ball sweep (tie points with a clock offset per camera)
ball_obs = []                                             # (cam, k, xy_fit_in at the ball-centre height)
if BALLS:
    for l in json.loads(Path(BALLS).read_text(encoding="utf-8"))["labels"]:
        if l["verdict"] == "ball" and l.get("centre") and l.get("method") != "machine-unchecked":
            g = cams[l["cam"]].to_paddock(to_0918(l["cam"], l["centre"])[0], z_mm=R_BALL, units="in")
            if np.isfinite(g).all():
                ball_obs.append((l["cam"], int(l["k"]), np.asarray(g, float)))
TAU_CAMS = [c for c in names if c != TAU_REF and any(o[0] == c for o in ball_obs)]


def ball_velocity(W):
    """in/s per time step from the mean of the cameras' warped marks; central difference, else one-sided, else 0."""
    m = collections.defaultdict(list)
    for c, k, g in ball_obs:
        m[k].append(fcorr.warp(g[None], W[c], DEG[c])[0])
    P = {k: np.mean(v, 0) for k, v in m.items()}
    V = {}
    for k in P:
        if k - 1 in P and k + 1 in P:
            V[k] = (P[k + 1] - P[k - 1]) / (2 * BALL_STEP)
        elif k + 1 in P:
            V[k] = (P[k + 1] - P[k]) / BALL_STEP
        elif k - 1 in P:
            V[k] = (P[k] - P[k - 1]) / BALL_STEP
        else:
            V[k] = np.zeros(2)
    return V


def multi(ks):
    """the ball observations at the steps in ks that two or more cameras saw, and those steps."""
    obs = [o for o in ball_obs if o[1] in ks]
    n = collections.Counter(k for _, k, _ in obs)
    keep = sorted(k for k in n if n[k] >= 2)
    return [o for o in obs if n[o[1]] >= 2], keep


def _terms(c, pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    return pts, (fcorr.terms(pts, DEG[c]) if len(pts) else np.zeros((0, NT[c])))


IDS18 = set()                                             # --soft-lattice: the 09-18 cones as shared latent points
if SOFT18 > 0:
    REV = {tuple(np.round(np.asarray(v, float), 3)): k for k, v in fd.LATTICE.items()}
    for c in names:
        pts, tgt, kind, grp = base[c]
        isp = kind == "p"
        for g, t in zip(pts[isp], tgt[isp]):
            j = REV[tuple(np.round(t, 3))] + "@0918"
            cone_obs.append((c, j, np.asarray(g, float))); IDS18.add(j); POS[j] = fd.LATTICE[j[:-5]]
        base[c] = (pts[~isp], tgt[~isp], kind[~isp], grp[~isp])

PRE = {}                                                  # per camera: fixed points and their polynomial terms
for _c in names:
    _p, _t, _k, _ = base[_c]
    _p, _T = _terms(_c, _p)
    _cp, _Tc = _terms(_c, cord_obs[_c][0])
    PRE[_c] = dict(p=_p, T=_T, t=np.asarray(_t, float).reshape(-1, 2), mx=np.isin(_k, ["p", "x"]), my=np.isin(_k, ["p", "y"]),
                   cp=_cp, Tc=_Tc, cy=np.asarray(cord_obs[_c][1], float))


def solve(use_ids, use_cords=True, ball_ks=(), V=None, W_fixed=None):
    """joint fit; use_ids = the supplement cone IDs whose observations enter, ball_ks = the ball time steps that enter
    (V = ball velocity per step). W_fixed: keep these warps and fit only the ball positions and clock offsets.
    Returns (coef per cam, P per id, tau per cam)."""
    ids = sorted(set(use_ids) | IDS18)
    jx = {j: i for i, j in enumerate(ids)}
    obs = [(c, j, g) for c, j, g in cone_obs if j in jx]
    design = np.array([POS[j] for j in ids], float).reshape(-1, 2)
    bobs, bks = multi(set(ball_ks))
    jb = {k: i for i, k in enumerate(bks)}
    W_init = W_fixed or REL_W
    b0 = np.array([np.mean([fcorr.warp(g[None], W_init[c], DEG[c])[0] for c, kk, g in bobs if kk == k], 0) for k in bks]).reshape(-1, 2)
    warps0 = [] if W_fixed else [np.concatenate([W_init[c][0], W_init[c][1]]) for c in names]
    x0 = np.concatenate(warps0 + [design.ravel() if not W_fixed else np.zeros(0), b0.ravel(), np.zeros(len(TAU_CAMS) if bks else 0)])

    def split(x):
        W, o = {}, 0
        if W_fixed:
            W = W_fixed
        else:
            for c in names:
                W[c] = x[o:o + 2 * NT[c]].reshape(2, NT[c]); o += 2 * NT[c]
        nP = 0 if W_fixed else 2 * len(ids)
        P = x[o:o + nP].reshape(-1, 2); o += nP
        B = x[o:o + 2 * len(bks)].reshape(-1, 2); o += 2 * len(bks)
        tau = dict(zip(TAU_CAMS, x[o:])) if bks else {}
        return W, P, B, tau

    # observations grouped per camera, with their polynomial terms, so a residual is a few matrix products
    GB = {}
    for c in names:
        sel = [(k, g) for cc, k, g in bobs if cc == c]
        if sel:
            g, T = _terms(c, [g for _, g in sel])
            GB[c] = (g, T, np.array([jb[k] for k, _ in sel]), np.array([V[k] for k, _ in sel]))
    GC = {}
    for c in names:
        sel = [(j, g) for cc, j, g in obs if cc == c]
        if sel:
            g, T = _terms(c, [g for _, g in sel])
            GC[c] = (g, T, np.array([jx[j] for j, _ in sel]))

    def wp(g, T, Wc):
        return g + np.stack([T @ Wc[0], T @ Wc[1]], 1)

    def resid(x):
        W, P, B, tau = split(x)
        r = [np.zeros(0)]
        for c, (g, T, ib, v) in GB.items():
            r.append((BALL_W * (wp(g, T, W[c]) - B[ib] - tau.get(c, 0.0) * v)).ravel())
        if bks:
            r.append(np.array(list(tau.values())) / TAU_SIGMA)
        if W_fixed:
            return np.concatenate(r)
        for c in names:
            pc = PRE[c]
            if len(pc["p"]):
                w = wp(pc["p"], pc["T"], W[c])
                r.append(w[pc["mx"], 0] - pc["t"][pc["mx"], 0]); r.append(w[pc["my"], 1] - pc["t"][pc["my"], 1])
            r.append(W[c].ravel() / RIDGE)
            if use_cords and len(pc["cp"]):
                r.append(CORD_W * (wp(pc["cp"], pc["Tc"], W[c])[:, 1] - pc["cy"]))
        for c, (g, T, ij) in GC.items():
            r.append((wp(g, T, W[c]) - P[ij]).ravel())
        if len(ids):
            sig = np.array([SOFT18 if j in IDS18 else SIGMA_LAYOUT for j in ids])[:, None]
            r.append(((P - design) * (OBS_SIGMA / sig)).ravel())
        return np.concatenate(r)

    sol = least_squares(resid, x0, loss="soft_l1", f_scale=3.0)
    W, P, B, tau = split(sol.x)
    return W, dict(zip(ids, P)), tau


def ball_score(W, tau, ks, V):
    """held-out ball steps ks: (pairwise distance between two cameras' marks after the clock offsets (in), pair names)."""
    bobs, bks = multi(set(ks))
    at = collections.defaultdict(dict)
    for c, k, g in bobs:
        at[k][c] = fcorr.warp(g[None], W[c], DEG[c])[0] - tau.get(c, 0.0) * V[k]
    d, pn = [], []
    for k, v in at.items():
        for a, b in itertools.combinations(sorted(v), 2):
            d.append(np.hypot(*(v[a] - v[b]))); pn.append(f"{a}-{b}")
    return np.array(d), np.array(pn)


def mapped(W, c, g):
    return fcorr.warp(np.asarray(g)[None], W[c], DEG[c])[0]


def score(W, ids):
    """for the cones in ids: pairwise camera disagreement and distance to design (inches)."""
    pos = {}
    for c, j, g in cone_obs:
        if j in ids:
            pos.setdefault(j, {})[c] = mapped(W, c, g)
    pair = [np.hypot(*(d[a] - d[b])) for d in pos.values() for a, b in itertools.combinations(sorted(d), 2)]
    des = [np.hypot(*(p - POS[j])) for j, d in pos.items() for p in d.values()]
    return np.array(pair), np.array(des)


MM = 25.4
REL_W0 = {c: np.array([REL["cameras"][c]["cx"], REL["cameras"][c]["cy"]]) for c in names}
DEG0 = {c: REL["cameras"][c]["deg"] for c in names}
REL_W = {c: np.pad(REL_W0[c], ((0, 0), (0, NT[c] - REL_W0[c].shape[1]))) for c in names}   # the release, in the requested degree
V0 = ball_velocity(REL_W) if ball_obs else {}
ALL_KS = sorted({k for _, k, _ in ball_obs})
L = [f"REFIT OF THE GROUND CORRECTION WITH THE 2026-09-30 SUPPLEMENT  (bundle unchanged: {pm.FIT})",
     f"{len(cone_obs)} cone observations of {len({j for _, j, _ in cone_obs})} cones, "
     f"{sum(len(v[0]) for v in cord_obs.values())} cord points (Y39/Y201); prior {SIGMA_LAYOUT} in on the layout, cord weight {CORD_W}; "
     f"09-30 pixels carried to 09-18 through {DRIFT.name}"]
if ball_obs:
    _bo, _bk = multi(set(ALL_KS))
    L.append(f"ball sweep {Path(BALLS).name}: {len(ball_obs)} marks, {len(_bk)} time steps seen by 2+ cameras ({len(_bo)} marks) as tie "
             f"points, weight {BALL_W}, clock offsets for {', '.join(TAU_CAMS)} (reference {TAU_REF})")
L.append("")

# 1. sanity: no supplement -> the release
W0, _, _ = solve(set(), use_cords=False)
from matplotlib.path import Path as MPath
_G = np.array([[x, y] for x in range(0, 481, 12) for y in range(0, 241, 12)], float)
dmax = max(float(np.abs(fcorr.terms(g, DEG[c]) @ (W0[c] - REL_W[c]).T).max())
           for c in names for g in [_G[MPath(np.asarray(REL["cameras"][c]["support"], float)).contains_points(_G)]])
L.append(f"1. without the supplement the joint fit differs from the release by at most {dmax * MM:.1f} mm inside each camera's "
         f"support ({'the release itself' if all(DEG[c] == DEG0[c] for c in names) else 'a different warp degree for ' + ', '.join(c for c in names if DEG[c] != DEG0[c])})")

# 2. K-fold over the supplement cones: held-out cones, new fit vs release
all_ids = sorted({j for _, j, _ in cone_obs} - IDS18)
rng = np.random.default_rng(0)
order = rng.permutation(all_ids)
folds = [set(order[i::FOLDS]) for i in range(FOLDS)]
hp_new, hd_new, hp_rel, hd_rel = [], [], [], []
for i, fo in enumerate(folds):
    Wf, _, _ = solve(set(all_ids) - fo, ball_ks=ALL_KS, V=V0)
    p, d = score(Wf, fo); hp_new += list(p); hd_new += list(d)
    p, d = score(REL_W, fo); hp_rel += list(p); hd_rel += list(d)
q = lambda a: f"median {np.median(a) * MM:4.0f} mm, p90 {np.percentile(a, 90) * MM:4.0f}, max {np.max(a) * MM:4.0f}" if len(a) else "-"
L += [f"2. HELD-OUT supplement cones ({FOLDS} folds; each fold refitted without its cones"
      + (", all balls in" if ball_obs else "") + "):",
      f"   two cameras on the same unseen cone   release: {q(np.array(hp_rel))}   (n {len(hp_rel)})",
      f"                                         refit:   {q(np.array(hp_new))}",
      f"   a camera's cone vs its design position release: {q(np.array(hd_rel))}   (n {len(hd_rel)})",
      f"                                         refit:   {q(np.array(hd_new))}"]

# 2b. K-fold over the ball steps in contiguous blocks: held-out balls, release / cone-only refit / cone+ball refit
if ball_obs:
    _, mk = multi(set(ALL_KS))
    blocks = np.array_split(np.array(mk), FOLDS)
    Wc, _, _ = solve(set(all_ids))                           # the cone-only refit (balls not used)
    acc = {m: ([], []) for m in ("release", "cone refit", "cone+ball refit")}
    for blk in blocks:
        test = set(blk.tolist()); train = [k for k in ALL_KS if k not in test]
        for m, Wm in (("release", REL_W), ("cone refit", Wc), ("cone+ball refit", None)):
            if Wm is None:
                Wm, _, tm = solve(set(all_ids), ball_ks=train, V=V0)
            else:
                _, _, tm = solve(set(), ball_ks=train, V=V0, W_fixed=Wm)
            d, pn = ball_score(Wm, tm, test, V0)
            acc[m][0].extend(d); acc[m][1].extend(pn)
    L.append(f"2b. HELD-OUT balls ({FOLDS} contiguous blocks of the sweep; clock offsets fitted on the training balls each time):")
    for m, (d, pn) in acc.items():
        d, pn = np.array(d), np.array(pn)
        per = "  ".join(f"{pp} {np.median(d[pn == pp]) * MM:.0f}" for pp in sorted(set(pn)) if (pn == pp).sum() >= 4)
        L.append(f"   {m:16} two cameras on the same unseen ball: {q(d)}   (n {len(d)})")
        L.append(f"   {'':16} per pair (median mm, pairs with >= 4): {per}")

# 3. the fit with everything (or, with --no-supplement, the same model on the 09-18 labels alone)
W, P, TAU = solve(set(all_ids), ball_ks=ALL_KS, V=V0)
if NO_SUPP:
    W, _, _ = solve(set(), use_cords=False)
    L.append("   --no-supplement: the written correction is fitted WITHOUT the 2026-09-30 cones and cords (a control)")
p, d = score(W, set(all_ids))
off = np.array([np.hypot(*(P[j] - POS[j])) for j in all_ids])
L += [f"3. ALL supplement cones in (training): two cameras on the same cone {q(p)}; vs design {q(d)}",
      f"   estimated cone positions vs design (the layout as the cameras see it): {q(off)}",
      "   largest: " + ", ".join(f"{j} {o * MM:.0f} mm" for j, o in sorted(zip(all_ids, off), key=lambda t: -t[1])[:8])]
if ball_obs:
    d, _ = ball_score(W, TAU, ALL_KS, V0)
    L.append(f"   balls (training): two cameras on the same ball {q(d)}; clock offsets " +
             ", ".join(f"{c} {t:+.2f} s" for c, t in TAU.items()) + f" (vs {TAU_REF})")
from matplotlib.path import Path as MPath
GRID = np.array([[x, y] for x in range(0, 481, 12) for y in range(0, 241, 12)], float)
for c in names:
    inside = GRID[MPath(np.asarray(REL["cameras"][c]["support"], float)).contains_points(GRID)]
    shift = np.hypot(*(fcorr.terms(inside, DEG[c]) @ (W[c] - REL_W[c]).T).T) * MM
    L.append(f"   {c}: correction moved by median {np.median(shift):4.0f} mm, max {shift.max():4.0f} mm (inside the release's support)")

# write: bundle copy + frame_correction.json in the release schema
shutil.copy2(pm.FIT, OUT / "camera_fit.npz")
out = dict(fit_sha256=hashlib.sha256((OUT / "camera_fit.npz").read_bytes()).hexdigest(),
           note=REL["note"].split(" | ")[0] + " | refitted jointly with the 2026-09-30 supplement (refit_supplement.py)"
                + (f"; 09-18 lattice cones latent, prior {SOFT18} in" if SOFT18 > 0 else "") + (f"; balls weight {BALL_W}" if ball_obs else ""),
           soft_lattice_in=SOFT18 if SOFT18 > 0 else None, baseline_warp=str(opt("--rel", Path(pm.FIT).parent / "frame_correction.json")),
           fit=str(OUT / "camera_fit.npz"), ridge_in=RIDGE, deg_pano=REL["deg_pano"], held_out_groups=[],
           balls=dict(labels=str(BALLS), weight=BALL_W, n_marks=len(ball_obs), clock_offset_s={c: float(t) for c, t in TAU.items()},
                      reference=TAU_REF) if ball_obs else None,
           supplement=dict(session=S30.name, drift=str(DRIFT), sigma_layout_in=SIGMA_LAYOUT, cord_weight=CORD_W,
                           cones={j: dict(design=list(POS[j]), estimated=[round(float(v), 2) for v in P[j]]) for j in all_ids}),
           cameras={})
for c in names:
    pts = list(base[c][0]) + [g for cc, _, g in cone_obs if cc == c] + list(cord_obs[c][0]) + [g for cc, _, g in ball_obs if cc == c]
    pts = np.asarray(pts, float)
    hull = pts[ConvexHull(pts).vertices]; ctr = hull.mean(0); vec = hull - ctr
    hull = ctr + vec * (1 + 12.0 / np.maximum(np.linalg.norm(vec, axis=1), 1e-9))[:, None]
    before = fcorr.residual_of(fcorr.warp(base[c][0], REL_W[c], DEG[c]), base[c][1], base[c][2])
    after = fcorr.residual_of(fcorr.warp(base[c][0], W[c], DEG[c]), base[c][1], base[c][2])
    out["cameras"][c] = dict(deg=DEG[c], cx=[float(v) for v in W[c][0]], cy=[float(v) for v in W[c][1]],
                             support=[[round(float(a), 2), round(float(b), 2)] for a, b in hull],
                             n_points=int((base[c][2] == "p").sum()) + sum(1 for cc, j, _ in cone_obs if cc == c and j in IDS18),
                             n_cord=int((base[c][2] == "x").sum()),
                             n_wall_y=int((base[c][2] == "y").sum()),
                             n_supplement_cones=sum(1 for cc, _, _ in cone_obs if cc == c), n_supplement_cord=len(cord_obs[c][0]),
                             rms_release_on_0918_labels_in=float(np.sqrt((before ** 2).mean())),
                             rms_refit_on_0918_labels_in=float(np.sqrt((after ** 2).mean())))
    L.append(f"   {c}: 09-18 labels rms {np.sqrt((before ** 2).mean()):.2f} in (release) -> {np.sqrt((after ** 2).mean()):.2f} in (refit); "
             f"{out['cameras'][c]['n_supplement_cones']} supplement cones, {len(cord_obs[c][0])} cord points")
(OUT / "frame_correction.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
(OUT / "REFIT_SUPPLEMENT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", OUT)
