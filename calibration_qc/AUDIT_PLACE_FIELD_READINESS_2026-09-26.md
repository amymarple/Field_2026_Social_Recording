# Can every camera's position be put on one paddock map? Place-field readiness audit, 2026-09-26

Question from the operator: can the position a rat has in each camera be restored to one 2-D paddock map
accurately enough for place cells, without the rat jumping from one point to another when it passes from
one camera to the next? Everything below is about the release fit (`camera_fit.npz`, sha256 `6e4b54e9...`,
reproduced on the lab PC 2026-09-26 with the same mapping to within 0.1 mm) and its ground correction.

## Verdict

* **Typical accuracy is 3-9 cm per camera (median), the tail 7-22 cm (p90), the worst labels 15-36 cm.** Two cameras
  looking at the same new point disagree by 8 cm (median) and 14 cm (p90); that disagreement is the jump
  a track takes at a handoff. Whole-paddock 5 cm is not supported; 10 cm is supported over most of the
  paddock and not at the +x end, the corners, or in CH01's far field.
* **Place-field readiness has not been assessed on the release.** The only downstream analysis
  (`DOWNSTREAM_VALIDATION.txt`) was computed on an earlier fit and measures something narrower than
  its title (section 1). Revision 2 of the report already withdrew its acceptance claim; nothing replaced it.
* **The calibration numbers leave out four error sources that matter as much at handoffs**: the height
  of the tracked point, the ground between labels, the time offset between camera streams, and the tape
  lattice itself (section 3). Two of them (height, timing) are fixable in the tracking pipeline and one
  (timing) has never been measured.
* **The mapping of the small cameras depends on which boards were used, and CH01's on the choice of
  model** (section 2.2). Both are what the planned cone supplement (`CALIB_CONE_SHEET_2026-09-26.html`)
  addresses: more labelled ground points where the cameras overlap.

## 1. What was validated before

`downstream_validation.py` (commit `cd8550b`, output `DOWNSTREAM_VALIDATION.txt`, 2026-09-24 13:19):

| Issue | Evidence |
|---|---|
| Stale | Written 13:19 against the fit of that hour; the release fit was written 14:50 with a different pano warp (degree 3, not 4) and a different accepted view set. Pair counts in the file (CH01-CH04 481, CH01-CH02 230) do not match the release (`AUDIT_CALIBRATION_2026-09-24_UPDATE.md`, finding 1). |
| Measures warp sensitivity only | The ensemble varies the ground warp (degree, ridge, constraint types, bootstrap of label points) on ONE bundle. Bundle, lens, board and label uncertainty are absent, and a bias shared by all members is invisible (UPDATE finding 2). |
| Place-cell test cannot fail | 300 Gaussian cells with sigma 100-250 mm, median spatial information 7.8 bits/spike, classified at SI > 0.5; no null, weak or near-threshold cells, not the classifier that will be used. |
| Handoffs not in the tracks | Board disagreement is reported separately; simulated positions never jump between cameras. |
| No height, no timing | Positions are ground points; every camera sees them at the same instant. |
| Synthetic occupancy | Uniform / wall-following / shelter mixture; no real tracks existed. |

Its occupancy and place-field numbers therefore say how much the analysis moves between ground-warp
variants, not how far the map is from the paddock. They should not be quoted as place-field validation.

## 2. The accuracy that can be stated today

### 2.1 Against the lattice, held out (`CV_LANDMARKS.txt`: each cord / wall side / cone group predicted by a warp that never saw it)

| camera | labels | median | p90 | max | training rms of the warp |
|---|---|---|---|---|---|
| CH01 (pano) | 166 | 91 mm | 216 mm | 358 mm | 94 mm |
| CH02 (pano) | 146 | 61 mm | 152 mm | 284 mm | 71 mm |
| CH03 | 33 | 48 mm | 102 mm | 279 mm | 61 mm |
| CH04 | 32 | 74 mm | 99 mm | 203 mm | 51 mm |
| CH05 | 25 | 33 mm | 66 mm | 147 mm | 23 mm |
| CH06 | 22 | 48 mm | 94 mm | 259 mm | 53 mm |
| all | 424 | 65 mm | 185 mm | 358 mm | |

