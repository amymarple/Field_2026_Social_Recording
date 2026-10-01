# -*- coding: utf-8 -*-
r"""GUI for the ball sweep: the operator marks the ball in every camera, one frame every --step seconds.

The ball (a stand-in rat of known size, CALIB_CONE_SHEET_2026-09-26.html step 6) is patterned and pushed
with a stick among coloured cones, so it is marked by hand. For each time on the grid, every camera's frame is
extracted at full resolution (pano cameras upright, so the pixels are paddock_map's "upright" space). The page
shows one camera large and all of them as thumbnails; the operator marks the ball's outline where it is visible:
  1 click   = the ball's centre only (when no edge can be seen);
  2 clicks  = the two ends of a diameter;
  3-4 clicks = points on the visible edge (an arc is enough, grass may hide the rest); a circle is fitted;
  5+ clicks = an ellipse is fitted instead, tilted as the outline is (the pano canvases and the lens edges
             stretch the ball into a rotated ellipse; a circle forced onto it would pull the centre).
The ellipse can also be set by hand: "e" turns the current circle into one, then drag its centre handle to
move it, the long-axis handle to stretch and rotate it, the short-axis handle to widen or narrow it - useful
when only part of the outline shows. The ball's position is the centre of the ellipse (or circle).
"s" says the ball is not in this camera's view at that time, "h" that it is there but hidden (house, person,
stick) and cannot be outlined: "not visible" is the operator's statement, never the program's.
The previous time's mark in the same camera is drawn as a dashed circle; the view keeps its zoom between
times, so the ball is usually near the middle of it.

Times are PC clock = segment start (from the file name, 1 s resolution) + offset in the file. The streams'
true relative delays are unknown at this point; the ball tracks are what will measure them.

Usage: python ball_gui.py --session <dir|YYYY-MM-DD> --window HH:MM:SS-HH:MM:SS [--step 2] [--cams CH01,...]
                          [--reuse-frames] [--out <dir>]
Output: <qc>\ball\<cam>\<cam>_<nnnn>.jpg, jobs.json, ball_gui.html; the page exports ball_labels.json.
"""
import sys, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

FFMPEG = qc_paths.FFMPEG
args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)


def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default


if not opt("--window"):
    raise SystemExit("usage: python ball_gui.py --session <dir|date> --window HH:MM:SS-HH:MM:SS [--step 2] [--cams ...]")
