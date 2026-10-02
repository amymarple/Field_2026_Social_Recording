# -*- coding: utf-8 -*-
r"""2026-09-30 pixels -> 2026-09-18 COLOUR pixels per camera, with the analysis repository's landmark_track.

Replaces landmark_drift.py's edge-template similarity for the 09-30 supplement (2026-10-02). landmark_drift aligned
the edges of a colour template to the target's edges; on CH03/CH04's corrugated walls an edge template can lock
one corrugation period off (it gave CH04 0 and 18 px on frames minutes apart, and its two 09-30 frames disagreed by
14 px / 0.5 deg). landmark_track (cv/cv_field/landmark_track.py in Field2026_Social_analysis) matches patches along
the operator's labels by NCC within a small window of a coarse prediction, uses only the normal component on lines,
fits an affine by IRLS and reports a leave-one-landmark-out error.

Chain, per camera (homogeneous 3x3; landmark_track returns the forward map reference -> target):
  F_t : 09-18 IR reference px (the labelled frame) -> 09-30 px at time t   (tracked at several times)
  G   : 09-18 IR reference px -> 09-18 colour px                           (same day, camera static; the mean of
                                                                            the "ok" colour frames)
  M_t = G o F_t^-1 : 09-30 px -> 09-18 colour px (the pixel space of the boards, cones and the release fit).
The per-time M_t are reported and the median of the "ok" ones near the ball sweep and the cone-label frame is
written. CH05/CH06: identity (unmoved, camera_drift.py).
Cohort reference (as landmark_track --ref-labels --tie): CH04's labelled 09-18 frame has people in view and does
not track 09-30; for a camera in COHORT_REF the 09-30 frames are tracked from the operator's 09-04 12:00 colour
reference instead and composed with the label-to-label tie 09-18 -> 09-04: F_t = A_track(t) o A_tie. CH03 is
computed both ways as a cross-check. Neither reference tracks CH04's 09-30 frames from the default start
(2-4 landmarks lock), and its edges are periodic (corrugated wall), so for CH04 the 09-30 frame is pre-shifted by a
grid of guesses (+-100 px, 25 px steps), landmark_track runs from each, and the "ok" fit with the lowest held-out
error is kept (`grid` below; checked by eye on 16:35:10: the labels land on the wall top, the pole edges and the
nails, and the rival +52 px solution does not). Result: CH04 did not move between 09-18 and 09-30 beyond a few px;
landmark_drift's (-46, -26) px for CH04, and its CH03 transform (~25 px off, same corrugation lock), were wrong.

Usage: python landmark_track_drift.py [--out <json>] [--times 16:35:10,16:34:40,...]
Output: <root>\qc\2026-09-30\landmark_track_drift.json (cameras: {cam: {affine_30_to_18: 2x3, ...}}) and the report
beside it; refit_supplement.py / ball_check.py read it with --drift.
"""
import sys, json, subprocess
from datetime import date, datetime
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths                                                          # noqa: E402
LTDIR = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\cv_field")
sys.path.insert(0, str(LTDIR))
import landmark_track as lt                                               # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
S18 = Path(opt("--a", str(qc_paths.CALIB_ROOT / "session_2026-09-18_13-54-34") if hasattr(qc_paths, "CALIB_ROOT")
               else r"G:\calibration\session_2026-09-18_13-54-34"))
