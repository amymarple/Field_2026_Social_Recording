# 2026-07-17 — UltraMic384K audio recorder (WASAPI, verified at 384 kHz)

## What
`ultramic_record.ps1` (supervisor) + `ultramic_wasapi_capture.ps1` (WASAPI capture
engine, embedded C# via Add-Type) + `install_ultramic_task_system.ps1` +
`ultramic.config.example.psd1` + `README_ultramic.md` — the **audio** counterpart to
the camera recorders, for the Dodotronic **UltraMic384K_EVO** USB ultrasound mic.
`.gitignore` gained `*.wav` / `*.flac`.

## Why not ffmpeg (all measured on the field PC with the connected mic)
- ffmpeg's only Windows audio input is DirectShow; this mic's dshow pin caps at
  **96 kHz** (384 k/192 k → I/O error; `sample_size 32` rejected; unforced open
  negotiates 44100 Hz stereo).
- WASAPI **shared** mode (= sounddevice `dtype=float32`) delivers only the Windows
  "Default Format" — currently **48 kHz/2 ch** on this PC.
- WASAPI **exclusive** mode opens the device at its self-declared native
  **384000 Hz / 1 ch / 16-bit PCM** → that's what the capture engine uses (Mode
  'auto' falls back to shared with a loud log warning). No OpenAL runtime and no
  real Python exist on this machine, so the engine is pure PS 5.1 + Add-Type C#
  COM interop (IMMDeviceEnumerator → IAudioClient → IAudioCaptureClient) — zero
  installs, zero downloads. Interop gotcha: `[PreserveSig]` on every method, or
  .NET auto-throws on failing HRESULTs and fallback logic never runs.

## Independence from the camera pipeline (user requirement)
Zero shared components: USB/WASAPI vs RTSP/ffmpeg, own mutex
(`Global\FieldUltraMicRecorder` + per-mic `Global\FieldUltraMicCapture_<Name>`),
own SYSTEM task **Field UltraMic Recorder**, own root `E:\ultramic_record` (video
QC/copy/delete tooling never sees it). Never enumerates or kills ffmpeg. The two
recording systems run side by side as SYSTEM scheduled tasks.

## Behavior
Hourly clock-aligned WAV segments, rig filename contract (`_to_` on finalize; child
renames on rollover, supervisor backstop-renames after a crash/kill). int16 storage
default (mic ADC is 16-bit; ~2.76 GB/h ≈ 66 GB/day); float32 optional; >4 GB
segments auto-upgrade to RF64 (JUNK→ds64 trick). Stall-watchdog via `Get-HandleLen`;
orphan capture from a crashed supervisor is **adopted** via its named mutex — NOT
exit codes, because PS 5.1 `Start-Process -RedirectStandardOutput` always returns
NULL `ExitCode` (measured) — and reaped only if it stalls. Retention/disk-guard OFF
by default and scoped to own folders.

## Verified live (2026-07-17, scratchpad output, all cleaned up)
- 5 s exclusive clip: ffprobe `pcm_s16le 384000 Hz mono`, peak −11 dB; spectrogram
  shows genuine broadband energy to 192 kHz (no resample wall).
- 60 s-segment run: splits exactly on clock boundaries, ~46.08 MB per 60 s (no
  sample loss), correct `_to_` renames, header durations parse (60.01 s).
- Supervisor: child killed → restarted ≤15 s, abandoned segment backstop-renamed;
  supervisor killed → new supervisor **adopts** the still-recording orphan (no
  double-pull); orphan killed → replacement child within one 15 s poll.
- Camera path untouched throughout (video tasks were already stopped post-experiment
  2026-07-12; audio path contains no ffmpeg).

## Deploy (user, on the field PC)
copy example config → `E:\ultramic_record\ultramic.config.psd1` (Device='UltraMic'
already matches) → `-ListDevices` / `-SelfTest` / `-TestClip 5` → elevated
`install_ultramic_task_system.ps1 -RunNow`.
