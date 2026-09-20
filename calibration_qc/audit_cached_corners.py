"""Read-only cache audit; stationary runs are NOT verified field stations."""
import datetime as dt
import json
from pathlib import Path
import re
import numpy as np

ROOT = Path(r'E:\calibration\qc\corners')
OUT = Path(__file__).with_name('audit_2026-09-19_cache.json')

def load_frame(path):
    with np.load(path, allow_pickle=False) as z:
        ids, px = z['ids'].astype(int), z['px'].astype(float)
        seg, rel = str(z['seg'].item()), float(z['t_rel'])
    stamp = re.search(r'(2026-09-18_\d\d-\d\d-\d\d)_to_', seg)
    if not stamp:
        raise ValueError(f'Unrecognized closed segment: {seg}')
    time = dt.datetime.strptime(stamp[1], '%Y-%m-%d_%H-%M-%S') + dt.timedelta(seconds=rel)
    valid = (px.shape == (len(ids), 2) and np.isfinite(px).all()
             and len(set(ids)) == len(ids) and np.all((ids >= 0) & (ids < 88)))
    spread = valid and len(ids) >= 12 and len(set(ids % 11)) >= 3 and len(set(ids // 11)) >= 3
    return dict(time=time, ids=ids, px=px, valid=bool(valid), spread=bool(spread), file=path.name)

def stationary(frames, tolerance):
    runs, run = [], []
    def finish():
        if len(run) >= 3 and (run[-1]['time'] - run[0]['time']).total_seconds() >= 3:
            runs.append({'start':run[0]['time'].isoformat(), 'end':run[-1]['time'].isoformat(),
                         'frames':len(run), 'first_cache':run[0]['file']})
    for f in frames:
        compatible = False
        if run and f['spread'] and (f['time'] - run[-1]['time']).total_seconds() <= 5:
            # Compare against the first frame, preventing accumulated motion drift.
            ids, a, b = np.intersect1d(run[0]['ids'], f['ids'], return_indices=True)
            if len(ids) >= 12 and len(set(ids % 11)) >= 3 and len(set(ids // 11)) >= 3:
                dist = np.linalg.norm(run[0]['px'][a] - f['px'][b], axis=1)
                compatible = np.median(dist) <= tolerance and np.quantile(dist,.9) <= 2*tolerance
        if not compatible:
            finish()
            run = []
        if f['spread']:
            run.append(f)
    finish()
    return runs

result = {'limitations': ['Cached detections only: no detection-rate denominator.',
    'Stationary runs can split one placement or include a stationary hand-held board.',
    'No independent station identity, ground height, orientation, or metric accuracy verified.'],
    'ground_window': ['2026-09-18T15:01:00','2026-09-18T15:40:20'], 'cameras':{}}
for camera in sorted(ROOT.iterdir()):
    if not camera.is_dir():
        continue
    frames = sorted((load_frame(p) for p in camera.glob('*.npz')), key=lambda f:f['time'])
    ground = [f for f in frames if '15:01:00' <= f['time'].strftime('%H:%M:%S') <= '15:40:20']
    result['cameras'][camera.name] = {
        'cached_frames':len(frames), 'ground_window_frames':len(ground),
        'invalid_frames':sum(not f['valid'] for f in frames),
        'ground_spread_pass':sum(f['spread'] for f in ground),
        'ground_id0_visible':sum(0 in f['ids'] for f in ground),
        'stationary_3px':stationary(ground,3), 'stationary_10px':stationary(ground,10)}
OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
for cam, x in result['cameras'].items():
    print(cam, {k:len(v) if isinstance(v,list) else v for k,v in x.items()})
print(OUT)