CH01 does not fit its own labels better than 9 cm rms: its cones, cords and wall foot cannot all be met
by one smooth warp. That is label position error (tape, displaced cones), ground height at the labels
(CH01 slides 0.88 mm per mm of height), and the stitched pano canvas, in unknown shares.

### 2.2 Stability of the whole pipeline (`fold_stability.py` -> `qc\cv\FOLD_STABILITY.txt`)

The five placement folds are complete recalibrations from 80 % of the boards. With the release's warp
settings, the displacement of a point at rat height between the release and the worst fold:

| camera | median | p90 | max | where it is worst |
|---|---|---|---|---|
| CH01 | 3 mm | 8 mm | 21 mm | short-wall ends (p90 14 mm) |
| CH02 | 1 mm | 3 mm | 7 mm | |
| CH03 | 53 mm | 96 mm | 203 mm | corners (107 / 170 mm), long-wall edge (84 / 117 mm) |
| CH04 | 16 mm | 24 mm | 49 mm | corners (26 / 42 mm) |
| CH05 | 23 mm | 37 mm | 79 mm | long-wall edge (75 / 78 mm) |
| CH06 | 7 mm | 12 mm | 17 mm | |

The panos are pinned by their ~130 labels whatever boards the bundle had. The four small cameras
have 6-9 cones each and an affine warp, so their mapping follows the bundle, i.e. the boards; CH03
moves up to 20 cm when a fifth of them is removed.

Model choice is a larger effect for the panos: the release bundle with a degree-4 instead of degree-3
pano warp (the placement folds chose 3 in four folds and 4 in one; both are legitimate) moves CH01 by
49 mm median, 107 mm p90, 192 mm max, and CH02 by 24 / 46 / 118 mm. Between its labels, CH01's
map is not determined better than that.

### 2.3 Between cameras (the handoff jump)

| statistic | value | kind |
|---|---|---|
| per placement, 26 placements seen by 2+ cameras | median 76 mm, p90 137 mm, max 256 mm | held out (`CV_FOLDS.txt`) |
| per shared corner, release | median 71 mm, p90 153 mm, max 248 mm | training (`PADDOCK_AGREEMENT.txt`) |
| worst pair | CH01-CH04, median 108 mm, p90 227 mm, systematic (-59, -58) mm | training |
| worst places | T75 225 mm, T74 154 mm, T54 138 mm, F23 117 mm | training |

38 of the 64 placements were seen by one camera and cannot be scored. 47 % of the paddock is mapped by
exactly one camera and 1.2 % (the four corners) by none (`cone_supplement.py`, at rat height): in the
single-camera half there is no cross-check at all, only the held-out labels of 2.1.

## 3. Error sources the numbers above do not contain

1. **Height of the tracked point.** A pixel is a ray. The oblique cameras slide 0.86-1.03 mm per mm of
   height error, the shelter cameras 0.09-0.10. A back tracked at 60 mm but mapped at 0 lands 5-6 cm off,
   and two cameras on opposite sides land on opposite sides: up to ~11 cm of pure handoff jump. Fix in
   the tracking: one consistently defined keypoint, mapped at its height (`to_paddock(uv, z_mm=...)`).
2. **Ground between labels.** The warp is right at every labelled cone whatever the local height, and
   interpolates between them. A 5 cm bump between labels is up to ~4.5 cm per oblique camera.
