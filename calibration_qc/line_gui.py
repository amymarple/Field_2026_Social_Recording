# -*- coding: utf-8 -*-
r"""Single-file HTML GUI for labelling LINES on a calibration frame: the 13 cross cords
(x = 24..456 in; there were no cords along the length) and the foot of the wall (WALL). The operator picks a line in the side panel and
clicks along it in the image; each line is a polyline in click order. Faint dashed guides show
where the CURRENT fit (with its frame correction) puts each cord, so the operator can tell X96
from X132 - he clicks the real cord, not the guide, and the gap between them is the measurement.
The wall has no guide: its shape is what we are asking.

Why: a cord is a straight line at a known place, and every camera sees several of them end to
end. Pushed through a camera onto the ground they must come out straight and at that x (or y):
where they bend or drift, that camera's rays are wrong THERE - a continuous, model-free check
that boards at a few stations cannot give, and dense material for the frame correction. The wall
foot is the same physical curve in every camera: where two cameras' traces of it disagree, so
does their calibration, in a place no board was ever put.

Usage: python line_gui.py CHxx HH:MM:SS [--session <dir|date>] [--half]
       -> <qc>\line_gui_CHxx.html ; Export -> line_labels_CHxx.json (full-res UPRIGHT px)
The frame is embedded at full resolution (a cord is one pixel wide); --half embeds it at half.
"""
import sys, json, base64, subprocess
from pathlib import Path
from datetime import datetime
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402
FFMPEG = "E:/Reolink_record/bin/ffmpeg.exe"; FFPROBE = "E:/Reolink_record/bin/ffprobe.exe"
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess)
cam, clock = args[0], args[1]
PANO = cam in ("CH01", "CH02")
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
XS = sorted(TRAIN_X + VT_X); YS = sorted(TRAIN_Y + VT_Y)
# Only the 13 cross cords exist on the ground (x = 24..456 in, each running across the paddock);
# the y positions were tick marks along them, there were never cords along the length
# (operator, 2026-09-23). So: the 13 cords, and the foot of the wall.
LINES = [f"X{x}" for x in XS] + ["WALL"]

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
H, W = up.shape[:2]
scale = 0.5 if "--half" in args else 1.0
small = up if scale == 1.0 else cv2.resize(up, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80]); b64 = base64.b64encode(jpg).decode()

# guides: where the current fit (frame-corrected) puts each cord, as image polylines (full-res upright px)
guides = {}
try:
    import paddock_map as pm
    c = pm.load()[cam]
    for x0 in XS:
        pts = np.array([[x0, y] for y in np.arange(0, 240.1, 2.0)])
        uv = c.to_paddock_inv(pts, z_mm=0.0, units="in"); vis = c.sees(pts, units="in", margin=-100)
        seg_pts = [[round(float(u), 1), round(float(v), 1)] for (u, v), ok_ in zip(uv, vis) if ok_ and np.isfinite(u) and np.isfinite(v)]
        if len(seg_pts) > 1: guides[f"X{x0}"] = seg_pts
except Exception as e:                                                   # no fit yet: no guides
    print(f"[line_gui] no guides ({e})")

