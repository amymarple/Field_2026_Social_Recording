"""Bounded detector diagnostic on existing stills; never writes calibration caches."""
import ast
import json
import time
from pathlib import Path
import cv2
import numpy as np

cv2.setNumThreads(1)
HERE = Path(__file__).resolve().parent
SOURCE = Path(r'E:\calibration\qc\frames')
BOARD = cv2.aruco.CharucoBoard((12,9), .060, .045,
    cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))

def params(wide=False):
    p = cv2.aruco.DetectorParameters()
    p.minMarkerPerimeterRate = .005
    p.perspectiveRemovePixelPerCell = 8
    p.errorCorrectionRate = .8
    if wide:
        p.adaptiveThreshWinSizeMax = 73
    return p

def count(c):
    return 0 if c is None else len(c)

# Load only the existing pure detector function, avoiding top-level video jobs.
tree = ast.parse((HERE/'qc_placements.py').read_text(encoding='utf-8-sig'))
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='detect_refined')
env = dict(cv2=cv2,np=np,REFINE_SCALE=3,
           det=cv2.aruco.CharucoDetector(BOARD,detectorParams=params()))
exec(compile(ast.Module(body=[fn],type_ignores=[]),'qc_placements.py','exec'),env)

paths = [SOURCE/name for name in (
    'detect_test_CH01_150620_crop.jpg','detect_test_CH01_151645_crop.jpg',
    'detect_test_CH01_152410_crop.jpg','detect_test_CH02_150420_crop.jpg',
    'CH01_h15_t600_crop_gray.png')]
paths += [HERE/'audit_CH01_150959.jpg', HERE/'audit_CH02_150807.jpg']
paths += [HERE.parent/'calibration.png']
paths += sorted(HERE.glob('audit_native_*.png'))
results=[]
# Approximate, manually reviewed outer outlines on existing diagnostic JPEGs.
# These are detection hypotheses only, NOT measured board poses or control points.
QUADS={
 'detect_test_CH01_150620_crop.jpg': [[719,718],[902,784],[957,972],[755,894]],
 'detect_test_CH01_151645_crop.jpg': [[515,628],[711,704],[762,1151],[558,1105]],
 'detect_test_CH02_150420_crop.jpg': [[519,637],[719,493],[693,676],[506,839]],
}
for path in paths:
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:
        continue
    row={'file':str(path),'shape':list(g.shape),'methods':{}}
    t=time.perf_counter()
    nm,nc,_,_,_=env['detect_refined'](g)
    row['methods']['existing_refined']={'markers':nm,'corners':nc,'seconds':round(time.perf_counter()-t,3)}
    for wide,check in ((False,True),(True,True),(False,False),(True,False)):
        cp=cv2.aruco.CharucoParameters(); cp.checkMarkers=check
        detector=cv2.aruco.CharucoDetector(BOARD,charucoParams=cp,detectorParams=params(wide))
        t=time.perf_counter()
        cc,ci,mc,mi=detector.detectBoard(g)
        label=f'wide_{wide}_check_{check}'
        row['methods'][label]={'markers':count(mi),'corners':count(ci),'seconds':round(time.perf_counter()-t,3)}
        if ci is not None:
            row['methods'][label]['ids']=ci.ravel().tolist()
    if path.name in QUADS:
        quad=np.array(QUADS[path.name],np.float32)
        for width,height in ((960,720),(720,960)):
            target=np.array([[40,40],[width+40,40],[width+40,height+40],[40,height+40]],np.float32)
            H=cv2.getPerspectiveTransform(quad,target)
            rect=cv2.warpPerspective(g,H,(width+80,height+80),borderValue=255)
            cc,ci,mc,mi=env['det'].detectBoard(rect)
            label=f'manual_rectify_{width}x{height}'
            row['methods'][label]={'markers':count(mi),'corners':count(ci)}
            if ci is not None:
                overlay=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
                original=cv2.perspectiveTransform(cc.reshape(-1,1,2),np.linalg.inv(H)).astype(np.float32)
                cv2.aruco.drawDetectedCornersCharuco(overlay,original,ci)
                cv2.imwrite(str(HERE/f'audit_rectified_{path.stem}_{width}.jpg'),overlay)
    results.append(row)
    print(path.name, {k:(v['markers'],v['corners']) for k,v in row['methods'].items()},flush=True)
(HERE/'audit_detector_benchmark.json').write_text(json.dumps({'opencv':cv2.__version__,'results':results},indent=2),encoding='utf-8')
