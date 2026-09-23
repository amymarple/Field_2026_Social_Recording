# -*- coding: utf-8 -*-
r"""Pixel <-> paddock. Turn a point in any camera's frame into paddock (x, y), and back.

    from paddock_map import load
    cams = load()                                   # E:\calibration\qc\camera_fit.npz
    x_in, y_in = cams["CH03"].to_paddock((2100, 1700), z_mm=0, units="in")
    u, v      = cams["CH03"].to_paddock_inv((240, 120), z_mm=0, units="in")

THE ONE THING THAT MATTERS: a pixel is a RAY, not a point. A camera cannot know how far along
that ray the thing is, so every pixel -> paddock conversion has to assume a height. `z_mm` is
that assumption: 0 = the ground, 6 = the top of the calibration plate, ~60 = a rat's back. Get it
wrong by dz and the answer slides horizontally by dz / tan(depression angle) - which for the two
panoramas (~54 deg down) is 0.73 mm per mm of height. Tracking an animal's back at z = 0 puts it
~4 cm too far from the camera. `height_sensitivity()` prints the factor for each camera.

Pixel coordinates are UPRIGHT (space="upright", the default): for CH01/CH02 that is the 7680 x 2160
frame you get after rotating the stored 2160 x 7680 video 90 deg CCW, which is what every tool in
calibration_qc works in. Pass space="stored" to use raw video pixels instead.

The 3 x 3 matrix, for the four ordinary lenses: `homography(z_mm)` returns H with
[X, Y, 1] ~ H^-1 [u, v, 1], i.e. H maps paddock mm on the plane z = z_mm to UNDISTORTED pixels. It
is exact, but only after undistortion - these lenses have k1 ~ -0.35, which moves a frame-corner
pixel by over a hundred pixels, so a raw pixel through a bare homography is simply wrong. Use
`undistort()` first, or just call `to_paddock`, which does it for you. The two panoramas have no
such matrix at all: an equirectangular canvas is not a projective image of anything, so a plane in
it is not a homography. Use the function.
"""
import sys
from pathlib import Path
import numpy as np, cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_models as fm                                                   # noqa: E402

FIT = Path(r"E:\calibration\qc\camera_fit.npz")
MM_PER_IN = 25.4
PANO = ("CH01", "CH02")


class Camera:
    """One calibrated camera. X_cam = R @ X_field + t, all lengths in millimetres."""

    def __init__(self, name, model, intr, rvec, tvec, stored_size):
        self.name = name
        self.model = str(model)
        self.intr = np.asarray(intr, float)
        self.rvec = np.asarray(rvec, float)
        self.tvec = np.asarray(tvec, float)
        self.R = cv2.Rodrigues(self.rvec)[0]
        self.centre = -self.R.T @ self.tvec                  # camera position in paddock mm
        self.stored_size = tuple(int(v) for v in stored_size)
        self.rotated = self.stored_size[1] > self.stored_size[0]
        self.upright_size = ((self.stored_size[1], self.stored_size[0]) if self.rotated
                             else self.stored_size)

    # ---------------------------------------------------------------- pixel spaces
    def stored_to_upright(self, uv):
        p = np.asarray(uv, float).reshape(-1, 2)
        if not self.rotated:
            return p
        sw = self.stored_size[0]
        return np.stack([p[:, 1], (sw - 1) - p[:, 0]], 1)

    def upright_to_stored(self, uv):
        p = np.asarray(uv, float).reshape(-1, 2)
        if not self.rotated:
            return p
        sw = self.stored_size[0]
        return np.stack([(sw - 1) - p[:, 1], p[:, 0]], 1)

    # ---------------------------------------------------------------- the conversion
    def rays(self, uv, space="upright"):
        """pixels -> unit direction vectors in PADDOCK coordinates, from self.centre."""
        p = np.asarray(uv, float).reshape(-1, 2)
        if space == "stored":
            p = self.stored_to_upright(p)
        b = fm.bearings(self.model, self.intr, p)            # unit rays in camera coords
        return b @ self.R                                    # R.T @ b for each row

    def to_paddock(self, uv, z_mm=0.0, space="upright", units="mm"):
        """pixel(s) -> the point on the horizontal plane z = z_mm that the pixel looks at.

        Returns NaN where the ray points at or above that plane (the sky, the far wall)."""
        d = self.rays(uv, space)
        with np.errstate(divide="ignore", invalid="ignore"):
            s = (z_mm - self.centre[2]) / d[:, 2]
        X = self.centre + s[:, None] * d
        X[(s <= 0) | ~np.isfinite(s)] = np.nan
        out = X[:, :2] / (MM_PER_IN if units == "in" else 1.0)
        return out[0] if np.ndim(uv) == 1 else out

    def to_paddock_inv(self, xy, z_mm=0.0, space="upright", units="mm"):
        """paddock (x, y) at height z_mm -> pixel(s). The exact inverse of to_paddock."""
        p = np.asarray(xy, float).reshape(-1, 2) * (MM_PER_IN if units == "in" else 1.0)
        X = np.concatenate([p, np.full((len(p), 1), float(z_mm))], 1)
        uv = fm.project(self.model, self.intr, X @ self.R.T + self.tvec)
        if space == "stored":
            uv = self.upright_to_stored(uv)
        return uv[0] if np.ndim(xy) == 1 else uv

    def sees(self, xy, z_mm=0.0, units="mm", margin=0):
        """Is that paddock point inside this camera's frame, and in front of it?"""
        p = np.asarray(xy, float).reshape(-1, 2) * (MM_PER_IN if units == "in" else 1.0)
        X = np.concatenate([p, np.full((len(p), 1), float(z_mm))], 1) @ self.R.T + self.tvec
        uv = fm.project(self.model, self.intr, X)
        W, H = self.upright_size
        ok = ((uv[:, 0] >= margin) & (uv[:, 0] < W - margin) &
              (uv[:, 1] >= margin) & (uv[:, 1] < H - margin))
        if self.model == "pinhole":
            ok &= X[:, 2] > 0
        return ok[0] if np.ndim(xy) == 1 else ok

    # ---------------------------------------------------------------- the matrix form
    def K(self):
        if self.model != "pinhole":
            return None
        f, cx, cy = self.intr[:3]
        return np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])

    def dist(self):
        return None if self.model != "pinhole" else np.array([self.intr[3], self.intr[4], 0.0, 0.0])

    def homography(self, z_mm=0.0):
        """3x3 H with  [u, v, 1]^T ~ H @ [X_mm, Y_mm, 1]^T  for UNDISTORTED pixels, None for a pano.

        Derivation: a paddock point on the plane is [X, Y, z], so
        X_cam = R[:,0] X + R[:,1] Y + (R[:,2] z + t)  - linear in [X, Y, 1]. H = K @ that."""
        if self.model != "pinhole":
            return None
        M = np.stack([self.R[:, 0], self.R[:, 1], self.R[:, 2] * z_mm + self.tvec], 1)
        return self.K() @ M

    def undistort(self, uv, space="upright"):
        """raw pixels -> the pixels the same lens would give with no distortion (pinhole only)."""
        if self.model != "pinhole":
            return np.asarray(uv, float).reshape(-1, 2)
        p = np.asarray(uv, float).reshape(-1, 2)
        if space == "stored":
            p = self.stored_to_upright(p)
        return cv2.undistortPoints(p.reshape(-1, 1, 2), self.K(), self.dist(),
                                   P=self.K()).reshape(-1, 2)

    def height_sensitivity(self, xy=None, units="mm"):
        """mm of horizontal slide per mm of error in the assumed height, at a paddock point
        (or at the middle of what this camera sees). This is 1 / tan(depression to that point)."""
        c = self.centre
        p = (np.asarray(xy, float) * (MM_PER_IN if units == "in" else 1.0)
             if xy is not None else self.to_paddock(np.array(self.upright_size) / 2.0))
        d = np.hypot(p[0] - c[0], p[1] - c[1])
        return float(d / max(c[2], 1e-6))

    def __repr__(self):
        c = self.centre / MM_PER_IN
        return (f"<{self.name} {self.model} at x={c[0]:.1f}in y={c[1]:.1f}in "
                f"h={self.centre[2]/1000:.2f}m>")


