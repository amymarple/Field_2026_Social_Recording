"""Model selection, immutable evaluation, inference, BEV and legacy diagnostics."""
from pathlib import Path
from datetime import datetime
import math
import cv2
import numpy as np
from scipy.spatial import cKDTree
from .io import digest, read_json, write_json, new_dir, safe_input
from .session import validate_session
from .models import Mesh, fit_candidate, combined_map, validate_regions, FIELD_SIZE


def validate_dataset(data):
    validate_session(data["session"])
    if data.get("units") != "cm" or data["session_hash"] != digest(data["session"]):
        raise ValueError("Dataset session/units changed")
    placements = {p["position_id"]: p for p in data["session"]["placements"]}
    seen = set()
    for r in data["rows"]:
        p = placements[r["position_id"]]
        if r["split"] != p["split"] or r["region"] != p["regions"][r["channel"]]:
            raise ValueError("Dataset position split/region mismatch")
        key = r["channel"], r["position_id"], r["corner_id"]
        if key in seen:
            raise ValueError("Duplicate corner rows; aggregate captures first")
        seen.add(key)
        if not np.isfinite([r["pixel"], r["world_cm"]]).all():
            raise ValueError("Nonfinite control point")
        from .session import board_world
        if r["method"] == "charuco":
            from .board import make_board
            if not isinstance(r["corner_id"], int) or not 0 <= r["corner_id"] < 88:
                raise ValueError("Wrong ChArUco corner ID")
            local = make_board(data["session"]["board"]).getChessboardCorners()[r["corner_id"], :2]
        elif r["method"] == "manual_ground":
            local = np.asarray(r["local_cm"], float)
        else:
            raise ValueError("Unknown point method")
        if not np.allclose(board_world(p,[local])[0],r["world_cm"],atol=1e-5):
            raise ValueError("World point does not match measured placement and local point")


def metrics(rows, meshes):
    if not rows:
        raise ValueError("No evaluation points")
    pred, valid = combined_map(meshes, [r["pixel"] for r in rows])
    world = np.array([r["world_cm"] for r in rows])
    errors = np.linalg.norm(pred-world, axis=1)
    result = []
    for pid in sorted({r["position_id"] for r in rows}):
        ii = np.array([i for i, r in enumerate(rows) if r["position_id"] == pid])
        r = rows[ii[0]]
        complete = bool(valid[ii].all())
        result.append(dict(position_id=pid, region=r["region"], zone=r["zone"], depth=r["depth"],
                    ground_cm=world[ii].mean(axis=0).tolist(), n_corners=len(ii), valid=complete,
                    rmse_cm=float(np.sqrt(np.mean(errors[ii]**2))) if complete else None,
                    max_cm=float(errors[ii].max()) if complete else None,
                    residual_cm=(pred[ii]-world[ii]).mean(axis=0).tolist() if complete else None))
    complete = all(r["valid"] for r in result)
    return dict(positions=result, coverage_fraction=float(valid.mean()),
                rmse_cm=float(np.sqrt(np.mean([r["rmse_cm"]**2 for r in result]))) if complete else None,
                max_cm=max(r["max_cm"] for r in result) if complete else None)


