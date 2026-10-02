# -*- coding: utf-8 -*-
r"""Cross-camera agreement on the ~20 Hz ball tracks, after fitting each camera's clock offset. A CHECK, not a fit.

Input: ball_track20.py's per-camera tracks (<ball dir>\track20\ball20_<CAM>.json, another session's run, 2026-10-02):
every decoded frame with its time and, where SAM 3 found the ball, its ellipse in 09-30 upright pixels. Each
detection goes to the ground at the ball-centre height (105 mm) after the 09-30 -> 09-18 colour transform
(session_2026-09-30_drift_final.json) through the given fit.

Time base. The frame times in the files are the recording's timestamps, and they are bursty: frames arrive in
clumps (intervals near 0) followed by gaps (~0.2 s); against a steady clock (frame index / frame rate, fitted
over the whole sweep) they scatter by 0.04-0.09 s rms and up to 0.57 s. The cameras capture at a steady 20 fps,
so the steady clock is the candidate for capture time; both are scored ("pts" and "index") and the data decide.

Clock offset per camera pair: camera b's track is linearly interpolated (only across gaps < GAP s) at camera a's
detection times shifted by tau; tau minimises the median distance over a grid of 0.01 s. Pushes and stops of the
stick change the ball's velocity, which is what pins tau; a long straight push at constant speed would not.
Per-camera offsets (vs CH02) by least squares over the pairs, weighted by overlap; then every frame pair is
compared at its aligned time: per pair, per camera, by region (x < 60 in, 60-400, > 400 = the CH04 end), and for
slow frames (ball under 5 cm/s), where any timing error no longer matters.

Usage: python ball_sync20.py [--fit <camera_fit.npz>] [--track <dir>] [--drift <json>] [--base index|pts|both]
Output: <fit dir>\BALL_SYNC20.txt
"""
import sys, json, itertools, collections
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths, paddock_map as pm                                        # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
FIT = Path(opt("--fit", str(pm.FIT)))
TRACK = Path(opt("--track", str(qc_paths.QC_ROOT / "2026-09-30" / "ball" / "track20")))
DRIFT = Path(opt("--drift", str(HERE / "session_2026-09-30_drift_final.json")))
BASES = ["index", "pts"] if opt("--base", "both") == "both" else [opt("--base")]
Z, GAP, REF, SLOW = 105.0, 0.25, "CH02", 50.0                             # mm; s; reference camera; mm/s
TAUS = np.round(np.arange(-1.5, 1.5001, 0.01), 3)
cams = pm.load(FIT)
drift = json.loads(DRIFT.read_text(encoding="utf-8"))["cameras"]


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = drift.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:
        A = np.asarray(d["affine_30_to_18"], float)
        return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


