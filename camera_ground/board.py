"""Recover the actual board layout; never guess dictionary IDs."""
import cv2
import numpy as np
from .io import safe_input, file_digest, digest


def dictionary(name):
    if not name.startswith("DICT_5X5_") or not hasattr(cv2.aruco, name):
        raise ValueError("Unsupported 5x5 ArUco dictionary")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def make_board(spec):
    board = cv2.aruco.CharucoBoard(tuple(spec["squares_xy"]),
                                  float(spec["square_cm"]), float(spec["marker_cm"]),
                                  dictionary(spec["dictionary"]),
                                  np.asarray(spec["ids"], np.int32))
    board.setLegacyPattern(spec["legacy_pattern"])
    return board


def identify(path, square_cm=6.0, marker_cm=4.5):
    if not 0 < marker_cm < square_cm:
        raise ValueError("Require 0 < marker size < square size (cm)")
    img = cv2.imread(str(safe_input(path)), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Cannot decode board image")
    h, w = img.shape
    if abs(w / h - 12 / 9) > .001:
        raise ValueError("Expected uncropped 12-column, 9-row reference image")
    matches = []
    # Larger OpenCV dictionaries share prefixes; record every compatible name.
    for name in ("DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000"):
        corners, ids, _ = cv2.aruco.ArucoDetector(dictionary(name)).detectMarkers(img)
        if ids is None or len(ids) != 54 or len(set(ids.ravel())) != 54:
            continue
        cells = {}
        for c, marker_id in zip(corners, ids.ravel()):
            center = c.reshape(4, 2).mean(axis=0)
            col, row = int(center[0] / (w / 12)), int(center[1] / (h / 9))
            if (row + col) % 2 != 1 or (row, col) in cells:
                raise ValueError("Unexpected board cell layout")
            cells[row, col] = int(marker_id)
        ordered = [cells[r, c] for r in range(9) for c in range(12) if (r + c) % 2]
        for legacy in (False, True):
            spec = {"squares_xy": [12, 9], "square_cm": square_cm,
                    "marker_cm": marker_cm, "dictionary": name,
                    "ids": ordered, "legacy_pattern": legacy}
            board = make_board(spec)
            # Compare reconstructed source, including marker rotations and parity.
            rebuilt = board.generateImage((w, h), marginSize=0, borderBits=1)
            difference = float(np.mean((rebuilt > 127) != (img > 127)))
            detector = cv2.aruco.CharucoDetector(board)
            cc, ci, _, _ = detector.detectBoard(img)
            if ci is not None and len(ci) == 88 and difference < .005:
                matches.append((spec, difference))
                break
    if not matches:
        raise ValueError("No dictionary/layout reproduces all 54 markers and 88 corners")
    spec, difference = matches[0]
    spec.update(schema_version=1, units="cm", compatible_dictionaries=[m[0]["dictionary"] for m in matches],
                reference_sha256=file_digest(path), source_image=str(safe_input(path)),
                image_size=[w, h], marker_count=54, corner_count=88,
                reconstruction_difference_fraction=difference,
                physical_dimensions_verified=False,
                note="Smallest compatible dictionary; original dictionary capacity is not identifiable from shared IDs")
    spec["board_hash"] = digest(spec)
    return spec


def verify_spec(spec):
    contents = {k: v for k, v in spec.items() if k != "board_hash"}
    if digest(contents) != spec["board_hash"]:
        raise ValueError("Board definition changed; regenerate board definition")


def detector_params():
    """OpenCV's default minMarkerPerimeterRate=0.03 is relative to the LARGEST image side: on the
    2160x7680 panorama it rejects every marker under ~58 px, i.e. every ground board beyond ~3 m
    (measured 2026-09-18: 0 markers with defaults, 19 on the full frame with these settings)."""
    p = cv2.aruco.DetectorParameters()
    p.minMarkerPerimeterRate = 0.005
    p.perspectiveRemovePixelPerCell = 8
    p.errorCorrectionRate = 0.8
    return p


def detect(image, spec, refine_scale=3):
    verify_spec(spec)
    board = make_board(spec)
    detector = cv2.aruco.CharucoDetector(board, detectorParams=detector_params())
    corners, ids, mk_corners, mk_ids = detector.detectBoard(image)
    # Far boards: re-detect on an upscaled crop of the board region (0 -> ~47 corners at 6-7 m).
    if mk_ids is not None and len(mk_ids) and refine_scale > 1:
        allc = np.concatenate([m.reshape(-1, 2) for m in mk_corners])
        x0, y0 = allc.min(axis=0); x1, y1 = allc.max(axis=0)
        pad = 0.35 * max(x1 - x0, y1 - y0) + 20
        h, w = image.shape[:2]
        x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
        x1, y1 = int(min(w, x1 + pad)), int(min(h, y1 + pad))
        crop = image[y0:y1, x0:x1]
        if crop.size and max(crop.shape[:2]) * refine_scale <= 6000:
            up = cv2.resize(crop, None, fx=refine_scale, fy=refine_scale, interpolation=cv2.INTER_CUBIC)
            c2, i2, _, mi2 = detector.detectBoard(up)
            if i2 is not None and (ids is None or len(i2) > len(ids)):
                corners = c2.reshape(-1, 1, 2) / refine_scale + np.array([x0, y0], float)
                ids = i2
    if ids is None:
        raise ValueError("No ChArUco corners; use measured flat manual markers")
    ids = ids.ravel()
    xy = board.getChessboardCorners()[ids, :2]
    if len(ids) < 12 or len(np.unique(xy[:, 0])) < 3 or len(np.unique(xy[:, 1])) < 3:
        raise ValueError("Need >=12 corners across >=3 rows and >=3 columns")
    return ids, corners.reshape(-1, 2), xy
