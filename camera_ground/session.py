"""Capture manifest, pixel convention and measured placement validation."""
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
from .board import detect, verify_spec
from .io import read_json, safe_input, file_digest, digest
from .models import valid_polygon, FIELD_SIZE


def template(board):
    placements = []
    for i, x in enumerate(range(60, 1141, 180)):
        for j, y in enumerate(range(30, 511, 120)):
            placements.append(placement(f"T{i+1}{j+1}", "train", x, y))
    for i, x in enumerate(range(150, 1051, 180)):
        for j, y in enumerate(range(90, 451, 120)):
            split = "validation" if (i+j) % 2 == 0 else "test"
            placements.append(placement(f"{'V' if split == 'validation' else 'E'}{i+1}{j+1}", split, x, y))
    return dict(schema_version=1, session_id="SET_DATE_AND_EPOCH", units="cm",
                status="pending_field_capture", board=board,
                physical_board_verified=False, five_squares_measured_cm=None,
                target_plane="ground", geometry_revision=None,
                cameras={ch: dict(image_size=[2160, 7680], geometry_reviewed=False,
                    stitching_settings=None, valid_from=None, valid_to=None,
                    pixel_transform=dict(decoded_size=[2160, 7680], rotate_cw=0,
                                         crop_xywh=None, output_size=[2160, 7680]),
                    regions=[dict(id="ground", threshold="core", polygon_px=[], exclude_px=[])])
                    for ch in ("CH01", "CH02")}, placements=placements,
                note="Proposed positions are NOT measured coordinates. Draw regions and seam exclusions on canonical reference images.")


def placement(pid, split, x, y):
    return dict(position_id=pid, split=split, proposed_origin_cm=[x, y],
                measured_origin_cm=None, x_axis_reference_cm=None, plane_height_cm=None,
                plane_verified=False, measurement_uncertainty_cm=None,
                regions={"CH01": None, "CH02": None}, zone="core", depth="unknown",
                capture_start=None, capture_end=None, notes="")


