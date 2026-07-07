# Disk-space Slack warning

> ⚠️ **STATUS: BUILT & TESTED — NOT YET INSTALLED (deferred 2026-06-29).**
> The script and installer exist and Slack delivery is verified, but the scheduled
> task is **not** registered, so it does **not** run automatically yet. Install it
> when ready (command below). Check with:
> `Get-ScheduledTask -TaskName 'Field Disk Space Check' -ErrorAction SilentlyContinue`
> (returns nothing until installed).

## Why this exists

Recorder auto-delete was turned **OFF** on 2026-06-29 (`RetentionDays = 0`,
`MinFreeGB = 0` in both `recorder.config.psd1` and `thermal.config.psd1`), so nothing
is ever deleted by age or low space. `disk_space_check.ps1` is the safety net: it
Slack-warns at **50% / 80% / 90%** full so footage can be backed up and space freed
before recording is ever at risk. At ~160 GB/day (~0.8%/day) the warnings come with
weeks of lead time.

## What it does

- Reads free/used space on `E:` (read-only; never deletes or touches recordings).
- Alerts when it crosses **up** into a new band (50 → 80 → 90%), then at most once per
  24 h while it stays there; sends a "recovered" note if space drops back below all
  thresholds.
- Sends to the **disk-space** destination list `SlackChannels` in
  `E:\recording_qc\overexposure.config.psd1` (channel `C0BDSLAJ3A5` + Hongyu's DM).
  *(Overexposure alerts use the separate `OverexposureChannels` = DM-only list.)*
- Logs to `E:\recording_qc\disk_space_log.txt`; de-dup state in `disk_space_state.json`.

## Install when ready (Administrator PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\install_disk_space_check_task_system.ps1" -RunNow
```

Registers SYSTEM task **Field Disk Space Check**, runs **every 6 h** (00:15 / 06:15 /
12:15 / 18:15). Change cadence with `-EveryHours 12`; thresholds default to 50/80/90.

## Run / test by hand

```powershell
$dc = "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\disk_space_check.ps1"
& $dc -DryRun        # print current % full + band; send nothing
& $dc -TestSlack     # send a test message to the disk-space destinations
```

## Reminder

With auto-delete off, keeping space free is manual: back up with `copy_day_to_usb.ps1`,
then reclaim with `delete_day.ps1`. If the disk ever fills, recording stops — there is
no longer a safety net to shed old footage. **Installing this task is what makes sure
you get warned in time.**
