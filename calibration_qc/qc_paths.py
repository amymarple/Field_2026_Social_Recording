# -*- coding: utf-8 -*-
r"""Session / QC-folder resolution shared by the calibration_qc scripts.

The 2026-09-18 session is the default and its QC outputs live flat in E:\calibration\qc (as produced
on the day). Any other session gets its own QC subfolder E:\calibration\qc\<session date>\ holding
corners/, the annotated timelapses, timeline_gui.html, frames/. Every script accepts
--session <dir | YYYY-MM-DD> (a date picks the latest session folder of that day)."""
from pathlib import Path
import numpy as _np

ROOT = Path(r"E:\calibration")
QC_ROOT = ROOT / "qc"
DEFAULT_SESSION = ROOT / "session_2026-09-18_13-54-34"


def pop_session(args):
    """Remove '--session X' from an argv list; returns (args, X or None)."""
    args = list(args)
    if "--session" in args:
        i = args.index("--session"); val = args[i + 1]; del args[i:i + 2]
        return args, val
    return args, None


def resolve(arg=None):
    """-> (session dir, qc dir). arg: None (default session), a session directory, or a date."""
    if not arg:
        return DEFAULT_SESSION, QC_ROOT
    p = Path(arg)
    if not p.is_dir():
        cands = sorted(ROOT.glob(f"session_{arg}_*"))
        if not cands:
            raise SystemExit(f"no session folder matches '{arg}' under {ROOT}")
        p = cands[-1]
    if p.resolve() == DEFAULT_SESSION.resolve():
        return DEFAULT_SESSION, QC_ROOT
    qc = QC_ROOT / p.name.split("_")[1]
    qc.mkdir(parents=True, exist_ok=True)
    return p, qc


def session_date(session):
    return Path(session).name.split("_")[1]


def cone_labels(qc, cam):
    """Cone labels for a session: the session's own file if it exists, else the 2026-09-18 labels
    (the cones stayed on their ticks until the mid-point move)."""
    for d in (qc, QC_ROOT):
        f = d / f"cone_labels_{cam}.json"
        if f.exists():
            return f
    return None


# ---------------------------------------------------------------- frame geometry
# Nothing downstream may hardcode 2160/7680: a label file can be made at any display scale, and it
# declares the pixel space of its own coordinates in "frame_size_upright". Everything here converts
# to the camera's REAL frame, read from the video once and cached.
import json as _json, subprocess as _sp                                   # noqa: E402
FFPROBE = r"E:\Reolink_record\bin\ffprobe.exe"
_SIZE = {}

def frame_size(session, cam):
    """(width, height) of the camera's STORED frames, from ffprobe."""
    key = (str(session), cam)
    if key not in _SIZE:
        segs = sorted(Path(session).glob(f"{cam}_*_to_*.mp4"))
        if not segs:
            raise SystemExit(f"no closed {cam} segment in {session}")
        out = _sp.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height", "-of", "csv=p=0", str(segs[0])]).decode()
        _SIZE[key] = tuple(int(v) for v in out.strip().split(",")[:2])
    return _SIZE[key]

def is_rotated(session, cam):
    """True when the stream is stored rotated (the Duo3 panos are stored 2160x7680, upright 7680x2160)."""
    w, h = frame_size(session, cam)
    return h > w

def upright_size(session, cam):
    w, h = frame_size(session, cam)
    return (h, w) if h > w else (w, h)

def upright_to_stored(pts, session, cam):
    """Upright pixels -> stored pixels. Identity for the cameras that are not stored rotated."""
    p = _np.asarray(pts, float).reshape(-1, 2)
    if not is_rotated(session, cam):
        return p
    sw, _sh = frame_size(session, cam)
    return _np.stack([(sw - 1) - p[:, 1], p[:, 0]], 1)

def stored_to_upright(pts, session, cam):
    p = _np.asarray(pts, float).reshape(-1, 2)
    if not is_rotated(session, cam):
        return p
    sw, _sh = frame_size(session, cam)
    return _np.stack([p[:, 1], (sw - 1) - p[:, 0]], 1)

def load_cones(qc, cam, session, space="upright"):
    """station -> (x, y) from the operator's cone labels, RESCALED from the pixel space the labels
    declare ("frame_size_upright") to this camera's real frame. space: 'upright' or 'stored'."""
    f = cone_labels(qc, cam)
    if f is None:
        return {}
    lab = _json.loads(f.read_text(encoding="utf-8"))
    uw, uh = upright_size(session, cam)
    dw, dh = lab.get("frame_size_upright", [uw, uh])
    sx, sy = uw / float(dw), uh / float(dh)
    if abs(sx - 1) > 1e-6 or abs(sy - 1) > 1e-6:
        print(f"[qc_paths] {f.name}: labels are in {dw}x{dh}, camera is {uw}x{uh} -> scaling by {sx:.4f},{sy:.4f}")
    out = {}
    for q in lab.get("points", []):
        st = (q.get("station") or "").upper()
        if not st or st == "NONE":
            continue
        p = _np.array([q["x"] * sx, q["y"] * sy], float)
        out[st] = upright_to_stored(p, session, cam)[0] if space == "stored" else p
    return out