def load(fit=FIT, session=None):
    """-> {name: Camera}. Frame sizes come from the videos via qc_paths, never hardcoded."""
    import qc_paths
    z = np.load(Path(fit), allow_pickle=False)
    if float(np.abs(z["cam_tvec"]).max()) < 100:
        raise SystemExit(f"{fit} has translations in metres - re-run fit_cameras.py")
    sess = qc_paths.resolve(session)[0]
    out = {}
    for i, name in enumerate(z["units"]):
        cam = str(name)
        out[cam] = Camera(cam, z["models"][i], z["intr"][i], z["cam_rvec"][i], z["cam_tvec"][i],
                          qc_paths.frame_size(sess, cam[:4]))
    return out


# ====================================================================== self-check / demo
if __name__ == "__main__":
    np.set_printoptions(suppress=True, precision=3)
    cams = load()
    print("cameras:", *cams.values(), sep="\n  ")

    print("\n--- round trip: paddock -> pixel -> paddock, over the whole grid -----------------")
    gx, gy = np.meshgrid(np.arange(24, 457, 36.0), np.arange(12, 229, 27.0))
    grid = np.stack([gx.ravel(), gy.ravel()], 1)
    for c in cams.values():
        ok = c.sees(grid, units="in")
        if not ok.any():
            continue
        uv = c.to_paddock_inv(grid[ok], units="in")
        back = c.to_paddock(uv, units="in")
        e = np.linalg.norm(back - grid[ok], axis=1) * MM_PER_IN
        print(f"  {c.name}  {ok.sum():3d}/{len(grid)} grid points in frame, "
              f"round trip max {np.nanmax(e):.2e} mm")

    print("\n--- the 3x3 matrix for the ordinary lenses (undistorted px <- paddock mm, z=0) ---")
    for c in cams.values():
        H = c.homography(0.0)
        if H is None:
            print(f"  {c.name}  equirectangular pano - a plane in it is NOT a homography, "
                  f"no 3x3 exists; use to_paddock()")
            continue
        H = H / H[2, 2]
        print(f"  {c.name}  H =")
        for row in H:
            print("        " + "  ".join(f"{v: .6e}" for v in row))

    print("\n--- how far the answer slides per mm of height you assume wrong -------------------")
    for c in cams.values():
        s = c.height_sensitivity()
        print(f"  {c.name}  {s:5.2f} mm per mm   ->  a rat's back at 60 mm read as ground = "
              f"{60*s:5.0f} mm error")
