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
- 1000 mAh cell ≈ **17–24 h**. Auto-stop lands at ~3.40 V; knee 3.68 V; the dive below the
  knee takes ~2 h (regular) / ~4 h (1000 mAh).
- Install **≥4.18 V rested** — the 4.08–4.12 V installs have been the first to die every time.

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
| **9/4 20:10–20:33** evening | all EVO | Fresh: SF07 4.16, SF08 4.12, SF09 4.18, **SF10 4.08 (below the ≥4.18 rule)**, SF11 4.12, SF12 4.18. Expect the 4.08–4.12 installs (SF10, SF08, SF11) to die first, ~08:00–08:45 9/5; the 01:02 forecast gives the order. |

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
| 09-04 20:10–20:33 | all six | EVO | 4.08–4.18 | (running) | | | | current cells |

## Lessons banked

1. **Never pull a battery without Record Stop** (night 1). Low-voltage auto-stop commits; a
   pull or a brownout cliff does not. FM65 adds a 5-min directory checkpoint.
2. **Only the EVO 512 is a low-power card.** Same rats, same day (9/3): non-EVO cards → knee at
   ~9 h; EVO → 14.1–14.3 h. Sonic 512, Pro Endurance 256/128 and Insignia 128 all belong to the
   high-power group in the logger (the bench in `EXPERIMENT_sd_card_power.md` ranks them
   among themselves but has not measured the EVO yet). Fleet = EVO only, since 9/3 evening.
3. **Install voltage matters**: 4.08–4.12 V installs die 1–2 h before 4.20–4.24 V ones.
   Rule: ≥4.18 V rested or it does not go on a rat overnight. The 3.42 V (9/1) and 3.78 V
   (9/1) mistakes cost a session tail each.
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
