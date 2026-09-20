# -*- coding: utf-8 -*-
r"""Decode the placements the operator marked by hand in manual_board_gui.html.

Each entry of manual_quads.json carries the four clicked outline corners (first click = the corner
that sits on the cone), the camera, the station and the timeline window. The quad is mapped back to
full-frame stored pixel coordinates and handed to board_detect.detect() as the board hint for every
keyframe of that window; the corners are cached exactly like the automatic path
(corners/CHxx/<HHMMSS>_m<n>.npz, method 'manual-*'). The clicked cone corner is recorded per window
in manual_cone_corner.json so the fit knows which board corner touches the cone.
Usage: python manual_boards.py [--session <dir|date>] [<manual_quads.json>] [--step 1]
"""
import sys, re, json, subprocess, threading, time
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths, board_detect as bd  # noqa: E402

FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"; FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
STEP = int(opt("--step", "1"))
rest = [a for a in args if not a.startswith("--") and a not in (opt("--step"),)]
src = Path(rest[0]) if rest else (QC / "manual" / "manual_quads.json")
if not src.exists():
    alt = Path.home() / "Downloads" / "manual_quads.json"
    if alt.exists(): src = alt
    else: sys.exit(f"no manual_quads.json (looked in {QC / 'manual'} and Downloads)")
jobs = json.loads(src.read_text(encoding="utf-8"))
print(f"{src}: {len(jobs)} entries ({sum(1 for j in jobs if j.get('skip'))} skipped by the operator)")
SW = 2160

def to_stored(cam, pts_disp, off, scale, pano):
    """GUI canvas px -> full-frame STORED px (the panos are displayed upright)."""
    p = np.asarray(pts_disp, float) / scale + np.asarray(off, float)
    if pano:
        return np.stack([(SW - 1) - p[:, 1], p[:, 0]], 1)                  # upright (x,y) -> stored
    return p

def seg_for(cam, t):
    for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t <= b: return p, a
    return None, None

cone_corner = {}
cc_path = QC / "manual_cone_corner.json"
if cc_path.exists():
    cone_corner = json.loads(cc_path.read_text(encoding="utf-8"))
summary = []
for j in jobs:
    if j.get("skip") or not j.get("quad"):
        summary.append((j["cam"], j["station"], "operator: board not visible")); continue
    cam, st, pano = j["cam"], j["station"], j.get("pano", j["cam"] in ("CH01", "CH02"))
    a, b = [datetime.strptime(f"{DATE} {x}", "%Y-%m-%d %H:%M:%S") for x in j["win"]]
    quad = to_stored(cam, j["quad"], j["off"], j.get("scale", 1.0), pano)
    seg, seg_start = seg_for(cam, a)
    if seg is None:
        summary.append((cam, st, "no closed segment")); continue
    w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                                     "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
    R = 1.2 * max(np.ptp(quad[:, 0]), np.ptp(quad[:, 1])) + 120
    c = quad.mean(0)
    x0, y0 = int(max(0, c[0] - R)), int(max(0, c[1] - R)); x1, y1 = int(min(w, c[0] + R)), int(min(h, c[1] + R))
    off = np.array([x0, y0], float)
    hint = quad - off
    area = abs(cv2.contourArea(quad.astype(np.float32)))
    ss = (a - seg_start).total_seconds(); dur = (b - a).total_seconds() + 0.5
    cmd = [FFMPEG, "-v", "info", "-nostats", "-skip_frame", "nokey", "-ss", f"{ss:.2f}", "-i", str(seg), "-t", f"{dur:.2f}",
           "-vf", f"select=not(mod(n\\,{STEP})),showinfo", "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=w * h * 4)
    pts_list = []
    def rd():
        for line in proc.stderr:
            m = re.search(rb"pts_time:\s*([0-9.]+)", line)
            if m and b"showinfo" in line: pts_list.append(float(m.group(1)))
    th = threading.Thread(target=rd, daemon=True); th.start()
    n = saved = best = 0; notes = {}; t0 = time.time()
    while True:
        buf = proc.stdout.read(w * h)
        if len(buf) < w * h: break
        for _ in range(200):
            if len(pts_list) > n: break
            time.sleep(0.005)
        t_rel = ss + (pts_list[n] if len(pts_list) > n else n * STEP / 15.0)
        gray = np.frombuffer(buf, np.uint8).reshape(h, w)[y0:y1, x0:x1]; n += 1
        method, px, ids, note, mk_ids, mk_px = bd.detect(gray, quad_hint=hint, area_hint=area)
        if method is None and n == 1:
            # Nothing decodes even with the hint (blurred far-field board): the operator's four clicks
            # ARE the measurement. Corners are predicted from that outline homography and parity-checked;
            # accuracy is click accuracy (a few px), so the method tag keeps them separable in the fit.
            Hq = cv2.findHomography(bd.OUTLINE_MM.reshape(-1, 1, 2).astype(np.float32), hint.reshape(-1, 1, 2).astype(np.float32), 0)[0]
            if Hq is not None:
                vis = bd.visible_corners(gray, Hq, min_contrast=8.0)
                if vis.sum() >= 12:
                    px = cv2.perspectiveTransform(bd.OBJ_MM.reshape(-1, 1, 2), Hq).reshape(-1, 2)[vis]
                    ids = np.arange(88)[vis]; method = "outline"; mk_ids = mk_px = None
                    note = f"operator outline only, {int(vis.sum())}/88 corners predicted from the clicked quad"
        if method and len(ids) >= 12:
            tag = (seg_start + timedelta(seconds=t_rel)).strftime("%H%M%S")
            extra = {} if mk_ids is None else dict(mk_ids=np.asarray(mk_ids, np.int32), mk_px=np.asarray(mk_px, float) + off)
            np.savez_compressed(QC / "corners" / cam / f"{tag}_m{n:04d}.npz", ids=np.asarray(ids, np.int32), px=np.asarray(px, float) + off,
                                seg=seg.name, t_rel=float(t_rel), bw=False, method="manual-" + method, **extra)
            saved += 1; best = max(best, len(ids)); notes["manual-" + method] = notes.get("manual-" + method, 0) + 1
            if saved == 1:                       # which board corner did the operator put on the cone?
                Hm, _ = cv2.findHomography(bd.OBJ_MM[ids].reshape(-1, 1, 2), (np.asarray(px, float)).reshape(-1, 1, 2), 0)
                if Hm is not None:
                    ol = cv2.perspectiveTransform(bd.OUTLINE_MM.reshape(-1, 1, 2), Hm).reshape(-1, 2)
                    k = int(np.argmin(np.linalg.norm(ol - hint[0], axis=1)))
                    cone_corner.setdefault(cam, {})[f"{st}@{j['win'][0]}"] = {"corner_mm": bd.OUTLINE_MM[k].tolist(),
                                                                             "dist_px": float(np.linalg.norm(ol[k] - hint[0]))}
    proc.wait(); th.join(timeout=2)
    line = (cam, st, f"{j['win'][0]}-{j['win'][1]}: tried {n} frames, saved {saved} (best {best} corners) {notes} {time.time()-t0:.0f}s")
    summary.append(line); print(*line, flush=True)
cc_path.write_text(json.dumps(cone_corner, indent=1), encoding="utf-8")
print("\n=== manual summary ===")
for s in summary: print(*s)
print("->", cc_path)
