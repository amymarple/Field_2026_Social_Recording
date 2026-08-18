# UltraMic384K audio recorder

`ultramic_record.ps1` (supervisor) + `ultramic_wasapi_capture.ps1` (capture engine)
are the **audio** counterpart to the camera recorders: they continuously record the
Dodotronic **UltraMic384K_EVO** USB ultrasound microphone at its **native
384000 Hz / mono / 16-bit** and write **hourly, clock-aligned WAV** files, one
folder per mic:

```
E:\ultramic_record\MIC01\MIC01_2026-07-17_20-00-00_to_21-00-00.wav   finished
E:\ultramic_record\MIC01\MIC01_2026-07-17_21-00-00.wav               still recording (no _to_)
```

## Fully independent of the camera pipeline

The two systems share **no components** and can run side by side as SYSTEM tasks:

| | cameras (video) | UltraMic (audio) |
|---|---|---|
| transport | RTSP over the network | USB (WASAPI) |
| capture engine | ffmpeg (`-c copy`) | embedded C# WASAPI client — **no ffmpeg at all** |
| supervisor | `rtsp_record.ps1` / `extra_cam_record.ps1` / `thermal_record.ps1` | `ultramic_record.ps1` |
| mutex | per-recorder `Global\...` mutexes | `Global\FieldUltraMicRecorder` (+ per-mic capture mutex) |
| scheduled task | per-recorder tasks | **Field UltraMic Recorder** |
| output root | `E:\Reolink_record`, `E:\thermal_record` | `E:\ultramic_record` |

The audio recorder never enumerates, kills, or interacts with ffmpeg processes or
video folders in any way; its (default-off) retention/disk-guard is scoped to its own
mic folders only. The video QC/copy/delete tooling (`*.mp4`-based) never sees the
audio files.

## Why WASAPI exclusive mode (measured on this PC, 2026-07-17)

The obvious ffmpeg route **cannot** record this mic at 384 kHz — this was measured,
not assumed:

| capture path | result with the connected `UltraMic384K_EVO 16bit r0` |
|---|---|
| ffmpeg DirectShow (`-f dshow`), any channel count | opens at **max 96000 Hz**; 192 k/384 k → I/O error; `sample_size 32` rejected (dshow is int16-max); left alone it negotiates 44100 Hz stereo |
| WASAPI **shared** mode (= Python `sounddevice` `dtype=float32`) | delivers the Windows "Default Format" of the endpoint — currently **48000 Hz / 2 ch float32** on this PC → everything ultrasonic silently discarded |
| WASAPI **exclusive** mode | opens the device at its self-declared native format: **384000 Hz / 1 ch / 16-bit PCM** ✔ verified: 5 s clip, spectrogram shows real energy across the full 0–192 kHz band |

Notes on formats:
- The mic's ADC is 16-bit (it's in the device name). Shared-mode/sounddevice
  `float32` is just the Windows engine's internal format — it holds no extra
  information from this hardware. `StoreFormat = 'int16'` (default) is therefore
  lossless and half the disk; `'float32'` is supported if an analysis tool insists
  (4 GB+ segments then auto-upgrade to RF64).
- Exclusive mode also locks the mic to the recorder while it runs — desirable for a
  dedicated field mic (nothing else can grab or reconfigure it mid-experiment).
- `Mode = 'auto'` tries exclusive and falls back to shared with a loud warning in the
  capture log; `'exclusive'` refuses to run degraded.

## How the supervisor behaves (same recipe as the camera recorders)

- One capture child per mic; hourly WAV segments split **on the clock hour**; the
  child finalize-renames `..._to_<end>.wav` on each rollover (the supervisor also has
  a backstop rename for segments left open by a crash/kill).
- Supervisor loop restarts a child that exits and stall-restarts one whose newest
  file stops growing for `StallSeconds` (default 240 s), read via a shared read
  handle (`Get-HandleLen` — `Get-ChildItem .Length` is stale for open files).
- Single-instance via `Global\FieldUltraMicRecorder`; each mic's capture child also
  holds `Global\FieldUltraMicCapture_<Name>` (exit code 3 = orphan from a crashed
  supervisor still recording — the new supervisor adopts it rather than double-pulling
  the device, and reaps it only if it stalls).
- Retention/disk-guard **OFF by default** (`RetentionDays = 0`, `MinFreeGB = 0`).

## Storage budget

384000 Hz × mono × 16-bit = 768 kB/s ≈ **2.76 GB/hour ≈ 66 GB/day**. Hourly int16
mono segments (~2.6 GiB) stay under the classic-WAV 4 GB limit; anything larger
(float32, longer segments) transparently becomes RF64.

