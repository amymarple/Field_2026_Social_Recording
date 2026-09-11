# Cohort-3 neurologger battery log (SF07–SF12)

Released ~19:00 2026-08-30. One row per **battery cell on a logger** — start = the swap
(upward jump ≥150 mV in the advertised voltage), end = the next swap or the auto-stop.
Auto-extracted from `E:\recording_qc\neurologger_telemetry_history.csv` (5-min advertisement
snapshots) on 2026-09-04 20:40; rounds before 9/1 23:41 are reconstructed from the incident
log / connected-heartbeat decodes because the ad watchdog was off (troubleshooting) and FM63
froze advertisement telemetry during recording (8/31 → 9/1). Card model per row is from the
operator's read-off (only the physical read is authoritative). Regenerate the table any time
with the extraction snippet at the bottom.

## THE HANDLING RULE (read this before proposing any swap)

**Catching a rat is the expensive step, not the swap. Rats are caught ONCE per round, all together. Never plan a single-logger battery change, a single-logger card swap or a “while you're there” fix — if one animal has to be caught, the whole round happens, and if the round is not happening, nobody is caught.**

Why: every catch disturbs sleep, which is the experiment. Two catches in a day cost twice the disturbance and buy nothing — the rats have to be caught for the next round anyway. A round takes 1–2 h of handling, so “just SF07” is never just SF07.

What follows from it:

- **The round is timed by the FIRST logger to reach the knee**, not by the average. Everyone gets a fresh cell at that time, even the ones with 4 h left.
- **A weak cell installed mid-round is not swapped out early.** It either runs to its auto-stop (FM65 commits byte-exact) or it is covered by an anchor touch — it is not a reason to catch that animal again.
- **BLE-only actions are free** (connect-only anchor touches, Record Stop/Start, Resync on an idle logger, reading telemetry): no catching, no disturbance. Use them freely instead of handling — that is the whole point of the knee-voltage anchor pass.
- **Auto-stop is an acceptable outcome, a mid-day catch is not.** A logger that auto-stops loses recording time between the stop and the round; it does not lose the session.
- Consequence for the forecast tools: the advice line is “START THE ROUND BY hh:mm” for the whole fleet. Per-logger swap times are the ORDER within one round, never separate trips.

**Design numbers so far**
- Regular cell on an **EVO 512** card: **12–14 h** to auto-stop (9/3 night 14.1–14.3 h is the
  record; 9/4 day cells were swapped alive at 11.8–12.0 h with 1–2 h left).
- Same cells on **non-EVO cards** (Sonic / Pro Endurance / Insignia): knee at **~9 h**
  (9/3 day). **Only the EVO is a low-power card** — the 9/3 same-day switch (non-EVO day
  batch → all-EVO night batch) is the cleanest evidence: +50% life from the card alone.
- The regular cells are **900 mAh nominal**; the two "1000 mAh" cells last **17–24 h** — 1.5–2×
  the 900s despite only +11% on the label, so the 900s are delivering well under their rating.
  **The label does not predict life; the measured life in this table does** (cell triage).
- Auto-stop lands at ~3.40 V; knee 3.68 V; the dive below the knee takes ~2 h (900 mAh) /
  ~4 h (1000 mAh).
- **The 3.5 V rule (measured 9/10 on every cohort-3 auto-stop in the telemetry history):** from the first ad ≤ 3.60 V it is **30–50 min** to auto-stop, ≤ 3.55 → 15–20 min, ≤ 3.50 → **5–15 min** (0–25). The last 30 min run 270–430 mV/h (7–10× the plateau); the forecast's 4-h slope under-reads the dive by 30–60 min once a logger is past the knee. Read the ads as **3.60 = half an hour, 3.50 = ten minutes**; SF07/SF10 read lower under load (holder contact), so their margin is tighter still.
- Install full. **900 mAh: ≥4.18 V rested** — the 4.08–4.12 V installs of 900s have been the
  first to die every time. **1000 mAh: they top out at ~4.08–4.12 V — that IS full for them;
  do not reject them by the 4.18 rule.**

## Rounds

