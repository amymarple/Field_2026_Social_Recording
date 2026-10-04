# -*- coding: utf-8 -*-
r"""How good is ONE camera's 2-D ground map where the tracking will use it (operator, 2026-10-03: each region has a primary
camera; where only that camera sees the ground, cross-camera agreement says nothing). Two held-out checks, both from
refit_rays.py runs, drawn on the primary-camera map (camera_error_map.py):

  * the ChArUco plates held out by station (refit_rays.py --boards, board_heldout.json): a rigid 800 x 600 mm plate
    mapped by one camera - its shape rms about the printed pattern (mm) and its scale error (%), i.e. how much that
    camera stretches or shrinks the ground locally. Only relative: a shifted map keeps a perfect plate.
  * the cords held out one at a time (refit_rays.py --cord-folds, cord_heldout.json): the cord's labels mapped by a fit
    that never saw that cord, across the cord against the drone's line - absolute, in the paddock frame. The drone's
    own uncertainty is in the report (model 0 vs model 1). --cords keeps only cords labelled close in time to the drone
    flight (2026-10-02): the X cords were labelled on 09-18 and may have been knocked or moved by rain since (operator,
    2026-10-04), so only Y39 / Y201 (labelled 09-30) are a fair absolute check.

Usage: python single_camera_check.py --run <refit dir> [--run2 <refit dir>] [--cords Y39,Y201] [--min-corners 40] [--primary <camera_error_map.json>] [--out <dir>]
Output: <out>\SINGLE_CAMERA_CHECK.txt, single_camera_check.png   (default <qc root>\single_camera_check)
"""
import sys, json, collections
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUNS = [Path(p) for p in (opt("--run"), opt("--run2")) if p]
KEEP = set(opt("--cords").split(",")) if opt("--cords") else None
MIN_N = int(opt("--min-corners", "40"))                                   # a plate view needs this many corners to count
PRIM = json.loads(Path(opt("--primary", str(qc_paths.QC_ROOT / "camera_error" / "camera_error_map.json"))).read_text(encoding="utf-8"))
OUT = Path(opt("--out", str(qc_paths.QC_ROOT / "single_camera_check"))); OUT.mkdir(parents=True, exist_ok=True)
CELL = PRIM["cell_in"]; P = PRIM["primary"]; NY, NX = len(P), len(P[0])
CAMS = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH06"]
COL = dict(zip(CAMS, ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#9c755f"]))


def primary(x, y):
    i, j = int(np.clip(x // CELL, 0, NX - 1)), int(np.clip(y // CELL, 0, NY - 1))
    return P[j][i]


def run_name(r):
    rm_ = json.loads((r / "RAYMAP.json").read_text(encoding="utf-8")) if (r / "RAYMAP.json").exists() else {}
    return f"{r.name}, {'cords from the drone' if rm_.get('drone_cords') else 'cords on design'}"


L = ["SINGLE-CAMERA CHECK  the primary camera's own 2-D ground map where tracking uses it (primary map: camera_error_map.py, "
     f"{CELL:.0f} in cells)", ""]
plates = []
B = json.loads((RUNS[0] / "board_heldout.json").read_text(encoding="utf-8")) if (RUNS[0] / "board_heldout.json").exists() else []
for v in B:
    if "cam" in v and v["n"] >= MIN_N:                                  # partial views (few corners) give no scale
        plates.append(dict(v, primary=primary(v["x_in"], v["y_in"]) == v["cam"]))
L.append(f"PLATES held out by station ({RUNS[0].name}; views with >= {MIN_N} of 88 corners - partial views under the panos give no scale): "
         "one camera's map of a rigid 800 x 600 mm plate; scale error = local stretch, "
         "shape = rms about the printed pattern after the best similarity")
for c in CAMS:
    for prim_only in (True, False):
        s = [p for p in plates if p["cam"] == c and (p["primary"] or not prim_only)]
        if s:
            k = np.array([p["scale_err_pct"] for p in s]); sh = np.array([p["shape_rms_mm"] for p in s])
            L.append(f"  {c} {'as primary' if prim_only else 'all views '}: n {len(s):2d}, scale |error| median {np.median(abs(k)):.1f} %, p90 "
                     f"{np.percentile(abs(k), 90):.1f} (signed median {np.median(k):+.1f}); shape median {np.median(sh):.0f} mm, p90 {np.percentile(sh, 90):.0f}")
L.append("  a scale error of s % moves a point d m from the plate's place by about s x d cm along the stretch - it is local, the plates "
         "are 0.8 m")
L.append("")
cords = []
for r in RUNS:
    f = r / "cord_heldout.json"
    if not f.exists():
        continue
    C = json.loads(f.read_text(encoding="utf-8")); rows = collections.defaultdict(list)
    for key, v in C.items():
        ref, cam, cord = key.split("|")
        if KEEP is not None and cord not in KEEP:
            continue
        for o, (x, y) in zip(v["offset_mm"], v["xy_in"]):
            rows[ref].append(dict(cam=cam, cord=cord, off=o, x=x, y=y, primary=primary(x, y) == cam))
    cords.append((r, rows))
    L.append(f"CORDS held out one at a time ({run_name(r)}): labels mapped by a fit that never saw the cord, across the cord vs the drone line, mm"
             + (f"; only {', '.join(sorted(KEEP))}" if KEEP else ""))
    for ref, rr in rows.items():
        for prim_only in (True, False):
            s = [q for q in rr if q["primary"] or not prim_only]
            if not s:
                continue
            by = collections.defaultdict(list)
            for q in s:
                by[(q["cam"], q["cord"])].append(q["off"])
            med = {k: np.median(v) for k, v in by.items() if len(v) >= 3}
            L.append(f"  vs {ref:13s} {'primary only' if prim_only else 'all labels  '}: every label |offset| median {np.median([abs(q['off']) for q in s]):.0f}, "
                     f"p90 {np.percentile([abs(q['off']) for q in s], 90):.0f} (n {len(s)}); per camera and cord |median| {np.median(np.abs(list(med.values()))):.0f} (n {len(med)})")
            if prim_only:
                L.append("     " + "; ".join(f"{c} {k} {m:+.0f}/{len(by[(c, k)])}" for (c, k), m in sorted(med.items())))
    L.append("")
(OUT / "SINGLE_CAMERA_CHECK.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt   # noqa: E402
npan = 1 + len(cords)
fig, axs = plt.subplots(npan, 1, figsize=(13, 6.2 * npan))
axs = np.atleast_1d(axs)


def background(ax):
    for j in range(NY):
        for i in range(NX):
            c = P[j][i]
            ax.add_patch(plt.Rectangle((i * CELL, j * CELL), CELL, CELL, fc=COL.get(c, "#eee"), ec="white", alpha=0.25))
            if c:
                ax.text(i * CELL + 2, j * CELL + 2, c[2:], fontsize=7, color=COL[c], alpha=0.8)
    ax.set_xlim(-10, 490); ax.set_ylim(-10, 250); ax.set_aspect("equal"); ax.set_xlabel("x (in)"); ax.set_ylabel("y (in)")


ax = axs[0]; background(ax)
for p in plates:
    if p["primary"]:
        k = p["scale_err_pct"]
        ax.plot(p["x_in"], p["y_in"], "s", ms=7, mfc=COL[p["cam"]], mec="k")
        ax.text(p["x_in"], p["y_in"] + 5, f"{k:+.0f}%", ha="center", fontsize=8, fontweight="bold" if abs(k) >= 4 else "normal",
                color="#b00" if abs(k) >= 4 else "k")
ax.set_title("held-out plates, mapped by the PRIMARY camera of their cell: local scale error (%)  [relative only: a shift keeps the plate perfect]", fontsize=10)
for ax, (r, rows) in zip(axs[1:], cords):
    background(ax)
    rr = rows.get("drone model 1", [])
    for q in rr:
        if q["primary"]:
            o = q["off"]; ax.plot(q["x"], q["y"], "o", ms=4 + min(abs(o), 200) / 20, mfc="#c33" if abs(o) >= 50 else "#3a3" if abs(o) < 25 else "#e90",
                                   mec="k", mew=0.4, alpha=0.85)
    by = collections.defaultdict(list)
    for q in rr:
        if q["primary"]:
            by[(q["cam"], q["cord"], int(q["x"] // 96) if q["cord"].startswith("Y") else int(q["y"] // 96))].append(q)
    for (c, k, b), qs in by.items():
        if len(qs) >= 2:
            xm, ym = np.median([q["x"] for q in qs]), np.median([q["y"] for q in qs])
            ax.text(xm + 3, ym + 4, f"{c[2:]} {np.median([q['off'] for q in qs]):+.0f}", fontsize=7.5)
    ax.set_title(f"held-out cords vs drone model 1, PRIMARY camera only: offset across the cord (mm; green < 25, orange < 50, red >= 50)"
                 + (f" - {', '.join(sorted(KEEP))} only (labelled 2 days before the drone)" if KEEP else f" - {run_name(r)}"), fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "single_camera_check.png", dpi=100)
print("->", OUT)
