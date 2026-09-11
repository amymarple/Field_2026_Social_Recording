---
name: field-log
description: Log a cohort field event the standard way - battery round, Stop/Start, anchor pass, probe advance, reset or config change, incident, animal behaviour observation. Full entry goes to the incident log / battery log / sync repo FIRST; Notion gets a 4-8 line digest with pointers. Use whenever the operator says "log ...", "记录下 ...", "mark in notion ...", "log 下 ...".
---

# /field-log - how a field event gets written down

One rule: **the incident log is the system of record; Notion is a digest with pointers; behaviour has its own
table + CSV.** Nothing is ever deleted - if a Notion row must shrink, the old wording is archived first.
Everything written to a file is English (Chinese stays in chat). Times are ET (local); the console log is UTC.

## 0. Classify the event (decides where it goes)

| Event | Incident log | BATTERY_LOG | Sync repo | Notion day row | Behaviour table + CSV |
|---|---|---|---|---|---|
| Battery round (Stop/Start, swap, card) | yes | yes (rows) | mirror | 1-2 lines | - |
| Anchor / Resync pass | yes (verified counts) | - | mirror | 1 line | - |
| Probe advance (e.g. "SF12 turn 1/4") | yes | note in the row | mirror | 1 bold line + pre/post session boundary | - |
| Reset / hang / config change / software | yes | if it changes drain | mirror + dedicated note if the lab needs boundaries | 1-2 lines | - |
| Data-quality incident (outage, noise, contamination) | yes | - | mirror + boundaries CSV/note | 1-2 lines in Issues, bold | - |
| Animal behaviour (nesting, REM twitch, pile, corner rest) | one line | - | CSV row | **nothing** | yes (both) |

Mixed messages ("换完电池了,log 8:30 SF12 turn 1/4") are several events - handle each.

## 1. Verify from the machine record before writing anything

Never log an operator claim as verified unless the record shows it. Say "operator-reported" otherwise.

- Console BLE log: `C:\Users\Cornell\AppData\Local\CE32_console\ble_messages.csv` (strip NUL bytes; UTC, local = UTC-4).
  Columns ts, launch-id, device name, opcode, len, hex payload. Name suffix -> logger: 3111=SF07, E131=SF08,
  62DB=SF09, 0151=SF10, 21B1=SF12.
  - 0xAF heartbeat: rec s = LE u32 bytes 0-3; V = LE u16 bytes 4-5 x 2.0142e-4.
  - 0x8F sync_live anchor (~5 s cadence while connected) - count and duration per logger = the anchor pass.
  - 0x8B RTC write (Resync) - must land only on an IDLE logger (rec 0); flag any that hit a recording one.
  - 0x85 text (hex ASCII): "Rec Start", "Rec Stop", "RTC SET OK", "ERR 0505/0503/0702 ..." (harmless).
  - 0x8E Rec Start command; 0x90 = 512-byte config block (byte 28 = 0x08 -> ADC/mic lane ON: NEVER re-enable,
    it injects a 312.5 Hz pulse train on all 64 channels and freezes the battery reading).
  - 0xAD preview waveform - noise for these analyses, filter out.
- Telemetry: `E:\recording_qc\neurologger_telemetry_history.csv` (5-min polls; ts_local, device, label, age_min,
  battery_v, storage_pct, rec_elapsed_s - skip age_min > 3), `neurologger_connected_telemetry.csv`,
  `neurologger_alive_log.txt`.
- Battery forecast: `powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -DryRun -RoundHours 7,18`
  (rig repo). VFROZEN = the ad's battery sample stopped updating; plan by cell-hours then.
- Session start for behaviour rows: the 0x85 "Rec Start" time of that logger; rec_s = observation time - session start.
- Live surfaces stay off limits (D:\Wiser\data never; open `.mp4`/`.wav` without `_to_` never) - see CLAUDE.md.

## 2. Incident log - the full entry, written FIRST

File: `E:\recording_health_reports\incident_log.md` - append-only, CRLF, UTF-8, English.

```
## YYYY-MM-DD HH:MM - <one-line title with the verdict in it>

- <who/what/when, with the verified times and voltages>
- <what the record showed (counts, times, V) and what was NOT verifiable>
- <analysis consequence: session splits, exclusion / contamination windows, provenance boundary, kilosort window>
- <lesson or rule, if one was born>
```

- The heading time is the event time (not the writing time); keep entries in the order written (append).
- Bold the analysis flag when there is one (**KILOSORT ...**, **EXCLUDE ...**, **PROVENANCE ...**).
- Behaviour gets one line: `## ... - Behaviour note: <animal> <behaviour> (operator, video)` plus the rec seconds.
- Edit scripts, not heredocs: Bash heredocs mangle backslashes on this PC. Write a small Python script with the
  Write tool (`s.replace(old, new)` with `assert s.count(old) == 1`, keep CRLF, `newline=""`), run it with
  `python script.py`; use `PYTHONIOENCODING=utf-8` when printing.

