# -*- coding: utf-8 -*-
"""Build a single-file HTML GUI for labelling cones: click a cone in the pano (or click empty grass
to add a missed cone), then click its station on the field map or type the ID. Export = JSON.
Usage: python cone_gui.py CHxx HH:MM:SS [--session <dir|date>]   -> <qc>/cone_gui_CHxx.html
Any camera: the panos are shown upright (rotated), the ordinary lenses as stored. The candidate
points come from cones_CHxx.csv when the cone detector has been run for that camera; otherwise the
page starts empty and every cone is added by clicking it. Coordinates are exported in the full
UPRIGHT frame (frame_size_upright), which is what qc_paths.load_cones expects."""
import sys, csv, json, base64, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
FFMPEG = r"E:/Reolink_record/bin/ffmpeg.exe"; FFPROBE = r"E:/Reolink_record/bin/ffprobe.exe"
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess)
cam, clock = args[0], args[1]
PANO = cam in ("CH01", "CH02")
DISPLAY_W = 3840          # embedded image width (px); clicks are scaled back to full-res upright coords
t = datetime.strptime(clock, "%H:%M:%S"); seg = off = None
for s in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
    a = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
    b = datetime.strptime(s.name.split("_")[1] + " " + s.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
    if a.time() <= t.time() <= b.time(): seg, off = s, (datetime.combine(a.date(), t.time()) - a).total_seconds()
if seg is None:
    sys.exit(f"no closed {cam} segment covers {clock}")
w, h = [int(v) for v in subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                 "stream=width,height", "-of", "csv=p=0", str(seg)]).decode().strip().split(",")[:2]]
buf = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{off:.1f}", "-i", str(seg), "-frames:v", "1", "-f", "rawvideo",
                      "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
up = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE) if PANO else img.copy()
H, W = up.shape[:2]; scale = DISPLAY_W / W
small = cv2.resize(up, (DISPLAY_W, int(H * scale)), interpolation=cv2.INTER_AREA)
ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 74]); b64 = base64.b64encode(jpg).decode()
cand = QC / f"cones_{cam}.csv"
points = ([dict(idx=int(c["idx"]), x=float(c["upright_x"]), y=float(c["upright_y"]), station=c["station"] or "")
           for c in csv.DictReader(open(cand, encoding="utf-8"))] if cand.exists() else [])
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
stations = [dict(id=f"T{li}{si}", x=x, y=y, set="T") for li, x in enumerate(TRAIN_X, 1) for si, y in enumerate(TRAIN_Y, 1)]
stations += [dict(id=f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}", x=x, y=y, set="V" if (i + j) % 2 == 0 else "F")
             for i, x in enumerate(VT_X, 1) for j, y in enumerate(VT_Y, 1)]
