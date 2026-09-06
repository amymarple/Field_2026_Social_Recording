# Cohort-3 neurologger battery log (SF07–SF12)

Released ~19:00 2026-08-30. One row per **battery cell on a logger** — start = the swap
(upward jump ≥150 mV in the advertised voltage), end = the next swap or the auto-stop.
Auto-extracted from `E:\recording_qc\neurologger_telemetry_history.csv` (5-min advertisement
snapshots) on 2026-09-04 20:40; rounds before 9/1 23:41 are reconstructed from the incident
log / connected-heartbeat decodes because the ad watchdog was off (troubleshooting) and FM63
froze advertisement telemetry during recording (8/31 → 9/1). Card model per row is from the
operator's read-off (only the physical read is authoritative). Regenerate the table any time
with the extraction snippet at the bottom.

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
| **9/6 06:54–08:10** AM | **all EVO** (cards NOT formatted, 19–23% at restart) | Fresh (heartbeat, under load): SF07 4.14, SF08 4.20, SF09 4.18, SF10 4.17, SF11 4.16, SF12 4.17. 1000 mAh now on **SF08 + SF12** (operator 08:20: SF11's 1000 mAh went to SF12, SF11 got a 900) - expect the four 900s (SF07/09/10/11) to stop ~20:00-22:00, SF08/SF12 to run past 01:00. **14:18 CHECK: SF08 and SF12 drain 55-60 mV/h, identical to the 900s (the 9/5-night 1000s did 26-37 mV/h and sat at 3.94 V after 5 h; these are at 3.80 after 6 h) - whatever is in SF08/SF12 is NOT behaving as a full 1000 mAh (not charged? mixed up?). Treat all six as 900s tonight: auto-stop 19:40-22:00, evening round by 18:45.** | Night cells: **manually Stopped 06:54–07:02 at 3.60–3.72 V after 11.9–12.1 h** – none auto-stopped, 14–16 end anchors each (64–73 s connects); SF12 first to the edge again (3.58 at 06:56); the 1000 mAh on SF08/SF11 still at 3.70–3.71. **SF10 stopped ~04:03 at 3.74 V flat** (counter froze at 32745 s; ads unchanged before/after) → operator restarted it 05:58 on the same cell (3.74–3.76 under load, ran 1.0 h to the round's Stop 07:00) and suspects a loose battery contact – the 9/5 'retired' cell may have been innocent; check SF10's holder. SF07 05:36–05:56 ad rec-counter freeze looked like a stop but the heartbeat (40529 s at 06:03) proved continuous recording. Midnight connect-only pass 00:21–00:36: 13–24 anchors each. Restarts 07:53–08:10 (Resync on idle loggers only, guard files, 14–18 start anchors) = ~1-h fleet gap. Expect 900 mAh on EVO 12–14 h → ~20:00–22:00; the 1000s to ~01:00. |

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
| 09-06 07:53–08:10 | all six | EVO 512 (not formatted, 19–23%) | 4.14–4.20 | (running) |  |  |  | day shift; all six drain 55-63 mV/h = 900-class (the "1000 mAh on SF08 + SF12" is not visible in the data - see the round row); 900 on SF07/09/10/11; SF07 + SF11 sessions split by 1/4-turn probe moves (Stop 12:31:20 / 12:32:32 -> Start 13:29:42 / 13:33:38, same cells) |

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
