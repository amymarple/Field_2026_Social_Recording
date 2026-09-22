# -*- coding: utf-8 -*-
r"""Drop cached 'located' detections whose plate outline runs into the frame border.

A plate clipped by the edge of the image is no longer an 800 x 600 rectangle, so its outline cannot
be turned into four known field points - keeping it would feed a systematic error into the fit.
board_detect.plausible_board_quad now rejects those at detection time; this prunes what is already
cached. Decoded detections are never touched.
Usage: python prune_located.py [--session <dir|date>] [--border 6] [--dry-run]
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent)); import qc_paths  # noqa: E402

args, sess = qc_paths.pop_session(sys.argv[1:])
SESSION, QC = qc_paths.resolve(sess)
border = float(args[args.index("--border") + 1]) if "--border" in args else 6.0
dry = "--dry-run" in args
kept = dropped = 0
for cam_dir in sorted((QC / "corners").iterdir()):
    if not cam_dir.is_dir():
        continue
    w, h = qc_paths.frame_size(SESSION, cam_dir.name)              # from the video, never hardcoded
    for p in sorted(cam_dir.glob("*.npz")):
        with np.load(p, allow_pickle=False) as z:
            if "method" not in z.files or str(z["method"]) != "located" or "quad" not in z.files:
                continue
            q = z["quad"].astype(float).reshape(-1, 2)
        if q[:, 0].min() < border or q[:, 1].min() < border or q[:, 0].max() > w - 1 - border or q[:, 1].max() > h - 1 - border:
            dropped += 1
            print(f"drop {cam_dir.name}/{p.name}: outline {q.min(0).round().tolist()}..{q.max(0).round().tolist()} in {w}x{h}")
            if not dry:
                p.unlink()
        else:
            kept += 1
print(f"\nlocated detections: kept {kept}, dropped {dropped}" + (" (dry run)" if dry else ""))
