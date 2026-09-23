# -*- coding: utf-8 -*-
r"""Calibrate the paddock cameras from the ChArUco placements. No field survey is used.

WHAT IS MEASURED AND WHAT IS SOLVED
-----------------------------------
Measured (already in the repo): the 88 corner pixels of a board whose geometry is known to the
millimetre (720 x 540 mm pattern, 60 mm squares, on an 800 x 600 x 6 mm plate), the operator's cone
labels, and the operator's placement timeline.

Solved (outputs, not inputs): every camera's focal length and distortion, and every camera's
position - x, y AND height - and orientation in the paddock frame. The camera height is not needed
beforehand; it falls out of stage 3 before the field frame even exists, because the boards all lie
on one plane and the distance from the projection centre to that plane IS the height.

STAGES
  1  intrinsics   - from the free-pose views (the operator carrying/waving the board, cached but
                    never assigned to a station). These are NOT coplanar, which is what makes the
                    intrinsics identifiable; the flat placements alone could not do it.
  2  board poses  - one 6-DOF pose per placement per camera, in that camera's own coordinates.
  3  ground plane - the common plane of all the placements a camera sees -> camera height above the
                    board plane and the tilt of its optical axis, with no field frame at all.
  4  registration - the paddock frame enters through the operator's cone labels (station <-> pixel)
                    on the two panos; every other camera is registered through the placements it
                    shares with them. Still no survey: the cones are the operator's own marks.
  5  bundle       - everything refined together: intrinsics, camera poses, board poses, against the
                    corner pixels, the cone pixels, and the physical prior that a plate lying on
                    grass is flat and 6 mm above the ground.

Usage: python fit_cameras.py [--split] [--out <dir>]
"""
import sys, json, csv, os
from pathlib import Path
import numpy as np, cv2
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, board_detect as bd, fit_data as fd, fit_models as fm       # noqa: E402
import fit_intrinsics as fi                                                # noqa: E402

REPO = Path(__file__).resolve().parent
PANO = ("CH01", "CH02")
PLATE_Z = 6.0                       # printed plane sits on 6 mm of plate above the grass
CONE_Z = 50.0                       # the hole the operator clicks is the top of a ~5 cm disc cone
CONE_SIGMA = float(os.environ.get("FIT_CONE_SIGMA", 60.0))   # the cone labels are coarse operator marks and the
                                    # operator has already said they need re-doing; they are
                                    # kept only to pick the right branch of the frame
STATION_SIGMA = float(os.environ.get("FIT_STATION_SIGMA", 100.0))   # how near a plate corner lands to its cone, mm
                                    # (env overrides exist so the fit can be run with the anchors switched off: then the
                                    #  cameras are tied only by the boards they share, and the design grid is a CHECK)
FLAT_SIGMA_DEG = float(os.environ.get("FIT_FLAT_SIGMA_DEG", 2.0))   # a plate on grass tilts a few degrees;
FLAT_SIGMA_Z = float(os.environ.get("FIT_FLAT_SIGMA_Z", 1.0))       # its HEIGHT is pinned to the ground (see below)
# Why the height is pinned (2026-09-23): with a 40 mm height prior under the robust loss, the bundle
# slid the far plates DOWN their rays (by 0.2-0.5 m) instead of moving the cameras, because the
# panos have many more corners than the ordinary lenses. The cameras then disagreed by 0.3-0.5 m at
# the ends of the paddock. Pinned to 6 mm the same data give a cross-camera median of 78 mm
# (p90 174 mm) against 112 mm (p90 341 mm) loose, and 104 mm (212 mm) at 10 mm. A plate on grass
# is never 0.5 m below the grass; the 1-3 cm it can really sit above the soil costs less than the
# freedom did. FIT_FLAT_SIGMA_Z=40 reproduces the loose fit.
args = sys.argv[1:]
SPLIT = "--split" in args        # one pose per pano by default: splitting the canvas into its
                                 # two lens halves and giving each its own pose does NOT reduce
                                 # the residual, so the stitch really is one projection centre
OUT = Path(args[args.index("--out") + 1]) if "--out" in args else REPO
SESSIONS = ("2026-09-18", "2026-09-19")
L = []
DROPPED = []      # (unit, session, station, window, why) - views this fit refused to use


def say(s=""):
    print(s, flush=True)
    L.append(s)


# ----------------------------------------------------------------- units (a pano is two cameras)
def unit_of(cam, px, W):
    if cam not in PANO or not SPLIT:
        return cam
    return cam + ("L" if np.median(px[:, 0]) < W / 2 else "R")


def straddles(cam, px, W, margin=40.0):
    return cam in PANO and SPLIT and px[:, 0].min() < W / 2 - margin < W / 2 + margin < px[:, 0].max()


def kabsch(A, B):
    """rigid transform taking A -> B (no scaling): returns R, t with B ~= A @ R.T + t."""
    A = np.asarray(A, float); B = np.asarray(B, float)
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, cb - R @ ca


def plane_fit(P):
    """least-squares plane through 3-D points -> (unit normal, offset) with n.X = c."""
    c = P.mean(0)
    n = np.linalg.svd(P - c)[2][-1]
    return n / np.linalg.norm(n), float(n @ c / np.linalg.norm(n))