def select(data, channel):
    validate_dataset(data)
    camera = data["session"]["cameras"][channel]
    rows = [r for r in data["rows"] if r["channel"] == channel]
    selected, comparisons, validations = [], [], []
    for region in camera["regions"]:
        train = [r for r in rows if r["region"] == region["id"] and r["split"] == "train"]
        val = [r for r in rows if r["region"] == region["id"] and r["split"] == "validation"]
        if len({r["position_id"] for r in train}) < 6 or len({r["position_id"] for r in val}) < 3:
            raise ValueError(f"{region['id']}: need >=6 training and >=3 validation positions")
        candidates = []
        for kind, lam in [("poly", 0), ("affine_mesh", 0)] + [("tps", x) for x in (0, 1e-6, 1e-4, 1e-2, 1)]:
            record = dict(region=region["id"], kind=kind, smoothing=lam)
            try:
                mesh = fit_candidate([r["pixel"] for r in train], [r["world_cm"] for r in train],
                    [r["position_id"] for r in train], region, camera["image_size"], kind, lam)
                score = metrics(val, [mesh])
                if score["rmse_cm"] is None:
                    raise ValueError("Incomplete validation coverage; supplement training or narrow declared region")
                record.update(rmse_cm=score["rmse_cm"], valid=True)
                candidates.append((score["rmse_cm"], mesh, score))
            except (ValueError, np.linalg.LinAlgError) as exc:
                record.update(valid=False, reason=str(exc))
            comparisons.append(record)
        if not candidates:
            raise ValueError(f"No deployable model for {region['id']}: {comparisons}")
        candidates.sort(key=lambda a: a[0])
        winner = candidates[0]
        for candidate in candidates:
            if candidate[1].metadata["kind"] == "affine_mesh" and candidate[0] <= winner[0]+1:
                winner = candidate
                break
        selected.append(winner[1])
        validations.extend(winner[2]["positions"])
    validate_regions(selected)
    artifact = dict(schema_version=1, type="ground_mesh_v1", channel=channel,
        status="provisional", units="cm", field_size_cm=FIELD_SIZE.tolist(),
        session_id=data["session"]["session_id"], dataset_hash=digest(data),
        valid_from=camera["valid_from"], valid_to=camera.get("valid_to"),
        image_size=camera["image_size"], pixel_transform=camera["pixel_transform"],
        stitching_settings=camera["stitching_settings"],
        board=data["session"]["board"], geometry_revision=data["session"]["geometry_revision"],
        regions=camera["regions"], meshes=[m.as_dict() for m in selected],
        validation_positions=validations, candidates=comparisons,
        created=datetime.now().astimezone().isoformat(),
        warning="Geometric ground mapping only. Provisional until independent test acceptance; no historical extrapolation.")
    artifact["artifact_hash"] = digest(artifact)
    return artifact


def load_artifact(path):
    a = read_json(path)
    if digest({k: v for k, v in a.items() if k != "artifact_hash"}) != a["artifact_hash"]:
        raise ValueError("Artifact checksum mismatch")
    if a["type"] != "ground_mesh_v1" or a["units"] != "cm":
        raise ValueError("Wrong model type/units")
    meshes = [Mesh.from_dict(m) for m in a["meshes"]]
    validate_regions(meshes)
    return a, meshes


