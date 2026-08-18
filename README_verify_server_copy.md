# Verify a Field-PC → Server Copy (agent instructions)

You are an AI agent (or a human) on the **analysis server / receiving computer**. Data
was copied here from the field recording PC of the 2026 rat social-sleep study with
`copy_to_analysis.ps1` (robocopy, copy-only). Your job: **decide whether the copy is
complete**, and produce a precise list of anything missing so the field-PC side can
re-run the copy for exactly those days.

You have NO access to the source machine. Everything you need is in this document
plus the copied tree itself. Written 2026-08-18; numbers below were measured on the
live source that day.

---

## 1. What should exist — expected tree

The copy destination root (call it `DEST`, whatever directory this file sits next
to / the share root) should contain:

```
DEST\
  Reolink_record\CH01 … CH08          8 video streams (hourly MP4)
  thermal_record\108_thermal          4 thermal-camera streams (hourly MP4)
                \108_visual
                \109_thermal
                \109_visual
  ultramic_record\MIC01               ultrasound audio, 384 kHz WAV (hourly)
                 \MIC02               ultrasound audio, 250 kHz WAV (hourly)
  Wiser_backup\snapshots\             daily SQLite snapshots (~03:30 daily)
              \incremental\           incremental CSV exports
              backup_log.txt, backup_state.json, …
```

**14 media streams total.** A missing stream FOLDER means a whole modality/channel
was never copied — that is always a finding.

The same folders may also hold files from EARLIER cohorts (the field PC keeps
everything until it is manually offloaded, and a full no-`-Date` copy brings old
days along). Verification is scoped to the current cohort: segments ending before
the per-stream start times below are ignored. For a different cohort, edit the
`EPOCH`/`DEFAULT_EPOCH` constants in the checker.

Per-stream recording start times (files before these cannot exist):

| Stream | First data (local, America/New_York) |
|---|---|
| CH01–CH08 | 2026-08-15 00:03 |
| 108/109 thermal+visual | 2026-08-15 00:07 |
| MIC01 | 2026-08-15 13:56 |
| MIC02 | 2026-08-16 16:29 |

## 2. The filename contract (parse this, trust nothing else)

Every media segment is named:

```
<stream>_YYYY-MM-DD_HH-MM-SS_to_HH-MM-SS.<mp4|wav|flac>     e.g.
CH05_2026-08-17_13-00-01_to_14-00-01.mp4
108_thermal_2026-08-17_13-00-55_to_14-00-55.mp4
MIC01_2026-08-17_13-00-00_to_14-00-00.wav
```

- `<stream>` may itself contain `_` (e.g. `108_thermal`) — parse from the RIGHT.
- Segments are ~1 hour, aligned to the wall clock **with per-stream offsets of up
  to a minute** (`…-00-55` is normal). Do NOT require :00:00 boundaries.
- The `_to_` end time is on the SAME date except when a segment crosses midnight
  (`…_23-00-00_to_00-00-00` ⇒ end = next day).
- A file WITHOUT `_to_` is a still-open, still-being-written segment. The copier
  **deliberately never copies these** — so on the server the newest hour of every
  stream is always absent. That is not a finding.

## 3. Completeness = chain continuity, not file counts

For each of the 14 streams:

1. Collect its files, parse start/end datetimes from names, sort by start.
2. Walk the chain: for consecutive segments, `gap = next.start − prev.end`.
   - `gap ≤ 90 s` → continuous (rollover jitter).
   - `gap > 90 s` → **HOLE**: data missing between those timestamps. Report
     stream + both timestamps + gap length.
   - Negative gap (overlap) → benign (recorder restart double-covers); ignore.
3. The chain should start at the stream's first-data time (±1 h) and end within
   ~2 h of the newest segment anywhere in the tree (the open segment + the
   just-closed one may still be pending the next copy run).
4. Expect ~24 files per stream per full day (23–25 is normal around restarts).

Known benign gaps (do not flag):
- Sunday ~minutes-long gap on all CH* simultaneously (NVR weekly reboot).
- A short gap on ALL streams around 16:00 daily is possible (logger-resync window
  disturbs nothing, but recorder restarts have happened at day boundaries).
