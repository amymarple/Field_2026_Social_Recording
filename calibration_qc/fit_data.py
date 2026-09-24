# -*- coding: utf-8 -*-
r"""Assemble the cached corner detections into one observation per PLACEMENT, ready for the fit.

A placement = (session, camera, station, operator window). The board and the camera are both static
inside a window, so its N keyframes are N noisy looks at the SAME pose: they are collapsed into one
observation by taking the per-corner median over the frames that agree on where the board is (a
window can contain two distinct poses when the operator re-placed the plate, so the frames are first
clustered on their corner centroid and only the largest, latest cluster is kept).

Coordinates are UPRIGHT pixels for every camera (identity except for the two Duo3 panos, which are
stored rotated). Corner ids index board_detect.OBJ_MM (88 inner corners, millimetres on the printed
plane).

'outline' / 'manual-outline' placements carry no measured corners at all - their 88 points were
PREDICTED from the operator's four clicks through a homography, so they are exactly homography
consistent and would (a) count 88 times their true weight and (b) pull the distortion toward zero.
They are kept as what they really are: the four clicked PLATE corners, tagged weak.
"""
from pathlib import Path
import csv, json, sys, os
from datetime import datetime
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, board_detect as bd                                        # noqa: E402

REPO = Path(__file__).resolve().parent
MM_PER_IN = 25.4
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
LATTICE = {f"T{li}{si}": (x, y) for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)}
LATTICE.update({f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}": (x, y)
                for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)})
STATION_MM = {k: (v[0] * MM_PER_IN, v[1] * MM_PER_IN) for k, v in LATTICE.items()}

# measurement sigma in pixels, by how the corner was obtained
SIGMA = {"charuco": 0.7, "rect-charuco": 0.9, "chessboard": 0.8, "rect-chess": 1.0,
         "rect-markers": 1.6, "outline": 4.0}
WEAK = ("outline",)                     # not corner measurements: four operator clicks
CLUSTER_PX = float(os.environ.get("FIT_CLUSTER_PX", "4.0"))   # frames of one placement agree to this
HOM_REJECT = 4.0                        # px; see hom_rms()

# Burnt-in OSD text (timestamp top-centre, model name bottom-right) sits ON the footage: a corner
# detector run over it returns corners of the letters. Corners inside these boxes (UPRIGHT px,
# fractions of the frame so they hold for any resolution) are dropped before anything else.
# Measured on 2026-09-18/19 frames: Duo 3 pano 7680x2160, RLC-1212A 4512x2512 and 2560x1920.
OSD_BOXES = {
    "pano": [(0.41, 0.0, 0.60, 0.065), (0.855, 0.93, 1.0, 1.0)],
    "rlc":  [(0.34, 0.0, 0.66, 0.05), (0.73, 0.94, 1.0, 1.0)],
}


def in_osd(px, upright, cam):
    W, H = upright
    boxes = OSD_BOXES["pano" if cam in ("CH01", "CH02") else "rlc"]
    m = np.zeros(len(px), bool)
    for x0, y0, x1, y1 in boxes:
        m |= (px[:, 0] >= x0 * W) & (px[:, 0] <= x1 * W) & (px[:, 1] >= y0 * H) & (px[:, 1] <= y1 * H)
    return m

# Windows whose station label the footage itself contradicts (frames rendered and looked at, not
# inferred from a residual). The fit must not anchor these to that station; they are left out
# until the operator confirms or relabels them. (session, station, window_start) -> what was seen.
EXCLUDE = {
    ("2026-09-19", "T61", "12:41:05"):
        "not a placement - operator 2026-09-23: 'nothing there, I just set the plate down'. The frames "
        "agree (plate beside house 7, no cone at its corner; CH06 cannot see the T61 cone). The "
        "timeline row now carries the label NONE, so this entry only guards an old labelled_frames table",
}