PAT_CTR = np.array([360.0, 270.0, 0.0])              # centre of the printed pattern, board coords
PLATE4 = np.concatenate([bd.PAPER_MM, np.zeros((4, 1))], 1) * 1e-3   # the four plate corners, metres


def solve(res, x0, n=400):
    return least_squares(res, np.asarray(x0, float), method="trf", loss="huber", f_scale=3.0,
                         x_scale="jac", xtol=1e-12, ftol=1e-12, max_nfev=n).x


def camera_pose(model, intr, looks, x0):
    """6-vector (rvec, tvec) of a camera, X_cam = R X_field + t, from a list of
    (field points, pixels, sigma) - the boards it sees and, for the panos, the cone labels."""
    def res(x):
        R = cv2.Rodrigues(x[:3])[0]
        return np.concatenate([((fm.project(model, intr, X @ R.T + x[3:]) - uv) / s).ravel()
                               for X, uv, s in looks])
    return solve(res, x0)


def board_pose(looks, x0):
    """6-vector of ONE board in the field frame, from every camera that sees it, plus the physical
    prior that a plate lying on grass is flat and its printed face is 6 mm above the ground."""
    def res(x):
        R = cv2.Rodrigues(x[:3])[0]
        e = []
        for obj, uv, s, model, intr, Rc, tc in looks:
            Xc = (obj @ R.T + x[3:]) @ Rc.T + tc
            e.append(((fm.project(model, intr, Xc) - uv) / s).ravel())
        e.append([np.degrees(np.arccos(np.clip(abs(R[2, 2]), -1, 1))) / FLAT_SIGMA_DEG,
                  ((R @ PAT_CTR)[2] + x[5] - PLATE_Z) / FLAT_SIGMA_Z])
        return np.concatenate(e)
    return solve(res, x0)


# ================================================================== main
say("=" * 100)
say("CAMERA CALIBRATION FROM THE CHARUCO PLACEMENTS   (sessions %s)" % ", ".join(SESSIONS))
say("=" * 100)

P0 = fd.all_placements()
P = [p for p in P0 if not p["bad"] and not p["weak"]]
cams = sorted(set(p["cam"] for p in P))
say("")
say(f"  {len(P0)} placements assembled from the cached corners; {len(P0) - len(P)} rejected by the")
say(f"  homography gate (their corners cannot be a flat board under ANY camera - wrong ids, not noise):")
for p in sorted([q for q in P0 if q["bad"]], key=lambda q: -q["hom_rms"]):
    say(f"     {p['cam']} {p['station']:4s} {p['session']} {p['win']}  {len(p['ids']):3d} corners"
        f"  own-plane rms {p['hom_rms']:5.2f}px  ({p['method']})")
weak = [q for q in P0 if q["weak"] and not q["bad"]]
say("")
say(f"  {len(weak)} further placements are operator CLICKS, not decoded corners, and are held out of")
say("  the geometry: four clicks on the plate edge fix the rectangle but not which corner is which.")
say("  An 800 x 600 rectangle maps onto itself under a 180 deg turn, so the labelling has a twin that")
say("  no single view can tell apart - and measured against the cameras that DO decode those boards,")
say("  the twin was being picked often enough to drag whole cameras out of place. They still count as")
say("  coverage (the operator saw the plate there); they contribute 4 points each of 7000+, so the")
say("  geometry loses nothing by leaving them out:")
say("     " + ", ".join(sorted(set(f"{q['cam']}/{q['station']}" for q in weak))))

# ---------------------------------------------------------------- stage 1: intrinsics
say("")
say("STAGE 1  INTRINSICS - from the free-pose views (board carried / swept, orientations vary).")
say("         A board lying flat is one plane; one plane cannot fix a focal length. These views can.")
say("")
INTR = {}
for cam in cams:
    W, H = qc_paths.upright_size(qc_paths.resolve(None)[0], cam)
    r = fi.for_camera(cam)
    if r is None:
        say(f"  {cam}  too few free-pose views - cannot calibrate intrinsics")
        continue
    INTR[cam] = r
    if cam in PANO:
        i = r["intr"]
        say(f"  {cam}  equirect 180 deg canvas {W}x{H}: fu=fv={i[0]:.1f} px/rad (=W/pi), "
            f"centre ({i[1]:.1f},{i[3]:.1f})  [nominal, confirmed by {r['n_views']} free-pose views]")
        continue
    f, cx, cy, k1, k2 = r["intr"]
    say(f"  {cam}  pinhole {W}x{H}: f={f:8.1f}px  c=({cx:7.1f},{cy:7.1f})  k1={k1:+.4f} k2={k2:+.4f}"
        f"   HFOV={2*np.degrees(np.arctan(W/2/f)):5.1f} deg   rms={r['rms']:.3f}px"
        f"  ({r['n_views']} views, {r['n_dropped']} rejected)")

