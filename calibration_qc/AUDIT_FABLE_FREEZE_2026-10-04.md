# Can the paddock calibration be frozen? Which version, how its error is defined, and what the error is

Auditor: Claude (Fable 5.1), 2026-10-04, read-only. Judged from results only: the brief's numbers and the result
files listed at the end (REFIT_RAYS / SWEEP_* reports, handoff, camera-error and single-camera maps for rev f and
rev g, the place-cell and physical-limit audits, RELEASE_2026-10-03.md, REPRODUCE.md). No code, raw video or raw
label data was opened; no computation beyond arithmetic on copied numbers (`tmp_freeze\arithmetic.txt`, cited as
"arith N"). mm, median / p90 unless stated. "rev f" = release 2026-10-03 rev f (`refit_rays\G_design_cordfolds`);
"rev g" = rev f + the 2026-09-18 hand-held sweep boards at weight 0.5 (`refit_rays\S05_all`). Cells are the 40 in
(1.02 m) cells of the handoff / camera-error maps, 72 in all.

## Executive summary

1. **Freeze: YES, rev g (sweep weight 0.5)**, after three desk items of hours: back up `F:\calibration\qc`, reproduce rev g
   bit for bit and commit it as rev f was, run `house_check` on rev g (gate: houses agree across cameras within ~6 cm).
2. Rev g = rev f on every held-out ground check within noise (plates 25/55 vs 28/54, cones 40/70 vs 41/72, ball 36/79
   vs 38/84, own error 18/55 vs 19/58), 3x better above ground where tested (8-9/17-27 vs 22-24/55-59); no lever is left.
