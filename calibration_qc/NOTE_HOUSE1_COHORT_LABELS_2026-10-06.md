# house_check.py on the cohort-period house_1 labels — answers (2026-10-06)

From the analysis repo (`Field2026_Social_analysis`, cv_field landmark tracking). Two questions were asked.

## 1. Can `house_check.py` take the CH01 / CH02 `20260904_120002` house_1 labels?

The fit itself works for these labels, but `house_check.py` cannot read them as is. Check these points first:

**a. Do not convert them with `Corrections("2026c").to_09_18`.** That table holds NIGHT samples only (CH01/CH02 hourly
21:00 → 04:20). At 09-04 12:00:02 it silently returns the 09-04 21:00 sample, with flag `ok` on CH02. That lookup was
compared with a proper noon correction at the house_1 label points:

| Camera | Night-table lookup vs noon correction at the house_1 label points |
|---|---|
| CH01 | median 3.0 px, max 3.5 px |
| CH02 | median **30.1** px, max 31.8 px |

CH02 moved between noon and 21:00. Use the noon transforms below instead. They were tracked directly from the 09-18
references (`landmark_track.py --tag ch0102_0904noon`, run `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0102_0904noon_20261006_1540\track_frames.csv`).

The convention is A = 09-18 px → 09-04 12:00 px, in full-resolution upright pixels. Labels go back with inv(A):

| Camera | A (a11 a12 a13 / a21 a22 a23) | Status, held-out median / p90 |
|---|---|---|
| CH01 | 0.99955 0.00030 11.52866 / −0.00109 1.00017 5.94528 | ok, 1.27 / 3.63 px |
| CH02 | 1.00090 0.00246 12.44847 / −0.00103 1.00184 0.18110 | ok, 1.74 / 5.65 px |

These are image affines fitted on poles, boxes and wall tops; they are not 3-D poses. Expect ~1–2 px at the landmarks,
possibly more near the frame edges. house_1 lies at x ≈ 1860–2510 px in CH01 and x ≈ 5970–6680 px in CH02.

**b. Inputs and frames.** `pieces()` only globs `landmarks_<cam>_20260918_*.json`, so the converted pieces need a new
input path. After inv(A) they are 09-18 **IR** reference pixels (CH01 13:57:30, CH02 15:22:30). The cohort frames are IR
as well (HSV saturation 0.0), so `IR2COL` applies exactly as it does for the 09-18 labels.

Per frame there are 7 edge pieces and 1 label:
- CH01: ROOF_X 2 pieces, ROOF_Y 2, BASE_Z 3, and HOUSE_1_LABEL.
- CH02: the same counts.

There are no BASE_X / BASE_Y pieces (grass). `cls()` ignores the X / Y in the names, so the naming needs no fix.

**c. Free parameters.** The fit has 4 free parameters for all cameras together: centre x, y (in), θ (±15° around the
start) and the soil offset dz (−50 … +200 mm). Per-camera fits free x, y, θ with dz fixed.

The start grid is DESIGN_XY ± 12 / ± 9 in. The cohort position should lie inside it. In CH05 the roof label moved by
about (+91, −223) px between 09-04 and 09-18, which is roughly 15–20 cm at CH05's ~1.4 m to the roof — an order of
magnitude only.

**d. Soil offset.** The 09-18 joint fits gave HOUSE_1 +58 mm and HOUSE_2 +93 mm. dz therefore depends on where the
house stands (soil under the house plus the calibration's ground warp), and the 09-18 value does not carry over to the
cohort spot.

Only two cameras are usable: CH01 and CH02, mid-field, about 40° apart in viewing direction. CH05 cannot be converted to
09-18 px, for two reasons:
- CH05 hangs from the crossbeam on top of pole B1, so B1 moves with the camera.
- house_1 and the nails on its roof moved on 09-18.

So dz and the centre trade along the two viewing rays. Fit dz free, and report the centre with dz fixed at +58 and at
+93 mm as a sensitivity.

**e. The roof is the lid.** The house roofs are lifted at every battery round and catch (33 events in cohort 3,
`Field2026_Social_analysis/cv/configs/cohort3_lid_events.json`). The 09-04 12:00 frames come after the 09-04 AM round
(08:11–08:26). The rigid model ties the roof edges (ridge, eaves, rakes) to the body. A lid replaced a few cm off would
bias the centre. Only BASE_Z (vertical body corners) is lid-independent, and that is 3 pieces per camera here.

Compare a roof-only fit with a BASE_Z-only fit. If they disagree by more than the 09-18 per-camera spread (30 mm), the
lid offset matters.

**f. LABEL.** `house_check.py` does not use `HOUSE_n_LABEL`: the survey has no position for the number plate on the
roof. It could enter only as an extra point constraint. That needs its in-house coordinates first, for example from the
09-18 rays intersected with the fitted roof plane, validated on HOUSE_2 (never moved). The plate sits on the lid, so (e)
applies to it too. Leave it out of the first fit.

## 2. Has the cohort-period house_1 position (audit A4) been computed?

**No.** No centre, ridge direction or ray residual exists yet on our side.

It is planned as the route to tie CH05 to the calibration. CH05's own view has no rigid structure that stayed put
across 09-18: house_1 moved, the roof nails moved with it, and the B1 pole moves with the camera. The plan has two steps:
1. Fit house_1's cohort pose from CH01 + CH02 as in 1.
2. Fit CH05's cohort pose from its own 09-04 house_1 labels (`landmarks_CH05_20260904_120002.json` / `_030100.json`)
   against that pose.

If you run step 1 with the noon transforms above, we will use your numbers. Otherwise we will do it and report the same
quantities as `HOUSE_CHECK_*.txt`: centre, ridge angle, dz, per-camera ray residual median / p90, and per-camera centres.
