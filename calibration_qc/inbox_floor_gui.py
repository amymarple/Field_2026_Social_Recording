# -*- coding: utf-8 -*-
r"""Labelling page for the in-box cameras' floor (CH07 in house_2, CH08 in house_1), 2026-10-10.

The in-box cameras sit in the house lids and look down on the floor. To map them into the paddock (pixel -> floor of
the house -> paddock through the house's pose) the floor rectangle must be located in the image: its four corners and
its four edges where the walls meet the floor (bedding surface), and the four vertical wall joints (their lines meet at
the point straight below the lens). The analysis repo's in-box labels (FOODBOX, DOORFRAME, INNER_EDGES) are unnamed
and made for tracking the camera between lid events; they are drawn here as dashed guides only.

Frames: the lid-closed segment 2026-09-04 08:31 -> 13:35 (between the AM round and the probe advances), the segment of
the analysis repo's in-box reference frame 09-04 12:00:02 (cv/configs/cohort3_lid_events.json, frame_correction.py).
The camera does not move inside a segment, so every frame of a camera shares its pixel coordinates: label each item
once, on whichever frame shows it best. Names are IMAGE sides as the frame is shown (top / bottom / left / right).

Usage: python inbox_floor_gui.py [--date 2026-09-04] [--times 09:00:00,10:00:00,11:00:00,12:00:02,13:00:00]
Output: <qc root>\inbox_floor\inbox_floor_labels.html (+ frames\); Export writes inbox_floor_labels.json
"""
import sys, json, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
DATE = opt("--date", "2026-09-04")
TIMES = opt("--times", "09:00:00,10:00:00,11:00:00,12:00:02,13:00:00").split(",")
CAMS = ("CH07", "CH08")
COHORT = Path(opt("--cohort-root", r"F:\3rd_rat"))
LM = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c")
OUT = qc_paths.QC_ROOT / "inbox_floor"; (OUT / "frames").mkdir(parents=True, exist_ok=True)


def segment_file(cam, t):
    """the closed hourly file holding field-PC time t and the offset into it (s); the file name carries its start"""
    best = None
    for f in sorted((COHORT / DATE / cam).glob(f"{cam}_{DATE}_*_to_*.mp4")):
        s = datetime.strptime(f"{DATE} {f.stem.split('_')[2]}", "%Y-%m-%d %H-%M-%S")
        if s <= t:
            best = (f, (t - s).total_seconds())
    return best


frames = []
for cam in CAMS:
    for hms in TIMES:
        t = datetime.strptime(f"{DATE} {hms}", "%Y-%m-%d %H:%M:%S")
        f, off = segment_file(cam, t)
        name = f"{cam}_{t:%Y%m%d_%H%M%S}.jpg"
        dst = OUT / "frames" / name
        if not dst.exists():
            subprocess.run([qc_paths.FFMPEG, "-v", "error", "-ss", f"{off:.3f}", "-i", str(f), "-frames:v", "1", "-q:v", "2", str(dst)], check=True)
        frames.append(dict(camera=cam, time=f"{t:%Y-%m-%d %H:%M:%S}", name=name, file=f"frames/{name}", source=f.name, offset_s=off))

guides = {}
for cam in CAMS:
    fs = sorted(LM.glob(f"landmarks_{cam}_{DATE.replace('-', '')}_1200*.json"))
    if fs:
        L = json.loads(fs[-1].read_text(encoding="utf-8"))["landmarks"]
        guides[cam] = {k: v for k, v in L.items() if k in ("FOODBOX", "DOORFRAME", "INNER_EDGES")}

Q = ("top-left", "top-right", "bottom-left", "bottom-right")
groups = [
    dict(title="Floor corners (point)", quad=True,
         items=[dict(name=f"floor corner {q}", kind="point", label=q) for q in Q],
         hint="Where two walls meet the floor (the bedding surface), at the image's top-left, top-right ... corner of the floor. "
              "Skip a corner hidden under the food box, a rat or deep bedding; the edges below still place it."),
    dict(title="Floor edges (several clicks along each)", quad=True,
         items=[dict(name=f"floor edge {s}", kind="line", label=s) for s in ("top", "bottom", "left", "right")],
         hint="The line where each wall meets the floor / bedding: 3-6 clicks along the stretches you can see. Across a door "
              "opening, click along the sill (the bottom of the opening) if it is in line with the wall foot, otherwise skip it."),
    dict(title="Wall joints (several clicks along each)", quad=True,
         items=[dict(name=f"wall joint {q}", kind="line", label=q) for q in Q],
         hint="The vertical edge where two walls meet, from the floor up towards the frame edge: 2-4 clicks along it. "
              "These four lines meet at the point straight below the lens."),
    dict(title="Door openings (several clicks along each)", quad=False,
         items=[dict(name=f"door {s} {e}", kind="line", label=f"door {s}: {e}") for s in ("left", "right") for e in ("near side", "far side")],
         hint="Optional: the two vertical sides of each door opening (left / right wall of the image), 2-3 clicks each, as "
              "far down as you can see them. They give the door's position along the wall."),
]
task = (f"Label the floor of each house box: CH07 = inside house_2, CH08 = inside house_1; frames {DATE} {TIMES[0]} - {TIMES[-1]}, "
        "one lid-closed segment, so the camera did not move: label each item once, on the frame where it is clearest. "
        "Top / bottom / left / right are sides of the image as shown. When done: Export, and give the json to Claude.")
page = (Path(__file__).resolve().parent / "inbox_floor_gui_template.html").read_text(encoding="utf-8")
page = (page.replace("__FRAMES__", json.dumps(frames)).replace("__GROUPS__", json.dumps(groups)).replace("__GUIDES__", json.dumps(guides))
        .replace("__RUN__", json.dumps(f"inbox_floor_{DATE}")).replace("__TASK__", json.dumps(task)))
(OUT / "inbox_floor_labels.html").write_text(page, encoding="utf-8")
(OUT / "frames.json").write_text(json.dumps(frames, indent=1), encoding="utf-8")
print(len(frames), "frames ->", OUT / "inbox_floor_labels.html")
