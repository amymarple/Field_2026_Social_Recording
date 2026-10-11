# -*- coding: utf-8 -*-
r"""The two houses as rigid above-ground objects: a CHECK of the camera mapping, nothing is fitted to the cameras
(2026-10-03). The operator's survey (survey_2026-10-03.json: body 62.55 x 45.72 cm, eaves ~59-62 cm and ridge ~88 cm
above the soil, roof slopes, ridge 66 cm) gives each house as a set of rigid 3-D edges: ridge, two eaves, four gable
rakes, base edges, vertical corners. The operator's edge labels on the 09-18 frames (analysis repo, 2026c landmarks:
HOUSE_n_ROOF_X / _ROOF_Y / _BASE_X / _BASE_Y / _BASE_Z, straight pieces sorted by 3-D direction, only visible stretches)
are rays from the cameras; the house model is placed by its position, its rotation and one height offset between the
soil (the survey's datum) and the calibration's ground - 4 numbers for all cameras together - and every labelled ray
must pass through its edge. Each label piece is assigned to the nearest edge of its own direction class.

Reported: how far the rays miss the rigid house (mm, per camera), and the house position fitted from each camera
alone with the joint height offset - if the cameras agree on where a 60-88 cm high object is, the mapping holds above
the ground there. HOUSE_2 never moved; HOUSE_1 was moved on 09-18 (operator) and its labelled frames are from
different times (CH01 13:57, CH02 15:22, CH05 14:10), so its cross-camera result is only indicative.
Also per label piece: how far its rays leave one plane through the camera centre (a straight 3-D edge must give a
plane whatever the lens) - a lens-model check.

Usage: python house_check.py [--rays release|candidate|<json>|warp]
Output: <qc root>\house_check\HOUSE_CHECK_<rays>.txt
"""
import sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths, paddock_map as pm                                        # noqa: E402  (paddock_map imports cv2 first)
from scipy.optimize import least_squares                                 # noqa: E402

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
RAYS = opt("--rays", "release")
cams = pm.load(rays=None if RAYS == "warp" else RAYS)
LM = Path(r"D:\Documents\GitHub\Field2026_Social_analysis\cv\configs\landmarks\2026c")
IR2COL = {"CH01": (0.68, -0.39), "CH02": (0.90, 0.67)}                   # 09-18 IR -> colour px (as refit_rays)
SV = json.loads((HERE / "survey_2026-10-03.json").read_text(encoding="utf-8"))["houses"]
DESIGN_XY = {"HOUSE_1": (134.9, 120.0), "HOUSE_2": (347.0, 119.1)}       # design footprint centres, in (survey_sheet.py)
OUT = qc_paths.QC_ROOT / "house_check"; OUT.mkdir(parents=True, exist_ok=True)
IN, CM = 25.4, 10.0


def house_edges(h):
    """rigid edges in the house frame (mm; u along the ridge, v across, z up from the soil): name, class, p0, p1."""
    s = SV[h]; L2, W2 = SV["body_footprint"]["length"] * CM / 2, SV["body_footprint"]["width"] * CM / 2
    eaves = [v for v in s["eave_height"].values() if v is not None]; he = np.mean(eaves) * CM
    rr = s["ridge_height"]; hr = (np.mean(list(rr.values())) if isinstance(rr, dict) else rr) * CM
    run = np.sqrt((np.mean(s["roof_slope_ridge_to_eave"]) * CM) ** 2 - (hr - he) ** 2)    # eave line from the ridge, across
    R2 = s["ridge_length"] * CM / 2; wall = he - 30.0                                      # wall top a few cm under the eave
    E = [("ridge", "ru", (-R2, 0, hr), (R2, 0, hr)), ("eave+", "ru", (-R2, run, he), (R2, run, he)),
         ("eave-", "ru", (-R2, -run, he), (R2, -run, he))]
    for su in (-1, 1):
        for sv in (-1, 1):
            E.append((f"rake{su:+d}{sv:+d}", "rv", (su * R2, sv * run, he), (su * R2, 0, hr)))
            E.append((f"corner{su:+d}{sv:+d}", "bz", (su * L2, sv * W2, 0), (su * L2, sv * W2, wall)))
        E.append((f"base_v{su:+d}", "bv", (su * L2, -W2, 0), (su * L2, W2, 0)))
    for sv in (-1, 1):
        E.append((f"base_u{sv:+d}", "bu", (-L2, sv * W2, 0), (L2, sv * W2, 0)))
    return [(n, c, np.array(a, float), np.array(b, float)) for n, c, a, b in E], he, hr, run


