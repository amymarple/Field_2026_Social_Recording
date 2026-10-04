# Is the paddock calibration accurate enough for rat place-cell analyses? Audit of release 2026-10-03 rev f

Auditor: Claude (Fable 5.1), 2026-10-04, read-only. Judged from RESULTS only: the brief's numbers, `CAMERA_ERROR_MAP.txt`
(+ png), `SINGLE_CAMERA_CHECK.txt` (+ png), `DRONE_LINE_CHECK.txt`, `HANDOFF_MAP_2026-10-03.txt`, and
`AUDIT_FABLE_PHYSLIMIT_2026-10-03.md` for context. No code, raw video or raw label data was opened. Literature: 16 web
searches plus direct reads of five sources; every citation below carries its verification status ("verified" = I read the
number in the paper or its PMC text; "unverified" = recalled or from a secondary summary). The derived numbers (height
multipliers, speed artefacts, phase smear, bin-flip rates, timing) are plain arithmetic in
`tmp_placecell\placecell_budget.py` -> `placecell_budget.out`; "(budget N)" points at its section.

All errors in mm unless stated; "median / p90".

## Executive summary

1. **Verdict: sufficient for the core place-cell analyses (rate maps at 5-10 cm bins, field size/number/location, spatial
   information, Bayesian decoding, theta sequences, replay, remapping) with three conditions; insufficient as it stands for
   two things: anything measured relative to physical features (walls, houses, objects) in the design frame, and speed
   around primary-camera switches.** The fixed map error (primary camera's own error 19 / 58, pairs 38 / 84) is below the
   ~5 cm intrinsic tracking error the field's reference decoding paper quotes for lab LED tracking (Zhang et al. 1998) and
   below one rate-map bin; it displaces, it does not blur.
2. **Action 1 (analysis, 1-2 days, no field time): never switch cameras hard.** Blend the primary and secondary camera over
   a transition band (or at least hysteresis + a smoother that models the switch). Jumps of 25-60 (p90 32-97) are
   harmless to occupancy but produce 50-280 cm/s speed spikes and 15-70 deg phase steps inside small fields (budget 2, 3).
3. **Action 2 (analysis, a parameter + one desk measurement): map at the tracked keypoint's real height, never z = 0,
   and gate rearing.** The brief's 0.73 mm/mm is a frame-centre value; geometry gives d/(H - z) = 1.0 at 2.4 m from the
   pole and 2-3 at the far pano rows (PHYSLIMIT agrees: 2.4-2.9), so z = 0 for a 7 cm keypoint is a 7-21 cm radial bias and
   posture is the largest stochastic term there (budget 1, 6).
4. **Action 3 (analysis, hours): locate walls, houses and objects in the SAME camera map** (click their ground contact
   in each primary camera's frames, per day) and compute feature distances there. That removes the common-mode frame
   error (+76..+180 at the east end and far edge) from every boundary/object analysis; a drone-cord refit does not help
   place cells beyond that.
5. Before teardown the only place-cell-relevant field items are small: 30-40 min of rigid plates (located by the drone) in
   the two one-camera strips and the two hollows, a 2-min +y/-y ball pass through CH04, and a one-time check that the sync
   LED is visible in all six cameras. Everything else can be done at the desk after teardown.

## Summary table

| analysis | accuracy needed (threshold I used; source) | our relevant number | verdict |
|---|---|---|---|
| Rate maps, 5-10 cm bins | fixed warp <= 1 bin; frame-to-frame / day-to-day blur sd <= bin/2. Lab bins 2-3.5 cm (Pfeiffer & Foster 2013: 2 cm + 4 cm Gaussian, verified; Zhang 1998: 1 cm kernel, verified); megaspace 5.3 x 3.5 m: 12 cm^2 bins = 3.5 cm, fields > 200 cm^2 (Harland et al. 2021, verified) | primary own error 19 / 58 (max 187 bound); pairs 38 / 84; plates 28 / 54 (fixed, per location) | **sufficient** at 5 cm away from seams and hollows, at 10 cm everywhere; conditions: z at keypoint height, no hard switch |
| Place-field size, number, location | error <= 10 % of field width; fields here will be 0.3-2 m (78 % of megaspace fields <= 1 m^2, 22 % 1-4 m^2, 82 % of cells 2-5 subfields; Harland 2021, verified; 0.6-32 m in bats, Eliav 2021, verified) | 19-58 fixed = 2-19 % of a 30 cm field, < 6 % of a 1 m field; local scale 1-4 % median (p90 7-12 %) -> area +-2-8 % | **sufficient**; do not read area differences < 10 % as biology |
| Spatial information (bits/spike) | invariant to a smooth re-labelling of space; sensitive only to blur (Skaggs et al. 1993, unverified in this audit; Harland 2021 SI > 0.5 criterion, verified) | fixed warp: no effect; stochastic 22-88 mm per frame before smoothing (posture x d/(H-z) dominates; budget 6) | **sufficient** within one map; compare SI only across the same map/bins |
| Stability across days, field shift | daily map shift <= 2 cm (half a 3.5-5 cm bin; stable fields shift a median 3.5 cm, 74-83 % <= 7 cm, Ziv et al. 2013, verified, mice) | drift (e) open; PHYSLIMIT quotes panos 5-15 mm most nights, CH03/CH04 10-25 mm | **sufficient with conditions**: per-day rigid-landmark correction applied and its residual reported |
| Phase precession | within-field relative error <= 10 % of field length (<= 36 deg smear; O'Keefe & Recce 1993, Skaggs et al. 1996, verified phenomenon) | smooth warps: < 3 cm across a 60 cm field; a 25-60 mm seam step inside a 30-60 cm field = 15-72 deg (budget 3) | **sufficient away from seams; insufficient within ~20 cm of a seam without blending** |
| Theta sequences, Bayesian decoding | calibration error <= 1/3 of the decoding floor; floor ~5 cm with 25-30 cells in a 1 m maze, equal to the tracking error (Zhang 1998, verified); events span 40-200 cm (Pfeiffer & Foster 2013, verified) | 19-58 fixed, self-consistent between training and test | **sufficient**; decoding here will be limited by cell count and field size, not by the map |
| Replay | decoded in map coordinates against templates built in the same map (Davidson et al. 2009, 10 m track, ~8 m/s, verified) | same as above | **sufficient** |
| Remapping (global / rate / partial) | comparisons within one fixed map; coherent shifts must be < 2 cm | fixed map OK; drift (e) open | **sufficient with the per-day correction**; a coherent shift of all fields in one camera's region is drift, not remapping |
| Fields relative to walls, houses, objects (BVC, border, object-vector) | <= 2-3 cm within 30 cm of the feature (BVC preferred distances biased to short range, width grows with distance, Lever et al. 2009, verified; border cells hug the wall, Solstad et al. 2008, verified; object-vector cells, Hoydal et al. 2019, verified existence) | common-mode frame error: CH01 far edge +76 (to +122), east end +100..+182, CH02 strip -2 (abs 37); shape rms 6-17; local scale 1-4 % | **insufficient in the design frame; sufficient with conditions** if features are located in the same camera map (residual 1-4 cm) |
| Speed filtering, speed modulation | spurious speed <= 2 cm/s after smoothing; thresholds 5-10 cm/s (Pfeiffer & Foster 2013: 5; Harland 2021: 10, stops < 6 cm/s for 0.5 s; verified) | seam steps 25-92 -> 10-37 cm/s after 0.25 s smoothing, 5-18 after 0.5 s (budget 2); rearing at far rows 10-40 cm transients | **insufficient at hard switches; sufficient** with blending/hysteresis, >= 0.25-0.5 s smoothing and posture gating |
| Inter-animal distance (social) | proximity thresholds 10-20 cm | same camera: warps cancel to 1-4 % of the distance; different cameras: <= one jump (3-6 cm) | **sufficient** |

## Q1. What accuracy do rat place-cell analyses need?

**What lab tracking actually delivers.** The reference decoding paper tracked head LEDs at 20 Hz on a 256 x 256 grid over
~111 x 111 cm (0.43 cm/px) and states that the best Bayesian reconstruction errors (~5 cm with 25-30 cells, 1 s windows)
"were comparable with the intrinsic error of the system for tracking the animal's position, which was estimated to be
~5 cm" (Zhang et al. 1998, citing Skaggs et al. 1996 and Wilson & McNaughton 1993; verified). Pfeiffer & Foster (2013)
used two LEDs at 60 Hz in a 2 x 2 m arena, 2 cm bins, a 4 cm Gaussian and a 5 cm/s speed threshold (verified). Harland
et al. (2021) tracked two LEDs with an overhead 25-30 fps camera in a 5.3 x 3.5 m megaspace, binned at 12 cm^2 (~3.5 cm),
thresholded at 10 cm/s and accepted fields > 200 cm^2 (verified). Markerless keypoint trackers reach a few pixels: LEAP
< 3 px after ~500 labelled frames (Pereira et al. 2019, from a search summary), DeepLabCut "comparable to human accuracy"
with ~200 frames (Mathis et al. 2018, verified statement; the pixel figures often quoted, ~3-5 px test / 2.7 px human,
are unverified here). At 2-8 px/cm on this rig (handoff map resolution table) that is 0.5-2.5 cm per frame. So the
field's own tolerance is set by LED systems with 1-5 cm intrinsic error; nobody tracks a rat's head to millimetres,
and head LEDs sit 5-8 cm above the floor with the same parallax error this audit discusses (ignored in the lab because
H/d is large there).

**Rate maps and bins.** Lab bins are 2-3.5 cm with 1-2 bin Gaussian or Hanning smoothing (Zhang 1998; Pfeiffer & Foster
2013; Ziv et al. 2013 used 3.5 cm; Harland 2021 used ~3.5 cm in the megaspace; all verified). Need: the fixed map error
should be <= 1 bin, and the stochastic error (frame-to-frame jitter, posture, day-to-day drift, boundary flicker) should
have sd <= bin/2, otherwise occupancy and spikes land in neighbouring bins (a 2 cm sd flips 32 % of samples out of a 5 cm
bin and 16 % out of a 10 cm bin; budget 4). Smoothing at 1-2 bins makes a sub-bin blur invisible.

**Field size, number, location; large environments.** In classic < 1 m^2 arenas most cells have one field of ~20-30 cm
(Harland 2021: 94 % single-field in a 0.54 m^2 box; verified). In larger spaces fields multiply and enlarge: a 1.8 x 1.4 m
box gives multiple, irregular, enlarged fields (Fenton et al. 2008, verified); a 2.5 m^2 arena multiple fields in CA1, CA3
and DG (Park et al. 2011, verified existence); on a 48 m track a gamma-Poisson generative model of multi-field cells (Rich
et al. 2014, verified); the 5.3 x 3.5 m megaspace gives 2-5 subfields in 82 % of cells, 78 % of fields <= 1 m^2 and 22 %
1-4 m^2, with a subfield area range > 0.6 m^2 in 79 % of multi-field cells (Harland 2021, verified); along the
dorsoventral axis on an 18 m track field size grows from < 1 m to ~10 m (Kjelstrup et al. 2008; track verified, sizes
unverified); bats in a 200 m tunnel show 0.6-32 m fields, up to 20-fold within one neuron (Eliav et al. 2021, verified).
In a 12.2 x 6.1 m paddock (4x the megaspace) expect fields from ~30 cm to several metres and 3-10 per cell. Need: position
error <= 10 % of the smallest field one wants to resolve, i.e. 3-5 cm for 30-50 cm fields; the centroid of a 1 m field is
located to ~1 bin anyway.

**Spatial information and stability across days.** Spatial information (Skaggs et al. 1993; standard, unverified in this
audit) is a function of the rate map and occupancy; a smooth, fixed re-labelling of space changes it only through the
bin-area change (1-4 % local scale here). Stability: in a familiar track, fields that recur across days shift their
centroid by a median 3.5 cm, 74-83 % by <= 7 cm, against a 24 cm field width (Ziv et al. 2013, verified, mice, Ca
imaging). Harland (2021) found fields less stable between megaspace visits than between small-arena visits (verified) -
a large, outdoor, social environment will have real drift of its own. Need: the map's day-to-day shift must be small
against 3.5 cm, i.e. <= 2 cm, or it biases the shift distribution and the population-vector correlation at 3.5-5 cm bins.

**Phase precession, theta sequences, decoding.** Phase precession maps position within the field onto 360 deg of theta
(O'Keefe & Recce 1993; Skaggs et al. 1996; verified), so a position error e smears phase by 360 e/L: 5 cm in a 30 cm
field is 60 deg, in a 1 m field 18 deg (budget 3). Theta sequences sweep ahead of the animal over tens of centimetres
(Wikenheiser & Redish 2015, verified existence; distances unverified) and awake trajectory events decoded at 20 ms span
40-200 cm (Pfeiffer & Foster 2013, verified). Bayesian decoding error floors at ~5 cm with 25-30 cells in a 1 m maze and
is set by cell count, window and field size (Zhang 1998, verified: error falls roughly as cells^-1/2, 1 s windows best,
large errors during immobility, best alignment with a time shift of ~ -66 ms, i.e. within ~100 ms). Need: the map error
should be a fraction (<= 1/3) of the decoding floor and continuous over the extent of a sequence (no step inside the
40-200 cm an event covers).

**Replay and remapping.** Replay is decoded against templates built from the same position stream (Davidson et al.
2009, verified existence; bins unverified); remapping compares rate maps across conditions. Both are invariant to a fixed
warp and sensitive only to time-varying error.

**Fields relative to physical features.** BVCs prefer short distances (bias to the near range, tuning width growing
with distance; Lever et al. 2009, verified), border cells fire along the wall itself (Solstad et al. 2008, verified),
object-vector cells at a given distance and direction from an object (Hoydal et al. 2019, verified existence, ranges
unverified); in the megaspace field size correlates weakly with wall distance (r = 0.36, Harland 2021, verified). Need:
the rat's position and the feature's position in the same frame to 2-3 cm within the first 30 cm of the feature.

**Speed filtering.** Thresholds 5-10 cm/s (Pfeiffer & Foster 2013; Harland 2021; verified; 2.5 cm/s also common, from
a search summary). Speed from differenced positions amplifies noise by the frame rate: a position sd of 1 cm at 30 Hz is
~40 cm/s of speed noise before smoothing, which is why labs smooth over 0.25-0.5 s. Need: no step in the position stream
larger than threshold x window (1-5 cm for 5 cm/s x 0.25-1 s).

## Q2. Our numbers against those needs

**The decisive distinction is fixed versus time-varying error.** Of the six kinds in the brief, (a) smooth per-camera
distortion and (c) common-mode frame error are fixed functions of place; (b) boundary jumps are fixed in place but
time-varying in effect (the rat crosses them); (d) height, (e) drift and (f) jitter are time-varying. Rate maps,
fields, SI, decoding, replay and remapping live in whatever coordinates the position stream uses; a fixed, smooth
re-labelling of space leaves them intact (field areas change by the local scale, +-2-8 %). Only the time-varying terms
blur them, and only feature-relative analyses see the frame error.

**(a) Fixed per-camera distortion - 19 / 58 own error, 38 / 84 between cameras, plates 28 / 54.** Below one 5 cm bin
in the median, about one bin at p90, two bins in the worst cells (x 360-400 y 120-160 CH06 <= 187 is a bound, not an
estimate; x 80-120 y 0-40 <= 79; x 0-40 y 0-40 <= 58). Verdict: sufficient for all map-internal analyses at 5 cm bins
away from those cells and the seams, at 10 cm everywhere. Note the 23 cells with no comparison (the y 200-240 strip
under CH01 and the y 0-40 strip under CH02, x 80-400): their only evidence is the single-camera plate check (CH01 shape
17 / 25, scale 3.6 % / 7.5 %; CH02 11 / 36, 2.9 % / 12 %) - smooth, but with no absolute own-error estimate. Treat them
as 10 cm class until the before-teardown plates say otherwise.

**(b) Jumps at primary switches - 25-60 median, 32-97 p90, CH01|CH02 58 / 92 across the middle of the field, CH04|CH06
unmeasured.** They cannot split or duplicate a field: 6 cm is < 1/5 of the smallest field, so a field straddling a seam
shows a kink or offset of one half by <= 1 bin, not two fields. With a fixed primary per cell and hysteresis the
occupancy map has a seam stripe of at most one bin of under/over-occupancy - visible to a reviewer, not damaging.
Without hysteresis a rat lingering on a boundary flickers between two images 25-92 mm apart: a doubled occupancy and
a continuous train of 50-280 cm/s speed spikes (budget 2) that pass every speed filter, inflate "running" time at the
seams and corrupt speed-rate modulation and speed-gated phase and sequence analyses. Inside a small field the step is
15-72 deg of phase (budget 3). Verdict: insufficient for speed and phase precession at the seams as a hard switch;
sufficient with blending. For decoding and replay the seam is self-consistent (templates and test share it): harmless.

**(c) Common-mode frame error - CH01 far edge +76 (to +122 west), east end +100..+182 (three cameras agree with each
other), CH02 strip -2 (abs 37); drone itself 3-7 cm, its anchoring 5-10 cm.** Invisible to every map-internal analysis:
the rat and its fields move together. Harmful only where a position is compared with a physical feature placed in the
design frame: a wall "at y = 0" that is really 10-18 cm away makes a border cell look like a 15 cm-offset BVC and
shifts object-vector tuning by the same amount. Verdict: insufficient for feature-relative analyses done in the design
frame; irrelevant otherwise. The remedy is not a better frame but the same frame for both (Q3, A4).

**(d) Height - the largest term at the far rows, and I challenge the brief's 0.73 mm/mm as a general figure.** A pixel
is a ray; a point at height z + g mapped at z moves horizontally by g x d / (H - z), away from the camera. With the
camera at 2.4 m that is 0.43 at 1 m from the pole, 1.0 at 2.4 m, 2.2 at 5 m, 3.0 at 7 m (budget 1); the PHYSLIMIT audit's
far-row sensitivities (2.4-2.9 for the panos, 3.8-4.2 for CH03/CH04 at the opposite end) agree. Consequences: mapping a
7 cm keypoint at z = 0 biases it by 7 cm at 2.4 m and 15-21 cm at the far pano cells - a fixed radial bias of 1-4 bins
that also inflates every seam (the two cameras' biases point in different directions). With z set to the keypoint's
height +-2-3 cm, the posture term is 2-3 cm x s: 2-3 cm near a pole, 6-9 cm in the far strips - the dominant stochastic
blur there (budget 6: 22-34 mm per frame at s = 1, 59-88 at s = 2.9), and a rear (head +10-15 cm) is a 10-45 cm
transient at the far rows. Verdict: sufficient near the poles with the right z; the far strips need 10 cm bins or a
posture-aware z (or the lowest stable keypoint) to be 5 cm class.

**(e) Day-to-day drift - open; PHYSLIMIT quotes 5-15 mm (panos) and 10-25 mm (CH03/CH04) per night.** Within one
camera's region every field shifts coherently by the drift of that day. Against a 3.5 cm median centroid shift of stable
fields (Ziv 2013) a 1-2.5 cm coherent bias is a visible distortion of the shift distribution and of the across-day
population-vector correlation at 3.5-5 cm bins; it masquerades as partial remapping confined to a camera region.
Verdict: cross-day analyses are sufficient only after the planned rigid-landmark per-day correction, with its residual
reported; within-day analyses are unaffected.

**(f) Tracker jitter - not measured.** At 2-8 px/cm a 2-5 px jitter is 0.3-2.5 cm per frame, smoothed away by the
usual 0.25-0.5 s window; it matters for speed (see Q1) and nothing else. Identity swaps between rats are a separate,
far larger risk than any centimetre (a swapped rat is a wrong rate map, not a shifted one).

**Per-analysis verdicts** (thresholds in the table):
rate maps - sufficient (5 cm bins away from seams/hollows/far strips, 10 cm there; z at keypoint height; no hard
switch). Field size/number/location - sufficient. Spatial information - sufficient within one map. Stability/field shift
- sufficient with the per-day correction. Phase precession - sufficient away from seams, insufficient at hard seams.
Theta sequences/decoding - sufficient. Replay - sufficient. Remapping - sufficient with the per-day correction.
Feature-relative - insufficient in the design frame, sufficient with features in the camera frame. Speed - insufficient
at hard switches, sufficient with blending, >= 0.25 s smoothing and posture gating.

## Q3. Remedies, with expected gain and cost

### Analysis side (all desk work; none needs the paddock)

| # | remedy | expected gain | cost |
|---|---|---|---|
| A1 | **Blend cameras across a transition band** (0.5-1 m wide along the primary boundaries from `HANDOFF_MAP`, weights by ground resolution or inverse error) instead of switching; if switching is kept, add hysteresis and a smoother/Kalman filter with a per-camera bias state so the switch is a ramp over ~0.5 s. Exclude +-0.5 s around any residual switch from speed and phase analyses. | the 25-92 mm steps become a ramp of <= 1 cm per 10 cm travelled; speed spikes vanish; phase precession and speed modulation become usable in the seam cells (~30 of 72 cells touch a seam); no change to absolute accuracy (blending does not remove common mode, and it improves random error by at most sqrt 2) | 1-2 days; uses the cell map and resolution table already computed |
| A2 | **One z per keypoint, never 0; prefer the lowest stable keypoint** (tail base / body centre ~5-6 cm) over the nose/head for the position stream; detect rearing from pose (foreshortened body length, head-tail base distance) and interpolate or flag; set z per camera consistently. Measure the keypoint's real height once by triangulating real rats from two cameras in overlap cells on existing footage. | removes a 5-21 cm fixed radial bias and most of the seam inflation; cuts the far-row stochastic term from 6-9 cm to 2-4 cm; a cheap desk measurement replaces a guess | a parameter + 1 desk day for the triangulation |
| A3 | **Bins >= 5 cm with 1-bin Gaussian; 10 cm in the two one-camera strips, the two hollows (row-C east corner, west row A) and for cross-day comparisons; field threshold >= 200 cm^2 as in Harland 2021** | rate maps immune to the fixed error everywhere; fields of 30 cm and up still resolved; the honest per-region accuracy becomes a figure, not a caveat | none |
| A4 | **Features in the camera frame**: click wall bases, house footprints and any object's ground contact in each primary camera's frames, per day for anything that moves (HOUSE_1 moved on 09-18), map them through the same calibration at the right z, and compute every boundary/object distance there | the common-mode error (up to 18 cm) disappears from BVC/border/object analyses; residual = local scale x distance = 1-4 cm within 30 cm (budget 7) | hours of clicking; can be done after teardown from existing frames |
| A5 | **Per-day rigid-landmark correction** (planned in the analysis repo) applied before any cross-day comparison; report the per-camera residual per day and show the field-shift distribution against the measured camera shift as a control | cross-day stability and remapping become interpretable; the 5-25 mm nightly shifts stop looking like drift of the code | already planned |
| A6 | **Speed from the blended, smoothed stream** (>= 0.25-0.5 s window), threshold >= 5 cm/s, rearing-gated; cross-check the speed distribution with and without blending and against the UWB stream | removes the artefactual "running" at seams; a reviewer-ready figure | half a day |
| A7 | **Injection test**: perturb a real position stream by the per-cell error map, the posture term and a simulated day-to-day shift, recompute rate maps/fields/decoding and show the metric changes are within tolerance | turns this audit's thresholds into measured sensitivities for the paper | 1 desk day |

### Calibration side

| # | remedy | expected gain | cost |
|---|---|---|---|
| C1 | **The one calibration improvement that matters for place cells: shrink the inter-camera disagreement at the seams** (CH01|CH02 58 / 92 across the middle, CH01|CH04 45 / 83, CH01|CH06 28 / 46, CH02|CH03 34 / 97) - per PHYSLIMIT the levers are the drone terrain model in the mapping (desk) and rigid plates at the far rows / seam band (field). Since A1 already removes the discontinuity, C1 buys smaller residual distortion, not continuity. | handoff p90 100-122 -> ~80-90 (PHYSLIMIT's estimate); hollow cells 85-95 -> ~50 | 1 desk day + 30-40 min field (see below) |
| C2 | The drone-cord (common-mode) refit now under evaluation | nothing for map-internal analyses; for feature analyses A4 is better and cheaper; useful only if positions must be published in true metres relative to the design frame or tied to UWB in metres | desk only; low priority for place cells |
| C3 | Measure CH04|CH06 (unmeasured boundary, 6 cells) and the CH04 clock confound | closes the last unknown seam | 2 min field (+y/-y ball pass) + 1 h desk |

### What must be measured in the field before teardown

- **Rigid ChArUco plates, located by the drone, in the places no second camera checks**: 4-6 along the y 200-240 strip
  (x 80-400, CH01 only), 4-6 along the y 0-40 strip (x 120-400, CH02 only), 2-3 in each hollow (x 400-480 y 200-240;
  x 0-120 y 0-40). This is PHYSLIMIT action 2 with the strips added. It converts 23 "no data" cells into measured own
  errors and decides whether those strips are 5 cm or 10 cm class. 30-40 min; nothing after teardown can replace it.
- **A +y/-y ball pass through CH04's view** (2 min) for the clock-vs-geometry confound and the CH04|CH06 seam.
- **Sync LED visibility in all six cameras** (a frame check, minutes): the LED is the only common timebase between
  video and ephys; if any camera cannot see it, add a second LED or a visible clap event now.
- Optional, only if positions must ever be stated in true metres: short tapes (<= 1.5 m) from pole bases to the wall
  feet and house corners (rigid references; the operator's rule allows short runs). Not needed for A4.
- Not needed: more cones, cords, long tapes, a rat height measurement in the field (A2 does it from footage), a new
  drone survey for place-cell purposes.

## Q4. Checks a place-cell reviewer will ask for that are not in the list

1. **The tracked keypoint and its height**: which body part, its height distribution by posture (measured, not
   assumed), and the resulting radial error per region; the fraction of frames spent rearing per region.
2. **Video-ephys temporal alignment, per camera**: offset and drift of each camera's frame clock against the ephys
   clock (the NVR OSD already differs from the PC clock by ~59 min; RTSP/NVR latency; frame-rate drift; segment
   rollover gaps), demonstrated with the LED to <= 1 frame. A 33 ms error is 1.7-3.3 cm at 50-100 cm/s (budget 5);
   the lab optimum is an alignment within ~100 ms (Zhang 1998). Spikes and LFP share the logger clock, so phase
   precession and theta sequences depend on this only through position, but a reviewer will ask for the number.
3. **Per-frame jitter and identity**: tracker error on held-out labelled frames per camera (px and cm), identity-swap
   rate in the social group (UWB as the arbiter), fraction of frames without a detection (houses, walls, other rats)
   and how gaps are filled. A swapped identity is the one error that invalidates a rate map outright.
4. **A single-camera absolute check in the one-camera strips** (above) - today those cells have no own-error estimate.
5. **Day-to-day drift**: magnitude per camera per day and the residual after the landmark correction; a figure of
   field-centroid shifts against the camera shift.
6. **An independent-sensor sanity check**: the camera stream against the UWB stream for the same rat (after fitting the
   frame transform on simultaneous data) - UWB will not verify centimetres but it catches gross errors, identity
   swaps and timing.
7. **Seam artefacts in the occupancy map**: a reviewer will look for stripes along the primary boundaries and for a
   speed distribution that differs at the seams; show both with and without blending (A6).
8. **The injection test** (A7): how much each error term moves rate-map correlation, field centroids, SI and decoding
   error - the paper's "position error does not drive the result" paragraph.
9. **Inside the shelters**: rats in the houses are invisible to video; state how occupancy and spikes there are handled
   (UWB only, excluded, or a "house" bin).
10. **Height convention and terrain**: one z per keypoint for all cameras, relief handled (release rev e: z above the
    local ground), documented in Methods.

## Do not do

- Do not map at z = 0, and do not use a different z per camera: 7-21 cm of radial bias at the far rows and inflated seams.
- Do not switch cameras hard without hysteresis, and never compute speed or phase across a hard switch.
- Do not compute distance to a wall, house or object from design coordinates; locate the feature in the same camera map.
- Do not spend effort on the common-mode frame (drone-cord refit, re-anchoring) for place-cell purposes; it changes
  nothing in a rate map. Blending, z, features-in-frame and the per-day correction are where the gain is.
- Do not use bins < 5 cm anywhere, or < 10 cm in the one-camera strips and the hollows, and do not read field-area
  differences < 10 % between regions as biology (local scale 1-4 % median, 7-12 % p90).
- Do not compare field centroids or population vectors across days before the per-day correction, and do not call a
  coherent shift of every field in one camera's region "remapping".
- Do not mix camera-frame and UWB-frame positions without a transform fitted on simultaneous data.
- Do not quote the ball-sweep numbers as the rat's error: they include the ball check's own floor (26-44 mm per
  PHYSLIMIT) and exclude the rat's posture term.
- Do not expect blending to lower absolute error; it removes steps.
- Do not lay more cones or cords or tape long distances before teardown; the 30-40 min of plates and the 2-min ball
  pass are the whole field list.

## References (verification status in brackets)

- Zhang K, Ginzburg I, McNaughton BL, Sejnowski TJ (1998). Interpreting neuronal population activity by reconstruction:
  unified framework with application to hippocampal place cells. J Neurophysiol 79:1017-1044. [verified: pages read -
  20 Hz, 256 x 256 px over ~111 x 111 cm, 1 cm kernel, two-step Bayesian ~5 cm with 25-30 cells, "intrinsic error of
  tracking ~5 cm", 1 s windows, -66 ms optimal shift]
- Pfeiffer BE, Foster DJ (2013). Hippocampal place-cell sequences depict future paths to remembered goals. Nature
  497:74-79. [verified via PMC3990408: 2 x 2 m, 60 Hz two LEDs, 2 cm bins, 4 cm Gaussian, 5 cm/s, 212-250 units,
  events 40-199 cm, 20 ms windows]
- Harland B, Contreras M, Souder M, Fellous J-M (2021). Dorsal CA1 hippocampal place cells form a multi-scale
  representation of megaspace. Curr Biol 31. [verified: author manuscript read - 5.3 x 3.5 m, 82 % 2-5 subfields, 78 %
  of fields <= 1 m^2, 22 % 1-4 m^2, range > 0.6 m^2 in 79 %, 12 cm^2 bins, 10 cm/s, fields > 200 cm^2, 25-30 fps two
  LEDs, r = 0.36 size vs wall distance, less stable across megaspace visits; volume/pages unverified]
- Fenton AA, Kao H-Y, Neymotin SA, Olypher A, Vayntrub Y, Lytton WW, Ludvig N (2008). Unmasking the CA1 ensemble
  place code by exposures to small and large environments. J Neurosci 28:11250-11262. [verified: 76 cm cylinder vs
  1.8 x 1.4 m box; multiple enlarged fields]
- Park E, Dvorak D, Fenton AA (2011). Ensemble place codes in hippocampus: CA1, CA3 and dentate gyrus place cells have
  multiple place fields in large environments. PLoS ONE 6:e22349. [verified existence (PMC3137630); 2.5 m^2 per Harland
  2021; article number unverified]
- Rich PD, Liaw H-P, Lee AK (2014). Large environments reveal the statistical structure governing hippocampal
  representations. Science 345:814-817. [verified existence and 48 m track (via Harland 2021); field-size numbers not
  used]
- Kjelstrup KB, Solstad T, Brun VH, Hafting T, Leutgeb S, Witter MP, Moser EI, Moser M-B (2008). Finite scale of
  spatial representation in the hippocampus. Science 321:140-143. [verified existence and 18 m track; "< 1 m dorsal to
  ~10 m ventral" unverified]
- Eliav T, Maimon SR, Aljadeff J, Tsodyks M, Ginosar G, Las L, Ulanovsky N (2021). Multiscale representation of very
  large environments in the hippocampus of flying bats. Science 372:eabg4020. [verified: 200 m tunnel, fields 0.6-32 m,
  20-fold within a neuron]
- Ziv Y, Burns LD, Cocker ED, Hamel EO, Ghosh KK, Kitch LJ, El Gamal A, Schnitzer MJ (2013). Long-term dynamics of CA1
  hippocampal place codes. Nat Neurosci 16:264-266. [verified via PMC3784308: median centroid shift 3.5 cm, 74-83 %
  <= 7 cm, field width 24 cm, 3.5 cm bins, 84 cm track, mice]
- Lever C, Burton S, Jeewajee A, O'Keefe J, Burgess N (2009). Boundary vector cells in the subiculum of the hippocampal
  formation. J Neurosci 29:9771-9777. [verified via PMC2736390: bias to short preferred distances, width grows with
  distance, 62 x 62 cm box; no numeric distance range quoted]
- Solstad T, Boccara CN, Kropff E, Moser M-B, Moser EI (2008). Representation of geometric borders in the entorhinal
  cortex. Science 322:1865-1868. [verified existence and ~10 % border cells firing along walls; pages unverified]
- Hoydal OA, Skytoen ER, Andersson SO, Moser M-B, Moser EI (2019). Object-vector coding in the medial entorhinal
  cortex. Nature 568:400-404. [verified existence; distance ranges unverified]
- O'Keefe J, Recce ML (1993). Phase relationship between hippocampal place units and the EEG theta rhythm. Hippocampus
  3:317-330. [verified existence and phenomenon]
- Skaggs WE, McNaughton BL, Wilson MA, Barnes CA (1996). Theta phase precession in hippocampal neuronal populations and
  the compression of temporal sequences. Hippocampus 6:149-172. [verified existence; the ~5 cm tracking-error estimate
  attributed via Zhang 1998]
- Wilson MA, McNaughton BL (1993). Dynamics of the hippocampal ensemble code for space. Science 261:1055-1058. [cited
  via Zhang 1998; not independently verified]
- Wikenheiser AM, Redish AD (2015). Hippocampal theta sequences reflect current goals. Nat Neurosci 18:289-294.
  [verified existence; look-ahead distances unverified]
- Davidson TJ, Kloosterman F, Wilson MA (2009). Hippocampal replay of extended experience. Neuron 63:497-507.
  [verified: 10 m track, ~8 m/s virtual speed; bin sizes unverified]
- Skaggs WE, McNaughton BL, Gothard KM, Markus EJ (1993). An information-theoretic approach to deciphering the
  hippocampal code. Adv Neural Inf Process Syst 5:1030-1037. [standard reference; unverified in this audit]
- Mathis A, Mamidanna P, Cury KM, Abe T, Murthy VN, Mathis MW, Bethge M (2018). DeepLabCut: markerless pose estimation
  of user-defined body parts with deep learning. Nat Neurosci 21:1281-1289. [verified existence and "human-level
  accuracy with ~200 labelled frames"; pixel figures unverified]
- Pereira TD, Aldarondo DE, Willmore L, Kislin M, Wang SS-H, Murthy M, Shaevitz JW (2019). Fast animal pose estimation
  using deep neural networks. Nat Methods 16:117-125. [< 3 px after ~500 frames, from a search summary; pages unverified]
- Muller RU, Kubie JL, Ranck JB (1987). Spatial firing patterns of hippocampal complex-spike cells in a fixed
  environment. J Neurosci 7:1935-1950. [rate-map method; cited via Zhang 1998; not independently verified]
- Local: `CAMERA_ERROR_MAP.txt`, `SINGLE_CAMERA_CHECK.txt`, `DRONE_LINE_CHECK.txt`, `HANDOFF_MAP_2026-10-03.txt`,
  `AUDIT_FABLE_PHYSLIMIT_2026-10-03.md`; arithmetic in `tmp_placecell\placecell_budget.py` / `.out`.
