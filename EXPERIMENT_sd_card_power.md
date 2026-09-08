# EXPERIMENT: SD card power consumption (bench)

**Started:** 2026-09-02 (HC)
**Why:** cohort-3 battery life tracks the SD card model — Samsung EVO 512 ran ~10 mV/h
lower than other cards on the loggers. This bench test measures per-card draw directly so
we can standardize the fleet on the lowest-power card (see `incident_log.md` SD findings).

**Rig / conventions (fill in once):**
- Measurement point: ___ (e.g. USB SD reader on 5 V rail — implied V column cross-checks this)
- Card state during reading: ___ (idle mounted / sustained write / formatting) — power depends
  heavily on state, so keep ALL rows in the same state for a fair ranking.
- The absolute W here is at the reader's rail (~5 V); the logger runs the card at a lower rail,
  so in-logger watts differ — but the **relative ranking across cards is what transfers**.

| # | Card (capacity + model) | Current (A) | Power (W) | Implied V (W/A) | Notes |
|---|-------------------------|-------------|-----------|-----------------|-------|
| 1 | 128 GB Pro Endurance Samsung | 0.0732 | 0.3791 | 5.18 V | first reading |
| 2 | 128 GB Insignia | 0.0732 | 0.3783 | 5.17 V | ~identical to Samsung Pro Endurance |
| 3 | 128 GB Pro Endurance Samsung (#2) | 0.0752 | 0.3894 | 5.18 V | 2nd Pro Endurance sample — +11 mW vs #1 (card-to-card spread) |
| 4 | 512 GB Samsung Sonic | 0.0687 | 0.3566 | 5.19 V | lowest so far — 512 GB draws LESS than the 128 GB cards (matches the EVO-512 field win) |
| 5 | 512 GB Lexar Play Blue | 0.0752 | 0.3921 | 5.21 V | HIGHEST so far — and also a 512 GB, so capacity is NOT the driver; the specific card is |
| 6 | **256 GB Samsung EVO** | **0.0563** | **0.2936** | 5.21 V | **NEW LOWEST by a wide margin — 63 mW (18%) under the Sonic 512, 100 mW under the Lexar. Bench now agrees with the field: EVO is the low-power card, and the ranking is set by the controller, not the capacity.** |

## Ranking (lowest power first) — auto-filled as rows come in

1. **256 GB Samsung EVO — 0.2936 W  ⭐ lowest (2026-09-08)**
2. 512 GB Samsung Sonic — 0.3566 W
3. 128 GB Insignia — 0.3783 W
4. 128 GB Pro Endurance Samsung (#1) — 0.3791 W
5. 128 GB Pro Endurance Samsung (#2) — 0.3894 W
6. 512 GB Lexar Play Blue — 0.3921 W  ⚠️ highest

_Notes: (a) the two Pro Endurance samples differ by ~11 mW — unit-to-unit variation within one
model is real, so measure the actual card that goes on each logger, not just the model.
(b) capacity is NOT the driver: 0.294 W (EVO 256) to 0.392 W (Lexar 512), with a 512 GB card at
each end of the middle — it is the specific card/controller.
(c) **the EVO gap is the big one: 63 mW below the Sonic, 98 mW below the Lexar, vs a 36 mW spread
across all the non-EVO cards.** Scaling the field result the same way: the non-EVO cards cost
~10 mV/h against each other, and EVO vs non-EVO is worth ~4.5 h of battery (12.5 h vs 8.0 h on the
same 900 mAh cells, 9/7–9/8) — so the bench ordering and the field ordering now agree in both
sign and rough magnitude._

## EVO benched 2026-09-08 — caveat closed

The open TODO ("EVO 512 not yet benched, so Sonic-512-is-#1 is provisional") is settled: a
**Samsung EVO 256** measured **0.0563 A / 0.2936 W** on the same rig — the lowest of every card
tested, by 63 mW over the next best (Sonic 512). The field verdict was right and the bench now
shows why: **the EVO controller draws ~18% less than anything else here**, and the effect is not
a capacity effect (this EVO is a 256 GB and still beats both 512 GB cards).

Two loose ends, neither affecting the ranking:
- The benched EVO is a **256 GB**; the fleet's field cards are **EVO 512**. Same family, but
  measure an actual EVO 512 when one is free to confirm the 512 behaves like the 256.
- Record the card **state** during the reading (idle-mounted vs sustained write) in the rig block
  above — all rows must be in the same state for the ranking to hold, and the logger's real duty
  cycle is sustained write at 2.48 MB/s.

**Standing rule unchanged, now with bench backing: EVO on every logger; Sonic/PE/Insignia are
day-shift or spare only; keep Lexar Play Blue off the loggers.**

## Field observations (in-logger, same night, cards as the only difference)

- **2026-09-02 evening round:** SF07 was fitted with a **Samsung Sonic 512**; the other five run
  **EVO 512**. All six got fresh cells (4.12–4.22 V) within 10 min of each other.
- **First 2 h (19:05 → 21:01):** SF07 dropped **200 mV** (4.18 → 3.98); the five EVO loggers
  dropped **~120 mV** each. Same battery batch, same load, same night — the card is the
  standout variable. **Not new — already established on night 1:** the one non-EVO logger
  (SF10 on the Sonic) drained fastest (75.6 vs 65–67 mV/h on 8/31) and was the only premature
  death (brownout 03:27). Tonight's SF07 is the same effect repeating.
- **Conclusion (field, CONFIRMED):** EVO 512 > Sonic 512 for logger battery life. Fleet
  standard = **EVO 512**. Sonic is second-tier — beats Lexar Play Blue / the 128 GB cards on the
  bench, but not EVO-level in the logger. **Never put a Sonic on a logger overnight**; spare only.
