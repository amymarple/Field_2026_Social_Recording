# -*- coding: utf-8 -*-
r"""Projection models and the per-camera fit used by fit_cameras.py.

Two families of camera are on this rig:

  pinhole      CH03-CH06 (and any ordinary lens): f, cx, cy, k1, k2.
  equirect     the Duo3 panos CH01/CH02. Their 7680 x 2160 upright frame is a true equirectangular
               canvas - fitting fu, cu, fv, cv freely lands on 7680/pi, 3839.5, 7680/pi, 1079.5,
               i.e. the nominal 180 deg mapping, to within 0.03 %. It is NOT one camera though: the
               Duo3 has two lenses a few centimetres apart and each is rendered into its own half of
               the canvas, so the left and right halves are two cameras that share a file. They are
               fitted as separate cameras (CH01L / CH01R) with their own pose.

No measured camera position, height or field dimension enters any of this. The board is the metric
object (60 mm squares on a 720 x 540 mm pattern), so focal length, distortion, and the distance and
attitude of every board come out of the corner pixels alone.
"""
import numpy as np, cv2
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

MODELS = ("pinhole", "equirect", "cylindrical")


def project(model, ip, Xc):
    X, Y, Z = Xc[:, 0], Xc[:, 1], Xc[:, 2]
    if model == "pinhole":
        f, cx, cy, k1, k2 = ip
        Z = np.where(np.abs(Z) < 1e-6, 1e-6, Z)
        x, y = X / Z, Y / Z
        r2 = x * x + y * y
        d = 1.0 + k1 * r2 + k2 * r2 * r2
        return np.stack([f * x * d + cx, f * y * d + cy], 1)
    fu, cu, fv, cv0, k1 = ip
    az = np.arctan2(X, Z)
    rho = np.maximum(np.hypot(X, Z), 1e-6)
    el = np.arctan2(Y, rho) if model == "equirect" else Y / rho
    return np.stack([cu + fu * az, cv0 + fv * el * (1.0 + k1 * az * az)], 1)


def bearings(model, ip, uv):
    """image px -> unit ray in camera coords (used to initialise poses at any field of view)."""
    uv = np.asarray(uv, float).reshape(-1, 2)
    if model == "pinhole":
        f, cx, cy, k1, k2 = ip
        # Exact inverse of THIS module's forward model, by Newton on the radius. cv2's
        # undistortPoints does 5 fixed-point steps against its own (5-coefficient) model, which at
        # k1 ~ -0.35 leaves a frame-edge point a pixel out - centimetres on the ground.
        xd = (uv[:, 0] - cx) / f
        yd = (uv[:, 1] - cy) / f
        rd = np.hypot(xd, yd)
        r = rd.copy()
        for _ in range(50):
            r2 = r * r
            g = r * (1.0 + k1 * r2 + k2 * r2 * r2) - rd
            dg = 1.0 + 3.0 * k1 * r2 + 5.0 * k2 * r2 * r2
            step = g / np.where(np.abs(dg) < 1e-12, 1e-12, dg)
            r = r - step
            if np.nanmax(np.abs(step)) < 1e-14:
                break
        scale = np.where(rd < 1e-12, 1.0, r / np.where(rd < 1e-12, 1.0, rd))
        b = np.stack([xd * scale, yd * scale, np.ones(len(uv))], 1)
    else:
        fu, cu, fv, cv0, k1 = ip
        az = (uv[:, 0] - cu) / fu
        e = (uv[:, 1] - cv0) / (fv * (1.0 + k1 * az * az))
        el = e if model == "equirect" else np.arctan(e)
        b = np.stack([np.cos(el) * np.sin(az), np.sin(el), np.cos(el) * np.cos(az)], 1)
    return b / np.linalg.norm(b, axis=1, keepdims=True)


