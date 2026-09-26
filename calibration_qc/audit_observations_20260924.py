"""Read small existing corner caches, without source writes or fitting."""
import collections
import json
import sys
from pathlib import Path
import numpy as np
import cv2
import qc_paths
import fit_data as fd
import paddock_map as pm

cv2.setNumThreads(1)
ROOT=qc_paths.ROOT
SESS={'2026-09-18':'session_2026-09-18_13-54-34','2026-09-19':'session_2026-09-19_12-23-53'}
def resolve_readonly(arg=None):
    date='2026-09-18' if arg is None else str(arg)
    session=ROOT/SESS[date]
    qc=ROOT/'qc' if date=='2026-09-18' else ROOT/'qc'/date
    assert session.is_dir() and qc.is_dir()
    return session,qc
# The standard resolver calls mkdir even for reading. Avoid that mutation here.
qc_paths.resolve=resolve_readonly
for date,name in SESS.items():
    for cam in ('CH01','CH02','CH03','CH04','CH05','CH06'):
        qc_paths._SIZE[(str(ROOT/name),cam)]=(2160,7680) if cam in ('CH01','CH02') else ((4512,2512) if cam in ('CH03','CH04') else (2560,1920))
allp=fd.all_placements()
z=np.load(ROOT/'qc'/'camera_fit.npz',allow_pickle=False)
drop={tuple(s.split('|')[:4]) for s in z['dropped_views']}
eligible=[p for p in allp if not p['bad'] and not p['weak']]
used=[p for p in eligible if (p['cam'],p['session'],p['station'],p['win']) not in drop]
report={'assembled_views':len(allp),'bad_views':sum(p['bad'] for p in allp),
    'weak_not_bad_views':sum(p['weak'] and not p['bad'] for p in allp),
    'eligible_before_fit_rejection':len(eligible),'after_saved_rejections':len(used),
    'corners_after_rejection':sum(len(p['ids']) for p in used),
    'methods_after_rejection':dict(collections.Counter(p['method'] for p in used)),
    'predicted_marker_views':[{'camera':p['cam'],'station':p['station'],'session':p['session'],
        'corners':len(p['ids']),'sigma_px':p['sigma']} for p in used if p['method']=='rect-markers']}
corrections=json.loads((ROOT/'qc'/'frame_correction.json').read_text())['cameras']
cams={}
for i,cam in enumerate(z['units']):
    cams[cam]=pm.Camera(cam,z['models'][i],z['intr'][i],z['cam_rvec'][i],z['cam_tvec'][i],
        qc_paths._SIZE[(str(ROOT/SESS['2026-09-18']),cam)],corrections[cam])
for tag,views in [('all_accepted',used),('exclude_rect_markers_majority', [p for p in used if p['method']!='rect-markers'])]:
    shared={}
    for p in views:
        xy=cams[p['cam']].to_paddock(p['px'],z_mm=6)
        for cid,q in zip(p['ids'],xy):
            if np.isfinite(q).all():
                shared.setdefault((p['session'],p['station'],p['win'],int(cid)),[]).append(q)
    distances=[]; placements={}
    for key,points in shared.items():
        if len(points)<2: continue
        arr=np.array(points)
        d=float(np.linalg.norm(arr[:,None,:]-arr[None,:,:],axis=2).max())
        distances.append(d); placements.setdefault(key[:3],[]).append(d)
    a=np.array(distances); b=np.array([np.median(d) for d in placements.values()])
    report[tag]={'shared_corners':len(a),'shared_placements':len(b),
        'corner_median_p90_max_mm':[float(np.median(a)),float(np.percentile(a,90)),float(a.max())],
        'fraction_corner_disagreement_le_50mm':float(np.mean(a<=50)),
        'fraction_corner_disagreement_le_100mm':float(np.mean(a<=100)),
        'placement_medians_le_50mm':int(np.sum(b<=50)),
        'placement_medians_le_100mm':int(np.sum(b<=100))}
report['caution']='Removing marker-predicted views changes the evaluation set; it does not isolate a causal effect or establish independent accuracy.'
output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_suffix('.json')
output.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
