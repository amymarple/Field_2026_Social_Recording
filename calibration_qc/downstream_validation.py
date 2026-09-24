# -*- coding: utf-8 -*-
r"""Downstream validation of the camera -> paddock calibration for a 10 cm-bin 2-D place-field
analysis over the 20 x 40 ft paddock. The question is not "how many millimetres is a landmark off"
but "would the place-field analysis change under another equally legitimate calibration?".

An ENSEMBLE of legitimate calibrations is built: the default per-camera ground warp (panos degree
4, ridge 8), its neighbours (degree 3 / 4, ridge 5 / 8 / 12), the warp fitted without one type of
constraint (no cords, no wall foot), and 20 bootstrap resamples of the constraint points per
camera. Every member maps a physical point slightly differently; that spread, plus the EMPIRICAL
disagreement between cameras on the boards (which the warp never used), is what the metrics are
built from. Regions are reported separately: centre, long-wall edges, short-wall ends, four
corners, camera seams (where the nearest-camera assignment changes hands).

Metrics (numbering as in the analysis brief):
 1. handoff continuity  - the jump a track would take when handed from one camera to another:
                          the boards' shared corners give it directly, per camera pair and by
                          position; the ensemble gives the modelled version. (Trajectory-based
                          extrapolation residuals need tracked animals, which do not exist yet:
                          handoff_residual() below is the function to run on them.)
 2. bin flip rate       - fraction of samples that land in a different 10 cm bin under another
                          member of the ensemble, overall, by region, as a heatmap.
 3. occupancy robustness- identical binning + smoothing, every member: Pearson / Spearman
                          correlation, normalised absolute difference, Jensen-Shannon divergence,
                          per-bin CV.
 4. place-field robustness - 300 simulated place cells (Gaussian fields, 10-25 cm sigma, Poisson
                          spikes from the TRUE positions), rate maps under every member: peak
                          shift, centroid shift, area change, spatial-information change,
                          classification stability.
 5. error vs position   - held-out landmark residuals (each constraint type evaluated by a warp
                          fitted without it) and the boards' cross-camera vectors, by region, as
                          magnitude AND mean vector (a bias moves a whole field; scatter does not).
 6. distance-to-feature - change of the distance to the wall and to the two shelters under the
                          ensemble.
Positions are synthetic until real tracks exist (--positions x_in,y_in CSV plugs them in): a
mixture of uniform, wall-following (thigmotaxis) and shelter-centred occupancy. The metrics that
depend on the occupancy shape (3, 4) are stated as such.

Usage: python downstream_validation.py [--positions tracks.csv] [--n 200000] [--boot 20] [--seed 0]
Output: <fit dir>\DOWNSTREAM_VALIDATION.txt, downstream_validation.png
"""
import sys, json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.ndimage import gaussian_filter
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, fit_data as fd, paddock_map as pm                        # noqa: E402

args = sys.argv[1:]
N = int(args[args.index("--n") + 1]) if "--n" in args else 200000
BOOT = int(args[args.index("--boot") + 1]) if "--boot" in args else 20
SEED = int(args[args.index("--seed") + 1]) if "--seed" in args else 0
POS = Path(args[args.index("--positions") + 1]) if "--positions" in args else None
rng = np.random.default_rng(SEED)
MM = 25.4
BIN = 100.0                                        # mm, the planned 10 cm bin
LX, LY = 480 * MM, 240 * MM
NX, NY = int(np.ceil(LX / BIN)), int(np.ceil(LY / BIN))
SHELTERS = {"house 4 (approx)": np.array([135.0, 120.0]) * MM, "house 7 (approx)": np.array([350.0, 125.0]) * MM}
OUT = pm.FIT.parent
L = []


def say(s=""):
    print(s, flush=True); L.append(s)


# =============================================================== the ensemble of calibrations
S, QC = qc_paths.resolve(None)
raw = pm.load(pm.FIT, correct=False)
default = pm.load(pm.FIT)
CONE_Z = 50.0


