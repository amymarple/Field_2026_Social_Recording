# Neurologger (CE64X / WILD) daily resync protocol

> ## ⚠️ SUPERSEDED (2026-08-30) — from cohort 3 on, follow the new protocol
> This document was written for cohort 2 (one reset + resync per day at 4 PM). **Its "reset the instant it
> connects" step conflicts with the current rule.**
> The current protocol (verified against the source) is on the Notion cohort-3 page, section "Daily sync check +
> Sync mechanics". Core changes:
> 1. **Resync only BEFORE Record Start; never Resync or reset while recording**;
> 2. every battery change = the double-anchor ritual: before pulling the battery stay connected ~30–60 s and wait
>    for `Sync[Live]` (end anchor, note `dev=`) → Record Stop → change the battery → reconnect, Resync →
>    Record Start → stay connected another ~30–60 s (start anchor);
> 3. anchors are written to the logger's own SD card (analogin.dat) at a ~5 s cadence; the PC stores no
>    sync-critical data;
> 4. offline acceptance: `WILD_generate_pc_time.py <session> --summary-plot`, anchors present at both ends and
>    flat residuals.
> The rest of this file is kept only as the cohort-2 historical record.

**Purpose**: the logger records continuously to its own SD card, but its on-board clock drifts further and
further from the main PC time (measured: one unit 12 min 43 s off, another 58 min 34 s). One reset + resync per
day re-anchors the device RTC to the main PC time, so the electrophysiology can be aligned with the camera video
and PC time; it also clears accumulated state such as a wedged device or repeated BLE reconnects.

**Version basis**: wild_console 3.4.2.132 (mechanism confirmed by decompilation on 2026-08-17; see "How it
works" at the end).

---

## Daily procedure (once a day at a fixed time, one logger after another)

**Use the main PC, not the mini PC** (the main PC's antenna is strong; the mini PC's signal is too weak: slow to
connect, drops easily).

1. **Connect**: open wild_console, select the target logger in the Device List, click **Connect**.
2. **Click Reset device the instant it connects** (daily routine, regardless of how fast it connected):
   - If connecting takes more than **60 s**, or it keeps auto-reconnecting after connecting, the device is
     wedged — all the more reason to click reset the instant it connects.
   - Reset reboots the device and **stops the current recording** (one short recording gap per day; expected).
3. **Wait for the reconnect to settle**: after the reset the device reboots and advertises again, and the console
   reconnects. Wait until the status bar's **`Cmd:` count reaches ≥ 256** before the next step (by then the RTC
   write 0x8A and the initial time sync `Sync[InitTrain]` have completed automatically and the telemetry
   heartbeat is steady).
4. **Check the time sync**: the status bar should show **`Sync[Live]`**; healthy means:
   - `dev=00:00.0xx` (min:sec.ms, should be near 0)
   - `err=±a few ms`; it must **not** be `err=outlier(...)`, nor hundreds of ms or seconds
   - Not healthy → click **Resync**; still not → reset once more and restart from step 3.
5. **Click Record Start** and confirm it really started:
   - **Recording time counting up from 00:00 and Storage Used (MB) growing** = recording.
   - If States shows `record start failed:` but both of the above are moving → a false alarm from a BLE ack
     timeout; ignore it (once recording is confirmed, the device confirms through the rec-time stream).
   - If Recording time does not move → click Record Start again.
6. **Fill in the daily table** (below), then **Disconnect** and let the device record on its own.

---

## Daily record table

| date | time | device ID | dev before reset | err after resync | voltage (V) | Storage (MB) | notes |
|------|------|-----------|------------------|------------------|-------------|--------------|-------|
|      |      | CE64X_CACB6D600151 |                  |                  |             |              |       |
|      |      | CE64X_A7F8EDC4A051 |                  |                  |             |              |       |

> **`dev before reset` must be recorded**: it is the clock offset of the previous day's recording relative to PC
> time, and aligning that day's data afterwards depends entirely on this number. After the reset the offset is
> gone from the device.

---

## Troubleshooting quick reference

| Symptom | Action |
|---|---|
| Connect takes more than 60 s | Disconnect and reconnect; click reset the instant it connects |
| Repeated reconnects after connecting | Device wedged — reset the instant it connects |
| `Sync[Live]` still outlier or a large error after reset | First check the main PC time (time.is), then Resync / reset again |
| `record start failed:` but Recording time moving and Storage growing | False alarm, ignore |
| `record start failed:` and Recording time not moving | Click Record Start again; if it still fails, reset and start over |

---

## Automatic monitoring (from 2026-08-18)

`neurologger_alive_check.ps1` (SYSTEM task, every 5 min) reads the continuously refreshed
`C:\Users\Cornell\AppData\Local\CE32_console\discovered_devices.csv` written by wild_console and sends a Slack
alert when a logger has not been heard over BLE for more than 60 min (with phone troubleshooting steps); it also
alerts when the CSV itself has not been updated for 15 min (console closed). Low battery (<3.60 V) and storage
(≥90 %) each get a one-time reminder. Details: `change_log/2026-08-18-neurologger-alive-check.md`.
**Prerequisite: wild_console must stay open and scanning on the main PC** — it is now part of the rig.

## How it works (why this procedure; from the 3.4.2.132 decompilation)

- Once connected, the console automatically sends an **RTC push (0x8A)** that writes the host time into the
  device RTC, then a sync start that launches the initial time sync (`Sync[InitTrain] ... n=N` is the device's
  automatic sync exchange), after which it enters periodic `Sync[Live]` syncing. **The RTC is rewritten only in
  this phase** — hence one reset + reconnect per day to re-anchor the clock.
- `Cmd:` is the cumulative count of device→console protocol messages (status heartbeat ~1/s + sync responses +
  operation acks). Waiting for ~256 is only an empirical "connection stable, initialisation done" criterion, not
  a specific command.
- `Sync[Live] dev=... err=... dly=...`: dev = offset between the device clock and the host clock; err =
  measurement error of each sync (shown as `outlier` and discarded above a threshold, not used in the
  statistics); dly = BLE round-trip delay.
- Record Start actually sends one 3-byte `record start` command and waits for the ack; a lost ack leaves the
  residual `record start failed:` state, but the command itself usually took effect — go by Recording time /
  Storage.
