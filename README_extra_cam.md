# Extra In-Box Sleep Cameras — CH07 / CH08

Two single-lens direct-IP (Dahua/EmpireTech-format) cameras placed **inside the home box** to
record sleep/rest directly. They exist because CH05/CH06 view the shelter **through an IR
window**, and fog/condensation on that glass is hard to solve — these bypass the glass.

Recorded by a **separate recorder** (`extra_cam_record.ps1`, own mutex + SYSTEM task) into the
same root as the Reolink footage, as CH07/CH08, so the existing QC / stall-alarm / copy tooling
picks them up automatically. See `extra_cam_record.ps1` and `install_extra_cam_task_system.ps1`.

## Cameras

| Channel | IP | Recorder output | Network segment |
|---|---|---|---|
| CH07 | `192.168.1.110` | `E:\Reolink_record\CH07` | IP-Camera NIC (.20) |
| CH08 | `192.168.1.111` | `E:\Reolink_record\CH08` | WISER NIC (.10) — verified no impact on WISER sampling |

- Format: Dahua-style RTSP `rtsp://<user>:<pass>@<ip>:554/cam/realmonitor?channel=1&subtype=0`
  (channel 1 main; channel 2 / thermal returns 403 — visual-only cameras).
- **Credentials are NOT stored in this repo** — they live only in
  `E:\Reolink_record\extra_cam.config.psd1` on the field PC (off-repo, like the other recorder configs).

## Finalized imaging settings (2026-07-07)

Applied identically to **both** CH07 and CH08:

| Setting | Value |
|---|---|
| Resolution | **1280×720 (720p)** |
| Frame rate / sampling | **10 fps (10 Hz)** |
| Shutter (exposure) | **1/10 s** |
| Gain | **90** |
| 3D NR (noise reduction) | **21** |
| White balance — Red gain | **24** |
| White balance — Blue gain | **10** |
| Color mode | **Color vision** (not B&W) |
| Day/Night schedule | **Night profile 20:15–05:15** (8:15 pm–5:15 am); Day otherwise |

Resulting stream: HEVC, 720p, 10 fps, **~0.7 Mbps each** (~0.3 GB/day for both — negligible).
Verified live + in the recorded files 2026-07-07 ~22:54 (recorder auto-reconnected through the
setting change; files before that boundary are the earlier 1440p/20fps).

## Rationale / caveats

- **Not an IR camera + dark box** → a longish 1/10 s exposure + high gain (90) are needed to get a
  usable image. Long exposure motion-blurs *moving* animals, but for **sleep/immobility** (still
  animals) that is fine. Color vision is kept (no IR illuminator).
- **10 Hz / 720p is sufficient** for the intended use (sleep, rest/active bouts, gross activity,
  in-box position, social proximity). It is NOT enough for fine/fast behaviors (grooming
  microstructure ~5-7 Hz, whisking) — those would need an IR illuminator + faster shutter + higher
  fps.
- A 1/10 s shutter caps the achievable frame rate at ~10 fps by definition (max fps ≈ 1/exposure).