def load(cam):
    fr = json.loads((TRACK / f"ball20_{cam}.json").read_text(encoding="utf-8"))["frames"]
    t_pts = np.array([f[0] for f in fr]); i = np.arange(len(fr))
    a, b = np.polyfit(i, t_pts, 1); t_idx = a * i + b                        # steady clock fitted to the timestamps
    sel = [k for k, f in enumerate(fr) if f[3]]
    uv = np.array([[fr[k][3]["cx"], fr[k][3]["cy"]] for k in sel], float)
    c = cams[cam]; d = c.rays(to_0918(cam, uv)); s = (Z - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    xy = pm.fit_to_physical(X[:, :2], c.correction); xy[~(s > 0)] = np.nan
    ok = np.isfinite(xy).all(1)
    return dict(pts=t_pts[sel][ok], index=t_idx[sel][ok], xy=xy[ok])


def interp(T, P, t):
    """track (T sorted, P) at times t; NaN where t falls in a gap > GAP or outside."""
    j = np.searchsorted(T, t)
    ok = (j > 0) & (j < len(T))
    j = np.clip(j, 1, len(T) - 1)
    t0, t1 = T[j - 1], T[j]
    ok &= (t1 - t0) <= GAP
    w = np.where(t1 > t0, (t - t0) / np.maximum(t1 - t0, 1e-9), 0.0)
    out = P[j - 1] + w[:, None] * (P[j] - P[j - 1])
    out[~ok] = np.nan
    return out


tracks = {c: load(c) for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06") if (TRACK / f"ball20_{c}.json").exists()}
L = [f"BALL SYNC 20 Hz  fit {FIT}; tracks {TRACK}; 09-30 px -> 09-18 colour px by {DRIFT.name}; ball centre z = {Z:.0f} mm",
     "detections mapped: " + ", ".join(f"{c} {len(v['xy'])}" for c, v in tracks.items()), ""]
q = lambda v: f"median {np.median(v):4.0f} mm, p90 {np.percentile(v, 90):4.0f}, n {len(v)}" if len(v) else "-"
for base in BASES:
    pair_tau, pair_n = {}, {}
    curves = {}
    for a, b in itertools.combinations(tracks, 2):
        A, B = tracks[a], tracks[b]
        best = None; cur = []
        for tau in TAUS:
            pb = interp(B[base], B["xy"], A[base] + tau)
            d = np.hypot(*(A["xy"] - pb).T); d = d[np.isfinite(d)]
            if len(d) < 40:
                cur.append(np.nan); continue
            m = np.median(d); cur.append(m)
            if best is None or m < best[0]:
                best = (m, tau, len(d))
        if best:
            pair_tau[(a, b)] = best[1]; pair_n[(a, b)] = best[2]; curves[(a, b)] = np.array(cur)
    names = [c for c in tracks if c != REF]
    rows, rhs, wts = [], [], []
    for (a, b), tau in pair_tau.items():                                  # tau_ab ~ off_b - off_a (b's clock leads)
        r = np.zeros(len(names))
        if a != REF: r[names.index(a)] -= 1
        if b != REF: r[names.index(b)] += 1
        rows.append(r); rhs.append(tau); wts.append(np.sqrt(pair_n[(a, b)]))
    off = dict(zip(names, np.linalg.lstsq(np.array(rows) * np.array(wts)[:, None], np.array(rhs) * np.array(wts), rcond=None)[0])); off[REF] = 0.0
    L.append(f"TIME BASE: {base}  ({'frame index / fitted frame rate' if base == 'index' else 'recording timestamps'})")
    L.append("  pairwise clock offset (b vs a), median distance at it, and how sharp the minimum is (median at tau +- 0.2 s):")
    for (a, b), tau in sorted(pair_tau.items()):
        cv = curves[(a, b)]; k = int(np.where(TAUS == tau)[0][0])
        lo, hi = cv[max(0, k - 20)], cv[min(len(cv) - 1, k + 20)]
        L.append(f"    {a}-{b}: tau {tau:+.2f} s, median {np.nanmin(cv):4.0f} mm (n {pair_n[(a, b)]}); +-0.2 s: {lo:4.0f} / {hi:4.0f} mm")
    L.append("  per-camera offsets (least squares, vs " + REF + "): " + ", ".join(f"{c} {o:+.2f} s" for c, o in sorted(off.items())))
    pair, percam, region, slow = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for a, b in itertools.combinations(tracks, 2):
        A, B = tracks[a], tracks[b]
        pb = interp(B[base] - off[b], B["xy"], A[base] - off[a])
        ok = np.isfinite(pb).all(1)
        if ok.sum() < 20:
            continue
        d = np.hypot(*(A["xy"][ok] - pb[ok]).T)
        pair[f"{a}-{b}"] += list(d); percam[a] += list(d); percam[b] += list(d)
        x = (A["xy"][ok][:, 0] + pb[ok][:, 0]) / 2 / 25.4
        for dd, xx in zip(d, x):
            region["x < 60 in" if xx < 60 else "x > 400 in (CH04 end)" if xx > 400 else "60-400 in"].append(dd)
        ta = A[base][ok] - off[a]                                         # speed from a's own track
        v = np.hypot(*np.gradient(A["xy"][ok], ta, axis=0).T)
        slow[f"{a}-{b}"] += list(d[v < SLOW])
    allp = np.concatenate([np.array(v) for v in pair.values()])
    L += [f"  ALIGNED, every frame pair: {q(allp)}", "  per camera:"] + [f"    {c}: {q(v)}" for c, v in sorted(percam.items())]
    L += ["  per pair (all frames | ball slower than 5 cm/s):"] + [f"    {p}: {q(v)}  |  {q(slow[p])}" for p, v in sorted(pair.items())]
    L += ["  by region:"] + [f"    {r}: {q(v)}" for r, v in sorted(region.items())] + [""]
OUT = FIT.parent / "BALL_SYNC20.txt"
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", OUT)
