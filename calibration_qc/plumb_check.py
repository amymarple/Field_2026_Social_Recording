# -*- coding: utf-8 -*-
# Plumb-line check (2026-10-01): vertical edges (poles, house corners) from the operator's landmark labels on the 09-18
# reference frames (analysis repo cv/configs/landmarks/2026c/). Under the release model, do their rays lie in a vertical
# plane through the camera? Prints the plane's tilt from vertical and the rays' rms scatter about it per polyline.
import sys, json, glob, os
import numpy as np
sys.path.insert(0, r"G:\Field_2026_Social_Recording\calibration_qc")
import paddock_map as pm
cams = pm.load(pm.FIT, correct=False)
D = "D:/Documents/GitHub/Field2026_Social_analysis/cv/configs/landmarks/2026c/"
for f in sorted(glob.glob(D + "landmarks_CH0*_20260918_*.json")):
    d = json.load(open(f, encoding="utf-8")); cam = d["camera"]; c = cams[cam]
    W, H = c.upright_size; fw, fh = d["frame_size_upright"]; sc = np.array([W / fw, H / fh])
    keys = sorted(d["landmarks"])
    print(f"== {cam} {os.path.basename(f)}: {len(keys)} landmark keys: {', '.join(keys)[:400]}")
    for k, polys in sorted(d["landmarks"].items()):
        if not any(t in k for t in ("POLE", "_Z", "VERT", "EDGE")):
            continue
        for i, pl in enumerate(polys):
            uv = np.asarray(pl, float) * sc
            if len(uv) < 3:
                continue
            r = c.rays(uv)
            n = np.linalg.svd(r - 0 * r.mean(0))[2][-1]          # plane through the camera centre containing the rays
            tilt = np.degrees(np.arcsin(abs(n[2])))
            resid = np.degrees(np.arcsin(np.clip(np.abs(r @ n), 0, 1)))
            span = np.degrees(np.arccos(np.clip(r[0] @ r[-1], -1, 1)))
            print(f"   {k}[{i}] {len(uv)} pts, span {span:5.1f} deg, plane tilt from vertical {tilt:5.2f} deg, curvature rms {np.sqrt((resid**2).mean())*60:5.1f} arcmin, uv0 ({uv[0,0]:.0f},{uv[0,1]:.0f})")
