# 2026-07-18 — UltraMic USB wedge: root cause, cable swap plan, alert mute

## Incident
MIC01 (UltraMic384K, WASAPI exclusive 384 kHz) stopped at **19:44:51** after a flawless ~31 h
run. PnP status of both device entries fell to **Unknown**; every software revival failed with
*Generic failure* (device answers no USB requests): user-run WMI Disable/Enable-PnpDevice,
Audiosrv restart, and the supervisor's new auto-recovery (level 1 PnP cycle 20:55, level 2
PnP+Audiosrv 20:57) → Slack page 20:59, then designed 5-min retry backoff. Deep firmware
wedge — only re-enumeration via reboot or physical power loss can clear it. Video/thermal
completely unaffected throughout.

## Root cause (user diagnosis) + solution plan
The mic hangs on a **65-foot PASSIVE USB extension** — ~4× beyond the USB 2.0 spec limit
(5 m / 16 ft). Marginal signaling + voltage drop at that length explains both the long
clean run and the sudden unrecoverable wedge. **Plan: swap to an ACTIVE (repeater) USB
extension cable** (regenerates the signal per segment; ideally one with external power
injection). Until the swap: mic stays down; supervisor keeps retrying every 5 min and will
auto-resume + send the all-clear when the device returns by any route.
Longer term (remote ops): powered-hub-on-a-smart-plug gives remote true power-cycle;
supervisor could call the plug API as recovery level 3.

## Alert mute (per user: one page per stop, no re-pages, until repaired)
`recording_alive_check.ps1` now supports **`AliveMuteGroups`** in the shared QC config
(`E:\recording_qc\overexposure.config.psd1`, currently `@('MIC01')` — config is read every
run, so no task re-registration was needed):
- muted group stops → **one** Slack page (:no_bell:, states it will not re-page), never re-alerts
- muted group recovers → one all-clear; state tracked per group (`mutedAlerted` in state JSON)
- non-muted groups keep the original behavior (alert → hourly re-alert → recovery)
- status line shows `[muted: ...]`; migration seeds an already-ongoing muted outage silently
  (it was already paged under the old model)
Verified: SelfTest PASS (incl. new mute-split case); live DryRun shows MIC01 muted-stalled
with all 12 video/thermal groups ok. Mirrored to `Field_2026_Social\reolink_record\`.
**Un-mute after the cable swap proves stable: remove MIC01 from AliveMuteGroups.**

## Also today (same day, separate entries may apply)
Supervisor gained device auto-recovery ladder (PnP cycle → +Audiosrv → page + 5-min backoff)
with recovery detection and all-clear messaging — worked as designed in this incident, the
wedge was simply below software reach.

## Update 2026-07-19 ~14:22 — RECOVERED after replug
User replugged the mic; capture auto-resumed at the supervisor's next 5-min retry (14:22:18) —
verified 384 kHz / mono / 16-bit, correct data rate, device PnP OK. Total audio outage:
2026-07-18 19:44 -> 2026-07-19 14:22 (~18.6 h). Fixed a recovery-state bug found during
verification: the all-clear/reset was gated on the rapid-fail streak, which the slow 5-min retry
cadence had already zeroed, so a subsequent wedge would not have re-paged from the supervisor
(alive-check one-shot still covered it). Reset now also triggers on lingering alerted/backoff
state; restart the 'Field UltraMic Recorder' task to load it. MIC01 stays in AliveMuteGroups
(one page per stop) until the ACTIVE extension cable is installed and has proven stable.
