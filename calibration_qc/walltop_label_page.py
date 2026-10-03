# -*- coding: utf-8 -*-
r"""Wall-top labelling page on the rig cameras' own frames from a recent session (2026-10-03). The wall-top labels the
ray refit uses (analysis repo, 2026c landmarks) are from 09-18; the drone measured the wall tops on 10-02 and the
west wall has been sagging. 10-02 camera footage is on the field PC only, so the closest session here is the 09-30
calibration session (two days before the drone), whose pixels already have a validated transform to the 09-18 frame
(session_2026-09-30_drift_final.json). Clean upright frames (no overlays, the panos rotated upright) at a few times
per camera go into the landmark page (drone_landmark_gui.build), where the operator draws the wall tops as clicked
lines. No model prediction is drawn: the labels must stay independent of the drone heights they are compared with.

Usage: python walltop_label_page.py [--session 2026-09-30] [--cams CH01,CH02,CH03,CH04] [--times 15:55:00,16:15:00,16:35:10]
Output: <qc>\walltop_gui\drone_landmarks.html (+ frames\)
"""
import sys, subprocess
from datetime import datetime
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import drone_landmark_gui as gui                                         # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess or "2026-09-30"); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
CAMS = opt("--cams", "CH01,CH02,CH03,CH04").split(",")
TIMES = opt("--times", "15:55:00,16:15:00,16:35:10").split(",")
OUT = QC / "walltop_gui"; (OUT / "frames").mkdir(parents=True, exist_ok=True)
FFPROBE = Path(qc_paths.FFMPEG).with_name("ffprobe" + Path(qc_paths.FFMPEG).suffix)
frames = []
for cam in CAMS:
    pano = qc_paths.is_rotated(SESSION, cam)
    for clock in TIMES:
        t = datetime.strptime(f"{DATE} {clock}", "%Y-%m-%d %H:%M:%S"); seg = None
        for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
            a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
            b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
            if a <= t <= b:
                seg, start = p, a
        if seg is None:
            print(f"{cam} {clock}: no closed segment"); continue
        w, h = [int(v) for v in subprocess.check_output([str(FFPROBE), "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                         "stream=width,height", "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
        raw = subprocess.run([qc_paths.FFMPEG, "-v", "error", "-ss", f"{(t - start).total_seconds():.2f}", "-i", str(seg), "-frames:v", "1",
                              "-vf", "transpose=2" if pano else "null", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             stdout=subprocess.PIPE, check=True).stdout
        W, H = (h, w) if pano else (w, h)
        img = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        name = f"{cam}_{clock.replace(':', '')}"
        cv2.imwrite(str(OUT / "frames" / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        frames.append(dict(model=cam, name=name, file=f"frames/{name}.jpg"))
task = (f"Wall tops in the rig cameras, {DATE}. Pick 'wall top X0 / X480 / Y0 / Y240' (Ground lines section) and click "
        "along the UPPER edge of the wall sheet, 6-15 points per wall you can see, denser where it bends or dips; skip "
        "stretches hidden by a person, a house or a pole. X0 = west wall (CH03 end), X480 = east wall (CH04 end), Y0 = "
        "row-A side, Y240 = row-C side. One good frame per camera is enough; use another time only where a person blocks the wall.")
gui.build(OUT, frames, f"walltop_{DATE}", page_id="", task=task, title="Camera Wall Tops")
print(f"{len(frames)} frames ->", OUT / "drone_landmarks.html")