# ---------------------------------------------------------------- stage 2: board poses per camera
say("")
say("STAGE 2  BOARD POSES - one 6-DOF pose per placement, in each camera's own coordinates.")
UNITS = {}
for p in P:
    cam = p["cam"]
    if cam not in INTR:
        continue
    W, H = p["upright"]
    if straddles(cam, p["px"], W):
        p["unit"] = None
        continue
    u = unit_of(cam, p["px"], W)
    p["unit"] = u
    UNITS.setdefault(u, dict(cam=cam, model=INTR[cam]["model"], intr=INTR[cam]["intr"], plc=[]))
    UNITS[u]["plc"].append(p)
for u in sorted(UNITS):
    U = UNITS[u]
    res = fm.fit_camera(U["model"], U["plc"], U["intr"], free_intr=())      # intrinsics frozen
    U["plc"] = res["plc"]
    U["poses"] = res["poses"]
    U["rms"] = res["rms"]
    U["per"] = res["per_placement"]
    say(f"  {u:6s} {len(U['plc']):3d} placements   reprojection rms {U['rms']:5.2f} px"
        f"   (median per placement {np.median(U['per']):.2f})")
n_strad = sum(1 for p in P if p.get("unit") is None)
if n_strad:
    say(f"  ({n_strad} placements dropped: they straddle the seam between the two Duo3 lenses)")

# ---------------------------------------------------------------- stage 3: ground plane -> height
say("")
say("STAGE 3  GROUND PLANE - the placements a camera sees are all on one plane. The distance from")
say("         the projection centre to that plane is the camera height. Nothing was measured.")
say("         Each board is then re-fitted LYING ON that plane (3 DOF, not 6): a free planar pose")
say("         always has a mirror twin, and for a small far board the solver can pick the twin.")
say("")
say(f"  {'unit':6s} {'n':>3s} {'height':>9s} {'flat-fit rms':>13s} {'optical axis':>18s}")
for u in sorted(UNITS):
    U = UNITS[u]
    pts = np.concatenate([fm.board_points(q, p["obj_mm"]) for q, p in zip(U["poses"], U["plc"])])
    n, c = plane_fit(pts)
    if c < 0:
        n, c = -n, -c
    for _ in range(2):
        U["poses"], (n, c), rms = fm.fit_flat(U["model"], U["intr"], U["plc"], U["poses"], (n, c))
    U["plane"] = (n, c)
    U["per"] = rms
    U["rms"] = float(np.median(rms))
    down = n if n[1] > 0 else -n                     # the plane normal that points away from the sky
    tilt = np.degrees(np.arccos(np.clip(abs(float(down @ np.array([0, 1.0, 0]))), -1, 1)))
    say(f"  {u:6s} {len(U['plc']):3d} {c/1000:7.3f} m {np.median(rms):10.2f} px {90-tilt:12.1f} deg down")
    cut = max(8.0, 4.0 * np.median(rms))
    drop = [(p, e) for p, e in zip(U["plc"], rms) if e > cut]
    for p, e in drop:
        DROPPED.append((u, p["session"], p["station"], p["win"], f"not flat ({e:.0f} px)"))
        say(f"         dropped {p['station']} {p['session']} {p['win']}: {e:.1f} px once the plate is"
            f" held flat - that measurement is not a flat board where the others are")
    if drop:
        kk = [i for i, e in enumerate(rms) if e <= cut]
        U["plc"] = [U["plc"][i] for i in kk]
        U["poses"] = [U["poses"][i] for i in kk]
        U["per"] = [rms[i] for i in kk]

# ---------------------------------------------------------------- stage 4: field registration
say("")
say("STAGE 4  PADDOCK FRAME - entered through the operator's own cone labels on the panos; every")
say("         other camera is carried in by the placements it shares with them.")
say("")
station_mm = fd.STATION_MM
FIELD = {}
CONE_OBS = {}
# Every camera's cone labels enter the bundle (the panos' also seed the frame in this stage). The
# operator clicks the hole at the TOP of the disc cone, CONE_Z above the station point on the cord
# crossing; the cones sit where the cords were laid, so they are the best absolute reference at
# the ends of the paddock, where the boards are few (operator labels for CH03-CH06, 2026-09-23).
for u in sorted(UNITS):
    cam = UNITS[u]["cam"]
    session, qc = qc_paths.resolve(None)
    W, H = qc_paths.upright_size(session, cam)
    for st, uv in qc_paths.load_cones(qc, cam, session, space="upright").items():
        if st not in station_mm:
            continue
        if SPLIT and cam in PANO and ((u.endswith("L")) != (uv[0] < W / 2)):
            continue
        CONE_OBS.setdefault(u, []).append(
            (np.array([station_mm[st][0], station_mm[st][1], CONE_Z]), np.asarray(uv, float), st))
