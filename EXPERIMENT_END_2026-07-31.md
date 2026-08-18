# Cohort `cohort1_mice` END — all recording stopped (2026-07-31)

**Cohort:** formal MICE cohort, **2026-07-19 20:00 → 2026-07-31 ~10:45** (≈11.6 days).
**Action:** all RTSP/thermal/audio recording stopped and every alert/QC task disabled
(reversible — tasks disabled, not deleted). WISER acquisition software + `wiserex`
service are the user's domain and were handled by the user.

## Shutdown timeline (2026-07-31)

1. ~10:44 — alert/QC tasks disabled first (no Slack flood), Reolink RTSP Recorder
   (CH01–08) stopped: its 8 ffmpeg ended, last video files ~10:45.
2. First pass left two supervisors alive (thermal task was registered under a
   different/old name; UltraMic stop did not take). Second pass stopped
   `Reolink Thermal Recorder` / `EmpireTech Thermal Cameras Recorder` /
   `Field UltraMic Recorder` by every known name and killed remaining processes.
3. **10:56 verified fully down:** ffmpeg = 0; ultramic supervisor + capture = 0
   (both `Global\FieldUltraMic*` mutexes released); all newest files frozen
   (video ~10:45, thermal ~10:54).

## Data coverage notes for analysis

- **Video (CH01–08) + thermal (108/109):** continuous through 2026-07-31 ~10:45/10:54.
  The final in-progress segments were closed by the kill (fragmented MP4 → playable,
  no `_to_` suffix). Copying that last partial hour requires `-IncludeActive`.
- **Ultrasonic audio (MIC01): ends 2026-07-28 12:39.** The mic wedged a second time
  (same failure signature as 07-18; still on the 65-ft PASSIVE USB extension — the
  planned ACTIVE-cable swap had not happened). One page was sent per the mute design;
  the supervisor retry-looped until shutdown. **No audio for the cohort's final ~3 days.**
- **Encoder settings all cohort:** CH01/CH02 VBR max 7168 (final config from the
  capped-keyframe experiment; daily 05:20 monitor watched it throughout).

## Disabled tasks (re-enable or re-run installers to resume)

Recorders: Reolink RTSP Recorder · Reolink Thermal Recorder (+ legacy EmpireTech name) ·
Field UltraMic Recorder · Field RTSP Failover Recorder.
Alerts/QC: Field Recording Alive Check · Field Overexposure Check (Finished + Sunrise
Active) · Field Disk Space Check · Field Capped Keyframe Check · Field Recording
Continuity Check · Recording Health Check · WISER Hourly Occupancy · WISER Daily Backup.

## Before the next cohort (lessons carried forward)

1. **Install the ACTIVE USB extension cable for the UltraMic** — two wedges in two
   cohort-weeks on the passive cable; also consider the powered-hub + smart-plug for
   remote power-cycling. Un-mute MIC01 (`AliveMuteGroups` in the QC config) once stable.
2. Archive this cohort: `copy_cohort_to_usb.ps1 -Usb <drive> -Cohort cohort1_mice`
   (layout `<drive>\cohort1_mice\<date>\<camera>\`; ~11 full days ≈ ~5 TB).
   Then day-by-day `delete_day.ps1` as space requires.
3. Resume = re-run the `install_*_task_system.ps1` installers (+ WISER installers with
   the new cohort's `-DbPath`), update `configs/rat_identities.csv` with the new
   roster, add the new `COHORTS.csv` row.