def init_pose(model, ip, obj_mm, uv):
    """6-DOF board pose from corner correspondences, valid at any field of view: the rays are
    rotated so the board sits near the optical axis and solved there as an ordinary pinhole."""
    b = bearings(model, ip, uv)
    m = b.mean(0)
    m = m / np.linalg.norm(m)
    z = np.array([0, 0, 1.0])
    v = np.cross(m, z)
    s = np.linalg.norm(v)
    c = float(m @ z)
    if s < 1e-9:
        R0 = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R0 = np.eye(3) + vx + vx @ vx * ((1 - c) / s ** 2)
    bb = b @ R0.T
    ok = bb[:, 2] > 1e-6
    if ok.sum() < 4:
        return None
    xy = (bb[ok, :2] / bb[ok, 2:3]).astype(np.float64)
    obj = np.concatenate([np.asarray(obj_mm, float)[ok], np.zeros((int(ok.sum()), 1))], 1)
    flag = cv2.SOLVEPNP_ITERATIVE if len(obj) >= 6 else cv2.SOLVEPNP_IPPE
    okp, rv, tv = cv2.solvePnP(obj, xy.reshape(-1, 1, 2), np.eye(3), None, flags=flag)
    if not okp:
        return None
    R = cv2.Rodrigues(rv)[0]
    return np.concatenate([cv2.Rodrigues(R0.T @ R)[0].ravel(), (R0.T @ tv).ravel()])


def board_points(pose, obj_mm):
    R = cv2.Rodrigues(np.asarray(pose[:3], float))[0]
    P = np.concatenate([np.asarray(obj_mm, float), np.zeros((len(obj_mm), 1))], 1)
    return P @ R.T + np.asarray(pose[3:], float)


class Views:
    """Flattened corner table for a set of placements: one row per corner, so the residual is a
    handful of vectorised numpy operations instead of a Python loop per placement."""

    def __init__(self, plc):
        self.plc = list(plc)
        self.idx = np.concatenate([np.full(len(p["ids"]), i) for i, p in enumerate(self.plc)])
        self.obj = np.concatenate([np.concatenate([p["obj_mm"], np.zeros((len(p["ids"]), 1))], 1)
                                   for p in self.plc]).astype(float)
        self.obs = np.concatenate([p["px"] for p in self.plc]).astype(float)
        self.sig = np.concatenate([np.full(len(p["ids"]), p["sigma"]) for p in self.plc]).astype(float)
        self.n = len(self.plc)

    def cam_points(self, poses):
        poses = np.asarray(poses, float)
        R = Rotation.from_rotvec(poses[:, :3]).as_matrix()
        return np.einsum("nij,nj->ni", R[self.idx], self.obj) + poses[self.idx, 3:]

    def reproj(self, model, ip, poses):
        return project(model, ip, self.cam_points(poses)) - self.obs

    def per_placement_rms(self, e):
        d = (e ** 2).sum(1)
        return [float(np.sqrt(d[self.idx == i].mean())) for i in range(self.n)]


def plane_basis(n):
    """orthonormal (e1, e2) spanning the plane whose unit normal is n."""
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(n, a); e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1)


def pose_on_plane(x, e1, e2, n, c, s=-1.0):
    """(theta, a, b) -> the 6-vector of a board LYING ON the plane n.X = c, printed face up
    (towards the camera). Three parameters instead of six, which is the whole point: a board that
    is known to be flat on the ground cannot take the mirrored solution that a free planar pose
    always admits, and that mirror is what makes a small, far board's orientation flip and put the
    camera in the wrong place."""
    th, a, b = x
    u = np.cos(th) * e1 + np.sin(th) * e2
    up = s * n            # which way the board frame's z points is solvePnP's choice, not ours
    R = np.stack([u, np.cross(up, u), up], 1)
    return np.concatenate([cv2.Rodrigues(R)[0].ravel(), a * e1 + b * e2 + c * n])


def to_plane_params(pose, e1, e2, n):
    R = cv2.Rodrigues(np.asarray(pose[:3], float))[0]
    u = R[:, 0]
    u = u - (u @ n) * n
    nu = np.linalg.norm(u)
    th = np.arctan2(float(u @ e2), float(u @ e1)) if nu > 1e-9 else 0.0
    t = np.asarray(pose[3:], float)
    return np.array([th, float(t @ e1), float(t @ e2)])