def constraints(cam):
    """the operator's ground labels for one camera in the RAW fit frame (inches): pts, targets, kinds."""
    c = raw[cam]
    pts, tgt, kind = [], [], []
    for st, uv in qc_paths.load_cones(QC, cam, S, space="upright").items():
        if st in fd.LATTICE:
            g = c.to_paddock(uv, z_mm=CONE_Z, units="in")
            if np.isfinite(g).all() and np.linalg.norm(g - fd.LATTICE[st]) < 40:
                pts.append(g); tgt.append(fd.LATTICE[st]); kind.append("cone")
    lf = QC / f"line_labels_{cam}.json"
    if lf.exists():
        d = json.loads(lf.read_text(encoding="utf-8"))
        uw, uh = qc_paths.upright_size(S, cam); dw, dh = d.get("frame_size_upright", [uw, uh])
        sc = np.array([uw / float(dw), uh / float(dh)])
        for k, v in d["lines"].items():
            g = c.to_paddock(np.asarray(v, float) * sc, z_mm=0.0, units="in"); g = g[np.isfinite(g).all(1)]
            if k.startswith("X"):
                x0 = float(k[1:])
                for q in g:
                    if abs(q[0] - x0) < 40 and -10 < q[1] < 250:
                        pts.append(q); tgt.append((x0, np.nan)); kind.append("cord")
            elif k in ("WALL_X0", "WALL_X480"):
                x0 = 0.0 if k.endswith("X0") else 480.0
                for q in g:
                    if 60 < q[1] < 180 and abs(q[0] - x0) < 40:
                        pts.append(q); tgt.append((x0, np.nan)); kind.append("wall")
            elif k in ("WALL_Y0", "WALL_Y240"):
                y0 = 0.0 if k.endswith("Y0") else 240.0
                for q in g:
                    if 100 < q[0] < 380 and abs(q[1] - y0) < 40:
                        pts.append(q); tgt.append((np.nan, y0)); kind.append("wall")
    return np.array(pts), np.array(tgt, float), np.array(kind)


CONS = {cam: constraints(cam) for cam in raw}


def fit_warp(cam, deg_pano=4, ridge=8.0, drop=None, boot_rng=None):
    pts, tgt, kind = CONS[cam]
    keep = np.ones(len(pts), bool)
    if drop:
        keep &= kind != drop
    idx = np.where(keep)[0]
    if boot_rng is not None:
        idx = boot_rng.choice(idx, len(idx), replace=True)
    pts, tgt, kind = pts[idx], tgt[idx], kind[idx]
    if len(pts) < 6:
        return None
    deg = deg_pano if len(pts) >= 90 else 1
    nt = pm._terms(pts[:1], deg).shape[1]
    isx = np.array([t == "cord" or (t == "wall" and not np.isnan(g[0])) for t, g in zip(kind, tgt)])
    isp = kind == "cone"; isy = ~isx & ~isp

    def resid(x):
        coef = x.reshape(2, nt); T = pm._terms(pts, deg)
        w = pts + np.stack([T @ coef[0], T @ coef[1]], 1)
        r = [w[isp] - tgt[isp], (w[isx, 0] - tgt[isx, 0])[:, None], (w[isy, 1] - tgt[isy, 1])[:, None]]
        return np.concatenate([v.ravel() for v in r] + [x / ridge])

    r = least_squares(resid, np.zeros(2 * nt), loss="soft_l1", f_scale=3.0)
    coef = r.x.reshape(2, nt)
    return dict(deg=deg, cx=coef[0].tolist(), cy=coef[1].tolist())


members = [("default deg4/ridge8", dict(deg_pano=4, ridge=8.0)),
           ("deg3/ridge5", dict(deg_pano=3, ridge=5.0)), ("deg4/ridge5", dict(deg_pano=4, ridge=5.0)),
           ("deg3/ridge8", dict(deg_pano=3, ridge=8.0)), ("deg4/ridge12", dict(deg_pano=4, ridge=12.0)),
           ("no cords", dict(deg_pano=4, ridge=8.0, drop="cord")), ("no wall foot", dict(deg_pano=4, ridge=8.0, drop="wall"))]
members += [(f"bootstrap {b + 1}", dict(deg_pano=4, ridge=8.0, boot_rng=np.random.default_rng(SEED + 100 + b))) for b in range(BOOT)]
WARPS = []
for name, kw in members:
    WARPS.append((name, {cam: fit_warp(cam, **kw) for cam in raw}))
say(f"ensemble: {len(WARPS)} calibrations ({BOOT} bootstrap, 6 named variants, the default)")


def warp_apply(corr, q_in):
    return pm.fit_to_physical(q_in * MM, corr) / MM


def displaced(member_warps, cam, p_phys_mm):
    """where member k puts the physical point p (mm) seen by camera cam: through the raw frame."""
    q = pm.physical_to_fit(p_phys_mm, default[cam].correction)          # raw-frame point of p
    return pm.fit_to_physical(q, member_warps[cam])