## 3. BATTERY_LOG_cohort3.md (rig repo) - every battery fact

- Cell rows: `| MM-DD HH:MM | SFxx | <card> | <install V> | <stop date time> | <stop V> | <real V> | <hours> | <note> |`;
  a running cell is `(running)` and is closed at the next round with the real Stop V.
- Round rows: `**M/D HH:MM-HH:MM** morning|evening | <card>, <mode> | ...` with per-logger Stop V / hours / Start V.
- Lessons are numbered bullets in the model section; correct a wrong claim in place and say it was corrected.
- Commit and push from the rig repo (outbound only: `git add <file>`, `git commit`, `git push`; never pull there).

## 4. field2026-sync (the lab reads THIS, not Notion)

- Mirror: copy the whole incident log to `from-field/<YYYY-MM-DD>_cohort3-incident-log.md` after each append.
- Dedicated notes when the lab needs machine-readable boundaries: `from-field/<date>_<topic>.md` and `.csv`
  (one row per piece/boundary, ET times, `end_type`, config-write times, notes).
- Answer a lab task in place: append a `## Field response (date)` table to `tasks/<file>.md`, then `git mv` it to
  `tasks/done/`.
- Push pattern (GitHub often times out at ~21 s): `git push -q || (git pull -q --rebase && git push -q)`, then
  verify with `git log origin/main --oneline -1`.

## 5. Animal behaviour - two copies, never in the operations column

1. Notion behaviour table (bottom of the cohort page, "Animal behaviour log"), one row:
   `Date | Time (ET) | Animal(s) | Behaviour | Source | Logger session -> rec (s) | Observer | Notes / analysis hook`.
2. `field2026-sync/from-field/behaviour_observations_cohort3.csv`, same observation, columns
   `date,time_start_et,time_end_et,animals,behaviour,source,logger_session_start_et,rec_s_start,rec_s_end,observer,notes`
   (animals `;`-separated, times HH:MM, empty when unknown). Commit + push.
3. One line in the incident log (section 2). Nothing about behaviour goes into the Notion day row.

## 6. Notion day row - the digest (4-8 lines), last

Page `3c23b0530d4a8152a204cce3afa11671`, table "Observation log", cells in order:
`Date | Day # | Time | Observer | Equipment | Rig / logger operations | Issues / anomalies (analysis flags) | Device condition`.

- **Time**: the day's timeline in one line (`AM round 07:17-08:35; SF12 move 08:30; PM round 18:36-19:47`).
- **Rig / logger operations**: what was done with times and voltages; probe moves and session splits in bold.
- **Issues / anomalies**: analysis flags in bold (contamination, KILOSORT window, provenance), one-line rule if
  born, then ALWAYS the pointer: `Details -> incident_log YYYY-MM-DD HH:MM, HH:MM; BATTERY_LOG M/D rows;
  Notion behaviour log (HH:MM SFxx <behaviour>)` (use the real arrow "→" in Notion).
- **Device condition**: Stop V range, fresh-cell range, anything reading low.
- Equipment column: ✅ clean day, ⚠️ anything the analysis must know about.
- Never paste the full incident-log entry; never write behaviour here.

Mechanics (`notion-update-page`, `command: update_content`, `old_str` -> `new_str`):
- `notion-fetch` the page first; a >50k result lands in a tool-results file (JSON-escaped: `\n`, `\"`, `\\`) -
  unescape before matching. `old_str` must equal Notion's stored markdown incl. escapes (`\~` for `~`).
- Updates are atomic (one bad `old_str` fails all) - one cell per call. Anchor on the cell's last words + `</td>`;
  if another session may have appended, re-fetch and anchor again. Appended text can land inside an open
  `**bold**` segment - close/reopen the bold explicitly.
- If a row must be rewritten (compression), archive the verbatim table first
  (`NOTION_OBSERVATION_LOG_ARCHIVE_cohort3.md` in the rig repo + the sync mirror), then replace the whole `<tr>`.

## 7. Reply to the operator (chat, Chinese is fine)

Three to six lines: what was verified (times, V, counts), what was logged where (incident-log heading time,
battery-log row, sync commit hash, Notion cell), and the one consequence that matters next (next round time,
a rule, a card to format). No file dumps.

## Reference

- Loggers: SF07=3079, SF08=3062, SF09=3077, SF10=306b, SF12=3059 (WISER tags); SF11 retired 09-07.
- Battery model (cohort 3): EVO 512 night 12.5-12.9 h to a manual Stop at 3.48-3.64 V; knee 3.68; the 3.5 V rule:
  first ad <= 3.60 V -> 30-50 min to auto-stop, <= 3.55 -> 15-20, <= 3.50 -> 5-15. Charge 1000 mAh cells to 4.2 V;
  install rule >= 4.18 V rested. SF07/SF10 read low under load (holder contact).
- Handling rule: rats are caught once per round, all together; BLE-only touches are free.
- Memory notes behind this skill: `notion-observation-log-is-a-digest`, `notion-behaviour-log-separate-table`.
