# -*- coding: utf-8 -*-
r"""Per-camera intrinsics from the FREE-POSE views.

Free-pose views are the cached detections that belong to no station: the operator carrying the
board between stations and the two deliberate sweeps in front of CH03 and CH04. They are the only
material in this capture whose board orientations vary, and that is exactly what an intrinsic
calibration needs - the 136 station placements all lie in one plane (the ground), and one plane
carries only its own homography, which cannot separate focal length from tilt.

Two numbers here DO come from the operator's tape-measured lens heights (2026-09-24), because
nothing in the footage can give them: a hand-held sweep from one standing spot leaves focal
length and distance degenerate (CH04's sweep is fitted equally well by any f from 2800 to 3130
px), and plates on the ground are one plane. With the height hard-fixed at the tape value and the
plates on the ground, the plates' apparent size fixes the scale:
  * CH04 f = 2960 px (sweep said 3130; same camera model as CH03, whose sweep 2949 agrees with its
    tape height; the ground cones/cords/walls at CH04's tape height ask for 2956).
  * Duo 3 canvas fu = 2325, fv = 2660 px/rad (nominal W/pi = 2444.6 for both): CH01 and CH02
    fitted independently give 2333/2711 and 2318/2616 - the canvas is ~190 deg x 47 deg, not
    180 x 50.6. With the nominal scale every camera came out 8-20 % too high.
FIT_NOMINAL_LENS=1 restores the sweep / nominal values.
"""
import csv, json, os
from pathlib import Path
import numpy as np, cv2
import qc_paths, board_detect as bd

REPO = Path(__file__).resolve().parent
PANO = ("CH01", "CH02")
SESSIONS = ("2026-09-18", "2026-09-19")
NOMINAL = os.environ.get("FIT_NOMINAL_LENS", "") == "1"
FOCAL_OVERRIDE = {} if NOMINAL else {"CH04": 2960.0}            # px, from the taped height (see above)
PANO_SCALE = None if NOMINAL else (2325.0, 2660.0)              # fu, fv px/rad, from the taped heights


def _sec(hms):
    h, m, sec = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def free_views(cam, min_c=20, sessions=SESSIONS):
    out = []
    for s in sessions:
        session, qc = qc_paths.resolve(None if s == sessions[0] else s)
        date = qc_paths.session_date(session)
        f = REPO / f"session_{date}_labelled_frames.csv"
        if not f.exists():
            continue
        # The operator's review of the hand-held sweeps (manual_board_gui --sweep): once a camera's
        # sweep has been reviewed, only frames inside windows he accepted or re-clicked are used; a
        # frame he marked not visible / partial / rejected is out even if the machine decoded it.
        # Corners PREDICTED from an outline (method *outline*) are never measurements and never
        # enter a lens fit: they are exactly homography-consistent and would pull the distortion to 0.
        review = {}
        mq = REPO / f"session_{date}_manual_quads.json"
        if mq.exists():
            for j in json.loads(mq.read_text(encoding="utf-8")):
                if j.get("station", "").startswith("SW"):
                    review.setdefault(j["cam"], []).append((_sec(j["win"][0]), _sec(j["win"][1]), j.get("verdict", "operator")))
        for r in csv.DictReader(open(f, newline="", encoding="utf-8")):
            if r["cam"] != cam or r["station"] or int(r["n_corners"]) < min_c:
                continue
            if "outline" in r.get("method", "") or "rect-markers" in r.get("method", ""):
                continue                    # predicted corners, not measurements (audit 2026-09-24)
            if cam in review:
                t = _sec(r["clock"])
                if not any(a <= t <= b + 0.5 and v in ("accept", "operator") for a, b, v in review[cam]):
                    continue
            p = qc / "corners" / cam / r["file"]
            if not p.exists():
                continue
            with np.load(p, allow_pickle=False) as z:
                ids = z["ids"].astype(int)
                px = qc_paths.stored_to_upright(z["px"].astype(float), session, cam)
            out.append(dict(ids=ids, obj_mm=bd.OBJ_MM[ids], px=px, sigma=1.0,
                            up=qc_paths.upright_size(session, cam), clock=r["clock"], session=date))
    return out


def robust_pinhole(views, W, H):
    """cv2 calibration on the free-pose views, with rejection passes for views whose own
    reprojection is far worse than the rest (a blurred or half-occluded board)."""
    obj = [np.concatenate([v["obj_mm"], np.zeros((len(v["ids"]), 1))], 1).astype(np.float32) for v in views]
    img = [v["px"].astype(np.float32) for v in views]
    flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO |
             cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K3)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 300, 1e-12)
    keep = list(range(len(obj)))
    K = d = None
    for _ in range(3):
        K = np.array([[0.75 * W, 0, W / 2], [0, 0.75 * W, H / 2], [0, 0, 1.0]])
        d = np.zeros(5)
        rms, K, d, rv, tv = cv2.calibrateCamera([obj[i] for i in keep], [img[i] for i in keep],
                                                (W, H), K, d, flags=flags, criteria=crit)
        per = np.array([float(np.sqrt((np.linalg.norm(
            cv2.projectPoints(obj[i], rv[j], tv[j], K, d)[0].reshape(-1, 2) - img[i], axis=1) ** 2).mean()))
            for j, i in enumerate(keep)])
        cut = max(2.0, 3.0 * np.median(per))
        if (per <= cut).all() or (per <= cut).sum() < 8:
            break
        keep = [i for i, e in zip(keep, per) if e <= cut]
    return dict(model="pinhole", intr=np.array([K[0, 0], K[0, 2], K[1, 2], d.ravel()[0], d.ravel()[1]]),
                rms=float(rms), n_views=len(keep), n_dropped=len(obj) - len(keep))


def pano_intrinsics(W, H):
    """The Duo3 canvas is an exact 180 deg equirectangular image: solving fu, cu, fv, cv freely on
    the free-pose views returns W/pi, (W-1)/2, W/pi, (H-1)/2 to within 0.03 %, from either half and
    either session. They are held at nominal - a pano has no focal length to calibrate, only a
    pose."""
    fu, fv = PANO_SCALE if PANO_SCALE else (W / np.pi, W / np.pi)
    return dict(model="equirect", intr=np.array([fu, (W - 1) / 2.0, fv, (H - 1) / 2.0, 0.0]),
                rms=float("nan"), n_views=0, n_dropped=0, scale_source="taped heights" if PANO_SCALE else "nominal W/pi")


def for_camera(cam, min_c=20):
    W, H = qc_paths.upright_size(qc_paths.resolve(None)[0], cam)
    if cam in PANO:
        r = pano_intrinsics(W, H)
        r["n_views"] = len(free_views(cam, min_c))
        return r
    V = free_views(cam, min_c)
    if len(V) < 8:
        return None
    r = robust_pinhole(V, W, H)
    if cam in FOCAL_OVERRIDE:
        r["intr"] = np.array(r["intr"], float); r["intr"][0] = FOCAL_OVERRIDE[cam]; r["f_source"] = "taped height"
    return r
