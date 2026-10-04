# Reproducing the paddock calibration

Status 2026-10-04, FROZEN (`CALIBRATION_FINAL_2026-10-04.md`). The release is `ray_correction.json` = release 2026-10-03
revision g (`RELEASE_2026-10-03.md`; revision f kept as `ray_correction_2026-10-03f.json`) on the bundle
`camera_fit.npz` (sha256 6e4b54e9...) and the ground warp `frame_correction.json` (10-02b, used for label selection and the
comparisons). Everything below runs from this folder with `CALIB_ROOT=F:\calibration` (lab PC) - check that
`qc_paths.ROOT` is `F:\calibration` before a run.

## Verified

- `refit_rays.py` with the release flags (below) reproduces revision g **bit for bit** (largest difference over every
  coefficient and camera centre: 0.0; `F:\calibration\qc\refit_rays\S05_repro`), and without the `--sweep` line it
  reproduces revision f bit for bit, checked twice on 2026-10-04 (`G_design_cordfolds`, `T_trace`) after the opt-in
  options of 2026-10-03/04 (`--drone-cords`, `--cord-folds`, `--fit`, `--sweep`) were added.
- Environment: the `cv` conda env, Python 3.11.15, numpy 2.4.4, scipy 1.17.1, opencv(-contrib) 5.0.0, pycolmap 4.2.1
  (drone steps only), matplotlib 3.11.0. On the lab PC scipy.linalg dies silently unless cv2 is imported first (every
  script here imports it through paddock_map / qc_paths).

## Where the data are

| what | primary | backup |
|---|---|---|
| code, release files, committed labels and survey (`session_*_manual_quads.json`, `*_labelled_frames.csv`, drift files, `terrain_2026-10-02.json`, `survey_2026-10-03.json`, `drone_cords_2026-10-02.json`) | this repo | GitHub |
| calibration videos, sessions 2026-09-18 (x2), 09-19, 09-30 | `F:\calibration\session_*` | `Q:\hc997\SocialFieldRat2026\3rd_rat\calibration\session_*` (2026-10-04; file counts and bytes checked equal) |
| drone footage 09-30, 10-02, 10-03 (originals) and the recovered PTSC_0017 / 0018 | `F:\ATOM_001\DCIM`, `F:\calibration\drone` | `...\3rd_rat\calibration\drone_ATOM_001`, `drone_recovered` |
| house photos, pole-spacing sketch | `F:\calibration\houses`, `survey` | `...\3rd_rat\calibration\houses`, `survey` |
| derived data and the operator's labels: corner caches, cone / line labels, the drone reconstruction and anchor, ball tracks, the sweep detections, every run | `F:\calibration\qc` (19 GB) | `...\3rd_rat\calibration\qc` (2026-10-04; counts and bytes checked) |
| the hand-held sweep boards used by revision g (406 instances) | `F:\calibration\qc\trial_sweep\instances_v3.json` | this repo, `sweep_instances_2026-09-18_v3.json` (sha256 identical) |
| rigid-landmark labels (wall tops, pole edges) | analysis repo `Field2026_Social_analysis\cv\configs\landmarks\2026c` | GitHub (that repo) |

## The final fit and exactly what it reads

    set CALIB_ROOT=F:\calibration
    python refit_rays.py --out <dir> --deg 4 --sig-coef 0.05 --walltop --wt-w 1.0 --seam-w-deg 3 --no-tape-dist --boards ^
        --board-w 3 --drone-scale anchor --height-source drone --board-weak --terrain terrain_2026-10-02.json ^
        --sweep sweep_instances_2026-09-18_v3.json --sweep-w 0.5
    -> <dir>\RAYMAP.json  (= ray_correction.json, sha-bound to camera_fit.npz) and REFIT_RAYS.txt (all checks)
    (revision f: the same without the last option line)

Files it opened (traced with an audit hook, 2026-10-04, `F:\calibration\qc\refit_rays\T_trace\inputs_opened.json`):
- corner caches: `F:\calibration\qc\corners\CH01..CH06\` and `F:\calibration\qc\2026-09-19\corners\CH0x\` (~2,170 files);
- labels: `F:\calibration\qc\cone_labels_CH0x.json`, `line_labels_CH0x.json` (09-18) and the same under `qc\2026-09-30\`;
- bundle and warp: `F:\calibration\qc\camera_fit.npz`, `frame_correction.json`;
- drone: `F:\calibration\qc\camera_centres_2026-10-03.json`, `qc\drone_sfm\2026-10-02_all\anchor\anchor.json`,
  `board_scale.json`, `walltop_profile.json`;
- checks only: `F:\calibration\qc\2026-09-30\ball\track20\ball20_CH0x.json`, `ball20_flags.json`, `held20.json`;
- analysis repo: `landmarks_CH0x_20260918_*.json` (6 files);
- this folder: `paddock_map.py`, `raymap.py`, `refit_rays.py`, the manual-quad / labelled-frame / cone-corner files of 09-18
  and 09-19, `session_2026-09-19_drift.json`, `session_2026-09-30_drift_final.json`, `terrain_2026-10-02.json`;
- plus the session videos' frame sizes (ffprobe through `qc_paths`);
- revision g in addition: the sweep instances (`--sweep`), built by `board_sweep20_instances.py` from the sweep corner
  detections under `F:\calibration\qc\sweep20\` (`board_sweep20.py`, `board_sweep20_rescue.py`, the operator's clicks).

## The upstream chain (each step is a dated README section)

1. Plates: `qc_placements.py` (corner caches) -> `rescue_boards.py` -> `timeline_gui.py` / `label_timeline.py` (operator
   timeline; station identity) -> `manual_board_gui.py` / `manual_boards.py` (operator clicks) -> `fit_data.py`.
2. Bundle: `fit_cameras.py --out <dir>` (never without `--out`) -> `camera_fit.npz`; `frame_correction.py` and
   `refit_supplement.py` -> the 10-02b warp.
3. Ground labels: `cone_gui` / `line_gui.py` pages (operator) for 09-18 and 09-30; `landmark_track_drift.py` -> the
   session drift files.
4. Drone: `drone_sfm.py` (COLMAP; not bit-reproducible - its sparse models are consumed as frozen files under
   `qc\drone_sfm\2026-10-02_all`), `drone_landmark_gui.py` (operator) -> `drone_landmark_anchor.py` -> `anchor.json`;
   `drone_lens_triangulate.py` -> `camera_centres_2026-10-03.json`; `drone_walltop.py`; `drone_board_scale.py`;
   `drone_terrain.py` -> `terrain_2026-10-02.json`.
5. Ray fit: `refit_rays.py` (above).
6. Checks: `ball_detect.py` / `ball_track20.py` / `ball_sync20.py` (20 Hz ball), `handoff_map.py`, `camera_error_map.py`,
   `house_check.py`, `single_camera_check.py`, `sweep_ray_check.py` (hand-held sweep boards, `board_sweep20*.py`),
   `drone_line_check.py`, `pole_tape_check.py`.