def transform_image(img, spec):
    expected = spec["decoded_size"]
    if [img.shape[1], img.shape[0]] != expected:
        raise ValueError("Decoded image size differs from declared pixel transform")
    rotation = spec["rotate_cw"]
    if rotation not in (0, 90, 180, 270):
        raise ValueError("rotate_cw must be 0,90,180,270")
    img = np.rot90(img, -(rotation//90)).copy()
    if spec["crop_xywh"] is not None:
        x, y, w, h = spec["crop_xywh"]
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > img.shape[1] or y+h > img.shape[0]:
            raise ValueError("Invalid crop")
        img = img[y:y+h, x:x+w]
    w, h = spec["output_size"]
    if min(w, h) <= 0:
        raise ValueError("Invalid output size")
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def validate_session(s):
    if s.get("schema_version") != 1 or s.get("units") != "cm" or s.get("target_plane") != "ground":
        raise ValueError("Require schema_version=1, units=cm, target_plane=ground")
    verify_spec(s["board"])
    measure = s.get("five_squares_measured_cm")
    if (s.get("physical_board_verified") is not True or not measure or len(measure) != 2
            or not np.isfinite(measure).all() or
            max(abs(np.asarray(measure)-s["board"]["square_cm"]*5)) > .1):
        raise ValueError("Verify physical board dimensions; update board definition if printed scale differs")
    if not s.get("geometry_revision") or s["session_id"] == "SET_DATE_AND_EPOCH":
        raise ValueError("Set session_id and measured geometry revision")
    placements = s["placements"]
    ids = [p["position_id"] for p in placements]
    if len(set(ids)) != len(ids):
        raise ValueError("A physical position must appear once; repeated frames must share its ID")
    origins = []
    for p in placements:
        if p["split"] not in ("train", "validation", "test"):
            raise ValueError("Unknown split")
        if p["measured_origin_cm"] is None:
            continue  # pending placements may exist but cannot be used
        origin = np.asarray(p["measured_origin_cm"], float)
        ref = np.asarray(p["x_axis_reference_cm"], float)
        if (origin.shape != (2,) or ref.shape != (2,) or not np.isfinite([origin, ref]).all()
                or np.linalg.norm(ref-origin) < 20):
            raise ValueError("Measured origin and distinct long-edge direction reference required")
        if p.get("plane_verified") is not True or p["plane_height_cm"] is None or abs(p["plane_height_cm"]) > .2:
            raise ValueError("Use ground-plane targets within 2 mm, or a separate measured-height model")
        uncertainty = p.get("measurement_uncertainty_cm")
        if uncertainty is None or not np.isfinite(uncertainty) or not 0 <= uncertainty <= 2:
            raise ValueError("Record measurement uncertainty <=2 cm")
        for old, split in origins:
            if np.linalg.norm(origin-old) < 1 and split != p["split"]:
                raise ValueError("Same measured location appears in different splits")
        origins.append((origin, p["split"]))
        if p["zone"] not in ("core", "edge", "seam") or p["depth"] not in ("near", "mid", "far"):
            raise ValueError("Set zone core/edge/seam and depth near/mid/far")
    for ch, c in s["cameras"].items():
        if ch not in ("CH01", "CH02") or not c["geometry_reviewed"] or not c["stitching_settings"]:
            raise ValueError("CH01/02 geometry and fixed stitching settings must be reviewed")
        date = datetime.fromisoformat(c["valid_from"])
        if date.tzinfo is None:
            raise ValueError("valid_from needs an explicit UTC offset")
        if c["image_size"] != c["pixel_transform"]["output_size"]:
            raise ValueError("Canonical size mismatch")
        names = [r["id"] for r in c["regions"]]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate region ID")
        for r in c["regions"]:
            valid_polygon(r["polygon_px"])
            if r["threshold"] not in ("core", "edge", "seam"):
                raise ValueError("Unknown region threshold")
            for hole in r.get("exclude_px", []):
                valid_polygon(hole)


def board_world(p, board_xy):
    origin = np.asarray(p["measured_origin_cm"], float)
    direction = np.asarray(p["x_axis_reference_cm"], float)-origin
    direction /= np.linalg.norm(direction)
    # Physical board +y must be CCW from its +x when viewed in the field frame.
    return origin + np.asarray(board_xy) @ np.array([direction, [-direction[1], direction[0]]])


def assemble(session, observation_paths):
    validate_session(session)
    placements = {p["position_id"]: p for p in session["placements"]}
    samples, source_ids = {}, set()
    for path in observation_paths:
        obs = read_json(path)
        ch, pid = obs["channel"], obs["position_id"]
        if ch not in session["cameras"] or pid not in placements:
            raise ValueError("Observation channel or position is not in session")
        p, camera = placements[pid], session["cameras"][ch]
        if p["measured_origin_cm"] is None:
            raise ValueError(f"Position {pid} has not been measured")
        if obs.get("board_hash") != session["board"]["board_hash"] or obs["pixel_transform"] != camera["pixel_transform"]:
            raise ValueError("Board or pixel convention mismatch")
        if obs.get("reviewed") is not True:
            raise ValueError("Review corner overlays (especially seam) before assembling")
        frame_id = (ch, obs["source"]["sha256"], obs["source"].get("frame_pts_s"))
        if frame_id in source_ids:
            raise ValueError("A frame cannot be assigned to multiple positions or used twice")
        source_ids.add(frame_id)
        region_id = p["regions"][ch]
        region = next((r for r in camera["regions"] if r["id"] == region_id), None)
        if region is None:
            raise ValueError("Set position's camera region")
        # Observation IDs must have unique points and correct local coordinates.
        seen = set()
        for point in obs["points"]:
            key = point["id"]
            if key in seen:
                raise ValueError("Duplicate corner ID in frame")
            seen.add(key)
            if obs.get("method") == "charuco":
                if not isinstance(key, int) or not 0 <= key < 88:
                    raise ValueError("Invalid ChArUco corner ID")
                from .board import make_board
                local = make_board(session["board"]).getChessboardCorners()[key, :2]
            elif obs.get("method") == "manual_ground":
                local = np.asarray(point["local_cm"], float)
            else:
                raise ValueError("Unknown observation method")
            px = np.asarray(point["pixel"], float)
            world = board_world(p, [local])[0]
            if not np.isfinite(px).all() or px.shape != (2,) or not ((px >= 0) & (px < camera["image_size"])).all():
                raise ValueError("Invalid canonical pixel")
            if not ((world >= 0) & (world <= FIELD_SIZE)).all():
                raise ValueError("World control point outside field")
            from shapely import Point
            shape = valid_polygon(region["polygon_px"])
            if not shape.covers(Point(px)) or any(valid_polygon(h).covers(Point(px)) for h in region.get("exclude_px", [])):
                continue  # explicitly excluded corners never enter any fit
            sample_key = (ch, pid, str(key))
            if sample_key in samples and (samples[sample_key]["method"] != obs["method"] or
                    not np.allclose(samples[sample_key]["local_cm"], local, atol=1e-8)):
                raise ValueError("Repeated corner ID has inconsistent local coordinates/method")
            samples.setdefault(sample_key, dict(pixels=[], world=world.tolist(), p=p, corner_id=key,
                method=obs["method"], local_cm=np.asarray(local).tolist()))["pixels"].append(px)
    rows = []
    for (ch, pid, _), v in samples.items():
        px = np.median(v["pixels"], axis=0)
        spread = float(np.max(np.linalg.norm(np.asarray(v["pixels"])-px, axis=1)))
        if spread > 3:
            raise ValueError(f"Unstable target/camera at {ch}/{pid}: >3 canonical pixels")
        if v["method"] == "charuco" and len(v["pixels"]) < 3:
            raise ValueError(f"{ch}/{pid}: need >=3 reviewed frames per retained ChArUco corner")
        p = v["p"]
        rows.append(dict(channel=ch, position_id=pid, split=p["split"], region=p["regions"][ch],
                         zone=p["zone"], depth=p["depth"], corner_id=v["corner_id"],
                         pixel=px.tolist(), world_cm=v["world"], method=v["method"], local_cm=v["local_cm"],
                         frame_count=len(v["pixels"]), spread_px=spread))
    if not rows:
        raise ValueError("No usable observations")
    return dict(schema_version=1, units="cm", session=session, session_hash=digest(session),
                observations=[dict(path=str(Path(p).resolve()), sha256=file_digest(p)) for p in observation_paths],
                rows=rows)


def observe_image(path, session, channel, pid):
    source = safe_input(path)
    img = cv2.imread(str(source))
    if img is None:
        raise ValueError("Cannot decode image")
    camera = session["cameras"][channel]
    img = transform_image(img, camera["pixel_transform"])
    ids, corners, _ = detect(img, session["board"])
    obs = dict(channel=channel, position_id=pid, method="charuco", reviewed=False,
               board_hash=session["board"]["board_hash"], pixel_transform=camera["pixel_transform"],
               source=dict(path=str(source), sha256=file_digest(source), frame_pts_s=None),
               points=[dict(id=int(i), pixel=p.tolist()) for i, p in zip(ids, corners)])
    for i, p in zip(ids, corners):
        at = tuple(np.rint(p).astype(int))
        cv2.circle(img, at, 5, (0, 255, 0), 2)
        cv2.putText(img, str(i), at, cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 255), 1)
    return obs, img
