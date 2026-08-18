# Encoder bitrate experiment — fix capped-keyframe bottom-band loss

**Started:** 2026-07-09 evening (field-PC time) · **Owner:** Hongyu Chang
**State:** CHANGE APPLIED — awaiting first full daytime (2026-07-10) to evaluate

---

## Root cause (verified 2026-07-09)

- CH01/CH02 = **Reolink Duo 3**, dual-lens stitched panorama, HEVC Main, **2160×7680 (16.6 MP)**,
  ~9.4 Mbps, ~2 s GOP.
- The camera encoder **truncates the bottom slices of any intra keyframe (IDR) that exceeds a
  ~2,000,000-byte cap** (byte-level verified). HEVC codes top→bottom, so the *bottom* of the frame
  is what gets dropped.
- **Daytime** keyframes (high detail) exceed the cap → bottom band dropped for the whole capped GOP.
  **Night** keyframes (~1.1 MB) fit → no loss.
- **Impact (baseline, CBR 10044):** ~**41%** of the 17:00 hour, ~**20.6%** at noon, **0%** at night.
- **Why playback hid it:** VLC/GPU (D3D11VA) fills the dropped band with **recycled decoder-surface
  memory** — a real frame from ~0.1–0.4 s earlier — so on a static scene it looks pixel-perfect
  (watermark, walkway, all present) but is **stale, not from that frame**. Software decode and
  single-frame ffmpeg grabs show the dropped band as black/smear (the truth). This is also the
  original "20% of the frame is black on cold seek, loads after scrubbing" symptom: scrubbing just
  refilled the surface pool.
- **The recorder uses `ffmpeg -c copy`** → it copies the camera's bytes verbatim and **cannot repair
  this**. The fix must be at the **camera encoder**.

## Change applied (2026-07-09)

| | Before | After |
|---|---|---|
| Bitrate mode | **CBR** (constant) | **VBR** (variable) |
| Max bitrate | **10044 kbps** | **12288 kbps** |
| Resolution / fps / color / codec | 2160×7680 · ~20 fps · color · HEVC | *(unchanged)* |

**Channel(s) changed:** CH01 **and** CH02 (both). No built-in control → evaluate **before/after**
vs the 2026-07-09 CBR-10044 baseline below (pick a clear-sky daytime hour to limit the weather/
scene-complexity confound).

**Verified live (2026-07-09 ~23:35):** change applied **on the fly, no stream drop / no recording
gap** (no recorder restart logged). Whole-hour bitrate fell from the flat CBR ~10.3 Mbps to
**6.64 Mbps (CH01) / 7.01 Mbps (CH02)** during the 22:00 hour → VBR confirmed active on both. A
post-change night frame decodes clean and full (watermark present). Night doesn't test the cap
(night keyframes already fit) — **daytime 07-10 is the real check.** Side effect: night files
shrank ~4.2 GB → ~2.8 GB (storage bonus); daytime VBR will spike *up* toward 12288 (the desired
bigger-keyframe behavior, and the bandwidth/stall risk to watch).

## Hypothesis

The 2 MB truncation is a **CBR VBV/buffer artifact, not a hard encoder limit**. In VBR the keyframe
is allowed to spike toward the ceiling, so the **full-height keyframe should pass through without
raising QP → fixed with no quality loss** (better than lowering quality/resolution).

## Risk to watch

Higher VBR peaks = larger keyframe bursts = more peak bandwidth → could **worsen the CH01–03 RTSP
stalls** (recorder `stalled (no growth for 240s); killing to restart`). Must confirm stall/restart
counts do **not** rise.

---

## Experiment (2026-07-10)

Compare on matched hours — **use FILENAME time** (NVR OSD clock runs ~1 h behind the PC):

1. **Keyframe size (MB) + capped-KF %** at a bright hour (~17:00), noon (~12:00), one night (~02:00).
2. **Before/after** (both cams changed, no control): CH01+CH02 on 07-10 vs the 07-09 CBR-10044
   baseline. Match a clear-sky daytime hour to limit the weather confound.
