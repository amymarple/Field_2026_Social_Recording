# -*- coding: utf-8 -*-
r"""Review video of one camera's 20 Hz ball track (ball_track20.py): what the machine marked, frame by frame.

Layout (1280 x 720, 20 fps, real time): top = the whole frame scaled down (the panos' 7680 x 2160 exactly 1/6),
the machine's ball as a green circle; bottom left = 640 x 360 native-resolution crop around the ball; bottom right =
the same spot zoomed 2x. Green ellipse = machine mark; magenta dashed = the operator's mark on the 2-s grid frame
nearest in time (shown only within 30 ms of a grid frame); red "NOT FOUND" = the frame was searched (the operator's
marks put the ball near) but nothing passed the gates. Frames that were not searched (operator: out of view) are
left out, so the video only covers the time the ball was expected in this camera.

Usage: python ball_track20_video.py CH01 --labels <ball_labels.json> [--ball <qc ball dir>]
Output: <ball dir>\track20\<CAM>_track20_review.mp4
"""
import sys, json, subprocess
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                           # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
CAM = args[0]
BALL = Path(opt("--ball", str(qc_paths.QC_ROOT / "2026-09-30" / "ball")))
SESSION = Path(opt("--session", r"F:\calibration\session_2026-09-30_15-49-39"))
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
job = next(c for c in jobs["cams"] if c["cam"] == CAM)
T = json.loads((BALL / "track20" / f"ball20_{CAM}.json").read_text(encoding="utf-8"))
FR = T["frames"]
OFF = float(job["offset_s"]) + float(T["grid_off_s"])
NT, STEP = len(jobs["clocks"]), float(jobs["step"])
OP = {}
for L in json.loads(Path(opt("--labels")).read_text(encoding="utf-8"))["labels"]:
    if L["cam"] == CAM and L["verdict"] == "ball" and L.get("centre") and not str(L.get("method", "")).startswith("machine"):
        e = L.get("ellipse")
        OP[L["k"]] = (e["cx"], e["cy"], e["a"], e["b"], e["theta_rad"]) if e else (L["centre"][0], L["centre"][1], L["r"] or 30, L["r"] or 30, 0.0)
W, H, pano = job["w"], job["h"], job["pano"]
S = 1280 / W                                                             # overview scale
OH = int(round(H * S / 2)) * 2                                          # even, for yuv420p
OUT = BALL / "track20" / f"{CAM}_track20_review.mp4"


def ell(img, e, scale, ox, oy, col, thick=2, dashed=False):
    cx, cy, a, b, th = e
    c = (int(round((cx - ox) * scale)), int(round((cy - oy) * scale)))
    ax = (max(1, int(round(a * scale))), max(1, int(round(b * scale))))
    if dashed:
        for s0 in range(0, 360, 20):
            cv2.ellipse(img, c, ax, np.degrees(th), s0, s0 + 10, col, thick, cv2.LINE_AA)
    else:
        cv2.ellipse(img, c, ax, np.degrees(th), 0, 360, col, thick, cv2.LINE_AA)
    cv2.drawMarker(img, c, col, cv2.MARKER_CROSS, 12, 1, cv2.LINE_AA)


def crop(img, cx, cy, w, h):
    x0 = int(np.clip(cx - w / 2, 0, W - w)); y0 = int(np.clip(cy - h / 2, 0, H - h))
    return img[y0:y0 + h, x0:x0 + w].copy(), x0, y0


ff = subprocess.Popen([str(qc_paths.FFMPEG), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"1280x{OH + 360}",
                       "-r", "20", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(OUT)],
                      stdin=subprocess.PIPE)
cap = cv2.VideoCapture(str(SESSION / job["file"]))
cap.set(cv2.CAP_PROP_POS_MSEC, (OFF - 1.5) * 1000)
i, last, written, mism = 0, None, 0, 0
while i < len(FR):
    if not cap.grab():
        break
    t_file = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    if t_file - OFF < -1.0:
        continue
    t, t_rec, src, det = FR[i]
    if abs(t_file - t_rec) > 1e-3:
        mism += 1
    i += 1
    if src is None:
        continue
    ok, img = cap.retrieve()
    if not ok:
        break
    if pano:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if det:
        last = (det["cx"], det["cy"])
    cx, cy = last if last else (W / 2, H / 2)
    top = cv2.resize(img, (1280, OH), interpolation=cv2.INTER_AREA)
    c1, x1, y1 = crop(img, cx, cy, 640, 360)
    c2, x2, y2 = crop(img, cx, cy, 320, 180); c2 = cv2.resize(c2, (640, 360), interpolation=cv2.INTER_CUBIC)
    k = int(round(t / STEP))
    op = OP.get(k) if abs(t - STEP * k) < 0.03 else None
    if det:
        e = (det["cx"], det["cy"], det["a"], det["b"], det["th"])
        cv2.circle(top, (int(det["cx"] * S), int(det["cy"] * S)), 9, (0, 255, 0), 2, cv2.LINE_AA)
        ell(c1, e, 1.0, x1, y1, (0, 255, 0), 2); ell(c2, e, 2.0, x2, y2, (0, 255, 0), 2)
    if op:
        ell(c1, op, 1.0, x1, y1, (255, 0, 255), 2, True); ell(c2, op, 2.0, x2, y2, (255, 0, 255), 2, True)
    frame = np.vstack([top, np.hstack([c1, c2])])
    txt = f"{CAM}  t {t:7.2f} s (grid frame {t / STEP + 1:6.1f})  prior: {src}"
    txt += f"   conf {det['conf']:.2f}  white {det['white']:.2f}" if det else "   NOT FOUND"
    cv2.putText(frame, txt, (8, OH + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, txt, (8, OH + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if det else (0, 0, 255), 1, cv2.LINE_AA)
    if op:
        cv2.putText(frame, "operator mark (2-s grid)", (648, OH + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2, cv2.LINE_AA)
    ff.stdin.write(frame.tobytes()); written += 1
    if written % 1000 == 0:
        print(f"{CAM}: {written} frames written, t {t:.1f} s", flush=True)
ff.stdin.close(); ff.wait()
print(f"{CAM}: {written} frames -> {OUT}  ({written / 20:.0f} s of video; frame-time mismatches vs the track file: {mism})")