- MIC02 nothing before 2026-08-16 16:29; MIC01 nothing before 08-15 13:56.

## 4. Size sanity (catches truncated copies)

| Stream | Healthy hourly size | Hard floor (bytes/sec of segment) |
|---|---|---|
| CH01–CH08 | 1.5–2.7 GB | > 20 kB/s |
| 108/109_visual | ~0.6 GB | > 5 kB/s |
| 108/109_thermal | ~40 MB | > 2 kB/s |
| MIC01 (384 kHz 16-bit mono WAV) | ~2.58 GiB | **exact**: 768 000 B/s × duration ±1% |
| MIC02 (250 kHz 16-bit mono WAV) | ~1.68 GiB | **exact**: 500 000 B/s × duration ±1% |

- WAV is uncompressed CBR ⇒ `size ≈ rate × duration_from_filename` is a strong
  integrity check; a mismatch means a truncated copy.
- Any 0-byte file = failed copy. Any video segment below its floor = suspect.
- Apply size checks only to segments **≥ 10 min**. Short restart stubs (a camera
  drop + supervisor restart, or the first segment after setup) legitimately have
  odd bitrates / partially-filled audio and would false-flag (verified against the
  live source 2026-08-18).
- Robocopy is resumable: re-running the copy on the field PC heals size mismatches
  and fills holes; nothing needs deleting on the server first.

For Wiser_backup: `snapshots\` should hold one dated `.sqlite` per day from
2026-08-15 through yesterday, sizes monotonically growing (cumulative DB).

## 5. Ready-to-run checker

Save as `verify_copy.py` next to the data and run `python verify_copy.py DEST`
(needs only the standard library). It implements sections 1–4 and prints a report;
exit 0 = complete, 1 = findings, 2 = structural problems (missing streams).

```python
import os, re, sys, datetime as dt
ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
STREAMS = {  # relpath -> (kind, hard_floor_Bps, exact_Bps or None)
  **{f'Reolink_record/CH0{i}': ('video', 20_000, None) for i in range(1, 9)},
  'thermal_record/108_thermal': ('video', 2_000, None),
  'thermal_record/108_visual':  ('video', 5_000, None),
  'thermal_record/109_thermal': ('video', 2_000, None),
  'thermal_record/109_visual':  ('video', 5_000, None),
  'ultramic_record/MIC01': ('audio', None, 768_000),
  'ultramic_record/MIC02': ('audio', None, 500_000),
}
EPOCH = {'ultramic_record/MIC01': dt.datetime(2026, 8, 15, 13, 56),
         'ultramic_record/MIC02': dt.datetime(2026, 8, 16, 16, 29)}
DEFAULT_EPOCH = dt.datetime(2026, 8, 15, 0, 0)
RX = re.compile(r'^(?P<s>.+)_(?P<d>\d{4}-\d{2}-\d{2})_(?P<a>\d{2}-\d{2}-\d{2})_to_(?P<b>\d{2}-\d{2}-\d{2})\.(mp4|wav|flac)$')
def t(datestr, hms):
    return dt.datetime.strptime(datestr + ' ' + hms, '%Y-%m-%d %H-%M-%S')
findings, structural = [], []
newest = None
per_stream = {}
for rel in STREAMS:
    p = os.path.join(ROOT, *rel.split('/'))
    if not os.path.isdir(p):
        structural.append(f'MISSING STREAM FOLDER: {rel}'); continue
    segs = []
    for f in os.listdir(p):
        m = RX.match(f)
        if not m: continue
        a = t(m['d'], m['a']); b = t(m['d'], m['b'])
        if b <= a: b += dt.timedelta(days=1)
        segs.append((a, b, f, os.path.getsize(os.path.join(p, f))))
    segs.sort()
    per_stream[rel] = segs
    if segs and (newest is None or segs[-1][1] > newest): newest = segs[-1][1]