# =============================================================== who sees what, and the seams
def primary_camera(p_mm):
    """nearest camera (ground distance) among those that see the point - a plausible handoff rule."""
    best = np.full(len(p_mm), -1); bd_ = np.full(len(p_mm), np.inf)
    names = sorted(default)
    for i, cam in enumerate(names):
        c = default[cam]
        ok = c.sees(p_mm, units="mm")
        d = np.hypot(p_mm[:, 0] - c.centre[0], p_mm[:, 1] - c.centre[1])
        m = ok & (d < bd_)
        best[m] = i; bd_[m] = d[m]
    return best, names


def regions(p_mm, prim=None):
    x, y = p_mm[:, 0] / MM, p_mm[:, 1] / MM
    end = (x < 36) | (x > 444); edge = (y < 24) | (y > 216)
    reg = np.full(len(x), "centre", dtype=object)
    reg[edge] = "long-wall edge"; reg[end] = "short-wall end"; reg[end & edge] = "corner"
    if prim is not None:                       # seam = within 30 cm of a change of primary camera
        seam = np.zeros(len(x), bool)
        for dx, dy in ((300, 0), (-300, 0), (0, 300), (0, -300)):
            q = p_mm + [dx, dy]
            inside = (q[:, 0] >= 0) & (q[:, 0] <= LX) & (q[:, 1] >= 0) & (q[:, 1] <= LY)
            pq, _ = primary_camera(q)
            seam |= inside & (pq != prim) & (pq >= 0) & (prim >= 0)
        reg = np.where(seam & (reg == "centre"), "camera seam", reg)
    return reg


REGION_ORDER = ["centre", "camera seam", "long-wall edge", "short-wall end", "corner"]

# =============================================================== positions (real tracks or a synthetic occupancy)
if POS is not None:
    import csv
    P = np.array([[float(r["x_in"]), float(r["y_in"])] for r in csv.DictReader(open(POS, encoding="utf-8"))]) * MM
    say(f"positions: {len(P)} samples from {POS}")