def pieces(cam, h):
    fs = sorted(LM.glob(f"landmarks_{cam}_20260918_*.json"))
    if not fs:
        return []
    L = json.loads(fs[-1].read_text(encoding="utf-8"))["landmarks"]; out = []
    for key in ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z"):
        for p in L.get(f"{h}_{key}", []):
            p = np.asarray(p, float).reshape(-1, 2)
            if len(p) < 2:
                continue
            pts = []
            for a, b in zip(p[:-1], p[1:]):
                n = max(2, int(np.hypot(*(b - a)) / 15)); pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
            pts.append(p[-1]); uv = np.array(pts) + IR2COL.get(cam, (0.0, 0.0))
            d = cams[cam].rays(uv); ok = np.isfinite(d).all(1)
            if ok.sum() >= 3:
                out.append(dict(cam=cam, key=key, d=d[ok], C=np.asarray(cams[cam].centre, float), t=fs[-1].stem[-6:]))
    return out


def to_paddock(x, P):
    """house frame -> paddock (mm): x = (cx_in, cy_in, theta_deg, dz_mm); z drops by dz (soil -> the calibration's ground)."""
    th = np.radians(x[2]); R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return np.c_[P[..., :2] @ R.T + np.array(x[:2]) * IN, P[..., 2] - x[3]]


def ray_seg_dist(C, d, A, B):
    """distance (mm) of each ray (C + s d, s > 0) from the segment A-B."""
    u = B - A; Lu = np.linalg.norm(u); u = u / Lu; w0 = C - A
    a, b, c = np.einsum("ij,ij->i", d, d), d @ u, 1.0
    dd, e = np.einsum("ij,j->i", d, w0), w0 @ u
    den = a * c - b * b
    s = np.where(np.abs(den) > 1e-12, (b * e - c * dd) / np.where(np.abs(den) > 1e-12, den, 1), 0.0)
    t = np.clip(np.where(np.abs(den) > 1e-12, (a * e - b * dd) / np.where(np.abs(den) > 1e-12, den, 1), e), 0, Lu)
    s = np.maximum((t * b - dd) / a, 0)                                  # re-solve the ray point for the clamped edge point
    return np.linalg.norm(C + s[:, None] * d - (A + t[:, None] * u), axis=1)


def cls(key, theta):
    """label class -> model classes allowed. Roof labels may be any roof edge and base labels any base edge: the X / Y
    in the label names does not follow the paddock axes for every house (CH06's HOUSE_2_ROOF_X pieces run along paddock
    y - the ridge and both eaves), so the direction comes from the data. Vertical corners stay corners."""
    if key.startswith("ROOF"):
        return ("ru", "rv")
    if key.endswith("_Z"):
        return ("bz",)
    return ("bu", "bv")



def fit(PC, edges, x0, free=(0, 1, 2, 3)):
    x0 = np.asarray(x0, float)

    def resid(xf):
        x = x0.copy(); x[list(free)] = xf; r = []
        for pc in PC:
            c = cls(pc["key"], x[2]); best = None
            for n, ec, A, B in edges:
                if ec not in c:
                    continue
                Ap, Bp = to_paddock(x, A[None])[0], to_paddock(x, B[None])[0]
                dist = ray_seg_dist(pc["C"], pc["d"], Ap, Bp)
                if best is None or np.median(dist) < np.median(best):
                    best = dist
            r.append(best if best is not None else np.full(len(pc["d"]), 1e3))
        return np.concatenate(r) / 10.0                                  # cm
    lo = np.array([-np.inf, -np.inf, x0[2] - 15.0, -50.0])[list(free)]; hi = np.array([np.inf, np.inf, x0[2] + 15.0, 200.0])[list(free)]
    sol = least_squares(resid, np.clip(x0[list(free)], lo + 1e-6, hi - 1e-6), bounds=(lo, hi), loss="soft_l1", f_scale=2.0,
                        x_scale=[5.0, 5.0, 5.0, 20.0][:len(free)])
    x = x0.copy(); x[list(free)] = sol.x
    return x


