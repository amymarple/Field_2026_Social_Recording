# -*- coding: utf-8 -*-
r"""Paddock showcase: the 2026-10-03 drone footage (cones already removed) with the paddock's geometry drawn into it as
3-D annotations - size, poles, houses and the eight cameras - for talks (2026-10-22). Two shots: PTSC_0020, one
continuous approach from above the barn down to the paddock, and PTSC_0021_0001, low passes around the outside of the
walls.

Stages:
  sfm     frames of both videos at 3 fps (1920 wide) + the 120 frames of the 09-30 model 0, COLMAP 4.2.1 CUDA: SIFT,
          sequential matching inside each video (neighbours by name) + a pairs list across videos and days (every 3rd
          frame), incremental mapping -> <qc root>\drone_sfm\2026-10-03_showcase\sparse\<i>. Exhaustive matching of
          ~1600 frames would be 1.3 M pairs; this is ~60 k.
  align   the model is tied to the paddock frame by the 09-30 frames: their centres in this model vs in model 0 moved by
          its anchor (drone_sfm 2026-10-02_all/anchor/anchor.json) -> one similarity (Umeyama), residuals reported.
  poses   per video, the keyframe poses (3 fps) in the paddock frame, interpolated to every video frame (slerp for the
          rotation, a cubic spline for the centre).
  still   a few frames of one video with every annotation and the poles as red 3-D lines, to check the alignment by eye.
  render  the film: one or more segments (video:start:duration), 1920 x 1080, annotations fading in one group at a time
          over the film's clock, a dip to black between segments, H.264.
Geometry (paddock frame, m; origin pole A0, x along the 40-ft side, y along the 20-ft side, z up): the inner
rectangle 12.19 x 6.10 m (480 x 240 in, design); poles from the analysis repo's occluders.json (rev g, B1-B3 measured,
the rest design; 2.4 m); the houses where they stood on 10-03 (house_check 09-18 fit; house_1 had been moved on
09-18); camera centres from the release (rev g) and the in-box models (cohort_ties_2026c.json).

Usage: python paddock_showcase.py --stage sfm [--step all|frames|features|match|map]
       python paddock_showcase.py --stage align [--sparse sparse_sub] | poses
         (--sparse: the model folder; sparse_sub = COLMAP mapper with --image_list_path on the chosen segments - the
         incremental mapper on all ~1600 frames ran > 10 h on the CPU, this build's Ceres has no CUDA)
       python paddock_showcase.py --stage still --video PTSC_0020 --times 10,30,50
       python paddock_showcase.py --stage render --segments PTSC_0020:15:60:3,PTSC_0021_0001:62:30:3 [--talk] [--out name.mp4]
         (video:start:source seconds:speed; --talk = the compressed fade-in schedule of a ~30 s film)
Output: <qc root>\paddock_showcase\ (ALIGN.txt, POSES.txt, poses_<video>.npz, still_<video>_<t>.jpg, the film)
"""
import sys, json, shutil, subprocess, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cv2                                                                # noqa: E402
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
STAGE = opt("--stage", "align")
OUT = qc_paths.QC_ROOT / "paddock_showcase"; OUT.mkdir(parents=True, exist_ok=True)
SFM = qc_paths.QC_ROOT / "drone_sfm" / "2026-10-03_showcase"
REF = qc_paths.QC_ROOT / "drone_sfm" / "2026-10-02_all"
VIDEOS = {"PTSC_0020": Path(r"F:\ATOM_001\DCIM\PTSC_0020.MP4"), "PTSC_0021_0001": Path(r"F:\ATOM_001\DCIM\PTSC_0021_0001.MP4")}
KEY_FPS = 3.0
W, H = 1920, 1080
IN = 0.0254
FONT_B, FONT_R = r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"   # the talk deck's font (Arial)
log = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)


def video_of(name):
    """image name -> (video key, frame number) for the shot frames; None for the 09-30 frames"""
    stem = Path(name).stem
    for v in VIDEOS:
        if stem.startswith(v + "_") and stem[len(v) + 1:].isdigit():
            return v, int(stem[len(v) + 1:])
    return None


