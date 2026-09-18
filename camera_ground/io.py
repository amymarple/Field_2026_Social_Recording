"""Explicit, local-only inputs and immutable artifact outputs."""
import hashlib
import json
from pathlib import Path


def safe_input(path, *, video=False):
    raw = str(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ValueError("Only local analysis files are allowed; no streams or network shares")
    p = Path(path).resolve()
    normalized = str(p).replace("\\", "/").lower()
    if "/wiser/data/" in normalized:
        raise ValueError("Live WISER data is forbidden")
    if p.suffix.lower() in (".mp4", ".wav") and "_to_" not in p.name:
        raise ValueError("Open recording segments are forbidden")
    if video and (p.suffix.lower() != ".mp4" or "_to_" not in p.name):
        raise ValueError("Video must be an explicitly named closed *_to_*.mp4 segment")
    if not p.is_file():
        raise FileNotFoundError(p)
    return p


def read_json(path):
    return json.loads(safe_input(path).read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(safe_input(path).read_bytes()).hexdigest()


def output_path(path):
    p = Path(path).resolve()
    s = str(p).replace("\\", "/").lower()
    if str(p).startswith("\\\\") or any(x in s for x in (
        "/reolink_record/", "/thermal_record/", "/ultramic_record/",
        "/nvr_rescue/", "/wiser/data/", "/wild/")):
        raise ValueError("Output must not target production recording/data directories")
    return p


def new_dir(path):
    p = output_path(path)
    p.mkdir(parents=True, exist_ok=False)
    return p


def write_json(path, value):
    p = output_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
