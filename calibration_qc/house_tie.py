# -*- coding: utf-8 -*-
r"""CH05 / CH06 at cohort times: the camera's turn between a cohort frame and the calibration, measured on the rigid
things in its view - the house under it and the pole it hangs from - at their known 3-D poses (2026-10-10).

CH05 / CH06 hang from crossbeams at the top of poles B1 / B3 and look down on house_1 / house_2. house_1 was moved on
09-18, the calibration day, so image registration cannot tie CH05's cohort frames to the calibration (the analysis
repo's correction table stops at CH05's own 09-04 frames). Two rigid objects of known 3-D pose are in view:
- the house: house_check.py's rigid model at house_1's COHORT pose, refitted here from the CH01 + CH02 09-04 12:00
  labels (mapped to 09-18 px with the noon affines), and at house_2's 09-18 pose (house_2 never moved);
- the pole: a cylinder (axis + radius) measured on rev g by the analysis repo's pole check (CH01 + CH02 09-18 labels).
  CH01 / CH02 track B1 and B3 between 09-04 and 09-18 to 1-2 px (analysis run cv_field_landmark_track_ch0102_0904noon_
  20261006_1540): the poles did not lean, so the crossbeam junction did not move and the camera can only have turned
  (on its bracket, or the crossbeam at the pole top). rev g's CH05 / CH06 miss the CH01 + CH02 cylinder by ~4 cm in their
  09-18 frames (the pole runs into the frame's bottom edge, 0.6-0.9 m from the lens), so each camera's pole is first
  shifted to its own 09-18 view (own_pole) and then used differentially.

Fits: every labelled roof ray must meet its roof edge (house_check's edge assignment; the operator's pieces are first
cut into straight runs - a ROOF_Y piece is a whole gable outline) and every labelled pole-edge ray must graze the pole.
Models: a turn about the camera centre, a turn about the pole top (both physical; they differ by ~1 cm at head height)
and, as a diagnostic, a turn plus a free shift. Even on the 09-18 frames, where the camera has not moved, a turn of
~1 deg is fitted: the camera's own view of the house and the house pose from CH01 + CH02 disagree by that much (mostly
the ridge direction). The DIFFERENTIAL tie removes it: the cohort fit minus the 09-18 fit. On CH06 it agrees with the
analysis repo's image registration 09-04 <-> 09-18 to 5-7 mm median at head height (the direct fit: ~22 mm). The roof is
the house LID, lifted at every round, so a tie carries that lid-closed segment's lid placement: tie a camera with labels
from the segment its house pose comes from (CH05: the 09-04 12:00 labels; its 03:01 frame lies one round earlier).

Output: per camera and frame the motion, the residuals before / after, and the map cohort-frame pixel -> rev g pixel at
head height (z = 60 mm above the local ground; what paddock_map's to_paddock then takes), its best affine and that
affine's residual over the frame's ground; CH06 against the analysis repo's own registrations. --write-ties writes the
CH05 differential ties to cohort_ties_2026c.json next to this file, which cohort_tie.py applies.

Usage: python house_tie.py [--z 60] [--write-ties]
Output: <qc root>\house_tie\HOUSE_TIE.txt + house_tie.json [+ calibration_qc\cohort_ties_2026c.json]
"""
import sys, json, hashlib
from datetime import datetime
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import house_check as hc                                                 # noqa: E402  (loads the release cameras, rev g)
import cohort_tie                                                        # noqa: E402
from scipy.optimize import least_squares                                 # noqa: E402
from scipy.spatial.transform import Rotation                             # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
Z = float(opt("--z", "60"))
IN = hc.IN
OUT = qc_paths.QC_ROOT / "house_tie"; OUT.mkdir(parents=True, exist_ok=True)
LM = hc.LM
POSE1 = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\house1_cohort_pose_2026c.json")
OCC = Path(r"D:\Field2026_analysis_out\2026c\cv_field_ch01_occlusion_20261006_1555\occluders.json")
HOUSE_OF = {"CH05": "HOUSE_1", "CH06": "HOUSE_2"}
POLE_OF = {"CH05": "B1", "CH06": "B3"}
# CH01 / CH02 09-18 px -> 09-04 12:00 px (analysis run cv_field_landmark_track_ch0102_0904noon_20261006_1540; NOTE_HOUSE1_
# COHORT_LABELS_2026-10-06.md)
NOON_A = {"CH01": [[0.9995522006960765, 0.00029984871570908067, 11.528658573124982], [-0.0010881634179411362, 1.0001713904362235, 5.9452789067268865]],
          "CH02": [[1.0009043772608561, 0.0024592448353249335, 12.44847029771644], [-0.0010328077979287753, 1.0018389662640357, 0.18109587660199675]]}