3. **Stall/restart events** per channel from `recorder.log`.

### Decision rule
- Day keyframes now **>2 MB AND full-height** (no dead bottom) → **VBR fixed it losslessly.** Keep it;
  roll out to CH02/CH03/CH04.
- Keyframes still **hard-stop at ~2,000,000 B with a dead bottom** → it's a hard cap; VBR won't help →
  fall back to **lower resolution/quality** until keyframes < 1.9 MB.
- Accept only if **no rise in stall events**.

### Baseline (CBR 10044, 2026-07-09) — capped-KF
| hour | capped-KF |
|---|---|
| 17:00 | 41% |
| noon | 20.6% |
| night | 0% |

### Results (measured 2026-07-11 ~14:15, 40 s keyframe windows + visual bottom-band checks)

**Cap value pinned exactly: 2,000,090 bytes** (identical repeated packet size — hard encoder limit).

| sample | keyframes at/near cap | bottom band (software decode = truth) |
|---|---|---|
| CH01 07-10 **17:00** (post-change, bright) | **7/20 at exactly 2,000,090** + 4 more ≥1.95 MB | **still broken** — ragged truncation ~45% down, watermark cut mid-text |
| CH01 07-11 **13:00** | **0/20** capped (max 1.77 MB) | **fully intact** — walkway + complete watermark |
| CH02 07-11 **13:00** | **1/20** at exactly 2,000,090 (max others 1.92 MB) | at the capped KF only a **~200 px sliver** lost at the very bottom (vs ~55% of frame pre-change) — near-fitting keyframes truncate far less |

**Stalls:** 07-06/07/08 = 0 · 07-09 = 28 (began 14:00, *before* the change) · 07-10 = 48 · **07-11 = 0**
→ the stall burst is **not attributable to VBR** (started pre-change, ended while VBR active); it was an
environmental/network episode that cleared. Zero stalls in the last ~24 h with VBR live.

**Storage bonus:** daytime hours 4.2 GB → ~2.5–2.8 GB; night ~2.8 GB (VBR).

### Deep-dive: CH01 07-10 17:00 damage profile (measured 2026-07-11)

Full-file keyframe scan (795 KFs / 71,034 packets) + per-row texture analysis of sampled capped
keyframes (cv-env numpy; intact 07-11 13:00 reference measures 99% textured = method baseline):

| window | GOPs capped | **time** inside damaged GOPs | frame area lost when capped |
|---|---|---|---|
| first 10 min | 78/138 (56.5%) | **80.0%** (480/600 s) | ~**8–13%** of frame height (592–965 rows) |
| last 10 min | 67/86 (**77.9%**) | **93.5%** (546/584 s) | ~**22%** of frame height (1,653–1,733 rows) |
| whole hour | 445/795 (56.0%) | **80.5%** (2,891/3,592 s) | grows through the hour |

- Smart encoding stretches GOPs (2 s → up to **78 s**; minute 42 has zero keyframes), so one truncated
  keyframe poisons long stretches — that's why time-damage ≫ KF-count damage.
- Cut depth grows toward evening (low sun = more detail per frame): early-hour caps cut ~600–950
  bottom rows, late-hour caps cut ~1,700 (matches the original "20% of the frame" symptom).
- Affected area = bottom of the panorama (walkway/wall strip nearest the camera + watermark zone):
  any rat there during a capped GOP is stale/phantom data for CV.

### Step 2 (2026-07-11 ~14:52): VBR max lowered 12288 → 8192, CH01 + CH02

07-10 17:00 proved VBR@12288 still caps at golden hour, so the quality target was stepped down
**before** today's bright evening. Verified live in the 14:00–15:00 file (change lands mid-file,
no restart/gap):