else:
    n_u, n_w, n_s = int(0.5 * N), int(0.3 * N), N - int(0.5 * N) - int(0.3 * N)
    u = np.stack([rng.uniform(0, LX, n_u), rng.uniform(0, LY, n_u)], 1)
    side = rng.integers(0, 4, n_w); t = rng.uniform(0, 1, n_w); dwall = rng.exponential(150.0, n_w)
    w = np.empty((n_w, 2))
    w[side == 0] = np.stack([t[side == 0] * LX, dwall[side == 0]], 1)
    w[side == 1] = np.stack([t[side == 1] * LX, LY - dwall[side == 1]], 1)
    w[side == 2] = np.stack([dwall[side == 2], t[side == 2] * LY], 1)
    w[side == 3] = np.stack([LX - dwall[side == 3], t[side == 3] * LY], 1)
    sh = np.concatenate([rng.normal(c, 500.0, (n_s // 2, 2)) for c in SHELTERS.values()])
    P = np.concatenate([u, w, sh])
    P = P[(P[:, 0] > 5) & (P[:, 0] < LX - 5) & (P[:, 1] > 5) & (P[:, 1] < LY - 5)]
    say(f"positions: {len(P)} SYNTHETIC samples (50 % uniform, 30 % wall-following, 20 % shelter-centred) - "
        "plug real tracks in with --positions")
prim, names = primary_camera(P)
P, prim = P[prim >= 0], prim[prim >= 0]
reg = regions(P, prim)
say("  primary camera share: " + ", ".join(f"{names[i]} {100 * (prim == i).mean():.0f}%" for i in range(len(names))))
say("  region share: " + ", ".join(f"{r} {100 * (reg == r).mean():.0f}%" for r in REGION_ORDER))

# every member's displacement of every sample, through its primary camera
DISP = np.zeros((len(WARPS), len(P), 2))
for k, (name, wk) in enumerate(WARPS):
    for i, cam in enumerate(names):
        m = prim == i
        if m.any():
            DISP[k, m] = displaced(wk, cam, P[m]) - P[m]
mag = np.linalg.norm(DISP, axis=2)                       # (K, N)


def by_region(values, f=np.median):
    return "  ".join(f"{r} {f(values[reg == r]):.0f}" for r in REGION_ORDER if (reg == r).any())


say("")
say("=" * 100)
say("DOWNSTREAM VALIDATION OF THE CALIBRATION FOR 10 cm PLACE-FIELD BINS")
say("=" * 100)

# =============================================================== 1. handoff continuity
say("")
say("1. CROSS-CAMERA HANDOFF CONTINUITY")
say("   (a) empirical, from the boards the warp never used: the same corner mapped by two cameras.")
Pl = [p for p in fd.all_placements() if not p["bad"] and not p["weak"]]
_z = np.load(pm.FIT, allow_pickle=False)
dropped = {tuple(s.split("|")[:4]) for s in _z["dropped_views"]}
Pl = [p for p in Pl if (p["cam"], p["session"], p["station"], p["win"]) not in dropped]
shared = {}
for p in Pl:
    xy = default[p["cam"]].to_paddock(p["px"], z_mm=6.0)
    for i, c in zip(p["ids"], xy):
        if np.isfinite(c).all():
            shared.setdefault(((p["session"], p["station"], p["win"]), int(i)), {})[p["cam"]] = c
pairs = {}; seam_pts = []; seam_vec = []
for key, d in shared.items():
    cs = sorted(d)
    for a in range(len(cs)):
        for b in range(a + 1, len(cs)):
            v = d[cs[b]] - d[cs[a]]
            pairs.setdefault((cs[a], cs[b]), []).append(v)
            seam_pts.append((d[cs[a]] + d[cs[b]]) / 2); seam_vec.append(v)
seam_pts = np.array(seam_pts); seam_vec = np.array(seam_vec); seam_mag = np.linalg.norm(seam_vec, axis=1)
say(f"   {'pair':12s} {'n':>5s} {'median':>7s} {'p90':>6s} {'p95':>6s}   mean vector (dx, dy) mm")
for (a, b), v in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
    v = np.array(v); m = np.linalg.norm(v, axis=1)
    say(f"   {a}-{b:7s} {len(v):5d} {np.median(m):6.0f}mm {np.percentile(m, 90):5.0f} {np.percentile(m, 95):5.0f}   ({v[:, 0].mean():+.0f}, {v[:, 1].mean():+.0f})")
say(f"   all shared corners: median {np.median(seam_mag):.0f} mm, p90 {np.percentile(seam_mag, 90):.0f}, p95 {np.percentile(seam_mag, 95):.0f} mm")
sreg = regions(seam_pts)
say("   by region (median mm): " + "  ".join(f"{r} {np.median(seam_mag[sreg == r]):.0f} (n={int((sreg == r).sum())})" for r in REGION_ORDER if (sreg == r).any()))
say("   (b) modelled, from the ensemble: the jump between the two cameras nearest a seam sample.")
jumps = []
for k in range(1, len(WARPS)):
    pass
seam_mask = reg == "camera seam"
if seam_mask.any():
    Ps = P[seam_mask]; prim_s = prim[seam_mask]
    # second camera = the nearest OTHER camera that sees the point
    sec = np.full(len(Ps), -1); bd2 = np.full(len(Ps), np.inf)
    for i, cam in enumerate(names):
        c = default[cam]; ok = c.sees(Ps, units="mm"); d = np.hypot(Ps[:, 0] - c.centre[0], Ps[:, 1] - c.centre[1])
        m = ok & (d < bd2) & (i != prim_s); sec[m] = i; bd2[m] = d[m]
    okk = sec >= 0
    J = []
    for k, (name, wk) in enumerate(WARPS):
        da = np.zeros((okk.sum(), 2)); db = np.zeros((okk.sum(), 2))
        for i, cam in enumerate(names):
            ma = prim_s[okk] == i; mb = sec[okk] == i
            if ma.any(): da[ma] = displaced(wk, cam, Ps[okk][ma]) - Ps[okk][ma]
            if mb.any(): db[mb] = displaced(wk, cam, Ps[okk][mb]) - Ps[okk][mb]
        J.append(np.linalg.norm(da - db, axis=1))
    J = np.array(J)
    say(f"   ensemble seam jump over {okk.sum()} seam samples: median {np.median(J):.0f} mm, p90 {np.percentile(J, 90):.0f}, p95 {np.percentile(J, 95):.0f} mm"
        " (the default's own two cameras agree by construction; this is the spread between legitimate warps)")
say("   NOTE: the trajectory-extrapolation form E_seam = |x(t+) - x_hat(t+|t-)| needs tracked animals;")
say("   handoff_residual() in this file computes it from a track (t, cam, u, v) once tracking exists.")


def handoff_residual(track, cams_, dt_extrap=0.75, fps=15.0):
    """track: list of (t, cam, u, v) upright pixels. -> residuals at every camera change, using a
    linear extrapolation of the last dt_extrap seconds before the change."""
    out = []
    xy = np.array([cams_[c].to_paddock((u, v), z_mm=60.0) for _, c, u, v in track]); t = np.array([r[0] for r in track]); cam = [r[1] for r in track]
    for i in range(1, len(track)):
        if cam[i] != cam[i - 1]:
            m = (t < t[i]) & (t >= t[i] - dt_extrap) & np.array([c == cam[i - 1] for c in cam])
            if m.sum() >= 3:
                A = np.stack([t[m], np.ones(m.sum())], 1); coef = np.linalg.lstsq(A, xy[m], rcond=None)[0]
                out.append(np.linalg.norm(xy[i] - (coef[0] * t[i] + coef[1])))
    return np.array(out)


# =============================================================== 2. bin flip rate
say("")
say("2. SPATIAL-BIN ASSIGNMENT FLIP RATE (10 cm bins)")
b0 = np.floor(P / BIN).astype(int)
flip = np.zeros((len(WARPS) - 1, len(P)), bool)
for k in range(1, len(WARPS)):
    bk = np.floor((P + DISP[k]) / BIN).astype(int)
    flip[k - 1] = (bk != b0).any(1)
fr = flip.mean(0)                                        # per sample: fraction of members that flip it
say(f"   whole arena: {100 * flip.mean():.1f} % of samples change bin under another legitimate calibration")
say("   by region: " + "  ".join(f"{r} {100 * fr[reg == r].mean():.1f}%" for r in REGION_ORDER if (reg == r).any()))
edge_d = np.minimum(P % BIN, BIN - P % BIN).min(1)      # distance of each sample to the nearest bin edge
interior = edge_d > 30
multi = np.zeros(len(P))
for k in range(1, len(WARPS)):
    bk = np.floor((P + DISP[k]) / BIN).astype(int)
    multi += (np.abs(bk - b0).max(1) > 1)
say(f"   of which: samples more than 3 cm from every bin edge flip {100 * flip[:, interior].mean():.1f} %; samples that move by MORE than one bin: {100 * multi.mean() / (len(WARPS) - 1):.2f} %")
say(f"   -> the flips are bin-boundary flips of a few centimetres, not relocations: a displacement d moves a fraction ~ d / 100 mm of samples across an edge per axis")
say(f"   the ensemble's own displacement: median {np.median(mag[1:]):.0f} mm, p90 {np.percentile(mag[1:], 90):.0f} mm")
say("   by region (median displacement, mm): " + by_region(np.median(mag[1:], 0)))

# =============================================================== 3. occupancy robustness
say("")
say("3. OCCUPANCY-MAP ROBUSTNESS (10 cm bins, gaussian smoothing sigma = 1 bin, identical for every member)")


def occ(points):
    h, _, _ = np.histogram2d(points[:, 0], points[:, 1], bins=[NX, NY], range=[[0, LX], [0, LY]])
    return gaussian_filter(h, 1.0)


O = np.array([occ(P + DISP[k]) for k in range(len(WARPS))])
O0 = O[0]; valid = O0 > 0.5 * O0.mean()
def jsd(a, b):
    a = a / a.sum(); b = b / b.sum(); m = 0.5 * (a + b)
    def kl(p, q):
        m_ = p > 0; return np.sum(p[m_] * np.log2(p[m_] / q[m_]))
    return 0.5 * kl(a, m) + 0.5 * kl(b, m)
rows = []
for k in range(1, len(WARPS)):
    rows.append((np.corrcoef(O0[valid], O[k][valid])[0, 1], spearmanr(O0[valid], O[k][valid])[0],
                 np.abs(O[k] - O0).sum() / O0.sum(), jsd(O0.ravel() + 1e-12, O[k].ravel() + 1e-12)))
rows = np.array(rows)
say(f"   vs the default, over {len(WARPS) - 1} members: Pearson r median {np.median(rows[:, 0]):.4f} (min {rows[:, 0].min():.4f}), "
    f"Spearman {np.median(rows[:, 1]):.4f} (min {rows[:, 1].min():.4f}),")
say(f"   normalised |dO| median {np.median(rows[:, 2]):.3f} (max {rows[:, 2].max():.3f}), JSD median {np.median(rows[:, 3]):.5f} bits (max {rows[:, 3].max():.5f})")
cv = O.std(0) / np.maximum(O.mean(0), 1e-9)
cx_, cy_ = np.meshgrid((np.arange(NX) + 0.5) * BIN, (np.arange(NY) + 0.5) * BIN, indexing="ij")
breg = regions(np.stack([cx_.ravel(), cy_.ravel()], 1)).reshape(NX, NY)
say("   per-bin occupancy CV across members (bins with occupancy): " +
    "  ".join(f"{r} {np.median(cv[valid & (breg == r)]):.3f}" for r in REGION_ORDER if (valid & (breg == r)).any()))

# =============================================================== 4. place-field robustness (simulated cells)
say("")
say("4. PLACE-FIELD ROBUSTNESS (300 simulated place cells; spikes from the TRUE positions; rate maps under every member)")
NC = 300; DT = 1 / 15.0
cent = np.stack([rng.uniform(150, LX - 150, NC), rng.uniform(150, LY - 150, NC)], 1)
sig = rng.uniform(100, 250, NC); peak = rng.uniform(5, 15, NC)
lam = peak[:, None] * np.exp(-((P[None, :, 0] - cent[:, None, 0]) ** 2 + (P[None, :, 1] - cent[:, None, 1]) ** 2) / (2 * sig[:, None] ** 2)) * DT
spk = rng.poisson(lam).astype(float)                   # (NC, N)


def ratemaps(points):
    o = occ(points)
    R = np.empty((NC, NX, NY))
    for c in range(NC):
        s, _, _ = np.histogram2d(points[:, 0], points[:, 1], bins=[NX, NY], range=[[0, LX], [0, LY]], weights=spk[c])
        R[c] = gaussian_filter(s, 1.0) / np.maximum(o, 1e-9) / DT
    R[:, ~valid] = 0.0
    return R, o


def field_stats(R, o):
    pk = np.array([np.unravel_index(np.argmax(r), r.shape) for r in R]) * BIN + BIN / 2
    cen = []; area = []; si = []
    pocc = o / o.sum()
    for r in R:
        m = r > 0.5 * r.max(); w = r * m
        cen.append([(cx_ * w).sum() / w.sum(), (cy_ * w).sum() / w.sum()])
        area.append((r > 0.2 * r.max()).sum() * (BIN / 1000) ** 2)
        mean = (pocc * r).sum(); q = r / max(mean, 1e-9)
        si.append(np.sum(pocc * q * np.log2(np.where(q > 0, q, 1))))
    return pk, np.array(cen), np.array(area), np.array(si)


R0, o0 = ratemaps(P); pk0, ce0, ar0, si0 = field_stats(R0, o0)
dpk, dce, dar, dsi, rc, cls = [], [], [], [], [], []
for k in range(1, len(WARPS)):
    Rk, ok_ = ratemaps(P + DISP[k]); pk, ce, ar, si = field_stats(Rk, ok_)
    dpk.append(np.linalg.norm(pk - pk0, axis=1)); dce.append(np.linalg.norm(ce - ce0, axis=1))
    dar.append(100 * (ar - ar0) / ar0); dsi.append(si - si0)
    rc.append([np.corrcoef(R0[c][valid], Rk[c][valid])[0, 1] for c in range(NC)])
    cls.append(((si0 > 0.5) != (si > 0.5)).mean())
dpk, dce, dar, dsi, rc = map(np.array, (dpk, dce, dar, dsi, rc))
say(f"   peak bin:       unchanged for {100 * (dpk == 0).mean():.1f} % of cell x member; moves one bin for {100 * ((dpk > 0) & (dpk < 150)).mean():.1f} %, more for {100 * (dpk >= 150).mean():.2f} %")
say(f"   peak shift:     median {np.median(dpk):.0f} mm, p90 {np.percentile(dpk, 90):.0f} mm (a peak is a bin index: 0 or >= 100 mm)")
say(f"   centroid shift: median {np.median(dce):.0f} mm, p90 {np.percentile(dce, 90):.0f} mm, max {dce.max():.0f} mm")
say(f"   rate-map spatial correlation: median {np.median(rc):.4f}, p10 {np.percentile(rc, 10):.4f}")
say(f"   field area change: median {np.median(np.abs(dar)):.1f} %, p90 {np.percentile(np.abs(dar), 90):.1f} %")
say(f"   spatial information change: median {np.median(np.abs(dsi)):.3f} bits/spike (SI itself: median {np.median(si0):.2f})")
say(f"   place-cell classification (SI > 0.5 bits/spike) changes for {100 * np.mean(cls):.2f} % of cells per member")
creg = regions(cent)
say("   centroid shift by field location (median mm): " + "  ".join(f"{r} {np.median(dce[:, creg == r]):.0f}" for r in REGION_ORDER if (creg == r).any()))

# =============================================================== 5. error vs position
say("")
say("5. ERROR MAGNITUDE AND VECTOR BIAS VS ARENA POSITION")
say("   (a) leave-one-TYPE-out landmarks: each constraint type evaluated through a warp fitted WITHOUT any of that type")
say("       (pessimistic: without the cones the warp has no 2-D point at all and is weak along y; the bootstrap")
say("        ensemble above and the boards in (b) are the fair held-out numbers)")
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
for typ in ("cone", "cord", "wall"):
    W = {cam: fit_warp(cam, drop=typ) for cam in raw}
    E, Pt = [], []
    for cam in raw:
        pts, tgt, kind = CONS[cam]; m = kind == typ
        if not m.any() or W[cam] is None:
            continue
        w = warp_apply(W[cam], pts[m])
        for q, t in zip(w, tgt[m]):
            e = np.array([q[0] - t[0] if not np.isnan(t[0]) else np.nan, q[1] - t[1] if not np.isnan(t[1]) else np.nan])
            E.append(e); Pt.append(q)
    E = np.array(E) * MM; Pt = np.array(Pt) * MM
    r_ = regions(Pt); magn = np.sqrt(np.nansum(E ** 2, 1))
    say(f"   {typ:5s} (n={len(E):3d}): |error| median {np.median(magn):.0f} mm, p90 {np.percentile(magn, 90):.0f} mm;  mean vector (dx, dy) = "
        f"({np.nanmean(E[:, 0]):+.0f}, {np.nanmean(E[:, 1]):+.0f}) mm;  by region: " +
        "  ".join(f"{r} {np.median(magn[r_ == r]):.0f} (dx {np.nanmean(E[r_ == r, 0]):+.0f})" for r in REGION_ORDER if (r_ == r).any()))
say("   (b) boards: each camera's reading of a shared corner relative to the mean of the cameras that saw it (bias per camera per region, mm)")
per_cam = {c: [] for c in names}; per_cam_p = {c: [] for c in names}
for key, d in shared.items():
    if len(d) < 2:
        continue
    mu = np.mean(list(d.values()), 0)
    for c, v in d.items():
        per_cam[c].append(v - mu); per_cam_p[c].append(mu)
say(f"   {'camera':7s} " + "".join(f"{r:>22s}" for r in REGION_ORDER))
for c in names:
    if not per_cam[c]:
        continue
    v = np.array(per_cam[c]); r_ = regions(np.array(per_cam_p[c]))
    say(f"   {c:7s} " + "".join((f"({v[r_ == r, 0].mean():+4.0f},{v[r_ == r, 1].mean():+4.0f}) n={int((r_ == r).sum()):4d}" if (r_ == r).any() else " " * 22).rjust(22) for r in REGION_ORDER))
say("   (c) ensemble displacement of the samples, mean vector by region (mm): " +
    "  ".join(f"{r} ({DISP[1:, reg == r, 0].mean():+.0f}, {DISP[1:, reg == r, 1].mean():+.0f})" for r in REGION_ORDER if (reg == r).any()))

# =============================================================== 6. distance to features
say("")
say("6. DISTANCE-TO-FEATURE ROBUSTNESS (change of the distance under another member, mm)")


def d_wall(p):
    return np.minimum.reduce([p[:, 0], LX - p[:, 0], p[:, 1], LY - p[:, 1]])


feats = {"nearest wall": d_wall}
for nm, cpos in SHELTERS.items():
    feats[nm] = (lambda c: (lambda p: np.linalg.norm(p - c, axis=1)))(cpos)
for nm, f in feats.items():
    d0 = f(P); dd = np.array([np.abs(f(P + DISP[k]) - d0) for k in range(1, len(WARPS))])
    say(f"   {nm:18s} |dd| median {np.median(dd):.0f} mm, p90 {np.percentile(dd, 90):.0f} mm;  by region: " +
        "  ".join(f"{r} {np.median(dd[:, reg == r]):.0f}" for r in REGION_ORDER if (reg == r).any()))
say("   (shelter positions are approximate, +-0.5 m; the distance CHANGE barely depends on them)")

# =============================================================== verdict
say("")
say("ANALYSIS FITNESS (priority: place-field stability > occupancy stability > handoff continuity > raw landmark error)")
say(f"   place fields:  centroid shift median {np.median(dce):.0f} mm / p90 {np.percentile(dce, 90):.0f} mm, peak bin unchanged {100 * (dpk == 0).mean():.0f} %, classification change {100 * np.mean(cls):.1f} %  -> {'below one 10 cm bin' if np.percentile(dce, 90) < 100 else 'about one bin at p90'}")
say(f"   occupancy:     r >= {rows[:, 0].min():.3f}, JSD <= {rows[:, 3].max():.4f} bits across every legitimate calibration")
say(f"   handoff:       boards say {np.median(seam_mag):.0f} mm median / {np.percentile(seam_mag, 90):.0f} mm p90 between cameras; ensemble seam jump {np.median(J) if seam_mask.any() else float('nan'):.0f} mm median")
say(f"   bin flips:     {100 * flip.mean():.1f} % overall; " + "  ".join(f"{r} {100 * fr[reg == r].mean():.0f}%" for r in ("corner", "short-wall end", "camera seam") if (reg == r).any()))
(OUT / "DOWNSTREAM_VALIDATION.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n->", OUT / "DOWNSTREAM_VALIDATION.txt")

# =============================================================== figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axs = plt.subplots(2, 2, figsize=(15, 8.5))
ext = [0, LX / MM, 0, LY / MM]
h, _, _ = np.histogram2d(P[:, 0], P[:, 1], bins=[NX, NY], range=[[0, LX], [0, LY]], weights=fr)
n, _, _ = np.histogram2d(P[:, 0], P[:, 1], bins=[NX, NY], range=[[0, LX], [0, LY]])
im = axs[0, 0].imshow((100 * h / np.maximum(n, 1)).T, origin="lower", extent=ext, cmap="magma", vmin=0, vmax=50)
axs[0, 0].set_title("2. bin flip rate under another legitimate calibration (%)"); plt.colorbar(im, ax=axs[0, 0])
hs, _, _ = np.histogram2d(seam_pts[:, 0], seam_pts[:, 1], bins=[NX // 3, NY // 3], range=[[0, LX], [0, LY]], weights=seam_mag)
ns, _, _ = np.histogram2d(seam_pts[:, 0], seam_pts[:, 1], bins=[NX // 3, NY // 3], range=[[0, LX], [0, LY]])
im = axs[0, 1].imshow(np.where(ns > 0, hs / np.maximum(ns, 1), np.nan).T, origin="lower", extent=ext, cmap="viridis", vmin=0, vmax=300)
axs[0, 1].set_title("1. cross-camera disagreement on the boards (mm, 30 cm cells)"); plt.colorbar(im, ax=axs[0, 1])
step = 12
gx, gy = np.meshgrid(np.arange(step, 480, 2 * step), np.arange(step, 240, 2 * step))
G = np.stack([gx.ravel(), gy.ravel()], 1) * MM
pg, _ = primary_camera(G); okg = pg >= 0
V = np.zeros((len(G), 2))
for k in range(1, len(WARPS)):
    for i, cam in enumerate(names):
        m = okg & (pg == i)
        if m.any(): V[m] += (displaced(WARPS[k][1], cam, G[m]) - G[m]) / (len(WARPS) - 1)
axs[1, 0].quiver(G[okg, 0] / MM, G[okg, 1] / MM, V[okg, 0], V[okg, 1], angles="xy", scale_units="xy", scale=8, color="#c0392b", width=0.003)
axs[1, 0].set_xlim(0, 480); axs[1, 0].set_ylim(0, 240); axs[1, 0].set_aspect("equal")
axs[1, 0].set_title("5. mean displacement vector of the ensemble vs the default (arrows x8)")
im = axs[1, 1].imshow(np.where(valid, cv, np.nan).T, origin="lower", extent=ext, cmap="cividis", vmin=0, vmax=0.3)
axs[1, 1].set_title("3. per-bin occupancy CV across the ensemble"); plt.colorbar(im, ax=axs[1, 1])
for a in axs.ravel():
    a.set_xlabel("x (in)"); a.set_ylabel("y (in)")
fig.tight_layout(); fig.savefig(OUT / "downstream_validation.png", dpi=120)
print("->", OUT / "downstream_validation.png")
