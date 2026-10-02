# -*- coding: utf-8 -*-
r"""Structure from motion on drone footage of the paddock: one shared camera for every frame, a sparse 3-D model of the
walls, poles, cones and camera housings. Step one of using the drone as a survey instrument; the model is in its
own arbitrary scale and orientation until known points (cones, poles, board) tie it to the paddock.

Runs the COLMAP 4.2.1 CUDA build on the GPU (<root>\bin\colmap-4.2.1-cuda; the pip pycolmap wheel is CPU-only and
~50x slower at feature extraction here), pycolmap only reads the result. Frames come from each video at --fps
(ffmpeg, scaled to --width), photos are copied as they are (keep the SD-card originals: they carry gimbal angles
and altitude in XMP); SIFT features on the GPU, exhaustive matching on the GPU (passes from different videos only
connect that way; no vocabulary tree is downloaded), incremental mapping; every model under <out>\sparse\<i>.

Usage: python drone_sfm.py --name <run> --videos <mp4> ... [--photos <jpg> ...] [--fps 1] [--width 1920]
                           [--features 8192] [--mapper incremental|global] [--stage all|frames|features|match|map|report]
Output: <qc root>\drone_sfm\<run>\images\, database.db, sparse\<i>\, SFM_REPORT.txt
"""
import sys, shutil, subprocess, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
def many(name):
    if name not in args:
        return []
    out, i = [], args.index(name) + 1
    while i < len(args) and not args[i].startswith("--"):
        out.append(args[i]); i += 1
    return out
OUT = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", time.strftime("%Y-%m-%d"))
IMG, DB, SP = OUT / "images", OUT / "database.db", OUT / "sparse"
COLMAP = Path(opt("--colmap", str(qc_paths.ROOT / "bin" / "colmap-4.2.1-cuda" / "bin" / "colmap.exe")))
VIDEOS, PHOTOS = many("--videos"), many("--photos")
FPS, WIDTH, NFEAT, STAGE = float(opt("--fps", "1")), int(opt("--width", "1920")), int(opt("--features", "8192")), opt("--stage", "all")
OUT.mkdir(parents=True, exist_ok=True); IMG.mkdir(exist_ok=True)
log = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)
images = lambda: sorted({p.name.lower(): p for p in IMG.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")}.values())
def colmap(*a):
    t = time.time(); subprocess.run([str(COLMAP), *map(str, a)], check=True); log(f"{a[0]} {time.time() - t:.0f} s")

log(f"data root {qc_paths.ROOT}; run {OUT}")
if STAGE in ("all", "frames"):
    for v in VIDEOS:
        stem = Path(v).stem
        subprocess.run([qc_paths.FFMPEG, "-v", "error", "-y", "-i", v, "-vf", f"fps={FPS},scale={WIDTH}:-2", "-q:v", "2",
                        str(IMG / f"{stem}_%04d.jpg")], check=True)
        log(f"frames from {stem}: {len(list(IMG.glob(stem + '_*.jpg')))}")
    for p in PHOTOS:
        shutil.copy2(p, IMG / Path(p).name)
    log(f"images: {len(images())}")
if STAGE in ("all", "features"):
    if DB.exists():
        DB.rename(DB.with_name(f"database_{time.strftime('%H%M%S')}.db"))          # never mix two extractions
    colmap("feature_extractor", "--database_path", DB, "--image_path", IMG, "--ImageReader.camera_model", "OPENCV",
           "--ImageReader.single_camera", 1, "--FeatureExtraction.use_gpu", 1, "--SiftExtraction.max_num_features", NFEAT)
if STAGE in ("all", "match"):
    colmap("exhaustive_matcher", "--database_path", DB, "--FeatureMatching.use_gpu", 1)
if STAGE in ("all", "map"):
    if SP.exists():
        shutil.rmtree(SP)
    SP.mkdir()
    if opt("--mapper", "incremental") == "global":                     # COLMAP 4's global mapper: much faster, try first on big sets
        colmap("global_mapper", "--database_path", DB, "--image_path", IMG, "--output_path", SP)
    else:                                                               # bundle adjustment on the GPU (default is CPU: 17 min of
        colmap("mapper", "--database_path", DB, "--image_path", IMG, "--output_path", SP, "--Mapper.ba_use_gpu", 1)   # 414 frames, 2026-10-02)
if STAGE in ("all", "map", "report"):
    import pycolmap
    L = [f"DRONE SfM  {OUT}; {len(images())} images; videos {', '.join(Path(v).name for v in VIDEOS) or '-'}; photos {len(PHOTOS)}; "
         f"fps {FPS}, width {WIDTH}, {NFEAT} SIFT features, exhaustive matching, COLMAP {COLMAP.parent.parent.name}", ""]
    for d in sorted(p for p in SP.iterdir() if p.is_dir()):
        rec = pycolmap.Reconstruction(str(d))
        by_src = {}
        for im in rec.images.values():
            k = im.name.rsplit("_", 1)[0]; by_src[k] = by_src.get(k, 0) + 1
        cams = "; ".join(f"{c.model.name} {c.width}x{c.height} params {[round(float(x), 4) for x in c.params]}" for c in rec.cameras.values())
        L += [f"model {d.name}: {rec.num_reg_images()} images registered, {rec.num_points3D()} points, mean reprojection error "
              f"{rec.compute_mean_reprojection_error():.2f} px", f"  per source: {dict(sorted(by_src.items()))}", f"  camera: {cams}"]
    (OUT / "SFM_REPORT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    log("\n".join(L))
