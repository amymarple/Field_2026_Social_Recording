"""Read-only checks of the released fit/warp; writes audit output only in the repo."""
import hashlib
import json
import sys
from pathlib import Path
import cv2
import numpy as np
import paddock_map as pm
import fit_models as fm

HERE = Path(__file__).resolve().parent
FIT = pm.FIT
cv2.setNumThreads(1)
z = np.load(FIT, allow_pickle=False)
bp = z['board_pose']
rot = np.array([cv2.Rodrigues(p[:3])[0] for p in bp])
height = (rot @ np.array([360.,270.,0.]))[:,2] + bp[:,5]
tilt = np.degrees(np.arccos(np.clip(np.abs(rot[:,2,2]),-1,1)))
report = {'fit_sha256': hashlib.sha256(FIT.read_bytes()).hexdigest(),
    'board_count': len(bp), 'height_centre_mm_min_max': [float(height.min()),float(height.max())],
    'height_error_from_6mm_rms':float(np.sqrt(np.mean((height-6)**2))),
    'boards_over_10mm_from_plane':int(np.sum(np.abs(height-6)>10)),
    'boards_over_50mm_from_plane':int(np.sum(np.abs(height-6)>50)),
    'tilt_rms_deg':float(np.sqrt(np.mean(tilt**2))),
    'negative_Rzz_count':int(np.sum(rot[:,2,2]<0)),
    'dropped_views':z['dropped_views'].tolist(), 'warp':{}, 'sources':{}}
for name in ('frame_correction.json','CALIBRATION_FIT.txt'):
    repo=(HERE/name).read_bytes()
    source=(FIT.parent/name).read_bytes()
    report['sources'][name]={'repo_equals_source':repo==source,'sha256':hashlib.sha256(source).hexdigest()}
corrections=json.loads((HERE/'frame_correction.json').read_text())['cameras']
xx,yy=np.meshgrid(np.linspace(0,480,241),np.linspace(0,240,121))
p=np.stack([xx.ravel(),yy.ravel()],1)*25.4
for cam,corr in corrections.items():
    mapped=pm.fit_to_physical(p,corr)
    dx=(pm.fit_to_physical(p+[.01,0],corr)-mapped)/.01
    dy=(pm.fit_to_physical(p+[0,.01],corr)-mapped)/.01
    det=dx[:,0]*dy[:,1]-dy[:,0]*dx[:,1]
    back=pm.physical_to_fit(mapped,corr)
    err=np.linalg.norm(back-p,axis=1)
    report['warp'][cam]={'grid_points':len(p),'det_min_max':[float(det.min()),float(det.max())],
        'nonpositive_determinants':int(np.sum(det<=0)),
        'grid_roundtrip_max_mm':float(np.nanmax(err)),
        'max_displacement_mm':float(np.max(np.linalg.norm(mapped-p,axis=1)))}
    idx=list(z['units']).index(cam)
    size=(2160,7680) if cam in ('CH01','CH02') else ((4512,2512) if cam in ('CH03','CH04') else (2560,1920))
    c=pm.Camera(cam,z['models'][idx],z['intr'][idx],z['cam_rvec'][idx],z['cam_tvec'][idx],size,corr)
    pixel=np.array(c.upright_size)/2
    delta=(c.to_paddock(pixel,z_mm=1)-c.to_paddock(pixel,z_mm=0))
    report['warp'][cam]['centre_pixel_height_derivative']=float(np.linalg.norm(delta))
    report['warp'][cam]['helper_height_sensitivity']=c.height_sensitivity()
    outside=np.array([[-10.,size[0]*.3],[c.upright_size[0]+10.,c.upright_size[1]*.6]])
    report['warp'][cam]['out_of_image_pixels_with_finite_xy']=int(np.isfinite(c.to_paddock(outside)).all(1).sum())
    # Perfect, flat synthetic boards under the exact released forward model.
    # Test the assertion that raw-image homography failure proves wrong IDs.
    bx,by=np.meshgrid(np.arange(1,12)*60.,np.arange(1,9)*60.)
    obj=np.stack([bx.ravel(),by.ravel()],1)
    hom_errors=[]
    for ox in np.linspace(0,11000,12):
        for oy in np.linspace(0,5400,7):
            world=np.column_stack([obj+[ox,oy],np.full(len(obj),6.)])
            campts=world@c.R.T+c.tvec
            uv=fm.project(c.model,c.intr,campts)
            W,H=c.upright_size
            if np.any((uv[:,0]<0)|(uv[:,0]>=W)|(uv[:,1]<0)|(uv[:,1]>=H)) or np.any(campts[:,2]<=0):
                continue
            hom,_=cv2.findHomography(obj.reshape(-1,1,2),uv.reshape(-1,1,2),0)
            pred=cv2.perspectiveTransform(obj.reshape(-1,1,2),hom).reshape(-1,2)
            hom_errors.append(float(np.sqrt(np.mean(np.sum((pred-uv)**2,axis=1)))))
    report['warp'][cam]['synthetic_perfect_board_homography']={'full_visible_boards':len(hom_errors),
        'max_rms_px':max(hom_errors,default=None),'above_4px':sum(e>4 for e in hom_errors)}
report['notes']=['Warp grid is the raw fit rectangle, not a certified visibility/support region.',
    'Positive sampled Jacobians do not prove global injectivity.',
    'No fitting, video decoding, or source-data mutation was performed.']
output = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE/'audit_release_20260924.json'
output.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
