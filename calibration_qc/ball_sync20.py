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

Held ball. Between passes the operator carries the ball; a ball in the hand is off the ground, and mapped at the
ball-centre height it lands up to metres away (2.3-2.5 mm sideways per mm of height on the panos), so those frames
are excluded before anything is compared. The evidence for "held" never comes from comparing cameras (that would
remove exactly the disagreements this check measures): it is
  - the operator's 2-s statements "off ground" (session_2026-09-30_ball_labels.json), and
  - each camera's own view: a ball lifted towards the camera looks larger than the calibration predicts for a
    ball on the ground at the same pixel (size ratio = sqrt(a b) / r_pred: on-ground labels 0.9-1.0 median,
    p90 <= 1.09; off-ground labels 1.3-1.5 median on CH01-CH03).
On a 0.05-s common clock (first-pass offsets) the evidence E(t) is the largest 5-frame running median of the
size ratio over the cameras that see the ball. A held interval is seeded at every operator "off ground" time
and at every stretch of E > HELD_ON lasting >= HELD_MIN s; it grows both ways until E <= HELD_OFF or an operator
"ball" mark (on the ground), and is padded by PAD s. Every detection of every camera inside it is dropped, and the
offsets are refitted. Operator corrections from the review page (ball20_gui.py export: held ranges added or
rejected, detections flagged wrong) are applied with --flags.
The cameras' own triangulated height (least-squares point of the simultaneous rays) is written beside the
intervals for the review page only; it is not used to exclude anything.