def evaluate(data, artifact):
    validate_dataset(data)
    if artifact["dataset_hash"] != digest(data):
        raise ValueError("Dataset differs from model-selection snapshot")
    rows = [r for r in data["rows"] if r["channel"] == artifact["channel"] and r["split"] == "test"]
    meshes = [Mesh.from_dict(m) for m in artifact["meshes"]]
    report = metrics(rows, meshes)
    issues = []
    if len(report["positions"]) < 12:
        issues.append("Fewer than 12 independent test positions")
    for region in artifact["regions"]:
        p = [x for x in report["positions"] if x["region"] == region["id"]]
        if len(p) < 3:
            issues.append(f"{region['id']}: fewer than 3 test positions")
        elif not all(x["valid"] for x in p):
            issues.append(f"{region['id']}: incomplete coverage")
        else:
            limit, maximum = (10, 20) if region["threshold"] == "core" else (20, 30)
            if np.sqrt(np.mean([x["rmse_cm"]**2 for x in p])) > limit or max(x["max_cm"] for x in p) > maximum:
                issues.append(f"{region['id']}: regional acceptance threshold exceeded")
    # Enforce each advertised zone, not only a favourable global average.
    required_zones = {p["zone"] for p in artifact["validation_positions"]}
    required_zones.update(r["threshold"] for r in artifact["regions"])
    for zone in required_zones:
        p = [x for x in report["positions"] if x["zone"] == zone]
        limit, maximum = (10, 20) if zone == "core" else (20, 30)
        if len(p) < 3 or not all(x["valid"] for x in p):
            issues.append(f"{zone}: insufficient independent coverage")
        elif np.sqrt(np.mean([x["rmse_cm"]**2 for x in p])) > limit or max(x["max_cm"] for x in p) > maximum:
            issues.append(f"{zone}: exceeds RMSE {limit}/maximum {maximum} cm")
    if report["coverage_fraction"] < 1:
        issues.append("Some test corners are outside deployable regions")
    report["by_depth"] = {}
    for depth in ("near", "mid", "far"):
        subset = [p for p in report["positions"] if p["depth"] == depth]
        report["by_depth"][depth] = dict(n_positions=len(subset),
            rmse_cm=float(np.sqrt(np.mean([p["rmse_cm"]**2 for p in subset])))
            if subset and all(p["valid"] for p in subset) else None)
    for depth in {p["depth"] for p in artifact["validation_positions"]}:
        if report["by_depth"][depth]["n_positions"] == 0:
            issues.append(f"No final-test coverage for declared {depth} depth")
    report.update(status="accepted" if not issues else "failed", issues=issues,
                  channel=artifact["channel"], artifact_hash=artifact["artifact_hash"],
                  dataset_hash=artifact["dataset_hash"],
                  note="Position-balanced RMSE; maximum is worst individual corner. No reliable P95 claim with small samples.")
    return report


class GroundCalibration:
    """Drop-in-style point interface with explicit pixel convention and epoch."""
    def __init__(self, path, *, allow_provisional=False):
        self.artifact, self.meshes = load_artifact(path)
        if not allow_provisional and self.artifact["status"] != "accepted":
            raise ValueError("Calibration is provisional/failed; acceptance required for production use")

    def _epoch(self, timestamp):
        if timestamp is None:
            raise ValueError("Explicit frame timestamp required; do not apply to arbitrary historical footage")
        t = datetime.fromisoformat(timestamp)
        if t.tzinfo is None:
            raise ValueError("Timestamp needs UTC offset")
        a = self.artifact
        if t < datetime.fromisoformat(a["valid_from"]) or (a.get("valid_to") and t >= datetime.fromisoformat(a["valid_to"])):
            raise ValueError("Frame lies outside calibration epoch")

    def to_field(self, pts_px, *, timestamp, src_size=None, pixel_transform=None, return_valid=False):
        self._epoch(timestamp)
        a = self.artifact
        if pixel_transform != a["pixel_transform"]:
            raise ValueError("Explicit matching canonical pixel transform required")
        p = np.asarray(pts_px, float).reshape(-1, 2)
        if src_size is not None:
            src = np.asarray(src_size, float)
            if src.shape != (2,) or not np.isfinite(src).all() or np.any(src <= 0):
                raise ValueError("Invalid src_size")
            # Pixel-centre preserving resize; arbitrary crop/rotation is NOT scaling.
            p = (p+.5)*np.asarray(a["image_size"])/src-.5
        out, valid = combined_map(self.meshes, p)
        return (out, valid) if return_valid else out

    def to_pixel(self, pts_cm, *, timestamp, return_valid=False):
        self._epoch(timestamp)
        out, valid = combined_map(self.meshes, pts_cm, inverse=True)
        return (out, valid) if return_valid else out


def to_field(channel, pts_px, config_dir, calib=None, src_size=None, *, timestamp,
             pixel_transform, return_valid=False):
    """Same leading parameters as legacy field_coords.to_field; opt-in adapter."""
    c = calib or GroundCalibration(Path(config_dir)/f"{channel}_calib.json")
    if c.artifact["channel"] != channel:
        raise ValueError("Channel mismatch")
    return c.to_field(pts_px, timestamp=timestamp, src_size=src_size,
                      pixel_transform=pixel_transform, return_valid=return_valid)