def split_straight(p, tol=8.0):
    """a clicked polyline -> its straight runs: split at the vertex farthest from the chord while that is > tol px. An
    operator piece can follow two edges - CH05 / CH06's HOUSE_n_ROOF_Y pieces are whole gable outlines, eave corner ->
    ridge end -> eave corner - which house_check.py scores as one straight edge (half of such a piece then misses its
    rake by 10-20 cm). Splitting an already straight piece only cuts it into runs on the same edge."""
    if len(p) <= 2:
        return [p]
    a, b = p[0], p[-1]; u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    d = np.abs((p - a) @ np.array([-u[1], u[0]])); k = int(np.argmax(d))
    if d[k] <= tol:
        return [p]
    return split_straight(p[:k + 1], tol) + split_straight(p[k:], tol)


def label_px(path, keys, A=None, add=(0.0, 0.0)):
    """label pieces of one frame -> [(key, uv samples every ~15 px)], each piece cut into straight runs.
    A: a 2 x 3 affine applied to the clicks first (cohort px -> 09-18 px); add: a constant offset after it (IR -> colour)."""
    L = json.loads(Path(path).read_text(encoding="utf-8"))["landmarks"]; out = []
    for key in keys:
        for q in L.get(key, []):
            q = np.asarray(q, float).reshape(-1, 2)
            if A is not None:
                q = q @ np.asarray(A)[:, :2].T + np.asarray(A)[:, 2]
            for p in split_straight(q + np.asarray(add)):
                if len(p) < 2:
                    continue
                pts = []
                for a, b in zip(p[:-1], p[1:]):
                    n = max(2, int(np.hypot(*(b - a)) / 15)); pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
                pts.append(p[-1]); out.append((key, np.array(pts)))
    return out