--centre top (tested 2026-10-02, not used): SAM 3's mask loses the ball's bottom where grass hides it, so its centre
sits a few px high (2.5-4.7 px on CH01-CH04 against the operator's drawings); this variant keeps SAM's top edge and
horizontal centre and takes the radius from the calibration (r_pred) where the ellipse is shorter. The cameras
agree less with it (all pairs 65 / 134 mm vs 62 / 122).

Usage: python ball_sync20.py [--fit <camera_fit.npz>] [--track <dir>] [--drift <json>] [--base index|pts|both]
                             [--labels <ball labels>] [--flags <ball20_flags.json>] [--keep-held] [--centre sam|top] [--out <txt>]
Output: <fit dir>\BALL_SYNC20.txt; <track dir>\held20.json (intervals, evidence, offsets, heights)
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
LABELS = Path(opt("--labels", str(HERE / "session_2026-09-30_ball_labels.json")))
FLAGS = opt("--flags")
KEEP_HELD = "--keep-held" in args
CENTRE = opt("--centre", "sam")                                           # sam | top (see the docstring)
BASES = ["index", "pts"] if opt("--base", "both") == "both" else [opt("--base")]
Z, GAP, REF, SLOW = 105.0, 0.25, "CH02", 50.0                             # mm; s; reference camera; mm/s
HELD_ON, HELD_OFF, HELD_MIN, PAD, DT = 1.25, 1.10, 0.5, 0.15, 0.05        # size ratio; s
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
    sel = np.array([k for k, f in enumerate(fr) if f[3]])
    det = [fr[k][3] for k in sel]
    uv = np.array([[q["cx"], q["cy"]] for q in det], float)
    if CENTRE == "top":                                                   # keep the top edge, radius from the calibration
        hv = np.sqrt([(q["a"] * np.sin(q["th"])) ** 2 + (q["b"] * np.cos(q["th"])) ** 2 for q in det])
        uv[:, 1] += np.maximum(0.0, np.array([q["r_pred"] for q in det]) - hv)
    c = cams[cam]; d = c.rays(to_0918(cam, uv)); s = (Z - c.centre[2]) / d[:, 2]
    X = c.centre + s[:, None] * d
    xy = pm.fit_to_physical(X[:, :2], c.correction); xy[~(s > 0)] = np.nan
    ok = np.isfinite(xy).all(1)
    rr = np.sqrt([q["a"] * q["b"] for q in det]) / np.array([q["r_pred"] for q in det])
    return dict(pts=t_pts[sel][ok], index=t_idx[sel][ok], xy=xy[ok], entry=sel[ok], rr=rr[ok], ray=d[ok],
                line=(float(a), float(b)))


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


def subset(tr, keep):
    return {c: {k: (v[keep[c]] if isinstance(v, np.ndarray) else v) for k, v in A.items()} for c, A in tr.items()}


def fit_offsets(tr, base):
    pair_tau, pair_n, curves = {}, {}, {}
    for a, b in itertools.combinations(tr, 2):
        A, B = tr[a], tr[b]
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
    names = [c for c in tr if c != REF]
    rows, rhs, wts = [], [], []
    for (a, b), tau in pair_tau.items():                                  # tau_ab ~ off_b - off_a (b's clock leads)
        r = np.zeros(len(names))
        if a != REF: r[names.index(a)] -= 1
        if b != REF: r[names.index(b)] += 1
        rows.append(r); rhs.append(tau); wts.append(np.sqrt(pair_n[(a, b)]))
    off = dict(zip(names, np.linalg.lstsq(np.array(rows) * np.array(wts)[:, None], np.array(rhs) * np.array(wts), rcond=None)[0]))
    off[REF] = 0.0
    return off, pair_tau, pair_n, curves


def runmed(x, n=5):
    h = n // 2; xp = np.pad(x, h, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, n), axis=1)


def held_intervals(tr, off, labels):
    """intervals [t0, t1] on the common clock (index base minus offset) where the ball is held; see the docstring."""
    t_all = np.concatenate([A["index"] - off[c] for c, A in tr.items()])
    g0 = np.floor(t_all.min()) - 1; nb = int((t_all.max() + 1 - g0) / DT) + 1
    E = np.full(nb, np.nan)
    for c, A in tr.items():
        b = np.round((A["index"] - off[c] - g0) / DT).astype(int)
        np.fmax.at(E, b, runmed(A["rr"]))
    tb = g0 + DT * np.arange(nb)
    gb = lambda t: int(np.clip(round((t - g0) / DT), 0, nb - 1))
    stop = np.zeros(nb, bool); stop[np.isfinite(E) & (E <= HELD_OFF)] = True
    seeds = []
    for L in labels:
        if L.get("method") == "machine-unchecked" or L["cam"] not in off:
            continue
        if L["verdict"] == "ball":
            stop[gb(2.0 * L["k"] - off[L["cam"]])] = True
    offk = collections.defaultdict(list)
    for L in labels:
        if L["verdict"] == "off ground" and L["cam"] in off:
            b = gb(2.0 * L["k"] - off[L["cam"]]); seeds.append((b, f"operator k{L['k']} {L['cam']}"))
            stop[b] = False                                               # the operator's statement wins at its own time
            offk[L["k"]].append(b)
    for k in offk:                                                        # held at two marks 2 s apart: held in between
        if k + 1 in offk:                                                 # (a hand can hide half the ball: small ratio)
            stop[min(offk[k]):max(offk[k + 1]) + 1] = False
    hi = np.isfinite(E) & (E > HELD_ON)                                   # sustained large size ratio, NaN gaps <= 0.2 s bridged
    k = 0
    while k < nb:
        if not hi[k]:
            k += 1; continue
        j, last = k, k
        while j + 1 < nb and (hi[j + 1] or (np.isnan(E[j + 1]) and j + 1 - last <= 4)):
            j += 1; last = j if hi[j] else last
        if (last - k) * DT >= HELD_MIN:
            seeds.append(((k + last) // 2, f"size ratio > {HELD_ON} for {(last - k) * DT:.1f} s"))
        k = j + 1
    spans = []
    for b, why in seeds:
        lo = b
        while lo - 1 >= 0 and not stop[lo - 1]:
            lo -= 1
        hi_ = b
        while hi_ + 1 < nb and not stop[hi_ + 1]:
            hi_ += 1
        spans.append([tb[lo] - PAD, tb[hi_] + PAD, [why]])
    spans.sort()
    merged = []
    for s in spans:
        if merged and s[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s[1]); merged[-1][2] += s[2]
        else:
            merged.append(s)
    out = []
    for t0, t1, why in merged:
        m = (tb >= t0) & (tb <= t1) & np.isfinite(E)
        ops = sorted({w for w in why if w.startswith("operator")})
        out.append(dict(t0=round(float(t0), 2), t1=round(float(t1), 2), source="operator" if ops else "size",
                        evidence=ops[:3] + ([f"... {len(ops) - 3} more"] if len(ops) > 3 else []) + sorted({w for w in why if not w.startswith("operator")}),
                        max_size_ratio=round(float(E[m].max()), 2) if m.any() else None))
    return out


def heights(tr, off):
    """least-squares point of the simultaneous rays (index base, aligned): z in mm per detection, for review only."""
    out = {}
    for c, A in tr.items():
        n = len(A["index"]); M = np.zeros((n, 3, 3)); r = np.zeros((n, 3)); cnt = np.zeros(n, int); cmax = np.zeros(n)
        P = np.eye(3)[None] - A["ray"][:, :, None] * A["ray"][:, None, :]
        M += P; r += P @ cams[c].centre
        for o, B in tr.items():
            if o == c:
                continue
            d = interp(B["index"] - off[o], B["ray"], A["index"] - off[c])
            ok = np.isfinite(d).all(1)
            d[ok] /= np.linalg.norm(d[ok], axis=1, keepdims=True)
            cosang = np.abs(np.einsum("ij,ij->i", np.where(ok[:, None], d, 0), A["ray"]))
            use = ok & (cosang < np.cos(np.radians(10)))                  # rays at least 10 deg apart
            Po = np.eye(3)[None] - d[:, :, None] * d[:, None, :]
            M[use] += Po[use]; r[use] += Po[use] @ cams[o].centre; cnt[use] += 1
        z = np.full(n, np.nan); u = cnt > 0
        z[u] = np.linalg.solve(M[u], r[u][:, :, None])[:, 2, 0]
        out[c] = (z, cnt + 1)
    return out


tracks = {c: load(c) for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06") if (TRACK / f"ball20_{c}.json").exists()}
labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"]
off0 = fit_offsets(tracks, "index")[0]                                    # first pass, every detection
held = held_intervals(tracks, off0, labels)
flags = json.loads(Path(FLAGS).read_text(encoding="utf-8")) if FLAGS else {}
for t0, t1 in flags.get("held_added", []):
    held.append(dict(t0=t0, t1=t1, source="operator (review page)", evidence=[], max_size_ratio=None))
rejected = [tuple(x) for x in flags.get("held_rejected", [])]
held = [h for h in held if not any(abs(h["t0"] - a) < 0.01 and abs(h["t1"] - b) < 0.01 for a, b in rejected)]
held.sort(key=lambda h: h["t0"])
wrong = {(f["cam"], f["entry"]) for f in flags.get("flags", []) if f.get("flag") == "wrong"}
keep, n_held, n_wrong = {}, collections.Counter(), collections.Counter()
for c, A in tracks.items():
    t = A["index"] - off0[c]
    h = np.zeros(len(t), bool)
    for H in held:
        h |= (t >= H["t0"]) & (t <= H["t1"])
    w = np.array([(c, int(e)) in wrong for e in A["entry"]], bool)
    n_held[c], n_wrong[c] = int(h.sum()), int(w.sum())
    keep[c] = ~w & (np.ones(len(t), bool) if KEEP_HELD else ~h)
z_rev = heights(tracks, off0)
if CENTRE == "sam":
    TRACK.joinpath("held20.json").write_text(json.dumps(dict(
        note="Ball held off the ground (ball_sync20.py): intervals on the common clock = steady index clock of each camera "
             "(line t = a * entry + b fitted to its timestamps) minus its offset vs CH02; heights are the cameras' "
             "triangulation, for review only (never used to exclude).",
        params=dict(held_on=HELD_ON, held_off=HELD_OFF, held_min_s=HELD_MIN, pad_s=PAD),
        offsets_s={c: round(float(o), 3) for c, o in off0.items()},
        lines={c: A["line"] for c, A in tracks.items()},
        intervals=held,
        cams={c: dict(entry=A["entry"].tolist(), size_ratio=np.round(A["rr"], 3).tolist(),
                      height_mm=[None if not np.isfinite(v) else round(float(v)) for v in z_rev[c][0]],
                      n_cams=z_rev[c][1].tolist()) for c, A in tracks.items()}), separators=(",", ":")), encoding="utf-8")

L = [f"BALL SYNC 20 Hz  fit {FIT}; tracks {TRACK}; 09-30 px -> 09-18 colour px by {DRIFT.name}; ball centre z = {Z:.0f} mm"
     + ("" if CENTRE == "sam" else "; CENTRE = top edge + calibrated radius (--centre top)"),
     "detections mapped: " + ", ".join(f"{c} {len(v['xy'])}" for c, v in tracks.items()), "",
     f"HELD BALL (operator 'off ground' + each camera's size ratio; {'NOT excluded (--keep-held)' if KEEP_HELD else 'excluded'}): "
     f"{len(held)} intervals, {sum(h['t1'] - h['t0'] for h in held):.0f} s; detections dropped: "
     + ", ".join(f"{c} {n_held[c]}" for c in tracks) + (f"; flagged wrong on the review page: " + ", ".join(f"{c} {n_wrong[c]}" for c in tracks) if wrong else "")]
L += [f"    {h['t0']:7.2f} - {h['t1']:7.2f} s  ({h['t1'] - h['t0']:4.1f} s)  {h['source']:<8} max size ratio {h['max_size_ratio']}  "
      + "; ".join(h["evidence"]) for h in held]
zz = {c: z_rev[c][0][keep[c]] for c in tracks}
zh = {c: z_rev[c][0][~keep[c]] for c in tracks}
fz = lambda v: (lambda v: f"median {np.median(v):4.0f} mm, p10-p90 {np.percentile(v, 10):4.0f}-{np.percentile(v, 90):4.0f}, n {len(v)}" if len(v) else "-")(v[np.isfinite(v)])
L += ["  triangulated ball-centre height (review only; the ball centre is at 105 mm): kept " + fz(np.concatenate(list(zz.values())))
      + " | dropped " + fz(np.concatenate(list(zh.values()))), ""]
tracks = subset(tracks, keep)
q = lambda v: f"median {np.median(v):4.0f} mm, p90 {np.percentile(v, 90):4.0f}, n {len(v)}" if len(v) else "-"
for base in BASES:
    off, pair_tau, pair_n, curves = fit_offsets(tracks, base)
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
        with np.errstate(divide="ignore", invalid="ignore"):              # pts has repeated times (bursts): speed NaN there
            v = np.hypot(*np.gradient(A["xy"][ok], ta, axis=0).T)
        slow[f"{a}-{b}"] += list(d[v < SLOW])
    allp = np.concatenate([np.array(v) for v in pair.values()])
    L += [f"  ALIGNED, every frame pair: {q(allp)}", "  per camera:"] + [f"    {c}: {q(v)}" for c, v in sorted(percam.items())]
    L += ["  per pair (all frames | ball slower than 5 cm/s):"] + [f"    {p}: {q(v)}  |  {q(slow[p])}" for p, v in sorted(pair.items())]
    L += ["  by region:"] + [f"    {r}: {q(v)}" for r, v in sorted(region.items())] + [""]
OUT = Path(opt("--out", str(FIT.parent / "BALL_SYNC20.txt")))
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", OUT, "and", TRACK / "held20.json")