html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Cone labelling __CAM__</title>
<style>
 body{margin:0;font-family:Arial,sans-serif;font-size:14px;display:flex;flex-direction:column;height:100vh}
 #top{padding:6px 10px;background:#222;color:#eee;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 #top input{font-size:16px;width:70px} button{font-size:14px;padding:4px 10px}
 #main{display:flex;flex:1;min-height:0}
 #imgwrap{flex:1;overflow:auto;position:relative;background:#111}
 #stage{position:relative;transform-origin:0 0}
 #stage img{display:block}
 #ov{position:absolute;left:0;top:0}
 #side{width:520px;padding:8px;overflow:auto;border-left:2px solid #444;background:#f4f4f4}
 .pt{cursor:pointer} .lab{font:bold 22px Arial;paint-order:stroke;stroke:#000;stroke-width:5px;fill:#ff0;pointer-events:none}
 .sel{stroke:#0f0!important;stroke-width:5px!important}
 #map circle{cursor:pointer} #map text{font:11px Arial;pointer-events:none}
 textarea{width:100%;height:120px;font:12px monospace}
</style></head><body>
<div id="top"><b>__CAM__ @ __CLOCK__</b>
 <span>selected: <b id="selinfo">none</b></span>
 <label>ID <input id="idbox" placeholder="T34"></label>
 <button onclick="setNone()">not a cone (NONE)</button>
 <button onclick="delSel()">delete point</button>
 <span>zoom <button onclick="zoom(0.5)">50%</button><button onclick="zoom(0.75)">75%</button><button onclick="zoom(1)">100%</button><button onclick="zoom(1.5)">150%</button></span>
 <button onclick="exportJSON()" style="background:#3c3;font-weight:bold">Export JSON</button>
 <span id="stat"></span></div>
<div id="main">
 <div id="imgwrap"><div id="stage"><img id="img" src="data:image/jpeg;base64,__B64__"><svg id="ov"></svg></div></div>
 <div id="side">
  <b>Field map: click a station to assign it to the selected cone</b> (green = assigned, grey = free). x → right, y → up.<br>
  <svg id="map" width="500" height="270" viewBox="-10 -10 500 260"></svg>
  <p>Click a circled cone in the image to select it, then click its station here or type the ID + Enter.<br>
  Click bare grass to <b>add a missed cone</b> (new number). Delete/NONE for false positives.</p>
  <b>Export</b> (also copied into the box):<br><textarea id="out"></textarea>
 </div></div>
<script>
const CAM="__CAM__", S=__SCALE__, IMGW=__IMGW__, IMGH=__IMGH__;
let pts=__POINTS__, stations=__STATIONS__, sel=null, z=0.5, nextIdx=Math.max(0,...pts.map(p=>p.idx))+1;
const ov=document.getElementById('ov'), img=document.getElementById('img'), stage=document.getElementById('stage');
function zoom(f){z=f;stage.style.transform='scale('+z+')';stage.style.width=IMGW+'px';stage.style.height=IMGH+'px';}
function draw(){
  ov.setAttribute('width',IMGW);ov.setAttribute('height',IMGH);
  let h='';
  for(const p of pts){const x=p.x*S,y=p.y*S;const col=p.station==='NONE'?'#f00':(p.station?'#0c0':'#fff');
    h+=`<circle class="pt${p===sel?' sel':''}" cx="${x}" cy="${y}" r="16" fill="none" stroke="${col}" stroke-width="3" data-i="${p.idx}"></circle>`;
    h+=`<text class="lab" x="${x+18}" y="${y-8}">${p.idx}${p.station?' '+p.station:''}</text>`;}
  ov.innerHTML=h;
  for(const c of ov.querySelectorAll('circle')) c.onclick=e=>{e.stopPropagation();select(pts.find(q=>q.idx==c.dataset.i));};
  drawMap();document.getElementById('stat').textContent=pts.filter(p=>p.station&&p.station!=='NONE').length+' labelled / '+pts.length+' points';
}
function drawMap(){const m=document.getElementById('map');let h=`<rect x="0" y="0" width="480" height="240" fill="#fff" stroke="#000"/>`;
  const used={};for(const p of pts) if(p.station&&p.station!=='NONE') used[p.station]=p.idx;
  for(const s of stations){const x=s.x,y=240-s.y;const a=used[s.id]!==undefined;
    h+=`<circle cx="${x}" cy="${y}" r="7" fill="${a?'#8e8':'#ddd'}" stroke="${s.set==='T'?'#000':(s.set==='V'?'#06c':'#c00')}" data-s="${s.id}"><title>${s.id}${a?' = cone '+used[s.id]:''}</title></circle>`;
    h+=`<text x="${x}" y="${y-9}" text-anchor="middle">${s.id}</text>`;}
  m.innerHTML=h;for(const c of m.querySelectorAll('circle')) c.onclick=()=>assign(c.dataset.s);}
function select(p){sel=p;document.getElementById('selinfo').textContent=p?('#'+p.idx+(p.station?' = '+p.station:'')):'none';document.getElementById('idbox').value=p&&p.station!=='NONE'?p.station:'';draw();document.getElementById('idbox').focus();}
function assign(id){if(!sel) return;id=id.trim().toUpperCase();for(const p of pts) if(p!==sel&&p.station===id) p.station='';sel.station=id;draw();}
function setNone(){if(sel){sel.station='NONE';draw();}}
function delSel(){if(sel){pts=pts.filter(p=>p!==sel);sel=null;draw();}}
ov.onclick=e=>{const r=ov.getBoundingClientRect();const x=(e.clientX-r.left)/z/S,y=(e.clientY-r.top)/z/S;
  let best=null,bd=1e9;for(const p of pts){const d=Math.hypot(p.x-x,p.y-y);if(d<bd){bd=d;best=p;}}
  if(best&&bd*S<30){select(best);return;}
  const p={idx:nextIdx++,x:x,y:y,station:''};pts.push(p);select(p);};
document.getElementById('idbox').addEventListener('keydown',e=>{if(e.key==='Enter'){assign(e.target.value);}});
function exportJSON(){const data={camera:CAM,clock:"__CLOCK__",frame_size_upright:[__IMGW__/S,__IMGH__/S],points:pts};
  const txt=JSON.stringify(data,null,1);document.getElementById('out').value=txt;
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(txt);a.download='cone_labels_'+CAM+'.json';a.click();}
zoom(0.5);draw();
</script></body></html>"""
html = (html.replace("__CAM__", cam).replace("__CLOCK__", clock).replace("__B64__", b64)
        .replace("__SCALE__", repr(scale)).replace("__IMGW__", str(small.shape[1])).replace("__IMGH__", str(small.shape[0]))
        .replace("__POINTS__", json.dumps(points)).replace("__STATIONS__", json.dumps(stations)))
out = QC / f"cone_gui_{cam}.html"; out.write_text(html, encoding="utf-8")
print(f"{cam}: {len(points)} points -> {out} ({out.stat().st_size // 1024} KB)")
