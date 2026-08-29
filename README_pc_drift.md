# PC clock drift monitor (`pc_drift_check.ps1`)

Passively measures this PC's clock against public NTP servers 4×/day and logs the
offset — **it never adjusts the clock** (raw read-only NTP queries, independent of
the W32Time service state). With "Set time automatically" OFF during a cohort, the
series is the **PC-vs-true-UTC drift curve** for the whole rig.

## Why this is an analysis resource

Every modality (video segments, mics, WISER, wild_console, led_sync) follows this
one PC clock. The neurologger pipeline maps logger time → PC time per session; this
log closes the chain with PC time → true UTC, and it directly tests the
linear-drift assumption on the PC side: a straight line in the plot = assumption
holds; bends or steps = something changed (temperature, NTP kicked in, manual
clock edit) and analysis should segment there.

## Outputs (`E:\recording_qc`)

- `pc_drift_log.csv` — one row per run:
  `local_time, utc_time, offset_ms, delay_ms, server, samples, tz_id, dst_capable, w32time, status`
  - `offset_ms` = PC minus NTP; **positive = PC fast**. Taken from the single
    sample with the smallest round-trip `delay_ms` across all servers (~15
    queries/run) — path-asymmetry error is bounded by delay/2, so low delay =
    trustworthy. `status` = `OK`, `OK-noisy` (best delay >200 ms — weight down or
    drop), or `FAIL:no-ntp-response`.
  - `tz_id`/`dst_capable`/`w32time` record the clock-config context, so later
    analysis can tell drift-regime changes (NTP on vs off) from real drift.
- `pc_drift.png` — offset vs time with the drift rate fitted over the last 7 days.
  **1 ppm = 86.4 ms/day.** Typical PC crystals: a few ppm to a few tens of ppm.

## Install (elevated, once)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_pc_drift_check_task_system.ps1 -RunNow
```

SYSTEM task "Field PC Drift Check": daily 00:45 + every 6 h (00:45/06:45/12:45/18:45).
Each run is ~15 UDP packets over the internet uplink — nothing touches the
analysis link or the USB fabric.

## Testing

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pc_drift_check.ps1 -SelfTest   # offline math checks
powershell -NoProfile -ExecutionPolicy Bypass -File .\pc_drift_check.ps1 -DryRun     # real query, no writes
```

Exit codes: 0 = ok, 1 = warning (NTP unreachable, FAIL row logged), 2 = error.

## Reading the plot

- Flat near 0 with wiggles of a few ms: NTP is actively steering (between cohorts).
- Straight sloped line: NTP off, clean linear drift — the slope is your correction
  rate and the neurologger linearity assumption is validated PC-side.
- A step: someone/something set the clock — check `w32time` column and the
  incident log; analysis must split at the step.
