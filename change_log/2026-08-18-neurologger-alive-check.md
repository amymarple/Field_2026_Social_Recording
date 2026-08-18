# 2026-08-18 — Neurologger "logger missing" Slack watchdog

## What

Added `neurologger_alive_check.ps1` + `install_neurologger_alive_check_task_system.ps1`
at the repo root: a read-only watchdog for the 6 CE64X loggers of the LFP cohort.

Data source: wild_console (3.4.2.132) continuously rewrites a snapshot CSV of every
logger it hears over BLE:

```
C:\Users\Cornell\AppData\Local\CE32_console\discovered_devices.csv
  device_name, bluetooth_addresses, reporter_rssi, rssi_dbm, last_seen_local,
  format_version, recording_elapsed_seconds, used_storage_percent,
  battery_voltage_volts, payload
```

(Path confirmed by decompiling `Form_DiscoveredDevices.ResolveStatusCsvPath`:
`%LOCALAPPDATA%\CE32_console`, fallbacks exe-dir `ce32_console_logs` and `%TEMP%`.
Updates every few seconds while the console's Discovered Dataloggers scan runs.)

## Alerts

- `:rotating_light:` **NEUROLOGGER MISSING** — a rostered logger's `last_seen_local`
  older than 60 min (field rule: < 1 h dropouts are normal BLE flakiness). Page once,
  re-page hourly, `:white_check_mark:` recovery when all are seen again. The alert
  text includes the rat-05 phone check instructions (Scan only — never connect).
- `:warning:` **FEED STALE** — the CSV itself not rewritten for 15 min (wild_console
  closed / scan stopped): logger status unknown. Per-logger checks are skipped while
  the feed is down so it cannot false-page all six at once. Exit 2.
- `:battery:` low battery (< 3.60 V), `:rotating_light:` battery CRITICAL (< 3.50 V —
  the LiPo discharge knee: hours left, added same day after the 900 mAh runtime
  estimate), and `:floppy_disk:` storage (>= 90 %) — one page per device per
  excursion, silent auto-clear. Both battery tiers are separately de-duped, so a
  cell gets one warn page at 3.6 and one urgent page at 3.5.

Slack creds reused from `E:\recording_qc\overexposure.config.psd1`. Optional config
key `NeurologgerDevices = @{ device_name = 'label' }` overrides the built-in cohort
roster (SF01 Delta …64C4 → SF06 Barrs …0151) without task re-install.
State/log: `E:\recording_qc\neurologger_alive_{state.json,log.txt}`.

## Verified

- `-SelfTest` PASS (stale row, missing row, low battery, high storage all detected
  on synthetic rows; no disk state, no Slack).
- `-DryRun` against the live CSV 2026-08-18 02:2x: 6/6 loggers seen (ages < 1 min),
  exit 0.
- Task NOT yet installed — needs `-TestSlack` and the elevated installer run.

## Install (elevated PowerShell)

```
powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_alive_check.ps1 -TestSlack
powershell -NoProfile -ExecutionPolicy Bypass -File install_neurologger_alive_check_task_system.ps1 -RunNow
```

## Fix same day: FILETIME-zero false FEED STALE

First installed run paged "not updated for 223858725.2 min" (= 425.6 years = the
timestamp read as 1601-01-01, FILETIME zero). Cause: wild_console rewrites the CSV
every few seconds and `Get-Item .LastWriteTime` raced the rewrite, returning
uninitialized metadata. Fix: feed freshness is now the NEWER of (a) fs
LastWriteTime, ignored unless sane (year >= 2020), and (b) the newest
`last_seen_local` inside the CSV content; if neither yields a sane timestamp the
run skips silently (transient collision) instead of paging. An empty/half-written
CSV likewise skips instead of declaring all six loggers missing.

## Notes

- Wholly independent of the camera/audio recorders: reads one CSV under the Cornell
  profile, writes state only under `E:\recording_qc`. Never talks BLE, never touches
  loggers or recordings.
- Depends on wild_console running with its discovery scan active on the main PC —
  that is now part of the rig by protocol (Notion "Daily Checks"); if it is closed,
  the FEED STALE alert says so instead of guessing.
- Watchdog complements, not replaces, the daily 4 PM manual resync protocol
  (`README_neurologger_daily_resync.md`).