3. **Final error: the primary camera's own 2-D error in the camera frame at the keypoint height, per 1 m cell - median
   18 mm, p90 55 mm over the 49 measured cells (ball, 105 mm); 23 cells (32 %) unmeasured, smooth, taken as <= 10 cm;
   handoff step per boundary 20-61 / 31-95 mm end-to-end (the calibration's own share ~1 cm); CH04|CH06 unmeasured.**
   The user adds the keypoint-height term (0.45-3 mm per mm of height error) and the per-day drift (5-25 mm/night).

## Q1. Freeze? Which version? What blocks? Which levers remain?

### Verdict

Freeze rev g (w 0.5) as the final `ray_correction.json`, with rev f kept as the documented fallback (`load()` of the
previous sha). Freeze means: no more fitting of any kind; validation data may still be appended to the error
statement without touching the model.

### Evidence: the sweep-weight scan (every other setting identical; all checks held out unless marked "fit")

| check | rev f (w 0) | w 0.25 | **rev g (w 0.5)** | w 1.0 |
|---|---|---|---|---|
| plates held out by station, two cameras on one corner, z 6 mm | 28 / 54 | 26 / 50 | **25 / 55** | 24 / 58 |
| held-out plate shape, rms about the printed pattern | 10.1 / 25.3 | 10.2 / 25.4 | 9.8 / 25.7 | 9.3 / 25.8 |
| 09-30 cones, 5-fold, two cameras on one unseen cone | 41 / 72 | 42 / 71 | **40 / 70** | 43 / 69 |
| 20 Hz ball at 105 mm, all pairs | 38 / 84 | 36 / 81 | **36 / 79** | 35 / 79 |
| ball CH01-CH02 / CH01-CH03 / CH02-CH04 (medians) | 52 / 41 / 58 | 52 / 39 / 52 | 52 / 37 / 43 | 50 / 36 / 36 |
| sweep plates held out, odd / even 10-s blocks (own triangulated z) | 22 / 55, 24 / 59 | not read (not in the file list) | **8 / 17, 9 / 27** | 6 / 14, 8 / 21 |
| sweep 2-D jump in the z 0-200 mm band, CH03-01 / 03-02 / 04-01 / 04-02 | 15 / 7 / 19 / 13 | - | 7 / 10 / 7 / 6 (fit) | - |
| sweep px offset, pose of the end camera projected into the pano | 12.6 / 29.4 px | - | 8.8 / 20.7 px (fit) | - |
| west wall top, spread CH01 / 02 / 03 per 24 in (fit) | 18 / max 48 | 19 / 48 | 21 / 50 | 24 / 53 |
| camera heights minus drone lens heights, six cameras (arith 5) | -23..-6, mean -12 | -11..+4, mean -1 | +7..+21, mean +17 | +29..+46, mean +40 |
| CH01-CH02 baseline (drone 69.7 in, tape 69.2, sigma 24 mm) (arith 4) | 68.6 (1.2 sigma) | 67.0 (2.9) | 66.3 (3.6) | 67.1 (2.8) |
| primary camera's own error, 49 cells | 19 / 58, max 187 | - | **18 / 55, max 188** | - |
| single-camera plate stretch as primary, CH01 / 02 / 03 / 04 / 05 / 06, median % | 3.6 / 2.9 / 1.9 / 1.1 / 2.6 / 0.9 | - | 4.2 / 3.1 / 1.8 / 1.4 / 2.4 / 1.1 | - |

Handoff steps on the ball (same instant, two cameras, median / p90, n), rev f -> rev g: CH01|CH02 58 / 92 -> 61 / 82
(n 370); CH01|CH03 47 / 63 -> 43 / 58 (246); CH01|CH04 45 / 83 -> 54 / 83 (108); CH01|CH05 25 / 42 -> 20 / 39 (210);
CH01|CH06 28 / 46 -> 26 / 48 (259); CH02|CH03 34 / 97 -> 31 / 95 (458); CH02|CH04 43 / 65 -> 35 / 50 (76);
CH02|CH05 25 / 47 -> 22 / 46 (305); CH02|CH06 26 / 32 -> 23 / 31 (32); CH04|CH06 not measured in either. Equal-weight
mean of the nine medians 36.8 -> 35.0, n-weighted 37.6 -> 36.0 (arith 6): a draw on the ball, as expected - six of
the nine boundaries sit at 20-35 mm, i.e. at the ball check's own floor of 26-44 mm (PHYSLIMIT 1.2), where the ball
cannot resolve a calibration change at all (arith 12).

How to read the scan:

* **On the ground the four fits are the same model.** Plates, cones and ball move by 1-4 mm, under the noise of
  those checks (plates: ~31 stations; cones: n 62; ball: floor 26-44). Nothing on the ground argues for or against
  the sweep.
* **Above the ground rev g is a different, better model where the sweep looks** - the CH03 / CH04 overlaps with the
  panos at the two ends, 0.14-0.54 m up. Rev f's 22-24 / 55-59 is a true extrapolation figure (no sweep in its fit);
  rev g's 8-9 / 17-27 is interpolation between 10-s blocks of a continuous walk, so it flatters, but the same blocks
  score rev f at 22-24: the 3x gain is real for that region. The z 0-200 band (where a rat keypoint lives) improves
  from 7-19 to 6-10 per pair. The apparent-size ratio of the end camera's pose seen from the pano goes from
  0.88-1.03 to 0.96-1.00: rev f carried a ~9 % scale inconsistency between CH04 and CH01 above the ground that is now
  gone.
* **The price is in the camera centres and heights, and it is a bookkeeping price, not a tracking price.** With the
  sweep, CH04's centre moves 10 in (25 cm) in y from rev f, the CH01-CH02 baseline closes to 66.3 in against the
  drone's 69.7 and the tape's 69.2 (3.6 sigma of the fit's own prior), and all heights rise 2.5-3 cm (rev f 1-2 cm
  below the drone's lens heights, rev g 1-2 cm above; weight 0.25 lands on them, weight 1.0 is 4 cm above). A
  centre error dC that the ray polynomial compensates on the ground reappears at height z as dC x z / H: 25 cm at a
  rat's 6-15 cm is 7-17 mm, at 0.5 m it is 58 mm (arith 2); a 3 cm height error compensated on the ground is 3 mm at
  10 cm, 15 mm at 0.5 m (arith 3). That is exactly why the ground checks are blind to the change and the sweep is not,
  and it is also the size of rev f's sweep disagreement (29-39 mm for the CH04 pairs): the budget closes. Which
  revision has the physically right CH04 the drone can arbitrate at the desk (its anchored lens positions are good to
  ~10 cm); the fit used only distances and heights from it, and a y-move of a camera whose baselines all run along
  x changes no distance by more than ~1 cm. Either way the 2-D map at rat height is unaffected to better than 2 cm.
* **Weight choice.** 0.25 and 0.5 cannot be separated by anything on the ground; 0.5 is the one whose held-out
  sweep, handoff, error and single-camera maps exist, and its heights are within the prior's 40 mm. 1.0 is the first
  weight at which a ground check worsens beyond noise (plates p90 54 -> 58, wall-top spread 48 -> 53) and the
  heights leave the drone by 4 cm: the sweep begins to override the ground. Take 0.5 and stop; the lever is flat.
* Minor debits of rev g, for the record: CH01's local plate stretch as primary 3.6 -> 4.2 % (n 12 plates; one plate
  at (250, 183 in) reads +13 % in both revisions), the CH01|CH02 median 58 -> 61 (its p90 improves 92 -> 82), the
  CH01|CH04 median 45 -> 54 (p90 unchanged; this boundary carries the CH04 clock confound of 30-60 mm in y, so the
  ball cannot say which revision is better there - the sweep says rev g).

### What blocks the freeze (none of these is a reason to delay more than a day)

1. **Backup.** `F:\calibration\qc` (19 GB: corner caches, the operator's labels, the drone reconstruction and
   anchor, ball tracks, every run) has no backup (REPRODUCE.md). A frozen calibration whose inputs exist on one
   disk is not frozen. Copy it to the lab server next to the videos before declaring the freeze.
2. **Reproducibility of rev g.** Rev f reproduces bit for bit from the committed code. Rev g adds inputs (the sweep
   corner caches, their clocks, `--sweep` flags) that REPRODUCE.md does not list yet; run the same trace, list the
   files, verify bit for bit, then replace `ray_correction.json` and append a "Revision g" section to the release
   note with the table above and the centre / height tension written down.
3. **House check on rev g** (desk, minutes). The houses are the only rigid above-ground validation outside the
   sweep's region (HOUSE_1: CH01 / CH02 / CH05; HOUSE_2: CH01 / CH02 / CH06, at 60-88 cm). Rev f: per-camera house
   positions agree to 36-39 mm. If rev g stays within ~6 cm, freeze rev g; if it does not, the sweep bought the ends
   at the price of the middle and rev f is the freeze. This is the one gate.
4. Not blockers: the 23 unmeasured cells and the CH04|CH06 boundary (they are gaps in the error statement, not in the
   model), the drone-frame questions (absolute frame, see Q2), the tracking-side conditions of the place-cell audit
   (blending, keypoint height, features in the same map).

### Remaining levers, with expected gain and cost

Fitting levers: **none.** Degree 3-5, priors 0.03-0.10, seam bands 0-10 deg (PHYSLIMIT) and now sweep weights
0-1.0 all lie within the noise of every ground check. Drone cords were tested and not adopted. No new label type on
the ground can change a two-camera agreement that is already at the checks' floors.

Field, before teardown (the rats are in the paddock; everything here is minutes, and all of it changes the error
statement, not the fit):

| # | measurement | expected gain | cost | do it? |
|---|---|---|---|---|
| F1 | A 2-min ball pass along x ~ 400 in, y 40-200 (the CH04|CH06 boundary) and a +y / -y pass through CH04's view | the only unmeasured primary boundary (6 cells) gets a number; separates the CH04 clock from geometry at CH01|CH04 (54 / 83); expectation 25-45 mm (two pinholes 30 in apart, B/(H-z) 0.35, so the height term is small; bound from the CH01 pairs 60 / 96 in quadrature, arith 7) | 2 min field, 1 h desk with the existing ball tools | yes |
| F2 | Rigid plates against the long walls: 6-8 placements per wall with the plate's long edge on the wall foot, x taped from the nearest pole base (< 1.5 m, a short rigid run) | the first ABSOLUTE own-error measurement of CH01 (y 200-240) and CH02 (y 0-40) in the 15 wall-strip cells - the rows where border / boundary-vector analyses live - without the drone, whose own frame is only good to 3-10 cm; converts "<= 10 cm, shape-verified" into a figure, likely 2-5 cm | 20-30 min field, 1-2 h desk (existing detectors, operator timeline) | yes if a person may enter the paddock for 30 min; otherwise accept the 10 cm class |
| F3 | Sync-LED visibility in all six cameras (frame check) | not a calibration item, but the only thing on the field list that cannot be recovered later | minutes | yes (place-cell audit) |
| - | More cones, cords, long tapes, a new drone flight for the calibration, still-ball spots, mowing | nothing the checks can see | - | no |

Desk, now or after teardown:

| # | item | gain | cost |
|---|---|---|---|
| D1 | `house_check` on rev g | the gate above | minutes |
| D2 | Compare rev f's and rev g's camera centres with the drone's anchored lens positions; write the answer into the release note | closes the 25 cm CH04 / 8.6 cm CH01-CH02 question as provenance (which revision is physically placed; both map the ground alike) | 1 h |
| D3 | Look at the two outlier plates in the single-camera check: -46 % at (260, 27 in) in the CH02 wall strip (its neighbour 15 in away reads -4 %; a smooth degree-4 map cannot do both, so this is almost surely a detection or pose failure) and +13 % at (250, 183) under CH01. Render the frames before deciding (detect-then-decode); if they are detection failures, drop them from the single-camera figures (CH02 p90 10.7 % -> ~7 %) | an honest single-camera table for the strips | 30 min |
| D4 | Once tracking runs: the step of real rat tracks at every primary boundary crossing, the step at the wall-strip edges, and the keypoint height by two-camera triangulation of real rats in overlap cells (place-cell audit A2) | the end-to-end handoff and height numbers for the paper, from the animals themselves; needs no paddock | 1-2 days, tracking-side |

## Q2. How the final error should be defined

### The error classes, separated

| class | what it is for one-primary-camera tracking | how it was measured | rev g number | role in the report |
|---|---|---|---|---|
| **A. Within-camera (the primary's own map error)** | how far the primary camera's mapped position is from where every other camera would put the same point, as a fixed function of place, at the stated height | three-cornered hat on the 20 Hz ball per cell (3+ cameras, 21 cells) or the bound d / sqrt 2 (2 cameras, 28 cells); 49 of 72 cells | 18 / 55 over cells, max 188 (a bound) | **THE reported error (map + two numbers)** |
| A'. Within-camera shape and local scale | smoothness of the map inside one camera: field shape, distances within a camera | held-out rigid plates mapped by the primary alone | shape 7-18 mm rms per camera; local scale 1-4 % median (p90 2.5-11 %) | context; the only evidence in the 23 unmeasured cells |
| **B. Between-camera handoff** | the step a track takes where the primary changes | same-instant two-camera difference on the ball at 105 mm, per boundary (end-to-end: includes clock, centroid and ball-height noise) | 20-61 / 31-95 per boundary; CH04|CH06 none | **THE second reported number (per boundary)** |
| B'. Calibration-only share of a handoff | the geometric part of B | rigid sweep plate at its own triangulated height, held out in 10-s blocks (CH03 / CH04 vs the panos only) | 8-9 / 17-27 (per pair 6-13 / 15-53) | context: shows B is dominated by the check and the height term, not by the rays |
| C. Absolute frame | where the camera frame sits on the physical paddock (walls, poles, houses, UWB) | rigid references not in the fit: houses across cameras ~4 cm at 60-88 cm; drone cord Y39 0-4 cm, Y201 +6..+15 cm (unexplained); drone frame itself 3-10 cm; scale from the pole tape | 3-4 cm where rigid references exist; unverified beyond ~5-15 cm in the interior | context; matters only for feature-relative analyses done in design coordinates and for the UWB tie |
| D. Keypoint height assumption | g x d / (H - z) away from the camera for a height error g | geometry; the keypoint and its z are the tracking pipeline's choice | 0.45 mm/mm at 1 m from the camera, 1.0 at 2.4 m, 2-3 at the far rows; g 25 mm -> 11-75 mm (arith 8) | **the user adds it**; not a calibration number |
| E. Temporal drift | camera motion night to night | PHYSLIMIT: 5-25 mm per night per camera; corrected per day in the analysis repo | residual to be reported there | the user adds it |
| F. Check noise | the ball's clock, centroid, 09-30 -> 09-18 transform, its own height spread | PHYSLIMIT 1.2: 26-44 mm floor | - | must never be quoted as calibration error, in either direction |

### What should be THE calibration error

Report **A and B together, as a map and two lines**, both at the stated keypoint height above the local ground:

1. **Primary-camera own error, per 1 m cell, in the camera frame: median 18 mm, p90 55 mm over the 49 measured
   cells (21 estimates, 28 two-camera bounds), max 188 mm (a bound in one cell); 23 cells unmeasured.** This is the
   number a place-cell or social analysis cares about: it is the fixed displacement of a rat's position inside the
   map that tracking actually uses. It is measured on a 10 cm ball at 105 mm with the ball's own clock / centroid /
   height-spread noise partitioned into it, so it is conservative for the rays and realistic for an object whose
   height scatters by +-3 cm - which is what a rat is. Its floor is the hat's own resolution: many cells read exactly
   10 mm (CH03's west end, CH05, CH04's near cells); read those as "<= 10-15, at the limit of the check".
2. **Handoff step at each primary boundary: median / p90 of the same-instant two-camera difference, per boundary**,
   20-61 / 31-95 on the ball; quote the per-boundary table, not one number, and name the unmeasured boundary.

Statistic: per-sample errors -> per-cell median -> paddock median and p90 over cells with equal weight (not per
sample: the ball visited some cells 300 times and others 25). Max is reported as a bound, separately. For handoffs:
median / p90 over same-instant pairs per boundary with n. Height: the ball numbers refer to a point 105 mm above the
local ground as surveyed by the drone (rev e terrain), whose datum is the grass top / plate surface, 67-90 mm above
the soil at the houses; the plates refer to 6 mm; the sweep to 0.14-0.54 m. A rat keypoint at 50-100 mm is inside
that range; the calibration's own share changes little with z, the height term (D) is added on top.

Context numbers that support the headline and should be quoted with it: plates held out 25 / 55 (pair, rigid,
same session; per camera ~18 / 39, arith 1 - the clean geometric figure, agreeing with the hat's median); cones
40 / 70 (pair, different session, hand-laid); ball all pairs 36 / 79; sweep 8-9 / 17-27 (pair, rigid, above ground,
ends only); shape 7-18 mm and local scale 1-4 % per camera; houses ~4 cm across cameras at 0.6-0.9 m.

Numbers that must not be quoted as accuracy: any fit residual (label residuals 0.2-2.3 in, boards in the fit 12 / 24,
sweep corners in the fit 3-8 mm, wall tops in the fit, west-wall spread, the cost); the sweep 8 / 17 as "the handoff
error" (own triangulated height, interpolation, four pairs); the ball figures as the calibration's error without
the 26-44 mm floor, or as the rat's error (no posture term); the "e 10" cells as 10 mm measurements; the "<= 188"
cell as a 19 cm error (a two-camera bound in a cell the handoff map lists as having no ball at its 25-detection
threshold: unmeasured, not 19 cm); the 09-24 figure 76 / 137 (stale bundle CV); the 10-02b numbers; any single
whole-paddock number without the map and the height it refers to.

## Q3. The final numbers (rev g; rev f in brackets where different)

| quantity | value | status | height | what the user must add |
|---|---|---|---|---|
| **Primary camera's own error, per cell** | **18 / 55 mm, max 188 (bound)** over 49 cells [19 / 58, max 187] | measured in 21 cells (3+ cameras), bounded in 28 (2 cameras); floor ~10 mm | 105 mm above the local ground | keypoint height term (D), per-day drift (E) |
| ... west end (CH03 primary, x 0-80) | 10-23 mm in 10 of 12 cells; <= 55 at (0-40, 0-40), <= 18 at (40-80, 0-40) | measured | 105 | same |
| ... CH05 / CH04 / CH06 cells | CH05 10-18; CH04 10-50 (<= 47, <= 66 bounds at the corners); CH06 13-24 (<= 188 one cell, see Q2) | measured / bounds | 105 | same |
| ... pano interior (CH01 / CH02 primary, two-camera cells) | bounds <= 11..<= 80; the seam band x 200-280: <= 47 (CH01), <= 55-56 (CH02); the worst measured cell (80-120, 0-40): <= 80 (pair 117) | bounds | 105 | same |
| **Unmeasured cells: 23 (32 % of the floor)** | CH01 strip y 200-240, x 80-400 (8 cells, 99-139 ball detections each, one camera); CH02 strip y 0-40, x 120-400 (7 cells, 28-158 detections); (160-200, 160-200), (200-280, 160-200), (240-280, 40-80), (280-320, 40-80), (360-400, 40-80), (440-480, 40-80), (440-480, 0-40) | **not measured**; evidence: smooth map (shape 12-18 mm rms, local scale 3-4 % for CH01 / CH02 as primary, one suspect plate at (260, 27)), wall-foot and wall-top constraints along the strips' outer edge, continuity from the neighbouring measured cells (20-60 mm) | - | treat as <= 10 cm; F2 would measure 15 of them |
| **Handoff step, per boundary (ball)** | CH01\|CH02 61 / 82 (n 370); CH01\|CH03 43 / 58 (246); CH01\|CH04 54 / 83 (108); CH01\|CH05 20 / 39 (210); CH01\|CH06 26 / 48 (259); CH02\|CH03 31 / 95 (458); CH02\|CH04 35 / 50 (76); CH02\|CH05 22 / 46 (305); CH02\|CH06 23 / 31 (32) | measured, end-to-end (includes the check's 26-44 mm floor; six boundaries sit at that floor) | 105 | the keypoint height term enters a handoff as g x B/(H-z) = 0.35-1.6 g (PHYSLIMIT 1.1): a 25 mm posture scatter adds 9-40 mm per step |
| ... CH04\|CH06 (6 cells, x ~ 400, y 40-200) | **not measured** | expectation 25-45; bound 60 / 96 by quadrature of the CH01 pairs (arith 7) | - | F1 measures it in 2 min |
| Calibration-only share of a handoff (rigid plate, own z) | CH03-01 6-10 / 18-19; CH03-02 9 / 15-16; CH04-01 11-13 / 29-53; CH04-02 7 / 16-19 (held out odd / even) [22-24 / 55-59] | measured, interpolation, ends only | 0.14-0.54 m (z 0-200 band: 4-13) | - |
| Within-camera shape / local scale (held-out plates, primary only) | shape CH01 18, CH02 12, CH03 7, CH04 8, CH05 7, CH06 7 mm rms; scale 4.2 / 3.1 / 1.8 / 1.4 / 2.4 / 1.1 % median, p90 8.5 / 10.7 / 6.3 / 2.5 / 3.8 / 3.8 % (n 12 / 10 / 12 / 11 / 5 / 9) | measured | 6 mm | a 4 % local scale is 3-4 cm over 0.8-1 m (arith 10); field areas +-2-8 % |
| Absolute frame (camera frame vs the physical paddock) | scale: pole tape (design 480 in, matched to 0.05 %); walls: in the fit by construction (wall tops vs drone -30..+16 where checked); houses: ~4 cm across cameras at 0.6-0.9 m; drone cords: Y39 0-4 cm, Y201 +6..+15 cm; drone frame 3-10 cm | partly measured, inconsistent | ground / 0.6-0.9 m | locate walls, houses and objects in the same camera map; fit the UWB transform on simultaneous data |
| Above the ground | ends, 0.14-0.54 m: the sweep figures above; middle, 0.6-0.9 m: houses ~4 cm (rev f; rev g to be run, D1); elsewhere above 0.3 m: nothing | partly measured | - | nothing above ~0.5 m is claimable outside those places |
| Keypoint height term | horizontal error = g x d/(H-z): 0.45 at 1 m, 1.0 at 2.4 m, 2-3 at the far rows; a fixed wrong z of 50 mm = 2-15 cm radial bias | geometry | - | choose z per keypoint, never 0; measure the keypoint's height from footage |
| Temporal drift | 5-25 mm per night per camera (PHYSLIMIT) | measured in the analysis repo | - | per-day rigid-landmark correction; report its residual |

Honest one-sentence statement for a rat keypoint at 5-10 cm, in the camera frame, on the 09-18 geometry, in the
68 % of the floor with a measurement: **about 2 cm median and 5-6 cm at the 90th percentile per cell, with a
2-6 cm step where the primary camera changes, before the height and drift terms the tracking pipeline adds; in the
two wall strips and six interior cells the map is smooth to 1-2 cm and 1-4 % but its absolute error is not measured
and is taken as up to 10 cm.**

## Q4. Methods paragraph, and what not to claim

**Methods (camera-to-paddock mapping).** Six cameras 2.2-2.3 m above a 12.2 x 6.1 m grass paddock (two dual-lens
stitched panoramas near the centre, four single-lens cameras at the ends) were calibrated from two field sessions
(2026-09-18/19) with a rigid 800 x 600 mm ChArUco plate (64 placements, 125 views) and refined with ground labels
(cones, cords, wall feet), operator-traced wall tops, a drone survey (camera positions, wall tops, ground relief), 406
hand-held plate poses 0.14-0.54 m above the ground, and the taped pole grid for scale. Each camera's rays carry a
degree-4 angular correction and a centre offset fitted to these data; a pixel is mapped to the paddock frame by
intersecting its ray with a plane at an assumed keypoint height above the locally surveyed ground. Positions are
taken from one primary camera per 1 x 1 m floor cell (the camera with the finest ground resolution); the other
cameras serve for consistency checks and for blending at the boundaries. Accuracy was assessed on data not used in
the fit: plates held out by station (two cameras on the same corner, 25 mm median, 55 mm 90th percentile), 62 cones
from a later session (40 / 70 mm), a 10 cm ball tracked at 20 Hz in all cameras (36 / 79 mm between camera pairs at
105 mm height, including timing and centroid noise), and the hand-held plates held out in alternate 10-s blocks
(8-9 / 17-27 mm between the end cameras and the panoramas). From the ball, the primary camera's own error per cell
(three-cornered hat, or a two-camera bound) is 18 mm median and 55 mm 90th percentile over the 49 cells with
multi-camera coverage; the remaining 23 cells - the 1 m strips along the long walls and six interior cells - are
seen by one camera only, where held-out plates show the map to be smooth (shape 7-18 mm rms, local scale 1-4 %) but
an absolute error could not be measured, and we treat them as accurate to 10 cm. Where the primary camera changes,
a trajectory steps by 20-61 mm median (31-95 mm 90th percentile, per boundary) on the ball; tracks are blended across
boundaries so that no step enters speed or phase analyses. These figures refer to a keypoint at the stated height;
an error g in the assumed height displaces the mapped position by g x d / (H - z) away from the camera (0.45-3 mm per
mm across the paddock), and day-to-day camera motion (5-25 mm per night) is corrected per day from rigid landmarks and
reported separately.

**Do not claim**

* "5 cm over the whole paddock", "centimetre" or "millimetre" accuracy. Claim 2 cm median / 5-6 cm p90 per cell
  where measured, 10 cm class in the 23 unmeasured cells, with the map.
* An error for the two wall strips, the six interior cells or the CH04|CH06 boundary (none is measured).
* The fit residuals (12 / 24 boards, 3-8 mm sweep corners, 0.2-2 in labels, the wall-top agreement) as accuracy.
* The sweep's 8 / 17 as the handoff error of the system: it is at the plate's own triangulated height, interpolated,
  and exists for four camera pairs at the ends only.
* The ball figures as the pure calibration error (they include a 26-44 mm check floor) or as the rat's error (they
  exclude the posture term and the tracker's own jitter).
* Absolute (design-frame) accuracy better than ~5 cm, or wall / house / object distances computed in design
  coordinates to the calibration's error; locate the feature in the same camera map instead.
* Accuracy above ~0.5 m except at the ends (sweep, <= 0.54 m) and at the houses (~4 cm at 0.6-0.9 m); nothing is
  claimable for climbing or standing on walls and roofs elsewhere.
* Accuracy on any day other than 2026-09-18 without the per-day correction and its residual.
* That the fitted camera centres and heights are the physical ones: they are effective model parameters (the
  CH01-CH02 baseline sits 8.6 cm short of two independent measurements; CH04's centre differs by 25 cm between
  revisions f and g while both map the ground alike).
* The 09-24 figure 76 / 137, the 10-02b figures, or any number from a revision other than the frozen one.

## Do not do

* Do not fit anything further: no weight, degree, prior, seam-band or label-type change; no drone-cord refit; no
  re-anchoring of the frame; no re-labelling of ball centres. The checks are at their floors and the scan is flat.
* Do not replace `ray_correction.json` before the house check on rev g, the bit-for-bit reproduction and the backup
  of `F:\calibration\qc`.
* Do not drop rev f: keep it loadable by sha and named in the release note as the fallback and as the reference the
  other audits (SOTA, PHYSLIMIT, place-cell) were written against.
* Do not add cones, cords or long tapes, fly the drone again for the calibration, mow, or spend field time on
  anything but F1-F3.
* Do not quote one number for the calibration; quote the map, the per-boundary table and the height.
* Do not map at z = 0 or with a different z per camera; do not switch cameras hard; do not measure wall / house
  distances in design coordinates (the place-cell audit's rules stand).
* Do not let the "e 10" cells or the "<= 188" cell into a summary as measurements.

## One-table summary of the final numbers (rev g, w 0.5)

| | median | p90 | max / bound | coverage | height | measured on |
|---|---|---|---|---|---|---|
| **Primary camera's own error, per cell (THE error)** | **18 mm** | **55 mm** | 188 (bound) | 49 / 72 cells (68 %) | 105 mm above local ground | ball, three-cornered hat / 2-camera bound |
| Unmeasured cells | - | - | taken as <= 100 mm | 23 / 72 (32 %): wall strips 15, interior 8 | - | shape 12-18 mm, scale 3-4 % from held-out plates |
| **Handoff step, per boundary (THE second number)** | 20-61 mm | 31-95 mm | - | 9 of 10 boundaries | 105 mm | ball, same instant (includes 26-44 mm check floor) |
| Handoff CH04\|CH06 | not measured | - | <= 60 / 96 (quadrature) | 6 cells | - | F1 (2 min) |
| Calibration-only handoff share (context) | 8-9 mm | 17-27 mm | - | CH03 / CH04 vs panos, ends | 0.14-0.54 m, own z | rigid sweep plate, held-out blocks |
| Plates held out, two cameras (context) | 25 mm (~18 per camera) | 55 mm (~39) | - | ~31 stations | 6 mm | rigid plate, by station |
| Cones held out (context) | 40 mm | 70 mm | - | n 62 pairs | 50 mm (above local ground) | 09-30 cones, 5-fold |
| Ball, all pairs (context) | 36 mm | 79 mm | - | n 6325 | 105 mm | 20 Hz ball |
| Within-camera local scale | 1-4 % | 2.5-11 % | - | per camera | 6 mm | held-out plates, primary only |
| Absolute frame | 3-4 cm where rigid references exist | - | unverified beyond ~5-15 cm in the interior | houses, Y39; Y201 +6..+15 | 0-0.9 m | not in the fit |
| Height term (user adds) | 0.45-3 mm per mm of height error | - | - | by region | - | geometry |
| Drift (user adds) | 5-25 mm per night per camera | - | - | per camera | - | analysis repo, corrected per day |

## Files read

`F:\calibration\qc\refit_rays\{S05_all, G_design_cordfolds, S_all, S025_all}\REFIT_RAYS.txt`;
`S05_all\SWEEP_ALL.txt`; `sweep_check_release_revf_v3.txt`; `S05_hold_odd\SWEEP_HELDOUT.txt`,
`S05_hold_even\SWEEP_HELDOUT.txt`, `S_hold_odd\SWEEP_HELDOUT_odd*.txt`, `S_hold_even\SWEEP_HELDOUT_even*.txt`;
`F:\calibration\qc\handoff\S05_all\{HANDOFF_MAP.txt, handoff_map.json, handoff_map.png}`;
`F:\calibration\qc\camera_error\S05_all\{CAMERA_ERROR_MAP.txt, camera_error_map.png}`;
`F:\calibration\qc\single_camera_check\S05_all\{SINGLE_CAMERA_CHECK.txt, single_camera_check.png}`;
`G:\Field_2026_Social_Recording\calibration_qc\{HANDOFF_MAP_2026-10-03.txt, CAMERA_ERROR_MAP_2026-10-03.txt,
SINGLE_CAMERA_CHECK_2026-10-04.txt, AUDIT_FABLE_PLACECELL_PRECISION_2026-10-04.md, RELEASE_2026-10-03.md, REPRODUCE.md}`;
`F:\calibration\qc\audit\AUDIT_FABLE_PHYSLIMIT_2026-10-03.md`. Not read (not in the list): the S025 held-out sweep
files, any HOUSE_CHECK for rev g. Arithmetic: `F:\calibration\qc\audit\tmp_freeze\arithmetic.txt`.
