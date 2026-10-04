# Paddock camera calibration - FINAL, frozen 2026-10-04 (release 2026-10-03, revision g)

**Status: frozen** (operator, 2026-10-04). No further fitting of any kind. Validation data may still be added to the error
statement below without touching the model. Cohort 3 is the last cohort and the paddock is demolished afterwards; this
is the calibration of record for every camera of the 2026 social recording.

## What it is and how to use it

`paddock_map.load()` returns, per camera, a `RayCamera`: the 2026-09-24 bundle (`camera_fit.npz`, sha256 6e4b54e9...)
with the ray-space correction `ray_correction.json` (revision g, sha256 37615ee2...; degree-4 angular polynomial per
camera, pano lens halves blended over 3 deg at the stitch seam, a centre offset per camera) and the ground relief
`terrain_2026-10-02.json`. `cams["CH01"].to_paddock((u, v), z_mm=Z)` maps an UPRIGHT pixel to the paddock floor plan
(mm; `units="in"` for inches; origin pole A0, x along the 40 ft length, y along the 20 ft width) at **Z mm above the
local ground**. It works from this repository alone (numpy / scipy / cv2).

Revision f, the release of 2026-10-03 that every earlier audit refers to, stays loadable:
`load(rays="ray_correction_2026-10-03f.json")`. The 10-02b ground warp: `load(rays=None)`.

Rules for the tracking that the error statement below assumes (place-cell audit, `AUDIT_FABLE_PLACECELL_PRECISION_2026-10-04.md`):
1. Map each keypoint at its real height above the ground, never at z = 0. A height error g moves the point by
   g x d / (H - z) away from the camera: 0.45 mm per mm at 1 m from the camera, 1.0 at 2.4 m, 2-3 at the far rows.
2. One primary camera per region (`camera_error_map.json`), and blend the two cameras across a boundary instead of
   switching hard (a hard switch is a 2-6 cm step: speed spikes and phase steps).
3. Measure distances to walls, houses and objects in the same camera map (locate the feature in that camera), not
   from the design drawing.
4. Apply the per-day camera correction from rigid landmarks (analysis repo) before comparing days.

## How it was fitted

From two field sessions (2026-09-18/19) with a rigid 800 x 600 mm ChArUco plate (64 placements, 125 views, plus the
operator's clicks of the views the detector missed), ground labels (09-18 lattice and 09-30 supplement cones, the cross
cords, the wall feet), the operator's wall-top traces, a drone survey on 2026-10-02 (camera lens positions -> camera
distances and heights, wall-top heights, ground relief), 406 hand-held plate poses 0.14-0.54 m above the ground
(2026-09-18 sweep, seen at one moment by CH03 / CH04 and a panorama), and the operator's pole tape for scale.
`refit_rays.py`, the exact command and inputs in `REPRODUCE.md`; reproduced bit for bit on 2026-10-04.

Revision g = revision f + the hand-held sweep boards at weight 0.5 (`--sweep sweep_instances_2026-09-18_v3.json
--sweep-w 0.5`). The weight was chosen by a scan (0 / 0.25 / 0.5 / 1.0): flat on every ground check, 0.5 keeps most of
the above-ground gain, 1.0 is the first weight at which a ground check worsens and the camera heights leave the
drone's. Gates passed before the freeze (Fable freeze audit, `AUDIT_FABLE_FREEZE_2026-10-04.md`): the houses agree
across cameras at 60-88 cm height to 35 / 30 mm (revision f 39 / 38); revision g reproduces bit for bit; the
calibration data are backed up (below). Revision g also puts every camera within 6 cm (horizontal) and 1-2 cm
(height) of the drone's independently anchored lens positions; revision f had CH04 20 cm, CH06 16 cm, CH03 / CH05
10-12 cm off - the sweep moved the cameras towards where they physically are.

## The final error

