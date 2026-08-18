# 2026-08-16 — Second-mic prep: exact device matching + staged MIC02 config

## Why
A second USB mic (hardware not yet connected) will join MIC01. If it is another
UltraMic, Windows names it `Microphone (2- UltraMic384K_EVO 16bit r0)` — and MIC01's
old `Device = 'UltraMic'` substring would then match BOTH endpoints, blocking MIC01
capture restarts with "matches 2 capture devices".

## Changes (all inert to the live recording: the supervisor reads config once at
## startup, and running processes never reload scripts from disk)
- `ultramic_wasapi_capture.ps1` `FindDevice`: EXACT friendly-name match (case-
  insensitive) now wins before the substring path; multiple matches still error
  rather than silently picking (a wrong pick after a reboot would record the wrong
  mic into a folder). Verified via `-ListDevices` (compiles, enumerates, exact-match
  path exercised by SelfTest's would-launch line).
- Live `E:\ultramic_record\ultramic.config.psd1`: MIC01 `Device` hardened to the
  exact full name; commented MIC02 template + 4-step activation runbook added.
  Config re-parsed + supervisor `-SelfTest` PASS; MIC01 file growth verified
  unchanged (768 kB/s) after all edits.
- `ultramic.config.example.psd1` + `README_ultramic.md`: same guidance, plus the
  zero-interruption activation procedure (kill ONLY the supervisor; the task's
  5-min self-heal restarts it; the new supervisor adopts MIC01's running capture
  via `Global\FieldUltraMicCapture_MIC01` and spawns MIC02's).

## Activation outcome (same day, 16:29)
The second mic turned out to be an **UltraMic 250K 16 bit r4** (native 250000 Hz /
1 ch / 16-bit — different name, but exact-match still the right hygiene). Activation
verified live:
- kill supervisor → **the 5-min self-heal tick did NOT relaunch it**: the surviving
  capture child keeps the task instance counted as "running", so `IgnoreNew`
  suppresses new launches. `Start-ScheduledTask` (elevated) is REQUIRED after the
  kill — runbook in README/config corrected accordingly.
- new supervisor: `2 mic(s) [MIC01,MIC02]`, **adopted MIC01's running capture via
  its mutex (zero interruption — MIC01's open segment never stopped growing)**, and
  started MIC02: `device (exact)` match, EXCLUSIVE at native 250 kHz, growth at the
  nominal 500 kB/s (~1.8 GB/h, ~43 GB/day).
- Side-finding: while the supervisor is down, `recording_alive_check` false-paged
  MIC01 as stalled — an open file's LastWriteTime only refreshes when something
  probes it (normally the supervisor's 15 s `Get-HandleLen`); cleared itself on
  supervisor start. The alive check now covers 14 groups (MIC02 auto-discovered).
