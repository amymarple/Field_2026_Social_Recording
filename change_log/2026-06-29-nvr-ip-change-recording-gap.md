# NVR IP Change — Recording Gap and Recorder Repoint

## Date

2026-06-29. Change is currently uncommitted.

## Summary

The Reolink NVR's IP address changed from `192.168.1.151` to `192.168.1.163`
during an on-NVR channel-order reconfiguration. The RTSP recorder, which targets
the NVR by IP, could no longer connect, so all six Reolink channels (CH01–CH06)
stopped recording until the recorder was repointed at the new address.

## Recording Gap (excluded interval)

- **Channels affected:** CH01–CH06 (Reolink only).
- **Gap:** ~15:00:42 → 17:46:20 local (**~2 h 46 m**) on 2026-06-29. Each channel's
  15:00 hourly file froze at ~16–35 MB and did not grow until the repoint.
- **Not affected:** thermal cameras (`192.168.1.108` / `.109`) and WISER UWB — these
  use separate addresses/paths and continued normally.
- Treat this interval as **missing video** for CH01–CH06 in any downstream analysis.

## Root Cause

Not a recorder or NVR hardware fault. The recorder was running the whole time and
its stall-watchdog was correctly killing/restarting ffmpeg every ~4 min — but the
target NVR was unreachable at `.151`. A channel reorder on the NVR had changed its
network address to `.163`. (`.151` stopped answering ping/RTSP; a LAN scan found the
NVR at `.163` — identified as the host serving `Preview_06_main`, since only the NVR
exposes a channel 6, whereas a standalone camera has only channel 1.)

## What Changed

- `E:\Reolink_record\recorder.config.psd1` (gitignored, on the field PC): `NvrIp`
  updated `192.168.1.151` → `192.168.1.163`, with an inline note.
- Recorder restarted via **Stop-ScheduledTask + Start-ScheduledTask**
  `-TaskName 'Reolink RTSP Recorder'` so the supervisor re-read the config (a running
  supervisor caches the old IP; `Restart-ScheduledTask` does not exist in this
  PowerShell — Stop then Start is required).

No repo code changed; this was an operational config fix.

## Side Effect

The on-NVR reconfiguration also **reset the CH01/CH02 microphone "Record Audio"
setting to OFF** (both measured −91 dB / digital silence afterward). The mics were
re-enabled on the cameras and re-verified (see Verification). See the prior audio
work referenced in project memory `ch01-audio-enabled`.

## Verification

Live RTSP probes via `E:\Reolink_record\bin\ffprobe.exe` / `ffmpeg.exe`:

- Located the NVR by scanning `192.168.1.140–.170` for an open port 554 host that
  serves `Preview_06_main` → `192.168.1.163`.
- After repoint + restart, all six channels wrote fresh files at 17:46 with
  last-write age 0–2 s and growing; `recorder.log` showed CH01–CH06 `started`;
  ffmpeg process count nominal.
- Audio (8 s `volumedetect` on the live stream, post mic re-enable):
  - CH01: mean −50.4 dB, max −30.2 dB.
  - CH02: mean −49.0 dB, max −28.8 dB.
  - (Both were −91 dB silent immediately after the NVR reconfig before re-enabling.)

## Follow-ups

- **Pending:** assign the NVR a **static IP or DHCP reservation** so its address
  cannot drift again. This incident's only root cause was the IP change; until the
  address is pinned, a recurrence is possible. If the NVR is set back to `.151`,
  revert the `NvrIp` config line.
- **Gap in QC coverage:** the daily continuity checks are video-only and would not
  flag a silently-reset microphone. A lightweight audio-level check on CH01/CH02
  (alert if they fall back to ~−91 dB) was proposed but not yet implemented.
