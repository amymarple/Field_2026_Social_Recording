# -*- coding: utf-8 -*-
"""Frame-step timeline GUI over the annotated CH01/CH02 timelapses: scrub frame by frame, read the
exact PC clock of the current frame, mark start/end, type the station ID, export 'start-end station'.
Writes E:\calibration\qc\timeline_gui.html (open it from that folder; the mp4s are referenced relatively)."""
import json, re, subprocess
from pathlib import Path
from datetime import datetime, timedelta

QC = Path(r"E:\calibration\qc"); SESSION = Path(r"E:\calibration\session_2026-09-18_13-54-34")
FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
VIDEOS = {"CH01": "annotated_CH01_150000-154936_timelapse.mp4", "CH02": "annotated_CH02_150000-154936_timelapse.mp4"}
clocks = {}
for cam in VIDEOS:
    seg = sorted(SESSION.glob(f"{cam}_*15-00-0*_to_*.mp4"))[0]
    a = datetime.strptime(seg.name.split("_")[1] + " " + seg.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
    out = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                                   "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(seg)]).decode()
    pts = [float(x) for x in out.split() if x]
    clocks[cam] = [(a + timedelta(seconds=p)).strftime("%H:%M:%S") for p in pts]
    print(cam, len(pts), "keyframes", clocks[cam][0], "->", clocks[cam][-1])
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
names = [f"T{li}{si}" for li in range(1, 8) for si in range(1, 6)] + \
        [f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}" for i in range(1, 7) for j in range(1, 5)] + ["SWEEP-CH03", "SWEEP-CH04", "NONE"]
html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Placement timeline</title>
<style>
 body{margin:0;font-family:Arial,sans-serif;font-size:14px;background:#1b1b1b;color:#eee}
 #vids{display:flex;flex-direction:column;gap:4px;padding:6px}
 video{width:100%;max-width:1700px;background:#000}
 #ctrl{padding:8px;background:#2a2a2a;display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0}
 button{font-size:14px;padding:4px 10px} input{font-size:15px}
 #clock{font:bold 24px monospace;color:#ff0;min-width:110px}
 #rows{padding:8px} table{border-collapse:collapse} td,th{border:1px solid #555;padding:2px 8px} textarea{width:600px;height:140px;font:13px monospace}
 .cur{background:#333}
</style></head><body>
<div id="ctrl">
 <button onclick="step(-10)">-10</button><button onclick="step(-1)">← frame</button><button onclick="toggle()">play/pause</button>
 <button onclick="step(1)">frame →</button><button onclick="step(10)">+10</button>
 <input id="slider" type="range" min="0" max="1500" value="0" style="width:420px" oninput="seekFrame(+this.value)">
 <span>frame <b id="fi">0</b></span> <span id="clock">15:00:01</span>
 <span>| start <b id="st">--</b> end <b id="en">--</b></span>
 <button onclick="markStart()">[ mark start</button><button onclick="markEnd()">] mark end</button>
 <input id="sid" list="ids" placeholder="station" size="10"><datalist id="ids">__DATALIST__</datalist>
 <button onclick="addRow()" style="background:#3c3;font-weight:bold">Enter: add</button>
 <button onclick="exportTxt()">Export timeline.txt</button>
 <span style="opacity:.7">keys: ←/→ frame, shift+←/→ ±10, space play, [ ] mark, Enter add</span>
</div>
<div id="vids">
 <video id="v1" src="__V1__" muted preload="auto"></video>
 <video id="v2" src="__V2__" muted preload="auto"></video>
</div>
<div id="rows"><table id="tbl"><tr><th>#</th><th>start</th><th>end</th><th>station</th><th></th></tr></table>
<p><textarea id="out"></textarea></p></div>
<script>
const C1=__CLOCKS1__, C2=__CLOCKS2__, FPS=10;
const v1=document.getElementById('v1'), v2=document.getElementById('v2');
let rows=[], start=null, end=null;
function frame(){return Math.round(v1.currentTime*FPS);}
function clockOf(f){return C1[Math.min(Math.max(f,0),C1.length-1)];}
function show(){const f=frame();document.getElementById('fi').textContent=f;document.getElementById('clock').textContent=clockOf(f);document.getElementById('slider').value=f;}
function seekFrame(f){f=Math.max(0,Math.min(f,C1.length-1));v1.pause();v2.pause();v1.currentTime=(f+0.5)/FPS;v2.currentTime=(f+0.5)/FPS;show();}
function step(d){seekFrame(frame()+d);}
function toggle(){if(v1.paused){v1.play();v2.currentTime=v1.currentTime;v2.play();}else{v1.pause();v2.pause();}}
v1.addEventListener('timeupdate',show);
function markStart(){start=clockOf(frame());document.getElementById('st').textContent=start;}
function markEnd(){end=clockOf(frame());document.getElementById('en').textContent=end;document.getElementById('sid').focus();}
function addRow(){const s=document.getElementById('sid').value.trim().toUpperCase();if(!start||!s){alert('mark start (and end) and type the station');return;}
  rows.push({start:start,end:end||start,station:s});start=end=null;document.getElementById('st').textContent='--';document.getElementById('en').textContent='--';document.getElementById('sid').value='';render();}
function delRow(i){rows.splice(i,1);render();}
function render(){const t=document.getElementById('tbl');t.innerHTML='<tr><th>#</th><th>start</th><th>end</th><th>station</th><th></th></tr>'+rows.map((r,i)=>`<tr><td>${i+1}</td><td>${r.start}</td><td>${r.end}</td><td>${r.station}</td><td><button onclick="delRow(${i})">x</button></td></tr>`).join('');
  document.getElementById('out').value=rows.map(r=>`${r.start}-${r.end}  ${r.station}`).join('\n');
  try{localStorage.setItem('timeline_rows',JSON.stringify(rows));}catch(e){}}
function exportTxt(){render();const a=document.createElement('a');a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(document.getElementById('out').value+'\n');a.download='placement_timeline.txt';a.click();}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'&&e.key!=='Enter'&&e.key!=='['&&e.key!==']')return;
  if(e.key==='ArrowLeft'){step(e.shiftKey?-10:-1);e.preventDefault();}else if(e.key==='ArrowRight'){step(e.shiftKey?10:1);e.preventDefault();}
  else if(e.key===' '){toggle();e.preventDefault();}else if(e.key==='['){markStart();}else if(e.key===']'){markEnd();}else if(e.key==='Enter'){addRow();}});
try{const saved=localStorage.getItem('timeline_rows');if(saved){rows=JSON.parse(saved);render();}}catch(e){}
v1.addEventListener('loadedmetadata',()=>{document.getElementById('slider').max=C1.length-1;show();});
</script></body></html>"""
html = (html.replace("__V1__", VIDEOS["CH01"]).replace("__V2__", VIDEOS["CH02"])
        .replace("__CLOCKS1__", json.dumps(clocks["CH01"])).replace("__CLOCKS2__", json.dumps(clocks["CH02"]))
        .replace("__DATALIST__", "".join(f'<option value="{n}">' for n in names)))
(QC / "timeline_gui.html").write_text(html, encoding="utf-8")
print("->", QC / "timeline_gui.html")
