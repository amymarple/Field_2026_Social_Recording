# Overexposure / near-black QC with Slack alerts

`overexposure_check.ps1` grabs **one recent frame per Reolink channel**, measures its
exposure, and Slack-alerts (channel **+** DM to Hongyu in **AYAlab**) when a frame is
**OVEREXPOSED** (blown-out / sun glare) or **NEAR-BLACK** (covered lens / dead feed).

## The safety guarantee (how it reads frames)

It **never opens the camera/NVR RTSP streams** and **never risks the live recording**.
Frames always come from the files on disk:

- **Finished mode (default, every hour):** reads only the newest **completed** hourly
  file (name contains `_to_`). Zero interaction with any file being written.
- **Active mode (sunrise window only, 08:10/08:30/08:50):** reads one recent frame
  from the **currently-recording** fragmented-MP4 using the **same read-only shared
  handle** the recorder itself uses (`Get-HandleLen` in `rtsp_record.ps1`). It:
  - snapshots the file length **once** and treats that as the only trusted end,
  - copies out **only complete `moof`+`mdat` fragments** that end at/before that
    length (never assumes the tail is complete), preferring the **second-to-last**,
  - runs ffmpeg on that tiny temp clip — never on the growing file itself,
  - has a **hard 5 s timeout** and, on *any* uncertainty (no complete fragment,
    unparseable, timeout, locked), **fails fast and falls back** to the newest
    finished file.

Verified on the live rig: active sampling pulled a fresh frame from all 6
still-recording files in ~5 s with all 10 recorders untouched and the files still
growing.

## One-time setup

1. **Create the config** (holds the Slack token, kept out of git):
   copy `overexposure.config.example.psd1` to
   `E:\recording_qc\overexposure.config.psd1` and fill in `SlackBotToken` +
   `SlackChannels` (a channel id and Hongyu's user id). See the comments in the
   example for how to get a bot token (scopes `chat:write`, `im:write`) and the ids.
2. **Test Slack:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File overexposure_check.ps1 -TestSlack
   ```
   Confirm the test message arrives in the channel **and** as a DM.
3. **Install the scheduled tasks** (elevated Administrator PowerShell):
   ```powershell
   powershell -ExecutionPolicy Bypass -File install_overexposure_check_task_system.ps1 -RunNow
   ```
   This registers two SYSTEM tasks:
   - **Field Overexposure Check (Finished)** — `-Mode Finished`, hourly all day.
   - **Field Overexposure Check (Sunrise Active)** — `-Mode Active`, at 08:10/08:30/08:50.

## Running by hand

```powershell
# logic self-test (no disk / ffmpeg / Slack)
overexposure_check.ps1 -SelfTest

# preview metrics for every channel; no Slack, no state/log writes
overexposure_check.ps1 -Mode Finished -DryRun
overexposure_check.ps1 -Mode Active   -DryRun     # safe to run during recording
```

`-Mode Auto` (the default for ad-hoc runs) picks Active inside the sunrise window,
else Finished. The scheduled tasks always pass an explicit `-Mode`.

## What counts as a problem

For each channel the downscaled frame yields `mean luma`, `saturated_ratio`
(fraction of pixels at/above `SatLuma`), and `dark_ratio`. A channel is:

- **OVEREXPOSED** if `saturated_ratio >= SatRatioThresh` (default 0.20) **or**
  `mean >= MeanHighThresh` (default 235);
- **NEAR_BLACK** if `dark_ratio >= DarkRatioThresh` (default 0.98) **or**
  `mean <= MeanLowThresh` (default 12).

Tune these in the config against the logged values. (On first live run, a genuinely
sun-glared CH03 showed `sat 38%, mean 213` and was flagged, while normal channels sat
at `sat 0–17%, mean 120–175`.)

## Alerts & no-spam

State is kept in `E:\recording_qc\overexposure\state.json`. A Slack alert is sent when
a channel **changes** into a bad state, or it's still bad and `RealertHours` (default
6 h) have passed — so you don't get hourly repeats. When a channel recovers, a one-line
"back to normal" note is sent (`SendRecovery`). DMs are delivered by resolving the user
id through `conversations.open` first, then `chat.postMessage`.

## Outputs (under `E:\recording_qc\overexposure\`)

| File | Contents |
|---|---|
| `overexposure_log.json` / `.txt` | every check: channel, time, mode, metrics, status |
| `CHxx_<ts>_<STATUS>.jpg` | the offending frame, saved **only** when a channel is flagged |
| `state.json` | per-channel last status + last alert time (de-dup) |

## Exit codes

`0` = ran, nothing flagged · `1` = at least one channel flagged · `2` = error
(e.g. ffmpeg missing).

## Notes / scope

- Only the **6 visible Reolink channels** (`E:\Reolink_record\CHxx`). Thermal cameras
  are out of scope (their sensor frames use a palette, not RGB clipping).
- Active sampling runs **only** in the 08:00–09:00 sunrise window, not all day.
- ffmpeg is reused from `E:\Reolink_record\bin\ffmpeg.exe` (falls back to PATH).
- Image attachment is best-effort and **off by default** (`UploadImage`); the text
  alert with metrics is always the primary, reliable notification.
