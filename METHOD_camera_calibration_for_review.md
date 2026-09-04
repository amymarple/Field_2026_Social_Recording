# Multi-camera → common ground coordinates: method for external review

Self-contained method description for a second opinion. No repo context needed; everything
relevant is stated here. **Questions for the reviewer are at the bottom.**

## Setup

Outdoor rat paddock, **20 × 40 ft (609.6 × 1219.2 cm)**, grass floor, enclosed by a
**97.79 cm** wall. Permanent structure available as calibration references:

- **15 poles** on an exact 10-ft grid: 3 rows (y = 0 / 304.8 / 609.6 cm) × 5 columns
  (x = 0 … 1219.2 cm). Surveyed positions are trusted.
- The wall (top and bottom edges = long straight lines in side-camera views).
- Two **shelter boxes** (62.55 × 45.72 cm exterior footprint) at known poses on the field.

Common frame: ground-plane cm, origin at a corner pole. An independent UWB tracking system
(WISER) reports animal positions in the same frame — usable for end-to-end cross-validation.

8 cameras, three families, all pole-mounted at ~2.44 m:

| Cams | Hardware | View | Native res |
|---|---|---|---|
| CH01/CH02 | Reolink Duo 3 — **dual-lens, software-stitched 180° panorama** | full-field panorama from mid-field poles | 7680×2160 (stored rotated 90°) |
| CH03/CH04 | Reolink RLC-1212A — rectilinear wide, **107° HFOV**, moderate barrel distortion | oblique down the field length from each short end | 4096×2784 |
| CH05/CH06 | RLC-520A, ~nadir above each shelter, viewing **through an IR-transmitting glass window** | shelter + small surround | 2560×1920 |
| CH07/CH08 | 720p cams **inside** each shelter box (dark box, 1/6 s exposure, ~6 fps, soft image) | box interior floor | 1280×720 |

Goal: map animal detections (bounding boxes) from every camera into field-cm.
**Only the ground plane matters** — no 3D reconstruction, no metric depth.
Accuracy targets: nadir/in-box < 3 cm; oblique side cams < 15–20 cm at far field.
Animals are rats: body height ~5 cm above ground (parallax source for oblique views).

Operational constraints: cameras record 24/7 and must not be disturbed; field actions are
performed in front of the running recorders and the footage is extracted afterwards.
Calibration landmarks are clicked by hand on reference stills (±2–3 px realistic).

## Per-family mapping models

**CH05/CH06 (nadir over shelter):** plane-to-plane **homography** from the shelter's 4
corners (known field-cm) to their image positions. Currently an exact 4-point fit (zero
redundancy); plan is to add visible pole bases as extra correspondences so the fit is
overdetermined and RMSE is meaningful. Refraction through the flat IR window is treated as
absorbed by the homography for the floor plane (near-nadir, thin glass).

**CH07/CH08 (inside the boxes):** same construction one level down — homography from the
box **interior floor corners** (interior clear dimensions tape-measured once, box pose in
the field known) to image. Output is field-cm via the box pose. Corners are static
structure, clickable even in the soft 720p image.

**CH03/CH04 (107° rectilinear, oblique):** two-step.
1. **Undistort.** Preferred: **plumb-line** self-calibration — fit a 1-parameter division
   model (+ distortion center) that straightens the wall-top and wall-base lines, which
   cross most of the frame horizontally. Zero field action, automatically repeatable from
   any still. Fallback if held-out error fails: classic **checkerboard intrinsics**
   (A1 board, 10×7 squares of ~75 mm, 15–30 poses, ±30–45° out-of-plane tilts, whole
   frame covered — with the caveat that a ground-held board cannot easily reach the top
   image corners from below a 2.44 m camera).
