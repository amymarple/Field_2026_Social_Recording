# Handover: a metric, photorealistic 3-D reconstruction of the rat paddock for Unity

To: ChatGPT Astra, taking over. From: the camera-calibration session (Claude) of the `Field_2026_Social_Recording`
project, 2026-10-05, at the operator's request. Everything referred to below is in this folder,
`Q:\hc997\SocialFieldRat2026\render\`, unless a path says otherwise.

## 1. The goal

Build the outdoor rat paddock as a Unity scene that is **accurate in metres and realistic in appearance**:
photoreal surfaces (grass, corrugated walls, wooden poles, shelters, net) on geometry that matches the real site to a
few centimetres, in a coordinate frame tied to the study's camera calibration, so that a virtual camera placed where a
real rig camera hangs sees what that camera saw. The paddock no longer exists (it was demolished after the last
cohort, autumn 2026): this footage is all there will ever be.

Deliverable (Section 8): a Unity-ready asset set + a short report with the validation numbers of Section 7.

## 2. The site (facts; do not re-derive)

| item | value | source |
|---|---|---|
| location | lab paddock near Cornell University, Ithaca NY; drone GPS ~ (lat 42.4610, lon -76.4448) - consumer GPS, metres | `drone_original\DCIM\*.SRT` |
| inside size | 40 x 20 ft = 12.19 x 6.10 m | design |
| walls | ~1 m corrugated metal sheet, white / grey; wall tops 0.87-1.05 m above the local ground (west wall ~1.00 m at both ends, a dip to 0.87-0.90 m between y 37 and 97 in), orange flagging on the tops in Sept-Oct | `reconstruction\colmap_2026-10-02_all\walltop_profile.json`, `WALLTOP_PROFILE.txt` |
| poles | 15 wooden poles in 3 rows (A y = 0, B y = 120 in, C y = 240 in) x 5 columns (x = 0, 120, 240, 360, 480 in), tops ~2.3-2.5 m; diameter ~13-15 cm (B1 / B2 / B3 circumference 18.5 / 16.5 / 17.5 in); they LEAN by an unmeasured few degrees; the operator's tape at ~1.05 m height: spans 113.75-125.5 in, rows A / C 480.25 / 480.0 in end to end, row B 469 in | `geometry\survey_2026-10-03.json`, `pictures\survey\pole_spacing_sketch_2026-10-03.jpg` |
| overhead | black net on a top frame between the pole tops; wires / cables along the poles; camera mounts and boxes on poles | rig and drone footage |
| shelters ("houses") | 2 white wooden boxes with a gabled roof: body 62.55 x 45.72 cm, eaves 58.5-62 cm and ridge 87.5-88.2 cm above the soil, ridge length 66 cm, gable rise 24-24.5 cm. HOUSE_1 (roof number 4): centre (147.5, 121.7) in, ridge 90.3 deg from x; HOUSE_2 (roof 7): centre (342.4, 117.7) in, ridge 92.0 deg from x (09-18 geometry; HOUSE_1 was moved on 09-18) | `geometry\survey_2026-10-03.json`, `geometry\HOUSE_CHECK_2026-10-04_revg.txt`, `pictures\house_measurements_2026-10-03\` (the operator's measurements drawn on the photos, cm) |
| other fixed objects | two water towers (TOWER_1 near (225, 221) in, TOWER_2 near (297, 7) in), a white stool / step, boxes; a step ladder inside on calibration days | drone anchor report, frames |
| ground | grass and clover, tall and changing over the season; relief sd 21 mm on a 2 ft grid (floor within +-5 cm of a plane); the floor plane rises 14.6 mm/m along x and 34.6 mm/m along y against gravity (~18 cm west -> east, ~21 cm row A -> row C) | `geometry\terrain_2026-10-02.json`, `survey_2026-10-03.json` (ground_tilt_vs_gravity) |
| rig cameras | 6 cameras at 2.2-2.3 m: CH01 / CH02 Reolink Duo 3 dual-lens stitched panoramas (7680 x 2160 upright) near the middle; CH03 / CH04 (4512 x 2512) at the ends; CH05 / CH06 (2560 x 1920) between; colour by day, greyscale IR in low light | `rig_cameras\cameras.json` |
| transient things in the footage | people, the drone's shadow, cones (09-30, 10-02), cords on the grass (moved over time), a ChArUco plate lying on the grass (10-02, PTSC_0016 / 0017: a scale reference), tools, rats (small) | - |

## 3. Coordinate frames (the frame of record is fixed - do not redefine it)

- **Paddock frame**: origin pole A0, x along the 40 ft length, y along the 20 ft width, z normal to the GROUND PLANE
  (not to gravity), right-handed; the calibration works in mm, the drone anchor in metres, field labels in inches.
- **Drone COLMAP models -> paddock frame**: `reconstruction\colmap_2026-10-02_all\anchor\anchor.json`, per model key
  ("0" = the 09-30 high pass, "1" = the 10-02 inside flights; `sparse\1_ch04` is model 1 plus CH04 close-up frames
  registered into it and uses anchor "1"): `X_paddock_m = scale * R(rotvec) @ X_model + t`
  (rotvec = Rodrigues vector; COLMAP world coordinates in, metres out).
- **Gravity**: up in the paddock frame = normalize(0.0146, 0.0346, 1) (from the drone gimbal; per-video spread
  0.0141-0.0153 / 0.0334-0.0362).
- **Unity** (left-handed, Y up, metres): `unity = (x, z, y) / 1000` from paddock mm (swapping y and z is the
  handedness change). For a gravity-true Unity Y, first rotate paddock vectors so the gravity-up vector above becomes
  +z (a ~2.1 deg tilt). State in the report which of the two you used.

## 4. What is in this folder

| path | what | notes |
|---|---|---|
| `drone_original\DCIM\` | the drone's SD card, untouched (Potensic Atom 2): MP4 4K 3840 x 2160, 29.97 fps, H.264; SRT telemetry per video (altitude in whole metres, GPS, exposure; NO gimbal angles); JPG photos 3840 x 2160 with XMP (`drone-Potensic:` GimbalPitch / Yaw / Roll, Flight attitude, RelativeAltitude to the cm, GPS; focal 4.73 mm = 24 mm equivalent) | 39 files, 16.7 GB; file times = local capture times (EDT) |
| ... 2026-09-30, ~17:00 | PTSC_0001 (high pass over the paddock, COLMAP model 0), 0002 / 0003 (short), 0004, 0007; photos 0005, 0006, 0008 (near-nadir, pitch -76.65 deg, 14.7 m), 0009, 0010 | cones of the 09-30 layout on the grass |
| ... 2026-10-02, 17:37-17:58 | PTSC_0011-0018, flown INSIDE the paddock at 1-2 m; 0011 / 0015 include passes looking out over the walls; 0016 / 0017 film the ChArUco plate on the grass | 0018 was not finalised on the card ("moov atom not found") - use `drone_original\recovered\PTSC_0018_recovered.mp4` |
| ... 2026-10-03, 16:45-16:58 | PTSC_0019 (short), 0020, 0021_0001 (4.1 GB): OUTSIDE the paddock at different heights and angles, gimbal level - the exterior, the walls from outside, the surroundings | not yet reconstructed |
| `reconstruction\colmap_2026-10-02_all\` | the existing COLMAP 4.2.1 reconstruction: `images\` (1080p frames extracted at 1 fps: `d0930\`, `d1002\`, `d1002_ch04\`), `sparse\0` (09-30, 120 frames), `sparse\1` (10-02, 647 of 661 frames, 300k points, 1.02 px), `sparse\1_ch04`, `sparse\2` (a small split-off piece); `anchor\` (anchor.json, ANCHOR_REPORT.txt, anchored point clouds .ply); `SFM_REPORT.txt`; `walltop_profile.json`, `board_scale.json`, `lens_tri.json` (rig camera lenses triangulated in the drone frames), `cam_frames.json`, `board_frames.json`, `landmark_gui_*` (the operator's landmark clicks in drone frames), `paddock_3d_anchored.html` (interactive view) | the feature databases (3.4 GB) were left out - regenerate if needed. Camera: OPENCV, f ~ 1475 px at 1920 wide (66 deg across), k1 ~ 0.075 |
| `geometry\` | survey (poles, houses, ground tilt), terrain (2 ft grid of ground height above the best ground plane, mm), drone-measured cord lines, the operator's drone landmark labels, the house check (house positions per camera), the rig camera centres from tape and drone | small JSON / text |
| `rig_cameras\` | `cameras.json` + per camera `<CAM>_rays.npz` / `<CAM>_rays_f32.raw`: every 16th pixel's unit ray in the paddock frame and the optical centre (from the frozen calibration), plus each grid pixel's point on the local ground; `release\` holds the calibration itself (`camera_fit.npz`, `ray_correction.json`, `frame_correction.json`, `terrain_2026-10-02.json`) and its statement `CALIBRATION_FINAL_2026-10-04.md` | model-agnostic: a renderer reproduces a real camera's view by casting these rays (bilinear between grid points) from the centre |
| `pictures\` | `drone_stills_2026-09-30\` (the 5 originals), `house_measurements_2026-10-03\` (dimensions drawn on the photos), `survey\` (pole spacing sketch), `rig_camera_reference_2026-09-30_colour\` (one colour frame per rig camera, sunny, cones on the grass), `rig_camera_reference_2026-09-18_IR\` (the calibration day, greyscale IR), `rig_camera_reference_2026-09-17_1130_IR\` (an ordinary recording day with rats), `context\` (terrain map, anchored drone check, the primary-camera map) | rig frames are UPRIGHT (the panos rotated 90 deg CCW from storage); their burned-in OSD clock is ~59 min behind local time |

## 5. Accuracy facts you inherit (do not re-derive; challenge only with a reason)

1. Drone model 1 is locally accurate to the millimetre: the ChArUco plate (printed 720 x 540 mm corner pattern)
   triangulated from 23 model frames fits to 1.6 mm rms.
2. Its global scale has a recorded tension: the plate says the anchor scale is 1.2 % too large (`board_scale.json`
   k_board 0.9878); the operator's pole tape (rows A / C 480.25 / 480.0 in at ~1 m height) supports the anchor's
   design-grid scale, which the calibration adopted (the plate's scale may be local). Report your scale against both
   (Section 7) rather than choosing silently.
3. The anchor frame itself is defined to a few cm (landmark choice moves it 9-12 cm; the two drone models disagree on
   cord positions by 34 mm median after a similarity). The rig calibration's camera centres agree with the drone's
   anchored lens positions within 6 cm horizontally and 1-2 cm in height.
4. The calibration ground (z = 0) is the plate surface on the grass, i.e. about grass-top level; the soil is 6-9 cm
   lower at the houses. Shelter heights in the survey are from the soil.
5. Only rigid objects are exact references: the ChArUco plate and the shelters. Cones, cords and long tape runs are not
   (operator); cords were moved between dates.
6. The rig calibration is FROZEN (release 2026-10-03 revision g): use it, never refit it. Its own error is ~2 cm median
   / 5-6 cm p90 per 1 m cell on the ground (`rig_cameras\release\CALIBRATION_FINAL_2026-10-04.md`).

## 6. A suggested route (yours to change - say why in the report)

1. **Inherit the frame**: rebuild or extend the reconstruction with more and better frames (4K, 2-3 fps, sharpness-
   filtered; the 10-03 exterior passes and the 09-30 high pass for the walls' outside and the overall shape), then
   move the new model into the paddock frame by a similarity fitted on the existing model's registered camera centres
   (same frame names) - the frame of record comes with them. Watch for the 180-deg ambiguity: the paddock looks alike
   turned around (four alike walls, a regular pole grid); strict matching (min 40 inliers) was needed before.
2. **Geometry**: dense MVS (COLMAP / OpenMVS / RealityCapture / Metashape) -> a metric mesh for collision and
   occlusion; thin structures (net, wires, cords) will not reconstruct - model them procedurally from the measured
   geometry (net on the frame between the pole tops).
3. **Appearance**: 3D Gaussian Splatting (Unity: e.g. aras-p/UnityGaussianSplatting) and / or a textured mesh with PBR
   materials; grass as terrain texture + grass cards / shader, calibrated against the colour reference frames.
4. **Clean** the transients (people, drone shadow, cones, cords, the plate) from textures / splats.
5. **Lighting**: sun direction from the GPS and the capture times (EDT); a sky / HDRI from frames looking out.
6. **Cameras in Unity**: put the six rig cameras at their centres; reproduce each view exactly by casting the
   `rig_cameras` rays (a render-texture remap or a ray-cast shader), not with a Unity pinhole camera (the panos are
   stitched dual-lens images and all lenses are distorted).

## 7. Validation (report every number; these are the acceptance tests)

- **V1 scale / shape (rigid objects)**: the ChArUco pattern 720 x 540 mm if reconstructed (within 0.5 %); each shelter
  body 62.55 x 45.72 cm, ridge length 66 cm, ridge height ~88 cm above the soil (within 1-2 cm); pole spans at ~1.05 m
  height against the survey (within 2-3 cm, poles lean); wall-top height profile against `walltop_profile.json`.
- **V2 frame**: pole feet / tops and the wall lines against the drone landmark positions in `anchor\ANCHOR_REPORT.txt`;
  the six lens positions against `rig_cameras\cameras.json` (within 5-6 cm); the shelters against the house check.
- **V3 views**: render every rig camera through its rays and overlay on its reference frame (`pictures\
  rig_camera_reference_2026-09-30_colour\`; IR sets for night-like appearance): wall-top edges, pole edges, shelter
  edges - median / max offset in pixels per camera, with the overlay images. The calibration's own error (~2 cm
  median, 5-6 cm p90 on the ground) is roughly 5-15 px at the typical 3-6 m ranges of these lenses; offsets of that size
  are consistent with it; larger, systematic offsets mean the reconstruction and the calibration disagree - report
  where, do not "fix" the calibration.
- **V4 realism**: side-by-side render vs reference frame per camera (colour and IR look), and a statement of what is
  photogrammetric and what is procedural.

## 8. Output and what not to do

- Write everything to `Q:\hc997\SocialFieldRat2026\render\astra_output\` (new folder): the Unity assets (or a Unity
  project / package), the transforms used (paddock -> model -> Unity, as matrices), the validation report
  (`REPORT.md`, numbers first, then methods), and the overlay images. Leave every other file in this folder untouched.
- Do not redefine the paddock frame, re-anchor the drone model to a different reference, or edit the calibration
  files; do not use cones / cords as exact references; do not quote the COLMAP reprojection error as accuracy.
- Stop when the deliverable and V1-V4 are reported; list open issues instead of chasing them.

## 9. Provenance

The calibration project lives in the GitHub repo `amymarple/Field_2026_Social_Recording` (`calibration_qc\`: the
lab notebook `README.md`, `RELEASE_2026-10-03.md`, `CALIBRATION_FINAL_2026-10-04.md`, `REPRODUCE.md`; the drone tools
`drone_sfm.py`, `drone_landmark_anchor.py`, `drone_board_scale.py`, `drone_walltop.py`, `drone_terrain.py`; the camera
export `export_rig_cameras.py`). Raw calibration data and every intermediate run are also backed up at
`Q:\hc997\SocialFieldRat2026\3rd_rat\calibration\`.