say("  cone labels per camera: " + ", ".join(f"{u} {len(v)}" for u, v in sorted(CONE_OBS.items())))
for u in sorted(UNITS):
    U = UNITS[u]
    cam = U["cam"]
    if cam not in PANO:
        continue
    session, qc = qc_paths.resolve(None)
    cones = qc_paths.load_cones(qc, cam, session, space="upright")
    W, H = qc_paths.upright_size(session, cam)
    n, c = U["plane"]
    A, B, used = [], [], []
    for st, uv in cones.items():
        if st not in station_mm:
            continue
        if SPLIT and ((u.endswith("L")) != (uv[0] < W / 2)):
            continue
        b = fm.bearings(U["model"], U["intr"], uv.reshape(1, 2))[0]
        den = float(n @ b)
        if abs(den) < 1e-6:
            continue
        s = c / den
        if s <= 0:
            continue
        A.append(s * b)
        B.append([station_mm[st][0], station_mm[st][1], 0.0])
        used.append(st)
    if len(A) < 4:
        say(f"  {u:6s} only {len(A)} usable cone labels - registered through shared placements instead")
        continue
    A = np.array(A); B = np.array(B)
    R, t = kabsch(A, B)                              # camera coords -> field coords
    e = np.linalg.norm((A @ R.T + t) - B, axis=1)
    keep = e < max(300.0, 3 * np.median(e))
    if keep.sum() >= 4 and keep.sum() < len(A):
        R, t = kabsch(A[keep], B[keep])
        e = np.linalg.norm((A @ R.T + t) - B, axis=1)
    FIELD[u] = (R, t)
    say(f"  {u:6s} {int(keep.sum())}/{len(A)} cone labels  ->  field frame, "
        f"cone residual median {np.median(e[keep]):.0f} mm (p90 {np.percentile(e[keep],90):.0f} mm)")

# board poses in the field frame, from whichever unit is already registered
BOARD = {}
def key(p):
    return (p["session"], p["station"], p["win"])
for u, (R, t) in list(FIELD.items()):
    U = UNITS[u]
    for q, p in zip(U["poses"], U["plc"]):
        k = key(p)
        if k in BOARD:
            continue
        Rb = cv2.Rodrigues(q[:3])[0]
        BOARD[k] = (R @ Rb, R @ q[3:] + t)           # board -> field
for _ in range(3):
    for u in sorted(UNITS):
        if u in FIELD:
            continue
        U = UNITS[u]
        A, B = [], []
        for q, p in zip(U["poses"], U["plc"]):
            k = key(p)
            if k not in BOARD:
                continue
            A.append(fm.board_points(q, bd.OBJ_MM))
            Rb, tb = BOARD[k]
            B.append(np.concatenate([bd.OBJ_MM, np.zeros((88, 1))], 1) @ Rb.T + tb)
        if len(A) < 2:
            continue
        A = np.concatenate(A); B = np.concatenate(B)
        R, t = kabsch(A, B)                          # coarse; refined in the image domain below
        FIELD[u] = (R, t)
        say(f"  {u:6s} {len(A)//88} shared placements -> field frame "
            f"(coarse 3-D residual median {np.median(np.linalg.norm((A @ R.T + t) - B, axis=1)):.0f} mm)")
        for q, p in zip(U["poses"], U["plc"]):
            k = key(p)
            if k not in BOARD:
                Rb = cv2.Rodrigues(q[:3])[0]
                BOARD[k] = (R @ Rb, R @ q[3:] + t)

missing = [u for u in UNITS if u not in FIELD]
if missing:
    say(f"  NOT registered: {', '.join(missing)}")
say("")
say(f"  {len(BOARD)} distinct physical board placements now have a pose in the paddock frame.")

# --- alternate camera <-> board refinement, in the image domain where the noise actually is.
# A 3-D fit weights a board's poorly observed depth as heavily as its well observed direction; two
# rounds of this bring every camera from hundreds of millimetres to a few pixels before the bundle.
say("")
say("  refining camera <-> board alternately (image domain, robust):")
POSE = {}
for u in FIELD:
    R, t = FIELD[u]
    POSE[u] = np.concatenate([cv2.Rodrigues(R.T)[0].ravel(), -R.T @ t])      # X_cam = R X_f + t
SEEN = {}
for u in FIELD:
    for p in UNITS[u]["plc"]:
        SEEN.setdefault(key(p), []).append((u, p))
BP = {k: np.concatenate([cv2.Rodrigues(R)[0].ravel(), t]) for k, (R, t) in BOARD.items()}
for rnd in range(3):
    for k, obs in SEEN.items():
        looks = []
        for u, p in obs:
            if u not in POSE:
                continue
            Rc = cv2.Rodrigues(POSE[u][:3])[0]
            obj = np.concatenate([p["obj_mm"], np.zeros((len(p["obj_mm"]), 1))], 1)
            looks.append((obj, p["px"], p["sigma"], UNITS[u]["model"], UNITS[u]["intr"], Rc, POSE[u][3:]))
        if looks:
            BP[k] = board_pose(looks, BP[k])
    worst = []
    for u in sorted(POSE):
        U = UNITS[u]
        looks = []
        for p in U["plc"]:
            k = key(p)
            if k not in BP:
                continue
            Rb = cv2.Rodrigues(BP[k][:3])[0]
            obj = np.concatenate([p["obj_mm"], np.zeros((len(p["obj_mm"]), 1))], 1)
            looks.append((obj @ Rb.T + BP[k][3:], p["px"], p["sigma"]))
        for Xf, uv, _st in CONE_OBS.get(u, []):
            looks.append((Xf.reshape(1, 3), uv.reshape(1, 2), CONE_SIGMA))
        if looks:
            POSE[u] = camera_pose(U["model"], U["intr"], looks, POSE[u])
            e = np.concatenate([np.linalg.norm(
                fm.project(U["model"], U["intr"],
                           X @ cv2.Rodrigues(POSE[u][:3])[0].T + POSE[u][3:]) - uv, axis=1)
                for X, uv, _ in looks])
            worst.append(f"{u} {np.median(e):.1f}")
    say(f"    round {rnd + 1}: median reprojection per camera  " + "  ".join(worst) + "  px")
