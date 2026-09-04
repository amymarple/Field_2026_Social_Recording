# Camera Calibration → Common Field Coordinates (all 8 channels)

Protocol + **recording-side ledger** for mapping every camera into the one shared field
frame. This file lives in the RECORDING repo on purpose: calibration validity is tied to
the physical rig timeline (a camera that got touched is a camera whose calibration is
suspect), and only the recording side knows when that happened. **Whoever touches a
camera, wall, pole, or shelter fills in the tables below — that is the contract.**

Division of labor:

| Where | What |
|---|---|
| **This repo** (this file) | Protocol, calibration-epoch registry, physical-event log, field-action capture log — the human-filled ground truth |
| `Field_2026_Social\preprocessing\computer_vision` | All fitting code (`calibration.py`, `intrinsics.py`, `field_coords.py`, `merge_cameras.py`) and machine configs (`configs/field_layout.json`, `configs/CHxx_calib.json`, overlays) |

## The common frame (already defined — do not redefine)

Field cm, origin at corner pole **A0**; **x = 40 ft length** (0–1219.2 cm),
**y = 20 ft width** (0–609.6 cm). Deliberately aligned with the WISER UWB frame
(WISER reports inches; 1 in = 2.54 cm) so camera tracks and UWB tracks cross-validate.
Geometry source of truth: `configs/field_layout.json` in the CV folder — 15 poles on a
10 ft grid (rows A/B/C × columns 0–4), wall height 97.79 cm, two shelters.

## Camera inventory and mapping models

| Channel | Camera / view | Model → field cm | Calib status (2026-09-04) |
|---|---|---|---|
| CH01/CH02 | Duo3 180° panoramas on B1/B3 | `poly` (2nd-order, ≥6 pole bases) | **not done** |
| CH03/CH04 | RLC-1212A side cams (x=0 / x=1219.2 ends) | checkerboard intrinsics → undistort → homography (or PnP via pole base + wall-top pairs) | **not done**; temp ground markers M*/N* presumed removed from the grass |
| CH05/CH06 | RLC-520A nadir over shelters, through IR window | homography from shelter's 4 corners | done **2026-06-29** — 4-point exact fit (RMSE 0.0 is an identity, not accuracy) and **unverified since the 07-17 rewiring** |
| CH07/CH08 | EmpireTech 720p **inside** the home boxes (bypass the IR glass) | homography: box interior floor corners → that shelter's field-cm footprint | **not started**; CH07/08 absent from `field_layout.json` and `camera_specs.json` |

## Protocol

### Phase 0 — calibration epoch

Pick one day as the epoch base. Grab one reference still per camera **the same day**
(`extract_clip.py --channel CHxx --frame` — reads only closed `_to_` segments; zero
impact on recording). Every calib file belongs to that epoch. Any physical contact with
a camera afterwards opens a new epoch (see the event log below).

### Phase 1 — CH05/CH06: verify, don't redo

Overlay the existing `CH05/06_grid_overlay.png` grid on a fresh still first — if the
grid still lands on the real structure, the camera hasn't moved and the calib carries
over. Either way, **add redundant landmarks this pass** (visible pole bases beyond the
4 shelter corners) so the RMSE becomes a real number and future drift checks have
reference pixels.

### Phase 2 — CH01/CH02 (Duo3 poly)

Click as many pole bases as the panorama shows (≥6 required; aim for 10+), hold 2–3 out
of the fit for a held-out error. **Pitfall: Duo3 footage is stored rotated 90°** — the
calibration still must be in the SAME orientation the tracking pipeline decodes, or the
pixel frame won't match.

### Phase 3 — CH03/CH04 (the heavy pair)

1. **Intrinsics**: in daylight, wave a flat checkerboard in front of each camera for
   60–90 s (±30–45° tilts, cover the whole frame incl. corners, near+far, stop-and-go).
   No recording changes — the normal recorder captures it; afterwards extract that
   window from the closed segment and run `intrinsics.py`. Sanity check: the wall looks
   straighter in `CHxx_undistort_preview.png`.
2. **Ground correspondences**: markers are gone, so use the **PnP route** — for each
   visible pole click its base (z=0) AND where it crosses the wall top (z=97.79 cm).
   3 poles × 2 = 6 points solves the pose even with collinear ground poles. (Fallback:
   re-place temporary markers for one recorded hour, then remove — log it below.)

### Phase 4 — CH07/CH08 (in-box cams; conceptually different)

They see the box interior, not the open field — but each box has a known pose in the
field frame (`shelters.left/right` in the layout). So: homography from the **interior
floor's 4 corners** to that box's field-cm footprint — same construction as CH05/06.
One field action needed: **when a box is animal-free** (cohort changeover / daily
check), lay a ruler on the interior floor, let the camera record one frame of it, and
tape-measure the interior clear dimensions (inner-wall to inner-wall — NOT the
62.55 × 45.72 cm exterior footprint). Then add CH07/CH08 `camera_mounts` entries +
an EmpireTech-720p entry in `camera_specs.json`; existing `calibration.py` takes it
from there. The 1/6 s-exposure image is soft, but the four corners are static
structure and clickable.