| CH01 | mean KF | max KF | capped/5 min |
|---|---|---|---|
| 14:00–14:50 (VBR 12288) | 1.6–1.9 MB | pinned at 2,000,090 | 11–45 ❌ |
| 14:55–15:00 (VBR 8192) | **1.00 MB** | **1.42 MB** | **0** ✅ |

CH02 identical (1.03 / 1.42 / 0). Post-change keyframes carry ~30% headroom below the cap in full
afternoon sun, and GOP cadence returned to a steady 2 s (150 KFs/5 min — long capped GOPs gone).
**Decisive test: today's 17:00–18:00 hour** (golden-hour complexity adds ~10–30% → worst case
~1.85 MB, should still clear). Scan after 18:00.

### FINAL VERDICT (2026-07-11 18:05, after the peak-hour test)

Settled settings: **CH01 + CH02 main stream = VBR, max 8192 kbps, resolution/fps/color unchanged
(2160×7680 @ ~20 fps HEVC).** The 2,000,090-byte IDR cap is a hard firmware limit that no bitrate
mode lifts; the fix is keeping the encoder's *desired* keyframe size under it.

Peak hour (17:00–18:00) before vs after, worst channel:

| | 07-10 (VBR 12288) | **07-11 (VBR 8192)** |
|---|---|---|
| time inside damaged GOPs | **80.5%** (2891 s) | **CH01 1.7% (60 s) · CH02 5.4% (194 s)** |
| frame area lost when capped | 8→23% (grows to evening) | **~7.7%** (593 rows, thin bottom strip) |
| GOP length | stretched to 78 s | steady 2 s (1800 KFs/hour) |
| expected bottom-strip pixel-time loss | ~12% | **~0.1–0.4%** (≈30–90× reduction) |

- Residual: a few % of evening GOPs still cap (CH02 runs hotter: mean 1.56 MB, 365 KFs ≥1.9 MB —
  thin margin on complex windy/sunny evenings). Each event costs ~2 s × bottom ~600 rows and CV
  masks it via `find_capped_gops()` / `CAPPEDGOP_` labels. **Accepted.**
- If daily monitoring shows bad evenings creeping back (>10–15% capped), step CH02 (or both) down
  once more (8192 → 6144) before considering any resolution change.
- Night bonus: files ~4.2 → ~2.8 GB/h; midday ~2.5–2.8 GB/h (≈35% storage saving).
- DONE (2026-07-11): daily regression monitor built — `capped_keyframe_check.ps1` +
  `install_capped_keyframe_check_task_system.ps1` (SYSTEM task, daily 05:20, scans yesterday's
  CH01/CH02 hours 12/16/17, Slack alert at >=10% capped). See `README_capped_kf.md`.
  Verified: SelfTest PASS; dry-run flags 07-10 17:00 (56%), stays quiet on 07-11 17:00 (1.7/5.4%);
  test DM delivered.

### Step 3 (2026-07-18 ~13:00): dusk regression at 8192 → A/B test, CH01=6144 vs CH02=7168

24 h test run (07-17) showed VBR 8192 is NOT robust at dusk: 19:00 = **60.5% / 46.6%** capped
(CH01/CH02), 20:00 = 49.9% / 33.5%, dusk mean KF 1.78–1.89 MB (riding the cap). A week earlier the
same setting measured only 8–15% — normal scene variation (vegetation growth, clearer sky) eats the
margin. History also shows dawn (07-12 05:00) at 18–22%: both gain-ramps cap.

**Change (applied ~13:00, on the fly): CH01 max → 6144, CH02 max → 7168** — deliberate A/B in the
same paddock/dusk. Caveat: CH02 historically runs ~1.2–1.5× hotter than CH01 at equal settings.
Decision rule on tonight's 19:00/20:00 scan (05:20 task, or on-demand after 21:00):
- both ≈0% → 7168 suffices → raise CH01 to 7168 (keep the quality).
- CH01 clean, CH02 >10% → 6144 is the number → drop CH02 to 6144.
- CH01 also >10% → step both to 4096 and reconsider 3D-NR / resolution.
Test-day footage (07-17) was deleted after analysis (test data, save-log mark-only + delete_day).

