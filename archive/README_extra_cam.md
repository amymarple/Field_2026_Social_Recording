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

Final settings (2026-07-08), applied identically to **both** CH07 and CH08:

| Setting | Value |
|---|---|
| Resolution | **1280×720 (720p)** |
| Frame rate | **~6 fps** (exposure-limited; see below) |
| Shutter (exposure) | **1/6 s** |
| Gain | **60** (fixed 60–60) |
| Exposure compensation | 51 |
| Anti-flicker | Outdoor |
| 3D NR | **Level 0** (temporal NR disabled) |
| 2D NR | **50** (spatial NR) |
| White balance — Red / Blue gain | 24 / 10 |
| Color mode | Color vision (not B&W) |
| Day/Night schedule | Night profile **20:15–05:15**; Day otherwise |

Resulting stream: HEVC, 720p, **~0.67 Mbps each** → **~300 MB/hour, ~7 GB/day per camera**
(~14 GB/day for both). Verified via 60 s live captures 2026-07-08.

## Rationale / caveats (final 2026-07-08)

- **Frame rate is exposure-limited.** Max fps ≈ 1 / exposure, so the 1/6 s shutter caps both
  cameras at **~6 fps** regardless of the 10 fps setting (verified `6 tbr` via ffprobe). Both were
  normalized to 1/6 for a matched ~6 fps. 6 Hz is ample for sleep/rest/activity scoring.
- **Noise, not resolution/fps, drives file size.** 3D NR (temporal) was disabled because it
  averages consecutive frames → motion blur / ghost trails on moving rats (only helps a static
  image). With it off, raw sensor grain hit the encoder and the bitrate jumped ~0.67 → ~1.5–1.75
  Mbps (~600–700 MB/hour). Fixed **without** re-introducing temporal blur by lowering **gain
  90 → 60** (less noise at source) and raising **2D NR → 50** (spatial NR cleans grain per-frame,
  no cross-frame averaging). That brought it back to **~0.67 Mbps / ~300 MB/hour**. (Gain 65 vs 60
  made no measurable size difference — 2D NR is doing the cleanup; the floor is real scene content.)
- **Residual motion blur on *moving* animals is the 1/6 s exposure itself, not NR** — each frame
  integrates 166 ms of motion. Unavoidable in a dark box without IR; irrelevant for still sleep.
- **Not an IR camera + dark box** → long exposure + gain are needed for a usable image; color
  vision kept (no IR illuminator). A true 10 Hz + sharp motion would require an IR illuminator +
  faster shutter.
- **~6 Hz / 720p is sufficient** for the intended use (sleep, rest/active bouts, gross activity,
  in-box position, social proximity). NOT enough for fine/fast behaviors (grooming microstructure
  ~5–7 Hz, whisking) — those would need IR + faster shutter + higher fps.
- To shrink files further if ever needed, cap the camera's encode **Bit Rate** (Stream → Encode),
  not the gain.