## First-time setup

1. Plug in the mic and copy the example config:
   ```
   copy ultramic.config.example.psd1  E:\ultramic_record\ultramic.config.psd1
   ```
2. Check the device is visible (read-only; shows native + shared formats):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -ListDevices
   ```
3. Validate offline, then prove real capture:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -SelfTest
   powershell -NoProfile -ExecutionPolicy Bypass -File ultramic_record.ps1 -TestClip 5
   ```
   `-TestClip` writes one short finalized clip per mic into its folder; check the
   capture log line `capture mode: EXCLUSIVE` and delete the clip after.
4. Install the 24/7 task (elevated Administrator PowerShell):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install_ultramic_task_system.ps1 -RunNow
   ```
   Registers SYSTEM task **Field UltraMic Recorder** (starts at boot, self-heals
   every 5 min via the mutex). Give it ~15 s, then watch `E:\ultramic_record\MIC01`
   for a growing `.wav`.

## Flags

| flag | what it does |
|------|--------------|
| `-ListDevices` | list WASAPI capture endpoints with native + shared formats (read-only) |
| `-SelfTest`    | offline: config parses, capture script present, root writable, prints per-mic launch commands, checks `_to_` rename logic — **no device access** |
| `-DryRun`      | same checks, then exit (alias in spirit of the other recorders' flag) |
| `-TestClip N`  | record one `N`-second clip per mic and report the file (opens the device) |

`ultramic_wasapi_capture.ps1` can also be run standalone (see its comment header)
with `-Device/-OutDir/-Prefix/-SegmentSeconds/-Seconds/-StoreFormat/-Mode`.

## Verified on this PC (2026-07-17)

- 5 s exclusive-mode clip: `pcm_s16le, 384000 Hz, mono`, peak −11 dB / RMS −36 dB,
  spectrogram shows genuine broadband content and tonal components up to the
  ultrasonic band (no 24/48 kHz wall — i.e. not resampled audio).
- Segment rollover at a clock boundary produces correct `_to_` finalized files.
- Camera recorders unaffected throughout (no ffmpeg involvement; the video tasks
  were stopped post-experiment during testing, and the audio path never touches them).

## Adding a second mic (no interruption to the running one)

The supervisor is multi-mic by design: one capture child, mutex, folder, and log per
`Streams` entry. Because the supervisor reads its config **once at startup**, and
because a restarted supervisor **adopts** still-running capture children via their
mutexes instead of respawning them, a new mic can be added without losing a sample
from the existing one:

1. Plug the new mic into its own USB port (direct — no passive extensions; one
   killed MIC01 twice in cohort 1).
2. `ultramic_record.ps1 -ListDevices` → copy the new endpoint's **exact full name**.
   (A second identical UltraMic shows up as `Microphone (2- UltraMic384K_EVO 16bit r0)`.
   Device matching prefers exact names precisely for this case — set BOTH entries
   to exact names once two mics share a substring.)
3. Add/uncomment the `MIC02` entry in `E:\ultramic_record\ultramic.config.psd1`.
4. Kill **only the supervisor** (the powershell process running `ultramic_record.ps1`
   — not `ultramic_wasapi_capture.ps1`), then immediately
   `Start-ScheduledTask 'Field UltraMic Recorder'` from an elevated shell. Do NOT
   rely on the task's 5-min self-heal here: the surviving capture children keep the
   task instance counted as "running", so `IgnoreNew` suppresses the tick (observed
   2026-08-16). The new supervisor re-reads the config, **adopts** the running
   captures via their mutexes (zero interruption — verified live), and starts the
   new mic. While the supervisor is down, the alive-check can false-page a mic as
   stalled (open-file age metadata only refreshes when the supervisor probes it);
   it self-clears when the new supervisor starts.
5. Verify `E:\ultramic_record\MIC02` grows and `logs\MIC02.capture.log` says
   `capture mode: EXCLUSIVE`. The alive-check discovers `MIC*` folders automatically.

Storage note: each 384 kHz mic adds ~66 GB/day.

## Caveats

- The capture child needs the mic present; if the USB device disappears the child
  exits and the supervisor retries every ~15 s until it's back.
- Exclusive mode requires "Allow applications to take exclusive control" (on by
  default) on the endpoint; if someone disables it, `auto` falls back to shared and
  the capture log warns loudly — check the log after any Windows audio changes.
- Audio segments are **not** picked up by the MP4-based video QC tools — that
  isolation is intentional. Say the word if you want a WAV-aware continuity/coverage
  check added.