| round | cards | what happened |
|---|---|---|
| **8/30 ~18:35–20:00** release install | mixed, mostly non-EVO | 3.96–4.10 V (lower than later rounds). Night 1: **all six lost** (batteries pulled without Record Stop under FM59–62 = no directory entry) and three loggers went far below the auto-stop point — SF10 browned out at 03:30 (2.84 V, 8.8 h), SF12 2.40 V (9.5 h), SF11 2.62 V (11.3 h). SF07/SF08 lasted 12.3 h. |
| **8/31 03:30–07:30** early round | EVO on all but SF10 | Fresh cells 4.06–4.14 V on all six (SF10/SF12 got two brief interim cells first, see table). Day drain: EVO cluster 65–67 mV/h, SF10 (non-EVO) 75.6. Daytime 11:00–18:00 = troubleshooting blank on all loggers. |
| **8/31 ~18:45–19:15** evening | only SF07 EVO | Fresh 4.08–4.18 V (logger-side; meter read ~4.6 V off-load — over the LiPo limit, charger checked). Night drain 54–69 mV/h, SF07 (EVO) lowest at 54; auto-stops ~03:30 9/1 (8.5–8.75 h). |
| **9/1 05:42–08:17** AM round | mixed | Old cells at 3.40–3.68 V; fresh 4.03–4.21 V. **SF08's cell was undercharged (3.78 V)** → died ~13:45–14:30; re-batteried 15:30 (4.125 V, a 1000 mAh). |
| **9/1 19:29–19:56** evening | **all EVO 512** from here | Fresh 4.08–4.24 V. SF12 first got a **dead 3.42 V cell** (caught after 11 min, replaced 19:56 at 4.148). 1000 mAh on SF08 (from 15:30) and SF11. Overnight fleet drain only ~35 mV/h → nobody died before 05:26; 1000 mAh confirmed by half-slope. |
| **9/2 ~08:00–08:20** AM | all EVO | Fresh 4.06–4.24 V; SF07 formatted only. Midday 12:57 Stop→Start (no swap). |
| **9/2 19:01–19:11** evening | SF07 **Sonic 512**, rest EVO | Fresh 4.16–4.22 V. SF07 first to die (04:17 9/3, 9.2 h incl. a 200 mV surface-charge drop); the EVO five lasted 12.3 h+ (swapped alive ~07:21 9/3). Midnight Stop→Start 00:16–00:25 (no swap). |
| **9/3 ~08:06** AM | **all non-EVO**: SF07/08/09 Sonic 512, SF10 Pro Endurance 256, SF11 Pro Endurance 128, SF12 Insignia 128 | Fresh 4.06–4.20 V. **Fast-draining day batch — the cards.** SF08 and SF11 auto-stopped in the afternoon (SF08 restarted 16:03 on the same cell; SF11 restarted, ran a 580-s stub and died again at 3.40 V); SF09/SF10 were at 3.40–3.50 V when stopped for the round (16:53); SF12 was **stopped manually at 16:55, still 3.62 V**. **SF07's 9/3 08:06 cell ran 24.0 h** (to 9/4 08:06) = a 1000 mAh, even starting on a Sonic. |
| **9/3 16:46–18:10** evening | **all switched to EVO** | Round ran 16:46–18:10 (Stops from 16:46, fresh cells 17:50–18:10): 4.18–4.22 V on SF08–SF12, SF07 kept its 1000 mAh (card swapped at its 17:49 Stop/Start). **Longest regular-cell run so far: 14.1–14.3 h** — SF10/SF11/SF12 auto-stopped 08:06–08:21 9/4, minutes before the round reached them (operator arrived ~08:15); SF08/SF09 swapped alive at the knee. |
| **9/4 08:11–08:26** AM | all EVO | Fresh 4.14–4.24 V. Midday ~14:02 Stop→Start on SF07/SF11 (no swap). All six still alive at the evening swap (11.8–12.0 h, 3.62–3.72 V). |
| **9/4 20:10–20:33** evening | all EVO | Fresh: SF07 4.16, SF08 4.12, SF09 4.18, **SF10 4.08 (a 900 mAh — genuinely low)**, SF11 4.12, SF12 4.18. **SF08 and SF11 carry the two 1000 mAh (4.12 is their full charge)**; SF07/SF09/SF10/SF12 are 900 mAh. Expect SF10 first (~08:00 9/5), then SF07/SF09/SF12 (~08:30–09:30); SF08/SF11 run to ~13:00. The 01:02 forecast gives the exact order. |
| **9/5 08:40–09:50** AM | **high-power set, operator-confirmed 17:50 (SF07/08/09 Sonic 512, SF10 PE 256, SF11 PE 128, SF12 Insignia 128; inferred from fill rates 10:00→13:00 beforehand):** Insignia is NOT a low-power card: bench 0.378 W = PE 128 (Sonic 0.357 W); today all six drained 62–67 mV/h with SF12 at 67, the highest — SF12 only looks good because it keeps getting the fullest cell (4.18–4.24 V installs on 9/3 and 9/5). SF07/08/09 ~1.7 %/h = 512 GB (Sonic), SF10 3.4 %/h = 256 GB (Pro Endurance, not formatted, 33→45%), SF11/SF12 7 %/h = 128 GB (Pro Endurance / Insignia). Drain 92–109 mV/h in the first 3.5 h vs ~65 on EVO = ×1.5–1.7. | Night cells (9/4 20:20–20:33): the 900s ran **12.2–12.5 h** and were stopped at 3.58–3.64 V, right at the auto-stop edge (~08:31–08:45); the 1000 mAh on SF08/SF11 were alive at 3.68–3.70 after 12.3 h. **SF10's 4.08 V cell died three times** (~06:58, ~07:29 after a zombie restart at 07:00, ~08:30 after another at 08:05) → retired. **Anchor-only BLE pass 08:00–08:10, no handling**: 14–16 anchors per logger; SF12 (the first to slide) was ridden 07:30–08:10 = 210 anchors. **All six Record-Stopped ~08:40–08:50; fresh cells at 09:31 (SF07 4.22, SF08 4.18, SF09 4.22, SF10 4.22, SF11 4.18, SF12 4.24); Rec Start 09:33–09:50 → a ~50-min fleet-wide recording gap during the swap + 5 card formats.** Round deliberately late: operator cannot do dawn, and with 8-h cards the morning round should sit as late as the night cells allow. |
| **9/5 18:00–19:03** evening | **all EVO** (cards 0% at start) | Fresh (heartbeat, under load): SF07 4.21, SF08 4.18, SF09 4.19, SF10 4.22, SF11 4.16, SF12 4.18 (ads 4.14–4.24). 1000 mAh = SF08 + SF11 (23:50 slopes 34-37 mV/h vs 62-69 on the 900s). 23:50 forecast: auto-stop SF12 ~07:08, SF07/SF09 ~08:25, SF10 ~09:07, SF08/SF11 ~16:00 -> bedtime connect-only touch on the four 900s as insurance end anchors; AM round ~08:30 starting with SF10 (still alive), SF08/SF11 last. | Day cells (high-power card set) were **manually Record-Stopped 18:00–18:08 at 3.58–3.66 V after 8.3–8.5 h** – none auto-stopped, so every session got a real end anchor (14–16 anchors in the ~65–71 s before each Stop); the 17:22–17:32 insurance pass was not needed. Round: Stops 18:00–18:08 → Resync on the idle loggers (2–3 RTC writes each, none while recording) → 30-s guard file → final Rec Start SF07 18:47:33, SF08 18:51:05, SF09 18:54:22, SF10 18:57:09, SF11 18:59:31, SF12 19:02:41 (14–17 start anchors each) = a ~45-min fleet gap. Console attribution glitch: SF10's 18:06:45 Stop was logged under SF11's device ID and SF11's 18:08:22 Stop under the corrupted name AS-NBB-AOG35 – resolved by the rec counters (30429 s = SF10, 10608 s = SF11). Expect the 900 mAh cells to auto-stop 07:00–09:00 on 9/6 (12.2–14.2 h on EVO). |
| **9/6 06:54–08:10** AM | **all EVO** (cards NOT formatted, 19–23% at restart) | Fresh (heartbeat, under load): SF07 4.14, SF08 4.20, SF09 4.18, SF10 4.17, SF11 4.16, SF12 4.17. **All six day cells are 900 mAh (operator 14:30, correcting the 08:20 note); the two 1000 mAh cells are night-shift only, on SF08 + SF11.** 14:18: all six 55-60 mV/h, 3.80-3.82 V at 6 h -> auto-stop 19:40-22:00 (SF08 first ~19:42, SF12 last ~22:03), evening round by 18:45. | Night cells: **manually Stopped 06:54–07:02 at 3.60–3.72 V after 11.9–12.1 h** – none auto-stopped, 14–16 end anchors each (64–73 s connects); SF12 first to the edge again (3.58 at 06:56); the 1000 mAh on SF08/SF11 still at 3.70–3.71. **SF10 stopped ~04:03 at 3.74 V flat** (counter froze at 32745 s; ads unchanged before/after) → operator restarted it 05:58 on the same cell (3.74–3.76 under load, ran 1.0 h to the round's Stop 07:00) and suspects a loose battery contact – the 9/5 'retired' cell may have been innocent; check SF10's holder. SF07 05:36–05:56 ad rec-counter freeze looked like a stop but the heartbeat (40529 s at 06:03) proved continuous recording. Midnight connect-only pass 00:21–00:36: 13–24 anchors each. Restarts 07:53–08:10 (Resync on idle loggers only, guard files, 14–18 start anchors) = ~1-h fleet gap. Expect 900 mAh on EVO 12–14 h → ~20:00–22:00; the 1000s to ~01:00. |
| **9/6 19:00–19:55** evening | **all EVO** (NOT formatted two rounds running, 39–43% at restart) | Fresh (heartbeat, under load): SF07 4.20, **SF08 4.10 (1000 mAh)**, SF09 4.22, SF10 4.22, SF11 4.19, **SF12 4.19 (1000 mAh)** (operator 20:15: the 1000s are on SF08 + SF12 tonight; SF11 on a 900). | Day cells (all 900 mAh) **manually Stopped 19:01–19:10 at 3.65–3.68 V after 10.9–11.1 h** – none auto-stopped; end clusters 14–27 anchors (SF07 first past the knee, 3.66 at 17:51). Midday anchor pass 15:32–15:43 on SF08–SF12 (14–20 each). Restarts 19:40:36–19:55:03 (Resync on idle loggers only, guard files, 14–21 start anchors) = ~40-min fleet gap. **Cards: ~67% by the AM round, ~88% by tomorrow evening → format at the 9/7 AM round.** Expect the 900s (SF07/09/10/11) to auto-stop ~07:50–10:00 on 9/7 (SF09 first), the 1000s (SF08/SF12) ~13:00. |
| **9/7 08:06–09:15** AM | **HIGH-POWER card set again (inferred 12:40 from fill rates: SF07/08/09 ~1.8 %/h = 512 GB Sonic, SF10 3.4 %/h = 256 GB PE, SF12 6.8 %/h = 128 GB), formatted** (0–4% at restart) | Fresh (heartbeat, under load): SF08 4.20, SF09 4.19, SF10 4.16, SF12 4.20; **SF07 4.10 → weak (144 mV sag in the first minute), pulled after 15 min and replaced 09:15 with a 4.08 cell** (4.00 at 09:36). Day shift = all 900 mAh. | Night cells **manually Stopped 08:06–08:14 at 3.53–3.70 V after 12.3–12.4 h** – none auto-stopped. Anchors: midnight pass 23:43–23:57 (13–27 each), knee-voltage pass 06:41–06:49 (SF11 15, SF08 19, SF07 30, SF09 19; lab protocol), end clusters at the Stops 14–36 (SF11 only 2 – moot). **SF11 implant fell off ~07:40 → Stopped 08:12:41 with a commit receipt, NOT restarted, retired from the roster 08:52.** SF08's 1000 mAh ended at 3.60 after 12.4 h (20:00 4.06, ran like a 900) vs SF12's 1000 at 3.70 → number SF08's cell as a suspect 1000. **SF07 logger: 3–7× the fleet's start-up sag on 3 of its last 4 installs with different cells (65 / 62 / 144 mV vs 4–34) → ~1–2 Ω contact resistance in its holder, same class as SF10; its logger-side voltage reads low under load, so it auto-stops earlier than the cell warrants → clean/tighten SF07 + SF10 holder contacts.** Restart gap ~45 min (SF07 09:15 after the second swap). **12:40 CHECK: all five drain 85–100 mV/h (x1.67 of the EVO curve) - the cards, not the cells; knee 14:40–16:15, auto-stop 16:35–18:10 -> EVENING ROUND BY 15:30 (SF07 first), anchor pass ~14:30. Tonight must be EVO again; the 128 GB card on SF12 cannot do a night (7 %/h).** 1000s back on SF08 + SF12 for the night. |
| **9/7 16:54–18:00** evening | fresh cards, all formatted (0–1% at restart) – **model per logger to be read off** (EVO wanted for the night) | Fresh (heartbeat, under load): SF07 4.13, SF08 4.17, SF09 4.21, SF10 4.21, SF12 4.20. | Day cells (high-power cards) **manually Stopped 16:54–17:02 at 3.50–3.67 V after 7.7–8.0 h** – none auto-stopped; **8 h is the high-power-card life, vs 12.3–12.4 h on EVO the night before.** Anchor pass 13:17–13:25 (14–23 each) and end clusters at the Stops 16:53–17:01 (15–23 each). SF07 lowest again at 3.50 (its holder contact reads low under load). Restarts 17:48–18:00 (Resync on idle loggers only, guard files, 15–16 start anchors) = ~55-min fleet gap. Five loggers now (SF11 retired). |
| **9/8 06:21–07:26** AM | **EVO 512 all five, NOT formatted** (23–24% at restart) | Fresh (heartbeat, under load): SF07 4.22, **SF08 4.09 and SF12 4.12 - UNDERCHARGED 900s, not 1000s (day shift is all-900; the 1000s are night-only)**, SF09 4.22, SF10 4.23. | Night cells **manually Stopped 06:21–06:30 at 3.50–3.68 V after 12.5–12.6 h on EVO** – none auto-stopped, 15–16 end anchors each (66–73 s connects). Round deliberately early (operator came at 05:00) to beat SF07's dive: SF07 was at 3.50 and falling 100 mV/h at 06:19, Stopped 06:21. **Cards confirmed EVO** by the overnight fill (1.8–2.0 %/h = 512 GB) after the high-power day set. **Ad feed dead 00:01–05:04** (operator correction 9/10: not a link left open - the console window had not been reopened after the 23:33 touch, so nothing was scanning) → no telemetry rows for 5 h, the 01:02 forecast was all-STALE; recording unaffected (counters continuous). Bedtime anchor pass 23:14–23:33 on all five (14–22 each). Restarts 07:15–07:26 (Resync on idle loggers only, guard files, 15–27 start anchors) = ~55-min fleet gap. **SF08 (4.09) and SF12 (4.12) went in undercharged** - the day shift is all 900 mAh, so those are 900s below the 4.18 V install rule, and by 12:12 they were the first two to the knee (3.80/3.82 vs 3.88-3.90) at the same 56-61 mV/h as the rest. Number both cells and check them rested. On EVO expect ~18:45–20:00 for the 900s → evening round ~18:30. |
| **9/8 18:54–19:48** evening | **EVO 512, cards NOT formatted** (45% at restart) | Fresh (heartbeat, under load): SF07 4.16, SF08 4.18, SF09 4.20, SF10 4.22, SF12 4.17 – **all five 4.16–4.22, no undercharged cell this time**. | Day cells **manually Stopped 18:54–19:01 at 3.53–3.68 V after 11.6–11.7 h on EVO** – none auto-stopped; end clusters 15–34 anchors (66–288 s). The two undercharged 900s (SF08 4.09, SF12 4.12 at install) led all day but flattened in the plateau (26–31 mV/h vs 41–51) and finished only 60–150 mV behind – **an undercharged cell costs ≈ the missing volts, not a faster drain**. Midday connect-only pass 12:15–12:41 (SF07 194, SF08 14, SF09 23, SF10 51, SF12 18) + a 18:49 knee touch on SF08 (18). Restarts 19:37–19:48 (Resync on idle loggers only, guard files, 15–17 start anchors) = ~45-min fleet gap. **Cards at 45% and NOT formatted for the third round running → ~88% by tomorrow evening: format at the 9/9 AM round.** Construction with heavy machinery near the paddock from ~07:5x (see incident log – quantify from mic + video audio later). |
| **9/9 08:16–09:14** AM | **EVO 256 on ALL FIVE** (operator: the whole day set was 256; the planned single-logger test became a fleet test), all formatted (0–2%) | Fresh (heartbeat): SF07 4.22, SF08 4.14, SF09 4.21, SF10 4.22, SF12 4.12 (900s; SF08/SF12 again under the 4.18 rule). | Night cells (EVO 512) manually Stopped 08:16–08:22 at 3.58–3.67 V after **12.6 h** – the best night of the cohort. Overnight anchor pass 03:17–03:27 landed on all five despite scattered rats. **EVO 256 FIELD RESULT (n=5):** phase-matched 1–6 h drain 63.7 mV/h vs 57.0 on the 9/8 AM EVO-512 batch = **+6.7 mV/h, matching the bench's +22 mW ≈ +7 mV/h**; projected life 11.2–11.7 h vs 11.6–12.6 on EVO 512 (cells were Stopped early at 8.8–8.9 h for rain, so the projection was not run to the end). **256 = day shift only, never overnight; fill 3.66 %/h → format every round.** Mowing near the paddock 09:41–14:00. |
| **9/9 17:55–18:51** evening | **EVO 512 all five** (fill 1.8 %/h confirms), not formatted (4%) | Fresh (heartbeat): SF07 4.19, SF08 4.12, SF09 4.16, SF10 4.19, SF12 4.10 – SF08/SF12 at the 1000 mAh full-charge level (night shift). | Day cells (EVO 256) **manually Stopped 17:55–18:02 at 3.68–3.73 V after 8.8–8.9 h** – 2 h early for incoming rain, still on the plateau. End clusters 16–22 anchors; afternoon pass 16:44–16:55 (SF09 topped up to 22). **Probe moves at this round: SF08 and SF12 each advanced 1/4 turn (down; probes sat high)** – SF08's move fell inside its swap (pre-move session ends 17:57:34, post-move from 18:50:36, no split); SF12 was started 18:40:28, Stopped 18:46:34 for the adjustment, Resync idle, restarted **18:47:51** (6-min stub 18:40–18:46 is pre-move). Restarts 18:38–18:51 (Resync idle only, guard files, 14–16 start anchors), fleet gap ~45 min. Expect 900s 12–12.5 h → ~06:40–07:20 on 9/10; the 1000s past noon. |
| **9/10 07:17–08:35** AM | **EVO 512 all five, NOT formatted** (24% at restart) | Fresh (heartbeat at Start): SF07 4.19, SF08 4.22, SF09 4.23, SF10 4.24, SF12 4.25 – every cell ≥ 4.18. | Night cells **manually Stopped 07:17–07:43 at 3.48–3.64 V after 12.5–12.9 h** – none auto-stopped, but SF10 (3.48) and SF09 (3.52) were minutes from it; end clusters 14–19 anchors (65–85 s) on top of the knee pass 06:04–06:12 (14–18 each). Rats scattered outside all evening → no bedtime pass; SF07 out of BLE range 22:33–23:06 (parked at a paddock corner), recorded through. The two “1000 mAh” cells (SF08 3.62, SF12 3.55) finished inside the 900 pack again (3.74/3.72 at 11.5 h, then 41–46 mV/h) → number both, measure rested, 900-class until proven otherwise. Restarts 08:23–08:35 (Resync on idle loggers only, guard files, 26–38 start anchors), fleet gap 52–66 min. **SF12 probe advanced 1/4 turn at 08:30, inside the swap (pre-move session ends 07:43:01, post-move from 08:35:07) → kilosort 08:35→~12:30 unstable; second advance in 14 h.** **THE 3.5 V RULE measured today (see Lessons): 3.60 = 30–50 min, 3.55 = 15–20, 3.50 = 5–15 min to auto-stop.** Cards ~46% by tonight, ~68% by the 9/11 AM round → format then. Day shift: knee ~19:40–20:40, auto-stop ~21:00–22:00 → evening round 18:00 as planned (could run to ~19:30). |
| **9/10 18:36–19:47** evening | **EVO 512, ADC lane ON**; SF08's card formatted (0%), the other four NOT (43–44%) → format at the 9/11 AM round | Fresh (heartbeat at Start – the only fresh reading in ADC mode): **all five 1000 mAh (803060)** – SF07 4.16, SF08 4.17, SF09 4.10, SF10 4.15, SF12 4.19. | Day cells (900, EVO 512, ADC on from ~15:00) **manually Stopped 18:39–18:51 after 10.3 h; real voltages read at the next Start: SF07 3.72, SF08 3.71, SF09 3.68, SF10 3.67, SF12 3.74** (mean 3.70 vs 3.69 / 3.76 / 3.74 at 10 h in the 9/8–9/9 EVO batches → **no measurable ADC cost**). **BATTERY READING FROZEN IN ADC MODE:** ads AND heartbeat stuck at the Start value while recording (3.80–3.85 all afternoon), refreshed only at a Record Start → forecast blind, auto-stop presumed dead → **tonight by the clock: Stop at the 07:00 round (11.3–11.5 h), SF09 (4.10) first; a mid-night touch shows nothing.** End clusters 15–43 anchors (70–256 s); start clusters 15–20 after the final Starts (SF07 19:33:05, SF08 19:35:30, SF09 19:42:03, SF10 19:44:42, SF12 19:47:10); RTC written only while idle; guard stubs on all five. Fleet gap 54–56 min. Forecast tool now flags VFROZEN (8191354). |
| **9/11 08:04–09:48** AM | **EVO 512 all five, ALL FORMATTED** (0% at restart; SF08's was 23%) | Fresh (ads idle before the Start / heartbeat at Start): SF07 4.10 / 4.12, SF08 4.08 / 4.10, **SF09 3.98 / 4.00 – 200 mV under the 4.18 rule, it reaches the knee first → PM round by ~16:30, SF09 first**, SF10 4.24 / 4.26, SF12 4.24 / 4.24 (capacity of the day cells not stated). | Night cells (**all five 1000 mAh**) **manually Stopped 08:06–08:24 at 3.64–3.73 V real after 12.5–12.6 h** (SF07 3.70, SF08 3.64, SF09 3.67, SF10 3.73, SF12 3.65; end anchors 15–26 each; none auto-stopped, SF08 past the knee and diving 46 mV/h at the Stop). Phase-matched against the 900s of the 9/9 night (3.48–3.64 at 12.5–12.9 h): +20 (SF08) … +250 mV (SF10) → **the 1000 mAh cells buy 0.5–1.5 h, not more**; SF08's 1000 was the weakest for the third time (9/6, 9/9, 9/10 nights) → number the cells from now on. **SF12's ad rec-counter froze 07:59:46–08:22 while it recorded on** (second telemetry freeze after SF07 9/5 05:36–05:56; the forecast flagged REC-FROZEN) → connected 08:22, heartbeat rec advancing, 25 anchors, clean Stop 08:24:11, **no reset**. Restarts: SF07 09:16:16, SF08 09:19:31 (its first Start 09:17:54 got no ack and the firmware aborted it 33 s later with **ERR 0602 F00 D20 – new code**; the retry was fine), SF09 09:22:25, SF10 09:24:41, SF12 09:47:47 (**SF12 was unreachable 08:26–09:44 – operator suspects the SD card slot; probe possibly broken – incident log 09:47**). Every logger ran a 30–100 s trial session before its final Start (tiny stubs on the cards). RTC writes only on idle loggers; mic off read back on all five before the Starts. |
| **9/11 18:22–19:24** evening | **EVO 512, cards NOT formatted** (SF08 23%, the other four 46% at restart) | Fresh (heartbeat at Start / ads idle at 19:41): SF07 4.17 / 4.08, SF08 4.20 / 4.08, SF09 4.20 / 4.08, SF10 4.12 / 4.06, SF12 4.21 / 4.10 (capacity not stated by the operator). Final Starts SF07 19:14:50, SF08 19:17:16, SF09 19:19:47, SF10 19:22:07, SF12 19:24:28, each after a ~33 s trial session; mic off read back on all five; RTC writes only on idle loggers; start anchors 24–27 each. **19:40: five non-implanted females released into the paddock (operator) – 10 animals from here.** | Day cells: knee anchor pass 16:51–16:58 (14–20 anchors, 65–96 s each, no RTC writes), then per the 9/6 protocol. **SF09 (installed at 3.98 V) auto-stopped ~17:32–17:36 at the 3.40 line after 8.2 h** (ad counter frozen at 29388 s; last touch 16:54:37–16:55:47, 15 anchors at 3.62 → tail ~40 min) – the round came before the other four: manual Stops **SF08 18:23:51 3.63, SF10 18:25:50 3.72, SF07 18:27:26 3.65, SF12 18:29:17 3.73 V real after 8.7–9.2 h** (end anchors 15–21 each). A 3.98 V install = 8.2 h to auto-stop vs 9+ h still above the knee for the 4.10–4.24 installs: the 4.18 rule again. |

## Cell table (auto-extracted; 9/1 23:41 onward is exact, earlier rows are partial)

`life h` = time from swap to the next swap **or** to the auto-stop; `auto-stopped` = recording
counter frozen over the last 3 samples **and** voltage at the ~3.40 V auto-stop line. A frozen
counter at a healthy voltage is a **manual Record Stop** at the round and is labelled as such
(the first auto-extraction mislabelled SF12 9/3 — fixed). Rows marked † span a history gap
(watchdog off / FM63 ad freeze) and are **not** single cells — several swaps happened inside
them (see Rounds). Card = model on the logger during that cell.

| cell start | rat | card | install V | end (last seen) | end V | min V | life h | auto-stopped / how it ended |
|---|---|---|---|---|---|---|---|---|
| 08-30 18:35 | SF11 | ? | 4.10 | 08-31 05:55 | 2.62 | 2.62 | 11.3 | brownout |
| 08-30 18:40 | SF08 | ? | 4.00 | 08-31 07:00 | 3.14 | 3.00 | 12.3 | |
| 08-30 18:45 | SF07 | ? | 4.08 | 08-31 07:00 | 3.38 | 3.38 | 12.3 | yes |
| 08-30 18:45 | SF10 | non-EVO | 4.08 | 08-31 03:30 | 2.84 | 2.84 | 8.8 | brownout |
| 08-30 20:00 | SF09 | ? | 4.00 | 08-31 06:40 | 3.34 | 3.34 | 10.7 | yes |
| 08-30 20:00 | SF12 | ? | 3.96 | 08-31 05:30 | 2.40 | 2.40 | 9.5 | brownout |
| 08-31 03:35 | SF10 | non-EVO | 3.06 | 08-31 04:45 | 3.06 | 3.04 | 1.2 | interim cell |
| 08-31 04:55 | SF10 | non-EVO | 3.22 | 08-31 06:40 | 3.00 | 3.00 | 1.7 | interim cell |
| 08-31 05:35 | SF12 | ? | 3.04 | 08-31 07:00 | 3.06 | 2.96 | 1.4 | interim cell |
| 08-31 07:00 † | SF09 | EVO → mixed → EVO | 4.10 | 09-02 07:51 | 3.66 | 3.62 | (gap) | |
| 08-31 07:00 † | SF10 | non-EVO → mixed → EVO | 4.14 | 09-02 07:51 | 3.70 | 3.66 | (gap) | |
| 08-31 07:00 † | SF11 | EVO → mixed → EVO | 4.12 | 09-02 07:51 | 3.72 | 3.72 | (gap) | |
| 08-31 07:05 † | SF12 | EVO → mixed → EVO | 4.12 | 09-02 07:51 | 3.42 | 3.42 | (gap) | |
| 08-31 07:10 † | SF08 | EVO → mixed → EVO | 4.06 | 09-02 07:51 | 3.48 | 3.46 | (gap) | |
| 08-31 07:30 † | SF07 | EVO | 4.12 | 09-02 07:51 | 3.66 | 3.64 | (gap) | |
| 09-02 08:21 | SF07 | EVO | 4.06 | 09-02 18:51 | 3.66 | 3.62 | 10.5 | swapped alive |
| 09-02 08:21 | SF08 | EVO | 4.20 | 09-02 18:51 | 3.72 | 3.70 | 10.5 | swapped alive |
| 09-02 08:21 | SF09 | EVO | 4.20 | 09-02 18:51 | 3.72 | 3.70 | 10.5 | swapped alive |
| 09-02 08:21 | SF10 | EVO | 4.24 | 09-02 18:51 | 3.74 | 3.72 | 10.5 | swapped alive |
| 09-02 08:21 | SF11 | EVO | 4.14 | 09-02 18:51 | 3.70 | 3.68 | 10.5 | swapped alive |
| 09-02 08:21 | SF12 | EVO | 4.24 | 09-02 18:51 | 3.74 | 3.74 | 10.5 | swapped alive |
| 09-02 19:01 | SF07 | **Sonic 512** | 4.22 | 09-03 07:21 | 3.40 | 3.40 | 12.3 | **yes 04:17** (9.2 h) |
| 09-02 19:01 | SF08 | EVO | 4.20 | 09-03 07:21 | 3.74 | 3.74 | 12.3 | swapped alive |
| 09-02 19:01 | SF09 | EVO | 4.16 | 09-03 07:21 | 3.64 | 3.62 | 12.3 | swapped alive |
| 09-02 19:01 | SF10 | EVO | 4.18 | 09-03 07:21 | 3.66 | 3.64 | 12.3 | swapped alive |
| 09-02 19:01 | SF11 | EVO | 4.16 | 09-03 07:21 | 3.72 | 3.68 | 12.3 | swapped alive |
| 09-02 19:01 | SF12 | EVO | 4.22 | 09-03 07:21 | 3.64 | 3.62 | 12.3 | swapped alive |
| 09-03 08:06 | SF07 | Sonic 512 → EVO 17:50 | 4.20 | 09-04 08:06 | 3.60 | 3.60 | **24.0** | 1000 mAh, swapped alive |
| 09-03 08:06 | SF08 | **Sonic 512** | 4.10 | 09-03 17:21 | 3.50 | 3.40 | 9.2 | yes (afternoon; 16:03 restart stub) |
| 09-03 08:06 | SF09 | **Sonic 512** | 4.14 | 09-03 17:21 | 3.46 | 3.40 | 9.2 | stopped for the round 16:53, at the knee |
| 09-03 08:06 | SF10 | **Pro Endurance 256** | 4.20 | 09-03 17:21 | 3.50 | 3.50 | 9.2 | stopped for the round 16:53, at the knee |
| 09-03 08:06 | SF11 | **Pro Endurance 128** | 4.06 | 09-03 17:21 | 3.40 | 3.40 | 9.2 | yes (3.40 V; 580-s restart stub died again) |
| 09-03 08:11 | SF12 | **Insignia 128** | 4.20 | 09-03 17:21 | 3.62 | 3.62 | 9.2 | **manual Record Stop 16:55, alive (3.62 V)** |
| 09-03 18:01 | SF08 | EVO | 4.20 | 09-04 08:11 | 3.52 | 3.52 | 14.2 | swapped alive |
| 09-03 18:01 | SF09 | EVO | 4.20 | 09-04 08:11 | 3.44 | 3.40 | 14.2 | swapped at the knee |
| 09-03 18:01 | SF10 | EVO | 4.22 | 09-04 08:21 | 3.38 | 3.38 | 14.3 | yes |
| 09-03 18:01 | SF11 | EVO | 4.18 | 09-04 08:21 | 3.50 | 3.50 | 14.3 | yes |
| 09-03 18:01 | SF12 | EVO | 4.22 | 09-04 08:06 | 3.40 | 3.40 | 14.1 | yes |
| 09-04 08:11 | SF07 | EVO | 4.18 | 09-04 20:11 | 3.70 | 3.68 | 12.0 | swapped alive |
| 09-04 08:11 | SF12 | EVO | 4.24 | 09-04 20:11 | 3.72 | 3.70 | 12.0 | swapped alive |
| 09-04 08:16 | SF08 | EVO | 4.14 | 09-04 20:11 | 3.66 | 3.64 | 11.9 | swapped alive |
| 09-04 08:16 | SF09 | EVO | 4.14 | 09-04 20:11 | 3.66 | 3.62 | 11.9 | swapped alive |
| 09-04 08:26 | SF10 | EVO | 4.22 | 09-04 20:11 | 3.70 | 3.68 | 11.8 | swapped alive |
| 09-04 08:26 | SF11 | EVO | 4.20 | 09-04 20:11 | 3.70 | 3.68 | 11.8 | swapped alive |
| 09-04 20:27 | SF10 | EVO | 4.08 | 09-05 06:58 | 3.52 | 3.52 | 10.5 | **yes 06:58**; zombie restarts 07:00→07:29 and 08:05→~08:30 — **RETIRED** |
| 09-04 20:20 | SF07 | EVO | 4.16 | 09-05 08:3x | 3.64 | 3.64 | 12.3 | stopped at the edge (~08:31–08:45) |
| 09-04 20:25 | SF09 | EVO | 4.18 | 09-05 08:3x | 3.64 | 3.62 | 12.2 | stopped at the edge (~08:31–08:45) |
| 09-04 20:33 | SF12 | EVO | 4.18 | 09-05 08:4x | 3.58 | 3.58 | 12.2 | slid 3.66→3.58 from 08:00; stopped at the edge; 210 anchors 07:30–08:10 |
| 09-04 20:23 | SF08 | EVO | 4.12 | 09-05 08:45 | 3.68 | 3.68 | 12.4 | 1000 mAh, manual Stop, alive |
| 09-04 20:31 | SF11 | EVO | 4.12 | 09-05 08:45 | 3.70 | 3.70 | 12.3 | 1000 mAh, manual Stop, alive |
| 09-05 09:33 | SF07 | Sonic 512 | 4.22 | 09-05 18:00 | 3.62 | 3.62 | 8.5 | manual Stop for the round (probe move 13:15–13:31 split the session, same cell) |
| 09-05 09:35 | SF08 | Sonic 512 | 4.18 | 09-05 18:03 | 3.58 | 3.58 | 8.5 | manual Stop for the round |
| 09-05 09:47 | SF09 | Sonic 512 | 4.22 | 09-05 18:05 | 3.62 | 3.62 | 8.3 | manual Stop for the round |
| 09-05 09:39 | SF10 | Pro Endurance 256 | 4.22 | 09-05 18:06 | 3.60 | 3.60 | 8.5 | manual Stop for the round (logged under SF11's ID by the console) |
| 09-05 09:45 | SF11 | Pro Endurance 128 | 4.18 | 09-05 18:08 | 3.60 | 3.60 | 8.4 | manual Stop for the round (probe move 15:02–15:11 split the session, same cell; Stop logged under the corrupted name AS-NBB-AOG35) |
| 09-05 09:45 | SF12 | Insignia 128 | 4.24 | 09-05 18:02 | 3.64 | 3.64 | 8.3 | manual Stop for the round |
| 09-05 18:47 | SF07 | EVO 512 | 4.21 | 09-06 06:54 | 3.67 | 3.66 | 12.1 | manual Stop for the round; 05:36–05:56 ad rec-counter freeze (NOT a stop – heartbeat continuous) |
| 09-05 18:51 | SF08 | EVO 512 | 4.18 | 09-06 06:55 | 3.71 | 3.70 | 12.1 | 1000 mAh (26 mV/h), manual Stop, alive |
| 09-05 18:54 | SF09 | EVO 512 | 4.19 | 09-06 06:59 | 3.65 | 3.64 | 12.1 | manual Stop for the round, at the knee |
| 09-05 18:57 | SF10 | EVO 512 | 4.22 | 09-06 07:00 | 3.72 | 3.72 | 12.0 | **stopped ~04:03 at 3.74 flat (contact suspected, not the cell)**; restarted 05:58 on the same cell, ran 1.0 h to the round's Stop |
| 09-05 18:59 | SF11 | EVO 512 | 4.16 | 09-06 07:02 | 3.70 | 3.70 | 12.0 | 1000 mAh (26 mV/h), manual Stop, alive |
| 09-05 19:03 | SF12 | EVO 512 | 4.17 | 09-06 06:57 | 3.60 | 3.58 | 11.9 | manual Stop at the edge; SF12 the logger drains 5–10% faster than the rest in every batch; ERR 0505 text 06:50 |
| 09-06 07:54 | SF07 | EVO 512 | 4.14 | 09-06 19:01 | 3.65 | 3.64 | 11.1 | manual Stop for the round; first past the knee (3.66 at 17:51); session split by the 12:31/13:29 probe move |
| 09-06 07:59 | SF08 | EVO 512 | 4.20 | 09-06 19:02 | 3.68 | 3.68 | 11.1 | manual Stop for the round |
| 09-06 08:02 | SF09 | EVO 512 | 4.18 | 09-06 19:05 | 3.67 | 3.66 | 11.1 | manual Stop for the round |
| 09-06 08:05 | SF10 | EVO 512 | 4.17 | 09-06 19:07 | 3.66 | 3.66 | 11.0 | manual Stop for the round; ran clean all day (no contact event) |
| 09-06 08:08 | SF11 | EVO 512 | 4.16 | 09-06 19:04 | 3.67 | 3.66 | 10.9 | manual Stop for the round; session split by the 12:32/13:34 probe move |
| 09-06 08:10 | SF12 | EVO 512 | 4.17 | 09-06 19:10 | 3.68 | 3.68 | 11.0 | manual Stop for the round |
| 09-06 19:40 | SF07 | EVO 512 | 4.20 | 09-07 08:06 | 3.65 | 3.64 | 12.4 | manual Stop for the round; knee touch 06:44 (30 anchors) |
| 09-06 19:43 | SF08 | EVO 512 | 4.10 | 09-07 08:08 | 3.60 | 3.60 | 12.4 | **1000 mAh that ran like a 900** (20:00 4.06; 3.66 at 12 h); manual Stop – number it, suspect |
| 09-06 19:46 | SF09 | EVO 512 | 4.22 | 09-07 08:09 | 3.64 | 3.64 | 12.4 | manual Stop for the round; knee touch 06:48 |
| 09-06 19:49 | SF10 | EVO 512 | 4.22 | 09-07 08:12 | 3.66 | 3.66 | 12.4 | manual Stop for the round; clean night (no contact event) |
| 09-06 19:52 | SF11 | EVO 512 | 4.19 | 09-07 08:13 | 3.53 | 3.53 | 12.3 | **implant fell off ~07:40** – Stop 08:12:41, logger retired; cell excluded from stats |
| 09-06 19:55 | SF12 | EVO 512 | 4.19 | 09-07 08:14 | 3.70 | 3.70 | 12.3 | 1000 mAh, manual Stop, alive |
| 09-07 08:52 | SF07 | EVO 512 | 4.10 | 09-07 09:07 | 3.96 | 3.91 | 0.25 | **weak cell: idle 4.10, 144 mV sag in the first minute → pulled after 15 min (stub session 08:52:49–09:07:34); RETIRE** (SF07's holder contact contributes, see round row) |
| 09-07 09:15 | SF07 | Sonic 512 | 4.08 | 09-07 16:54 | 3.50 | 3.50 | 7.7 | second cell of the morning; manual Stop; lowest of the batch (holder contact reads low under load) |
| 09-07 08:55 | SF08 | Sonic 512 | 4.20 | 09-07 16:55 | 3.66 | 3.66 | 8.0 | manual Stop for the round |
| 09-07 08:58 | SF09 | Sonic 512 | 4.19 | 09-07 16:57 | 3.64 | 3.64 | 8.0 | manual Stop for the round |
| 09-07 09:01 | SF10 | Pro Endurance 256 | 4.16 | 09-07 16:59 | 3.61 | 3.61 | 8.0 | manual Stop for the round |
| 09-07 09:04 | SF12 | Insignia 128 | 4.20 | 09-07 17:01 | 3.67 | 3.67 | 7.9 | manual Stop for the round; card was at 53% |
| 09-07 17:48 | SF07 | EVO 512 | 4.13 | 09-08 06:21 | 3.50 | 3.50 | 12.5 | manual Stop; diving 100 mV/h at the end (holder contact reads low under load); ERR 0505 at 06:05 |
| 09-07 17:51 | SF08 | EVO 512 | 4.17 | 09-08 06:30 | 3.64 | 3.64 | 12.6 | 1000 mAh, manual Stop, alive |
| 09-07 17:54 | SF09 | EVO 512 | 4.21 | 09-08 06:25 | 3.64 | 3.64 | 12.5 | manual Stop for the round |
| 09-07 17:57 | SF10 | EVO 512 | 4.21 | 09-08 06:26 | 3.61 | 3.61 | 12.5 | manual Stop for the round |
| 09-07 18:00 | SF12 | EVO 512 | 4.20 | 09-08 06:28 | 3.68 | 3.68 | 12.5 | 1000 mAh, manual Stop, alive |
| 09-08 07:15 | SF07 | EVO 512 | 4.22 | 09-08 18:55 | 3.68 | 3.68 | 11.7 | manual Stop for the round; 194 anchors at the midday pass |
| 09-08 07:17 | SF08 | EVO 512 | 4.09 | 09-08 18:54 | 3.53 | 3.53 | 11.6 | **UNDERCHARGED at install (4.09 < 4.18 rule)** → first to the knee all day; knee touch 18:49; manual Stop |
| 09-08 07:20 | SF09 | EVO 512 | 4.22 | 09-08 18:57 | 3.67 | 3.66 | 11.6 | manual Stop for the round |
| 09-08 07:23 | SF10 | EVO 512 | 4.23 | 09-08 18:58 | 3.66 | 3.66 | 11.6 | manual Stop for the round |
| 09-08 07:26 | SF12 | EVO 512 | 4.12 | 09-08 19:00 | 3.60 | 3.60 | 11.6 | **UNDERCHARGED at install (4.12)**; second to the knee; manual Stop |
| 09-08 19:37 | SF07 | EVO 512 | 4.16 | 09-09 08:16 | 3.58 | 3.58 | 12.6 | manual Stop for the round; lowest of the batch (holder contact reads low under load) |
| 09-08 19:39 | SF08 | EVO 512 | 4.18 | 09-09 08:17 | 3.64 | 3.64 | 12.6 | manual Stop for the round |
| 09-08 19:43 | SF09 | EVO 512 | 4.20 | 09-09 08:19 | 3.64 | 3.64 | 12.6 | manual Stop for the round |
| 09-08 19:45 | SF10 | EVO 512 | 4.22 | 09-09 08:20 | 3.65 | 3.65 | 12.6 | manual Stop for the round; commit receipt O000000000012F400 |
| 09-08 19:48 | SF12 | EVO 512 | 4.17 | 09-09 08:22 | 3.67 | 3.67 | 12.6 | manual Stop for the round; slowest of the batch overnight (20–36 mV/h) |
| 09-09 09:03 | SF07 | **EVO 256** | 4.22 | 09-09 17:55 | 3.73 | 3.73 | 8.9 | 256 fleet test; manual Stop 2 h early (rain); 1–6 h drain 65 mV/h |
| 09-09 09:06 | SF08 | **EVO 256** | 4.14 | 09-09 17:58 | 3.70 | 3.70 | 8.9 | 256 fleet test; under the 4.18 rule at install; 1–6 h drain 61 mV/h |
| 09-09 09:09 | SF09 | **EVO 256** | 4.21 | 09-09 17:59 | 3.71 | 3.71 | 8.8 | 256 fleet test; 1–6 h drain 65 mV/h (its own EVO-512 baseline 54.0 ± 3.6) |
| 09-09 09:11 | SF10 | **EVO 256** | 4.22 | 09-09 18:01 | 3.71 | 3.71 | 8.8 | 256 fleet test; 1–6 h drain 69 mV/h |
| 09-09 09:14 | SF12 | **EVO 256** | 4.12 | 09-09 18:02 | 3.68 | 3.68 | 8.8 | 256 fleet test; under the 4.18 rule at install; 1–6 h drain 58 mV/h |
| 09-09 18:38 | SF07 | EVO 512 | 4.19 | 09-10 07:17 | 3.64 | 3.64 | 12.7 | manual Stop for the round; knee pass 06:04 (18 anchors); out of BLE range 22:33–23:06 (rat at a corner), no gap |
| 09-09 18:42 | SF09 | EVO 512 | 4.16 | 09-10 07:20 | 3.52 | 3.52 | 12.6 | manual Stop for the round, deep in the dive |
| 09-09 18:45 | SF10 | EVO 512 | 4.19 | 09-10 07:18 | 3.48 | 3.48 | 12.6 | manual Stop **minutes before auto-stop** (3.48 under load; holder contact reads low) |
| 09-09 18:47 | SF12 | EVO 512 | 4.10 | 09-10 07:43 | 3.55 | 3.55 | 12.9 | “1000 mAh” finished inside the 900 pack; manual Stop; probe advanced 1/4 at the round (08:30) |
| 09-09 18:50 | SF08 | EVO 512 | 4.12 | 09-10 07:21 | 3.62 | 3.62 | 12.5 | “1000 mAh” ran as a 900 again (3.74 at 11.5 h, then 46 mV/h); manual Stop |
| 09-10 08:24 | SF07 | EVO 512 + ADC | 4.19 | 09-10 18:39 | 3.72 | 3.72 | 10.3 | manual Stop for the round; reading frozen at 3.80 all afternoon (ADC mode), 3.72 read at the next Start |
| 09-10 08:26 | SF08 | EVO 512 + ADC | 4.22 | 09-10 18:42 | 3.71 | 3.71 | 10.3 | manual Stop; frozen reading 3.82; card formatted at the round |
| 09-10 08:29 | SF09 | EVO 512 + ADC | 4.23 | 09-10 18:48 | 3.68 | 3.68 | 10.3 | manual Stop; frozen reading 3.82 |
| 09-10 08:32 | SF10 | EVO 512 + ADC | 4.24 | 09-10 18:50 | 3.67 | 3.67 | 10.3 | manual Stop; frozen reading 3.84 |
| 09-10 08:35 | SF12 | EVO 512 + ADC | 4.25 | 09-10 18:51 | 3.74 | 3.74 | 10.3 | manual Stop; frozen reading 3.84; probe advanced 1/4 at 08:30 |
| 09-10 19:33 | SF07 | EVO 512 | 4.16 | 09-11 08:06 | 3.70 | 3.70 | 12.6 | 1000 mAh (803060); ADC lane ON at the install, OFF again from the mic-off Start 20:44:13; manual Stop for the round (26 anchors), above the knee |
| 09-10 19:36 | SF08 | EVO 512 | 4.17 | 09-11 08:07 | 3.64 | 3.64 | 12.5 | 1000 mAh (803060); ADC lane ON at the install, OFF again from the mic-off Start 21:02:46; manual Stop (15 anchors) past the knee, diving 46 mV/h; **weakest 1000 for the third time → number this cell** |
| 09-10 19:40 | SF09 | EVO 512 | 4.10 | 09-11 08:09 | 3.68 | 3.67 | 12.5 | 1000 mAh (803060); ADC lane ON at the install, OFF again from the mic-off Start 20:49:12; manual Stop (17 anchors) at the knee |
| 09-10 19:44 | SF10 | EVO 512 | 4.15 | 09-11 08:15 | 3.72 | 3.73 | 12.5 | 1000 mAh (803060); ADC lane ON at the install, OFF again from the mic-off Start 20:56:12; manual Stop (15 anchors); best of the five |
| 09-10 19:47 | SF12 | EVO 512 | 4.19 | 09-11 08:24 | 3.66 | 3.65 | 12.6 | 1000 mAh (803060); ADC lane ON at the install, OFF again from the mic-off Start 21:05:19; ad rec-counter frozen 07:59:46–08:22 (recorded on); manual Stop (25 anchors), no reset |
| 09-11 09:15 | SF07 | EVO 512 (formatted) | 4.12 | 09-11 18:27 | 3.66 | 3.65 | 9.2 | day cell (capacity not stated); ad idle 4.10; final Start 09:16:16; knee anchors 16:51 (20); manual Stop for the round (15 anchors) |
| 09-11 09:18 | SF08 | EVO 512 (formatted) | 4.10 | 09-11 18:24 | 3.64 | 3.63 | 9.1 | day cell; ad idle 4.08 (under the 4.18 rule); first Start 09:17:54 failed (ERR 0602), final Start 09:19:31; knee anchors 16:53 (16); manual Stop for the round (16 anchors), first of the four |
| 09-11 09:21 | SF09 | EVO 512 (formatted) | 4.00 | 09-11 ~17:34 | 3.40 | – | 8.2 | day cell; **ad idle 3.98 – 200 mV under the 4.18 rule → AUTO-STOPPED ~17:32–17:36 at the 3.40 line** (ad counter frozen at 29388 s; 3.60 first read 16:41, 3.62 at the knee anchors 16:54:37–16:55:47, 15 anchors = last touch, tail ~40 min); idle RTC write 18:24 before the swap |
| 09-11 09:24 | SF10 | EVO 512 (formatted) | 4.26 | 09-11 18:26 | 3.72 | 3.72 | 9.0 | day cell; ad idle 4.24; final Start 09:24:41; knee anchors 16:55 (14); manual Stop for the round (16 anchors) |
| 09-11 09:45 | SF12 | EVO 512 (formatted) | 4.24 | 09-11 18:29 | 3.74 | 3.73 | 8.7 | day cell; ad idle 4.24; final Start 09:47:47 (unreachable 08:26–09:44, card slot suspected; **probe possibly broken – lab to check**); knee anchors 16:57 (15); manual Stop for the round (21 anchors), best of the five |
| 09-11 19:14 | SF07 | EVO 512 (46%) | 4.17 | (running) |  |  |  | night cell (capacity not stated); ad idle 4.08 at 19:41; trial 19:14:08–19:14:41, final Start 19:14:50 (27 anchors) |
| 09-11 19:16 | SF08 | EVO 512 (23%) | 4.20 | (running) |  |  |  | night cell; ad idle 4.08; trial 19:16:34–19:17:07, final Start 19:17:16 (24 anchors) |
| 09-11 19:19 | SF09 | EVO 512 (46%) | 4.20 | (running) |  |  |  | night cell; ad idle 4.08; trial 19:19:03–19:19:35, final Start 19:19:47 (24 anchors) |
| 09-11 19:21 | SF10 | EVO 512 (46%) | 4.12 | (running) |  |  |  | night cell; ad idle 4.06 (lowest – SF10 reads low under load); trial 19:21:22–19:21:56, final Start 19:22:07 (25 anchors); **07:00 round, SF10 first** |
| 09-11 19:23 | SF12 | EVO 512 (46%) | 4.21 | (running) |  |  |  | night cell; ad idle 4.10; trial 19:23:42–19:24:16, final Start 19:24:28 (25 anchors) |

## Retired cells

| cell | evidence | verdict |
|---|---|---|
| **900 mAh on SF10, 9/4 20:26 (install 4.08 V)** | lowest install of the batch; life 10.5 h to auto-stop (~06:58 9/5) vs 11-14 h for the same batch/card; 06:51 sag-and-rebound (high-IR fingerprint); restarted 07:00 on the same cell, held 15 min then slid 240 mV/h to a second auto-stop ~07:29 with no rebound. SF10 the logger ran its previous two cells normally (14.3 h, 11.8 h) -> not the logger. | **RETIRE.** Confirm with one full charge + rested reading: < 4.15 V = aged, bin it; 4.20 V = was undercharged, day-shift pool only, never overnight. Sharpie it. |

## Lessons banked

1. **Never pull a battery without Record Stop** (night 1). Low-voltage auto-stop commits; a
   pull or a brownout cliff does not. FM65 adds a 5-min directory checkpoint.
2. **Only the EVO 512 is a low-power card.** Same rats, same day (9/3): non-EVO cards → knee at
   ~9 h; EVO → 14.1–14.3 h. Sonic 512, Pro Endurance 256/128 and Insignia 128 all belong to the
   high-power group in the logger (the bench in `EXPERIMENT_sd_card_power.md` ranks them
   among themselves but has not measured the EVO yet). Fleet = EVO only, since 9/3 evening.
3. **Install voltage matters (per cell type)**: among the 900 mAh cells, 4.08–4.12 V installs
   die 1–2 h before 4.20–4.24 V ones — rule: ≥4.18 V rested or it does not go on a rat
   overnight. The 1000 mAh cells are full at ~4.08–4.12 V and are exempt. The 3.42 V (9/1) and
   3.78 V (9/1) mistakes cost a session tail each.
4. **Slopes are only comparable at matched post-install phase** — install-hour slopes carry
   surface charge; the 01:02/13:02 forecast is timed to be past it.
5. **12-h rounds vs 12–14 h EVO cells = 0–2 h margin.** Two 1000 mAh cells cover two loggers to
   ~13:00; more are not coming. So: cell triage by measured life (this log), full-charge rule,
   20:00 / 08:00–08:15 schedule, midnight Stop→Start as late as possible.
6. **Below 3.6 V the clock runs fast.** Measured on every cohort-3 auto-stop: 3.60 → 30–50 min, 3.55 → 15–20, 3.50 → 5–15. A logger reading 3.5x in the ads is not “an hour of margin”, it is the next poll or two. Time rounds off the knee (3.68), never off the dive.
7. **The ADC/microphone lane freezes the battery reading.** With the lane on, the logger's battery variable is read at Record Start and never again while recording – ads and heartbeat both report the install value all day (9/10: 3.80–3.85 for 3 h while the cells were really at 3.67–3.74). No forecast, no knee touch, no auto-stop: run such a shift by the clock and read the real voltage only at a Start. The tool flags it as VFROZEN.
8. **A frozen rec counter in the ads is not a hang.** Twice now (SF07 9/5 05:36–05:56, SF12 9/11 07:59:46–08:22) the advertised rec field stopped updating while the logger recorded on; the ads and a real stop look identical. The forecast flags REC-FROZEN; before any reset, connect and read the heartbeat rec counter – if it advances, anchor and Stop normally (SF12 got 25 anchors and a clean Stop).
9. **1000 mAh vs 900 mAh, measured on five cells the same night (9/10→9/11):** at 12.5–12.6 h the 1000s read 3.64–3.73 V real where the 900s of the night before read 3.48–3.64 at 12.5–12.9 h – worth 0.5–1.5 h by the 3.5 V rule, no more. The spread between cells (SF08's 1000 was the weakest for the third time) is as large as the 900→1000 gain, so cells must be numbered and tracked individually.

## Regenerate the cell table

```python
# python (cv env): swaps = upward jump >= 0.15 V between consecutive 5-min samples (<= 60 min apart)
import csv; from datetime import datetime
rows={}
for r in csv.DictReader(open(r"E:\recording_qc\neurologger_telemetry_history.csv",encoding="utf-8-sig")):
    if r["ts_local"]<"2026-08-30" or not r["battery_v"]: continue
    lab=r["label"].split(" ")[0]; ts=datetime.strptime(r["ts_local"][:19],"%Y-%m-%d %H:%M:%S")
    rows.setdefault(lab,[]).append((ts,float(r["battery_v"]),float(r["rec_elapsed_s"] or 0)))
for lab,lr in rows.items():
    lr.sort(); s=0
    for i in range(1,len(lr)):
        if lr[i][1]-lr[i-1][1]>=0.15 and (lr[i][0]-lr[i-1][0]).seconds<=3600:
            seg=lr[s:i]; print(lab, seg[0][0], seg[0][1], seg[-1][0], seg[-1][1], round((seg[-1][0]-seg[0][0]).total_seconds()/3600,1)); s=i
```