**CLOSED (2026-07-19 ~14:05): FINAL SETTINGS = CH01 + CH02 both VBR max 7168 kbps**, resolution/
fps/codec untouched (2160×7680 @ ~20 fps HEVC). The full-day A/B (07-18 dusk + 07-19 dawn/morning/
noon/afternoon, all zero caps on the hotter CH02@7168) justified raising CH01 from 6144. The daily
05:20 capped-KF monitor (alert >=10%) remains the standing tripwire; 6144 is the proven fallback.

**A/B RESULT (2026-07-18 dusk, scanned ~21:20): both PASS with zero caps.**
| | CH01@6144 | CH02@7168 |
|---|---|---|
| 19:00 | 0/1800 capped, max 1.48 MB | 0/1799 capped, max 1.76 MB |
| 20:00 | 0/1800 capped, max 1.49 MB | 0/1800 capped, max 1.76 MB |
No keyframe ≥1.9 MB anywhere. Headroom below the 2,000,090-byte cap: CH01@6144 ≈ 22–25%,
CH02@7168 ≈ 8–12%. Since CH02 is historically the hotter camera and passed cleanly at 7168,
**recommendation: raise CH01 to 7168 too (both cams = VBR max 7168)** — best quality that the
worst-case camera has demonstrated safe, consistent encode across both panoramas for CV, with
the daily 05:20 capped-KF monitor (alert ≥10%) as the tripwire and 6144 as the proven fallback
if a complex evening ever fires it. Caveat: one evening of data; the monitor is the guarantee.

NOTE for tomorrow's 05:20 scan of 07-18: hours 05 and 12 were recorded BEFORE the ~13:00
change (still @8192) and may correctly report caps / fire one alert — that is historical
footage, not a regression. Only the 17/19/20 rows reflect the new settings.

### Dusk follow-up (2026-07-11 21:15): the residual hotspot is the DUSK GAIN-RAMP, not golden hour

19:00/20:00 scans under VBR 8192: CH01 7.8%/9.8%, **CH02 15.0%/14.2% capped** (peak 19:30–20:45,
CH02 up to 27% per 15 min; tapers when IR night mode kicks in ~20:45). Cause: fading light raises
sensor gain; gain noise is incompressible, keyframes swell, both cams ride the 8.4 Mbps ceiling.
Dawn should mirror this. Monitor default hours updated to **5, 12, 17, 19, 20**. Note dusk/dawn =
peak rat activity. Options if unacceptable: step max bitrate 8192 → 6144 (clears caps, slightly
clamps midday too since midday uses ~6.3 Mbps) or raise camera 3D-NR at dusk. Streams healthy:
zero stalls since 07-11 14:00.

### CH03–CH06 checked (2026-07-11 17:00 hour, same worst-hour scan) — NO issue, NO change needed

| ch | model | mean KF | max KF | cap signature |
|---|---|---|---|---|
| CH03 | RLC-1212A fisheye | 1.11 MB | 1.26 MB | none |
| CH04 | RLC-1212A fisheye | 0.96 MB | 1.10 MB | none |
| CH05 | RLC-520A shelter | 0.46 MB | 0.74 MB | none |
| CH06 | RLC-520A shelter | 0.62 MB | 0.73 MB | none |

No keyframe repeats byte-identically at a ceiling and nothing near 2,000,090 — worst keyframes sit
at 35–63% of the Duo 3 cap even at golden hour. Their existing (default/CBR) settings are healthy;
**leave CH03–CH06 untouched** — only the 16.6 MP Duo 3 panoramas ever outgrew the per-frame cap.

---

## Log snapshots

Raw operational logs are copied to **`logs/`** (gitignored) — see `logs/_manifest.txt`.
**Refresh them before evaluating** (re-run `copy_logs_here.ps1`) so the stall/keyframe tallies use
tomorrow's data, not tonight's.
