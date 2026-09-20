"""Isolated checks of existing rescue functions, without launching video jobs."""
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np

cv2.setNumThreads(1)
HERE=Path(__file__).resolve().parent
board=cv2.aruco.CharucoBoard((12,9),.060,.045,cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
env=dict(cv2=cv2,np=np,board=board,OBJ=board.getChessboardCorners()[:,:2])
import board_detect as bd
env['chessboard_detect']=bd.chessboard_detect
source_hash=hashlib.sha256((HERE/'board_detect.py').read_bytes()).hexdigest()
files=[HERE.parent/'calibration.png'] + list(Path(r'E:\calibration\qc\frames').glob('detect_test*crop.jpg'))
rows=[]
for path in files:
    gray=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
    start=time.perf_counter()
    result=env['chessboard_detect'](gray,None)
    row=dict(file=str(path),source_sha256=source_hash,seconds=round(time.perf_counter()-start,3),corners=0 if result is None else len(result[1]),note=None if result is None else result[2])
    if result is not None:
        px,ids,_=result
        dp=cv2.aruco.DetectorParameters(); dp.minMarkerPerimeterRate=.005; dp.perspectiveRemovePixelPerCell=8; dp.errorCorrectionRate=.8
        cc,ci,mc,mi=cv2.aruco.CharucoDetector(board,detectorParams=dp).detectBoard(gray)
        if ci is not None:
            shared,a,b=np.intersect1d(ids,ci.ravel(),return_indices=True)
            row['shared_charuco_ids']=len(shared)
            if len(shared):
                errors=np.linalg.norm(px[a]-cc.reshape(-1,2)[b],axis=1)
                row['shared_id_median_px']=float(np.median(errors))
                row['shared_id_max_px']=float(errors.max())
        overlay=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        cv2.aruco.drawDetectedCornersCharuco(overlay,px.reshape(-1,1,2),ids.reshape(-1,1))
        cv2.imwrite(str(HERE/f'audit_chessboard_{path.stem}.jpg'),overlay)
    rows.append(row); print(row,flush=True)
(HERE/'audit_rescue_diagnostic.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
