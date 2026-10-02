# -*- coding: utf-8 -*-
r"""Review page for the ~20 Hz ball tracks (ball_track20.py): every searched frame of every camera, the ball's
neighbourhood at full resolution with the detected ellipse, played or stepped; the operator flags wrong and
missed detections.

Frames are decoded exactly as ball_track20.py did (same segment, seek, grab order, pano rotation) and paired with
the track file entry by entry (their times must agree to 1 ms; mismatches are counted and reported). For each
frame the track searched, a square crop around the detection (or, where nothing was found, around the nearest
detection within 1 s) is saved at 360 px; its side is 6 x the predicted ball radius (300-900 px of the frame).

Page: camera buttons; the crop with the ellipse (toggle d); left / right one frame, up / down 20 frames, space
plays at 20 fps (speed 0.25-4x); b = this detection is wrong (not the ball, or off the ball), m = the ball is there
but was not detected, c = clear the flag, f = next flagged frame, n = next frame without a detection. Flags live
in this browser; Export writes ball20_flags.json.

Usage: python ball20_gui.py [--cams CH01,...] [--ball <qc ball dir>] [--session <09-30 dir>] [--html-only]
Output: <ball dir>\track20\gui\<CAM>\<CAM>_<nnnnn>.jpg, index_<CAM>.json, ball20_review.html
"""
import sys, json, time
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
BALL = Path(opt("--ball", str(qc_paths.QC_ROOT / "2026-09-30" / "ball")))
SESSION = Path(opt("--session", r"F:\calibration\session_2026-09-30_15-49-39"))
TR = BALL / "track20"; OUT = TR / "gui"; OUT.mkdir(exist_ok=True)
jobs = json.loads((BALL / "jobs.json").read_text(encoding="utf-8"))
CAMS = opt("--cams", "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
SIDE = 360
NT, STEP = len(jobs["clocks"]), float(jobs["step"])


def build(cam):
    d = json.loads((TR / f"ball20_{cam}.json").read_text(encoding="utf-8"))
    fr, off_grid = d["frames"], float(d["grid_off_s"])
    job = next(c for c in jobs["cams"] if c["cam"] == cam)
    W, H, pano, off = job["w"], job["h"], job["pano"], float(job["offset_s"]) + off_grid
    start = datetime.strptime(f"{jobs['date']} {job['file_start']}", "%Y-%m-%d %H:%M:%S")
    dets = [(f[0], f[3]) for f in fr if f[3]]
    dt_ = np.array([t for t, _ in dets])
    (OUT / cam).mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(SESSION / job["file"]))
    cap.set(cv2.CAP_PROP_POS_MSEC, (off - 1.5) * 1000)
    n, index, mism, t0 = 0, [], 0, time.time()
    while n < len(fr):
        if not cap.grab():
            break
        t_file = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        t = t_file - off
        if t < -1.0:
            continue
        e = fr[n]; n += 1
        if abs(e[0] - round(t, 4)) > 1e-3:
            mism += 1
        if not e[2]:                                                    # not searched (operator: out of view)
            continue
        det = e[3]
        if det:
            c, r = (det["cx"], det["cy"]), det["r_pred"]
        else:
            if not len(dt_):
                continue
            j = int(np.argmin(np.abs(dt_ - e[0])))
            if abs(dt_[j] - e[0]) > 1.0:
                continue
            c, r = (dets[j][1]["cx"], dets[j][1]["cy"]), dets[j][1]["r_pred"]
        ok, img = cap.retrieve()
        if not ok:
            break
        if pano:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        s = int(np.clip(6 * r, 300, 900))
        x0 = int(np.clip(c[0] - s / 2, 0, W - s)); y0 = int(np.clip(c[1] - s / 2, 0, H - s))
        crop = cv2.resize(img[y0:y0 + s, x0:x0 + s], (SIDE, SIDE), interpolation=cv2.INTER_AREA)
        name = f"{cam}_{n - 1:05d}.jpg"
        cv2.imwrite(str(OUT / cam / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        k = SIDE / s
        ent = dict(i=n - 1, t=e[0], tf=e[1], clock=(start + timedelta(seconds=e[1])).strftime("%H:%M:%S.%f")[:-4],
                   src=e[2], img=f"{cam}/{name}", x0=x0, y0=y0, s=s)
        if det:
            ent["ell"] = [round((det["cx"] - x0) * k, 1), round((det["cy"] - y0) * k, 1), round(det["a"] * k, 1),
                          round(det["b"] * k, 1), det["th"]]
            ent["conf"], ent["white"] = det["conf"], det["white"]
        index.append(ent)
        if len(index) % 500 == 0:
            print(f"{cam}: {len(index)} crops, t {t:6.1f} s, {time.time() - t0:.0f} s", flush=True)
    (OUT / f"index_{cam}.json").write_text(json.dumps(dict(cam=cam, file=job["file"], n_track=len(fr), mismatched_times=mism,
                                                           frames=index)), encoding="utf-8")
    print(f"{cam}: done - {len(index)} crops ({sum(1 for x in index if 'ell' in x)} with a detection), "
          f"time mismatches vs the track file: {mism}, {time.time() - t0:.0f} s", flush=True)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Ball 20 Hz review</title>
<style>
 body{margin:0;background:#1b1b1b;color:#eee;font-family:Arial,sans-serif;font-size:14px}
 #bar{position:sticky;top:0;background:#2a2a2a;padding:6px 8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;z-index:5}
 button{font-size:13px;padding:3px 9px} button.on{outline:2px solid #ff0} b{color:#ff0}
 #wrap{display:flex;gap:12px;padding:8px;flex-wrap:wrap}
 canvas{background:#000} #side{min-width:260px;line-height:1.6}
 #slider{width:min(900px,90vw)} .flag{padding:2px 8px;border-radius:4px;font-weight:bold}
 #help{padding:4px 8px 10px;opacity:.75;font-size:12px;max-width:1100px}
 #strip{display:block;width:min(900px,90vw);height:18px;margin:4px 8px;background:#333}
</style></head><body>
<div id="bar"><span id="cams"></span>
 <button onclick="step(-20)">&laquo; 20</button><button onclick="step(-1)">&lsaquo; 1</button>
 <button id="play" onclick="toggle()">play (space)</button>
 <button onclick="step(1)">1 &rsaquo;</button><button onclick="step(20)">20 &raquo;</button>
 <label>speed <select id="speed"><option>0.25</option><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select></label>
 <button onclick="setFlag('wrong')" style="background:#a33">wrong (b)</button>
 <button onclick="setFlag('missed')" style="background:#a60">missed (m)</button>
 <button onclick="setFlag(null)">clear (c)</button>
 <button onclick="nextWhere(e=>flags[key(e)])">next flagged (f)</button>
 <button onclick="nextWhere(e=>!e.ell)">next no detection (n)</button>
 <button onclick="exportFlags()" style="background:#3c3;font-weight:bold">Export ball20_flags.json</button>
</div>
<input id="slider" type="range" min="0" value="0" style="margin:6px 8px">
<canvas id="strip" width="900" height="18" title="green = detected, grey = searched without a detection, red = flagged"></canvas>
<div id="wrap"><canvas id="cv" width="720" height="720"></canvas>
<div id="side"></div></div>
<div id="help">One square per searched frame: the ball's neighbourhood at full resolution (side = 6 x the predicted ball radius),
cyan = the detected ellipse (d hides it). Where nothing was detected the square sits on the nearest detection within 1 s.
Keys: &larr;/&rarr; one frame, &uarr;/&darr; 20 frames, space play/pause, b wrong, m missed, c clear, f next flagged, n next frame without a detection,
1-6 camera, d overlay. Flags are kept in this browser; Export writes them to a file.</div>
<script>
const CAMS=__CAMS__, KEYS='ball20_flags_v1';
const $=id=>document.getElementById(id), cv=$('cv'), g=cv.getContext('2d'), st=$('strip'), sg=st.getContext('2d');
let data={}, cam=null, i=0, timer=null, overlay=true, flags={}, cache=new Map();
try{flags=JSON.parse(localStorage.getItem(KEYS)||'{}')||{};}catch(e){flags={};}
function save(){try{localStorage.setItem(KEYS,JSON.stringify(flags));}catch(e){}}
function key(e){return cam+'|'+e.i;}
function fr(){return data[cam].frames;}
function img(e){if(!cache.has(e.img)){const im=new Image();im.onload=()=>{if(fr()[i]===e)draw();};im.src=e.img;cache.set(e.img,im);
  if(cache.size>400){for(const k of cache.keys()){cache.delete(k);if(cache.size<=300)break;}}}return cache.get(e.img);}
function draw(){const F=fr(),e=F[i];if(!e)return;const im=img(e);for(let k=1;k<=8&&i+k<F.length;k++)img(F[i+k]);
  g.fillStyle='#000';g.fillRect(0,0,cv.width,cv.height);if(im.complete&&im.naturalWidth)g.drawImage(im,0,0,cv.width,cv.height);
  const z=cv.width/360;
  if(overlay&&e.ell){const [x,y,a,b,th]=e.ell;g.strokeStyle='#0ff';g.lineWidth=2;g.beginPath();g.ellipse(x*z,y*z,Math.max(a*z,2),Math.max(b*z,2),th,0,7);g.stroke();
    g.beginPath();g.moveTo(x*z-8,y*z);g.lineTo(x*z+8,y*z);g.moveTo(x*z,y*z-8);g.lineTo(x*z,y*z+8);g.stroke();}
  const f=flags[key(e)];
  if(f){g.fillStyle=f==='wrong'?'rgba(200,40,40,.85)':'rgba(220,120,0,.85)';g.fillRect(0,0,cv.width,30);g.fillStyle='#fff';g.font='bold 18px Arial';g.fillText(f.toUpperCase(),10,22);}
  $('slider').value=i;
  $('side').innerHTML=`<div><b>${cam}</b> &nbsp; frame ${i+1} / ${F.length} (track entry ${e.i})</div>
   <div>clock <b>${e.clock}</b> &nbsp; t in file ${e.tf.toFixed(2)} s</div><div>2-s grid time ${e.t.toFixed(2)} s</div>
   <div>prior: ${e.src}</div><div>${e.ell?`detected: conf ${e.conf.toFixed(2)}, white ${e.white.toFixed(2)}`:'<span class="flag" style="background:#555">no detection</span>'}</div>
   <div>crop: x ${e.x0}, y ${e.y0}, side ${e.s} px</div>
   <div style="margin-top:8px">flags on ${cam}: ${F.filter(x=>flags[key(x)]==='wrong').length} wrong, ${F.filter(x=>flags[key(x)]==='missed').length} missed</div>`;
  strip();}
function strip(){const F=fr(),w=st.width;sg.fillStyle='#333';sg.fillRect(0,0,w,18);
  F.forEach((e,k)=>{const x=Math.floor(k*w/F.length);sg.fillStyle=flags[key(e)]?'#e33':(e.ell?'#2a2':'#777');sg.fillRect(x,flags[key(e)]?0:6,Math.max(1,Math.ceil(w/F.length)),flags[key(e)]?18:12);});
  sg.fillStyle='#ff0';sg.fillRect(Math.floor(i*w/F.length),0,2,18);}
function go(k){const F=fr();i=Math.max(0,Math.min(F.length-1,k));draw();}
function step(d){go(i+d);}
function toggle(){if(timer){clearInterval(timer);timer=null;$('play').classList.remove('on');return;}
  $('play').classList.add('on');timer=setInterval(()=>{if(i>=fr().length-1){toggle();return;}step(1);},50/parseFloat($('speed').value));}
function setFlag(v){const e=fr()[i];if(v)flags[key(e)]=v;else delete flags[key(e)];save();draw();}
function nextWhere(p){const F=fr();for(let k=i+1;k<F.length;k++)if(p(F[k])){go(k);return;}}
async function load(c){if(!data[c]){const r=await fetch(`index_${c}.json`).catch(()=>null);
  data[c]=r&&r.ok?await r.json():(window.INDEX&&window.INDEX[c]);}cam=c;i=0;$('slider').max=fr().length-1;
  document.querySelectorAll('#cams button').forEach(b=>b.classList.toggle('on',b.textContent===c));draw();}
function exportFlags(){const out=[];for(const c of Object.keys(data))for(const e of data[c].frames){const f=flags[c+'|'+e.i];
    if(f)out.push({cam:c,entry:e.i,clock:e.clock,t_file:e.tf,t_grid:e.t,flag:f,detected:!!e.ell});}
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify({flags:out},null,1));
  a.download='ball20_flags.json';a.click();}
$('cams').innerHTML=CAMS.map(c=>`<button onclick="load('${c}')">${c}</button>`).join('');
$('slider').addEventListener('input',e=>go(+e.target.value));
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;
  if(e.key==='ArrowRight')step(1);else if(e.key==='ArrowLeft')step(-1);else if(e.key==='ArrowUp'){e.preventDefault();step(-20);}
  else if(e.key==='ArrowDown'){e.preventDefault();step(20);}else if(e.key===' '){e.preventDefault();toggle();}
  else if(e.key==='b')setFlag('wrong');else if(e.key==='m')setFlag('missed');else if(e.key==='c')setFlag(null);
  else if(e.key==='f')nextWhere(x=>flags[key(x)]);else if(e.key==='n')nextWhere(x=>!x.ell);
  else if(e.key==='d'){overlay=!overlay;draw();}else if(e.key>='1'&&e.key<=String(CAMS.length))load(CAMS[+e.key-1]);});
</script>
<script>window.INDEX=__INDEX__;</script>
<script>load(CAMS[0]);</script>
</body></html>"""


if __name__ == "__main__":
    if "--html-only" not in args:
        for cam in CAMS:
            build(cam)
    have = [c for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06") if (OUT / f"index_{c}.json").exists()]
    inline = {c: json.loads((OUT / f"index_{c}.json").read_text(encoding="utf-8")) for c in have}   # file:// pages cannot fetch
    (OUT / "ball20_review.html").write_text(PAGE.replace("__CAMS__", json.dumps(have)).replace("__INDEX__", json.dumps(inline)),
                                            encoding="utf-8")
    print("->", OUT / "ball20_review.html", "cameras:", have)