def assign(PC, edges, x):
    out = []
    for pc in PC:
        c = cls(pc["key"], x[2]); best = (np.inf, None)
        for n, ec, A, B in edges:
            if ec in c:
                dist = ray_seg_dist(pc["C"], pc["d"], to_paddock(x, A[None])[0], to_paddock(x, B[None])[0])
                if np.median(dist) < best[0]:
                    best = (np.median(dist), n, dist)
        out.append((pc, best[1], best[2]))
    return out


def main():
    L = [f"HOUSE CHECK  cameras: {RAYS} ({type(next(iter(cams.values()))).__name__}); labels {LM} (09-18); survey_2026-10-03.json", ""]
    for h in ("HOUSE_2", "HOUSE_1"):
        edges, he, hr, run = house_edges(h)
        PC = [p for c in ("CH01", "CH02", "CH03", "CH04", "CH05", "CH06") if c in cams for p in pieces(c, h)]
        if not PC:
            continue
        L.append(f"{h}: eaves {he / 10:.1f} cm, ridge {hr / 10:.1f} cm above the soil, eave lines +-{run / 10:.1f} cm from the ridge; "
                 f"{len(PC)} label pieces from " + ", ".join(sorted({p['cam'] for p in PC})))
        starts = []                                                          # coarse grid first (the fit has local minima:
        for th0 in (0.0, 90.0, 180.0, 270.0):                                # a label piece can latch onto the wrong eave)
            for dx in np.arange(-12, 13, 3.0):
                for dy in np.arange(-9, 10, 3.0):
                    x = np.array([DESIGN_XY[h][0] + dx, DESIGN_XY[h][1] + dy, th0, 50.0])
                    starts.append((np.median(np.concatenate([a[2] for a in assign(PC, edges, x)])), x))
        starts.sort(key=lambda t: t[0])
        best = None
        for _, x0 in starts[:6]:                                             # houses stand square to the paddock: +-15 deg
            x = fit(PC, edges, x0)
            r = np.concatenate([a[2] for a in assign(PC, edges, x)])
            if best is None or np.median(r) < best[1]:
                best = (x, np.median(r))
        x = best[0]; A = assign(PC, edges, x)
        L.append(f"  joint fit: centre ({x[0]:.1f}, {x[1]:.1f}) in, ridge at {x[2] % 180:.1f} deg from x, soil {x[3]:+.0f} mm below the calibration's ground")
        for c in sorted({p["cam"] for p in PC}):
            r = np.concatenate([d for pc, n, d in A if pc["cam"] == c])
            L.append(f"    {c}: rays miss the rigid house by median {np.median(r):.0f} mm, p90 {np.percentile(r, 90):.0f} (n {len(r)}); pieces -> "
                     + ", ".join(f"{pc['key'].replace('ROOF_', 'R').replace('BASE_', 'B')}:{n} {np.median(d):.0f}" for pc, n, d in A if pc["cam"] == c))
        per = {}
        for c in sorted({p["cam"] for p in PC}):
            sub = [p for p in PC if p["cam"] == c]
            if len(sub) >= 2:
                xc = fit(sub, edges, x, free=(0, 1, 2))
                per[c] = xc
        if len(per) >= 2:
            P = np.array([[v[0], v[1]] for v in per.values()]) * IN
            L.append("  house centre from each camera alone (soil offset fixed to the joint value): "
                     + "; ".join(f"{c} ({v[0]:.1f}, {v[1]:.1f}) in, {v[2] % 180:.1f} deg" for c, v in per.items())
                     + f" -> spread {np.max(np.linalg.norm(P - P.mean(0), axis=1)):.0f} mm from their mean, pairwise "
                     + ", ".join(f"{a}-{b} {np.linalg.norm((per[a][:2] - per[b][:2]) * IN):.0f}" for i, a in enumerate(per) for b in list(per)[i + 1:]) + " mm")
        pl = []
        for pc in PC:
            _, S, Vt = np.linalg.svd(pc["d"]); n = Vt[-1]
            pl.append(np.degrees(np.max(np.abs(np.arcsin(np.clip(pc["d"] @ n, -1, 1))))))
        L.append(f"  straightness: rays of a label piece leave their best plane through the camera by median {np.median(pl):.3f} deg, max {np.max(pl):.3f} deg")
        L.append("")
    (OUT / f"HOUSE_CHECK_{Path(RAYS).stem if RAYS not in ('release', 'candidate', 'warp') else RAYS}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
