# -*- coding: utf-8 -*-
r"""Ray-space correction of the bundle cameras (2026-10-03, AUDIT_FABLE_SOTA_2026-10-03.md section 1): instead of
warping the ground point a camera's ray hits (frame_correction.py, object space: one xy shift whatever the height),
each camera's RAY is corrected, so the correction holds at every height (walls, an animal's back) and not only on
the ground it was fitted on.

Pano (Duo 3 canvas): the bundle's (azimuth, elevation) of a pixel get
    az' = az + T(a, e) @ cA,   el' = el + T(a, e) @ cE,   a = az / 1.6 rad, e = el / 0.4 rad,
T = monomials up to DEG in (a, e) plus, for the two lens halves either side of the stitch seam (az = 0), a step
h = sign(az) times (1, a, e) - each half may sit slightly rotated against the other. The vendor stitch blends the
two lenses over a band rather than switching at one column; SEAM_W > 0 (radians of azimuth) replaces the step by a
linear ramp h = clip(az / SEAM_W, -1, 1) across that band (0 = the step, as the first candidate D). So the angular scales can vary
with azimuth (the 1.2 deg elevation error at the canvas corners, LINE_CHECK raw offsets).
Pinhole: normalised image coordinates x = X/Z, y = Y/Z get x' = x + T(x, y) @ cX, y' = y + T(x, y) @ cY (extra
distortion terms). The constant and linear terms act as small rotations; the camera centre may move by dC.

RayCam(cam, coef, dC) wraps a paddock_map.Camera loaded WITHOUT its ground warp.
"""
import numpy as np

import fit_models as fm

PANO = ("CH01", "CH02")
DEG = 3
SEAM_W = 0.0


def n_terms(name, deg=None):
    deg = DEG if deg is None else deg
    k = (deg + 1) * (deg + 2) // 2
    return k + 3 if name in PANO else k


def base_coords(cam, uv):
    """the bundle's own angular / normalised coordinates of upright pixels (fixed per observation)."""
    b = fm.bearings(cam.model, cam.intr, np.asarray(uv, float).reshape(-1, 2))
    if cam.name in PANO:
        return np.stack([np.arctan2(b[:, 0], b[:, 2]), np.arcsin(np.clip(b[:, 1], -1, 1))], 1)
    return np.stack([b[:, 0] / b[:, 2], b[:, 1] / b[:, 2]], 1)


def terms(name, q, deg=None, seam_w=None):
    deg = DEG if deg is None else deg
    seam_w = SEAM_W if seam_w is None else seam_w
    if name in PANO:
        a, e = q[:, 0] / 1.6, q[:, 1] / 0.4
    else:
        a, e = q[:, 0], q[:, 1]
    cols = [np.ones_like(a)]
    for d in range(1, deg + 1):
        for i in range(d + 1):
            cols.append(a ** (d - i) * e ** i)
    if name in PANO:
        h = np.clip(q[:, 0] / seam_w, -1, 1) if seam_w > 0 else np.sign(q[:, 0])
        cols += [h, h * a, h * e]
    return np.stack(cols, 1)


class RayCam:
    def __init__(self, cam, coef=None, dC=None, deg=None, seam_w=None):
        deg = DEG if deg is None else deg
        self.cam, self.name, self.deg = cam, cam.name, deg
        self.seam_w = SEAM_W if seam_w is None else seam_w
        nt = n_terms(cam.name, deg)
        self.coef = np.zeros((2, nt)) if coef is None else np.asarray(coef, float).reshape(2, nt)
        self.dC = np.zeros(3) if dC is None else np.asarray(dC, float)

    @property
    def centre(self):
        return self.cam.centre + self.dC

    def rays_q(self, q, T=None):
        """unit rays in paddock coordinates from base coordinates q (and their terms T, if precomputed)."""
        T = terms(self.name, q, self.deg, self.seam_w) if T is None else T
        a2 = q[:, 0] + T @ self.coef[0]; b2 = q[:, 1] + T @ self.coef[1]
        if self.name in PANO:
            b = np.stack([np.cos(b2) * np.sin(a2), np.sin(b2), np.cos(b2) * np.cos(a2)], 1)
        else:
            b = np.stack([a2, b2, np.ones_like(a2)], 1)
            b /= np.linalg.norm(b, axis=1, keepdims=True)
        return b @ self.cam.R

    def rays(self, uv):
        return self.rays_q(base_coords(self.cam, uv))

    def to_plane_q(self, q, z_mm, T=None):
        d = self.rays_q(q, T); C = self.centre
        with np.errstate(divide="ignore", invalid="ignore"):
            s = (z_mm - C[2]) / d[:, 2]
        X = C + s[:, None] * d
        X[~(s > 0)] = np.nan
        return X

    def to_paddock(self, uv, z_mm=0.0, units="mm"):
        X = self.to_plane_q(base_coords(self.cam, uv), z_mm)[:, :2]
        return X / (25.4 if units == "in" else 1.0)

    def todict(self):
        return dict(deg=self.deg, seam_w=self.seam_w, coef=self.coef.tolist(), dC_mm=self.dC.tolist())