def bev(artifact, image, cm_per_pixel=1.0):
    if not np.isfinite(cm_per_pixel) or not .5 <= cm_per_pixel <= 10:
        raise ValueError("cm_per_pixel must be 0.5..10")
    if [image.shape[1], image.shape[0]] != artifact["image_size"]:
        raise ValueError("BEV needs a canonical image with declared size")
    meshes = [Mesh.from_dict(m) for m in artifact["meshes"]]
    w, h = np.ceil(FIELD_SIZE/cm_per_pixel).astype(int)
    x, y = np.meshgrid((np.arange(w)+.5)*cm_per_pixel, (np.arange(h)+.5)*cm_per_pixel)
    ground = np.column_stack([x.ravel(), y.ravel()])
    uv, mask = combined_map(meshes, ground, True)
    mask &= (ground <= FIELD_SIZE).all(axis=1)
    uv[~mask] = -1
    output = cv2.remap(image, uv[:, 0].reshape(h, w).astype(np.float32),
                       uv[:, 1].reshape(h, w).astype(np.float32), cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT)
    alpha = mask.reshape(h, w).astype(np.uint8)*255
    positions = artifact["validation_positions"]
    centres = np.array([p["ground_cm"] for p in positions])
    errors = np.array([p["rmse_cm"] for p in positions])
    # Conservative local ranking, not a calibrated uncertainty estimate.
    k = min(3, len(centres))
    _, indices = cKDTree(centres).query(ground, k=k)
    score = errors[indices] if k == 1 else errors[indices].max(axis=1)
    score[~mask] = np.inf
    return np.dstack([output, alpha]), score.reshape(h, w)


def residual_svg(report, path):
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 -60 1300 730">',
             '<rect x="0" y="0" width="1219.2" height="609.6" fill="white" stroke="black"/>',
             '<text x="0" y="-20" font-size="20">Ground residuals: arrows x5; red = invalid</text>']
    import html
    for p in report["positions"]:
        x, y = p["ground_cm"]
        color = "#007a65" if p["valid"] else "#d22"
        lines.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
        lines.append(f'<text x="{x+7}" y="{y}" font-size="12">{html.escape(p["position_id"])}</text>')
        if p["valid"]:
            dx, dy = np.asarray(p["residual_cm"])*5
            lines.append(f'<path d="M{x},{y} l{dx},{dy}" stroke="{color}" stroke-width="2"/>')
    lines.append('</svg>')
    from .io import output_path
    output_path(path).write_text("\n".join(lines), encoding="utf-8")


def audit_legacy(config_dir, out):
    out = new_dir(out)
    summary = {}
    for channel in ("CH01", "CH02"):
        a = read_json(Path(config_dir)/f"{channel}_calib.json")
        if a["type"] != "poly":
            raise ValueError("Legacy audit expects polynomial")
        p = np.asarray(a["image_px"])
        from .models import features
        predicted = features(p) @ np.asarray(a["forward"]).T
        truth = np.asarray(a["world_points"])[:, :2]
        error = np.linalg.norm(predicted-truth, axis=1)
        report = dict(label="LEGACY TRAINING RESIDUALS, NOT INDEPENDENT ACCURACY", positions=[
            dict(position_id=n, ground_cm=w.tolist(), residual_cm=d.tolist(), valid=True,
                 error_cm=float(e)) for n, w, d, e in zip(a["landmarks"], truth, predicted-truth, error)])
        residual_svg(report, out/f"{channel}_legacy_residuals.svg")
        summary[channel] = dict(training_rmse_cm=float(np.sqrt(np.mean(error**2))),
                                image_size=a.get("image_size"), created=a["created"], points=report["positions"])
    write_json(out/"legacy_audit.json", summary)
    return summary