# ------------------------------------------------------------------------------------------------ sfm
if STAGE == "sfm":
    COLMAP = qc_paths.ROOT / "bin" / "colmap-4.2.1-cuda" / "bin" / "colmap.exe"
    IMG, DB, SP = SFM / "images", SFM / "database.db", SFM / "sparse"
    IMG.mkdir(parents=True, exist_ok=True)
    step = opt("--step", "all")

    def colmap(*a):
        t = time.time(); subprocess.run([str(COLMAP), *map(str, a)], check=True); log(f"{a[0]} {time.time() - t:.0f} s")
    if step in ("all", "frames"):
        for v, path in VIDEOS.items():
            for f in IMG.glob(v + "_*.jpg"):
                f.unlink()
            subprocess.run([qc_paths.FFMPEG, "-v", "error", "-y", "-i", str(path), "-vf", f"fps={KEY_FPS},scale={W}:-2", "-q:v", "2",
                            str(IMG / f"{v}_%04d.jpg")], check=True)
            log(f"frames from {v}: {len(list(IMG.glob(v + '_*.jpg')))}")
        for f in (REF / "images" / "d0930").glob("*.jpg"):
            shutil.copy2(f, IMG / f.name)
        log(f"images: {len(list(IMG.glob('*.jpg')))}")
    if step in ("all", "features"):
        if DB.exists():
            DB.rename(DB.with_name(f"database_{time.strftime('%H%M%S')}.db"))      # never mix two extractions
        colmap("feature_extractor", "--database_path", DB, "--image_path", IMG, "--ImageReader.camera_model", "OPENCV",
               "--ImageReader.single_camera", 1, "--FeatureExtraction.use_gpu", 1, "--SiftExtraction.max_num_features", 8192)
    if step in ("all", "match"):
        colmap("sequential_matcher", "--database_path", DB, "--SequentialMatching.overlap", 12, "--SequentialMatching.loop_detection", 0,
               "--FeatureMatching.use_gpu", 1)
        names = sorted(f.name for f in IMG.glob("*.jpg"))
        groups = {}
        for n in names:
            k = video_of(n); groups.setdefault(k[0] if k else "d0930", []).append(n)
        sub = {g: v[::3] for g, v in groups.items()}
        sub["d0930"] = groups["d0930"][::2]
        pairs = set(); keys = sorted(sub)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                pairs |= {(x, y) for x in sub[a] for y in sub[b]}
        (SFM / "pairs_cross.txt").write_text("\n".join(f"{x} {y}" for x, y in sorted(pairs)) + "\n", encoding="utf-8")
        log(f"cross pairs: {len(pairs)} ({', '.join(f'{g} {len(v)}' for g, v in sub.items())})")
        colmap("matches_importer", "--database_path", DB, "--match_list_path", SFM / "pairs_cross.txt", "--match_type", "pairs",
               "--FeatureMatching.use_gpu", 1)
    if step in ("all", "map"):
        if SP.exists():
            shutil.rmtree(SP)
        SP.mkdir()
        colmap("mapper", "--database_path", DB, "--image_path", IMG, "--output_path", SP, "--Mapper.ba_use_gpu", 1)
        import pycolmap
        L = []
        for d in sorted(p for p in SP.iterdir() if p.is_dir()):
            rec = pycolmap.Reconstruction(str(d)); by = {}
            for im in rec.images.values():
                k = video_of(im.name); g = k[0] if k else "d0930"; by[g] = by.get(g, 0) + 1
            L.append(f"model {d.name}: {rec.num_reg_images()} images {by}, {rec.num_points3D()} points, reprojection "
                     f"{rec.compute_mean_reprojection_error():.2f} px")
        (SFM / "SFM_REPORT.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        log("\n".join(L))


def umeyama(src, dst):
    """similarity dst ~ s R src + t (least squares)"""
    ms, md = src.mean(0), dst.mean(0); a, b = src - ms, dst - md
    U, S, Vt = np.linalg.svd(b.T @ a / len(src))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt; s = np.trace(np.diag(S) @ D) / (a ** 2).sum(1).mean()
    return s, R, md - s * R @ ms


def centres(rec):
    return {Path(im.name).name: np.asarray(im.projection_center(), float) for im in rec.images.values()}


def best_model():
    import pycolmap
    best = None
    for d in sorted(p for p in (SFM / opt("--sparse", "sparse")).iterdir() if p.is_dir()):
        rec = pycolmap.Reconstruction(str(d))
        n = sum(1 for im in rec.images.values() if video_of(im.name))
        if best is None or n > best[0]:
            best = (n, d, rec)
    return best[1], best[2]


# ------------------------------------------------------------------------------------------------ align
if STAGE == "align":
    import pycolmap
    d, rec = best_model()
    a0 = json.loads((REF / "anchor" / "anchor.json").read_text(encoding="utf-8"))["0"]
    s0, R0, t0 = a0["scale"], cv2.Rodrigues(np.array(a0["rotvec"], float))[0], np.array(a0["t"], float)
    ref = centres(pycolmap.Reconstruction(str(REF / "sparse" / "0")))
    new = centres(rec)
    per = {v: sum(1 for k in new if k.startswith(v + "_")) for v in VIDEOS}
    L = [f"SHOWCASE ALIGN  model {d} ({rec.num_reg_images()} images, per shot {per}, {rec.num_points3D()} points, "
         f"reprojection {rec.compute_mean_reprojection_error():.2f} px)"]
    common = sorted(k for k in new if k in ref and k.startswith("PTSC_0001"))
    if opt("--method", "shared") == "shared":
        src = np.array([new[k] for k in common]); dst = np.array([s0 * R0 @ ref[k] + t0 for k in common])
        s, R, t = umeyama(src, dst)
        res = np.linalg.norm((s * src @ R.T + t) - dst, axis=1)
        keep = res < max(0.05, 3 * np.median(res))                       # drop gross outliers once
        s, R, t = umeyama(src[keep], dst[keep]); res = np.linalg.norm((s * src @ R.T + t) - dst, axis=1)
        L.append(f"tie: {len(common)} shared 09-30 frames ({keep.sum()} kept) -> paddock via model 0's anchor; scale {s:.5f}; "
                 f"centre residual median {np.median(res[keep]) * 1000:.0f} mm, p90 {np.percentile(res[keep], 90) * 1000:.0f} mm, max {res.max() * 1000:.0f} mm")
    else:
        # gps-icp: the 09-30 and 10-03 frames share no features (3 pairs, ~15 inliers), so (1) the drone's GPS ties the
        # 10-03 model coarsely - local ENU -> paddock from the 09-30 frames' GPS and anchored centres - and (2) a
        # trimmed similarity ICP of the model's points onto the anchored 09-30 + 10-02 clouds refines it.
        import re
        from scipy.spatial import cKDTree

        def srt(path):
            txt = Path(path).read_text(encoding="utf-8", errors="replace"); out = []
            for m in re.finditer(r"(\d+):(\d+):(\d+),(\d+) -->.*?\n.*?H:(-?[\d.]+)m.*?GPS:\((-?[\d.]+),(-?[\d.]+)\)", txt):
                h_, m_, s_, ms, H_, lon, lat = m.groups()
                out.append((int(h_) * 3600 + int(m_) * 60 + int(s_) + int(ms) / 1000, float(lat), float(lon), float(H_)))
            return np.array(out)
        g30 = srt(r"F:\ATOM_001\DCIM\PTSC_0001.SRT")
        lat0, lon0 = g30[:, 1].mean(), g30[:, 2].mean()
        def enu(g, tq):
            lat = np.interp(tq, g[:, 0], g[:, 1]); lon = np.interp(tq, g[:, 0], g[:, 2]); hh = np.interp(tq, g[:, 0], g[:, 3])
            return np.c_[(lon - lon0) * np.cos(np.radians(lat0)) * 111320.0, (lat - lat0) * 110574.0, hh]
        ks = sorted(k for k in ref if Path(k).name.startswith("PTSC_0001"))
        pad30 = np.array([s0 * R0 @ ref[k] + t0 for k in ks])
        e30 = enu(g30, np.array([int(Path(k).stem.split("_")[-1]) - 1 for k in ks], float))
        sE, RE, tE = umeyama(e30, pad30)
        rE = np.linalg.norm(sE * e30 @ RE.T + tE - pad30, axis=1)
        src, dst = [], []
        for k, C in new.items():
            vk = video_of(k)
            if vk:
                gv = srt(VIDEOS[vk[0]].with_suffix(".SRT"))
                src.append(C); dst.append(sE * RE @ enu(gv, np.array([(vk[1] - 1) / KEY_FPS]))[0] + tE)
        src, dst = np.array(src), np.array(dst)
        s, R, t = umeyama(src, dst); rG = np.linalg.norm(s * src @ R.T + t - dst, axis=1)
        L.append(f"GPS: ENU -> paddock from {len(ks)} 09-30 frames, residual median {np.median(rE):.2f} m; 10-03 model -> paddock "
                 f"from {len(src)} frames' GPS, scale {s:.4f}, residual median {np.median(rG):.2f} m, p90 {np.percentile(rG, 90):.2f} m")

        def read_ply(p):
            b = Path(p).read_bytes(); i = b.index(b"end_header") + len(b"end_header\n")
            n = int(re.search(rb"element vertex (\d+)", b[:i]).group(1))
            dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
            a = np.frombuffer(b[i:i + n * dt.itemsize], dt)
            return np.c_[a["x"], a["y"], a["z"]].astype(float)
        box = lambda X: X[(X[:, 0] > -3) & (X[:, 0] < 15.5) & (X[:, 1] > -3) & (X[:, 1] < 9) & (X[:, 2] > -0.5) & (X[:, 2] < 3.5)]
        tgt = box(np.vstack([read_ply(REF / "anchor" / "paddock_points_0.ply"), read_ply(REF / "anchor" / "paddock_points_1.ply")]))
        tree = cKDTree(tgt)
        P0 = np.array([p.xyz for p in rec.points3D.values()], float)
        for dmax in ((2.0, 1.0, 0.6, 0.35, 0.2, 0.12, 0.08) if "--no-icp" not in args else ()):
            for _ in range(8):
                X = box(s * P0 @ R.T + t)
                dd, ii = tree.query(X, distance_upper_bound=dmax)
                ok = np.isfinite(dd)
                if ok.sum() < 200:
                    break
                cut = np.percentile(dd[ok], 80); ok &= dd <= cut
                ds, dR, dt_ = umeyama(X[ok], tgt[ii[ok]])
                s, R, t = ds * s, dR @ R, ds * dR @ t + dt_
        X = box(s * P0 @ R.T + t); dd, _ = tree.query(X)
        L.append(f"ICP onto the anchored 09-30 + 10-02 clouds ({len(tgt)} points in the paddock box): scale {s:.4f}; of {len(X)} model "
                 f"points in the box, {np.mean(dd < 0.05) * 100:.0f} % within 5 cm, {np.mean(dd < 0.10) * 100:.0f} % within 10 cm, "
                 f"median distance {np.median(dd) * 1000:.0f} mm")
    (OUT / "ALIGN.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    np.savez(OUT / "align.npz", s=s, R=R, t=t, model=str(d))
    print("\n".join(L))

# ------------------------------------------------------------------------------------------------ poses
if STAGE == "poses":
    import pycolmap
    from scipy.spatial.transform import Rotation, Slerp
    from scipy.interpolate import CubicSpline
    al = np.load(OUT / "align.npz"); s, R, t = float(al["s"]), al["R"], al["t"]
    rec = pycolmap.Reconstruction(str(al["model"]))
    cam = next(iter(rec.cameras.values()))
    L = []
    for v, path in VIDEOS.items():
        kt, kC, kR = [], [], []
        for im in rec.images.values():
            k = video_of(im.name)
            if not k or k[0] != v:
                continue
            P = im.cam_from_world() if callable(getattr(im, "cam_from_world", None)) else im.cam_from_world
            Rw = np.asarray(P.rotation.matrix(), float)                  # world (model) -> camera
            kt.append((k[1] - 1) / KEY_FPS); kC.append(s * R @ np.asarray(im.projection_center(), float) + t); kR.append(Rw @ R.T)
        if len(kt) < 4:
            L.append(f"{v}: only {len(kt)} keyframes registered - skipped"); continue
        o = np.argsort(kt); kt, kC, kR = np.array(kt)[o], np.array(kC)[o], np.array(kR)[o]
        gaps = np.diff(kt)
        cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS); nf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
        ft = np.arange(nf) / fps
        ok = (ft >= kt[0]) & (ft <= kt[-1])
        Cs = CubicSpline(kt, kC, axis=0)(ft[ok])
        Rs = Slerp(kt, Rotation.from_matrix(kR))(ft[ok]).as_matrix()
        big = gaps > 1.0                                                  # interpolation over > 1 s is not trusted
        bad = np.zeros(ok.sum(), bool)
        for a_, b_ in zip(kt[:-1][big], kt[1:][big]):
            bad |= (ft[ok] > a_) & (ft[ok] < b_)
        np.savez(OUT / f"poses_{v}.npz", t=ft[ok], C=Cs, R=Rs, bad=bad, fps=fps, cam_model=cam.model.name,
                 cam_params=np.asarray(cam.params, float), cam_size=[cam.width, cam.height], kt=kt, kC=kC)
        L += [f"{v}: {len(kt)} keyframes of {int(nf / fps * KEY_FPS) + 1}, {kt[0]:.1f} .. {kt[-1]:.1f} s; gaps > 1 s: "
              f"{int(big.sum())} ({', '.join(f'{a_:.1f}-{b_:.1f}' for a_, b_ in zip(kt[:-1][big], kt[1:][big])) or 'none'}); "
              f"{ok.sum()} video frames at {fps:.3f} fps",
              f"  drone height {kC[:, 2].min():.1f} .. {kC[:, 2].max():.1f} m; nearest to the paddock centre "
              f"{np.min(np.linalg.norm(kC[:, :2] - [6.1, 3.05], axis=1)):.1f} m"]
        for tt in range(0, int(kt[-1]) + 1, 10):
            i = np.argmin(abs(kt - tt)); L.append(f"    t {kt[i]:5.1f} s: drone at {np.round(kC[i], 1).tolist()}")
    L.insert(0, f"SHOWCASE POSES  camera {cam.model.name} {cam.width}x{cam.height} {np.round(cam.params, 4).tolist()}")
    (OUT / "POSES.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ------------------------------------------------------------------------------------------------ the scene
def scene():
    """3-D annotation geometry in the paddock frame (m)"""
    import paddock_map as pm
    S = {}
    L, Wd = 480 * IN, 240 * IN
    S["floor"] = np.array([[0, 0, 0], [L, 0, 0], [L, Wd, 0], [0, Wd, 0]], float)
    occ = json.loads(Path(r"D:\Field2026_analysis_out\2026c\cv_field_ch01_occlusion_20261006_1555\occluders.json").read_text(encoding="utf-8"))["poles"]
    S["poles"] = {k: (np.array(v["A"], float) / 1000, np.array(v["B"], float) / 1000) for k, v in occ.items()}
    sv = json.loads((HERE / "survey_2026-10-03.json").read_text(encoding="utf-8"))["houses"]
    bl, bw = sv["body_footprint"]["length"] / 100, sv["body_footprint"]["width"] / 100
    # where the houses stood on 10-03: house_check's 09-18 fits (rev g); soil below the calibration ground, eave, ridge,
    # eave line from the ridge (m)
    houses = {"house_1": ((147.5, 121.7), 90.3, 0.058, 0.590, 0.882, 0.262), "house_2": ((342.4, 117.7), 92.0, 0.093, 0.608, 0.8775, 0.277)}
    S["houses"] = {}
    for h, ((cx, cy), rd, soil, eave, ridge, run) in houses.items():
        r = np.radians(rd); ea, eb = np.array([np.cos(r), np.sin(r)]), np.array([-np.sin(r), np.cos(r)])
        c = np.array([cx, cy]) * IN; z0 = -soil
        def P(u, v, z):
            q = c + u * ea + v * eb; return np.array([q[0], q[1], z0 + z])
        R2 = 0.33
        S["houses"][h] = dict(centre=P(0, 0, ridge), soil=soil,
                              base=[P(su * bl / 2, sv_ * bw / 2, 0) for su, sv_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
                              eave=[P(su * R2, sv_ * run, eave) for su, sv_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
                              ridge=[P(-R2, 0, ridge), P(R2, 0, ridge)])
    cams = pm.load(); S["cams"] = {}
    spec = {"CH01": "Duo 3 panorama", "CH02": "Duo 3 panorama", "CH03": "RLC-1212A, looks to x = 0", "CH04": "RLC-1212A, looks to x = 40 ft",
            "CH05": "RLC-520A over house 1", "CH06": "RLC-520A over house 2"}
    for c, cm in cams.items():
        d = cm.rays(np.array([[cm.upright_size[0] / 2, cm.upright_size[1] / 2]]))[0]
        S["cams"][c] = dict(C=np.asarray(cm.centre, float) / 1000, axis=d, spec=spec[c])
    ties = json.loads((HERE / "cohort_ties_2026c.json").read_text(encoding="utf-8"))["cameras"]
    for c, hn in (("CH07", "house_2"), ("CH08", "house_1")):
        f = ties[c]["frames"]["2026-09-04 12:00:02"]; hc = S["houses"][hn]["centre"]
        S["cams"][c] = dict(C=np.array([hc[0], hc[1], f["camera_above_floor_mm"] / 1000 - S["houses"][hn]["soil"]]),
                            axis=np.array([0, 0, -1.0]), spec=f"RLC-520A inside {hn}")
    return S


def projector(P, i):
    """paddock points (n x 3, m) -> pixels at 1920 x 1080 for video frame i of the poses (NaN behind the camera)"""
    R = P["R"][i]; C = P["C"][i]; cw, ch = P["cam_size"]; k = W / cw
    pr = P["cam_params"]                                                  # OPENCV: fx fy cx cy k1 k2 p1 p2
    K = np.array([[pr[0] * k, 0, pr[2] * k], [0, pr[1] * k, pr[3] * k], [0, 0, 1]])
    dist = np.array([pr[4], pr[5], pr[6], pr[7]])
    rv = cv2.Rodrigues(R)[0]; tv = -R @ C
    def f(X):
        X = np.atleast_2d(np.asarray(X, float))
        zc = X @ R.T + tv
        uv = cv2.projectPoints(X.reshape(-1, 1, 3), rv, tv, K, dist)[0].reshape(-1, 2)
        uv[zc[:, 2] <= 0.2] = np.nan
        far = (np.abs(uv[:, 0] - W / 2) > 3 * W) | (np.abs(uv[:, 1] - H / 2) > 3 * H)   # far outside: distortion folds back
        uv[far] = np.nan
        return uv
    return f


def projector_rk(R, C, K, dist=None):
    """paddock points -> pixels for a camera (paddock -> camera rotation R, centre C, intrinsics K, OpenCV distortion)"""
    dist = np.zeros(4) if dist is None else dist
    rv = cv2.Rodrigues(R)[0]; tv = -R @ C
    def f(X):
        X = np.atleast_2d(np.asarray(X, float))
        zc = X @ R.T + tv
        uv = cv2.projectPoints(X.reshape(-1, 1, 3), rv, tv, K, dist)[0].reshape(-1, 2)
        uv[zc[:, 2] <= 0.2] = np.nan
        uv[(np.abs(uv[:, 0] - W / 2) > 3 * W) | (np.abs(uv[:, 1] - H / 2) > 3 * H)] = np.nan
        return uv
    return f


def intrinsics(P):
    cw, ch = P["cam_size"]; k = W / cw; pr = P["cam_params"]
    return np.array([[pr[0] * k, 0, pr[2] * k], [0, pr[1] * k, pr[3] * k], [0, 0, 1]]), np.array([pr[4], pr[5], pr[6], pr[7]])


def smooth_rotations(Rs, sigma_frames):
    """Gaussian-weighted mean of unit quaternions (signs aligned) -> the stabilised camera's rotations"""
    from scipy.spatial.transform import Rotation
    from scipy.ndimage import gaussian_filter1d
    q = Rotation.from_matrix(Rs).as_quat()
    for i in range(1, len(q)):
        if q[i] @ q[i - 1] < 0:
            q[i] = -q[i]
    qs = gaussian_filter1d(q, sigma_frames, axis=0, mode="nearest")
    return Rotation.from_quat(qs / np.linalg.norm(qs, axis=1)[:, None]).as_matrix()


def stabilise(img, R, Rs, K, dist, zoom, step=16):
    """the frame as the stabilised camera (rotation Rs, pinhole K with focal x zoom, no distortion) would see it: for each
    output pixel its ray, turned into the real camera (R Rs^T), projected with the real lens; the map on a coarse grid,
    upsampled. Returns the image and the share of output pixels that fell outside the source frame."""
    Kv = K.copy(); Kv[0, 0] *= zoom; Kv[1, 1] *= zoom
    gx, gy = np.arange(0, W + step, step, dtype=float), np.arange(0, H + step, step, dtype=float)
    U, V = np.meshgrid(gx, gy)
    d = np.stack([(U - Kv[0, 2]) / Kv[0, 0], (V - Kv[1, 2]) / Kv[1, 1], np.ones_like(U)], -1).reshape(-1, 3)
    src = cv2.projectPoints(d.reshape(-1, 1, 3), cv2.Rodrigues(R @ Rs.T)[0], np.zeros(3), K, dist)[0].reshape(len(gy), len(gx), 2)
    mx = cv2.resize(src[..., 0].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    my = cv2.resize(src[..., 1].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    outside = float(np.mean((src[..., 0] < 0) | (src[..., 0] > W - 1) | (src[..., 1] < 0) | (src[..., 1] > H - 1)))
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT), Kv, outside


class Painter:
    """lines and labels with alpha over a BGR frame (lines: OpenCV antialiased; text: Pillow)"""
    def __init__(self, img):
        from PIL import Image, ImageDraw, ImageFont
        self.img = img; self.texts = []; self.layers = {}
        self.Image, self.ImageDraw, self.ImageFont = Image, ImageDraw, ImageFont

    def _layer(self, col, a):
        k = (tuple(int(c) for c in col), round(float(a), 3))
        if k not in self.layers:
            self.layers[k] = np.zeros(self.img.shape[:2], np.uint8)
        return self.layers[k]

    def _flush(self):
        """one blend per (colour, alpha) mask, only inside its bounding box (the masks are drawn first, blended last)"""
        for (col, a), lay in self.layers.items():
            x, y, w, h = cv2.boundingRect(lay)
            if w == 0 or h == 0:
                continue
            sub = self.img[y:y + h, x:x + w]; m = lay[y:y + h, x:x + w].astype(np.float32) * (a / 255.0)
            sub[:] = (sub * (1 - m[..., None]) + np.array(col, np.float32) * m[..., None]).astype(np.uint8)
        self.layers = {}

    def line(self, pts, col, a, w=3, closed=False):
        p = np.asarray(pts, float)
        if not np.isfinite(p).all() or a <= 0:
            return
        cv2.polylines(self._layer(col, a), [np.round(p * 4).astype(np.int32)], closed, 255, w, cv2.LINE_AA, shift=2)

    def fill(self, pts, col, a):
        p = np.asarray(pts, float)
        if not np.isfinite(p).all() or a <= 0:
            return
        cv2.fillPoly(self._layer(col, a), [np.round(p * 4).astype(np.int32)], 255, cv2.LINE_AA, shift=2)

    def dot(self, p, col, a, r=6):
        if not np.isfinite(p).all() or a <= 0:
            return
        cv2.circle(self._layer(col, a), tuple(np.round(np.asarray(p) * 4).astype(int)), r * 4, 255, -1, cv2.LINE_AA, shift=2)

    def label(self, p, text, col, a, size=30, sub=None, dy=-44, dx=0):
        if np.isfinite(p).all() and a > 0 and -50 < p[0] < W + 50 and -50 < p[1] < H + 50:
            self.texts.append((np.asarray(p, float), text, col, a, size, sub, dy, dx))

    def finish(self):
        """labels: white boxes, dark text, a bar of the group's colour; placed in the order they were added, each moved
        up (then down) past the boxes already placed so none overlaps; a thin leader to the anchored point"""
        self._flush()
        if not self.texts:
            return self.img
        im = self.Image.fromarray(cv2.cvtColor(self.img, cv2.COLOR_BGR2RGB)).convert("RGBA")
        lay = self.Image.new("RGBA", im.size, (0, 0, 0, 0)); d = self.ImageDraw.Draw(lay)
        placed = []
        for p, text, col, a, size, sub, dy, dx in self.texts:
            fb = self.ImageFont.truetype(FONT_B, size); fr = self.ImageFont.truetype(FONT_R, int(size * 0.66))
            tw = d.textlength(text, font=fb); sw = d.textlength(sub, font=fr) if sub else 0
            bw, bh = max(tw, sw) + 34, size * 1.2 + (size * 0.8 if sub else 0) + 12
            cands = [(0, k) for k in (0, -1, -2, 1, 2)] + [(h, k) for h in (1, -1, 2, -2) for k in (0, -1, 1)]
            for h, k in cands:                                           # up / down first, then sideways
                x0 = min(max(p[0] + dx - bw / 2 + h * (bw + 10), 8), W - bw - 8); y0 = min(max(p[1] + dy - bh + k * (bh + 8), 8), H - bh - 8)
                if not any(x0 < q[2] + 6 and q[0] < x0 + bw + 6 and y0 < q[3] + 6 and q[1] < y0 + bh + 6 for q in placed):
                    break
            placed.append((x0, y0, x0 + bw, y0 + bh))
            A = int(255 * a); rgb = tuple(int(c) for c in col[::-1])
            ax, ay = x0 + bw / 2, (y0 + bh if p[1] > y0 + bh else y0)
            d.line([(p[0], p[1]), (ax, ay)], fill=(255, 255, 255, int(A * 0.9)), width=4)
            d.line([(p[0], p[1]), (ax, ay)], fill=rgb + (A,), width=2)
            d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=6, fill=(255, 255, 255, int(232 * a)))
            d.rounded_rectangle([x0, y0, x0 + 8, y0 + bh], radius=3, fill=rgb + (A,))
            d.text((x0 + 18, y0 + 6), text, font=fb, fill=(26, 26, 26, A))
            if sub:
                d.text((x0 + 18, y0 + 6 + size * 1.18), sub, font=fr, fill=(80, 80, 80, A))
        im = self.Image.alpha_composite(im, lay)
        return cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)


RED, WHT, AMB, CYA = (0, 0, 192), (255, 255, 255), (0, 160, 240), (220, 190, 0)   # BGR; RED = the deck's #C00000
CAM_SUB = {"CH01": "panoramic", "CH02": "panoramic", "CH03": "wide-angle", "CH04": "wide-angle",
           "CH05": "overhead, above house 1", "CH06": "overhead, above house 2"}


def draw(img, f, S, t, sched, check=False):
    """all annotation groups at film time t (s); sched = {group: fade-in start}"""
    def a(g, dur=0.8):
        return float(np.clip((t - sched[g]) / dur, 0, 1)) if g in sched else 0.0
    pt = Painter(img)
    fl = f(S["floor"]); aF = a("floor")
    pt.fill(fl, RED, 0.07 * aF); pt.line(fl, RED, 0.95 * aF, w=4, closed=True)
    Lm, Wm = S["floor"][1, 0], S["floor"][3, 1]
    off = sched.get("dim_side", (-0.8, -0.8))
    dl = f([[0, off[1], 0], [Lm, off[1], 0]]); dw = f([[off[0], 0, 0], [off[0], Wm, 0]])
    aD = a("dims")
    for seg, txt in ((dl, "12.2 m (40 ft)"), (dw, "6.1 m (20 ft)")):
        pt.line(seg, WHT, aD, w=3)
        for e in seg:
            pt.dot(e, WHT, aD, r=5)
        pt.label(np.nanmean(seg, 0), txt, RED, aD, size=32, dy=-16)
    aP = a("poles")
    for k, (A_, B_) in S["poles"].items():
        if check:
            pt.line(f([A_, B_]), (0, 0, 255), 0.9, w=2)
        pt.dot(f(B_)[0], WHT, aP, r=6)
    for h, g in S["houses"].items():
        aH = a("houses")
        pt.line(f(g["base"]), AMB, aH, w=3, closed=True)
        pt.line(f(g["eave"]), AMB, aH, w=3, closed=True)
        pt.line(f(g["ridge"]), AMB, aH, w=4)
        for j, e in enumerate(g["eave"]):
            pt.line(f([e, g["ridge"][0] if j in (0, 3) else g["ridge"][1]]), AMB, aH * 0.8, w=2)
        pt.label(f(g["centre"])[0], "House " + h[-1], AMB, aH, size=28, sub="camera inside", dy=-56)
    for j, c in enumerate(["CH01", "CH02", "CH03", "CH04", "CH05", "CH06", "CH07", "CH08"]):
        g = S["cams"][c]
        aC = a("cams") * float(np.clip((t - sched.get("cams", 1e9) - 0.25 * j) / 0.6, 0, 1))
        p = f(g["C"])[0]; q = f(g["C"] + 0.7 * g["axis"])[0]
        pt.line([p, q], CYA, aC, w=3)
        pt.dot(p, CYA, aC, r=9)
        if c in CAM_SUB:
            dx = {"CH01": -90, "CH02": 90, "CH03": -40, "CH04": 40, "CH05": -60, "CH06": 60}[c]
            pt.label(p, c, CYA, aC, size=26, sub=CAM_SUB[c], dy=-64, dx=dx)
    pB = S["poles"].get("C2", next(iter(S["poles"].values())))[1]
    pt.label(f(pB)[0], "UWB tracking anchors", (230, 230, 230), a("uwb"), size=24, sub="on the poles", dy=-36)
    return pt.finish()


def load_poses(v):
    P = dict(np.load(OUT / f"poses_{v}.npz", allow_pickle=False)); P["cam_size"] = list(P["cam_size"]); return P


def read_frames(v, start, dur, step=1):
    vf = f"scale={W}:{H}" if step == 1 else f"select=not(mod(n\\,{step})),scale={W}:{H}"
    cmd = [qc_paths.FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(VIDEOS[v]), "-t", f"{dur:.3f}", "-vf", vf,
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3).copy()
    p.wait()


SCHED = {"floor": 2.0, "dims": 3.5, "poles": 8.0, "uwb": 10.0, "houses": 14.0, "cams": 20.0, "inbox": 27.0}
SCHED_TALK = {"floor": 3.0, "dims": 4.0, "poles": 6.0, "uwb": 7.0, "houses": 9.0, "cams": 11.5}   # a ~30 s film from PTSC_0020 at 3 s
LAB_FRAMES = ["PTSC_0020_0076.jpg", "PTSC_0020_0136.jpg", "PTSC_0020_0196.jpg", "PTSC_0021_0001_0211.jpg", "PTSC_0021_0001_0271.jpg"]


def known_landmarks():
    """paddock positions (m) of the drone landmarks, from the anchored 10-02 inside model (anchor.json model 1): pole
    tops / feet as the drone saw them (with their lean), rig lenses, roof peaks, towers"""
    a = json.loads((REF / "anchor" / "anchor.json").read_text(encoding="utf-8"))["1"]["landmarks"]
    return {k: np.array(v, float) for k, v in a.items() if not k.startswith(("cord", "beam", "wall"))}


# ------------------------------------------------------------------------------------------------ wall-fit
# No labels: the paddock's own rigid geometry, fitted to the 10-03 model's points from the GPS start (align.npz of
# --method gps-icp --no-icp). Points near one of the four wall planes (x = 0 / 480 in, y = 0 / 240 in, 0 .. 1.1 m up)
# pull onto that plane, points near a pole axis (occluders.json, rev g; radius 75 mm) onto its surface, points on the
# floor inside the walls onto z = 0 (grass: down-weighted); a 7-number similarity correction, re-assigned while the
# distance gate shrinks from 1.2 m to 8 cm.
if STAGE == "wall-fit":
    import pycolmap
    from scipy.optimize import least_squares
    al = np.load(OUT / "align.npz"); s, R, t = float(al["s"]), al["R"], al["t"]
    rec = pycolmap.Reconstruction(str(al["model"]))
    P0 = np.array([p.xyz for p in rec.points3D.values()], float)
    Lm, Wm = 480 * IN, 240 * IN
    occ = json.loads(Path(r"D:\Field2026_analysis_out\2026c\cv_field_ch01_occlusion_20261006_1555\occluders.json").read_text(encoding="utf-8"))["poles"]
    poles = [(np.array(v["A"], float) / 1000, np.array(v["B"], float) / 1000) for v in occ.values()]

    def assign(X, dmax):
        x, y, z = X.T; W_, P_, G_ = [], [], []
        zin = (z > -0.3) & (z < 1.25)
        for axis, val, lo, hi in ((0, 0.0, 0, Wm), (0, Lm, 0, Wm), (1, 0.0, 0, Lm), (1, Wm, 0, Lm)):
            along = X[:, 1 - axis]
            m = zin & (np.abs(X[:, axis] - val) < dmax) & (along > lo - 0.2) & (along < hi + 0.2)
            W_.append((np.where(m)[0], axis, val))
        for A, B in poles:
            e = (B - A) / np.linalg.norm(B - A); v = X - A; a_ = v @ e
            r = np.linalg.norm(v - a_[:, None] * e, axis=1)
            m = (np.abs(r - 0.075) < dmax) & (a_ > 1.15) & (a_ < np.linalg.norm(B - A))    # above the walls only
            P_.append((np.where(m)[0], A, e))
        G_ = np.where((np.abs(z) < dmax) & (x > 0.4) & (x < Lm - 0.4) & (y > 0.4) & (y < Wm - 0.4))[0]
        return W_, P_, G_

    def tf(p, s, R, t):
        dR = cv2.Rodrigues(p[:3])[0]; ds = np.exp(p[6])
        return ds * s, dR @ R, ds * dR @ t + p[3:6]

    def resid(p, W_, P_, G_):
        s2, R2, t2 = tf(p, s, R, t); X = s2 * P0 @ R2.T + t2; r = []
        for idx, axis, val in W_:
            r.append(X[idx, axis] - val)
        for idx, A, e in P_:
            v = X[idx] - A; a_ = v @ e; r.append(np.linalg.norm(v - a_[:, None] * e, axis=1) - 0.075)
        r.append(0.3 * X[G_, 2])                                         # grass: 0.3 weight
        return np.concatenate(r) if r else np.zeros(1)
    L = ["SHOWCASE WALL FIT  (no labels): walls 480 x 240 in, poles (occluders.json rev g), floor; start = GPS"]
    for dmax in (1.2, 0.8, 0.5, 0.3, 0.2, 0.12, 0.08):
        for _ in range(3):
            X = s * P0 @ R.T + t; W_, P_, G_ = assign(X, dmax)
            sol = least_squares(resid, np.zeros(7), args=(W_, P_, G_), loss="soft_l1", f_scale=max(0.03, dmax / 3),
                                x_scale=[0.01, 0.01, 0.01, 0.1, 0.1, 0.1, 0.01])
            s, R, t = tf(sol.x, s, R, t)
        X = s * P0 @ R.T + t; W_, P_, G_ = assign(X, dmax)
        nw = [len(i) for i, *_ in W_]; npl = sum(len(i) for i, *_ in P_)
        rw = np.abs(np.concatenate([X[i, a] - v for i, a, v in W_])) if sum(nw) else np.array([np.nan])
        L.append(f"  gate {dmax:4.2f} m: wall points {nw} (x0, x480, y0, y240), pole points {npl}, floor {len(G_)}; wall distance median "
                 f"{np.median(rw) * 1000:.0f} mm; scale {s:.4f}")
    (OUT / "ALIGN.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    np.savez(OUT / "align.npz", s=s, R=R, t=t, model=str(al["model"]))
    print("\n".join(L))

# ------------------------------------------------------------------------------------------------ labels-page
# The 10-03 frames share no features with any anchored drone model (09-30: 3 pairs; 10-02: none), and GPS alone is off
# by 1-2 m: the operator labels named landmarks on a few frames (drone_landmark_gui's page), with the GPS estimate's
# projection of each landmark drawn as a guide.
if STAGE == "labels-page":
    import drone_landmark_gui as dlg
    lg = OUT / "landmark_gui"; (lg / "frames").mkdir(parents=True, exist_ok=True)
    frames, hints = [], {}
    K = known_landmarks()
    for n in LAB_FRAMES:
        shutil.copy2(SFM / "images" / n, lg / "frames" / n)
        vk = video_of(n); frames.append(dict(model="10-03 " + vk[0][5:9], name=n, file=f"frames/{n}"))
        P = load_poses(vk[0]); i = int(np.argmin(abs(P["t"] - (vk[1] - 1) / KEY_FPS))); f = projector(P, i)
        hints[n] = {k: f(v)[0].round(1).tolist() for k, v in K.items() if np.isfinite(f(v)[0]).all() and 0 <= f(v)[0][0] < W and 0 <= f(v)[0][1] < H}
    dlg.build(lg, frames, "2026-10-03_showcase", hints=hints, page_id="_showcase",
              task="10-03 drone frames (cones removed). Click the pole TOPS and FEET you can name, the camera lenses, both house roof peaks and "
                   "the towers - in at least two frames each where you can. The dashed yellow circles are only where a GPS estimate (1-2 m off) "
                   "puts each landmark: a guide to find it, never the answer. Export when done.",
              title="Showcase Landmark Labels")
    print(len(frames), "frames ->", lg / "drone_landmarks.html")

# ------------------------------------------------------------------------------------------------ anchor-labels
if STAGE == "anchor-labels":
    import pycolmap
    al = np.load(OUT / "align.npz"); rec = pycolmap.Reconstruction(str(al["model"]))
    imgs = {Path(im.name).name: im for im in rec.images.values()}
    LAB = json.loads(Path(opt("--labels", str(OUT / "landmark_gui" / "drone_landmarks.json"))).read_text(encoding="utf-8"))
    K = known_landmarks()
    P3 = np.array([p.xyz for p in rec.points3D.values()], float)
    rays = {}
    for fr in LAB["frames"]:
        im = imgs.get(fr["name"])
        if im is None:
            continue
        cam = rec.cameras[im.camera_id]; T = im.cam_from_world(); Rw = np.asarray(T.rotation.matrix()); C = np.asarray(im.projection_center())
        for name, v in fr["points"].items():
            if name not in K or not isinstance(v[0], (int, float)):
                continue
            xy = np.asarray(cam.cam_from_img(np.array([v], float)))[0]
            d = Rw.T @ np.r_[xy, 1.0]; rays.setdefault(name, []).append((C, d / np.linalg.norm(d), fr["name"], np.array(v, float), im, cam))
    pts, tgt, names, how = [], [], [], []
    for name, rs in rays.items():
        if len(rs) >= 2:                                                 # least-squares point closest to all rays
            A = np.zeros((3, 3)); b = np.zeros(3)
            for C, d, *_ in rs:
                M = np.eye(3) - np.outer(d, d); A += M; b += M @ C
            X = np.linalg.solve(A, b); hw = f"{len(rs)} rays"
        else:                                                            # one ray: the median depth of model points near the click
            C, d, fn, uv, im, cam = rs[0]
            T = im.cam_from_world(); Rw = np.asarray(T.rotation.matrix()); tw = np.asarray(T.translation)
            Xc = P3 @ Rw.T + tw; front = Xc[:, 2] > 0
            uvp = np.asarray(cam.img_from_cam(Xc[front])); near = np.hypot(*(uvp - uv).T) < 25
            if near.sum() < 3:
                continue
            X = C + d * np.median(np.linalg.norm(P3[front][near] - C, axis=1)); hw = "1 ray + model depth"
        pts.append(X); tgt.append(K[name]); names.append(name); how.append(hw)
    pts, tgt = np.array(pts), np.array(tgt)
    keep = np.ones(len(pts), bool)
    for _ in range(5):
        s, R, t = umeyama(pts[keep], tgt[keep]); res = np.linalg.norm(s * pts @ R.T + t - tgt, axis=1)
        bad = keep & (res > max(0.30, 3 * np.median(res[keep])))
        if not bad.any() or keep.sum() - bad.sum() < 4:
            break
        keep[np.argmax(np.where(keep, res, -1))] = False
    L = [f"SHOWCASE ANCHOR FROM LABELS  {len(names)} landmarks ({keep.sum()} kept) -> the anchored 10-02 positions; scale {s:.4f}; "
         f"residual median {np.median(res[keep]) * 1000:.0f} mm, max {res[keep].max() * 1000:.0f} mm"]
    for n_, r_, k_, h_ in sorted(zip(names, res, keep, how), key=lambda z: -z[1]):
        L.append(f"  {n_:20s} {r_ * 1000:6.0f} mm  {'' if k_ else 'DROPPED'}  ({h_})")
    (OUT / "ALIGN.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    np.savez(OUT / "align.npz", s=s, R=R, t=t, model=str(al["model"]))
    print("\n".join(L))

if STAGE == "still":
    v = opt("--video", "PTSC_0020"); P = load_poses(v); S = scene()
    for ts in [float(x) for x in opt("--times", "10,30,50,70,90").split(",")]:
        i = int(np.argmin(abs(P["t"] - ts)))
        img = next(read_frames(v, P["t"][i], 0.05))
        out = draw(img, projector(P, i), S, 1e6, SCHED, check=True)
        cv2.imwrite(str(OUT / f"still_{v}_{ts:05.1f}.jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print("still", v, ts, "->", OUT / f"still_{v}_{ts:05.1f}.jpg", "(interpolated over a gap)" if P["bad"][i] else "")

if STAGE == "render":
    S = scene(); segs = []
    for sgm in opt("--segments", "PTSC_0020:15:60:3,PTSC_0021_0001:62:30:3").split(","):
        q = sgm.split(":"); segs.append((q[0], float(q[1]), float(q[2]), float(q[3]) if len(q) > 3 else 1.0))
    fps = float(load_poses(segs[0][0])["fps"]); out = OUT / opt("--out", "paddock_showcase.mp4")
    enc = subprocess.Popen([qc_paths.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps:.5f}",
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE)
    sched = dict(SCHED_TALK) if "--talk" in args else dict(SCHED)
    if opt("--sched"):                                                    # e.g. floor=1.5,dims=2,poles=3,uwb=3.5,houses=4.5,cams=5.5
        sched = {k: float(v) for k, v in (kv.split("=") for kv in opt("--sched").split(","))}
    stab_s, zoom = float(opt("--stabilise", "0")), float(opt("--zoom", "1.10"))   # Gaussian sigma (source s); 0 = off
    clock, n, DIP, worst = float(opt("--clock0", "0")), 0, int(round(0.4 * fps)), 0.0
    for si, (v, start, dur, speed) in enumerate(segs):
        P = load_poses(v); step = int(round(speed)); m = int(dur / step * fps); k = 0
        K, dist = intrinsics(P)
        Rsm = smooth_rotations(P["R"], stab_s * fps) if stab_s > 0 else P["R"]
        for kk, img in enumerate(read_frames(v, start, dur, step)):
            j = kk * step                                                 # source frame (speed-up: every step-th)
            ts = start + j / fps
            i = int(np.argmin(abs(P["t"] - ts)))
            if abs(P["t"][i] - ts) <= 1.0 / fps and not P["bad"][i]:
                if stab_s > 0:
                    img, Kv, outside = stabilise(img, P["R"][i], Rsm[i], K, dist, zoom); worst = max(worst, outside)
                    f = projector_rk(Rsm[i], P["C"][i], Kv)
                else:
                    f = projector(P, i)
                img = draw(img, f, S, clock + k / fps, sched); n += 1
            g = 1.0
            if si > 0 and k < DIP:
                g = k / DIP                                               # dip from black into a later segment
            if si < len(segs) - 1 and k >= m - DIP:
                g = min(g, max(0, m - 1 - k) / DIP)                       # dip to black out of an earlier one
            enc.stdin.write((img * g).astype(np.uint8).tobytes() if g < 1 else img.tobytes()); k += 1
        clock += k / fps
    enc.stdin.close(); enc.wait()
    print(f"{n} annotated frames, {clock:.1f} s -> {out}" + (f"; stabilised (sigma {stab_s} s, zoom {zoom}), worst frame "
                                                              f"{worst * 100:.1f} % of the output grid outside the source" if stab_s > 0 else ""))
