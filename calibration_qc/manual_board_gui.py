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

html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Manual board corners __DATE__</title>
<style>
 body{margin:0;background:#1b1b1b;color:#eee;font-family:Arial,sans-serif;font-size:14px}
 #bar{position:sticky;top:0;background:#2a2a2a;padding:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:5}
 button{font-size:14px;padding:4px 10px} #wrap{position:relative;display:inline-block;margin:8px}
 canvas{cursor:crosshair;max-width:100%;background:#000} #list{padding:8px;font:12px monospace} b{color:#ff0}
 .done{color:#3c3} .skip{color:#f66}
</style></head><body>
<div id="bar">
 <span>#<b id="idx">1</b>/<b id="tot">0</b></span> <span id="status" style="padding:2px 10px;border-radius:4px;font-weight:bold">not reviewed</span>
 <span id="what"></span> <span>clicks: <b id="nclick">0</b>/4</span>
 <span>done <b id="ndone">0</b>/<b id="tot2">0</b></span>
 <button onclick="accept()" style="background:#286">accept machine box (a)</button>
 <button onclick="reject()" style="background:#833">machine box is WRONG (r)</button>
 <button onclick="undo()">undo (u)</button><button onclick="clearPts()">clear (c)</button>
 <button onclick="fitView();draw()">fit (f)</button><button onclick="zoomTo(JOBS[i].machine||pts,3)">zoom to box (z)</button>
 <span>zoom <b id="zoom">1.00x</b></span>
 <span style="opacity:.75">wheel = zoom, right-drag = pan | drag a point to adjust | 1-4 selects | shift+arrows nudge 1 px</span>
 <button onclick="prev()">&lt; prev</button><button onclick="next()">next &gt;</button>
 <button onclick="skipIt()" style="background:#833">board not visible (s)</button>
 <button onclick="partial()" style="background:#a60">partly visible, cannot outline (p)</button>
 <button onclick="exportJson()" style="background:#3c3;font-weight:bold">Export manual_quads.json</button>
 <span style="opacity:.75">click the PLATE EDGE (the whole 800x600 aluminium plate, white border included, TOP surface - not the printed pattern: two of its four corners are white-on-white and invisible). Order: the plate corner next to the cone first, then along the LONG edge, then the diagonal, then back. Orange = what the machine found.</span>
</div>
<div id="wrap"><canvas id="cv" width="1850" height="820"></canvas></div>
<div id="list"></div>
<script>
const JOBS=__JOBS__; const quads={}; let i=0, pts=[];
const $=id=>document.getElementById(id), cv=$('cv'), ctx=cv.getContext('2d');
let img=new Image();
// The canvas is a VIEWPORT onto the full frame: view.z scales, view.ox/oy translate. Points are stored
// in image pixels, so zooming and panning never change what gets exported.
let view={z:1,ox:0,oy:0};
function fitView(){if(!img.width)return;view.z=Math.min(cv.width/img.width,cv.height/img.height);
  view.ox=(cv.width-img.width*view.z)/2;view.oy=(cv.height-img.height*view.z)/2;}
function zoomTo(box,pad){if(!box)return;const xs=box.map(p=>p[0]),ys=box.map(p=>p[1]);
  const w=Math.max(20,Math.max(...xs)-Math.min(...xs))*pad,h=Math.max(20,Math.max(...ys)-Math.min(...ys))*pad;
  view.z=Math.min(cv.width/w,cv.height/h,12);
  view.ox=cv.width/2-(Math.min(...xs)+Math.max(...xs))/2*view.z;
  view.oy=cv.height/2-(Math.min(...ys)+Math.max(...ys))/2*view.z;draw();}
function toImg(e){const r=cv.getBoundingClientRect();
  const cx=(e.clientX-r.left)*cv.width/r.width, cy=(e.clientY-r.top)*cv.height/r.height;
  return [(cx-view.ox)/view.z,(cy-view.oy)/view.z];}
function load(){const j=JOBS[i];img=new Image();img.onload=()=>{fitView();draw();};img.src=j.file;
  pts=(quads[j.file]&&quads[j.file].pts)?quads[j.file].pts.slice():[];
  $('idx').textContent=i+1;$('tot').textContent=JOBS.length;
  $('what').textContent=`${j.cam} ${j.station}  window ${j.win[0]}-${j.win[1]}  frame ${j.clock}`
    + (j.machine?`  |  machine: ${j.machine_method} ${j.machine_corners}c`:'  |  machine: nothing')
    + (j.station.startsWith('SW')?'  |  HAND-HELD SWEEP: any corner first, then around the plate':'');
  render();showStatus();}
function draw(){const j=JOBS[i],S2I=(p)=>[p[0]*view.z+view.ox,p[1]*view.z+view.oy];
  ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#000';ctx.fillRect(0,0,cv.width,cv.height);
  ctx.imageSmoothingEnabled=view.z<1;
  ctx.drawImage(img,view.ox,view.oy,img.width*view.z,img.height*view.z);
  if(j.machine){const m=j.machine.map(S2I);ctx.lineWidth=3;ctx.strokeStyle='#ff8000';ctx.beginPath();
    ctx.moveTo(m[0][0],m[0][1]);for(let k=1;k<4;k++)ctx.lineTo(m[k][0],m[k][1]);
    ctx.closePath();ctx.stroke();ctx.fillStyle='#ff8000';ctx.font='bold 15px sans-serif';
    ctx.fillText('machine',m[0][0]+8,m[0][1]-8);}
  pts.forEach((p0,k)=>{const p=S2I(p0),sel=(k===last);ctx.strokeStyle=k===0?'#f0f':'#0f0';ctx.lineWidth=sel?3:2;
    ctx.beginPath();ctx.arc(p[0],p[1],sel?9:7,0,7);ctx.stroke();
    ctx.beginPath();ctx.moveTo(p[0]-12,p[1]);ctx.lineTo(p[0]+12,p[1]);ctx.moveTo(p[0],p[1]-12);ctx.lineTo(p[0],p[1]+12);ctx.stroke();
    ctx.fillStyle=k===0?'#f0f':'#0f0';ctx.font='bold 16px sans-serif';ctx.fillText(k===0?'cone':(k+1),p[0]+11,p[1]-8);});
  ctx.lineWidth=2;
  if(pts.length>1){const q=pts.map(S2I);ctx.strokeStyle='#f0f';ctx.beginPath();ctx.moveTo(q[0][0],q[0][1]);
    for(let k=1;k<q.length;k++)ctx.lineTo(q[k][0],q[k][1]);if(q.length===4)ctx.closePath();ctx.stroke();}
  if(hover){                                                      // magnifier: 6x image pixels around the cursor
    const Z=6,S=46,D=S*Z,hs=S2I(hover),mx=(hs[0]<cv.width/2)?cv.width-D-10:10,my=10;
    ctx.save();ctx.beginPath();ctx.rect(mx,my,D,D);ctx.clip();
    ctx.imageSmoothingEnabled=false;
    ctx.drawImage(img,hover[0]-S/2,hover[1]-S/2,S,S,mx,my,D,D);
    pts.forEach((p,k)=>{const zx=mx+(p[0]-hover[0]+S/2)*Z,zy=my+(p[1]-hover[1]+S/2)*Z;
      ctx.strokeStyle=k===0?'#f0f':'#0f0';ctx.lineWidth=2;ctx.beginPath();ctx.arc(zx,zy,7,0,7);ctx.stroke();});
    if(j.machine){const m=j.machine.map(p=>[mx+(p[0]-hover[0]+S/2)*Z,my+(p[1]-hover[1]+S/2)*Z]);
      ctx.strokeStyle='#ff8000';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(m[0][0],m[0][1]);
      for(let k=1;k<4;k++)ctx.lineTo(m[k][0],m[k][1]);ctx.closePath();ctx.stroke();}
    ctx.strokeStyle='#ff0';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(mx+D/2-16,my+D/2);ctx.lineTo(mx+D/2+16,my+D/2);
    ctx.moveTo(mx+D/2,my+D/2-16);ctx.lineTo(mx+D/2,my+D/2+16);ctx.stroke();
    ctx.restore();ctx.strokeStyle='#888';ctx.lineWidth=2;ctx.strokeRect(mx,my,D,D);}
  $('nclick').textContent=pts.length;$('zoom').textContent=view.z.toFixed(2)+'x';}
function accept(){const j=JOBS[i];if(!j.machine){alert('no machine box on this frame - click the four corners');return;}
  quads[j.file]={pts:[],skip:false,verdict:'accept'};render();next();}
function reject(){quads[JOBS[i].file]={pts:[],skip:false,verdict:'reject'};render();next();}
let drag=-1, last=-1, hover=null;
function toCv(e){const r=cv.getBoundingClientRect();
  return [(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height];}
function nearestPt(p){let bi=-1,bd=1e9;pts.forEach((q,k)=>{const d=Math.hypot(q[0]-p[0],q[1]-p[1]);if(d<bd){bd=d;bi=k;}});return [bi,bd];}
function commit(){if(pts.length===4)quads[JOBS[i].file]={pts:pts.slice(),skip:false,verdict:'operator'};}
let pan=null;
cv.addEventListener('contextmenu',e=>e.preventDefault());
cv.addEventListener('mousedown',e=>{
  if(e.button===2||e.button===1){const r=cv.getBoundingClientRect();
    pan={x:(e.clientX-r.left)*cv.width/r.width-view.ox,y:(e.clientY-r.top)*cv.height/r.height-view.oy};e.preventDefault();return;}
  const p=toImg(e);const [k,d]=nearestPt(p);
  if(pts.length&&d*view.z<=14){drag=k;last=k;draw();return;}                 // grab an existing point
  if(pts.length<4){pts.push(p);last=pts.length-1;commit();render();draw();}});
cv.addEventListener('mousemove',e=>{
  if(pan){const r=cv.getBoundingClientRect();
    view.ox=(e.clientX-r.left)*cv.width/r.width-pan.x;view.oy=(e.clientY-r.top)*cv.height/r.height-pan.y;draw();return;}
  hover=toImg(e);if(drag>=0){pts[drag]=hover;commit();}draw();});
cv.addEventListener('mouseleave',()=>{hover=null;pan=null;draw();});
cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect();
  const cx=(e.clientX-r.left)*cv.width/r.width, cy=(e.clientY-r.top)*cv.height/r.height;
  const k=e.deltaY<0?1.25:0.8, nz=Math.max(0.05,Math.min(20,view.z*k));
  view.ox=cx-(cx-view.ox)*nz/view.z;view.oy=cy-(cy-view.oy)*nz/view.z;view.z=nz;draw();},{passive:false});
window.addEventListener('mouseup',()=>{pan=null;if(drag>=0){drag=-1;render();}});
function nudge(dx,dy){if(last<0||!pts[last])return;pts[last][0]+=dx;pts[last][1]+=dy;commit();draw();render();}
function undo(){pts.pop();last=pts.length-1;delete quads[JOBS[i].file];draw();render();}
function clearPts(){pts=[];delete quads[JOBS[i].file];draw();render();}
function skipIt(){quads[JOBS[i].file]={pts:[],skip:true,verdict:'not visible'};render();next();}
// the plate IS there but its outline cannot be reconstructed (one corner showing, edges not traceable).
// Recorded separately from 'not visible' so absence is never claimed for a board that is present.
function partial(){quads[JOBS[i].file]={pts:[],skip:true,verdict:'partial'};render();next();}
function next(){if(i<JOBS.length-1){i++;load();}}
function prev(){if(i>0){i--;load();}}
const STAT={accept:['machine box ACCEPTED','#286'],reject:['machine box REJECTED','#a33'],
            operator:['LABELLED BY OPERATOR (4 corners)','#2a6cc0'],'not visible':['BOARD NOT VISIBLE','#a33'],
            partial:['BOARD PARTLY VISIBLE - cannot outline','#a60']};
function statusOf(file){const q=quads[file];
  if(!q)return ['not reviewed','#555'];
  if(q.verdict&&STAT[q.verdict])return STAT[q.verdict];
  if(q.skip)return STAT['not visible'];
  if(q.verdict&&STAT[q.verdict])return STAT[q.verdict];
  return q.pts&&q.pts.length===4?STAT.operator:['not reviewed','#555'];}
function showStatus(){const [txt,col]=statusOf(JOBS[i].file);const e=$('status');
  e.textContent=txt;e.style.background=col;
  $('ndone').textContent=JOBS.filter(j=>quads[j.file]).length;$('tot2').textContent=JOBS.length;}
function render(){showStatus();$('list').innerHTML=JOBS.map((j,k)=>{const q=quads[j.file];
  const cls=q?(q.skip||q.verdict==='reject'?'skip':'done'):'';const mark=statusOf(j.file)[0];
  return `<div class="${cls}" style="${k===i?'background:#333':''}"><a href="#" onclick="i=${k};load();return false" style="color:inherit">${j.cam} ${j.station} ${j.win[0]}-${j.win[1]}</a> ${mark}${j.machine?' [m]':''}</div>`;}).join('');
  const d=Object.values(quads).length;$('tot').textContent=JOBS.length;
  try{localStorage.setItem('manual_quads___DATE__',JSON.stringify(quads));}catch(e){}}
function exportJson(){const out=JOBS.filter(j=>quads[j.file]).map(j=>Object.assign({},j,
  {quad:quads[j.file].pts,skip:quads[j.file].skip,verdict:quads[j.file].verdict||'operator'}));
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(out,null,1));
  a.download='manual_quads.json';a.click();}
document.addEventListener('keydown',e=>{
  const step=e.shiftKey?1:0;
  if(step&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){          // shift+arrows nudge 1 px
    nudge(e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0, e.key==='ArrowUp'?-1:e.key==='ArrowDown'?1:0);
    e.preventDefault();return;}
  if(e.key==='u')undo();else if(e.key==='c')clearPts();else if(e.key==='s')skipIt();
  else if(e.key==='p')partial();
  else if(e.key==='a')accept();else if(e.key==='r')reject();
  else if(e.key>='1'&&e.key<='4'){last=+e.key-1;draw();}
  else if(e.key==='f'){fitView();draw();}
  else if(e.key==='z'){zoomTo(JOBS[i].machine||(pts.length?pts:null),3);}
  else if(e.key==='ArrowRight')next();else if(e.key==='ArrowLeft')prev();});
try{const s=localStorage.getItem('manual_quads___DATE__');if(s)Object.assign(quads,JSON.parse(s));}catch(e){}
load();
</script></body></html>"""
(OUT / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
(OUT / "manual_board_gui.html").write_text(html.replace("__JOBS__", json.dumps(jobs)).replace("__DATE__", DATE), encoding="utf-8")
print(f"\n{len(jobs)} frames to click -> {OUT / 'manual_board_gui.html'}")
