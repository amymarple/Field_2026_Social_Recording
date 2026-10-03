# -*- coding: utf-8 -*-
r"""Landmark labelling page for drone_sfm.py models: the operator clicks named rigid landmarks (pole feet and tops,
the rig cameras, the two water towers, house roofs) in a few frames of every model; drone_landmark_anchor.py then triangulates them inside
each model and moves the model into the paddock frame. Identity comes only from the operator (detect-then-decode):
the paddock looks the same turned 180 deg, which is exactly what fooled the reconstruction.

Frames: --per-model frames per model, evenly spread over its registered frames in name (= time) order, copied at the
size the model used (their pixels are the model's pixels). Page: pick a landmark (buttons laid out like the paddock),
click it in the frame; wheel zooms, drag pans, a click on a placed point selects it (Delete removes it); left / right
arrows change frame, Export writes drone_landmarks.json. Labels are kept in the browser between sessions.

Usage: python drone_landmark_gui.py --name 2026-10-02_anchor [--models 1,2,3] [--per-model 10]
Output: <qc root>\drone_sfm\<run>\landmark_gui\drone_landmarks.html (+ frames\)
"""
import sys, json, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_anchor")
MODELS, PER = opt("--models", "1,2,3").split(","), int(opt("--per-model", "10"))
OUT = RUN / "landmark_gui"; (OUT / "frames").mkdir(parents=True, exist_ok=True)
frames = []
for m in MODELS:
    rec = pycolmap.Reconstruction(str(RUN / "sparse" / m))
    names = sorted(im.name for im in rec.images.values())
    pick = [names[round(i * (len(names) - 1) / max(1, PER - 1))] for i in range(min(PER, len(names)))]
    for n in dict.fromkeys(pick):
        flat = n.replace("/", "__").replace("\\", "__")
        shutil.copy2(RUN / "images" / n, OUT / "frames" / flat)
        frames.append(dict(model=m, name=n, file=f"frames/{flat}"))
POLES = [f"{r}{c}" for r in "CBA" for c in range(5)]
LM = ([f"{p} foot" for p in POLES] + [f"{p} top" for p in POLES] + [f"CH0{i} lens" for i in range(1, 7)]
      + ["TOWER_1 top", "TOWER_1 base", "TOWER_2 top", "TOWER_2 base", "HOUSE_1 roof peak", "HOUSE_2 roof peak", "PC box top"])
page = (Path(__file__).resolve().parent / "drone_landmark_gui_template.html").read_text(encoding="utf-8")
(OUT / "drone_landmarks.html").write_text(page.replace("__FRAMES__", json.dumps(frames)).replace("__RUN__", json.dumps(RUN.name))
                                         .replace("__LM__", json.dumps(LM)), encoding="utf-8")
print(f"{len(frames)} frames from models {', '.join(MODELS)} ->", OUT / "drone_landmarks.html")
