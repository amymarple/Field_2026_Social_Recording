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

| Setting | CH07 | CH08 |
|---|---|---|
| Resolution | 1280×720 (720p) | 1280×720 (720p) |
| Frame-rate setting | 10 fps | 10 fps |
| Shutter (exposure) | **1/6 s** | **1/10 s** |
| **Effective frame rate** (exposure-limited) | **~6 fps** | **~8–10 fps** |
| Gain | 90 | 90 |
| 3D NR (noise reduction) | **OFF** | **OFF** |
| White balance — Red gain | 24 | 24 |
| White balance — Blue gain | 10 | 10 |
| Color mode | Color vision (not B&W) | Color vision (not B&W) |
| Day/Night schedule | Night 20:15–05:15 | Night 20:15–05:15 |

Resulting stream: HEVC, 720p, **~0.7 Mbps each** (~0.3 GB/day for both — negligible).

## Rationale / caveats (updated 2026-07-08)

- **Exposure caps the real frame rate** (max fps ≈ 1 / exposure). Even though both cameras are
  *set* to 10 fps, the long exposures limit actual delivery: CH07's **1/6 s → ~6 fps** (verified
  `6 tbr` via ffprobe), CH08's **1/10 s → ~8–10 fps**. To get a true 10 Hz you need shutter ≤ 1/10
  (a dimmer image). The longer CH07 exposure was chosen for the **brightest static sleep image**,
  accepting the lower rate — fine for immobility/sleep, where frame rate barely matters.
- **3D NR removed** (was 21). 3D noise reduction is *temporal* — it averages consecutive frames,
  which over-blends on moving rats and produces motion blur / ghost trails. It only helps a
  **static** image; with animals moving it hurts. Turned OFF on both.
- **Not an IR camera + dark box** → long exposure + high gain (90) are needed for a usable image;
  this motion-blurs moving animals but is fine for **sleep/immobility**. Color vision kept (no IR
  illuminator).
- **~6–10 Hz / 720p is sufficient** for the intended use (sleep, rest/active bouts, gross activity,
  in-box position, social proximity). NOT enough for fine/fast behaviors (grooming microstructure
  ~5–7 Hz, whisking) — those would need an IR illuminator + faster shutter + higher fps.
