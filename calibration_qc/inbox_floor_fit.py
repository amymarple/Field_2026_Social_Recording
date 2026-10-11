# -*- coding: utf-8 -*-
r"""In-box cameras CH07 (inside house_2) and CH08 (inside house_1): pixel -> house floor -> paddock (2026-10-10).

The in-box cameras sit in the house lids and look down on the floor. Their camera pose is fitted on the house floor as a
rigid object of known size, from the operator's labels on one lid-closed segment (inbox_floor_gui.py: floor corners,
the floor / wall edges, the vertical wall joints; image sides as shown):
- floor: the 62.55 x 45.72 cm body (survey_2026-10-03.json) minus 1/2-inch walls (operator, 2026-10-10) = 600.1 x
  432.0 mm; the long side runs along the ridge. The plane is the bedding surface the operator clicked (the wall foot as
  seen), so z = 0 is where the rats lie;
- the vertical wall joints stand at the floor corners (their images meet below the lens);
- lens: an RLC-520A like CH05 / CH06, whose release lenses agree (f 1995 / 2011 px, k1 -0.337 / -0.359): their mean is
  the start and f / k1 / k2 are fitted with a prior (the labelled straight edges decide);
- orientation: both images are the paddock map rotated 180 deg, not mirrored (operator: CH07 2026-10-10, CH08 "also"):
  image right = paddock -x, image up = paddock -y (toward row A).
Frame F (house floor): origin the floor centre, x = image right (across the ridge), y = image up (along it), z up; then
paddock = house centre + x (-sin r, cos r) + y (-cos r, -sin r), r the ridge angle (house_2 92.0 deg, the 09-18 fit;
house_1 88.5 deg, its cohort pose; analysis repo CAMERA_GEOMETRY_2026c.md section 4).

The fit is for the in-box reference frame (09-04 12:00:02 segment); the analysis repo's correction table maps every other
lid-closed segment to it (frame_correction.py), so cohort pixels reach this model through Corrections.to_09_18.

Usage: python inbox_floor_fit.py --labels <inbox_floor_labels.json> [--write-ties]   |   --selftest
Output: <qc root>\inbox_floor\INBOX_FLOOR_FIT.txt (+ the in-box entries of cohort_ties_2026c.json with --write-ties)
"""
import sys, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cv2                                                                # noqa: E402
from scipy.optimize import least_squares                                 # noqa: E402

IN = 25.4
SV = json.loads((HERE / "survey_2026-10-03.json").read_text(encoding="utf-8"))["houses"]
WALL_MM = 0.5 * IN                                                        # operator, 2026-10-10
FLOOR_L = SV["body_footprint"]["length"] * 10 - 2 * WALL_MM               # along the ridge = image vertical
FLOOR_W = SV["body_footprint"]["width"] * 10 - 2 * WALL_MM                # across = image horizontal
HOUSE_OF = {"CH07": "HOUSE_2", "CH08": "HOUSE_1"}
Q = {"top-left": (-1, 1), "top-right": (1, 1), "bottom-left": (-1, -1), "bottom-right": (1, -1)}   # signs of (x, y) in F
EDGES = {"top": ((-1, 1), (1, 1)), "bottom": ((-1, -1), (1, -1)), "left": ((-1, -1), (-1, 1)), "right": ((1, -1), (1, 1))}
JOINT_TOP_MM = 700.0                                                      # vertical joints sampled 0 .. 0.7 m above the floor


def lens_prior():
    """mean of CH05 / CH06's release lenses (pinhole f, cx, cy, k1, k2; upright 2560 x 1920)"""
    z = np.load(HERE / "camera_fit.npz", allow_pickle=False)
    ip = [z["intr"][i] for i, n in enumerate(z["units"]) if str(n) in ("CH05", "CH06")]
    return np.mean(ip, axis=0)


def corner(sx, sy, z=0.0):
    return np.array([sx * FLOOR_W / 2, sy * FLOOR_L / 2, z])