def house_keys(h):
    return [f"{h}_{k}" for k in ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z")]


def moved(cam, x, pivot=None):
    return cohort_tie.turned(cam, x, pivot)


def pieces(cam, lab):
    out = []
    for key, uv in lab:
        d = cam.rays(uv); ok = np.isfinite(d).all(1)
        if ok.sum() >= 3:
            out.append(dict(cam=cam.name, key=key.split("_", 2)[-1] if key.startswith("HOUSE") else key, d=d[ok],
                            C=np.asarray(cam.centre, float)))
    return out


def roof_miss(cam, lab, edges, x):
    return np.concatenate([a[2] for a in hc.assign(pieces(cam, lab), edges, x)])


def pole_miss(cam, plab, pole):
    """|distance of each labelled pole-edge ray from the pole axis - radius| (mm): a silhouette ray grazes the cylinder"""
    if not plab:
        return np.zeros(0)
    A, B, r = pole
    e = (B - A) / np.linalg.norm(B - A); C = np.asarray(cam.centre, float); out = []
    for _, uv in plab:
        d = cam.rays(uv); d = d[np.isfinite(d).all(1)]
        n = np.cross(d, e); n /= np.linalg.norm(n, axis=1)[:, None]
        out.append(np.abs(np.abs((C - A) @ n.T) - r))
    return np.concatenate(out)


def fit_motion(cam, lab, plab, edges, x, pole, k, pivot=None):
    def resid(p):
        m = moved(cam, p, pivot)
        return np.r_[roof_miss(m, lab, edges, x), pole_miss(m, plab, pole)] / 10.0      # cm
    sol = least_squares(resid, np.zeros(k), loss="soft_l1", f_scale=1.0, x_scale=np.r_[[0.01] * 3, [20.0] * 3][:k], diff_step=1e-4)
    J = sol.jac; cov = np.linalg.pinv(J.T @ J) * np.median(sol.fun ** 2) / 0.4549   # rough: robust scale, normal errors
    return sol.x, cov


def joint_pose(house, cams_labels):
    """house_check's joint fit (coarse grid, then 4 free numbers) on [(cam, lab)] -> x"""
    edges = hc.house_edges(house)[0]
    PC = [p for cam, lab in cams_labels for p in pieces(cam, lab)]
    starts = []
    for th0 in (0.0, 90.0, 180.0, 270.0):
        for dx in np.arange(-12, 13, 3.0):
            for dy in np.arange(-9, 10, 3.0):
                x0 = np.array([hc.DESIGN_XY[house][0] + dx, hc.DESIGN_XY[house][1] + dy, th0, 50.0])
                starts.append((np.median(np.concatenate([a[2] for a in hc.assign(PC, edges, x0)])), x0))
    starts.sort(key=lambda t: t[0]); best = None
    for _, x0 in starts[:6]:
        x = hc.fit(PC, edges, x0)
        r = np.median(np.concatenate([a[2] for a in hc.assign(PC, edges, x)]))
        if best is None or r < best[1]:
            best = (x, r)
    return best[0]


def pixel_map(cam, mcam, step=40):
    """cohort pixels (moved camera) -> rev g pixels seeing the same point at height Z; only pixels with ground"""
    W, H = cam.upright_size
    u, v = np.meshgrid(np.arange(step / 2, W, step), np.arange(step / 2, H, step)); uv = np.c_[u.ravel(), v.ravel()]
    X = mcam._ground(uv, Z); ok = np.isfinite(X).all(1)
    u18 = np.full_like(uv, np.nan); u18[ok] = cam.to_paddock_inv(X[ok], z_mm=Z)
    ok &= np.isfinite(u18).all(1)
    return uv[ok], u18[ok], X[ok]


def affine(src, dst):
    M = np.c_[src, np.ones(len(src))]
    B = np.linalg.lstsq(M, dst, rcond=None)[0].T                          # 2 x 3, frame px -> rev g px
    return B, np.linalg.norm(M @ B.T - dst, axis=1)


def inv2x3(A):
    return np.linalg.inv(np.vstack([np.asarray(A, float), [0, 0, 1]]))[:2]


cams = hc.cams
occ = json.loads(OCC.read_text(encoding="utf-8"))["poles"]
POLES = {c: (np.array(occ[p]["A"], float), np.array(occ[p]["B"], float), float(occ[p]["radius_mm"])) for c, p in POLE_OF.items()}
lab = {(c, t): label_px(LM / f"landmarks_{c}_{t}.json", house_keys(HOUSE_OF[c]))
       for c in ("CH05", "CH06") for t in ("20260918_141000", "20260904_120002", "20260904_030100")}
plab = {(c, t): label_px(LM / f"landmarks_{c}_{t}.json", [f"POLE_{POLE_OF[c]}_L", f"POLE_{POLE_OF[c]}_R"])
        for c in ("CH05", "CH06") for t in ("20260918_141000", "20260904_120002", "20260904_030100")}
def own_pole(cam, plab18, pole):
    """the pole cylinder as this camera saw it in its calibration frame: the CH01 + CH02 cylinder shifted perpendicular to
    its axis at both ends (4 numbers, weak 50 mm prior) until the 09-18 pole-edge labels graze it from the unmoved
    camera. rev g's CH05 / CH06 miss the CH01 + CH02 cylinder by ~4 cm (the pole runs into the frame's bottom edge,
    0.6-0.9 m from the lens, outside the ground the ray correction was fitted on), so the pole is used differentially:
    its image may only move by the camera's motion since 09-18 (CH01 / CH02 see no lean change of B1 / B3)."""
    A, B, r = pole; e = (B - A) / np.linalg.norm(B - A)
    a = np.cross(e, [0, 0, 1.0]); a /= np.linalg.norm(a); b = np.cross(e, a)
    def mk(q):
        return (A + q[0] * a + q[1] * b, B + q[2] * a + q[3] * b, r)
    sol = least_squares(lambda q: np.r_[pole_miss(cam, plab18, mk(q)) / 10.0, q / 50.0], np.zeros(4), loss="soft_l1", f_scale=1.0)
    return mk(sol.x), sol.x


# the 09-18 house poses, refitted as house_check.py does but with the pieces cut into straight runs
X_0918 = {h: joint_pose(h, [(cams[c], label_px(sorted(LM.glob(f"landmarks_{c}_20260918_*.json"))[-1], house_keys(h), add=hc.IR2COL.get(c, (0.0, 0.0))))
                            for c in ("CH01", "CH02", {"HOUSE_1": "CH05", "HOUSE_2": "CH06"}[h])])
          for h in ("HOUSE_1", "HOUSE_2")}
# house_1's cohort pose from the CH01 / CH02 09-04 12:00 labels (the json's pose was fitted on the unsplit pieces)
p1 = json.loads(POSE1.read_text(encoding="utf-8"))
X1_JSON = np.array([*p1["centre_in"], p1["ridge_deg"], p1["soil_below_calibration_ground_mm"]])
LAB1 = {c: label_px(LM / f"landmarks_{c}_20260904_120002.json", house_keys("HOUSE_1"), A=inv2x3(NOON_A[c]), add=hc.IR2COL[c]) for c in ("CH01", "CH02")}
X1_COHORT = joint_pose("HOUSE_1", [(cams[c], LAB1[c]) for c in LAB1])
E1 = hc.house_edges("HOUSE_1")[0]
X1_PER = {c: hc.fit(pieces(cams[c], LAB1[c]), E1, X1_COHORT, free=(0, 1, 2)) for c in LAB1}

cases = [  # camera, frame, house pose, what
    ("CH05", "20260918_141000", X_0918["HOUSE_1"], "control: the calibration frame, house_1's 09-18 pose (expect no motion)"),
    ("CH05", "20260904_120002", X1_COHORT, "THE TIE: house_1's cohort pose (CH01 + CH02, 09-04 12:00, same lid segment)"),
    ("CH05", "20260904_030100", X1_COHORT, "other lid segment (before the 09-04 AM round): lid placement + camera"),
    ("CH06", "20260918_141000", X_0918["HOUSE_2"], "control: the calibration frame, house_2's 09-18 pose (expect no motion)"),
    ("CH06", "20260904_120002", X_0918["HOUSE_2"], "check against the analysis repo's image tie (house_2 never moved)"),
    ("CH06", "20260904_030100", X_0918["HOUSE_2"], "check against the analysis repo's night table (03:00 sample)"),
]
# the analysis repo's image registrations for CH06 (frame px -> 09-18 px): night table 09-04 03:00 sample, day tie
TABLE_B = {("CH06", "20260904_030100"): np.array([[0.996673981527922, 0.008001248831187009, 23.004305201653512],
                                                    [-0.0019855298237154693, 0.9935392929363177, 6.944904543538446]]),
           ("CH06", "20260904_120002"): inv2x3([[1.004805828968026, -0.0011258937159328991, -32.05218871518841],
                                                [0.001020153033766953, 1.0036078973622506, -4.036260690101648]])}

L = [f"HOUSE TIE  cameras: release (rev g); labels {LM}; poles {OCC}; head height z = {Z:.0f} mm above the local ground", "",
     "09-18 house poses (house_check.py's fit, pieces cut into straight runs): "
     + "; ".join(f"{h} ({x[0]:.1f}, {x[1]:.1f}) in, {x[2] % 180:.1f} deg, soil {x[3]:+.0f} mm" for h, x in X_0918.items()),
     f"house_1 cohort pose, {POSE1.name} (unsplit pieces): ({X1_JSON[0]:.1f}, {X1_JSON[1]:.1f}) in, {X1_JSON[2] % 180:.1f} deg, soil {X1_JSON[3]:+.0f} mm",
     f"house_1 cohort pose refitted here (CH01 + CH02 09-04 12:00): ({X1_COHORT[0]:.1f}, {X1_COHORT[1]:.1f}) in, {X1_COHORT[2] % 180:.1f} deg, "
     f"soil {X1_COHORT[3]:+.0f} mm; " + "; ".join(f"{c} alone ({v[0]:.1f}, {v[1]:.1f}) in, {v[2] % 180:.1f} deg, miss median "
                                                  f"{np.median(roof_miss(cams[c], LAB1[c], E1, v)):.0f} mm" for c, v in X1_PER.items())
     + f"; CH01 - CH02 {np.linalg.norm((X1_PER['CH01'][:2] - X1_PER['CH02'][:2]) * IN):.0f} mm",
     "poles: " + "; ".join(f"{p} foot ({A[0] / IN:.1f}, {A[1] / IN:.1f}) in -> top ({B[0] / IN:.1f}, {B[1] / IN:.1f}) in at {B[2]:.0f} mm, r {r:.0f} mm"
                           for p, (A, B, r) in zip(POLE_OF.values(), POLES.values())), ""]
OWN = {}
for c in ("CH05", "CH06"):
    OWN[c], q = own_pole(cams[c], plab[(c, "20260918_141000")], POLES[c])
    L.append(f"{c}: pole {POLE_OF[c]} as the camera saw it on 09-18: the CH01 + CH02 cylinder missed by median "
             f"{np.median(pole_miss(cams[c], plab[(c, '20260918_141000')], POLES[c])):.0f} mm; shifted by {np.hypot(q[0], q[1]):.0f} mm at the foot, "
             f"{np.hypot(q[2], q[3]):.0f} mm at the top -> miss {np.median(pole_miss(cams[c], plab[(c, '20260918_141000')], OWN[c])):.0f} mm")
L.append("")
# models: the camera turned on its bracket (pivot = its centre) or the crossbeam turned at the pole top (pivot = the
# pole top); 'rigid' (turn + free shift) only as a diagnostic - CH01 / CH02 see no lean change, so the crossbeam's
# junction with the pole did not move, and the camera centre can only swing on the 0.6 m crossbeam
MODELS = (("centre", 3, "centre"), ("pole top", 3, "top"), ("rigid", 6, "centre"))
res = {}
for c, t, x, what in cases:
    cam = cams[c]; edges = hc.house_edges(HOUSE_OF[c])[0]; lb, pb, pole = lab[(c, t)], plab[(c, t)], OWN[c]
    r0, q0 = roof_miss(cam, lb, edges, x), pole_miss(cam, pb, pole)
    L.append(f"{c} {t}  {what}")
    L.append(f"  {len(r0)} roof samples ({len(lb)} straight runs), {len(q0)} pole-edge samples; unmoved camera: roof miss median "
             f"{np.median(r0):.0f} mm, p90 {np.percentile(r0, 90):.0f}; pole miss median {np.median(q0):.0f} mm, p90 {np.percentile(q0, 90):.0f}")
    out = {}
    for mn, k, pv in MODELS:
        piv = None if pv == "centre" else pole[1]
        p, cov = fit_motion(cam, lb, pb, edges, x, pole, k, piv); m = moved(cam, p, piv)
        r1, q1 = roof_miss(m, lb, edges, x), pole_miss(m, pb, pole)
        uv, u18, Xg = pixel_map(cam, m)
        B, ra = affine(uv, u18)
        sh = np.linalg.norm(u18 - uv, axis=1)
        dmm = np.linalg.norm(Xg - cam._ground(uv, Z), axis=1)
        sd = np.sqrt(np.diag(cov))
        out[mn] = dict(p=p, m=m, uv=uv, u18=u18, Xg=Xg, B=B, pivot=(np.asarray(cam.centre, float) if piv is None else piv))
        L.append(f"  {mn:8s}: centre moves {np.linalg.norm(m.centre - cam.centre):.0f} mm, turn {np.degrees(np.linalg.norm(p[:3])):.2f} deg (w = {np.degrees(p[:3]).round(2).tolist()} +- {np.degrees(sd[:3]).round(2).tolist()} deg)"
                 + (f", shift {np.linalg.norm(p[3:]):.0f} mm (t = {p[3:].round(0).tolist()} +- {sd[3:].round(0).tolist()} mm)" if k == 6 else "")
                 + f"; roof miss median {np.median(r1):.0f} / p90 {np.percentile(r1, 90):.0f} mm, pole {np.median(q1):.0f} / {np.percentile(q1, 90):.0f} mm")
        L.append(f"         pixel shift median {np.median(sh):.1f} px, max {sh.max():.1f}; ground at z = {Z:.0f} mm moved median {np.median(dmm):.0f} mm, "
                 f"max {dmm.max():.0f}; affine residual median {np.median(ra):.2f} px, max {ra.max():.2f}")
    for a_, b_ in (("centre", "pole top"), ("centre", "rigid")):
        d = np.linalg.norm(out[a_]["Xg"] - out[b_]["Xg"], axis=1)
        L.append(f"  {a_} vs {b_} at z = {Z:.0f} mm: median {np.median(d):.0f} mm, p90 {np.percentile(d, 90):.0f}, max {d.max():.0f} (over the frame's ground)")
    if (c, t) in TABLE_B:
        Bt = TABLE_B[(c, t)]
        for mn, _, _ in MODELS:
            o = out[mn]; pt = o["uv"] @ Bt[:, :2].T + Bt[:, 2]
            dp = np.linalg.norm(pt - o["u18"], axis=1)
            dm = np.linalg.norm(cam._ground(pt, Z) - o["Xg"], axis=1); ok = np.isfinite(dm)
            L.append(f"  vs the analysis repo's image registration ({mn}): {np.median(dp):.1f} px median, p90 {np.percentile(dp, 90):.1f}, "
                     f"max {dp.max():.1f}; at z = {Z:.0f} mm {np.median(dm[ok]):.0f} mm median, p90 {np.percentile(dm[ok], 90):.0f}, max {dm[ok].max():.0f}")
    res[f"{c}_{t}"] = {mn: dict(rotvec_rad=o["p"][:3].tolist(), pivot_mm=np.asarray(o["pivot"]).tolist(), shift_mm=np.r_[o["p"], np.zeros(6)][3:6].tolist(),
                                centre_mm=np.asarray(o["m"].centre).tolist(), affine_frame_to_revg_px=o["B"].tolist()) for mn, o in out.items()}
    L.append("")
# differential tie: the control's apparent motion at 09-18 is the disagreement between the camera's own view of the
# house and the house pose from CH01 + CH02 (the same model, the same views at both dates), so remove it - true cohort
# rays = R_18^T R_cohort d (camera-centre turns)
L.append("DIFFERENTIAL (cohort fit minus the 09-18 control fit, camera-centre turns)")
DIFF = {}
for c, t in (("CH05", "20260904_120002"), ("CH05", "20260904_030100"), ("CH06", "20260904_120002"), ("CH06", "20260904_030100")):
    cam = cams[c]; w18 = np.array(res[f"{c}_20260918_141000"]["centre"]["rotvec_rad"]); w = np.array(res[f"{c}_{t}"]["centre"]["rotvec_rad"])
    Rd = Rotation.from_rotvec(w18).as_matrix().T @ Rotation.from_rotvec(w).as_matrix(); wd = Rotation.from_matrix(Rd).as_rotvec()
    m = moved(cam, wd); uv, u18, Xg = pixel_map(cam, m); B, ra = affine(uv, u18)
    sh = np.linalg.norm(u18 - uv, axis=1); dmm = np.linalg.norm(Xg - cam._ground(uv, Z), axis=1)
    lb, pb = lab[(c, t)], plab[(c, t)]; x = X1_COHORT if c == "CH05" else X_0918["HOUSE_2"]
    r1, q1 = roof_miss(m, lb, hc.house_edges(HOUSE_OF[c])[0], x), pole_miss(m, pb, OWN[c])
    Xc = res[f"{c}_{t}"]["centre"]
    d_c = np.linalg.norm(Xg - moved(cam, np.array(Xc["rotvec_rad"]))._ground(uv, Z), axis=1)
    L.append(f"  {c} {t}: turn {np.degrees(np.linalg.norm(wd)):.2f} deg (w = {np.degrees(wd).round(2).tolist()} deg); roof miss median {np.median(r1):.0f} / "
             f"p90 {np.percentile(r1, 90):.0f} mm, pole {np.median(q1):.0f} / {np.percentile(q1, 90):.0f} mm; pixel shift median {np.median(sh):.1f} px; "
             f"ground at z = {Z:.0f} mm moved median {np.median(dmm):.0f} mm; vs the direct fit {np.median(d_c):.0f} mm median, p90 {np.percentile(d_c, 90):.0f}; "
             f"affine residual median {np.median(ra):.2f} px, max {ra.max():.2f}")
    DIFF[(c, t)] = dict(turn_deg=float(np.degrees(np.linalg.norm(wd))), ground_moved_med_mm=float(np.median(dmm)),
                        vs_direct_fit_med_mm=float(np.median(d_c)), vs_direct_fit_p90_mm=float(np.percentile(d_c, 90)),
                        roof_miss_med_mm=float(np.median(r1)), pole_miss_med_mm=float(np.median(q1)))
    if (c, t) in TABLE_B:
        Bt = TABLE_B[(c, t)]; pt = uv @ Bt[:, :2].T + Bt[:, 2]
        dp = np.linalg.norm(pt - u18, axis=1); dm = np.linalg.norm(cam._ground(pt, Z) - Xg, axis=1); ok = np.isfinite(dm)
        DIFF[(c, t)].update(vs_image_registration_med_px=float(np.median(dp)), vs_image_registration_med_mm=float(np.median(dm[ok])),
                            vs_image_registration_p90_mm=float(np.percentile(dm[ok], 90)))
        L.append(f"    vs the analysis repo's image registration: {np.median(dp):.1f} px median, p90 {np.percentile(dp, 90):.1f}, max {dp.max():.1f}; "
                 f"at z = {Z:.0f} mm {np.median(dm[ok]):.0f} mm median, p90 {np.percentile(dm[ok], 90):.0f}, max {dm[ok].max():.0f}")
    res[f"{c}_{t}"]["differential"] = dict(rotvec_rad=wd.tolist(), pivot_mm=np.asarray(cam.centre, float).tolist(), shift_mm=[0.0, 0.0, 0.0],
                                           centre_mm=np.asarray(cam.centre, float).tolist(), affine_frame_to_revg_px=B.tolist())
L.append("")
(OUT / "HOUSE_TIE.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / "house_tie.json").write_text(json.dumps(dict(z_mm=Z, house_poses={"HOUSE_1_cohort": X1_COHORT.tolist(),
                                                                           **{f"{h}_0918": x.tolist() for h, x in X_0918.items()}},
                                                     ties=res), indent=1), encoding="utf-8")