html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Line labelling __CAM__</title>
<style>
 body{margin:0;font-family:Arial,sans-serif;font-size:14px;display:flex;flex-direction:column;height:100vh}
 #top{padding:6px 10px;background:#222;color:#eee;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 button{font-size:14px;padding:4px 10px}
 #main{display:flex;flex:1;min-height:0}
 #imgwrap{flex:1;overflow:auto;position:relative;background:#111}
 #stage{position:relative;transform-origin:0 0} #stage img{display:block} #ov{position:absolute;left:0;top:0}
 #side{width:300px;padding:8px;overflow:auto;border-left:2px solid #444;background:#f4f4f4}
 .ln{display:block;width:100%;text-align:left;margin:2px 0;padding:4px 8px;border:2px solid #ccc;background:#fff;cursor:pointer}
 .ln.cur{border-color:#000;font-weight:bold} .ln .n{float:right;color:#666}
 textarea{width:100%;height:100px;font:11px monospace}
</style></head><body>
<div id="top"><b>__CAM__ @ __CLOCK__</b>
 <span>line: <b id="curinfo">none</b></span>
 <button onclick="undo()">undo last point (u)</button>
 <button onclick="clearLine()">clear this line</button>
 <span>zoom <button onclick="zoom(0.25)">25%</button><button onclick="zoom(0.5)">50%</button><button onclick="zoom(1)">100%</button><button onclick="zoom(2)">200%</button></span>
 <label><input type="checkbox" id="showg" checked onchange="draw()"> guides (dashed = where the current fit expects each cord)</label>
 <button onclick="exportJSON()" style="background:#3c3;font-weight:bold">Export JSON</button>
 <span id="stat"></span></div>
<div id="main">
 <div id="imgwrap"><div id="stage"><img id="img" src="data:image/jpeg;base64,__B64__"><svg id="ov"></svg></div></div>
 <div id="side">
  <b>1. pick a line &nbsp; 2. click along it in the image</b><br>
  <small>Click ON the cord (the thin line on the grass), every 0.5-1 m, wall to wall, as far as you can see it. The dashed guide only tells you which cord is which - if the real cord is beside the guide, click the real cord. WALL = the FOOT of the wall, where the sheet meets the ground. <b>Drag</b> a point to adjust it; <b>right-click</b> a point to delete it. The magnifier shows 4x around the cursor. Points are kept in this browser between visits.</small>
  <canvas id="mag" width="240" height="240" style="display:block;margin:6px 0;border:1px solid #888"></canvas>
  <div id="list"></div>
  <b>Export</b> (also copied here) / paste an earlier export here and <button onclick="loadJSON()">Load</button>:<br><textarea id="out"></textarea>
 </div></div>
<script>
const CAM="__CAM__", S=__SCALE__, IMGW=__IMGW__, IMGH=__IMGH__, LINES=__LINES__, GUIDES=__GUIDES__;
const COL={};LINES.forEach((l,i)=>{COL[l]=l==='WALL'?'#ff3030':(l[0]==='X'?`hsl(${(i*37)%360},90%,55%)`:`hsl(${(i*53+180)%360},90%,60%)`);});
let lines={}; LINES.forEach(l=>lines[l]=[]); let cur=null, z=0.5;
const ov=document.getElementById('ov'), stage=document.getElementById('stage');
function zoom(f){z=f;stage.style.transform='scale('+z+')';stage.style.width=IMGW+'px';stage.style.height=IMGH+'px';}
function draw(){ov.setAttribute('width',IMGW);ov.setAttribute('height',IMGH);let h='';
  if(document.getElementById('showg').checked){for(const [id,g] of Object.entries(GUIDES)){
    const d=g.map((p,i)=>(i?'L':'M')+(p[0]*S).toFixed(1)+' '+(p[1]*S).toFixed(1)).join(' ');
    h+=`<path d="${d}" fill="none" stroke="${COL[id]}" stroke-width="2" stroke-dasharray="14 10" opacity="0.55"/>`;
    const m=g[Math.floor(g.length/2)];h+=`<text x="${m[0]*S+6}" y="${m[1]*S-6}" font="bold 20px Arial" font-size="22" font-weight="bold" fill="${COL[id]}" stroke="#000" stroke-width="4" paint-order="stroke">${id}</text>`;}}
  for(const [id,pts] of Object.entries(lines)){if(!pts.length)continue;
    if(pts.length>1){const d=pts.map((p,i)=>(i?'L':'M')+(p[0]*S).toFixed(1)+' '+(p[1]*S).toFixed(1)).join(' ');
      h+=`<path d="${d}" fill="none" stroke="${COL[id]}" stroke-width="${id===cur?4:2.5}"/>`;}
    pts.forEach((p,i)=>{h+=`<circle cx="${p[0]*S}" cy="${p[1]*S}" r="${id===cur?9:6}" fill="none" stroke="${COL[id]}" stroke-width="3"/>`;});
    const p=pts[pts.length-1];h+=`<text x="${p[0]*S+10}" y="${p[1]*S+8}" font-size="24" font-weight="bold" fill="${COL[id]}" stroke="#000" stroke-width="5" paint-order="stroke">${id}</text>`;}
  ov.innerHTML=h;list();}
function list(){const L=document.getElementById('list');L.innerHTML=LINES.map(l=>`<button class="ln${l===cur?' cur':''}" style="border-left:12px solid ${COL[l]}" onclick="pick('${l}')">${l}<span class="n">${lines[l].length} pts</span></button>`).join('');
  document.getElementById('curinfo').textContent=cur||'none';
  document.getElementById('stat').textContent=Object.values(lines).reduce((a,b)=>a+b.length,0)+' points on '+Object.values(lines).filter(v=>v.length).length+' lines';}
function pick(l){cur=l;draw();}
// left-drag moves a point, left-click on grass adds one to the current line, right-click on a point deletes it
function toImg(e){const r=ov.getBoundingClientRect();return [(e.clientX-r.left)/z/S,(e.clientY-r.top)/z/S];}
function hit(x,y){for(const [id,pts] of Object.entries(lines)){for(let i=0;i<pts.length;i++){if(Math.hypot(pts[i][0]-x,pts[i][1]-y)*S*z<12)return [id,i];}}return null;}
let drag=null, hover=null;
ov.addEventListener('contextmenu',e=>{e.preventDefault();const [x,y]=toImg(e);const h=hit(x,y);if(h){lines[h[0]].splice(h[1],1);draw();}});
ov.addEventListener('mousedown',e=>{if(e.button!==0)return;const [x,y]=toImg(e);const h=hit(x,y);
  if(h){drag={id:h[0],i:h[1],moved:false};cur=h[0];draw();return;}
  if(!cur){alert('pick a line first (right panel)');return;}
  lines[cur].push([Math.round(x*10)/10,Math.round(y*10)/10]);drag={id:cur,i:lines[cur].length-1,moved:false};draw();});
ov.addEventListener('mousemove',e=>{const [x,y]=toImg(e);hover=[x,y];
  if(drag){lines[drag.id][drag.i]=[Math.round(x*10)/10,Math.round(y*10)/10];drag.moved=true;draw();}else mag();});
window.addEventListener('mouseup',()=>{if(drag){drag=null;draw();}});
ov.addEventListener('mouseleave',()=>{hover=null;mag();});
function undo(){if(cur&&lines[cur].length){lines[cur].pop();draw();}}
function clearLine(){if(cur&&confirm('clear all points of '+cur+'?')){lines[cur]=[];draw();}}
document.addEventListener('keydown',e=>{if(e.key==='u')undo();});
// magnifier: 4x around the cursor, with the points, so a click can be put on the cord itself
const mg=document.getElementById('mag'), mctx=mg.getContext('2d'), im=document.getElementById('img');
function mag(){if(!hover||!im.complete){mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);return;}
  const Z=4,Sz=mg.width/Z,cx=hover[0]*S,cy=hover[1]*S;mctx.imageSmoothingEnabled=false;
  mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);
  mctx.drawImage(im,cx-Sz/2,cy-Sz/2,Sz,Sz,0,0,mg.width,mg.height);
  for(const [id,pts] of Object.entries(lines))for(const p of pts){const px=(p[0]*S-cx+Sz/2)*Z,py=(p[1]*S-cy+Sz/2)*Z;
    if(px>=0&&px<=mg.width&&py>=0&&py<=mg.height){mctx.strokeStyle=COL[id];mctx.lineWidth=2;mctx.beginPath();mctx.arc(px,py,8,0,7);mctx.stroke();}}
  mctx.strokeStyle='#ff0';mctx.lineWidth=1;mctx.beginPath();mctx.moveTo(mg.width/2-14,mg.height/2);mctx.lineTo(mg.width/2+14,mg.height/2);
  mctx.moveTo(mg.width/2,mg.height/2-14);mctx.lineTo(mg.width/2,mg.height/2+14);mctx.stroke();}
