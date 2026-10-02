# -*- coding: utf-8 -*-
r"""The ball sweep as a stand-in rat: how far each camera puts the same ball, under a given fit. A CHECK, not a fit.

Every ball mark the operator drew or accepted (session_2026-09-30_ball_labels.json; unchecked machine marks are
skipped) goes to the ground at the ball-centre height (105 mm, the height cameras agree best at), after the
2026-09-30 pixels are carried into the 2026-09-18 pixel frame (landmark_drift similarity). At each 2-s step the
cameras that saw the ball are compared pairwise.

Clock: segment names give each camera's start to 1 s only, so a per-camera clock offset (vs CH02) is fitted to the
balls with the warps fixed (robust least squares, the ball moved at velocity v_k from the cameras' mean track) and
the distances are reported both without and with it. The fitted offsets come from the same marks they are scored
on, so the "with clock" numbers are optimistic; CH04's offset in particular is confounded with its position (both
passes through its view ran in -y) and disagrees with the cameras' burnt-in clocks (AUDIT_FABLE_2026-10-02.md 1.5).

Reported per camera pair, per camera (its distance to every other camera that saw the same ball), and by region
along the paddock (x < 60 in, 60-400, > 400 in = the CH04 end); "outside support" = marks the camera maps outside
the region its warp was verified on.

Usage: python ball_check.py [--fit <camera_fit.npz>] [--labels <ball labels>] [--drift <landmark_drift.json>]
                            [--z 105] [--out <txt>]
Output: <fit dir>\BALL_CHECK.txt (or --out)
"""
import sys, json, itertools, collections
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paddock_map as pm                                                  # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
FIT = Path(opt("--fit", str(pm.FIT)))
LABELS = Path(opt("--labels", str(HERE / "session_2026-09-30_ball_labels.json")))
DRIFT = Path(opt("--drift", str(HERE / "session_2026-09-30_landmark_drift.json")))
Z = float(opt("--z", "105"))
OUT = Path(opt("--out", str(FIT.parent / "BALL_CHECK.txt")))
STEP, REF = 2.0, "CH02"
cams = pm.load(FIT)
drift = json.loads(DRIFT.read_text(encoding="utf-8"))["cameras"]


def to_0918(cam, uv):
    uv = np.atleast_2d(np.asarray(uv, float)); d = drift.get(cam)
    if not d:
        return uv
    if "affine_30_to_18" in d:                                   # landmark_track_drift.py: 09-30 px -> 09-18 colour px
        A = np.asarray(d["affine_30_to_18"], float)
        return uv @ A[:, :2].T + A[:, 2]
    c = np.asarray(d["centre_px"], float); th = np.radians(d["rot_deg"])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return c + (uv - c - [d["dx_px"], d["dy_px"]]) @ R / d["scale"]


obs, outside = collections.defaultdict(dict), collections.Counter()
for L in json.loads(LABELS.read_text(encoding="utf-8"))["labels"]:
    if L["verdict"] != "ball" or not L.get("centre") or L.get("method") == "machine-unchecked":
        continue
    c = cams[L["cam"]]
    d = c.rays(to_0918(L["cam"], L["centre"]))
    s = (Z - c.centre[2]) / d[0, 2]
    if not s > 0:
        continue
    X = c.centre + s * d[0]
    outside[L["cam"]] += int(not c.in_support(X[None, :2])[0])
    obs[L["k"]][L["cam"]] = pm.fit_to_physical(X[None, :2], c.correction)[0]       # mm, paddock frame
ks = sorted(k for k in obs if len(obs[k]) >= 2)
mean = {k: np.mean(list(v.values()), 0) for k, v in obs.items()}
V = {}
for k in mean:
    a, b = (k - 1 if k - 1 in mean else k), (k + 1 if k + 1 in mean else k)
    V[k] = (mean[b] - mean[a]) / (STEP * (b - a)) if b != a else np.zeros(2)
others = sorted({c for k in ks for c in obs[k]} - {REF})


def resid(x):
    tau = dict(zip(others, x)); r = []
    for k in ks:
        v = np.array([obs[k][c] - tau.get(c, 0.0) * V[k] for c in sorted(obs[k])])
        r.append((v - v.mean(0)).ravel())
    return np.concatenate(r)


TAU = dict(zip(others, least_squares(resid, np.zeros(len(others)), loss="soft_l1", f_scale=75.0).x))


def table(tau):
    pair, percam, region = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for k in ks:
        p = {c: obs[k][c] - tau.get(c, 0.0) * V[k] for c in obs[k]}
        for a, b in itertools.combinations(sorted(p), 2):
            d = float(np.hypot(*(p[a] - p[b])))
            pair[f"{a}-{b}"].append(d); percam[a].append(d); percam[b].append(d)
            x = (p[a][0] + p[b][0]) / 2 / 25.4
            region["x < 60 in" if x < 60 else "x > 400 in (CH04 end)" if x > 400 else "60-400 in"].append(d)
    return pair, percam, region


q = lambda v: f"median {np.median(v):4.0f} mm, p90 {np.percentile(v, 90):4.0f}, n {len(v)}"
L = [f"BALL CHECK (the ball sweep as a stand-in rat; not used in the fit)  fit {FIT}",
     f"marks {LABELS.name}, ball centre at z = {Z:.0f} mm, 09-30 px carried to 09-18 by {DRIFT.name}; "
     f"{sum(len(v) for v in obs.values())} marks, {len(ks)} steps seen by 2+ cameras",
     "marks outside the camera's verified support: " + ", ".join(f"{c} {n}" for c, n in sorted(outside.items()) if n), ""]
for title, tau in (("WITHOUT clock offsets (file-name clocks)", {}),
                   ("WITH clock offsets fitted to these balls (optimistic; CH04's is confounded with position): "
                    + ", ".join(f"{c} {t:+.2f} s" for c, t in TAU.items()) + f" vs {REF}", TAU)):
    pair, percam, region = table(tau)
    allp = np.concatenate([np.array(v) for v in pair.values()])
    L += [title, f"  all pairs: {q(allp)}", "  per camera (its distance to the other cameras on the same ball):"]
    L += [f"    {c}: {q(v)}" for c, v in sorted(percam.items())]
    L += ["  per pair:"] + [f"    {p}: {q(v)}" for p, v in sorted(pair.items()) if len(v) >= 3]
    L += ["  by region:"] + [f"    {r}: {q(v)}" for r, v in sorted(region.items())] + [""]
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", OUT)
