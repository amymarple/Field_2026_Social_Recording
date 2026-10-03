# -*- coding: utf-8 -*-
r"""Frames for labelling the rig cameras' lenses, chosen by what each drone frame can see (operator's suggestion,
2026-10-03: the first landmark page spread its 21 frames evenly in time, so CH04's lens got one click in the big
model). Each rig camera's current position (the drone estimate in camera_centres_2026-10-03.json, else the tape) is
projected into every registered frame of the anchored model; a frame qualifies when the lens lands inside the image
(80 px margin, tested on the undistorted view first) with the drone within --max-range m (6 m for a camera with too
few closer views). Per camera --per frames are picked: the closest first, then
always the one whose viewing direction is furthest from those already picked (a wide spread of directions is what
triangulates a point). Frames the operator already labelled are left out.

The page is the landmark GUI with a dashed ring where the current estimate puts each lens: a guide, never a label
(the estimate can be 20-30 cm off). A contact sheet of the crops around every ring is written for review.

Usage: python drone_cam_frames.py --name 2026-10-02_all [--model 1] [--per 8] [--max-range 3.5]
Output: <run>\landmark_gui_cams\drone_landmarks.html (+ frames\, cam_frames.json, contact_sheet.jpg)
"""
import sys, json, shutil
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402
from scipy.spatial.transform import Rotation                             # noqa: E402
import drone_landmark_gui as gui                                         # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
MODEL, PER, MAX_RANGE, MARGIN = opt("--model", "1"), int(opt("--per", "8")), float(opt("--max-range", "3.5")), 80
OUT = RUN / "landmark_gui_cams"; (OUT / "frames").mkdir(parents=True, exist_ok=True)
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
A = json.loads((RUN / "anchor" / "anchor.json").read_text(encoding="utf-8"))[MODEL]
s, Rm, t = A["scale"], Rotation.from_rotvec(A["rotvec"]).as_matrix(), np.asarray(A["t"])
cc = json.loads((qc_paths.QC_ROOT / "camera_centres_2026-10-03.json").read_text(encoding="utf-8"))
target = {c: np.array([v["x_m"], v["y_m"], v["z_m"]]) for c, v in cc["drone"].items()}
for c, v in cc["tape"].items():
    target.setdefault(c, np.array([v["x_in"] * 0.0254, v["y_in"] * 0.0254, v["h_m"]]))
done = set()
lab = RUN / "landmark_gui" / "drone_landmarks.json"
if lab.exists():
    done = {f["name"] for f in json.loads(lab.read_text(encoding="utf-8"))["frames"]}

seen = {c: [] for c in target}                                           # camera -> (frame, range m, uv, unit dir lens->drone)
for im in rec.images.values():
    cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
    Rc, tc = T.rotation.matrix(), T.translation
    D = s * Rm @ im.projection_center() + t                              # drone position, paddock m
    for c, P in target.items():
        Xc = Rc @ (Rm.T @ (P - t) / s) + tc
        rng = float(np.linalg.norm(Xc) * s)
        if Xc[2] <= 0 or rng > 6.0:
            continue
        fx, fy, cx, cy = cam.params[:4]                                  # field of view first: the OPENCV polynomial (k2 < 0)
        if abs(Xc[0] / Xc[2]) > cx / fx or abs(Xc[1] / Xc[2]) > cy / fy:  # folds points far outside it back into the image
            continue
        uv = cam.img_from_cam(np.array([Xc]))[0]
        if not (MARGIN <= uv[0] < cam.width - MARGIN and MARGIN <= uv[1] < cam.height - MARGIN):
            continue
        seen[c].append((im.name, rng, uv, (D - P) / np.linalg.norm(D - P)))

pick, report = {}, []
for c in sorted(seen):
    cand = [x for x in seen[c] if x[1] <= MAX_RANGE and x[0] not in done]
    if len(cand) < PER:                                                  # CH04: the drone never came within 3.5 m of it
        cand = [x for x in seen[c] if x[0] not in done]
    chosen = []
    if cand:
        chosen.append(min(cand, key=lambda x: x[1]))
        while len(chosen) < min(PER, len(cand)):
            rest = [x for x in cand if x[0] not in {y[0] for y in chosen}]
            sep = [min(np.degrees(np.arccos(np.clip(x[3] @ y[3], -1, 1))) for y in chosen) for x in rest]
            chosen.append(rest[int(np.argmax(sep))])
    pick[c] = chosen
    spread = max((np.degrees(np.arccos(np.clip(x[3] @ y[3], -1, 1))) for x in chosen for y in chosen), default=0)
    report.append(f"{c}: {len(seen[c])} frames see it within 6 m, {len(cand)} within {MAX_RANGE} m and not yet labelled; "
                  f"picked {len(chosen)} at {', '.join(f'{x[1]:.1f}' for x in chosen)} m, directions spread over {spread:.0f} deg")

names = sorted({x[0] for L in pick.values() for x in L})
hints = {n: {} for n in names}
for c, L in seen.items():
    for n, rng, uv, _ in L:
        if n in hints:
            hints[n][f"{c} lens"] = [round(float(uv[0]), 1), round(float(uv[1]), 1)]
frames = []
for n in names:
    flat = n.replace("/", "__").replace("\\", "__")
    shutil.copy2(RUN / "images" / n, OUT / "frames" / flat)
    frames.append(dict(model=MODEL, name=n, file=f"frames/{flat}"))
task = ("Rig camera lenses only. A dashed yellow ring marks where the current estimate puts a lens (it can be 20-30 cm "
        "off, so look around it). Click the centre of the lens: for CH01 / CH02 (Duo 3, two lenses) the point midway "
        "between the two lenses. Skip a frame where the lens is hidden or you are not sure which camera it is.")
gui.build(OUT, frames, RUN.name, hints=hints, page_id="_cams", task=task, title="Rig Camera Lenses")
(OUT / "cam_frames.json").write_text(json.dumps({c: [dict(frame=x[0], range_m=round(x[1], 2), u=round(float(x[2][0]), 1),
                                                          v=round(float(x[2][1]), 1)) for x in L] for c, L in pick.items()}, indent=1),
                                     encoding="utf-8")
tiles = []                                                               # contact sheet: 360 px crops around each ring
for c in sorted(pick):
    row = []
    for n, rng, uv, _ in pick[c]:
        im = cv2.imread(str(RUN / "images" / n)); H, W = im.shape[:2]
        u, v = int(round(uv[0])), int(round(uv[1])); h = 180
        crop = cv2.copyMakeBorder(im, h, h, h, h, cv2.BORDER_CONSTANT)[v:v + 2 * h, u:u + 2 * h].copy()
        cv2.circle(crop, (h, h), 40, (61, 210, 255), 2)
        cv2.putText(crop, f"{c} {Path(n).stem[5:]} {rng:.1f}m", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        row.append(crop)
    row += [np.zeros((360, 360, 3), np.uint8)] * (PER - len(row))
    tiles.append(np.hstack(row))
cv2.imwrite(str(OUT / "contact_sheet.jpg"), np.vstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 85])
print("\n".join(report))
print(f"{len(frames)} frames ->", OUT / "drone_landmarks.html")