Defined for one-primary-camera tracking into the 2-D floor plan, at the keypoint height above the local ground,
measured only on data not used in the fit. Two numbers and a map (`CAMERA_ERROR_MAP_2026-10-04.txt`,
`HANDOFF_MAP_2026-10-04.txt`; pictures under `F:\calibration\qc\camera_error\S05_all\`, `\handoff\S05_all\`):

| | median | p90 | max / bound | coverage | measured on |
|---|---|---|---|---|---|
| **Primary camera's own error, per 1 m cell (THE error)** | **18 mm** | **55 mm** | 188 (a bound) | 49 of 72 cells (68 %) | 20 Hz ball at 105 mm: three-cornered hat (21 cells) or two-camera bound (28) |
| Cells with no comparison | - | - | taken as <= 100 mm | 23 cells: the 1 m strips along both long walls (15), 8 interior / corner cells | only one camera sees the ball there; held-out plates show the map smooth (shape 7-18 mm, local scale 1-4 %) |
| **Step where the primary camera changes (per boundary)** | 20-61 mm | 31-95 mm | - | all 9 boundaries with an overlap; CH04\|CH06 has none (behind HOUSE_2 only CH06 sees the floor - operator, 2026-10-04): not measurable, those cells are CH06-only | ball, same instant (includes the check's own 26-44 mm floor) |

Per boundary (median / p90 mm, n): CH01|CH02 61 / 82 (370); CH01|CH03 43 / 58 (246); CH01|CH04 54 / 83 (108);
CH01|CH05 20 / 39 (210); CH01|CH06 26 / 48 (259); CH02|CH03 31 / 95 (458); CH02|CH04 35 / 50 (76); CH02|CH05 22 / 46
(305); CH02|CH06 23 / 31 (32).

In one sentence: for a rat keypoint at 5-10 cm, on the 68 % of the floor with a measurement, **about 2 cm median and
5-6 cm at the 90th percentile per cell, with a 2-6 cm step where the primary camera changes**, before the height and
drift terms the tracking adds; in the two wall strips and six interior cells the map is smooth to 1-2 cm and 1-4 % but
its absolute error is not measured and is taken as up to 10 cm.

Context (all held out; quote with the headline, never instead of it):

| check | revision f | **revision g** |
|---|---|---|
| plates held out by station, two cameras on one corner (z 6 mm) | 28 / 54 | **25 / 55** (~18 / 39 per camera) |
| 09-30 cones, 5-fold, two cameras on one unseen cone | 41 / 72 | **40 / 70** |
| 20 Hz ball at 105 mm, all camera pairs | 38 / 84 | **36 / 79** |
| hand-held plates, held-out 10-s blocks, two cameras at the plate's own height (0.14-0.54 m) | 22-24 / 55-59 | **8-9 / 17-27** |
| same, z 0-200 mm band, per pair | 7-19 | **6-10** |
| houses at 60-88 cm, per-camera house position spread | 39 / 38 | **35 / 30** |
| within one camera: plate shape rms / local scale, as primary (views with >= 40 corners) | 6-17 mm / 0.8-3.6 % | 6-18 mm / 1.0-4.2 % |

Error classes the tracking adds or must keep apart: the keypoint-height term (above); day-to-day camera drift (5-25 mm
per night per camera, corrected per day in the analysis repo); the absolute frame (where the camera frame sits on the
physical paddock: 3-4 cm where rigid references exist - houses, cord Y39 - and unverified beyond ~5-15 cm elsewhere;
cord Y201 disagrees with the drone by 6-15 cm, unexplained; the X cords moved between labelling and the drone flight).

Not accuracy, never quote as such: any fit residual (plates in the fit 12 / 24, sweep corners 3-8 mm, label residuals,
the wall-top agreement); the sweep's 8 / 17 as "the handoff error"; the ball figures as the pure calibration error or
as the rat's error; the "10 mm" floor cells as measurements; the 188 mm bound as an error; the 09-24 figure 76 / 137
or any 10-02b number; one whole-paddock number without the map and the height.

## Optional before teardown (minutes; they add to the error statement, not to the model)

1. (The freeze audit's ball pass over the CH04|CH06 boundary is not possible: the two cameras do not overlap there -
   behind HOUSE_2 only CH06 sees the floor (operator). Those cells stay CH06-only and unmeasured.) A +y / -y ball pass
   through CH04's view would still separate CH04's clock from its geometry at CH01|CH04.
2. If someone may enter for ~30 min: 6-8 plates per long wall, the plate's long edge on the wall foot, x taped from the
   nearest pole base - the only absolute measurement possible in the two wall strips.
3. Check that the sync LED is visible in all six cameras (not calibration, but unrecoverable later).
Do not add cones, cords, long tapes or another drone flight for the calibration.

## Methods paragraph (from the freeze audit, house check added)

Six cameras 2.2-2.3 m above a 12.2 x 6.1 m grass paddock (two dual-lens stitched panoramas near the centre, four
single-lens cameras at the ends) were calibrated from two field sessions with a rigid 800 x 600 mm ChArUco plate (64
placements, 125 views) and refined with ground labels (cones, cords, wall feet), operator-traced wall tops, a drone
survey (camera positions, wall tops, ground relief), 406 hand-held plate poses 0.14-0.54 m above the ground, and the
taped pole grid for scale. Each camera's rays carry a degree-4 angular correction and a centre offset fitted to these
data; a pixel is mapped to the paddock frame by intersecting its ray with a plane at an assumed keypoint height above
the locally surveyed ground. Positions are taken from one primary camera per 1 x 1 m floor cell (the camera with the
finest ground resolution); the other cameras serve for consistency checks and for blending at the boundaries.
Accuracy was assessed on data not used in the fit: plates held out by station (two cameras on the same corner, 25 mm
median, 55 mm 90th percentile), 62 cones from a later session (40 / 70 mm), a 10 cm ball tracked at 20 Hz in all
cameras (36 / 79 mm between camera pairs at 105 mm height, including timing and centroid noise), the hand-held plates
held out in alternate 10-s blocks (8-9 / 17-27 mm between the end cameras and the panoramas), and the two shelters as
rigid objects (each camera's estimate of a shelter's position within 30-35 mm of the others at 60-88 cm height). From
the ball, the primary camera's own error per cell (three-cornered hat, or a two-camera bound) is 18 mm median and 55 mm
90th percentile over the 49 cells with multi-camera coverage; the remaining 23 cells - the 1 m strips along the long
walls and eight interior or corner cells - are seen by one camera only, where held-out plates show the map to be smooth
(shape 7-18 mm rms, local scale 1-4 %) but an absolute error could not be measured, and we treat them as accurate to
10 cm. Where the primary camera changes, a trajectory steps by 20-61 mm median (31-95 mm 90th percentile, per
boundary) on the ball; tracks are blended across boundaries so that no step enters speed or phase analyses. These
figures refer to a keypoint at the stated height; an error g in the assumed height displaces the mapped position by
g x d / (H - z) away from the camera (0.45-3 mm per mm across the paddock), and day-to-day camera motion (5-25 mm per
night) is corrected per day from rigid landmarks and reported separately.

## Do not claim

"5 cm over the whole paddock", centimetre or millimetre accuracy; an error for the wall strips, the interior
one-camera cells or the CH04|CH06 boundary; fit residuals as accuracy; the sweep's 8 / 17 as the system's handoff
error; design-frame accuracy better than ~5 cm, or wall / house / object distances in design coordinates; accuracy above
~0.5 m except at the sweep's ends and the houses; accuracy on another day without the per-day correction; that the
fitted camera centres and heights are physical measurements (they are effective parameters, although revision g's
agree with the drone's to 6 cm).

## Provenance and backups

- Release lineage: `RELEASE_2026-10-02.md` (10-02b), `RELEASE_2026-10-03.md` (revisions a-g), `README.md` (the dated
  lab notebook). Audits: `AUDIT_FABLE_SOTA_2026-10-03.md`, `F:\calibration\qc\audit\AUDIT_FABLE_PHYSLIMIT_2026-10-03.md`,
  `AUDIT_FABLE_PLACECELL_PRECISION_2026-10-04.md`, `AUDIT_FABLE_FREEZE_2026-10-04.md`.
- Reports of the final revision: `REFIT_RAYS_2026-10-04_revg.txt`, `SWEEP_HELDOUT_2026-10-04.txt`,
  `HANDOFF_MAP_2026-10-04.txt`, `CAMERA_ERROR_MAP_2026-10-04.txt`, `SINGLE_CAMERA_CHECK_2026-10-04_revg.txt`
  (revision f: `_revf.txt`), `HOUSE_CHECK_2026-10-04_revg.txt`.
- Reproduction: `REPRODUCE.md` (commands, the exact input files, environment; both revisions reproduced bit for bit).
- Backups on the lab server, `Q:\hc997\SocialFieldRat2026\3rd_rat\calibration\`, 2026-10-04, file counts and bytes
  checked equal to the source: the four calibration sessions' videos, the drone footage (`drone_ATOM_001`,
  `drone_recovered`), house photos, survey, and `qc\` (labels, corner caches, drone reconstruction, every run).