for rel, segs in per_stream.items():
    kind, floor, exact = STREAMS[rel]
    ep = EPOCH.get(rel, DEFAULT_EPOCH)
    segs = [s for s in segs if s[1] > ep]   # scope to the current cohort
    if not segs:
        structural.append(f'NO SEGMENTS IN COHORT WINDOW (after {ep}): {rel}'); continue
    if segs[0][0] > ep + dt.timedelta(hours=1):
        findings.append(f'{rel}: first segment {segs[0][2]} starts {segs[0][0]} '
                        f'— expected coverage from {ep} (head of recording missing?)')
    for (a1, b1, f1, _), (a2, b2, f2, _) in zip(segs, segs[1:]):
        gap = (a2 - b1).total_seconds()
        if gap > 90:
            if b1.weekday() == 6 and gap < 900 and rel.startswith('Reolink'):
                continue  # Sunday NVR reboot window
            findings.append(f'{rel}: HOLE {b1} -> {a2} ({gap/60:.1f} min) between {f1} and {f2}')
    for a, b, f, size in segs:
        dur = max((b - a).total_seconds(), 1)
        if size == 0:
            findings.append(f'{rel}/{f}: ZERO BYTES (failed copy)'); continue
        if dur < 600:
            continue  # restart stubs: bitrate/audio-fill unrepresentative, skip size checks
        if exact is not None:
            if abs(size - exact * dur) > 0.01 * exact * dur + 65536:
                findings.append(f'{rel}/{f}: size {size:,} != {exact} B/s x {dur:.0f}s (truncated?)')
        elif floor is not None and size < floor * dur:
            findings.append(f'{rel}/{f}: size {size:,} below floor ({floor} B/s x {dur:.0f}s)')
    if newest and (newest - segs[-1][1]).total_seconds() > 7200:
        findings.append(f'{rel}: ends {segs[-1][1]}, {(newest - segs[-1][1]).total_seconds()/3600:.1f} h '
                        f'behind the newest data in the tree (tail missing?)')
wl = os.path.join(ROOT, 'Wiser_backup')
if not os.path.isdir(wl):
    structural.append('MISSING: Wiser_backup')
print(f'streams checked: {len(per_stream)}/{len(STREAMS)}   newest data: {newest}')
for s in structural: print('STRUCTURAL:', s)
for f in findings: print('FINDING:', f)
if not structural and not findings:
    print('COPY LOOKS COMPLETE (chains continuous, sizes sane, all streams present).')
sys.exit(2 if structural else (1 if findings else 0))
```

## 6. Optional strongest check: manifest comparison

Destination-side checks cannot see files that never left the field PC on a day the
copy skipped entirely — chain continuity catches that, but a **source manifest**
makes it exact. Ask the field-PC operator (or the field-PC agent) to run this
read-only one-liner there, which writes `copy_manifest.csv` into the destination:

```powershell
Get-ChildItem E:\Reolink_record,E:\thermal_record,E:\ultramic_record,E:\Wiser_backup -Recurse -File |
  Where-Object { $_.Name -match '_to_' -or $_.FullName -like '*Wiser_backup*' } |
  ForEach-Object { '"{0}",{1}' -f $_.FullName.Substring(3).Replace('\','/'), $_.Length } |
  Set-Content -Encoding UTF8 DEST\copy_manifest.csv
```

Then on the server, compare: every manifest row must exist under `DEST` with the
**exact same size** (path in the manifest is relative to `E:\`, matching the tree
above). Rows missing or size-mismatched = the definitive re-copy list.

## 7. What to report back

1. Verdict: complete / incomplete.
2. If incomplete, group findings into **days + streams**, and emit the exact heal
   command for the field PC, e.g.:

```
copy_to_analysis.ps1 -Dest <share> -Date 2026-08-16,2026-08-17 -Channels CH03,CH07
```

(Re-running is always safe: robocopy copy-only + skip-in-sync; the source is never
modified. `-Channels` limits video only; audio/thermal re-copy in full for those
dates, which is cheap.)

3. Remember the expected absences before declaring "missing": open segments (no
   `_to_`), the newest ~1–2 h of every stream, pre-epoch hours (table in §1), and
   the Sunday CH* reboot minutes.
