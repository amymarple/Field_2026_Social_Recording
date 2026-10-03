# -*- coding: utf-8 -*-
r"""Register extra frames from chosen moments of the drone videos into an existing drone_sfm.py model, without moving
the model (2026-10-03: the operator's CH04 close-ups, PTSC_0014 45-55 s and PTSC_0015 0-15 / 25-36 s, where the
1-fps frames leave CH04 at the top edge). Frames are cut at --fps from each window at the model's width, SIFT on the
GPU into a COPY of the run's database (sharing the model's camera), matched only against the model's frames of the
same video within +-6 s and the new frames within +-1 s, then COLMAP's image_registrator adds them to a copy of the
model: no bundle adjustment, no triangulation, so every old pose and point stays where the landmark anchor put it.

Usage: python drone_register_frames.py --name 2026-10-02_all --model 1 --tag ch04 --fps 5
                                      --windows PTSC_0014:44-56,PTSC_0015:0-16,PTSC_0015:24.5-36.5 [--videos F:\ATOM_001\DCIM]
Output: <run>\images\<sub>_<tag>\<video>_t<ms>.jpg, <run>\database_<tag>.db, <run>\sparse\<model>_<tag>\ (+ printed report)
"""
import sys, re, shutil, subprocess, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
MODEL, TAG, FPS = opt("--model", "1"), opt("--tag", "extra"), float(opt("--fps", "5"))
VID = Path(opt("--videos", r"F:\ATOM_001\DCIM"))
COLMAP = qc_paths.ROOT / "bin" / "colmap-4.2.1-cuda" / "bin" / "colmap.exe"
WIN = [(w.split(":")[0], *map(float, w.split(":")[1].split("-"))) for w in opt("--windows").split(",")]
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
names = sorted(im.name for im in rec.images.values())
sub = names[0].split("/")[0]                                             # the model's image folder (e.g. d1002)
NEW = RUN / "images" / f"{sub}_{TAG}"; NEW.mkdir(parents=True, exist_ok=True)
log = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)


def colmap(*a):
    t = time.time(); subprocess.run([str(COLMAP), *map(str, a)], check=True, stdout=subprocess.DEVNULL); log(f"{a[0]} {time.time() - t:.0f} s")


new = []
for v, a, b in WIN:                                                      # frame i of a window sits at a + i / fps
    tmp = NEW / "_tmp"; tmp.mkdir(exist_ok=True)
    subprocess.run([qc_paths.FFMPEG, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(VID / f"{v}.MP4"),
                    "-vf", f"fps={FPS},scale=1920:-2", "-q:v", "2", str(tmp / "%05d.jpg")], check=True)
    for f in sorted(tmp.glob("*.jpg")):
        ms = int(round((a + (int(f.stem) - 1) / FPS) * 1000)); dst = NEW / f"{v}_t{ms:06d}.jpg"
        f.replace(dst); new.append(f"{NEW.name}/{dst.name}")
    tmp.rmdir()
new = sorted(set(new)); log(f"{len(new)} frames cut into {NEW}")
DB = RUN / f"database_{TAG}.db"
if not DB.exists():
    shutil.copy2(RUN / "database.db", DB)
cam_id = next(iter(rec.cameras))
lst = RUN / f"new_{TAG}.txt"; lst.write_text("\n".join(new) + "\n", encoding="utf-8")
colmap("feature_extractor", "--database_path", DB, "--image_path", RUN / "images", "--image_list_path", lst,
       "--ImageReader.existing_camera_id", cam_id, "--FeatureExtraction.use_gpu", 1, "--SiftExtraction.max_num_features", 8192)


def when(n):
    m = re.search(r"(PTSC_\d+)_t(\d+)\.jpg$", n)
    if m:
        return m.group(1), int(m.group(2)) / 1000
    m = re.search(r"(PTSC_\d+)_(\d+)\.jpg$", n)
    return m.group(1), int(m.group(2)) - 1.0                             # 1-fps frame k sits at k - 1 s


old_t = [(n, *when(n)) for n in names]
pairs = []
for n in new:
    v, t = when(n)
    pairs += [(n, o) for o, vo, to in old_t if vo == v and abs(to - t) <= 6]
    pairs += [(n, m) for m in new if m > n and when(m)[0] == v and abs(when(m)[1] - t) <= 1]
pl = RUN / f"pairs_{TAG}.txt"; pl.write_text("\n".join(f"{a} {b}" for a, b in pairs) + "\n", encoding="utf-8")
log(f"{len(pairs)} pairs")
colmap("matches_importer", "--database_path", DB, "--match_list_path", pl, "--match_type", "pairs", "--FeatureMatching.use_gpu", 1,
       "--TwoViewGeometry.min_num_inliers", 40)
OUTM = RUN / "sparse" / f"{MODEL}_{TAG}"; OUTM.mkdir(exist_ok=True)
colmap("image_registrator", "--database_path", DB, "--input_path", RUN / "sparse" / MODEL, "--output_path", OUTM,
       "--Mapper.abs_pose_min_num_inliers", 60)
r2 = pycolmap.Reconstruction(str(OUTM))
reg = sorted(im.name for im in r2.images.values() if im.name in set(new))
old = {im.name: im for im in rec.images.values()}
moved = max(np.linalg.norm(im.projection_center() - old[im.name].projection_center()) for im in r2.images.values() if im.name in old)
same_cam = np.allclose(r2.cameras[cam_id].params, rec.cameras[cam_id].params)
log(f"registered {len(reg)} of {len(new)} new frames into {OUTM}; old poses moved at most {moved:.2e} units; camera unchanged: {same_cam}")
for v, a, b in WIN:
    k = [n for n in reg if when(n)[0] == v and a <= when(n)[1] <= b]
    log(f"  {v} {a:g}-{b:g} s: {len(k)} registered")
