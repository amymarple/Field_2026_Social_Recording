# -*- coding: utf-8 -*-
r"""Frame-step timeline GUI over the annotated CH01/CH02 timelapses: scrub frame by frame, read the
exact PC clock of the current frame, mark start/end, type the station ID, export 'start-end station'.
Writes E:\calibration\qc\timeline_gui.html (open it from that folder; the mp4s are referenced relatively).

Frame bookkeeping: the current frame index is kept in a JS variable and the player is seeked to the
frame's midpoint (f+0.5)/FPS; the index is only re-derived from currentTime (floor, not round) during
playback. The first version derived it with Math.round(), which reads the midpoint back as f+1, so
'<- frame' re-seeked the same frame and '->' skipped two (operator report 2026-09-19).
CH02 is slaved to CH01 by PC clock (nearest keyframe), not by frame index - the two cameras' keyframe
trains drift by a few frames over the 50 min.
Clock readout truncates fractional seconds (floor), the same convention as the burnt-in 'CHxx PC HH:MM:SS'
of annotate_video.py (strftime) and the corners/<HHMMSS>.npz names, so the yellow clock always equals the
clock visible in the frame; rounding disagreed by 1 s on about half the frames.
Usage: python timeline_gui.py [--session <dir|YYYY-MM-DD>]  (uses the newest annotated_CHxx_*_timelapse.mp4
in the session's QC folder; aborts if the keyframe count differs from the timelapse frame count)."""
import sys, json, re, subprocess
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess); DATE = qc_paths.session_date(SESSION)
FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
VIDEOS = {}
for cam in ("CH01", "CH02"):
    vids = sorted(QC.glob(f"annotated_{cam}_*_timelapse.mp4"), key=lambda p: p.stat().st_mtime)
    if not vids:
        sys.exit(f"no annotated {cam} timelapse in {QC} - run annotate_video.py first")
    VIDEOS[cam] = vids[-1].name
hms = lambda s: str(timedelta(seconds=int(s)))
clocks = {}          # per camera: PC clock of every timelapse frame, seconds since midnight
for cam, name in VIDEOS.items():
    m = re.search(r"_(\d{6})-(\d{6})_", name)
    t0, t1 = [datetime.strptime(f"{DATE} {x}", "%Y-%m-%d %H%M%S") for x in m.groups()]
    pts_all = []
    for seg in sorted(SESSION.glob(f"{cam}_*_to_*.mp4")):        # same segment selection / -ss / -t as annotate_video.py
        a = datetime.strptime(seg.name.split("_")[1] + " " + seg.name.split("_")[2], "%Y-%m-%d %H-%M-%S")
        b = datetime.strptime(seg.name.split("_")[1] + " " + seg.name.split("_to_")[1][:8], "%Y-%m-%d %H-%M-%S")
        if b <= t0 or a >= t1:
            continue
        ss = max(0.0, (t0 - a).total_seconds()); to = (t1 - a).total_seconds()
        out = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                                       "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(seg)]).decode()
        base = (a - a.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
        pts_all += [round(base + p, 2) for p in (float(x) for x in out.split() if x) if ss <= p <= to]
    clocks[cam] = pts_all
    nb = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                  "stream=nb_read_frames", "-of", "csv=p=0", str(QC / name)]).decode().strip()
    n_video = int(nb) if nb.isdigit() else 0
    print(cam, len(pts_all), "keyframes", hms(pts_all[0]), "->", hms(pts_all[-1]), "| timelapse frames:", n_video)
    if n_video and n_video != len(pts_all):
        sys.exit(f"{cam}: {len(pts_all)} keyframes but {n_video} timelapse frames - the clock table would be misaligned")
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]; TRAIN_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]; VT_Y = [39, 93, 147, 201]
names = [f"T{li}{si}" for li in range(1, 8) for si in range(1, 6)] + \
        [f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}" for i in range(1, 7) for j in range(1, 5)] + ["SWEEP-CH03", "SWEEP-CH04", "NONE"]
