# -*- coding: utf-8 -*-
# the analysis repo's landmark_track (NCC, normal constraints, held-out error) from each camera's labelled 09-18 IR
# reference frame to colour frames of the same day (camera static): the IR -> colour junction of the cohort chain
import sys, json
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0, r"D:\Documents\GitHub\Field2026_Social_analysis\cv\cv_field")
sys.path.insert(0, r"G:\Field_2026_Social_Recording\calibration_qc")
import landmark_track as lt
src = Path(r"G:\Field_2026_Social_Recording\calibration_qc\landmark_drift.py").read_text(encoding="utf-8")
import subprocess, cv2, qc_paths
from datetime import datetime
ns = {"np": np, "cv2": cv2, "subprocess": subprocess, "datetime": datetime, "qc_paths": qc_paths, "Path": Path}
exec(src[src.index("def frame("):src.index("def edges(")], ns)
frame = ns["frame"]
S = Path(r"G:\calibration\session_2026-09-18_13-54-34")
LM = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c")
TARGETS = {"CH04": ["14:32:30", "14:34:00", "14:37:00", "14:41:00", "14:46:00", "15:05:00", "15:47:00"],
           "CH03": ["15:45:00", "15:44:00", "15:30:00", "15:05:00", "15:20:00"],
           "CH01": ["13:57:30", "13:59:00", "14:10:00", "15:20:00"],
           "CH02": ["15:22:30", "15:35:00", "15:47:00"]}
for cam, tl in TARGETS.items():
    lab = json.loads(next(LM.glob(f"landmarks_{cam}_20260918_*.json")).read_text(encoding="utf-8"))
    ref_t = lab["time"].split()[1]
    ref = frame(S, cam, ref_t); ref_g = lt.prep(ref)
    print(f"{cam}: reference = labelled frame {ref_t} (saturation {cv2.cvtColor(ref, cv2.COLOR_BGR2HSV)[..., 1].mean():.0f})", flush=True)
    for t in tl:
        img = frame(S, cam, t)
        mode = "colour" if cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].mean() > 15 else "IR"
        r = lt.track_frame(ref_g, lt.prep(img), lab["landmarks"], lab.get("kind", {}), date(2026, 9, 18), ref_day=date(2026, 9, 18))
        A = r.get("A")
        if A is None:
            print(f"   {t} {mode:6}: no fit ({r.get('status')})"); continue
        A = np.asarray(A); h, w = img.shape[:2]; c = np.array([w / 2, h / 2])
        sh = A[:, :2] @ c + A[:, 2] - c
        print(f"   {t} {mode:6}: shift at centre ({sh[0]:+6.2f},{sh[1]:+6.2f}) px, rot {np.degrees(np.arctan2(A[1, 0], A[0, 0])):+.3f} deg, "
              f"held-out {r['held_med']:.2f}/{r['held_p90']:.2f} px over {r['n_held']} units, {r['status']}", flush=True)