2. **Fit a homography** on undistorted ground correspondences. Correspondences come from
   pole bases; because the visible ground poles from an end-on view are few and nearly
   collinear, each pole contributes **two** points: its base (z=0) and where it crosses
   the wall top (z=97.79 cm) — solved either as planar-target PnP (IPPE) with a
   spec-sheet-approximated K (focal from nominal FOV), or, after undistortion, as a
   ground homography using bases only plus any extra ground marks.

  Rationale for plumb-line-first: the fitted-model error concentrates where the
  constraint lines are NOT — i.e., top image corners — which do not image the ground
  plane anyway; meanwhile a handful of hand-clicked landmarks cannot constrain a full
  distortion polynomial (README-observed failure mode: perfect at clicked points,
  50–100 cm elsewhere).

**CH01/CH02 (stitched dual-lens 180° panorama):** no single-lens model exists for a
software-stitched composite (two lenses + proprietary blending seam), and straight lines
are *supposed* to be curved in a 180° view, so neither checkerboard intrinsics nor
plumb-line applies. Instead a **direct empirical map**: 2nd-order bivariate polynomial
(12 params) from image px to field cm, least-squares fitted on **all visible pole bases**
(aim 10–12 of the 15; minimum 6), holding 2–3 out for validation. Lens distortion,
stitch warp, and pose are absorbed together; validity is restricted to the ground plane,
which is the only surface used. Known weak spots to check with held-out points: the
stitch seam (possible discontinuity) and the extreme panorama edges (strongest
compression). Escalation path if 2nd order is insufficient regionally: temporary ground
markers in that region for one recorded hour, and/or higher-order / thin-plate-spline map.

## Detections → ground point

Ground contact point = **bounding-box bottom-center**, not centroid: homographies map the
ground plane, and a rat's back at ~5 cm height seen from an oblique camera 10 m away
introduces ~20 cm of parallax if the centroid is used.

## Validation ladder

1. **Grid overlay**: reproject the 10-ft grid into each camera; must land on real poles.
2. **Held-out landmarks**: 2–3 per camera excluded from every fit; report cm error.
3. **UWB cross-validation**: animals carry UWB tags; project camera tracks to field-cm and
   compare against UWB positions at matched timestamps → end-to-end error distribution
   and a per-region accuracy map (also arbitrates which camera wins in overlap zones).
4. **Calibration walk**: a person stands 3 s at each of the 15 poles in one recorded
   pass — provides a known-position target for all cameras simultaneously, including on
   the panorama stitch seam.

Temporal validity: each calibration belongs to an epoch; any physical contact with a
camera opens a new epoch. Drift check = template-match the saved landmark pixels in a
fresh still; shift > ~5 px ⇒ recalibrate.

## Questions for review

1. **CH01/02 panorama:** is a 2nd-order polynomial a reasonable first model for a
   stitched 180° pano → ground plane, given 10–12 well-spread control points? Would you
   go straight to TPS, per-lens-half models, or something else? Any known pitfalls with
   Reolink Duo-3-style stitching (e.g., seam warp varying over time/temperature)?
2. **CH03/04:** is plumb-line (1-param division model from two long horizontal wall
   lines) → homography a sound *first* route for a 107° rectilinear lens, with
   checkerboard as escalation? Is the "weakly constrained regions don't image the
   ground" argument valid, or does distortion mis-estimated at the constraint band still
   bias the ground map significantly?
3. **PnP with spec-sheet K** (focal from nominal FOV, principal point at image center):
   acceptable for a ground-only mapping, or should we avoid PnP entirely and stick to
   undistort + ground homography?
4. **CH05/06 through flat glass at near-nadir:** is absorbing refraction into the
   homography safe at these angles, or should we expect a measurable radial shift near
   the shelter edges?
5. **Parallax handling:** bbox bottom-center — good enough, or is an explicit height
   correction (project ray, intersect z = 5 cm) worth it for the oblique cams?
6. Anything important this plan is missing for a fixed outdoor multi-camera rig
   (thermal expansion of poles, wind sway, day/night exposure differences affecting
   landmark clicks, etc.)?
