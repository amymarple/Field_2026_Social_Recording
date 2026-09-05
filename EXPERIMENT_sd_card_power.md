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

## Ranking (lowest power first) — auto-filled as rows come in
1. 512 GB Samsung Sonic — 0.3566 W  ⭐ lowest
2. 128 GB Insignia — 0.3783 W
3. 128 GB Pro Endurance Samsung (#1) — 0.3791 W
4. 128 GB Pro Endurance Samsung (#2) — 0.3894 W
5. 512 GB Lexar Play Blue — 0.3921 W  ⚠️ highest

_Notes: (a) the two Pro Endurance samples differ by ~11 mW — unit-to-unit variation within one
model is real, so measure the actual card that goes on each logger, not just the model.
(b) capacity is NOT the driver: the range is 0.357 W (Samsung 512) to 0.392 W (Lexar 512) — both
512 GB, spanning the whole spread. It's the specific card/controller. **Samsung Sonic 512 wins;
Lexar Play Blue 512 is worst** — standardize on the Samsung, keep Lexar off the loggers.
(c) full span so far ~36 mW ≈ the ~10 mV/h battery difference seen in the field._

## Caveat on the bench ranking — EVO 512 not yet benched

The bench table above ranks only the cards that were measured. **Samsung EVO 512 — the field
champion for battery life — has NOT been put on the bench rig yet.** So "Samsung Sonic 512 = #1"
is provisional: it beats the 128 GB cards and the Lexar, but the field says EVO beats Sonic.
**TODO: bench the EVO 512 under the same rig/state** to close the ranking.

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
