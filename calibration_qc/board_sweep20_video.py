# -*- coding: utf-8 -*-
r"""Review video of the 20 Hz hand-held sweep detections (board_sweep20.py), all cameras of one window side by side.

One column per camera (the sweep camera first), each 640 px wide: top = the whole frame scaled down with the
board's outline, bottom = a native-resolution crop around the board with every decoded corner drawn, coloured by
its id (row-major 0..87: blue -> red), so a board decoded upside down or shifted by a square shows as a colour
pattern out of place. The columns are synchronised on the sweep camera's frames, the other cameras shifted by
their clock offsets (--offsets) and matched to the nearest frame (regular frame times, see board_sweep20.py).

Usage: python board_sweep20_video.py --window CH03 --cams CH03,CH01,CH02 --offsets CH01=0.52,CH02=0.46
Output: <qc>\sweep20\<WINDOW>_sweep_review.mp4
"""
import sys, json, subprocess
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                           # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
WINDOW = opt("--window"); CAMS = opt("--cams").split(",")
OFFS = {k: float(v) for k, v in (x.split("=") for x in (opt("--offsets", "") or "").split(",") if x)}
SESSION, _ = qc_paths.resolve(opt("--session"))
SW = qc_paths.QC_ROOT / "sweep20"
OUT = SW / f"{WINDOW}_sweep_review.mp4"


def regular_times(t_abs):
    i = np.arange(len(t_abs)); b = np.polyfit(i, t_abs, 1)[0]; r = t_abs - b * i
    med = np.array([np.median(r[max(0, j - 200):j + 201]) for j in range(0, len(r), 20)])
    return np.interp(i, np.arange(0, len(r), 20), med) + b * i


class Stream:
    def __init__(self, cam):
        d = json.loads((SW / f"{WINDOW}_{cam}.json").read_text(encoding="utf-8"))
        self.cam, self.F = cam, d["frames"]
        self.t = regular_times(np.array([f[2] for f in self.F])) + OFFS.get(cam, 0.0)
        self.pano = cam in ("CH01", "CH02")
        self.cap = cv2.VideoCapture(str(SESSION / d["file"]))
        self.cap.set(cv2.CAP_PROP_POS_MSEC, (self.F[0][1] - 0.5) * 1000)
        self.i, self.img = -1, None
        while True:                                          # position on the first recorded frame
            if not self.cap.grab():
                raise SystemExit(f"{cam}: could not reach the first frame")
            if abs(self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 - self.F[0][1]) < 1e-3:
                self.i = 0; break
        self.last_box = None

    def at(self, t):
        """advance to the frame nearest t (never backwards); return (index, image)."""
        while self.i + 1 < len(self.F) and abs(self.t[self.i + 1] - t) <= abs(self.t[self.i] - t):
            self.cap.grab(); self.i += 1; self.img = None
        if self.img is None:
            ok, img = self.cap.retrieve()
            self.img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE) if (ok and self.pano) else (img if ok else None)
        return self.i, self.img


def panel(s, i, img, t_main):
    H, W = img.shape[:2]
    f = s.F[i]; ids = np.asarray(f[4], int); px = np.asarray(f[5], float).reshape(-1, 2)
    if len(px):
        s.last_box = (px.min(0), px.max(0))
    sc = 640 / W; top = cv2.resize(img, (640, int(round(H * sc / 2)) * 2), interpolation=cv2.INTER_AREA)
    if s.last_box is not None:
        a, b = s.last_box
        cv2.rectangle(top, tuple((a * sc).astype(int) - 4), tuple((b * sc).astype(int) + 4), (0, 255, 255) if len(px) else (0, 0, 255), 2)
    top = cv2.copyMakeBorder(top, 0, max(0, 360 - top.shape[0]), 0, 0, cv2.BORDER_CONSTANT)[:360]
    if s.last_box is not None:
        a, b = s.last_box; c = (a + b) / 2; side = float(np.clip(1.6 * (b - a).max(), 200, 1400))
    else:
        c = np.array([W / 2, H / 2]); side = 1400.0
    x0 = int(np.clip(c[0] - side * 16 / 18, 0, max(0, W - side * 16 / 9))); y0 = int(np.clip(c[1] - side / 2, 0, max(0, H - side)))
    cw, ch = int(min(W - x0, side * 16 / 9)), int(min(H - y0, side))
    crop = img[y0:y0 + ch, x0:x0 + cw]; k = min(640 / cw, 360 / ch)
    crop = cv2.resize(crop, (int(cw * k), int(ch * k)), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    for idv, p in zip(ids, px):
        col = cv2.applyColorMap(np.uint8([[int(255 * idv / 87)]]), cv2.COLORMAP_JET)[0, 0].tolist()
        cv2.circle(crop, (int((p[0] - x0) * k), int((p[1] - y0) * k)), 3, col, -1, cv2.LINE_AA)
    crop = cv2.copyMakeBorder(crop, 0, 360 - crop.shape[0], 0, 640 - crop.shape[1], cv2.BORDER_CONSTANT)
    out = np.vstack([top, crop])
    txt = f"{s.cam}  frame {i}  dt {s.t[i] - t_main:+.3f} s  corners {len(px)}"
    cv2.putText(out, txt, (6, 382), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(out, txt, (6, 382), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0) if len(px) >= 12 else (0, 0, 255), 1, cv2.LINE_AA)
    return out


streams = [Stream(c) for c in CAMS]
ff = subprocess.Popen([str(qc_paths.FFMPEG), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{640 * len(CAMS)}x720",
                       "-r", "20", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(OUT)],
                      stdin=subprocess.PIPE)
main = streams[0]; n = 0
for j in range(len(main.F)):
    t = main.t[j]
    cols = []
    for s in streams:
        i, img = s.at(t)
        cols.append(panel(s, i, img, t) if img is not None else np.zeros((720, 640, 3), np.uint8))
    ff.stdin.write(np.hstack(cols).tobytes()); n += 1
    if n % 400 == 0:
        print(f"{n} frames", flush=True)
ff.stdin.close(); ff.wait()
print(f"{n} frames -> {OUT}")