def project(p, X):
    """p = rvec(3), tvec(3), f, cx, cy, k1, k2 -> pixels of F points X (n x 3)"""
    R = cv2.Rodrigues(p[:3])[0]; Xc = X @ R.T + p[3:6]
    f, cx, cy, k1, k2 = p[6:11]
    x, y = Xc[:, 0] / Xc[:, 2], Xc[:, 1] / Xc[:, 2]; r2 = x * x + y * y; d = 1 + k1 * r2 + k2 * r2 * r2
    return np.stack([f * x * d + cx, f * y * d + cy], 1)


def seg_px(p, A, B, n=120):
    t = np.linspace(0, 1, n)[:, None]
    return project(p, A + t * (B - A))


def poly_dist(q, P):
    """distance of points q from the polyline P (both n x 2)"""
    a, b = P[:-1], P[1:]; ab = b - a; L2 = np.maximum((ab ** 2).sum(1), 1e-12)
    t = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(2) / L2[None], 0, 1)
    d = np.linalg.norm(q[:, None, :] - (a[None] + t[..., None] * ab[None]), axis=2)
    return d.min(1)


def residuals(p, lab, prior, sig_prior):
    r = []
    for q, (sx, sy) in Q.items():
        k = f"floor corner {q}"
        if k in lab:
            r.append((project(p, corner(sx, sy)[None])[0] - np.asarray(lab[k], float)))
    for e, (a, b) in EDGES.items():
        k = f"floor edge {e}"
        if k in lab:
            r.append(poly_dist(np.asarray(lab[k], float), seg_px(p, corner(*a), corner(*b))))
    for q, (sx, sy) in Q.items():
        k = f"wall joint {q}"
        if k in lab:
            r.append(poly_dist(np.asarray(lab[k], float), seg_px(p, corner(sx, sy), corner(sx, sy, JOINT_TOP_MM))))
    r.append((p[6:11] - prior) / sig_prior)                               # lens prior (f, cx, cy, k1, k2)
    return np.concatenate([np.ravel(x) for x in r])


def start(prior, h=650.0):
    R = np.diag([1.0, -1.0, -1.0])                                       # image right = +x, image up = +y, looking down
    t = -R @ np.array([0.0, 0.0, h])
    return np.r_[cv2.Rodrigues(R)[0].ravel(), t, prior]


SIG = np.array([60.0, 80.0, 80.0, 0.05, 0.03])                           # lens prior widths: f, cx, cy px; k1, k2


def fit(lab, prior):
    best = None
    for h in (450.0, 650.0, 850.0):
        sol = least_squares(residuals, start(prior, h), args=(lab, prior, SIG), loss="soft_l1", f_scale=3.0,
                            x_scale=np.r_[[0.05] * 3, [20.0] * 3, [20.0, 20.0, 20.0, 0.01, 0.01]])
        if best is None or sol.cost < best.cost:
            best = sol
    return best.x, best


def centre_F(p):
    R = cv2.Rodrigues(p[:3])[0]
    return -R.T @ p[3:6]