S30 = Path(opt("--b", r"F:\calibration\session_2026-09-30_15-49-39"))
LM = Path(opt("--landmarks", r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c"))
TIMES = opt("--times", "16:35:10,16:34:40,16:31:30,16:27:00,16:23:00,16:15:00,15:55:00").split(",")
OUT = Path(opt("--out", str(qc_paths.QC_ROOT / "2026-09-30" / "landmark_track_drift.json")))
RUNS = Path("D:/Field2026_analysis_out/2026c")
COHORT_REF = {"CH04": ("landmarks_CH04_20260904_120002.json", "cv_field_landmark_track_ch04_ref0904day_*", "CH04_REF_2026-09-04_120002.jpg"),
              "CH03": ("landmarks_CH03_20260904_120000.json", "cv_field_landmark_track_ch03_ref0904day_*", "CH03_REF_2026-09-04_120000.jpg")}
COLOUR18 = {"CH01": ["14:10:00", "15:20:00"], "CH02": ["15:35:00", "15:47:00"], "CH03": ["15:05:00", "15:20:00", "15:30:00"],
            "CH04": ["14:41:00", "15:05:00", "15:47:00"]}                  # 09-18 colour frames, camera static (ir_colour_shift.py)


def frame(session, cam, clock):
    d = session.name.split("_")[1]
    t = datetime.strptime(f"{d} {clock}", "%Y-%m-%d %H:%M:%S")
    for p in sorted(session.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t < b:
            r = subprocess.run([qc_paths.FFMPEG, "-v", "error", "-ss", f"{(t - a).total_seconds():.2f}", "-i", str(p), "-frames:v", "1",
                                "-vf", "transpose=2" if cam in ("CH01", "CH02") else "null", "-f", "image2pipe", "-vcodec", "png", "-"],
                               stdout=subprocess.PIPE)
            return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    raise SystemExit(f"no closed {cam} segment covers {clock} in {session}")


def H(A):
    return np.vstack([np.asarray(A, float), [0, 0, 1]])


def summary(M, c):
    sh = M[:2, :2] @ c + M[:2, 2] - c
    return sh, np.degrees(np.arctan2(M[1, 0], M[0, 0]))


L, out = [f"09-30 px -> 09-18 colour px via landmark_track  ({S30.name} -> {S18.name}; labels {LM})", ""], {}
GRID = {"CH04"}
for cam, via in (("CH01", None), ("CH02", None), ("CH03", None), ("CH03", "0904"), ("CH04", None)):
    lab = json.loads(next(LM.glob(f"landmarks_{cam}_20260918_*.json")).read_text(encoding="utf-8"))
    ref_t = lab["time"].split()[1]
    ref = frame(S18, cam, ref_t); ref_g = lt.prep(ref); h, w = ref.shape[:2]; c = np.array([w / 2, h / 2])
    kinds = lab.get("kind", {})
    def track(img, day):
        r = lt.track_frame(ref_g, lt.prep(img), lab["landmarks"], kinds, day, ref_day=date(2026, 9, 18))
        return r
    if via:                                                             # cohort reference + tie
        lf, run, rimg = COHORT_REF[cam]
        lab04 = json.loads((LM / lf).read_text(encoding="utf-8"))
        tie = lt.tie_labels(lab["landmarks"], lab04["landmarks"], date(2026, 9, 18), date(2026, 9, 4))
        ref04 = cv2.imread(str(sorted(RUNS.glob(run))[-1] / "frames" / rimg)); ref04_g = lt.prep(ref04)
        kinds04 = {**kinds, **lab04.get("kind", {})}
        Atie = H(tie["A"])
        def track(img, day, _r=ref04_g, _l=lab04, _k=kinds04, _t=Atie):
            r = dict(lt.track_frame(_r, lt.prep(img), _l["landmarks"], _k, day, ref_day=date(2026, 9, 4)))
            if r.get("A") is not None:
                r["A"] = (H(r["A"]) @ _t)[:2].tolist()                  # 09-18 IR ref px -> 09-30 px
            return r
        L.append(f"{cam} via the 09-04 12:00 reference: tie 09-18 -> 09-04 held-out {tie['held_med']:.2f}/{tie['held_p90']:.2f} px, {tie['status']}")
    Gs = []
    for t in COLOUR18[cam]:
        r = lt.track_frame(ref_g, lt.prep(frame(S18, cam, t)), lab["landmarks"], kinds, date(2026, 9, 18), ref_day=date(2026, 9, 18))
        if r.get("A") is not None and r["status"] == "ok":
            Gs.append(H(r["A"]))
    G = np.mean(Gs, 0)
    sh, rot = summary(G, c)
    L.append(f"{cam}: reference {ref_t} (IR); IR -> colour on 09-18 from {len(Gs)} ok frames: ({sh[0]:+.2f}, {sh[1]:+.2f}) px, rot {rot:+.3f} deg")
    if cam in GRID:                                                     # pre-shift grid, best ok fit
        def track(img, day, _track=track):
            best = None
            for sx in range(-100, 101, 25):
                for sy in range(-100, 101, 25):
                    pre = cv2.warpAffine(img, np.float32([[1, 0, -sx], [0, 1, -sy]]), (w, h), borderMode=cv2.BORDER_REPLICATE)
                    r = _track(pre, day)
                    if r.get("A") is None or r["status"] != "ok":
                        continue
                    if best is None or r["held_med"] < best["held_med"]:
                        A = H(r["A"]); A[0, 2] += sx; A[1, 2] += sy
                        best = dict(r, A=A[:2].tolist())
            return best or {"A": None, "status": "no ok fit"}
    Ms = []
    for t in (TIMES if cam != "CH01" else TIMES + [f"16:{m:02d}:00" for m in range(20, 36)]):
        r = track(frame(S30, cam, t), date(2026, 9, 30))
        if r.get("A") is None:
            L.append(f"   09-30 {t}: no fit"); continue
        M = G @ np.linalg.inv(H(r["A"]))
        sh, rot = summary(M, c)
        L.append(f"   09-30 {t}: 09-30 -> 09-18 colour ({sh[0]:+7.2f},{sh[1]:+7.2f}) px, rot {rot:+.3f} deg, held-out "
                 f"{r['held_med']:.2f}/{r['held_p90']:.2f} px over {r['n_held']} units, {r['status']}")
        if r["status"] == "ok":
            Ms.append(M)
    if not Ms:
        L.append("   no reliable frame: not written"); continue
    Mm = np.median(np.stack(Ms), 0)
    spread = max(np.abs(summary(M, c)[0] - summary(Mm, c)[0]).max() for M in Ms)
    sh, rot = summary(Mm, c)
    L.append(f"   -> written: median of {len(Ms)} ok frames ({sh[0]:+.2f}, {sh[1]:+.2f}) px, rot {rot:+.3f} deg; "
             f"largest deviation of a frame from it {spread:.2f} px")
    if via == "0904" and cam == "CH03":
        L.append("   (cross-check only, not written)"); continue
    out[cam] = dict(affine_30_to_18=Mm[:2].tolist(), via=via or "0918", centre_px=c.tolist(), n_frames=len(Ms), times=TIMES,
                    max_frame_deviation_px=float(spread), ir_to_colour_0918_shift_px=summary(G, c)[0].tolist(),
                    note="09-18 colour px = affine_30_to_18 @ [u30, v30, 1] (upright px)")
OUT.write_text(json.dumps(dict(a=S18.name, b=S30.name, method="landmark_track (Field2026_Social_analysis) + 09-18 IR->colour",
                               cameras=out), indent=1), encoding="utf-8")
OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print("->", OUT)