def hom_rms(obj_mm, px):
    """How well the corners of ONE placement fit a plane-to-plane homography, in pixels.

    This is a model-free quality gate. A flat board seen by any camera must be a homography of its
    design grid to within the lens distortion across the board (a fraction of a pixel to ~2 px at
    the frame edge). A placement that cannot be fitted by ANY homography does not have noisy
    corners - it has WRONG corners: the marker/parity path resolved the board orientation one
    square off, so whole rows carry the wrong id. Those must not enter the fit at any weight, and
    the ones in between are down-weighted by what they actually achieve."""
    obj = np.asarray(obj_mm, float)
    px = np.asarray(px, float)
    if len(obj) < 5:
        return 0.0
    H, _ = cv2.findHomography(obj.reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
    if H is None:
        return float("inf")
    q = cv2.perspectiveTransform(obj.reshape(-1, 1, 2), H).reshape(-1, 2)
    return float(np.sqrt((np.linalg.norm(q - px, axis=1) ** 2).mean()))


def base_method(m):
    return m[7:] if m.startswith("manual-") else m


def obj_of(ids):
    """board coordinates (mm) of corner ids: 0-87 chessboard corners, 1000 + 4*marker + k marker corners."""
    ids = np.asarray(ids, int)
    out = np.zeros((len(ids), 2))
    ch = ids < 1000
    out[ch] = bd.OBJ_MM[ids[ch]]
    for j in np.where(~ch)[0]:
        m, k = divmod(int(ids[j]) - 1000, 4)
        out[j] = bd.MARKER_MM[m][k]
    return out


# FIT_EXCLUDE="2026-09-18|T11|15:01:03;..." holds placements out of a fit (cross-validation folds)
for _item in os.environ.get("FIT_EXCLUDE", "").split(";"):
    if _item.strip():
        _d, _s, _w = _item.strip().split("|")
        EXCLUDE[(_d, _s, _w)] = "held out by FIT_EXCLUDE (validation fold)"


def load_session(sess_arg):
    session, qc = qc_paths.resolve(sess_arg)
    date = qc_paths.session_date(session)
    csv_path = REPO / f"session_{date}_labelled_frames.csv"
    rows = [r for r in csv.DictReader(open(csv_path, newline="", encoding="utf-8"))
            if int(r["n_corners"]) >= 12]
    quads = {}
    qf = REPO / f"session_{date}_manual_quads.json"
    if qf.exists():
        for j in json.loads(qf.read_text(encoding="utf-8")):
            if j.get("quad") and not j.get("skip") and j.get("verdict") not in ("reject", "partial", "accept"):
                p = np.asarray(j["quad"], float) / float(j.get("scale", 1.0)) + np.asarray(j["off"], float)
                quads[(j["cam"], j["station"], j["win"][0])] = p       # already UPRIGHT display px
    cone = {}
    cf = REPO / f"session_{date}_manual_cone_corner.json"
    if cf.exists():
        for cam, d in json.loads(cf.read_text(encoding="utf-8")).items():
            for k, v in d.items():
                st, win = k.split("@")
                cone[(cam, st, win)] = tuple(v["corner_mm"])
    return session, qc, date, rows, quads, cone


def placements(sess_arg, min_corners=12):
    """-> list of dicts, one per placement."""
    session, qc, date, rows, quads, cone = load_session(sess_arg)
    groups = {}
    for r in rows:
        groups.setdefault((r["cam"], r["station"], r["window_start"]), []).append(r)
    out = []
    for (cam, st, win), rs in sorted(groups.items()):
        if st not in STATION_MM or (date, st, win) in EXCLUDE:
            continue
        frames = []
        for r in rs:
            f = qc / "corners" / cam / r["file"]
            if not f.exists():
                continue
            with np.load(f, allow_pickle=False) as z:
                ids = z["ids"].astype(int); px = z["px"].astype(float)
                meth = str(z["method"]) if "method" in z.files else r["method"]
                if base_method(meth) == "rect-markers":
                    # this path never measured chessboard corners: its 88 'corners' are the design
                    # grid pushed through a homography fitted to the MARKER corners. The markers are
                    # the measurement (audit 2026-09-24, finding 3): use them, id 1000 + 4*marker + k.
                    if "mk_ids" not in z.files or len(z["mk_ids"]) == 0:
                        continue
                    mk = z["mk_ids"].astype(int).reshape(-1); mpx = z["mk_px"].astype(float).reshape(-1, 4, 2)
                    keep_m = np.array([m in bd.MARKER_MM for m in mk], bool)
                    mk, mpx = mk[keep_m], mpx[keep_m]
                    ids = (1000 + 4 * np.repeat(mk, 4) + np.tile(np.arange(4), len(mk))).astype(int)
                    px = mpx.reshape(-1, 2)
            if len(ids) < min_corners:
                continue
            px = qc_paths.stored_to_upright(px, session, cam)
            osd = in_osd(px, qc_paths.upright_size(session, cam), cam)
            if osd.any():
                ids, px = ids[~osd], px[~osd]
                if len(ids) < min_corners:
                    continue
            frames.append(dict(ids=ids, px=px, method=meth, clock=r["clock"],
                               ctr=px.mean(0), n=len(ids)))
        if not frames:
            continue
        # ---- keep the largest cluster of frames that agree on the board position (latest wins ties).
        # Agreement is measured on the corners two frames SHARE (median displacement of the same
        # ids), never on the centroid of whatever each frame happened to decode: a partly occluded
        # board decodes a different subset every frame and its centroid wanders by tens of pixels
        # while the plate has not moved a millimetre. (The centroid version kept 1-4 frames of 20-60
        # for a dozen placements, and at T61/T65 it kept the one frame where the board was still in
        # the operator's hands.)
        n = len(frames)
        agree = np.eye(n, dtype=bool)
        for i in range(n):
            di = dict(zip(frames[i]["ids"].tolist(), frames[i]["px"]))
            for j in range(i + 1, n):
                shared = [k for k in frames[j]["ids"].tolist() if k in di]
                if len(shared) < 6:
                    continue
                dj = dict(zip(frames[j]["ids"].tolist(), frames[j]["px"]))
                d = np.median(np.linalg.norm(np.array([di[k] - dj[k] for k in shared]), axis=1))
                agree[i, j] = agree[j, i] = d < CLUSTER_PX
        best, bi = None, None
        for i in range(n):
            m = int(agree[i].sum())
            if best is None or m > best or (m == best and i > bi):
                best, bi = m, i
        keep = [f for f, m in zip(frames, agree[bi]) if m]
        moving = n >= 3 and best == 1          # no two frames agree: the plate was in motion
        meths = [f["method"] for f in keep]
        weak = all(base_method(m) in WEAK for m in meths)
        if weak:
            q = quads.get((cam, st, win))
            if q is None:
                continue
            obs_mm = bd.PAPER_MM.copy()                 # the operator clicked the PLATE edge
            obs_px = np.asarray(q, float)
            sigma = SIGMA["outline"]
            method = "operator-clicks"
            ids = np.array([-1, -2, -3, -4])
        else:
            acc = {}
            for f in keep:
                if base_method(f["method"]) in WEAK:
                    continue
                for i, p in zip(f["ids"], f["px"]):
                    acc.setdefault(int(i), []).append(p)
            ids = np.array(sorted(acc))
            if len(ids) < min_corners:
                continue
            obs_px = np.array([np.median(np.array(acc[i]), 0) for i in ids])
            obs_mm = obj_of(ids)
            base = [base_method(m) for m in meths if base_method(m) not in WEAK]
            method = max(sorted(set(base)), key=base.count)      # deterministic tie-break
            sigma = SIGMA.get(method, 1.5)
        man = any(m.startswith("manual-") for m in meths) or method == "operator-clicks"
        hr = 0.0 if weak else hom_rms(obs_mm, obs_px)
        sigma = max(sigma, min(hr, HOM_REJECT))     # a board only as good as its own planarity
        # a plate cut by the frame edge (or mostly hidden) is a partial measurement: its pose from
        # a few corners in the most distorted part of the lens is the weakest thing in the fit
        # (CH04/T65, CH03/F12, CH06/T64 were 60-140 px off the other cameras). Half weight.
        uw, uh = qc_paths.upright_size(session, cam)
        edge = 0.02
        partial = (not weak) and (len(ids) < 30 or bool(((obs_px[:, 0] < edge * uw) | (obs_px[:, 0] > (1 - edge) * uw) |
                                                          (obs_px[:, 1] < edge * uh) | (obs_px[:, 1] > (1 - edge) * uh)).any()))
        if partial:
            sigma *= 2.0
        out.append(dict(session=date, cam=cam, station=st, win=win, method=method, manual=man,
                        hom_rms=float(hr), bad=bool(hr > HOM_REJECT) or moving, moving=moving, partial=partial,
                        n_frames=len(keep), n_frames_all=len(frames), ids=ids,
                        clocks=[f["clock"] for f in keep], clocks_all=[f["clock"] for f in frames],
                        obj_mm=np.asarray(obs_mm, float), px=np.asarray(obs_px, float),
                        sigma=float(sigma), weak=bool(weak),
                        cone_corner=cone.get((cam, st, win)),
                        station_mm=np.array(STATION_MM[st], float),
                        upright=qc_paths.upright_size(session, cam)))
    return out


def all_placements(sessions=("2026-09-18", "2026-09-19"), min_corners=12):
    out = []
    for s in sessions:
        out += placements(None if s == "2026-09-18" else s, min_corners)
    return out


if __name__ == "__main__":
    P = all_placements()
    import collections
    print(f"{len(P)} placements")
    per = collections.Counter(p["cam"] for p in P)
    for c in sorted(per):
        ps = [p for p in P if p["cam"] == c]
        print(f"  {c}: {len(ps):3d} placements, {len(set(p['station'] for p in ps)):2d} stations, "
              f"{sum(len(p['ids']) for p in ps):5d} corners, "
              f"methods {dict(collections.Counter(p['method'] for p in ps))}")
    print("  weak (operator clicks only):", sum(1 for p in P if p["weak"]))
