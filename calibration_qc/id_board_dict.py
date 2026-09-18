# -*- coding: utf-8 -*-
"""Identify the ArUco dictionary + CharucoBoard layout of a board artwork image.
Result for calibration.png (2026-09-18): 54 markers ids 0-53, only 5X5 dictionaries match,
DICT_5X5_100 is the smallest containing id 53; CharucoBoard((12, 9), 0.060, 0.045) interpolates
all 88 inner corners (non-legacy pattern)."""
import sys
import cv2

img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else r"..\calibration.png", cv2.IMREAD_GRAYSCALE)
print("image:", img.shape, "cv2:", cv2.__version__)
cands = ["DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000",
         "DICT_4X4_50", "DICT_6X6_250", "DICT_APRILTAG_36h11"]
results = {}
for name in cands:
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))
    corners, ids, _ = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters()).detectMarkers(img)
    n = 0 if ids is None else len(ids)
    results[name] = n
    print(f"{name:22s} markers={n:3d} id_range={None if ids is None else (int(ids.min()), int(ids.max()))}")
best = max(results, key=results.get)
print("BEST:", best)
d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, best))
for sx, sy in [(12, 9), (9, 12)]:
    board = cv2.aruco.CharucoBoard((sx, sy), 0.060, 0.045, d)
    ch_corners, ch_ids, _, _ = cv2.aruco.CharucoDetector(board).detectBoard(img)
    print(f"CharucoBoard {sx}x{sy}: interpolated corners = {0 if ch_ids is None else len(ch_ids)} (expect {(sx-1)*(sy-1)})")
