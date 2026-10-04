# -*- coding: utf-8 -*-
r"""GUI for the placements the automatic detector cannot find: the operator clicks the board's four
outline corners on one frame, the detector then decodes the whole window from that hint.

For every (timeline window x camera) with fewer than --min-frames cached detections, one frame from
the middle of the window is rendered (pano cameras upright, cropped around the expected board
position). The page shows them one by one; click the four corners of the PLATE EDGE - the whole
800 x 600 mm aluminium plate, white border included, TOP surface (it is 6 mm thick, so the side face
shows at oblique angles). NOT the printed pattern: a pattern corner is only visible where its outer
square is black, and two of the four are white-on-white. Order: the plate corner next to the cone
first, then along the long edge, then the diagonal, then back. "Skip" marks a frame as 'board not
visible'. Export writes manual_quads.json next to the frames; feed it to
  python manual_boards.py [--session ...]
which re-runs the detector with each quad as the board hint and caches the corners like the
automatic path.
--mode picks which windows to show:
  missing  (default) only windows with no cached detection at all;
  located  those plus the windows where the board was only LOCATED, not decoded - the machine's
           outline is drawn on the frame so the operator can accept it (key a) or re-click it;
  all      every window, including the decoded ones, for a full audit.
  audit    every window in which the machine found something, plus every window whose station the
           current fit (paddock_map) says is inside this camera's frame - so the operator sees each
           machine box the fit will use AND each place where the machine found nothing it should have.
--sweep CH03=15:36:32-15:41:46[,CH04=...]  adds the hand-held distortion sweeps as one frame every
           --sweep-step seconds (default 2), labelled SW<HHMMSS>; the machine's box is drawn where it
           has one. On a hand-held plate there is no cone: click any corner first and go around.
--timeline <file>  windows file to use instead of <qc>\placement_timeline.txt; --out <dir> output dir.
Usage: python manual_board_gui.py [--session <dir|date>] [--mode missing|located|all|audit] [--cams CH01,CH02]
                                  [--sweep CHxx=HH:MM:SS-HH:MM:SS,...] [--sweep-step 2] [--timeline <file>] [--out <dir>]
Output: <qc>\manual\  (frames + manual_board_gui.html)
"""
import sys, re, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = qc_paths.FFMPEG; FFPROBE = qc_paths.FFPROBE
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
CAMS = opt("--cams", "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
MODE = opt("--mode", "missing")
MIN_FRAMES = int(opt("--min-frames", "1"))
REUSE = "--reuse-frames" in args          # rebuild the page from the frames already on disk (seconds, not minutes)
CROP = "--crop" in args                   # old behaviour: cut a window around where the board is expected.
                                          # Default is the WHOLE frame: a crop centred on a false positive hides
                                          # the real board and invites the operator to confirm the wrong object
                                          # (operator, 2026-09-22). The page zooms and pans instead.
MAXW = int(opt("--max-width", "3840"))
OUT = Path(opt("--out")) if opt("--out") else QC / "manual"; OUT.mkdir(parents=True, exist_ok=True)
TIMELINE = Path(opt("--timeline")) if opt("--timeline") else QC / "placement_timeline.txt"
SWEEP_STEP = float(opt("--sweep-step", "2"))
SWEEPS = []                                   # (cam, start, end) hand-held distortion sweeps
for item in (opt("--sweep", "") or "").split(","):
    if item.strip():
        c, rng = item.split("="); a, b = rng.split("-")
        SWEEPS.append((c.strip().upper(), a.strip(), b.strip()))
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
LATTICE = {f"T{li}{si}": (x, y) for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)}
LATTICE.update({f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}": (x, y) for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)})

def clk(s): return datetime.strptime(f"{DATE} {s}", "%Y-%m-%d %H:%M:%S")
wins = []
for ln in TIMELINE.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*(\d\d:\d\d:\d\d)-(\d\d:\d\d:\d\d)\s+(\S+)", ln)
    if m:
        a, b = clk(m.group(1)), clk(m.group(2)); wins.append([min(a, b), max(a, b), m.group(3).upper(), None])
merged = []
for w in sorted(wins, key=lambda w: w[0]):
    same = next((c for c in merged if c[2] == w[2] and w[0] <= c[1] + timedelta(seconds=1) and w[1] >= c[0] - timedelta(seconds=1)), None)
    if same: same[0], same[1] = min(same[0], w[0]), max(same[1], w[1])
    else: merged.append(list(w))
wins = merged
for c, a, b in SWEEPS:                        # one window per sample, this camera only
    t, end = clk(a), clk(b)
    while t <= end:
        wins.append([t, t + timedelta(seconds=SWEEP_STEP), f"SW{t.strftime('%H%M%S')}", c])
        t += timedelta(seconds=SWEEP_STEP)
_FIT = None
if MODE == "audit":
    try:
        import paddock_map as _pm; _FIT = _pm.load()
        print("audit mode: windows are also included when the current fit puts the station inside the frame", flush=True)
    except Exception as e:
        print(f"audit mode: no usable fit ({e}); including every window", flush=True)
def in_view(cam, st):
    if _FIT is None or cam not in _FIT or st not in LATTICE: return True
    return bool(_FIT[cam].sees(LATTICE[st], units="in", margin=-150))

BOARD = cv2.aruco.CharucoBoard((12, 9), 0.060, 0.045, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
OBJ_MM = np.asarray(BOARD.getChessboardCorners(), float).reshape(-1, 3)[:, :2] * 1000.0
OUTLINE_MM = np.array([[0, 0], [720, 0], [720, 540], [0, 540]], float)

def cached(cam):
    """-> list of (time, n_corners, method, outline in STORED px or None)."""
    out = []
    for p in (QC / "corners" / cam).glob("*.npz"):
        with np.load(p, allow_pickle=False) as z:
            seg = str(z["seg"]); t_rel = float(z["t_rel"])
            ids = z["ids"].astype(int).reshape(-1); px = z["px"].astype(float).reshape(-1, 2)
            method = str(z["method"]) if "method" in z.files else "charuco"
            quad = z["quad"].astype(float).reshape(-1, 2) if "quad" in z.files else None
        m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d\d)-(\d\d)-(\d\d)_to_", seg)
        t = datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S") + timedelta(seconds=t_rel)
        ol = quad
        if ol is None and len(ids) >= 8:
            H, _ = cv2.findHomography(OBJ_MM[ids].reshape(-1, 1, 2), px.reshape(-1, 1, 2), 0)
            ol = None if H is None else cv2.perspectiveTransform(OUTLINE_MM.reshape(-1, 1, 2), H).reshape(-1, 2)
        out.append((t, len(ids), method, ol))
    return sorted(out, key=lambda r: r[0])

def cone_map(cam):
    """station -> UPRIGHT pixel, rescaled from whatever pixel space the label file declares."""
    return {k: v for k, v in qc_paths.load_cones(QC, cam, SESSION, space="upright").items() if k in LATTICE}

def expected_upright(cones, station, K=8):
    if station in cones: return cones[station], "cone"
    names = list(cones)
    if len(names) < 4: return None, None
    F = np.array([LATTICE[s] for s in names], float); P = np.array([cones[s] for s in names])
    d = np.linalg.norm(F - np.array(LATTICE[station], float), axis=1); o = np.argsort(d)[:K]
    H, _ = cv2.findHomography(F[o].reshape(-1, 1, 2), P[o].reshape(-1, 1, 2), 0)
    if H is None: return None, None
    return cv2.perspectiveTransform(np.array(LATTICE[station], float).reshape(-1, 1, 2), H).reshape(2), "lattice"

def seg_for(cam, t):
    for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= t <= b: return p, a
    return None, None

jobs = []
old_jobs = {}
if (OUT / "jobs.json").exists():
    try:
        old_jobs = {j["file"]: j for j in json.loads((OUT / "jobs.json").read_text(encoding="utf-8"))}
    except Exception:
        old_jobs = {}
for cam in CAMS:
    pano = cam in ("CH01", "CH02")
    cones = cone_map(cam) if pano else {}
    have = cached(cam)
    for a, b, st, only in wins:
        if only is not None and only != cam:
            continue
        inwin = [r for r in have if a <= r[0] <= b]
        decoded = [r for r in inwin if r[1] >= 12]
        if MODE == "missing" and len(inwin) >= MIN_FRAMES:
            continue
        if MODE == "located" and decoded:
            continue
        if MODE == "audit" and only is None and not inwin and not in_view(cam, st):
            continue
        # Take a frame from the LATE part of the window: the operator may still be walking in front of
        # the plate at the start, and the plate does not move within a window (operator, 2026-09-22).
        withq = [r for r in inwin if r[3] is not None]
        best = withq[-1] if withq else (max(inwin, key=lambda r: r[1]) if inwin else None)
        mid = best[0] if (best and best[3] is not None) else a + 0.8 * (b - a)
        seg, seg_start = seg_for(cam, mid)
        if seg is None:
            continue
        name = f"{cam}_{st}_{mid.strftime('%H%M%S')}.jpg"
        machine = None
        if best is not None and best[3] is not None:                       # machine outline, stored -> upright
            machine = qc_paths.stored_to_upright(best[3], SESSION, cam)
        prev = old_jobs.get(name)
        if REUSE and prev is not None and (OUT / name).exists():           # rebuild the page, no re-decoding
            j2 = dict(prev)
            disp = None if machine is None else ((machine - np.array(prev["off"], float)) * prev["scale"])
            j2.update(machine=None if disp is None else np.round(disp, 1).tolist(),
                      machine_method=None if best is None else best[2],
                      machine_corners=None if best is None else int(best[1]))
            jobs.append(j2); print(f"{cam} {st:6s} reuse {name}" + (f"  [machine {best[2]} {best[1]}c]" if machine is not None else ""), flush=True)
            continue
        w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                                         "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{(mid - seg_start).total_seconds():.2f}", "-i", str(seg), "-frames:v", "1",
                              "-vf", "transpose=2" if pano else "null", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE).stdout
        W, H = (h, w) if pano else (w, h)
        if len(raw) < W * H * 3:
            continue
        img = np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy()
        x0 = y0 = 0
        if pano:
            for cname, p in cones.items():                                  # every labelled cone, for orientation
                cv2.circle(img, tuple(int(v) for v in p), 10, (0, 255, 255), 2)
                cv2.putText(img, cname, (int(p[0]) + 12, int(p[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            if st in cones:                                                 # this window's own cone, emphasised
                p = cones[st]
                cv2.circle(img, tuple(int(v) for v in p), 26, (0, 200, 255), 4)
        if CROP and pano:
            c, how = expected_upright(cones, st)
            if machine is not None:
                c, how = machine.mean(0), "machine outline"
            if c is None:
                continue
            R = 900
            x0, y0 = int(max(0, min(W - 2 * R, c[0] - R))), int(max(0, min(H - 2 * R, c[1] - R)))
            x1, y1 = int(min(W, x0 + 2 * R)), int(min(H, y0 + 2 * R))
            if x1 - x0 < 50 or y1 - y0 < 50:          # predicted position outside this camera's frame
                print(f"{cam} {st:6s} predicted outside the frame ({c.round().tolist()}), skipped", flush=True)
                continue
            img = img[y0:y1, x0:x1]
        scale = 1.0
        if img.shape[1] > MAXW:
            scale = MAXW / img.shape[1]; img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(OUT / name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        disp = None if machine is None else ((machine - [x0, y0]) * scale)
        jobs.append(dict(file=name, cam=cam, station=st, clock=mid.strftime("%H:%M:%S"),
                         win=[a.strftime("%H:%M:%S"), b.strftime("%H:%M:%S")], off=[x0, y0], scale=scale,
                         w=int(img.shape[1]), h=int(img.shape[0]), pano=pano,
                         machine=None if disp is None else np.round(disp, 1).tolist(),
                         machine_method=None if best is None else best[2],
                         machine_corners=None if best is None else int(best[1])))
        print(f"{cam} {st:6s} {a.strftime('%H:%M:%S')}-{b.strftime('%H:%M:%S')} -> {name}"
              + (f"  [machine {best[2]} {best[1]}c]" if machine is not None else ""), flush=True)

from manual_gui_page import PAGE as html                                  # noqa: E402  (shared page)
(OUT / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
(OUT / "manual_board_gui.html").write_text(html.replace("__JOBS__", json.dumps(jobs)).replace("__DATE__", DATE), encoding="utf-8")
print(f"\n{len(jobs)} frames to click -> {OUT / 'manual_board_gui.html'}")
