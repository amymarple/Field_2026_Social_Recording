# -*- coding: utf-8 -*-
r"""Did a camera move between two calibration sessions? Image registration on what does not move.

Cones are no test: they get nudged (on 2026-09-30 the "unmoved" cones of 2026-09-18 had shifted 10-67 px in
every direction). Walls, poles, shelters and the fence do not. For each camera, one frame from each session is
matched with SIFT; a RANSAC homography keeps the static matches (grass, people and shadows change and drop
out). If the camera did not move, the inliers sit where they were: displacement ~0-1 px everywhere.
Reported per camera: inliers, their median / p90 displacement, and the displacement the homography implies at
the frame centre and corners (a camera that turned shows a smooth field, not noise).

Usage: python camera_drift.py --a <session dir> HH:MM:SS --b <session dir> HH:MM:SS [--cams CH01,...]
Output: printed, and <qc of b>\CAMERA_DRIFT.txt plus side-by-side match images in <qc of b>\frames\
"""
import sys, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                           # noqa: E402

args = sys.argv[1:]
A, TA = Path(args[args.index("--a") + 1]), args[args.index("--a") + 2]
B, TB = Path(args[args.index("--b") + 1]), args[args.index("--b") + 2]
CAMS = (args[args.index("--cams") + 1] if "--cams" in args else "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
_, QB = qc_paths.resolve(str(B))


def frame(session, cam, clock):
    date = session.name.split("_")[1]
    t = datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M:%S")
    for p in sorted(session.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t <= b:
            vf = "transpose=2" if cam in ("CH01", "CH02") else "null"
            r = subprocess.run([qc_paths.FFMPEG, "-v", "error", "-ss", f"{(t - a).total_seconds():.2f}", "-i", str(p),
                                "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"], stdout=subprocess.PIPE)
            return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    raise SystemExit(f"no closed {cam} segment covers {clock} in {session}")


sift = cv2.SIFT_create(nfeatures=20000)
L = [f"CAMERA DRIFT  {A.name} {TA}  ->  {B.name} {TB}  (SIFT + RANSAC homography on static structure)", "",
     "camera  matches  inliers  inlier displacement median / p90 (px)   homography at centre / worst corner (px)"]
(QB / "frames").mkdir(parents=True, exist_ok=True)
for cam in CAMS:
    ia, ib = frame(A, cam, TA), frame(B, cam, TB)
    ga, gb = (cv2.cvtColor(i, cv2.COLOR_BGR2GRAY) for i in (ia, ib))
    ka, da = sift.detectAndCompute(ga, None)
    kb, db = sift.detectAndCompute(gb, None)
    m = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [p[0] for p in m if len(p) == 2 and p[0].distance < 0.7 * p[1].distance]
    pa = np.float32([ka[g.queryIdx].pt for g in good]); pb = np.float32([kb[g.trainIdx].pt for g in good])
    H, inl = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
    inl = inl.ravel().astype(bool)
    d = np.linalg.norm(pb[inl] - pa[inl], axis=1)
    h, w = ga.shape
    probe = np.float32([[w / 2, h / 2], [0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]]).reshape(-1, 1, 2)
    moved = np.linalg.norm(cv2.perspectiveTransform(probe, H).reshape(-1, 2) - probe.reshape(-1, 2), axis=1)
    L.append(f"  {cam}   {len(good):6d}   {inl.sum():6d}        {np.median(d):5.2f} / {np.percentile(d, 90):5.2f}"
             f"                       {moved[0]:6.2f} / {moved[1:].max():6.2f}")
    vis = cv2.drawMatches(ia, ka, ib, kb, [g for g, k in zip(good, inl) if k][::max(1, int(inl.sum() // 300))], None,
                          matchColor=(0, 255, 0), flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    s = 3000 / vis.shape[1]
    cv2.imwrite(str(QB / "frames" / f"drift_{cam}.jpg"), cv2.resize(vis, None, fx=s, fy=s), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(L[-1], flush=True)
(QB / "CAMERA_DRIFT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("->", QB / "CAMERA_DRIFT.txt")