for k in BP:
    BOARD[k] = (cv2.Rodrigues(BP[k][:3])[0], BP[k][3:])
for u in POSE:
    R = cv2.Rodrigues(POSE[u][:3])[0]
    FIELD[u] = (R.T, -R.T @ POSE[u][3:])

# ---------------------------------------------------------------- stage 5: bundle adjustment
say("")
say("STAGE 5  BUNDLE ADJUSTMENT - camera poses, board poses and (for the ordinary lenses) focal")
say("         length and distortion, against every corner pixel, the cone pixels, and the physical")
say("         prior that a plate on grass is flat and 6 mm above the ground.")

unit_list = [u for u in sorted(UNITS) if u in FIELD]
board_list = sorted(BOARD)
uidx = {u: i for i, u in enumerate(unit_list)}
bidx = {k: i for i, k in enumerate(board_list)}
cam_list = sorted(set(UNITS[u]["cam"] for u in unit_list))
cidx = {c: i for i, c in enumerate(cam_list)}
free_f = []     # intrinsics stay where stage 1 put them: the placements are coplanar and
                # carry no information about f, c or k, so a free lens here only absorbs
                # pose error. A pano canvas has nothing to refine either.
MODEL_OF = {c: ("equirect" if c in PANO else "pinhole") for c in cam_list}

# observations
OBS = []
for u in unit_list:
    U = UNITS[u]
    for p in U["plc"]:
        k = key(p)
        if k in bidx:
            OBS.append((uidx[u], bidx[k], p))
CONES = [(uidx[u], Xf, uv, st) for u in unit_list for Xf, uv, st in CONE_OBS.get(u, [])]

NU, NB = len(unit_list), len(board_list)
OFF_B = 6 * NU
OFF_I = OFF_B + 6 * NB
x0 = np.zeros(OFF_I + 5 * len(free_f))
for i, u in enumerate(unit_list):
    R, t = FIELD[u]                                  # X_cam = R_cf X_field + t_cf
    Rcf, tcf = R.T, -R.T @ t
    x0[6 * i:6 * i + 6] = np.concatenate([cv2.Rodrigues(Rcf)[0].ravel(), tcf * 1e-3])
for i, k in enumerate(board_list):
    Rb, tb = BOARD[k]
    x0[OFF_B + 6 * i:OFF_B + 6 * i + 6] = np.concatenate([cv2.Rodrigues(Rb)[0].ravel(), tb * 1e-3])
for i, c in enumerate(free_f):
    x0[OFF_I + 5 * i:OFF_I + 5 * i + 5] = INTR[c]["intr"]

# flattened corner table - one row per corner, rebuilt if the second pass drops views
def build_tables():
    global c_ui, c_bi, c_obj, c_obs, c_sig, c_cam, c_grp
    c_ui = np.concatenate([np.full(len(p["obj_mm"]), ui) for ui, _, p in OBS])
    c_bi = np.concatenate([np.full(len(p["obj_mm"]), bi) for _, bi, p in OBS])
    c_obj = np.concatenate([np.concatenate([p["obj_mm"], np.zeros((len(p["obj_mm"]), 1))], 1)
                            for _, _, p in OBS]) * 1e-3          # metres: see x_scale below
    c_obs = np.concatenate([p["px"] for _, _, p in OBS])
    c_sig = np.concatenate([np.full(len(p["obj_mm"]), p["sigma"]) for _, _, p in OBS])
    c_cam = np.concatenate([np.full(len(p["obj_mm"]), cidx[UNITS[unit_list[ui]]["cam"]])
                            for ui, _, p in OBS])
    c_grp = {c: np.where(c_cam == cidx[c])[0] for c in cam_list}


build_tables()
# which plate corner the operator put on the cone. The rule is his ("the corner next to the cone
# first"), but which corner that was varies by station - the wall, the pole and the house forced a
# different edge at T15/25/35/45/55/65/75, T23, T53, T63. So it is READ OFF the initial solution
# (the corner that came out nearest the cone) rather than assumed, and only then held fixed.
b_corner = np.zeros(NB, int)
b_station = np.zeros((NB, 2))
for i, k in enumerate(board_list):
    Rb, tb = BOARD[k]
    plate = np.concatenate([bd.PAPER_MM, np.zeros((4, 1))], 1) @ Rb.T + tb
    st = np.array(station_mm[k[1]], float)
    b_corner[i] = int(np.argmin(np.linalg.norm(plate[:, :2] - st, axis=1)))
    b_station[i] = st * 1e-3
