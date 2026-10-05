# -*- coding: utf-8 -*-
r"""Export the frozen calibration's rig cameras for other tools (Unity, renderers) - 2026-10-05, render handover.

Per camera: the optical centre and a grid of pixel -> unit ray directions in the paddock frame, from
paddock_map.load() (release 2026-10-03 revision g, CALIBRATION_FINAL_2026-10-04.md). Model-agnostic: the panos'
stitched dual-lens model, the pinholes' distortion and the ray-space correction are all just one ray per pixel, so a
renderer can reproduce each real camera view by casting these rays (or by remapping a wide pinhole render through
them). Also each grid pixel's point on the local ground (z = 0 above the drone terrain; NaN outside the camera's
verified support) for checks.

Paddock frame: mm, origin pole A0, x along the 40 ft length, y along the 20 ft width, z normal to the ground plane
(right-handed). Pixels: UPRIGHT (the Duo 3 panos CH01 / CH02 are stored rotated 2160 x 7680; upright = 7680 x 2160,
ffmpeg transpose=2). Grid: pixel centres u = step / 2 + i * step, v = step / 2 + j * step.

Usage: python export_rig_cameras.py --out <dir> [--step 16]
Output: <out>\cameras.json (sizes, centres, grid, conventions, the paddock -> Unity transforms) and per camera
<CAM>_rays.npz (u, v, rays [nv, nu, 3], ground_mm [nv, nu, 2], centre_mm) and <CAM>_rays_f32.raw (float32
little-endian, rays [nv, nu, 3] row-major) for readers without numpy.
"""
import sys, json, hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paddock_map as pm                                                  # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
OUT = Path(opt("--out")); OUT.mkdir(parents=True, exist_ok=True)
STEP = int(opt("--step", "16"))
cams = pm.load()
TILT = (0.0146, 0.0346)                                                  # floor slope vs gravity, mm/m -> /1000 (survey json)
up = np.array([TILT[0], TILT[1], 1.0]); up /= np.linalg.norm(up)        # true vertical in the paddock frame
summary = dict(
    release="2026-10-03 revision g (frozen 2026-10-04)",
    ray_correction_sha256=hashlib.sha256((HERE / "ray_correction.json").read_bytes()).hexdigest(),
    paddock_frame="mm; origin pole A0; x along the 40 ft length, y along the 20 ft width, z normal to the ground plane; right-handed",
    pixels="upright; pixel centres u = step/2 + i*step, v = step/2 + j*step",
    step_px=STEP,
    gravity_up_in_paddock_frame=up.round(6).tolist(),
    gravity_note="the floor plane rises 14.6 mm/m along x and 34.6 mm/m along y against gravity (drone gimbal, survey_2026-10-03.json); "
                 "the paddock z axis is the floor normal, not the vertical",
    to_unity="Unity is left-handed, Y up, metres: unity = [x, z, y] / 1000 (swap y and z; the swap is the handedness change). "
             "For a gravity-true Unity Y, first rotate the paddock vector so gravity_up_in_paddock_frame becomes +z.",
    cameras={})
for c in sorted(cams):
    cm = cams[c]; W, H = cm.upright_size
    u = STEP / 2 + STEP * np.arange(int(W // STEP)); v = STEP / 2 + STEP * np.arange(int(H // STEP))
    U, V = np.meshgrid(u, v); uv = np.c_[U.ravel(), V.ravel()]
    rays = cm.rays(uv).reshape(len(v), len(u), 3).astype(np.float32)
    ground = cm.to_paddock(uv, 0.0).reshape(len(v), len(u), 2).astype(np.float32)
    np.savez_compressed(OUT / f"{c}_rays.npz", u=u.astype(np.float32), v=v.astype(np.float32), rays=rays, ground_mm=ground,
                        centre_mm=np.asarray(cm.centre, np.float32))
    rays.astype("<f4").tofile(OUT / f"{c}_rays_f32.raw")
    summary["cameras"][c] = dict(upright_size=[int(W), int(H)], grid=[len(v), len(u)], centre_mm=np.round(cm.centre, 1).tolist(),
                                 files=[f"{c}_rays.npz", f"{c}_rays_f32.raw"],
                                 kind="Reolink Duo 3 dual-lens stitched panorama" if c in ("CH01", "CH02") else "single-lens camera")
    print(c, W, H, "grid", len(v), "x", len(u), "centre mm", np.round(cm.centre, 0))
(OUT / "cameras.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("->", OUT)