class InboxCamera:
    """pixel (upright, the reference frame of the fit) <-> house floor F (mm) <-> paddock (mm / in)"""

    def __init__(self, name, p, house_xy_in, ridge_deg):
        self.name, self.p = name, np.asarray(p, float)
        self.R = cv2.Rodrigues(self.p[:3])[0]; self.centre_F = -self.R.T @ self.p[3:6]
        f, cx, cy, k1, k2 = self.p[6:11]
        self.K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]]); self.dist = np.array([k1, k2, 0, 0, 0.0])
        self.c = np.asarray(house_xy_in, float) * IN; r = np.radians(ridge_deg)
        self.ex, self.ey = np.array([-np.sin(r), np.cos(r)]), np.array([-np.cos(r), -np.sin(r)])

    def rays_F(self, uv):
        n = cv2.undistortPoints(np.asarray(uv, float).reshape(-1, 1, 2), self.K, self.dist).reshape(-1, 2)
        return np.c_[n, np.ones(len(n))] @ self.R                          # camera -> F (R^T applied row-wise)

    def to_floor(self, uv, z_mm=0.0):
        d = self.rays_F(uv); s = (z_mm - self.centre_F[2]) / d[:, 2]
        X = self.centre_F + s[:, None] * d
        return X[:, :2]

    def floor_to_paddock(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        return self.c + xy[:, :1] * self.ex + xy[:, 1:2] * self.ey

    def to_paddock(self, uv, z_mm=0.0, units="mm", why=False):
        """z_mm above the floor (the bedding surface); NaN outside the floor rectangle (a 2 cm margin)"""
        uv = np.asarray(uv, float); one = uv.ndim == 1
        xy = self.to_floor(uv.reshape(-1, 2), z_mm)
        inside = (np.abs(xy[:, 0]) <= FLOOR_W / 2 + 20) & (np.abs(xy[:, 1]) <= FLOOR_L / 2 + 20)
        P = self.floor_to_paddock(xy); P[~inside] = np.nan
        P = P / (IN if units == "in" else 1.0)
        st = np.where(inside, "ok", "outside the floor")
        if one:
            return (P[0], str(st[0])) if why else P[0]
        return (P, st) if why else P

    def to_paddock_inv(self, xy, z_mm=0.0, units="mm"):
        q = np.asarray(xy, float).reshape(-1, 2) * (IN if units == "in" else 1.0) - self.c
        M = np.stack([self.ex, self.ey], 1)
        f = np.linalg.solve(M, q.T).T
        uv = project(self.p, np.c_[f, np.full(len(f), float(z_mm))])
        return uv[0] if np.ndim(xy) == 1 else uv


def selftest():
    ok = True
    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    prior = lens_prior()
    truth = start(prior, 680.0); truth[:3] = cv2.Rodrigues(cv2.Rodrigues(truth[:3])[0] @ cv2.Rodrigues(np.radians([6.0, -8.0, 2.0]))[0])[0].ravel()
    truth[3:6] += [30.0, -40.0, 0.0]; truth[6] *= 1.02; truth[9] += 0.02
    rng = np.random.default_rng(1); lab = {}
    for q, (sx, sy) in Q.items():
        if q != "top-right":                                             # one corner hidden (the food box)
            lab[f"floor corner {q}"] = project(truth, corner(sx, sy)[None])[0] + rng.normal(0, 1.5, 2)
    for e, (a, b) in EDGES.items():
        t = np.linspace(0.15, 0.85, 5)[:, None]
        lab[f"floor edge {e}"] = project(truth, corner(*a) + t * (corner(*b) - corner(*a))) + rng.normal(0, 1.5, (5, 2))
    for q, (sx, sy) in Q.items():
        t = np.linspace(0.05, 0.6, 3)[:, None]
        lab[f"wall joint {q}"] = project(truth, corner(sx, sy) + t * np.array([0, 0, JOINT_TOP_MM])) + rng.normal(0, 1.5, (3, 2))
    p, sol = fit(lab, prior)
    cm = InboxCamera("T", p, (342.4, 117.7), 92.0); ct = InboxCamera("T", truth, (342.4, 117.7), 92.0)
    g = np.stack(np.meshgrid(np.linspace(-200, 200, 9), np.linspace(-280, 280, 9)), -1).reshape(-1, 2)
    for z in (0.0, 60.0):
        uv = project(truth, np.c_[g, np.full(len(g), z)])
        e = np.linalg.norm(cm.to_floor(uv, z) - g, axis=1)
        rec(f"synthetic pose recovered: floor error at z = {z:.0f} mm", np.median(e) < 3 and e.max() < 8, f"(median {np.median(e):.1f}, max {e.max():.1f} mm)")
    rec("camera height recovered", abs(cm.centre_F[2] - ct.centre_F[2]) < 10, f"({cm.centre_F[2]:.0f} vs {ct.centre_F[2]:.0f} mm)")
    P = ct.to_paddock(project(truth, np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0]])), 0.0)
    rec("orientation: image right -> paddock -x, image up -> paddock -y (ridge ~92 deg)",
        P[1, 0] < P[0, 0] - 95 and P[2, 1] < P[0, 1] - 95, f"({np.round(P / IN, 1).tolist()} in)")
    q = ct.to_paddock_inv(P[0], 0.0); rec("to_paddock_inv inverts to_paddock", np.allclose(ct.to_paddock(q, 0.0), P[0], atol=0.5))
    print(("PASS" if ok else "FAIL") + " - inbox_floor_fit self-test")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        raise SystemExit(selftest())
    print(__doc__)