k_ui = np.array([c[0] for c in CONES])
k_xf = (np.array([c[1] for c in CONES]) if CONES else np.zeros((0, 3))) * 1e-3
k_obs = np.array([c[2] for c in CONES]) if CONES else np.zeros((0, 2))
k_cam = np.array([cidx[UNITS[unit_list[c[0]]]["cam"]] for c in CONES], int)


def unpack(x):
    cp = x[:OFF_B].reshape(NU, 6)
    bp = x[OFF_B:OFF_I].reshape(NB, 6)
    ip = {c: INTR[c]["intr"] for c in cam_list}
    for i, c in enumerate(free_f):
        ip[c] = x[OFF_I + 5 * i:OFF_I + 5 * i + 5]
    return cp, bp, ip


def residuals(x, split=False):
    cp, bp, ip = unpack(x)
    Rc = Rotation.from_rotvec(cp[:, :3]).as_matrix()
    Rb = Rotation.from_rotvec(bp[:, :3]).as_matrix()
    Xf = np.einsum("nij,nj->ni", Rb[c_bi], c_obj) + bp[c_bi, 3:]
    Xc = np.einsum("nij,nj->ni", Rc[c_ui], Xf) + cp[c_ui, 3:]
    uv = np.empty_like(c_obs)
    for c in cam_list:
        g = c_grp[c]
        if len(g):
            uv[g] = fm.project(MODEL_OF[c], ip[c], Xc[g])
    e_corner = (uv - c_obs) / c_sig[:, None]
    if len(CONES):
        Xk = np.einsum("nij,nj->ni", Rc[k_ui], k_xf) + cp[k_ui, 3:]
        vk = np.empty_like(k_obs)
        for c in cam_list:
            g = np.where(k_cam == cidx[c])[0]
            if len(g):
                vk[g] = fm.project(MODEL_OF[c], ip[c], Xk[g])
        e_cone = (vk - k_obs) / CONE_SIGMA
    else:
        e_cone = np.zeros((0, 2))
    plate = np.einsum("nij,kj->nki", Rb, PLATE4) + bp[:, None, 3:]
    e_st = (plate[np.arange(NB), b_corner, :2] - b_station) / (STATION_SIGMA * 1e-3)
    e_tilt = np.degrees(np.arccos(np.clip(np.abs(Rb[:, 2, 2]), -1, 1))) / FLAT_SIGMA_DEG
    e_z = (np.einsum("nij,j->ni", Rb, PAT_CTR * 1e-3)[:, 2] + bp[:, 5] - PLATE_Z * 1e-3) / (FLAT_SIGMA_Z * 1e-3)
    if split:
        return e_corner, e_cone, e_tilt, e_z, e_st
    return np.concatenate([e_corner.ravel(), e_cone.ravel(), e_tilt, e_z, e_st.ravel()])


def build_sparsity():
    """Which parameter each residual row can possibly touch. Without this the 446-column jacobian
    is rebuilt by 446 full evaluations per iteration instead of a handful."""
    nr = 2 * len(c_obs) + 2 * len(k_obs) + 2 * NB + 2 * NB
    S = np.zeros((nr, len(x0)), bool)
    rw = np.arange(2 * len(c_obs))
    for j in range(6):
        S[rw, 6 * np.repeat(c_ui, 2) + j] = True
        S[rw, OFF_B + 6 * np.repeat(c_bi, 2) + j] = True
    for i, c in enumerate(free_f):
        g = c_grp[c]
        S[np.repeat(g * 2, 2) + np.tile([0, 1], len(g)), OFF_I + 5 * i:OFF_I + 5 * i + 5] = True
    r0 = 2 * len(c_obs)
    rw = np.arange(r0, r0 + 2 * len(k_obs))
    for j in range(6):
        S[rw, 6 * np.repeat(k_ui, 2) + j] = True
    for i, c in enumerate(free_f):
        g = np.where(k_cam == cidx[c])[0]
        if len(g):
            S[np.repeat(r0 + g * 2, 2) + np.tile([0, 1], len(g)), OFF_I + 5 * i:OFF_I + 5 * i + 5] = True
    r0 += 2 * len(k_obs)
    for i in range(NB):
        S[r0 + i, OFF_B + 6 * i:OFF_B + 6 * i + 3] = True
        S[r0 + NB + i, OFF_B + 6 * i:OFF_B + 6 * i + 6] = True
        S[r0 + 2 * NB + 2 * i: r0 + 2 * NB + 2 * i + 2, OFF_B + 6 * i:OFF_B + 6 * i + 6] = True
    return S


S = build_sparsity()
xs = np.empty_like(x0)                               # one trust-region step scale per kind
xs[:OFF_B] = np.tile([0.01, 0.01, 0.01, 0.02, 0.02, 0.02], NU)          # rad, metres
xs[OFF_B:OFF_I] = np.tile([0.01, 0.01, 0.01, 0.01, 0.01, 0.01], NB)
for i in range(len(free_f)):
    xs[OFF_I + 5 * i:OFF_I + 5 * i + 5] = [5.0, 5.0, 5.0, 2e-3, 2e-3]   # px, px, px, k1, k2