html = r"""<!doctype html><html><head><meta charset="utf-8"><title>Placement timeline __DATE__</title>
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
 <span>__DATE__ frame <b id="fi">0</b></span> <span id="clock">--:--:--</span> <span id="c2" style="opacity:.75"></span>
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
const C1=__CLOCKS1__, C2=__CLOCKS2__, FPS=10, N1=C1.length, N2=C2.length;   // PC clock (s since midnight) per frame
const $=id=>document.getElementById(id), v1=$('v1'), v2=$('v2');
let rows=[], start=null, end=null, cur=0;                                   // cur = current CH01 frame index (source of truth)
function hms(s){s=Math.floor(s);return [s/3600|0,(s%3600)/60|0,s%60].map(x=>String(x).padStart(2,'0')).join(':');}   // floor = burn-in convention
function frameFromTime(){return Math.max(0,Math.min(N1-1,Math.floor(v1.currentTime*FPS+0.02)));}   // frame f spans [f/FPS,(f+1)/FPS)
function f2of(f){const t=C1[f];let lo=0,hi=N2-1;while(lo<hi){const m=(lo+hi)>>1;if(C2[m]<t)lo=m+1;else hi=m;}
  if(lo>0&&t-C2[lo-1]<=C2[lo]-t)lo--;return lo;}                            // CH02 frame whose clock is nearest CH01 frame f
function clockOf(f){return hms(C1[Math.max(0,Math.min(f,N1-1))]);}
function show(){$('fi').textContent=cur;$('clock').textContent=clockOf(cur);$('slider').value=cur;const g=f2of(cur);$('c2').textContent='(CH02 frame '+g+' @ '+hms(C2[g])+')';}
function seekFrame(f){cur=Math.max(0,Math.min(Math.round(f),N1-1));v1.pause();v2.pause();
  v1.currentTime=(cur+0.5)/FPS;v2.currentTime=(f2of(cur)+0.5)/FPS;show();}   // midpoint of the frame -> unambiguous decode
function step(d){seekFrame(cur+d);}
function toggle(){if(v1.paused){v2.currentTime=(f2of(cur)+0.5)/FPS;v1.play();v2.play();}else{v1.pause();v2.pause();seekFrame(frameFromTime());}}
v1.addEventListener('timeupdate',()=>{if(v1.paused||v1.seeking)return;cur=frameFromTime();show();
  const want=(f2of(cur)+0.5)/FPS;if(Math.abs(v2.currentTime-want)>0.35)v2.currentTime=want;});   // keep CH02 within ~3 frames while playing
v1.addEventListener('ended',()=>{v2.pause();seekFrame(N1-1);});
v1.addEventListener('error',()=>{$('clock').textContent='VIDEO NOT FOUND - open this HTML from E:\\calibration\\qc';});
function markStart(){start=clockOf(cur);$('st').textContent=start;}
function markEnd(){end=clockOf(cur);$('en').textContent=end;$('sid').focus();}
function addRow(){const s=document.getElementById('sid').value.trim().toUpperCase();if(!start||!s){alert('mark start (and end) and type the station');return;}
  rows.push({start:start,end:end||start,station:s});start=end=null;document.getElementById('st').textContent='--';document.getElementById('en').textContent='--';document.getElementById('sid').value='';render();}
function delRow(i){rows.splice(i,1);render();}
function render(){const t=document.getElementById('tbl');t.innerHTML='<tr><th>#</th><th>start</th><th>end</th><th>station</th><th></th></tr>'+rows.map((r,i)=>`<tr><td>${i+1}</td><td>${r.start}</td><td>${r.end}</td><td>${r.station}</td><td><button onclick="delRow(${i})">x</button></td></tr>`).join('');
  document.getElementById('out').value=rows.map(r=>`${r.start}-${r.end}  ${r.station}`).join('\n');
  try{localStorage.setItem('__LSKEY__',JSON.stringify(rows));}catch(e){}}
function exportTxt(){render();const a=document.createElement('a');a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(document.getElementById('out').value+'\n');a.download='placement_timeline.txt';a.click();}
document.addEventListener('click',e=>{if(e.target.tagName==='BUTTON')e.target.blur();});   // so space/Enter never re-fire the last button
document.addEventListener('keydown',e=>{const typing=e.target.id==='sid';if(typing&&!['Enter','[',']'].includes(e.key))return;
  if(e.key==='ArrowLeft'){step(e.shiftKey?-10:-1);e.preventDefault();}else if(e.key==='ArrowRight'){step(e.shiftKey?10:1);e.preventDefault();}
  else if(e.key===' '){toggle();e.preventDefault();}else if(e.key==='['){markStart();e.preventDefault();}else if(e.key===']'){markEnd();e.preventDefault();}
  else if(e.key==='Enter'){addRow();e.preventDefault();}});
try{const saved=localStorage.getItem('__LSKEY__');if(saved){rows=JSON.parse(saved);render();}}catch(e){}
$('slider').max=N1-1;
v1.addEventListener('loadedmetadata',()=>{seekFrame(0);});
show();
</script></body></html>"""
lskey = "timeline_rows" if SESSION == qc_paths.DEFAULT_SESSION else f"timeline_rows_{DATE}"   # keep the 09-18 rows where they are
html = (html.replace("__V1__", VIDEOS["CH01"]).replace("__V2__", VIDEOS["CH02"])
        .replace("__CLOCKS1__", json.dumps(clocks["CH01"])).replace("__CLOCKS2__", json.dumps(clocks["CH02"]))
        .replace("__DATALIST__", "".join(f'<option value="{n}">' for n in names))
        .replace("__DATE__", DATE).replace("__LSKEY__", lskey)
        .replace("open this HTML from E:\\\\calibration\\\\qc", "open this HTML from " + str(QC).replace("\\", "\\\\")))
(QC / "timeline_gui.html").write_text(html, encoding="utf-8")
print("->", QC / "timeline_gui.html")
