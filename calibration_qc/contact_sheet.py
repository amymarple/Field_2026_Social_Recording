# -*- coding: utf-8 -*-
"""Human-in-the-loop station labelling: one row per placement (time-clustered across all six
cameras), pano crops around the detected board (or a downscaled full frame when neither pano
decoded it), the machine's station guess, and an input box for the operator's answer.
Writes E:\calibration\qc\contact_sheet.html + contact_sheet_template.csv."""
import csv, base64, subprocess
from pathlib import Path
from datetime import datetime, time as dtime
import numpy as np, cv2

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
QC = qc_paths.QC_ROOT; SESSION = qc_paths.DEFAULT_SESSION
FFMPEG = qc_paths.FFMPEG
CAMS = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
SWEEPS = [(dtime(15, 40, 25), dtime(15, 41, 35)), (dtime(15, 41, 40), dtime(15, 45, 45))]
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
OFF = np.array([14.2, 10.6]); stations = {}
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1): stations[f"T{li}{si}"] = np.array([x, y], float) + OFF
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1): stations[f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}"] = np.array([x, y], float) + OFF
names = list(stations); sxy = np.array([stations[n] for n in names])
maps = np.load(QC / "refined_pano_maps.npz")
def apply_poly(P, px):
    x, y = px[:, 0] / 1000.0, px[:, 1] / 1000.0
    return np.stack([np.stack([np.ones_like(x), x, y, x*x, x*y, y*y], 1) @ P[0],
                     np.stack([np.ones_like(x), x, y, x*x, x*y, y*y], 1) @ P[1]], 1)

events = []
for cam in CAMS:
    p = QC / f"{cam}_placements_e1.csv"
    if not p.exists(): continue
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["clock"], "%H:%M:%S")
            if any(a <= t.time() <= b for a, b in SWEEPS) or int(r["max_markers"]) < 4: continue
            events.append(dict(t=t, cam=cam, nc=int(r["max_corners"]), px=(float(r["px_x"]), float(r["px_y"])),
                               seg=None, dur=float(r["dur_s"])))
events.sort(key=lambda e: e["t"])
clusters = []
for e in events:
    if clusters and (e["t"] - clusters[-1]["t_end"]).total_seconds() <= 12:
        c = clusters[-1]; c["t_end"] = max(c["t_end"], e["t"]); c["ev"].append(e)
    else:
        clusters.append(dict(t=e["t"], t_end=e["t"], ev=[e]))

def seg_for(cam, t):
    for s in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a.time() <= t.time() <= b.time(): return s, (datetime.combine(a.date(), t.time()) - a).total_seconds()
    return None, None

def frame(cam, t, w, h):
    seg, off = seg_for(cam, t)
    if seg is None: return None
    buf = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{off:.1f}", "-i", str(seg), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(buf) < w * h * 3: return None
    return np.frombuffer(buf, np.uint8).reshape(h, w, 3)

def crop_b64(img, px, size=520):
    x, y = int(px[0]), int(px[1]); h, w = img.shape[:2]
    x0, y0 = max(0, x - size // 2), max(0, y - size // 2); x1, y1 = min(w, x0 + size), min(h, y0 + size)
    c = img[y0:y1, x0:x1]
    c = cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE)          # show panos upright like the reference stills
    ok, jpg = cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, 80]); return base64.b64encode(jpg).decode()

def full_b64(img):
    small = cv2.resize(cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE), (1920, 540))
    ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70]); return base64.b64encode(jpg).decode()

rows_html, rows_csv = [], []
cache = {}
for i, c in enumerate(clusters, 1):
    mid = c["t"] + (c["t_end"] - c["t"]) / 2
    per = {cam: max([e["nc"] for e in c["ev"] if e["cam"] == cam] or [0]) for cam in CAMS}
    guess = ""; pos = None
    for cam in ("CH01", "CH02"):
        best = max([e for e in c["ev"] if e["cam"] == cam], key=lambda e: e["nc"], default=None)
        if best and best["nc"] >= 6:
            p = apply_poly(maps[cam], np.array([best["px"]]))[0]
            pos = p if pos is None else (pos + p) / 2
    if pos is not None:
        d = np.linalg.norm(sxy - pos, axis=1); o = np.argsort(d)
        guess = f"{names[o[0]]} ({d[o[0]]:.0f} in)  alt {names[o[1]]} ({d[o[1]]:.0f})"
    imgs = []
    for cam in ("CH01", "CH02"):
        best = max([e for e in c["ev"] if e["cam"] == cam], key=lambda e: e["nc"], default=None)
        img = frame(cam, best["t"] if best else mid, 2160, 7680)
        if img is None: imgs.append(f"<td>{cam}: no frame</td>"); continue
        if best:
            imgs.append(f'<td>{cam} {best["nc"]} corners<br><img src="data:image/jpeg;base64,{crop_b64(img, best["px"])}"></td>')
        else:
            imgs.append(f'<td>{cam}: not detected - full frame<br><img width="960" src="data:image/jpeg;base64,{full_b64(img)}"></td>')
    counts = " ".join(f"{k}:{v}" for k, v in per.items() if v)
    rows_html.append(f'<tr><td><b>#{i}</b><br>{c["t"].strftime("%H:%M:%S")}<br>-{c["t_end"].strftime("%H:%M:%S")}<br>{counts}<br>guess: {guess}'
                     f'<br><input id="s{i}" size="6" placeholder="ID"> <label><input type="checkbox" id="x{i}"> not a placement</label></td>{"".join(imgs)}</tr>')
    rows_csv.append([i, c["t"].strftime("%H:%M:%S"), c["t_end"].strftime("%H:%M:%S"), counts, guess.split(" ")[0] if guess else "", ""])
    print(f"#{i} {c['t'].strftime('%H:%M:%S')} {counts} guess={guess}", flush=True)

html = ["<html><head><meta charset='utf-8'><title>2026-09-18 placements - confirm station IDs</title>",
        "<style>body{font-family:Arial;font-size:13px} td{vertical-align:top;border-bottom:1px solid #ccc;padding:4px} img{max-width:520px}</style></head><body>",
        "<h2>Confirm the station ID of every placement (T11..T75, V.., F..). Leave blank if unsure; tick 'not a placement' for sweeps/carrying.</h2>",
        "<p>Rows = placements clustered by time across all six cameras; crops are CH01/CH02 around the detected board (rotated upright). Then press the button and paste the text back.</p>",
        "<button onclick=\"var out=[];document.querySelectorAll('tr').forEach(function(tr){var n=tr.querySelector('input[id^=s]');if(!n)return;var i=n.id.slice(1);out.push(i+','+(document.getElementById('x'+i).checked?'NONE':n.value));});document.getElementById('out').value=out.join('\\n');\">Collect answers</button>",
        "<textarea id='out' rows='6' cols='40'></textarea><table>", *rows_html, "</table></body></html>"]
(QC / "contact_sheet.html").write_text("\n".join(html), encoding="utf-8")
with open(QC / "contact_sheet_template.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["idx", "start", "end", "corners_per_cam", "guess", "operator_station_id"]); w.writerows(rows_csv)
print(f"{len(clusters)} placements -> {QC / 'contact_sheet.html'}")