def fit_flat(model, ip, plc, poses, plane, sigmas=None):
    """Re-fit every placement with its board constrained to `plane` (3 DOF each), then re-fit the
    plane offset and tilt to those boards. Returns (poses, plane, per-placement rms)."""
    n, c = plane
    if c < 0:
        n, c = -n, -c
    out, rms = [], []
    e1, e2 = plane_basis(n)
    for p, q in zip(plc, poses):
        x0 = to_plane_params(q, e1, e2, n)
        s = -1.0 if float(cv2.Rodrigues(np.asarray(q[:3], float))[0][:, 2] @ n) < 0 else 1.0
        obj = np.concatenate([p["obj_mm"], np.zeros((len(p["obj_mm"]), 1))], 1)

        def res(x, obj=obj, p=p, s=s):
            pose = pose_on_plane(x, e1, e2, n, c, s)
            R = cv2.Rodrigues(pose[:3])[0]
            return ((project(model, ip, obj @ R.T + pose[3:]) - p["px"]) / p["sigma"]).ravel()

        best = None
        for dth in (0.0, np.pi / 2, np.pi, -np.pi / 2):   # the four ways the plate can be laid down
            r = least_squares(res, x0 + [dth, 0, 0], method="trf", loss="huber", f_scale=2.0,
                              x_scale="jac", xtol=1e-12, ftol=1e-12, max_nfev=300)
            if best is None or r.cost < best.cost:
                best = r
        e = res(best.x) * p["sigma"]
        out.append(pose_on_plane(best.x, e1, e2, n, c, s))
        rms.append(float(np.sqrt((e.reshape(-1, 2) ** 2).sum(1).mean())))
    pts = np.concatenate([board_points(q, p["obj_mm"]) for q, p in zip(out, plc)])
    w = np.concatenate([np.full(len(p["obj_mm"]), 1.0 / max(r, 0.5) ** 2) for p, r in zip(plc, rms)])
    ctr = (pts * w[:, None]).sum(0) / w.sum()
    nn = np.linalg.svd((pts - ctr) * np.sqrt(w)[:, None])[2][-1]
    if nn @ ctr < 0:
        nn = -nn
    return out, (nn, float(nn @ ctr)), rms


def fit_camera(model, plc, ip0, free_intr=(0, 1, 2, 3, 4), loss="huber", f_scale=2.0, poses0=None):
    """Intrinsics + one free 6-DOF pose per view. Nothing about the field is used."""
    ip = np.array(ip0, float)
    keep, poses = [], []
    for i, p in enumerate(plc):
        q = poses0[i] if poses0 is not None else init_pose(model, ip, p["obj_mm"], p["px"])
        if q is None or not np.isfinite(q).all() or q[5] <= 0:
            continue
        keep.append(p)
        poses.append(np.asarray(q, float))
    if len(keep) < (3 if free_intr else 1):   # poses alone need no second view
        return None
    free_intr = list(free_intr)
    V = Views(keep)
    n_f = len(free_intr)
    x0 = np.concatenate([ip[free_intr], np.concatenate(poses)])

    def unpack(x):
        q = ip.copy()
        q[free_intr] = x[:n_f]
        return q, x[n_f:].reshape(-1, 6)

    def resid(x):
        q, ps = unpack(x)
        return (V.reproj(model, q, ps) / V.sig[:, None]).ravel()

    rows = 2 * len(V.obs)
    S = np.zeros((rows, len(x0)), bool)
    S[:, :n_f] = True
    r2 = np.repeat(V.idx, 2)
    for j in range(6):
        S[np.arange(rows), n_f + 6 * r2 + j] = True
    r = least_squares(resid, x0, jac_sparsity=S, method="trf", loss=loss, f_scale=f_scale,
                      x_scale="jac", xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=200)
    q, ps = unpack(r.x)
    e = V.reproj(model, q, ps)
    return dict(model=model, intr=q, poses=ps, plc=keep, err=e,
                rms=float(np.sqrt((e ** 2).sum(1).mean())),
                per_placement=V.per_placement_rms(e))
