# Delete one day's recordings (targeted cleanup)

`delete_day.ps1` removes the recordings for **one specific day** from
`E:\Reolink_record` and `E:\thermal_record`. It is the counterpart to
`copy_day_to_usb.ps1` (the **save** script): by default it refuses to delete a day
unless the save log shows that day was already copied off.

## What it does (and what it can't do)

- Deletes only the **finished** `.mp4` files whose **start date** (parsed from the
  filename, e.g. `CH01_2026-06-20_14-00-00_to_15-00-00.mp4`) equals the day you
  give it. Every other day is left untouched.
- **Never** touches the still-recording file (the one with no `_to_` in its name),
  so it is safe to run while recording continues — even on today's date.
- **Never** deletes folders, and never reaches into `bin/` or `logs/`.
- Writes an audit record of everything it removed to the **delete log**
  (`E:\recording_qc\delete_log.json` + `.txt`).
- There is **no "delete everything" mode** — `-Date` is mandatory.

## The save check (default ON)

`-RequireSaved` defaults to `$true`. With it on, the day must appear in the save
log (`E:\recording_qc\save_log.json`, written by `copy_day_to_usb.ps1`) as a
successful save (`failed = 0`), or the script refuses and deletes nothing.

The save log is created by the **saving script**, `copy_day_to_usb.ps1`:

- A normal `copy_day_to_usb.ps1 -Usb F: -Date 2026-06-20` run records the day as
  saved automatically when the copy succeeds.
- If you **don't actually need to back the day up** but still want to clean it,
  flag it saved without copying:

  ```powershell
  copy_day_to_usb.ps1 -MarkSavedOnly -Date 2026-06-20
  ```

  This writes a `mark-only (NOT copied)` record to the save log so the delete is
  allowed. The log clearly marks it as not-copied, for honesty in the audit trail.

To delete without any save check (you intend to discard the footage):

```powershell
delete_day.ps1 -Date 2026-06-20 -RequireSaved:$false
```

## Usage

```powershell
# 1) ALWAYS preview first - shows exactly what would go and which days stay
delete_day.ps1 -Date 2026-06-20 -DryRun

# 2) Delete (asks you to re-type the date to confirm)
delete_day.ps1 -Date 2026-06-20

# Unattended (skip the confirmation prompt)
delete_day.ps1 -Date 2026-06-20 -Yes
```

Run with the full path if you're not in the folder:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\delete_day.ps1" -Date 2026-06-20 -DryRun
```

## Options

| Flag | Effect |
|---|---|
| `-Date 2026-06-20` | **Required.** The single day to delete (`yyyy-MM-dd`). |
| `-RequireSaved` | Default `$true`. Require a successful save-log record before deleting. `-RequireSaved:$false` to skip the check. |
| `-DryRun` | List what would be deleted and the save-check result; delete nothing. |
| `-Yes` | Skip the interactive "type the date to confirm" prompt. |
| `-SaveLog` | Path to the save log. Default `E:\recording_qc\save_log.json`. |
| `-SourceRoots` | Recorder roots to clean. Default `E:\Reolink_record`, `E:\thermal_record`. |

## Exit codes

- `0` — deleted successfully, or nothing matched (already clean).
- `1` — aborted at the confirmation prompt.
- `2` — refused (no save record, bad date) or one or more deletions failed.

## Typical flow

```powershell
# save the day to USB (records it in the save log)...
copy_day_to_usb.ps1 -Usb F: -Date 2026-06-20
# ...then reclaim the space, with the save check protecting you
delete_day.ps1 -Date 2026-06-20 -DryRun
delete_day.ps1 -Date 2026-06-20
```
