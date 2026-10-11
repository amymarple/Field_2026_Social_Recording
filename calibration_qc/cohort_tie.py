# -*- coding: utf-8 -*-
r"""Cohort-time cameras (2026-10-10): the frozen release cameras (rev g) as they stood during cohort 3, for a camera
whose cohort frames cannot be tied to its calibration frame by image registration.

The analysis repo's correction table (Field2026_Social_analysis cv/cv_field/frame_correction.py) maps every cohort frame
of a camera to one reference frame: the 09-18 calibration frame for CH01-CH04 and CH06, but for CH05 a user-labelled
09-04 frame (03:01 at night, 12:00:02 by day), because house_1 - the only rigid thing CH05 sees besides the pole it hangs
from - was moved on 09-18. house_tie.py measures how far CH05 had turned between such a 09-04 frame and the calibration:
on house_1 at its cohort pose (CH01 + CH02) and on pole B1, differentially against the 09-18 frame (validated on CH06,
whose house never moved, against the analysis repo's own image registration). This module applies that turn to the
release camera: pixels of the 09-04 reference frame then map to the paddock exactly as the release does for 09-18
pixels (z_mm above the local ground, the same verified support).

    import cohort_tie
    ties = cohort_tie.load()                                   # cohort_ties_2026c.json next to this file
    cam = ties.camera("CH05", "2026-09-04 03:01:00")           # or ties.find("CH05", "09-04 03:01 (user-labelled frame)")
    x_in, y_in = cam.to_paddock((u, v), z_mm=60, units="in")   # (u, v): upright pixel of THAT reference frame
    u, v = cam.to_paddock_inv((x_in, y_in), z_mm=60, units="in")

Refuses a tie file made for another release (camera_fit.npz / ray_correction.json sha256), like paddock_map.load().
python cohort_tie.py --selftest
"""
import sys, json, copy, hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paddock_map as pm                                                  # noqa: E402  (imports cv2 first)
import cv2                                                                # noqa: E402

TIES = HERE / "cohort_ties_2026c.json"


def turned(cam, x, pivot=None):
    """a shallow copy of a paddock_map camera turned by the rotation vector x[:3] (rad, paddock frame) about pivot (mm;
    default its own centre) and then shifted by x[3:6] (mm): its rays turn, its centre moves; to_paddock / to_paddock_inv
    / sees / _ground work unchanged on the copy (RayCamera computes everything from rays() and centre)."""
    x = np.r_[np.asarray(x, float), np.zeros(6)][:6]
    R = cv2.Rodrigues(x[:3])[0]; m = copy.copy(cam)
    base = cam.rays; C = np.asarray(cam.centre, float); P = C if pivot is None else np.asarray(pivot, float)
    m.rays = lambda uv, space="upright": base(uv, space) @ R.T
    m.centre = P + R @ (C - P) + x[3:]
    return m


def release_sha():
    fit = Path(pm.FIT)
    return {"camera_fit.npz": hashlib.sha256(fit.read_bytes()).hexdigest(),
            "ray_correction.json": hashlib.sha256((fit.parent / "ray_correction.json").read_bytes()).hexdigest()}


class Ties:
    def __init__(self, path=TIES, cams=None):
        self.path = Path(path)
        self.d = json.loads(self.path.read_text(encoding="utf-8"))
        have, want = release_sha(), self.d["release_sha256"]
        bad = [k for k in want if want[k] != have.get(k)]
        if bad:
            raise SystemExit(f"{self.path} was made for another release ({', '.join(bad)} differ): re-run house_tie.py --write-ties")
        self._cams = cams
        self._cache = {}

    def frames(self, cam):
        return sorted(self.d["cameras"].get(cam, {}).get("frames", {}))

    def camera(self, cam, frame):
        """the release camera turned to where it stood at reference frame `frame` ("YYYY-MM-DD HH:MM:SS")"""
        k = (cam, frame)
        if k not in self._cache:
            f = self.d["cameras"][cam]["frames"][frame]
            if f.get("kind") == "inbox":                                  # CH07 / CH08: the house-floor model
                import inbox_floor_fit
                self._cache[k] = inbox_floor_fit.InboxCamera(cam, f["params"], f["house_xy_in"], f["ridge_deg"])
                return self._cache[k]
            if self._cams is None:
                self._cams = pm.load()
            self._cache[k] = turned(self._cams[cam], f["rotvec_rad"] + f.get("shift_mm", [0.0, 0.0, 0.0]),
                                    None if f.get("pivot_mm") is None else np.asarray(f["pivot_mm"], float))
        return self._cache[k]

    def find(self, cam, target):
        """the camera for an analysis-table target frame label such as "09-04 03:01 (user-labelled frame)"; None if none"""
        for frame, f in self.d["cameras"].get(cam, {}).get("frames", {}).items():
            if str(target).startswith(f["target_frame"]):
                return self.camera(cam, frame)
        return None


def load(path=TIES, cams=None):
    return Ties(path, cams)


def selftest():
    ok = True
    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    cams = pm.load(); c = cams["CH05"]
    uv = np.array([[640.0, 480.0], [1280.0, 960.0], [1900.0, 1500.0]])
    rec("zero turn = the release camera", np.allclose(turned(c, np.zeros(3)).to_paddock(uv, 60.0), c.to_paddock(uv, 60.0), equal_nan=True))
    m = turned(c, np.radians([0.0, 1.0, 0.0]))
    a = m.to_paddock(uv, 60.0); b = m.to_paddock_inv(a, 60.0)
    ok_ = np.isfinite(a).all(1)
    rec("turned camera: to_paddock_inv inverts to_paddock", ok_.any() and np.allclose(b[ok_], uv[ok_], atol=0.5), f"({ok_.sum()} of {len(uv)} in support)")
    d = np.linalg.norm(m.to_paddock(uv, 60.0) - c.to_paddock(uv, 60.0), axis=1)
    rec("a 1 deg turn moves the ground by ~ H x 1 deg (35-50 mm at ~2.25 m)", np.nanmedian(d) > 30 and np.nanmedian(d) < 60, f"({np.nanmedian(d):.0f} mm)")
    if TIES.exists():
        t = load(cams=cams)
        for cam in t.d["cameras"]:
            for fr in t.frames(cam):
                rec(f"{cam} {fr}: tie loads and maps", np.isfinite(t.camera(cam, fr).to_paddock(uv[1:2], 60.0)).all())
    print(("PASS" if ok else "FAIL") + " - cohort_tie self-test")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
