# -*- coding: utf-8 -*-
r"""Compare two fits: what a re-run (another machine, another OpenCV/scipy, a held-out fold) changed.

    python compare_fits.py <release camera_fit.npz> <other camera_fit.npz>

Three layers, because they answer different questions:
  1. the bundle itself - lens, camera centres, plate poses, dropped views. The bundle's frame is only
     loosely anchored (cones, stations), so two runs that stop at the evaluation budget from different
     starts differ by a near-rigid shift of the whole frame; the per-camera scatter after removing the
     mean shift is the real disagreement.
  2. the checks next to each fit (PADDOCK_AGREEMENT / LINE_CHECK / CV_LANDMARKS, when present).
  3. the MAPPING - pixel -> paddock through each fit's own frame_correction.json, on a pixel grid per
     camera. This is what any downstream user sees; the frame correction absorbs the bundle's shift.
     Needs frame_correction.json next to both fits (run frame_correction.py --fit <npz>).

2026-09-25, laptop (OpenCV 4.13, scipy 1.18) vs the field PC release (OpenCV 5.0, scipy 1.17): bundle frame
shifted 42 mm, per-camera scatter 1-5 mm, mapping within 1.1 mm on five cameras and 7.7 mm max on CH03.
"""
import sys, json, re
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paddock_map as pm                                                  # noqa: E402



def bundle(a, b):
    print("BUNDLE")
    for k in sorted(set(a.files) & set(b.files)):
        x, y = a[k], b[k]
        if x.shape != y.shape:
            print(f"  {k:18s} shape {x.shape} vs {y.shape}")
        elif x.dtype.kind in "fc":
            d = float(np.nanmax(np.abs(x - y))) if x.size else 0.0
            print(f"  {k:18s} max|d| {d:.3g}")
        else:
            print(f"  {k:18s} {'equal' if np.array_equal(x, y) else 'differs'}")
    for k in set(a.files) ^ set(b.files):
        print(f"  {k:18s} only in {'A' if k in a.files else 'B'}")
    d = b["cam_centre_mm"] - a["cam_centre_mm"]
    m = d.mean(0)
    print(f"  camera centres: mean shift ({m[0]:+.1f}, {m[1]:+.1f}, {m[2]:+.1f}) mm = {np.linalg.norm(m):.1f} mm; "
          f"scatter after removing it {np.round(np.linalg.norm(d - m, axis=1), 1)} mm")
    da = set(map(str, a["dropped_views"])); db = set(map(str, b["dropped_views"]))
    ida = {s.split("|")[:4] and "|".join(s.split("|")[:4]) for s in da}; idb = {"|".join(s.split("|")[:4]) for s in db}
    print(f"  dropped views: {len(da)} vs {len(db)}; same set of views: {ida == idb}")
    for s in sorted(ida ^ idb):
        print("    only one side dropped:", s)


def checks(pa, pb):
    print("CHECKS (lines with a number that changed)")
    for f in ("PADDOCK_AGREEMENT.txt", "LINE_CHECK.txt", "CV_LANDMARKS.txt", "CALIBRATION_FIT.txt"):
        fa, fb = pa.parent / f, pb.parent / f
        if not (fa.exists() and fb.exists()):
            print(f"  {f}: missing on one side"); continue
        la = fa.read_text(encoding="utf-8").splitlines(); lb = fb.read_text(encoding="utf-8").splitlines()
        n = 0
        for x, y in zip(la, lb):
            if x != y and re.search(r"\d", x) and "npz" not in x:
                n += 1
                if n <= 6:
                    print(f"  {f}: A {x.strip()[:110]}\n  {' ' * len(f)}  B {y.strip()[:110]}")
        print(f"  {f}: {n} numeric lines differ of {len(la)}")


def mapping(pa, pb):
    print("MAPPING  pixel -> paddock through each fit's own frame_correction.json, z = 0")
    A = pm.load(fit=pa); B = pm.load(fit=pb)
    for cam in sorted(A):
        W, H = A[cam].upright_size                       # the pixel space every tool here works in
        d, support = [], 0
        for u in np.linspace(0, W - 1, 33):
            for v in np.linspace(0, H - 1, 17):
                x = np.asarray(A[cam].to_paddock((u, v), z_mm=0, units="mm"), float).ravel()[:2]
                y = np.asarray(B[cam].to_paddock((u, v), z_mm=0, units="mm"), float).ravel()[:2]
                fa, fb = np.all(np.isfinite(x)), np.all(np.isfinite(y))
                if fa and fb:
                    d.append(np.linalg.norm(x - y))
                elif fa != fb:
                    support += 1
        d = np.array(d)
        print(f"  {cam}: {len(d):4d} px supported by both; |A-B| median {np.median(d):5.1f}  p90 {np.percentile(d, 90):5.1f}  "
              f"max {d.max():5.1f} mm; support differs at {support} px")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    pa, pb = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    a = np.load(pa, allow_pickle=False); b = np.load(pb, allow_pickle=False)
    print(f"A = {pa}\nB = {pb}")
    bundle(a, b)
    checks(pa, pb)
    if (pa.parent / "frame_correction.json").exists() and (pb.parent / "frame_correction.json").exists():
        mapping(pa, pb)
    else:
        print("MAPPING skipped: frame_correction.json missing next to one fit (run frame_correction.py --fit <npz>)")