3. **Time offset between cameras.** `rtsp_record.ps1` stamps frames with the PC's arrival time
   (`-use_wallclock_as_timestamps 1`). Encoder, NVR and (for the Duo 3) stitching latency differ per
   stream and have never been measured. At 0.5 m/s every 100 ms of offset is 5 cm of handoff jump.
   Measurable from the LED sync pulser where two cameras see it, or from the tracks themselves (the
   lag that best aligns two cameras' simultaneous tracks of the same rat).
4. **The lattice.** The frame is the operator's cords and cones at design inches; no independent survey
   exists. The wall foot (straight middles are training data) lands within 3 in of the design; taped
   camera positions agree to 10 in (indicative only).
5. **Not checked:** day vs IR (the IR-cut filter switch is assumed not to move the image); cameras
   standing where they stood on 2026-09-18 for footage of earlier cohorts (`PRE_TEARDOWN_CAPTURE_CHECKLIST.md`
   section C); tracking-keypoint noise.

## 4. Why this is hard

* **Two of the six cameras are stitched panoramas.** The Duo 3 writes a 7680 x 2160 canvas from two
  lenses; its projection is proprietary and is not a pinhole, not a homography and not the nominal
  180 x 50.6 deg equirectangular (the fitted canvas is about 190 x 47 deg). No smooth lens model tried
  removes the inconsistency in the canvas corners, which are the two ends of the paddock. What
  remains is an empirical ground warp, right only where it was labelled.
* **Grazing views.** Lenses at 2.3-2.4 m over a 12 x 6 m field: the far field is seen 10-15 deg below
  the horizon, where a board square is ~20 px, a pixel covers ~7 mm of ground, and an angle error of
  0.1 deg moves the ground point by ~8 cm (10 m away, 2.35 m up).
* **The ground is not a plane.** Plates on grass tilt (24 of 64 at the 6 deg bound), and every
  oblique camera converts height into horizontal position at ~0.9.
* **Few shared observations.** 26 of 64 placements were seen by two cameras; CH02-CH03 rests on one
  board. The relative position of two cameras is only as good as what both saw.
* **Unobservable scale.** Neither the hand-held sweeps nor plates on the ground fix focal length; the
  taped lens heights were needed for CH04 and the panos.
* **No independent truth.** The same tape lattice defines the frame and checks it; nothing was surveyed
  with an instrument.

## 5. What this means for 10 cm place fields

* A 3-9 cm typical error is under one bin; the p90 of CH01 is two bins. Broad fields (tens of cm) keep
  their location to within a few cm; a field in CH01's far field, in a corner, or at the +x end can move
  by 1-2 bins.
* The damage concentrates at handoffs. An uncorrected 10 cm jump in one frame reads as a 2.5 m/s run at
  25 fps, and a field straddling a handoff line can be smeared or split between the two cameras'
  versions of it.
* Until validated: map at the keypoint's height; in overlaps, combine the cameras (weighted by the
  per-camera accuracy of 2.1) instead of switching between them; keep the NaN outside each camera's
  support; flag samples from CH01's far field, the corners and the +x end; and rerun any key result
  under the alternative calibrations that exist already (the degree-4 variant and the five fold fits).

## 6. What would validate it

1. **Cone supplement** (`CALIB_CONE_SHEET_2026-09-26.html`): 52 cones where the cameras overlap, the
   ground correction refitted with them, then `cv_landmarks.py`, `fold_stability.py` and the handoff
   numbers again. Aimed at exactly the weak points above: CH01 between its labels, CH03-CH06 with 6-9
   cones, the +x end and the corners.
2. **Real tracks, when they exist**: every frame where two cameras see the same rat gives the handoff
   error directly, at rat height, over every overlap, thousands of times; the lag that best aligns the
   two tracks gives the time offset per camera pair. This is the test that matches the question.
3. **A downstream analysis that can fail**, replacing `downstream_validation.py`: tracks mapped through
   the per-camera error field of 2.1 (spatially correlated, not white), the handoff rule, height and
   timing errors; a cell population with null, weak and near-threshold cells; the classifier and
   shuffle procedure that will actually be used; 10 / 15 / 20 cm bins; false-positive and false-negative
   place-cell rates and field splitting at handoff lines as outcomes.

## Reproduce

```
cd calibration_qc
python cv_landmarks.py                  # 2.1   (held-out label groups)
python fold_stability.py                # 2.2   (and --as-saved for the fold corrections as written)
python paddock_agreement.py             # 2.3   (training disagreement, height sensitivity)
python cone_supplement.py               # coverage by 0 / 1 / 2+ cameras, the cone plan
```
The degree-4 comparison of 2.2: `frame_correction.fit_warps(pm.FIT, ridge=8, deg_pano=4)` applied to
`pm.load(correct=False)`, compared with `pm.load()` on the same grid.
