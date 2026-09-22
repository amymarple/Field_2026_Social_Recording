# -*- coding: utf-8 -*-
r"""GUI for the placements the automatic detector cannot find: the operator clicks the board's four
outline corners on one frame, the detector then decodes the whole window from that hint.

For every (timeline window x camera) with fewer than --min-frames cached detections, one frame from
the middle of the window is rendered (pano cameras upright, cropped around the expected board
position). The page shows them one by one; click the four OUTLINE corners of the white board in
order, starting at the corner that sits ON THE CONE and going around the long edge first
(cone corner -> along the long edge -> diagonal -> back). "Skip" marks a frame as 'board not
visible'. Export writes manual_quads.json next to the frames; feed it to
  python manual_boards.py [--session ...]
which re-runs the detector with each quad as the board hint and caches the corners like the
automatic path.
--mode picks which windows to show:
  missing  (default) only windows with no cached detection at all;
  located  those plus the windows where the board was only LOCATED, not decoded - the machine's
           outline is drawn on the frame so the operator can accept it (key a) or re-click it;
  all      every window, including the decoded ones, for a full audit.
Usage: python manual_board_gui.py [--session <dir|date>] [--mode missing|located|all] [--cams CH01,CH02]
Output: <qc>\manual\  (frames + manual_board_gui.html)
"""
import sys, re, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = r"E:\Reolink_record\bin\ffmpeg.exe"; FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
CAMS = opt("--cams", "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
MODE = opt("--mode", "missing")
MIN_FRAMES = int(opt("--min-frames", "1"))
OUT = QC / "manual"; OUT.mkdir(parents=True, exist_ok=True)
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
LATTICE = {f"T{li}{si}": (x, y) for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)}
LATTICE.update({f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}": (x, y) for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)})
SW = 2160

def clk(s): return datetime.strptime(f"{DATE} {s}", "%Y-%m-%d %H:%M:%S")
wins = []
for ln in (QC / "placement_timeline.txt").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*(\d\d:\d\d:\d\d)-(\d\d:\d\d:\d\d)\s+(\S+)", ln)
    if m:
        a, b = clk(m.group(1)), clk(m.group(2)); wins.append([min(a, b), max(a, b), m.group(3).upper()])
merged = []
for w in sorted(wins, key=lambda w: w[0]):
    same = next((c for c in merged if c[2] == w[2] and w[0] <= c[1] + timedelta(seconds=1) and w[1] >= c[0] - timedelta(seconds=1)), None)
    if same: same[0], same[1] = min(same[0], w[0]), max(same[1], w[1])
    else: merged.append(list(w))
wins = merged

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
    lp = qc_paths.cone_labels(QC, cam)
    if lp is None: return {}
    lab = json.load(open(lp, encoding="utf-8"))
    return {q["station"].upper(): np.array([q["x"], q["y"]], float)            # UPRIGHT coords
            for q in lab["points"] if q.get("station") and q["station"].upper() in LATTICE}

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
for cam in CAMS:
    pano = cam in ("CH01", "CH02")
    cones = cone_map(cam) if pano else {}
    have = cached(cam)
    for a, b, st in wins:
        inwin = [r for r in have if a <= r[0] <= b]
        decoded = [r for r in inwin if r[1] >= 12]
        if MODE == "missing" and len(inwin) >= MIN_FRAMES:
            continue
        if MODE == "located" and decoded:
            continue
        best = max(inwin, key=lambda r: (r[1], r[3] is not None)) if inwin else None
        mid = best[0] if (best and best[3] is not None) else a + (b - a) / 2
        seg, seg_start = seg_for(cam, mid)
        if seg is None:
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
        machine = None
        if best is not None and best[3] is not None:                       # machine outline, stored -> upright
            q = best[3]
            machine = np.stack([q[:, 1], (SW - 1) - q[:, 0]], 1) if pano else q
        if pano:
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
            for name, p in cones.items():                                   # cone labels inside the crop
                if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                    cv2.circle(img, tuple(int(v) for v in p), 10, (0, 255, 255), 2)
                    cv2.putText(img, name, (int(p[0]) + 12, int(p[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            img = img[y0:y1, x0:x1]
        scale = 1.0
        if max(img.shape[:2]) > 1400:
            scale = 1400 / max(img.shape[:2]); img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        name = f"{cam}_{st}_{mid.strftime('%H%M%S')}.jpg"
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
 canvas{cursor:crosshair;max-width:100%} #list{padding:8px;font:12px monospace} b{color:#ff0}
 .done{color:#3c3} .skip{color:#f66}
</style></head><body>
<div id="bar">
 <span>#<b id="idx">1</b>/<b id="tot">0</b></span> <span id="what"></span>
 <span>clicks: <b id="nclick">0</b>/4</span>
 <button onclick="accept()" style="background:#286">accept machine box (a)</button>
 <button onclick="reject()" style="background:#833">machine box is WRONG (r)</button>
 <button onclick="undo()">undo click (u)</button><button onclick="clearPts()">clear (c)</button>
 <button onclick="prev()">&lt; prev</button><button onclick="next()">next &gt;</button>
 <button onclick="skipIt()" style="background:#833">board not visible (s)</button>
 <button onclick="exportJson()" style="background:#3c3;font-weight:bold">Export manual_quads.json</button>
 <span style="opacity:.75">click the PLATE EDGE (the whole 800x600 aluminium plate, white border included, TOP surface - not the printed pattern: two of its four corners are white-on-white and invisible). Order: the plate corner next to the cone first, then along the LONG edge, then the diagonal, then back. Orange = what the machine found.</span>
</div>
<div id="wrap"><canvas id="cv"></canvas></div>
<div id="list"></div>
<script>
const JOBS=__JOBS__; const quads={}; let i=0, pts=[];
const $=id=>document.getElementById(id), cv=$('cv'), ctx=cv.getContext('2d');
let img=new Image();
function load(){const j=JOBS[i];img=new Image();img.onload=()=>{cv.width=img.width;cv.height=img.height;draw();};img.src=j.file;
  pts=(quads[j.file]&&quads[j.file].pts)?quads[j.file].pts.slice():[];
  $('idx').textContent=i+1;$('tot').textContent=JOBS.length;
  $('what').textContent=`${j.cam} ${j.station}  window ${j.win[0]}-${j.win[1]}  frame ${j.clock}`
    + (j.machine?`  |  machine: ${j.machine_method} ${j.machine_corners}c`:'  |  machine: nothing');
  render();}
function draw(){ctx.drawImage(img,0,0);const j=JOBS[i];
  if(j.machine){ctx.lineWidth=3;ctx.strokeStyle='#ff8000';ctx.beginPath();
    ctx.moveTo(j.machine[0][0],j.machine[0][1]);for(let k=1;k<4;k++)ctx.lineTo(j.machine[k][0],j.machine[k][1]);
    ctx.closePath();ctx.stroke();ctx.fillStyle='#ff8000';ctx.font='bold 15px sans-serif';
    ctx.fillText('machine',j.machine[0][0]+8,j.machine[0][1]-8);}
  ctx.lineWidth=2;
  pts.forEach((p,k)=>{ctx.strokeStyle=k===0?'#f0f':'#0f0';ctx.beginPath();ctx.arc(p[0],p[1],7,0,7);ctx.stroke();
    ctx.fillStyle=k===0?'#f0f':'#0f0';ctx.font='bold 16px sans-serif';ctx.fillText(k===0?'cone':(k+1),p[0]+9,p[1]-6);});
  if(pts.length>1){ctx.strokeStyle='#f0f';ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
    for(let k=1;k<pts.length;k++)ctx.lineTo(pts[k][0],pts[k][1]);if(pts.length===4)ctx.closePath();ctx.stroke();}
  $('nclick').textContent=pts.length;}
function accept(){const j=JOBS[i];if(!j.machine){alert('no machine box on this frame - click the four corners');return;}
  quads[j.file]={pts:[],skip:false,verdict:'accept'};render();next();}
function reject(){quads[JOBS[i].file]={pts:[],skip:false,verdict:'reject'};render();next();}
cv.addEventListener('click',e=>{const r=cv.getBoundingClientRect();const sx=cv.width/r.width;
  if(pts.length>=4)return;pts.push([(e.clientX-r.left)*sx,(e.clientY-r.top)*sx]);
  if(pts.length===4){quads[JOBS[i].file]={pts:pts.slice(),skip:false,verdict:'operator'};render();}
  draw();});
function undo(){pts.pop();delete quads[JOBS[i].file];draw();render();}
function clearPts(){pts=[];delete quads[JOBS[i].file];draw();render();}
function skipIt(){quads[JOBS[i].file]={pts:[],skip:true,verdict:'not visible'};render();next();}
function next(){if(i<JOBS.length-1){i++;load();}}
function prev(){if(i>0){i--;load();}}
function render(){$('list').innerHTML=JOBS.map((j,k)=>{const q=quads[j.file];
  const cls=q?(q.skip||q.verdict==='reject'?'skip':'done'):'';const mark=q?(q.verdict||'4 corners'):'-';
  return `<div class="${cls}" style="${k===i?'background:#333':''}"><a href="#" onclick="i=${k};load();return false" style="color:inherit">${j.cam} ${j.station} ${j.win[0]}-${j.win[1]}</a> ${mark}${j.machine?' [m]':''}</div>`;}).join('');
  const d=Object.values(quads).length;$('tot').textContent=JOBS.length;
  try{localStorage.setItem('manual_quads___DATE__',JSON.stringify(quads));}catch(e){}}
function exportJson(){const out=JOBS.filter(j=>quads[j.file]).map(j=>Object.assign({},j,
  {quad:quads[j.file].pts,skip:quads[j.file].skip,verdict:quads[j.file].verdict||'operator'}));
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(out,null,1));
  a.download='manual_quads.json';a.click();}
document.addEventListener('keydown',e=>{if(e.key==='u')undo();else if(e.key==='c')clearPts();else if(e.key==='s')skipIt();
  else if(e.key==='a')accept();else if(e.key==='r')reject();
  else if(e.key==='ArrowRight')next();else if(e.key==='ArrowLeft')prev();});
try{const s=localStorage.getItem('manual_quads___DATE__');if(s)Object.assign(quads,JSON.parse(s));}catch(e){}
load();
</script></body></html>"""
(OUT / "manual_board_gui.html").write_text(html.replace("__JOBS__", json.dumps(jobs)).replace("__DATE__", DATE), encoding="utf-8")
print(f"\n{len(jobs)} frames to click -> {OUT / 'manual_board_gui.html'}")
