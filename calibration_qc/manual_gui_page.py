# -*- coding: utf-8 -*-
r"""The click page of manual_board_gui.py (four plate corners per frame, skip / partial verdicts, zoom, pan, a
magnifier, export to manual_quads.json), shared with board_sweep20_click_gui.py. __JOBS__ is replaced by the job
list, __DATE__ by a key that names the page (it also keys the browser's saved clicks)."""

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Manual board corners __DATE__</title>
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
