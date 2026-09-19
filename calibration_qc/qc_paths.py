# -*- coding: utf-8 -*-
r"""Session / QC-folder resolution shared by the calibration_qc scripts.

The 2026-09-18 session is the default and its QC outputs live flat in E:\calibration\qc (as produced
on the day). Any other session gets its own QC subfolder E:\calibration\qc\<session date>\ holding
corners/, the annotated timelapses, timeline_gui.html, frames/. Every script accepts
--session <dir | YYYY-MM-DD> (a date picks the latest session folder of that day)."""
from pathlib import Path

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
