# -*- coding: utf-8 -*-
r"""Rig camera lens positions triangulated from the operator's lens clicks in many drone frames (2026-10-03).
drone_landmark_anchor.py puts a clicked point at the median depth of the model points seen within 25 px of the
click - for a lens on a housing that depth mixes in the net, the beam or the sky behind it, and CH04 had a single
click. Here every click is a ray from its frame's registered pose, and each lens is the least-squares meeting point
of all its rays; clicks that miss it by more than max(12 px, 3 x the median) are listed and left out (a wrong name or
a lens that was not the one meant). The spread comes from a bootstrap over frames. The model point moves into the
paddock frame with the landmark anchor (design pole grid); positions are also given with the ChArUco plate's scale
(drone_board_scale.py) applied about the anchor's centre.

Usage: python drone_lens_triangulate.py --name 2026-10-02_all [--model 1] [--labels a.json,b.json] [--update]
Output: <run>\lens_tri.json, LENS_TRI.txt (+ with --update: a 'drone_tri' entry in camera_centres_2026-10-03.json)
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402
import pycolmap                                                          # noqa: E402
from scipy.spatial.transform import Rotation                             # noqa: E402

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RUN = qc_paths.QC_ROOT / "drone_sfm" / opt("--name", "2026-10-02_all")
MODEL = opt("--model", "1")
LABELS = opt("--labels", ",".join([str(HERE / "session_2026-10-02_drone_landmarks.json"),
                                    str(RUN / "landmark_gui_cams" / "drone_landmarks_cams.json")])).split(",")
IN = 0.0254
rec = pycolmap.Reconstruction(str(RUN / "sparse" / MODEL))
imgs = {im.name: im for im in rec.images.values()}
A = json.loads((RUN / "anchor" / "anchor.json").read_text(encoding="utf-8"))[MODEL]
s, Rm, t = A["scale"], Rotation.from_rotvec(A["rotvec"]).as_matrix(), np.asarray(A["t"])
to_pad = lambda X: s * Rm @ X + t                                        # model units -> paddock m

clicks = {}                                                              # (frame, lens) -> (u, v); later files win
for path in LABELS:
    for fr in json.loads(Path(path).read_text(encoding="utf-8"))["frames"]:
        for name, val in fr["points"].items():
            if name.endswith(" lens") and fr["name"] in imgs:
                clicks[(fr["name"], name)] = tuple(val)
rays = {}                                                                # lens -> list of (frame, centre, dir, cam, pose, uv)
for (fn, name), uv in clicks.items():
    im = imgs[fn]; cam = rec.cameras[im.camera_id]; T = im.cam_from_world()
    xn = cam.cam_from_img(np.array([uv], float))[0]
    d = T.rotation.matrix().T @ np.r_[xn, 1.0]; d /= np.linalg.norm(d)
    rays.setdefault(name[:4], []).append((fn, im.projection_center(), d, cam, T, np.asarray(uv, float)))


def meet(R):
    M = np.zeros((3, 3)); b = np.zeros(3)
    for _, C, d, *_ in R:
        P = np.eye(3) - np.outer(d, d); M += P; b += P @ C
    return np.linalg.solve(M, b)


def reproj(X, r):
    _, C, d, cam, T, uv = r
    Xc = T.rotation.matrix() @ X + T.translation
    return float(np.linalg.norm(cam.img_from_cam(np.array([Xc]))[0] - uv)) if Xc[2] > 0 else np.inf


cc_path = qc_paths.QC_ROOT / "camera_centres_2026-10-03.json"
cc = json.loads(cc_path.read_text(encoding="utf-8"))
from paddock_map import load                                              # noqa: E402
bundle = {c: np.asarray(cam.centre) / 1000 for c, cam in load(correct=False).items()}
bs = RUN / "board_scale.json"
k_board = (json.loads(bs.read_text(encoding="utf-8"))["mm_per_unit"] / 1000 / s) if bs.exists() else None
centre = np.array([240 * IN, 120 * IN, 0.0])                            # the design grid's middle (pole B2), where the anchor scale pivots
rng = np.random.default_rng(3)
out, L = {}, [f"LENS TRIANGULATION  run {RUN.name} model {MODEL}: {len(clicks)} lens clicks from {len(LABELS)} label files; "
              f"anchor scale {s:.4f} m per unit" + (f", board scale x{k_board:.4f} of it" if k_board else ""), ""]
L.append("camera  frames  rms px  dropped               paddock (x, y) in   z mm   sd x/y/z mm     tape (x, y) in   h mm   "
         "d_tape mm (x y z)     previous drone d mm   bundle d mm")
for c in sorted(rays):
    R = list(rays[c]); dropped = []
    while len(R) >= 2:
        X = meet(R); e = np.array([reproj(X, r) for r in R]); lim = max(12.0, 3 * np.median(e))
        if e.max() <= lim:
            break
        i = int(np.argmax(e)); dropped.append(f"{Path(R[i][0]).stem[5:]} {e[i]:.0f}px"); R.pop(i)
    if len(R) < 2:
        L.append(f"{c}: fewer than two consistent clicks"); continue
    X = meet(R); e = np.array([reproj(X, r) for r in R]); P = to_pad(X)
    boot = [to_pad(meet([R[j] for j in rng.integers(0, len(R), len(R))])) for _ in range(300)]
    boot = [b for b in boot if np.all(np.isfinite(b))]; sd = np.std(boot, 0) * 1000
    ang = max(np.degrees(np.arccos(np.clip(a[2] @ b[2], -1, 1))) for a in R for b in R)
    rec_c = dict(x_m=round(float(P[0]), 4), y_m=round(float(P[1]), 4), z_m=round(float(P[2]), 4), n_clicks=len(R),
                 rms_px=round(float(np.sqrt(np.mean(e ** 2))), 1), sd_mm=[round(float(v), 1) for v in sd],
                 ray_spread_deg=round(float(ang), 1), dropped=dropped)
    if k_board:
        Pb = centre + k_board * (P - centre); rec_c["board_scaled_m"] = [round(float(v), 4) for v in Pb]
    out[c] = rec_c
    tp = cc["tape"].get(c); pd = cc["drone"].get(c); bd = bundle.get(c)
    tape_s = f"({tp['x_in']:5.0f},{tp['y_in']:5.0f})  {tp['h_m'] * 1000:5.0f}" if tp else " " * 20
    dt = f"{(P[0] - tp['x_in'] * IN) * 1000:+5.0f} {(P[1] - tp['y_in'] * IN) * 1000:+5.0f} {(P[2] - tp['h_m']) * 1000:+5.0f}" if tp else " " * 17
    dpv = f"{np.linalg.norm(P - [pd['x_m'], pd['y_m'], pd['z_m']]) * 1000:5.0f}" if pd else "    -"
    dbu = f"{np.linalg.norm(P - bd) * 1000:5.0f}" if bd is not None else "    -"
    L.append(f"{c}    {len(R):3d}    {rec_c['rms_px']:5.1f}  {len(dropped):2d}  ({P[0] / IN:6.1f},{P[1] / IN:6.1f})  {P[2] * 1000:5.0f}  "
             f"{sd[0]:4.0f}/{sd[1]:3.0f}/{sd[2]:3.0f}   {tape_s}   {dt}     {dpv}               {dbu}   rays over {ang:.0f} deg")
    if dropped:
        L.append(f"        left out: {', '.join(dropped)}")
tp_c = [c for c in out if c in cc["tape"]]
if len(tp_c) >= 2:
    D = np.array([[out[c]["x_m"] - cc["tape"][c]["x_in"] * IN, out[c]["y_m"] - cc["tape"][c]["y_in"] * IN,
                   out[c]["z_m"] - cc["tape"][c]["h_m"]] for c in tp_c])
    off = D.mean(0); r = D - off
    L += ["", f"against the tape ({', '.join(tp_c)}): common offset ({off[0] / IN:+.1f}, {off[1] / IN:+.1f}) in, "
              f"{off[2] * 1000:+.0f} mm height; after it {np.sqrt((r[:, :2] ** 2).sum(1).mean()) / IN:.1f} in rms horizontal, "
              f"{np.sqrt((r[:, 2] ** 2).mean()) * 1000:.0f} mm rms height"]
    pairs = [(a, b) for i, a in enumerate(tp_c) for b in tp_c[i + 1:]]
    dd = [np.hypot(*(np.subtract([out[a]["x_m"], out[a]["y_m"]], [out[b]["x_m"], out[b]["y_m"]])))
          - np.hypot(*(np.subtract([cc["tape"][a]["x_in"], cc["tape"][a]["y_in"]], [cc["tape"][b]["x_in"], cc["tape"][b]["y_in"]]) * IN))
          for a, b in pairs]
    L.append("  frame-free: horizontal distances between cameras, drone - tape (mm): "
             + ", ".join(f"{a}-{b} {d * 1000:+.0f}" for (a, b), d in zip(pairs, dd)))
(RUN / "lens_tri.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
(RUN / "LENS_TRI.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
if "--update" in args:
    cc["drone_tri"] = {c: {k: v[k] for k in ("x_m", "y_m", "z_m", "n_clicks", "sd_mm")} for c, v in out.items()}
    cc["note_drone_tri"] = (f"drone_tri = lens clicks triangulated over many frames of {RUN.name} model {MODEL} "
                            f"(drone_lens_triangulate.py, 2026-10-03), anchor (design grid) scale; supersedes 'drone' where present")
    cc_path.write_text(json.dumps(cc, indent=1), encoding="utf-8")
    print("updated", cc_path)
