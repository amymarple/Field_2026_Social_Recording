# Storage failover recorder (E: → D:)

`failover_recorder.ps1` keeps RTSP capture alive if the **primary recording drive
`E:`** (a WD Purple HDD — the same line that just failed in the NVR) dies. It is a
**separate** recorder with its own task and mutex — it does **not** modify or share
code with `rtsp_record.ps1`.

## How it behaves

- **While `E:` is healthy → DORMANT.** It only write-probes `E:` every ~15 s and pulls
  no streams. Zero effect on the running primary recorder. (So even installing it is safe.)
- **If `E:` becomes unwritable** (write-probe fails `-ProbeFailsToTrip` times in a row,
  default 4 ≈ 60 s — a *disk* test, independent of "files not growing", so an RTSP/NVR
  outage will **not** trip it), it:
  1. **Slack-alerts** (🚨 STORAGE FAILOVER),
  2. **stops the primary recorder task** (which is now writing to a dead disk anyway), and
  3. **records all channels to `D:\Reolink_record\CHxx`** itself (same hourly fragmented-MP4
     naming), using ffmpeg + config + Slack creds **mirrored onto `D:`**.
- **`D:`** is a 4 TB NVMe SSD (~3.7 TB free) → **~23 days** of runway at ~160 GB/day.
- **Failback is MANUAL** — once on `D:` it stays there (no drive flapping).

## Install (elevated Administrator PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\install_failover_recorder_task_system.ps1" -RunNow
```

This **mirrors** to `D:` (so an `E:` death can't take them down too):
`ffmpeg.exe` → `D:\Reolink_record\bin\`, the recorder config → `D:\Reolink_record\`,
and the Slack creds → `D:\recording_qc\`. Then it registers the SYSTEM task
**Field RTSP Failover Recorder** (starts at boot, runs continuously, dormant while `E:` is fine).

> Re-run the installer whenever you change `recorder.config.psd1` or the Slack config,
> to refresh the `D:` mirror. Safe to run anytime — it does not restart the primary.

## Test it (no disruption)

```powershell
$fo = "C:\Users\Cornell\Documents\GitHub\Field_2026_Social\reolink_record\failover_recorder.ps1"
& $fo -SelfTest     # offline probe + naming logic
& $fo -Once         # read-only: prints E: writable? + failover state, takes no action
& $fo -TestSlack    # send a test alert to the channel + your DM
```

## When `E:` actually fails
You'll get the Slack alert; the primary task stops and recording continues to
`D:\Reolink_record`. Log + state live in `D:\recording_qc\failover_recorder.log` /
`failover_state.json`.

## Failback (manual, after `E:` is repaired/replaced)

1. Fix `E:` (new drive, remounted, and `E:\Reolink_record\...` writable again).
2. Stop the failover recorder and its streams:
   ```powershell
   Stop-ScheduledTask -TaskName 'Field RTSP Failover Recorder'
   Get-CimInstance Win32_Process -Filter "Name='ffmpeg.exe'" |
     Where-Object { $_.CommandLine -like '*D:\Reolink_record*' } |
     ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```
3. Clear the failover flag: `& failover_recorder.ps1 -Reset`
4. Restart the primary recorder: `Start-ScheduledTask -TaskName 'Reolink RTSP Recorder'`
5. Move/merge the footage that landed under `D:\Reolink_record\` back to `E:` (or back it
   up) as you see fit — it's named exactly like the normal recordings.

## Caveats
- Recording lands on `D:` (SSD) during failover; monitor `D:` free space if the outage runs
  long (23-day runway). The disk-space warning currently watches `E:` — tell me if you want
  it to watch `D:` too while failover is active.
- The failover reads NVR creds/channels from the **`D:` mirror**; if you change the primary
  config, re-run the installer so the mirror stays current.
