# -*- coding: utf-8 -*-
r"""Do the cameras' burned-in OSD clocks tick together? (2026-10-04, for video <-> ephys sync; a TEST, not a pipeline.)
On the 2026-09-30 ball session each camera's clock offset against CH02 is known from the 20 Hz ball (held20.json:
common clock = a * entry + b - offset). Per camera: decode the ball segment (seek as ball_track20.py); the OSD's
HH:MM:SS box (stored-frame pixels, BOX), binarised at grey > 200 (the white text only), changes by > 0.4 % of its
pixels at a seconds tick (at most one tick per 0.6 s); each tick's time on the common clock (half a frame before the
first frame showing the new second), modulo 1 s. If the OSD clocks were one clock, every camera's tick phase would be
the same.

Result 2026-10-04 (520 s, 523-534 ticks per camera): tick phase minus CH02's - CH04 +2, CH06 -22, CH05 +218, CH01 -250,
CH03 -409 ms; per-camera residual p90 13-208 ms (the phase itself to a few ms). So each camera's OSD is a continuous
clock of its own (it removes the +-1 s per-file offset of the file names), but the cameras' OSD clocks differ by up
to 0.4 s: every camera needs its own offset to the PC / ephys clock. Handoff: the analysis repo's
implementation_plan/2026-10-05-video-clock-sync.md.

Usage: python osd_tick_test.py [CH01,CH02,...]   -> prints, and writes <qc>\2026-09-30\ball\track20\osd_tick_test.json
"""
import json, sys
from pathlib import Path
import numpy as np, cv2

BALL = Path(r"F:\calibration\qc\2026-09-30\ball")
SESSION = Path(r"F:\calibration\session_2026-09-30_15-49-39")
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
H = json.loads((BALL / "track20" / "held20.json").read_text(encoding="utf-8"))
# OSD time box (x0, x1, y0, y1) in the STORED frame (panos stored 2160 x 7680, the text along the right edge)
BOX = {"CH01": (1950, 2160, 3700, 4500), "CH02": (1950, 2160, 3700, 4500), "CH03": (2150, 2700, 20, 150),
       "CH04": (2150, 2700, 20, 150), "CH05": (1240, 1530, 5, 75), "CH06": (1240, 1530, 5, 75)}
cams = sys.argv[1].split(",") if len(sys.argv) > 1 else list(BOX)
out = {}
for cam in cams:
    job = next(c for c in jobs["cams"] if c["cam"] == cam)
    fr = json.loads((BALL / "track20" / f"ball20_{cam}.json").read_text(encoding="utf-8"))
    tfile = np.array([f[1] for f in fr["frames"]]); a, b = H["lines"][cam]; off = H["offsets_s"][cam]
    cap = cv2.VideoCapture(str(SESSION / job["file"]))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, (float(job["offset_s"]) - 3.0)) * 1000)
    x0, x1, y0, y1 = BOX[cam]; prev, rows = None, []
    while True:
        ok = cap.grab()
        if not ok:
            break
        tf = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if tf > tfile[-1] + 0.01:
            break
        ok, img = cap.retrieve()
        g = (cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)   # the white OSD text only
        if prev is not None:
            rows.append((tf, float(np.abs(g - prev).mean())))
        prev = g
    T = np.array(rows); thr = 0.004
    cand = T[T[:, 1] > thr, 0]; tick = []
    for t_ in cand:                                                      # one tick per second: the first changed frame
        if not tick or t_ - tick[-1] > 0.6:
            tick.append(t_)
    tick = np.array(tick)
    # map tick frame times to ball entries (exact t_file match), then to the common clock
    ent = np.searchsorted(tfile, tick - 1e-4); ok = (ent < len(tfile)) & (np.abs(tfile[np.minimum(ent, len(tfile) - 1)] - tick) < 1e-3)
    tc = a * ent[ok] + b - off - a / 2                                   # half a frame before the first new-second frame
    ph = np.angle(np.mean(np.exp(2j * np.pi * tc))) / (2 * np.pi) % 1.0
    res = ((tc - ph + 0.5) % 1.0) - 0.5
    out[cam] = dict(n_ticks=int(ok.sum()), phase_s=round(float(ph), 4), spread_ms=round(float(np.std(res) * 1000), 1),
                    p90_abs_ms=round(float(np.percentile(np.abs(res), 90) * 1000), 1), thr=round(float(thr), 2))
    print(cam, out[cam], flush=True)
ref = out.get("CH02", next(iter(out.values())))["phase_s"]
print("tick phase minus CH02's (ms; equal phases = the OSD clocks agree with the ball's offsets):",
      {c: round((((v["phase_s"] - ref + 0.5) % 1.0) - 0.5) * 1000, 1) for c, v in out.items()})
json.dump(out, open(r"F:\calibration\qc\2026-09-30\ball\track20\osd_tick_test.json", "w"), indent=1)