print("\n".join(L))

if "--write-ties" in args:                                               # the committed tie file cohort_tie.py reads
    pv = {k: res[f"CH05_{k}"] for k in ("20260904_030100", "20260904_120002")}
    ties = dict(
        _about="Cohort-3 (2026c) ties of cameras whose cohort frames cannot be registered to their calibration frame: the "
               "release camera (rev g) turned about its centre by rotvec_rad (paddock frame) gives the camera as it stood at "
               "that reference frame. Read with cohort_tie.py. Made by house_tie.py --write-ties.",
        made=f"{datetime.now():%Y-%m-%dT%H:%M}", z_mm_for_checks=Z,
        release_sha256=cohort_tie.release_sha(),
        inputs=dict(labels=str(LM), poles=str(OCC), house1_cohort_pose_json=str(POSE1),
                    labels_sha256={f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(LM.glob("landmarks_CH0[1256]_2026090[4]_*.json")) + sorted(LM.glob("landmarks_CH0[1256]_20260918_*.json"))}),
        method="house_1 (rigid house_check model) at its cohort pose refitted from the CH01 + CH02 09-04 12:00 labels "
               f"({X1_COHORT[0]:.1f}, {X1_COHORT[1]:.1f}) in, ridge {X1_COHORT[2] % 180:.1f} deg, soil {X1_COHORT[3]:+.0f} mm, and pole B1 as CH05 itself "
               "saw it on 09-18 (the CH01 + CH02 cylinder shifted to CH05's 09-18 pole edges); the camera turned about its "
               "centre to fit the roof and pole edges of the 09-04 frame; minus the same fit on the 09-18 frame against the "
               "house's 09-18 pose (the common disagreement between CH05's own view and the CH01 + CH02 house pose cancels). "
               "Label pieces cut into straight runs (the ROOF_Y pieces are whole gable outlines).",
        validation={"CH06 (house_2 never moved; analysis repo image registration 09-18 <-> 09-04 as the reference)": {
                        t: DIFF[("CH06", t)] for t in ("20260904_120002", "20260904_030100")},
                    "CH05 03:01 vs 12:00 (one lid round apart)": dict(
                        turn_difference_deg=float(np.degrees(np.linalg.norm(cohort_tie.cv2.Rodrigues(
                            cohort_tie.cv2.Rodrigues(np.array(res["CH05_20260904_030100"]["differential"]["rotvec_rad"]))[0].T @
                            cohort_tie.cv2.Rodrigues(np.array(res["CH05_20260904_120002"]["differential"]["rotvec_rad"]))[0])[0])))),
                    "CH05 direct fit, pivot camera centre vs pole top (model uncertainty)": "see HOUSE_TIE.txt"},
        cameras={"CH05": dict(
            why="house_1 was moved on 09-18 (the calibration day): no image registration ties CH05's cohort frames to 09-18",
            frames={("2026-09-04 03:01:00" if k.endswith("030100") else "2026-09-04 12:00:02"): dict(
                target_frame="09-04 03:01" if k.endswith("030100") else "09-04 12:00",
                label_file=f"landmarks_CH05_{k}.json", rotvec_rad=v["differential"]["rotvec_rad"], pivot_mm=None,
                turn_deg=DIFF[("CH05", k)]["turn_deg"], ground_moved_med_mm=DIFF[("CH05", k)]["ground_moved_med_mm"],
                affine_frame_to_revg_px=v["differential"]["affine_frame_to_revg_px"])
                for k, v in pv.items()})})
    (Path(__file__).resolve().parent / "cohort_ties_2026c.json").write_text(json.dumps(ties, indent=1), encoding="utf-8")
    print("->", Path(__file__).resolve().parent / "cohort_ties_2026c.json")