// autosave in this browser, and import of an earlier export (paste into the box, then Load)
const KEY='line_labels_'+CAM+'_'+"__CLOCK__";
const _draw=draw;draw=function(){_draw();try{localStorage.setItem(KEY,JSON.stringify(lines));}catch(e){}};
function loadJSON(){try{const d=JSON.parse(document.getElementById('out').value);const L=d.lines||d;
  for(const [id,pts] of Object.entries(L)) if(lines[id]!==undefined) lines[id]=pts.map(p=>[+p[0],+p[1]]);draw();}catch(e){alert('not valid JSON: '+e);}}
function exportJSON(){const out={};for(const [id,pts] of Object.entries(lines)) if(pts.length) out[id]=pts;
  const data={camera:CAM,clock:"__CLOCK__",frame_size_upright:[IMGW/S,IMGH/S],lines:out};
  const txt=JSON.stringify(data);document.getElementById('out').value=txt;
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(txt);a.download='line_labels_'+CAM+'.json';a.click();}
try{const s=localStorage.getItem(KEY);if(s){const L=JSON.parse(s);for(const [id,pts] of Object.entries(L)) if(lines[id]!==undefined) lines[id]=pts;}}catch(e){}
zoom(0.5);draw();
</script></body></html>"""
html = (html.replace("__CAM__", cam).replace("__CLOCK__", clock).replace("__B64__", b64)
        .replace("__SCALE__", repr(scale)).replace("__IMGW__", str(small.shape[1])).replace("__IMGH__", str(small.shape[0]))
        .replace("__LINES__", json.dumps(LINES)).replace("__GUIDES__", json.dumps(guides)))
out = QC / f"line_gui_{cam}.html"; out.write_text(html, encoding="utf-8")
print(f"{cam}: {len(guides)} cord guides -> {out} ({out.stat().st_size // 1024} KB)")
