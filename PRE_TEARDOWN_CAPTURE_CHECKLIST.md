# PRE-TEARDOWN CAPTURE CHECKLIST — cohort 3 is the LAST cohort

Context (2026-09-09): cohort 3 closes the summer experiment and **the paddock will be
demolished**. Every calibration below is the FINAL one — after teardown nothing can be
re-measured, re-shot, or drift-checked, ever. The success criterion is therefore not
"today's cameras are calibrated" but: **the retrospective analysis of the ENTIRE
summer's footage (cohorts 1–3) has everything it will ever need.** Over-collect;
"exactly enough" is the failure mode.

Operator has unrestricted field control time. Governing docs:
[PLAN_CH01_CH02_pano_ground_map.md](PLAN_CH01_CH02_pano_ground_map.md) (v2),
[CAMERA_CALIBRATION_AUDIT_PLAN.md](CAMERA_CALIBRATION_AUDIT_PLAN.md),
[AUDIT_RESPONSE_2026-09-09.md](AUDIT_RESPONSE_2026-09-09.md).

## Hard ordering rules

1. **Cameras and recorders are dismantled LAST.** All calibration material must be
   captured while every camera still records from its final mounted position.
2. **Nothing is torn down until the day's captured material is extracted, verified,
   AND backed up to the analysis PC** (`copy_to_analysis.ps1`) with size checks.
   Teardown is the one deadline that converts a "re-shoot tomorrow" into "lost forever".
3. WISER comes down with the paddock too: any camera↔UWB cross-material must be
   captured while both run.

## A. Calibration material (cameras recording, field controlled)

- [ ] **CH01/CH02**: the full v2 session — 35 training + 24 val/test stations, seam
      groups, top-view deliverable. (The plan doc governs.)
- [ ] **CH03/CH04**: ChArUco intrinsics sweep per camera (20–30 held poses) + measured
      dispersed GROUND points across each camera's use region (board placements /
      flat markers; no mixed heights).
- [ ] **CH05/CH06**: measure the ACTUAL shelter poses now (resolves the 114.6 cm
      geometry conflict by direct measurement); target-plane material per audit §3.C
      (12 measured positions per plane: 6/3/3) + photos identifying exactly which
      plane (roof? floor? window frame?) the old June clicks were on.
- [ ] **CH07/CH08 — DEFERRED by operator decision 2026-09-09**: box positions are
      recoverable from video later, so no in-box field session. NON-NEGOTIABLE
      remainder: the boxes' interior clear dims + wall thickness + floor height cannot
      be recovered from video — tape-measure the boxes before they are disposed of
      (they may simply be kept after teardown; 5 minutes whenever convenient).
- [ ] **Static UWB dwells**: tag at 5–10 measured positions, 10–20 s each, tag height
      + antenna reference logged (last chance for camera↔WISER consistency evidence).
- [ ] Night-check clips: one short controlled-target capture after dark per camera
      family, so day-calibration → night-footage transfer can at least be sanity-checked.

## B. Field survey (independent of cameras — impossible after demolition)

- [ ] All 15 pole positions MEASURED (not design), with method + uncertainty.
- [ ] Field edge lengths + both diagonals; wall height at ≥4 points.
- [ ] Shelter exterior footprints AND interior dims, wall thickness, floor heights,
      poses in field coordinates.
- [ ] Camera mount positions + heights + aim for all 8 (resolves the layout
      placeholder warnings permanently).
- [ ] Any other structure visible in ANY camera (gates, feeders, wall seams, IR
      window frames): position + dimensions.
- [ ] **Photo survey**: high-res phone photos of every structure from multiple angles,
      with a tape measure in frame; wide shots tying structures together. Cheap
      insurance for every unanticipated future question.
- [ ] All numbers into the ledger/layout with date + method; design values that were
      verified get marked "measured", the rest stay flagged.

## C. Historical bridge (desk; footage must be archived first)

The calibrations apply to past months only where cameras did not move. Before analysis:

- [ ] Extract stills across the whole recording history (≈weekly + around every known
      physical event from the incident log) for all 8 channels.
- [ ] Template-match stable structures → segment each camera's timeline into
      stable periods; mark which periods today's calibration covers.
- [ ] Periods with a moved camera: calibrate retrospectively from structures visible
      in that period's footage + the section-B survey (this is WHY B must be complete).
- [ ] June parameters + their geometry version stay archived untouched.

## D. Final gate before demolition begins

- [ ] Every item above checked off or explicitly waived in writing in the ledger.
- [ ] All capture-day footage verified present on the analysis PC (manifest + sizes).
- [ ] `verify_on_analysis.ps1` run clean on the capture days.
- [ ] Ledger tables A/B/C in README_camera_calibration.md filled; this checklist
      committed with every box resolved.

Only then does teardown start — cameras last.