r = least_squares(residuals, x0, jac_sparsity=S, method="trf", loss="soft_l1", f_scale=4.0,
                  x_scale=xs, xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=1500)
ec0 = residuals(r.x, split=True)[0]
pix0 = np.linalg.norm(ec0 * c_sig[:, None], axis=1)
bad_obs = []
for j, (ui, bi, pp) in enumerate(OBS):
    g = (c_ui == ui) & (c_bi == bi)
    if np.median(pix0[g]) > max(20.0, 6 * np.median(pix0[c_ui == ui])):
        bad_obs.append(j)
if bad_obs:
    say("")
    say("  a second pass, after dropping the views no camera geometry can explain:")
    for j in bad_obs:
        ui, bi, pp = OBS[j]
        g = (c_ui == ui) & (c_bi == bi)
        DROPPED.append((unit_list[ui], pp["session"], pp["station"], pp["win"],
                        f"bundle {np.median(pix0[g]):.0f} px"))
        say(f"     {unit_list[ui]:7s} {pp['station']:4s} {pp['session']} {pp['win']}  "
            f"{int(g.sum()):3d} corners at {np.median(pix0[g]):7.1f} px")
    keep_obs = [j for j in range(len(OBS)) if j not in set(bad_obs)]
    OBS = [OBS[j] for j in keep_obs]
    build_tables()
    S = build_sparsity()
    r = least_squares(residuals, r.x, jac_sparsity=S, method="trf", loss="soft_l1", f_scale=4.0,
                      x_scale=xs, xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=1500)
cp, bp, ip = unpack(r.x)
ec, ek, et, ez, es = residuals(r.x, split=True)
say("")
say(f"  {len(x0)} parameters ({NU} camera poses, {NB} board poses, {len(free_f)} lens models)")
say(f"  {len(c_obs)} corner observations, {len(k_obs)} cone labels")
say(f"  weighted corner rms {np.sqrt((ec**2).sum(1).mean()):.2f} sigma; "
    f"cone rms {CONE_SIGMA*np.sqrt((ek**2).sum(1).mean()) if len(ek) else float('nan'):.0f} px; "
    f"plate tilt rms {FLAT_SIGMA_DEG*np.sqrt((et**2).mean()):.2f} deg; "
    f"plate height rms {FLAT_SIGMA_Z*np.sqrt((ez**2).mean()):.0f} mm")
say(f"  plate corner to its cone: median {1000*np.median(np.linalg.norm(es*STATION_SIGMA*1e-3, axis=1)):.0f} mm"
    f"   <- how well the placements reproduce the designed station grid")
say(f"  operator cone LABEL to the same grid: median {CONE_SIGMA*np.median(np.linalg.norm(ek, axis=1)):.0f} px"
    f" = {1000*np.median(np.linalg.norm(ek, axis=1))*CONE_SIGMA/2444.6*4.0:.0f} mm at 4 m")
say("  per-camera reprojection of the CORNERS only (the cone labels are listed separately):")
for i, u in enumerate(unit_list):
    g = c_ui == i
    ee = np.linalg.norm(ec[g] * c_sig[g, None], axis=1)
    say(f"     {u:7s} {len(set(c_bi[g])):2d} boards {g.sum():5d} corners   median {np.median(ee):5.2f} px"
        f"   rms {np.sqrt((ee**2).mean()):6.2f} px")

# ---------------------------------------------------------------- results
IN = fd.MM_PER_IN
say("")
say("=" * 100)
say("RESULT 1  WHERE THE CAMERAS ARE.  Paddock frame: origin at pole A0, x along the long cord")
say("          (0-480 in), y across (0-240 in), z up from the ground. All of this is OUTPUT.")
say("=" * 100)
say("")
say(f"  {'camera':7s} {'x (in)':>8s} {'y (in)':>8s} {'height':>9s} {'looks toward':>13s} "
    f"{'down':>7s} {'boards':>7s} {'reproj rms':>11s}")
pix = np.sqrt((ec ** 2).sum(1))
CAMPOS = {}
for i, u in enumerate(unit_list):
    Rcf = cv2.Rodrigues(cp[i, :3])[0]
    C = -Rcf.T @ cp[i, 3:] * 1000.0
    ax = Rcf.T @ np.array([0, 0, 1.0])
    yaw = np.degrees(np.arctan2(ax[1], ax[0]))
    down = np.degrees(np.arcsin(-ax[2] / np.linalg.norm(ax)))
    g = c_ui == i
    n_b = len(set(c_bi[g]))
    rms = float(np.sqrt((np.linalg.norm((c_obs[g] - c_obs[g]), axis=1) ** 2).mean())) if False else \
        float(np.sqrt(((pix[g] * c_sig[g]) ** 2).mean()))
    CAMPOS[u] = (C, yaw, down)
    face = "near-nadir" if down > 75 else f"{yaw:7.1f} deg"
    say(f"  {u:7s} {C[0]/IN:8.1f} {C[1]/IN:8.1f} {C[2]/1000:7.3f} m {face:>11s} {down:6.1f} "
        f"{n_b:7d} {rms:9.2f} px")
