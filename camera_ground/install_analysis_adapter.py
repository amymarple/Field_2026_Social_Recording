"""Opt-in compatibility update for an existing analysis field_coords.py.

Prepare and test first. --apply requires explicit filesystem authorization when
the analysis checkout is outside the current workspace. Existing models remain
on their unchanged implementation; no calibration files are overwritten.
"""
import argparse
import hashlib
from pathlib import Path


def adapt(source):
    source = source.replace("\r\n", "\n")
    if "ground_mesh_v1 adapter" in source:
        raise ValueError("Adapter is already installed")
    anchor = '        # distortion: if the fit was done in undistorted-pixel space, undistort before applying'
    insertion = '''        # ground_mesh_v1 adapter: opt-in, accepted artifacts only.
        if d.get("type") == "ground_mesh_v1":
            from camera_ground.pipeline import GroundCalibration
            return {"channel": channel, "type": "ground_mesh_v1",
                    "ground": GroundCalibration(p), "image_size": tuple(d["image_size"])}
'''
    if source.count(anchor) != 1:
        raise ValueError("Unexpected analysis source; review integration manually")
    source = source.replace(anchor, insertion+anchor)
    if source.count("def to_field(") != 1 or source.count("def to_pixel(") != 1:
        raise ValueError("Unexpected transform definitions")
    source = source.replace("def to_field(", "def _legacy_to_field(", 1)
    source = source.replace("def to_pixel(", "def _legacy_to_pixel(", 1)
    source += '''

# ground_mesh_v1 adapter. Legacy callers keep their original positional API.
def to_field(channel, pts_px, config_dir=CONFIG_DIR, calib=None, src_size=None,
             *, timestamp=None, pixel_transform=None, return_valid=False):
    c = calib or load_calib(channel, config_dir)
    if c["type"] == "ground_mesh_v1":
        return c["ground"].to_field(pts_px, timestamp=timestamp, src_size=src_size,
                                    pixel_transform=pixel_transform, return_valid=return_valid)
    result = _legacy_to_field(channel, pts_px, config_dir, c, src_size)
    return (result, np.isfinite(result).all(axis=1)) if return_valid else result


def to_pixel(channel, pts_cm, config_dir=CONFIG_DIR, calib=None,
             *, timestamp=None, return_valid=False):
    c = calib or load_calib(channel, config_dir)
    if c["type"] == "ground_mesh_v1":
        return c["ground"].to_pixel(pts_cm, timestamp=timestamp, return_valid=return_valid)
    result = _legacy_to_pixel(channel, pts_cm, config_dir, c)
    return (result, np.isfinite(result).all(axis=1)) if return_valid else result
'''
    # Existing __main__ block must execute AFTER wrappers are defined.
    block = 'if __name__ == "__main__":\n    _cli()'
    if source.count(block) != 1:
        raise ValueError("Unexpected CLI entrypoint")
    return source.replace(block, "", 1)+"\n\n"+block+"\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Analysis field_coords.py")
    parser.add_argument("--preview", required=True, help="Local proposed source output")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    target = Path(args.target).resolve()
    raw = target.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    proposed = adapt(raw.decode("utf-8-sig"))
    preview = Path(args.preview)
    if not args.apply:
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(proposed, encoding="utf-8")
        print(sha)
        return
    if args.expected_sha256 != sha or preview.read_text(encoding="utf-8") != proposed:
        raise ValueError("Source or reviewed patch changed; prepare and test again")
    plan = target.parents[2]/"implementation_plan"/"2026-09-09-ground-mesh-adapter.md"
    log = target.parents[2]/"change_log"/"2026-09-09-ground-mesh-adapter.md"
    if plan.exists() or log.exists():
        raise ValueError("Integration plan/log already exists")
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# Ground mesh compatibility adapter\n\nAdd an opt-in ground_mesh_v1 branch to field_coords. Preserve legacy transforms. Require accepted artifacts, explicit canonical pixel convention and timezone-aware epoch for new models. Install field-camera-ground in the analysis environment before using new artifacts. Do not alter historical calibration JSONs or recorder tasks.\n", encoding="utf-8")
    backup = target.with_name("field_coords.pre_ground_mesh.py.bak")
    with backup.open("xb") as f:
        f.write(raw)
    target.write_text(proposed, encoding="utf-8")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("# Ground mesh adapter\n\nAdded accepted-model loading and timestamp/pixel-convention-aware point transforms. Legacy leading arguments and calculations are unchanged. The implementation was prepared and tested before applying. No new calibration was installed, no real camera accuracy was claimed, and recording was not changed.\n", encoding="utf-8")
    print("Installed opt-in adapter; original source backed up")


if __name__ == "__main__":
    main()
