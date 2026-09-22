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
        if st not in STATION_MM:
            continue
        frames = []
        for r in rs:
            f = qc / "corners" / cam / r["file"]
            if not f.exists():
                continue
            with np.load(f, allow_pickle=False) as z:
                ids = z["ids"].astype(int); px = z["px"].astype(float)
                meth = str(z["method"]) if "method" in z.files else r["method"]
            if len(ids) < min_corners:
                continue
            px = qc_paths.stored_to_upright(px, session, cam)
            frames.append(dict(ids=ids, px=px, method=meth, clock=r["clock"],
                               ctr=px.mean(0), n=len(ids)))
        if not frames:
            continue
        # ---- keep the largest cluster of frames that agree on the board position (latest wins ties)
        C = np.array([f["ctr"] for f in frames])
        best, bi = None, None
        for i in range(len(frames)):
            m = np.linalg.norm(C - C[i], axis=1) < CLUSTER_PX
            if best is None or m.sum() > best or (m.sum() == best and i > bi):
                best, bi = int(m.sum()), i
        keep = [f for f, m in zip(frames, np.linalg.norm(C - C[bi], axis=1) < CLUSTER_PX) if m]
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
            obs_mm = bd.OBJ_MM[ids]
            base = [base_method(m) for m in meths if base_method(m) not in WEAK]
            method = max(set(base), key=base.count)
            sigma = SIGMA.get(method, 1.5)
        man = any(m.startswith("manual-") for m in meths) or method == "operator-clicks"
        hr = 0.0 if weak else hom_rms(obs_mm, obs_px)
        sigma = max(sigma, min(hr, HOM_REJECT))     # a board only as good as its own planarity
        out.append(dict(session=date, cam=cam, station=st, win=win, method=method, manual=man,
                        hom_rms=float(hr), bad=bool(hr > HOM_REJECT),
                        n_frames=len(keep), n_frames_all=len(frames), ids=ids,
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