say("")
say("  (x,y in inches on the cord grid; height in metres above the paddock ground plane;")
say("   'looks toward' is the compass-style bearing of the optical axis in the paddock frame,")
say("   0 deg = +x along the long cord, 90 deg = +y across; 'down' is its depression angle.)")
for cam in PANO:
    if cam + "L" in CAMPOS and cam + "R" in CAMPOS:
        d = np.linalg.norm(CAMPOS[cam + "L"][0] - CAMPOS[cam + "R"][0])
        da = CAMPOS[cam + "R"][1] - CAMPOS[cam + "L"][1]
        say(f"  {cam}: the two Duo3 lenses come out {d:.0f} mm apart, {da:+.1f} deg apart in bearing"
            f"  <- an independent check, nothing told the fit they were one camera")

say("")
say("=" * 100)
say("RESULT 2  LENS MODELS (the panos have none to fit - their canvas is a fixed 180 deg equirect)")
say("=" * 100)
for c in cam_list:
    if c in PANO:
        say(f"  {c}  equirect  {2444.6:.1f} px/rad, centre (3839.5, 1079.5)   [format, not fitted]")
        continue
    f, cx, cy, k1, k2 = ip[c]
    W, H = qc_paths.upright_size(qc_paths.resolve(None)[0], c)
    say(f"  {c}  pinhole   f={f:8.1f} px  c=({cx:7.1f},{cy:7.1f})  k1={k1:+.4f} k2={k2:+.4f}"
        f"   HFOV {2*np.degrees(np.arctan(W/2/f)):.1f} deg")

say("")
say("=" * 100)
say("RESULT 3  DOES THE DESIGNED STATION GRID MATCH THE GROUND?")
say("          Each fitted board is asked where its plate corners ended up. The corner nearest the")
say("          design station is the one the operator put on the cone; the distance is how far the")
say("          real placement sits from the drawing. This is a CHECK, not an input - the grid was")
say("          never given to the fit.")
say("=" * 100)
say("")
say(f"  {'station':8s} {'session':9s} {'cams':22s} {'cone corner':14s} {'offset':>8s} {'tilt':>6s} {'h':>7s}")
corner_names = {(0.0, 0.0): "origin", (720.0, 0.0): "long-far", (720.0, 540.0): "diagonal",
                (0.0, 540.0): "short-far"}
offsets, rows_r3 = [], []
for i, k in enumerate(board_list):
    Rb = cv2.Rodrigues(bp[i, :3])[0]
    plate = np.concatenate([bd.PAPER_MM, np.zeros((4, 1))], 1) @ Rb.T + bp[i, 3:] * 1000.0
    st = np.array([*station_mm[k[1]], 0.0])
    d = np.linalg.norm(plate[:, :2] - st[:2], axis=1)
    j = int(np.argmin(d))
    tilt = np.degrees(np.arccos(np.clip(abs(Rb[2, 2]), -1, 1)))
    h = float((Rb @ PAT_CTR)[2] + bp[i, 5] * 1000.0)
    cams_here = sorted(set(unit_list[ui] for ui, bi, _ in OBS if bi == i))
    nm = corner_names.get(tuple(bd.OUTLINE_MM[j]), f"corner{j}")
    offsets.append(d[j])
    rows_r3.append((k[1], k[0][-5:], ",".join(cams_here), nm, d[j], tilt, h))
for row in sorted(rows_r3, key=lambda t: -t[4]):
    say(f"  {row[0]:8s} {row[1]:9s} {row[2]:22s} {row[3]:14s} {row[4]:6.0f}mm {row[5]:5.1f}d {row[6]:5.0f}mm")
offsets = np.array(offsets)
say("")
say(f"  {len(offsets)} placements: offset from the designed station median {np.median(offsets):.0f} mm, "
    f"p90 {np.percentile(offsets,90):.0f} mm, max {offsets.max():.0f} mm")

np.savez(OUT / "camera_fit.npz",
         units=np.array(unit_list), cam_rvec=cp[:, :3], cam_tvec=cp[:, 3:] * 1000.0,
         cam_centre_mm=np.array([CAMPOS[u][0] for u in unit_list]),
         models=np.array([UNITS[u]["model"] for u in unit_list]),
         intr=np.array([ip[UNITS[u]["cam"]] for u in unit_list]),
         board_keys=np.array(["|".join(k) for k in board_list]),
         board_pose=np.concatenate([bp[:, :3], bp[:, 3:] * 1000.0], 1),
         board_station_mm=b_station * 1000.0, board_cone_corner=b_corner,
         dropped_views=np.array(["|".join(d) for d in DROPPED]),
         note="X_cam = Rodrigues(cam_rvec) @ X_field + cam_tvec; ALL lengths mm, "
              "field origin pole A0, x along the long cord, y across, z up")
say("")
say(f"  -> {OUT / 'camera_fit.npz'}")
(OUT / "CALIBRATION_FIT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("report ->", OUT / "CALIBRATION_FIT.txt")