### Phase 5 — validation, three levels (cheap → expensive)

1. **Grid overlay eyeball**: green grid must land on real poles/walls in every
   `CHxx_grid_overlay.png`.
2. **Held-out RMSE**: 2–3 landmarks per camera excluded from the fit. Targets: nadir
   cams < 3 cm; CH03/04 far-field < 15–20 cm acceptable.
3. **WISER cross-validation** (unique to this rig): pick a window with UWB-tagged rats
   moving on the field, project camera tracks to field cm, compare to WISER positions
   at the same timestamps (WISER data from the `E:\Wiser_backup` snapshots, never the
   live DB). Gives an end-to-end error distribution AND a per-region accuracy map
   telling you which camera to trust where. Overlap-zone agreement (CH01/02 vs
   CH03/04 seeing the same rat) falls out for free.

### Phase 6 — merge conventions

`merge_cameras.py` already concatenates + bounds-checks. Two conventions to fix:
(a) **ground point = bbox bottom-center, not centroid** — homographies map the ground
plane; a rat's back is ~5 cm up, which is ~20 cm of parallax at 10 m for the side cams;
(b) overlap de-duplication: initially "the camera with the better local accuracy-map
error wins"; cross-camera identity is a later stage by design.

## Ops rules

- **Capture-safe throughout**: all material (stills, checkerboard windows, validation
  windows) comes from closed `_to_` segments. Field actions are simply performed in
  front of the running recorders and extracted later. Nothing touches a live stream.
- **Time alignment**: filenames are PC-clock; use them for merging and WISER alignment.
  The on-image OSD clock is the NVR clock (**PC − 1 h**) — never align on it.
- **Drift check** (monthly + after any physical event): re-extract a still, template-
  match at the saved landmark pixels in `CHxx_calib.json` (raw clicks are stored there
  for exactly this), shift > ~5 px ⇒ recalibrate that camera and open a new epoch.

---

## LEDGER — fill these in (recording-side source of truth)

### A. Calibration epoch registry

One row per camera per epoch. `valid_from` = reference-still date; `valid_to` stays
open until a physical event closes it.

| Camera | Epoch | valid_from | valid_to | Reference still | Calib file | Held-out RMSE (cm) | Status |
|---|---|---|---|---|---|---|---|
| CH05 | 1 | 2026-06-29 | ? (07-17 rewiring unverified) | configs/CH05_reference.png | CH05_calib.json | n/a (4-pt exact) | needs verification |
| CH06 | 1 | 2026-06-29 | ? (07-17 rewiring unverified) | configs/CH06_reference.png | CH06_calib.json | n/a (4-pt exact) | needs verification |
| CH01 | — | | | | | | not calibrated |
| CH02 | — | | | | | | not calibrated |
| CH03 | — | | | | | | not calibrated |
| CH04 | — | | | | | | not calibrated |
| CH07 | — | | | | | | not in layout yet |
| CH08 | — | | | | | | not in layout yet |

### B. Physical event log

Anything that touches a camera, its mount, pole, wall, or shelter. Network-only events
(NVR reboot, PoE restart) don't move optics but log them anyway with "no contact".

| Date | Camera(s) | What happened | Physical contact? | Action |
|---|---|---|---|---|
| 2026-07-17 | CH07, CH08 | moved from direct PoE onto the NVR (rewiring at the cameras) | likely — cameras handled | drift check before first use of any pre-07-17 calib assumption |
| 2026-08-19 | CH01–CH08 | NVR reboot + PoE switch restart during outage debugging | no (network only, believed) | none; verify at next epoch stills |
| | | | | |

### C. Field-action capture log

So the analysis side can find the material inside the recordings.

| Date | Action | Camera(s) | Time window (PC clock) | Notes |
|---|---|---|---|---|
| | checkerboard sweep | CH03 | | board size/squares: |
| | checkerboard sweep | CH04 | | |
| | in-box ruler frame + interior tape measure | CH07 (left box) | | interior floor W×L (cm): |
| | in-box ruler frame + interior tape measure | CH08 (right box) | | interior floor W×L (cm): |
| | calibration walk (stand 3 s at each of the 15 poles) | all | | walker: |
| | (optional) temp markers re-placed / removed | CH03/CH04 | | positions logged in field_layout.json markers block |

### Suggested order

Desk work first (any time): CH05/06 verification → CH01/02 poly → layout entries for
CH07/08. Field actions (three, all cheap): ① 10 min checkerboard per side cam in
daylight; ② ruler + tape measure per box at the next animal-free moment; ③ one
calibration walk — it feeds every Phase-5 validation at once.