CAMS = opt("--cams", "CH01,CH02,CH03,CH04,CH05,CH06").split(",")
STEP = float(opt("--step", "2"))
REUSE = "--reuse-frames" in args
OUT = Path(opt("--out")) if opt("--out") else QC / "ball"
OUT.mkdir(parents=True, exist_ok=True)
w0, w1 = opt("--window").split("-")
T0 = datetime.strptime(f"{DATE} {w0}", "%Y-%m-%d %H:%M:%S")
T1 = datetime.strptime(f"{DATE} {w1}", "%Y-%m-%d %H:%M:%S")
N = int((T1 - T0).total_seconds() // STEP) + 1
CLOCKS = [(T0 + timedelta(seconds=k * STEP)).strftime("%H:%M:%S") + (f".{int(round((k * STEP) % 1 * 10))}" if STEP % 1 else "")
          for k in range(N)]


def seg_for(cam):
    """the closed segment that covers the whole window, and its start time from the file name."""
    for p in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):
        a = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(p.name.split("_")[1] + " " + p.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if a <= T0 and T1 <= b:
            return p, a
    raise SystemExit(f"no closed {cam} segment covers {w0}-{w1} in {SESSION}")


def extract(cam):
    seg, a = seg_for(cam)
    off = (T0 - a).total_seconds()
    d = OUT / cam
    d.mkdir(exist_ok=True)
    have = sorted(d.glob(f"{cam}_*.jpg"))
    if not (REUSE and len(have) >= N):
        for f in have:
            f.unlink()
        vf = f"fps=1/{STEP}" + (",transpose=2" if cam in ("CH01", "CH02") else "")
        subprocess.run([FFMPEG, "-v", "error", "-ss", f"{off:.3f}", "-i", str(seg), "-t", f"{(N - 1) * STEP + STEP / 2:.3f}",
                        "-vf", vf, "-q:v", "3", "-start_number", "0", str(d / f"{cam}_%04d.jpg")], check=True)
        have = sorted(d.glob(f"{cam}_*.jpg"))
    h, w = cv2.imread(str(have[0])).shape[:2]
    print(f"{cam}: {len(have)} frames from {seg.name} at +{off:.0f} s, {w}x{h}", flush=True)
    return dict(cam=cam, file=seg.name, file_start=a.strftime("%H:%M:%S"), offset_s=off, n=len(have), w=w, h=h,
                pano=cam in ("CH01", "CH02"))


with ThreadPoolExecutor(max_workers=len(CAMS)) as ex:
    cams = list(ex.map(extract, CAMS))
jobs = dict(session=SESSION.name, date=DATE, window=[w0, w1], step=STEP, clocks=CLOCKS, cams=cams)
(OUT / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")

html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Ball sweep __DATE__</title>
<style>
 body{margin:0;background:#1b1b1b;color:#eee;font-family:Arial,sans-serif;font-size:14px}
 #bar{position:sticky;top:0;background:#2a2a2a;padding:6px 8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;z-index:5}
 button{font-size:13px;padding:3px 9px} b{color:#ff0}
 #main{display:block;width:100%;max-width:1700px;cursor:crosshair;background:#000;margin:6px 0}
 #thumbs{display:flex;gap:6px;flex-wrap:wrap;padding:0 6px 6px}
 .th{border:3px solid #555;cursor:pointer;background:#000} .th.active{outline:2px solid #fff}
 #help{padding:4px 8px 10px;opacity:.75;font-size:12px;max-width:1700px}
</style></head><body>
<div id="bar">
 <span>time <b id="clock"></b> (<b id="ti"></b>/<b id="tn"></b>)</span>
 <span>camera <b id="camname"></b></span>
 <span id="status" style="padding:2px 10px;border-radius:4px;font-weight:bold"></span>
 <span id="fitinfo"></span>
 <button onclick="go(k-1)">&lt; time (&larr;)</button><button onclick="go(k+1)">time &gt; (&rarr;)</button>
 <button onclick="nextCam()">next camera (space)</button><button onclick="nextOpen()">next unreviewed (n)</button>
 <button onclick="setVerdict('not visible')" style="background:#833">not in view (s)</button>
 <button onclick="setVerdict('hidden')" style="background:#a60">there but hidden (h)</button>
 <button onclick="undo()">undo (u)</button><button onclick="clearPts()">clear (c)</button>
 <button onclick="toEllipse()">edit as ellipse (e)</button><button onclick="dropEllipse()">back to points (r)</button>
 <button onclick="fitView();draw()">fit (f)</button><button onclick="zoomBall()">zoom to ball (z)</button>
 <span>zoom <b id="zoom"></b></span>
 <span>reviewed <b id="ndone"></b> / <b id="ntot"></b></span>
 <button onclick="exportJson()" style="background:#3c3;font-weight:bold">Export ball_labels.json</button>
 <label style="font-size:12px">import <input type="file" id="imp" accept=".json"></label>
</div>
<canvas id="main" width="1700" height="760"></canvas>
<div id="thumbs"></div>
<div id="help">Click on the ball's EDGE where you can see it: 3-4 points along an arc fit a circle, 5 or more fit a TILTED ELLIPSE.
One click = centre only, two clicks = the ends of a diameter. "e" turns the shape into an ellipse with handles: drag the
centre square to move it, the long-axis handle (L) to stretch and ROTATE it, the short-axis handle (S) to widen it; "r" drops
the hand-set ellipse and goes back to the clicked points. Drag a point to move it, shift+arrows nudge the last point by 1 px. Wheel = zoom,
right-drag = pan; the view keeps its zoom when the time changes. Dashed orange = this camera's mark at an earlier time.
Keys: 1-6 camera, &larr;/&rarr; time, space next camera, n next unreviewed, s not in view, h hidden, u undo, c clear, e ellipse, r points, f fit, z zoom to ball.
Marks are saved in this browser as you go; Export writes them to a file.</div>
<script>
const JOBS=__JOBS__; const KEY='ball_labels___SESSION__';
const $=id=>document.getElementById(id), cv=$('main'), ctx=cv.getContext('2d');
let k=0, ci=0, labels={}, views={}, hover=null, drag=-1, last=-1, pan=null;
const cams=JOBS.cams, NT=JOBS.clocks.length, cache=new Map();
const pad=n=>String(n).padStart(4,'0');
function src(t,c){return `${cams[c].cam}/${cams[c].cam}_${pad(t)}.jpg`;}
function img(t,c){const s=src(t,c);if(!cache.has(s)){const im=new Image();im.onload=()=>{if(t===k){if(c===ci)draw();thumb(c);}};im.src=s;cache.set(s,im);}
  if(cache.size>80){for(const key of cache.keys()){if(!key.includes(`_${pad(k)}`)&&!key.includes(`_${pad(k+1)}`)){cache.delete(key);if(cache.size<=60)break;}}}
  return cache.get(s);}
function key(t,c){return t+'|'+cams[c].cam;}
function lab(t,c){return labels[key(t,c)];}
// ---- circle from the marks
function fitCircle(p){if(!p||!p.length)return null;
  if(p.length===1)return {c:p[0],r:null,method:'centre'};
  if(p.length===2)return {c:[(p[0][0]+p[1][0])/2,(p[0][1]+p[1][1])/2],r:Math.hypot(p[0][0]-p[1][0],p[0][1]-p[1][1])/2,method:'diameter'};
  // Kasa: x^2+y^2 + D x + E y + F = 0, least squares
  let A=[[0,0,0],[0,0,0],[0,0,0]],b=[0,0,0];
  for(const [x,y] of p){const row=[x,y,1],z=-(x*x+y*y);for(let i=0;i<3;i++){b[i]+=row[i]*z;for(let j=0;j<3;j++)A[i][j]+=row[i]*row[j];}}
  const s=solve3(A,b);if(!s)return null;const cx=-s[0]/2,cy=-s[1]/2,r=Math.sqrt(Math.max(0,cx*cx+cy*cy-s[2]));
  const res=Math.sqrt(p.reduce((a,q)=>a+(Math.hypot(q[0]-cx,q[1]-cy)-r)**2,0)/p.length);
  return {c:[cx,cy],r:r,method:'arc-'+p.length,rms:res};}
function solve3(A,b){const M=A.map((r,i)=>r.concat([b[i]]));for(let i=0;i<3;i++){let m=i;for(let j=i+1;j<3;j++)if(Math.abs(M[j][i])>Math.abs(M[m][i]))m=j;
  [M[i],M[m]]=[M[m],M[i]];if(Math.abs(M[i][i])<1e-12)return null;for(let j=0;j<3;j++)if(j!==i){const f=M[j][i]/M[i][i];for(let q=i;q<4;q++)M[j][q]-=f*M[i][q];}}
  return [M[0][3]/M[0][0],M[1][3]/M[1][1],M[2][3]/M[2][2]];}
function solveN(A,b){const n=b.length,M=A.map((r,i)=>r.concat([b[i]]));
  for(let i=0;i<n;i++){let m=i;for(let j=i+1;j<n;j++)if(Math.abs(M[j][i])>Math.abs(M[m][i]))m=j;[M[i],M[m]]=[M[m],M[i]];
    if(Math.abs(M[i][i])<1e-12)return null;for(let j=0;j<n;j++)if(j!==i){const f=M[j][i]/M[i][i];for(let q=i;q<=n;q++)M[j][q]-=f*M[i][q];}}
  return M.map((r,i)=>r[n]/r[i]);}
// conic A x^2 + B xy + C y^2 + D x + E y + F = 0 with A + C = 1, least squares in normalised coordinates
function fitEllipse(p){if(!p||p.length<5)return null;
  const mx=p.reduce((a,q)=>a+q[0],0)/p.length,my=p.reduce((a,q)=>a+q[1],0)/p.length;
  const sc=Math.sqrt(p.reduce((a,q)=>a+(q[0]-mx)**2+(q[1]-my)**2,0)/p.length)||1;
  const N=Array.from({length:5},()=>[0,0,0,0,0]),v=[0,0,0,0,0];
  for(const q of p){const x=(q[0]-mx)/sc,y=(q[1]-my)/sc,row=[x*x-y*y,x*y,x,y,1],z=-y*y;
    for(let i=0;i<5;i++){v[i]+=row[i]*z;for(let j=0;j<5;j++)N[i][j]+=row[i]*row[j];}}
  const s=solveN(N,v);if(!s)return null;const A=s[0],B=s[1],C=1-A,D=s[2],E=s[3],F=s[4];
  if(B*B-4*A*C>=0)return null;
  const det=4*A*C-B*B,x0=(B*E-2*C*D)/det,y0=(B*D-2*A*E)/det;
  const F0=A*x0*x0+B*x0*y0+C*y0*y0+D*x0+E*y0+F;
  const tr=A+C,dd=Math.sqrt(((A-C)/2)**2+(B/2)**2),l1=tr/2-dd,l2=tr/2+dd;   // l1 <= l2: l1 goes with the long axis
  if(-F0/l1<=0||-F0/l2<=0)return null;
  const a=Math.sqrt(-F0/l1)*sc,b=Math.sqrt(-F0/l2)*sc,th=Math.atan2(l1-A,B/2);
  const ell={cx:x0*sc+mx,cy:y0*sc+my,a:a,b:b,th:(B===0&&l1===A)?0:th};
  const res=Math.sqrt(p.reduce((acc,q)=>{const dx=q[0]-ell.cx,dy=q[1]-ell.cy,c=Math.cos(ell.th),s2=Math.sin(ell.th);
    const u=(dx*c+dy*s2)/ell.a,w=(-dx*s2+dy*c)/ell.b;return acc+((Math.hypot(u,w)-1)*(ell.a+ell.b)/2)**2;},0)/p.length);
  return Object.assign(ell,{rms:res});}
// what a label says about the ball: centre, a radius for display, the ellipse when there is one, how it was obtained
function shapeOf(L){if(!L||L.verdict!=='ball')return null;
  if(L.ell)return {c:[L.ell.cx,L.ell.cy],r:(L.ell.a+L.ell.b)/2,ell:L.ell,method:'ellipse-by-hand'};
  const e=fitEllipse(L.pts);
  if(e&&e.a<8*e.b)return {c:[e.cx,e.cy],r:(e.a+e.b)/2,ell:e,method:'ellipse-'+L.pts.length,rms:e.rms};
  return fitCircle(L.pts);}
function ghost(t,c){for(let d=1;d<=6;d++){const f=shapeOf(lab(t-d,c));if(f)return f;}return null;}
// ---- view
function V(){return views[cams[ci].cam];}
function fitView(){const c=cams[ci];views[c.cam]={z:Math.min(cv.width/c.w,cv.height/c.h),ox:0,oy:0};
  const v=V();v.ox=(cv.width-c.w*v.z)/2;v.oy=(cv.height-c.h*v.z)/2;}
function centreOn(p,z){const v=V();if(z)v.z=z;v.ox=cv.width/2-p[0]*v.z;v.oy=cv.height/2-p[1]*v.z;}
function zoomBall(){const f=shapeOf(lab(k,ci))||ghost(k,ci);if(!f)return;
  const r=Math.max(f.r||25,15);centreOn(f.c,Math.min(cv.height/(r*10),12));draw();}
function S2C(p){const v=V();return [p[0]*v.z+v.ox,p[1]*v.z+v.oy];}
function toImg(e){const r=cv.getBoundingClientRect(),v=V();const x=(e.clientX-r.left)*cv.width/r.width,y=(e.clientY-r.top)*cv.height/r.height;
  return [(x-v.ox)/v.z,(y-v.oy)/v.z];}
// ---- drawing
function handles(f){if(!f||!f.ell)return null;const e=f.ell,c=Math.cos(e.th),s=Math.sin(e.th);
  return {C:[e.cx,e.cy],L:[e.cx+e.a*c,e.cy+e.a*s],S:[e.cx-e.b*s,e.cy+e.b*c]};}
function shape(g,f,col,dash,w,T){if(!f)return;g.save();g.strokeStyle=col;g.lineWidth=w||2;if(dash)g.setLineDash(dash);
  const c=T(f.c);g.beginPath();
  if(f.ell){const z=T([f.c[0]+1,f.c[1]])[0]-c[0];g.ellipse(c[0],c[1],Math.max(f.ell.a*z,3),Math.max(f.ell.b*z,3),f.ell.th,0,7);}
  else{const z=T([f.c[0]+1,f.c[1]])[0]-c[0];g.arc(c[0],c[1],Math.max((f.r||10)*z,3),0,7);}
  g.stroke();g.setLineDash([]);g.beginPath();g.moveTo(c[0]-8,c[1]);g.lineTo(c[0]+8,c[1]);g.moveTo(c[0],c[1]-8);g.lineTo(c[0],c[1]+8);g.stroke();g.restore();}
function circle(g,c,r,col,dash,w){g.save();g.strokeStyle=col;g.lineWidth=w||2;if(dash)g.setLineDash(dash);g.beginPath();g.arc(c[0],c[1],Math.max(r,3),0,7);g.stroke();
  g.setLineDash([]);g.beginPath();g.moveTo(c[0]-8,c[1]);g.lineTo(c[0]+8,c[1]);g.moveTo(c[0],c[1]-8);g.lineTo(c[0],c[1]+8);g.stroke();g.restore();}
function draw(){const c=cams[ci],im=img(k,ci);if(!V())fitView();const v=V();
  ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#000';ctx.fillRect(0,0,cv.width,cv.height);
  if(im.complete&&im.naturalWidth){ctx.imageSmoothingEnabled=v.z<1;ctx.drawImage(im,v.ox,v.oy,c.w*v.z,c.h*v.z);}
  const g=ghost(k,ci);if(g)shape(ctx,g,'#ff8c00',[6,5],2,S2C);
  const L=lab(k,ci),pts=L&&L.pts?L.pts:[];const f=shapeOf(L);
  if(f)shape(ctx,f,'#0f0',null,2,S2C);
  const H=L&&L.ell?handles(f):null;
  if(H){for(const [nm,p0] of Object.entries(H)){const p=S2C(p0);ctx.fillStyle=nm==='C'?'#ff0':'#f0f';
    ctx.fillRect(p[0]-6,p[1]-6,12,12);ctx.fillStyle='#000';ctx.font='bold 10px sans-serif';ctx.fillText(nm,p[0]-3,p[1]+4);}}
  pts.forEach((p0,i)=>{const p=S2C(p0);ctx.strokeStyle=i===last?'#ff0':'#0ff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(p[0],p[1],5,0,7);ctx.stroke();});
  if(hover){const Z=6,S=46,D=S*Z,hs=S2C(hover),mx=(hs[0]<cv.width/2)?cv.width-D-10:10,my=10;
    ctx.save();ctx.beginPath();ctx.rect(mx,my,D,D);ctx.clip();ctx.imageSmoothingEnabled=false;
    if(im.complete)ctx.drawImage(im,hover[0]-S/2,hover[1]-S/2,S,S,mx,my,D,D);
    const zp=p=>[mx+(p[0]-hover[0]+S/2)*Z,my+(p[1]-hover[1]+S/2)*Z];
    if(f&&f.r)shape(ctx,f,'#0f0',null,2,zp);
    pts.forEach(p0=>{const p=zp(p0);ctx.strokeStyle='#0ff';ctx.beginPath();ctx.arc(p[0],p[1],6,0,7);ctx.stroke();});
    ctx.strokeStyle='#ff0';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(mx+D/2-16,my+D/2);ctx.lineTo(mx+D/2+16,my+D/2);
    ctx.moveTo(mx+D/2,my+D/2-16);ctx.lineTo(mx+D/2,my+D/2+16);ctx.stroke();ctx.restore();ctx.strokeStyle='#888';ctx.strokeRect(mx,my,D,D);}
  $('zoom').textContent=v.z.toFixed(2)+'x';
  $('fitinfo').textContent=f?(f.method+(f.ell?` ${(2*f.ell.a).toFixed(0)}x${(2*f.ell.b).toFixed(0)}px ${(f.ell.th*180/Math.PI).toFixed(0)}deg`:(f.r?` r=${f.r.toFixed(1)}px`:''))
    +(f.rms!==undefined&&f.rms!==null?` fit rms ${f.rms.toFixed(1)}px`:'')):'';
  status();}
const STAT={ball:['BALL MARKED','#2a6cc0'],'not visible':['NOT IN VIEW','#a33'],hidden:['THERE BUT HIDDEN','#a60']};
function stOf(t,c){const L=lab(t,c);if(!L)return ['not reviewed','#555'];return STAT[L.verdict]||['not reviewed','#555'];}
function status(){const [txt,col]=stOf(k,ci);const e=$('status');e.textContent=txt;e.style.background=col;
  $('clock').textContent=JOBS.clocks[k];$('ti').textContent=k+1;$('tn').textContent=NT;$('camname').textContent=cams[ci].cam;
  $('ndone').textContent=Object.keys(labels).length;$('ntot').textContent=NT*cams.length;}
function buildThumbs(){$('thumbs').innerHTML=cams.map((c,i)=>`<canvas class="th" id="th${i}" width="${c.pano?320:220}" height="${c.pano?90:124}" title="${c.cam} (key ${i+1})"></canvas>`).join('');
  cams.forEach((c,i)=>$('th'+i).addEventListener('click',()=>{ci=i;sel();}));}
function thumb(i){const c=cams[i],t=$('th'+i),g=t.getContext('2d'),im=img(k,i),s=Math.min(t.width/c.w,t.height/c.h);
  g.fillStyle='#000';g.fillRect(0,0,t.width,t.height);if(im.complete&&im.naturalWidth)g.drawImage(im,0,0,c.w*s,c.h*s);
  const f=shapeOf(lab(k,i));if(f)circle(g,[f.c[0]*s,f.c[1]*s],Math.max((f.r||10)*s,4),'#0f0',null,2);
  const gh=ghost(k,i);if(!f&&gh)circle(g,[gh.c[0]*s,gh.c[1]*s],Math.max((gh.r||10)*s,4),'#ff8c00',[3,3],1);
  g.fillStyle='#ff0';g.font='bold 13px sans-serif';g.fillText(c.cam,4,14);t.style.borderColor=stOf(k,i)[1];t.classList.toggle('active',i===ci);}
function allThumbs(){cams.forEach((c,i)=>thumb(i));}
function sel(){last=-1;const v=V(),g=ghost(k,ci);
  if(!v)fitView();
  else if(g){const p=S2C(g.c);if(p[0]<0||p[1]<0||p[0]>cv.width||p[1]>cv.height)centreOn(g.c);}
  draw();allThumbs();}
function go(t){if(t<0||t>=NT)return;k=t;for(let c=0;c<cams.length;c++)img(Math.min(NT-1,k+1),c);sel();}
function nextCam(){if(ci<cams.length-1)ci++;else{ci=0;if(k<NT-1)k++;}sel();}
function nextOpen(){for(let t=k;t<NT;t++)for(let c=(t===k?ci+1:0);c<cams.length;c++)if(!lab(t,c)){k=t;ci=c;sel();return;}}
// ---- marking
function save(){try{localStorage.setItem(KEY,JSON.stringify(labels));}catch(e){}}
function setPts(p){const L=lab(k,ci),ell=L&&L.ell?L.ell:null;
  if(p.length||ell)labels[key(k,ci)]=Object.assign({pts:p,verdict:'ball'},ell?{ell:ell}:{});else delete labels[key(k,ci)];save();draw();thumb(ci);}
function setEll(e){const L=lab(k,ci);labels[key(k,ci)]={pts:L&&L.pts?L.pts:[],verdict:'ball',ell:e};save();draw();thumb(ci);}
function toEllipse(){const f=shapeOf(lab(k,ci))||ghost(k,ci);if(!f)return;
  const r=f.r||Math.max(10,15/V().z);setEll(f.ell?Object.assign({},f.ell,{rms:undefined}):{cx:f.c[0],cy:f.c[1],a:r,b:r,th:0});}
function dropEllipse(){const L=lab(k,ci);if(!L||!L.ell)return;delete L.ell;if(!L.pts.length)delete labels[key(k,ci)];save();draw();thumb(ci);}
let hdrag=null;
function setVerdict(v){labels[key(k,ci)]={pts:[],verdict:v};save();nextCam();}
function curPts(){const L=lab(k,ci);return L&&L.verdict==='ball'?L.pts.map(p=>p.slice()):[];}
function undo(){const p=curPts();p.pop();last=p.length-1;setPts(p);}
function clearPts(){delete labels[key(k,ci)];save();last=-1;draw();thumb(ci);}
function nearest(p){const q=curPts();let bi=-1,bd=1e9;q.forEach((r,i)=>{const d=Math.hypot(r[0]-p[0],r[1]-p[1]);if(d<bd){bd=d;bi=i;}});return [bi,bd];}
cv.addEventListener('contextmenu',e=>e.preventDefault());
cv.addEventListener('mousedown',e=>{const r=cv.getBoundingClientRect(),v=V();
  if(e.button===2||e.button===1){pan={x:(e.clientX-r.left)*cv.width/r.width-v.ox,y:(e.clientY-r.top)*cv.height/r.height-v.oy};e.preventDefault();return;}
  const p=toImg(e),L=lab(k,ci),H=L&&L.ell?handles(shapeOf(L)):null;
  if(H){for(const [nm,q] of Object.entries(H))if(Math.hypot(q[0]-p[0],q[1]-p[1])*v.z<=10){hdrag=nm;return;}}
  const [i,d]=nearest(p);if(i>=0&&d*v.z<=10){drag=i;last=i;draw();return;}
  const q=curPts();q.push(p);last=q.length-1;setPts(q);});
cv.addEventListener('mousemove',e=>{const r=cv.getBoundingClientRect(),v=V();
  if(pan){v.ox=(e.clientX-r.left)*cv.width/r.width-pan.x;v.oy=(e.clientY-r.top)*cv.height/r.height-pan.y;draw();return;}
  hover=toImg(e);
  if(hdrag){const e0=Object.assign({},lab(k,ci).ell),dx=hover[0]-e0.cx,dy=hover[1]-e0.cy;
    if(hdrag==='C'){e0.cx=hover[0];e0.cy=hover[1];}
    else if(hdrag==='L'){e0.a=Math.max(2,Math.hypot(dx,dy));e0.th=Math.atan2(dy,dx);}
    else{e0.b=Math.max(2,Math.abs(-dx*Math.sin(e0.th)+dy*Math.cos(e0.th)));}
    setEll(e0);return;}
  if(drag>=0){const q=curPts();q[drag]=hover;setPts(q);return;}draw();});
cv.addEventListener('mouseleave',()=>{hover=null;pan=null;draw();});
window.addEventListener('mouseup',()=>{pan=null;drag=-1;hdrag=null;});
cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect(),v=V();
  const x=(e.clientX-r.left)*cv.width/r.width,y=(e.clientY-r.top)*cv.height/r.height,f=e.deltaY<0?1.25:0.8,nz=Math.max(0.03,Math.min(24,v.z*f));
  v.ox=x-(x-v.ox)*nz/v.z;v.oy=y-(y-v.oy)*nz/v.z;v.z=nz;draw();},{passive:false});
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
  if(e.shiftKey&&e.key.startsWith('Arrow')){const q=curPts();if(last>=0&&q[last]){q[last][0]+=e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0;
    q[last][1]+=e.key==='ArrowUp'?-1:e.key==='ArrowDown'?1:0;setPts(q);}e.preventDefault();return;}
  if(e.key>='1'&&e.key<=String(cams.length)){ci=+e.key-1;sel();}
  else if(e.key==='ArrowRight')go(k+1);else if(e.key==='ArrowLeft')go(k-1);
  else if(e.key===' '){e.preventDefault();nextCam();}else if(e.key==='n')nextOpen();
  else if(e.key==='s')setVerdict('not visible');else if(e.key==='h')setVerdict('hidden');
  else if(e.key==='u')undo();else if(e.key==='c')clearPts();
  else if(e.key==='e')toEllipse();else if(e.key==='r')dropEllipse();
  else if(e.key==='f'){fitView();draw();}else if(e.key==='z')zoomBall();});
function exportJson(){const out=[];for(const [kk,L] of Object.entries(labels)){const [t,cam]=kk.split('|');const f=shapeOf(L);
    const el=f&&f.ell?{cx:f.ell.cx,cy:f.ell.cy,a:f.ell.a,b:f.ell.b,theta_rad:f.ell.th}:null;
    out.push({k:+t,clock:JOBS.clocks[+t],cam:cam,verdict:L.verdict,pts:L.pts,centre:f?f.c:null,r:f?f.r:null,ellipse:el,
              method:f?f.method:null,fit_rms:f&&f.rms!==undefined?f.rms:null,hand_ellipse:L.ell?{cx:L.ell.cx,cy:L.ell.cy,a:L.ell.a,b:L.ell.b,th:L.ell.th}:null});}
  out.sort((a,b)=>a.k-b.k||a.cam.localeCompare(b.cam));
  const doc={session:JOBS.session,date:JOBS.date,window:JOBS.window,step:JOBS.step,space:'upright full-resolution pixels',cams:JOBS.cams,labels:out};
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(doc,null,1));
  a.download='ball_labels.json';a.click();}
$('imp').addEventListener('change',e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();
  rd.onload=()=>{const d=JSON.parse(rd.result);(d.labels||[]).forEach(L=>{labels[L.k+'|'+L.cam]=Object.assign({pts:L.pts||[],verdict:L.verdict},
    L.hand_ellipse?{ell:L.hand_ellipse}:{});});save();sel();};rd.readAsText(f);});
try{const s=localStorage.getItem(KEY);if(s)labels=JSON.parse(s);}catch(e){}
buildThumbs();go(0);
</script></body></html>"""
(OUT / "ball_gui.html").write_text(html.replace("__JOBS__", json.dumps(jobs)).replace("__DATE__", DATE)
                                   .replace("__SESSION__", SESSION.name), encoding="utf-8")
print(f"\n{N} times x {len(cams)} cameras -> {OUT / 'ball_gui.html'}")
