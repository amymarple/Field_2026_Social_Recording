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
| **9/5 08:40–09:50** AM | **high-power set, inferred from fill rates 10:00→13:00 (confirm by read-off):** SF07/08/09 ~1.7 %/h = 512 GB (Sonic), SF10 3.4 %/h = 256 GB (Pro Endurance, not formatted, 33→45%), SF11/SF12 7 %/h = 128 GB (Pro Endurance / Insignia). Drain 92–109 mV/h in the first 3.5 h vs ~65 on EVO = ×1.5–1.7. | Night cells (9/4 20:20–20:33): the 900s ran **12.2–12.5 h** and were stopped at 3.58–3.64 V, right at the auto-stop edge (~08:31–08:45); the 1000 mAh on SF08/SF11 were alive at 3.68–3.70 after 12.3 h. **SF10's 4.08 V cell died three times** (~06:58, ~07:29 after a zombie restart at 07:00, ~08:30 after another at 08:05) → retired. **Anchor-only BLE pass 08:00–08:10, no handling**: 14–16 anchors per logger; SF12 (the first to slide) was ridden 07:30–08:10 = 210 anchors. **All six Record-Stopped ~08:40–08:50; fresh cells at 09:31 (SF07 4.22, SF08 4.18, SF09 4.22, SF10 4.22, SF11 4.18, SF12 4.24); Rec Start 09:33–09:50 → a ~50-min fleet-wide recording gap during the swap + 5 card formats.** Round deliberately late: operator cannot do dawn, and with 8-h cards the morning round should sit as late as the night cells allow. |

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
| 09-05 09:31 | all six | high-power set (inferred: Sonic 512 ×3 / PE 256 / PE 128 / Insignia 128) | 4.18–4.24 | (running) | | | | 13:02 forecast: auto-stop 18:04–18:47 → evening round by 17:00; 1000 mAh not yet distinguishable (fleet 92–109 mV/h); **SF07 session split by a probe move (Stop 13:15:40 → Start 13:31:19, same cell)**; 14:47: all six 3.74–3.78 V, auto-stop 17:55–18:43 → PM round by 16:55 |

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
