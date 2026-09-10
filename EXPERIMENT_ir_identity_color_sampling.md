# EXPERIMENT: colour sampling for in-box IR identity (CH07 / CH08)

**Started:** 2026-09-09 (HC). Cohort 3 is the last cohort — the paddock is torn down after it,
so these are the only samples that will ever exist.

## The problem

During the day the rats never leave the shelter boxes, so the ONLY footage of them is the in-box
cameras **CH07 / CH08**, which run under **IR** (the box is dark). In IR the coban/sticker colours
may or may not be distinguishable, and the animals huddle (2026-09-07: all six within 8–21 cm in
one box), which is the hardest case for visual ID.

WISER is not a substitute: its resolution tells you **which box** an animal is in, not where it is
inside the box. So in-box identity has to come from the video.

**Governing goal (2026-09-09, operator): ten days of IR-only in-box footage already exist and must be
analysed. Everything collected from here on is in service of THOSE ten days** — i.e. it must produce
labelled IR examples under the same conditions (IR, daytime, huddle), not a separate colour dataset.
That single requirement settles the auto question: see the branch at the bottom.

**What the colour light actually buys:** not a colour→IR-grey lookup (near-IR reflectance does not
follow visible colour — red and green cobans can be the same grey at 850 nm), but **ground-truth
identity at a known instant**, which lets you (a) label the adjacent IR frames, (b) learn what each
animal looks like in IR, and (c) validate any IR classifier you build.

**Why sampled, not continuous / auto** (operator + GPT agree): auto day/night switching is triggered
by ambient light, so mode changes are unpredictable and unexplainable after the fact — the worst
kind of heterogeneity. Deterministic, logged inserts keep the boundaries clean (`exclude 12:00:00–
12:00:10`) and cost far less disturbance. **Do not put CH07/CH08 on auto.**

## The insight that shapes the schedule

**Battery rounds are free sampling windows.** At each round the animals are caught and handled
anyway, so the marginal disturbance of a light insert right afterwards is ≈ 0 — and in the 10–20 min
after they are returned they are still **moving and separated**, which is exactly the condition in
which labelling is easy. Midday, by contrast, is the sleep period (the dependent variable) AND the
huddle — expensive and hard, so take only a few short samples there, aimed at the hard case.

## What to sample — choose by POSTURE, not by the clock (operator, 2026-09-09)

**One rule decides the value of a flash: how long its label survives in the surrounding IR frames, and how
many markers the colour frame actually shows.** Look at the live IR preview first; flash only when the
configuration is informative. The clock times below are just reminders of when to go and look.

**Tier 1 — highest value per flash (these are what the ten earlier days look like):**

1. **A freshly settled, loose pile** — bodies touching, most back markers still visible. The pile is
   static, so the label propagates forward/backward through the IR for tens of minutes: one flash labels a
   long stretch. The single best sample for the retroactive goal.
2. **One or two animals apart, the rest piled** — the outsiders are fully labelled, the pile has one fewer
   unknown, and this is the commonest real configuration (animals joining/leaving the huddle).

**Tier 2 — the appearance dictionary the classifier needs:**

3. **Each animal separated and moving** (the 10–25 min after they are returned at a round — disturbance
   already paid): back, side and head-on views of every animal, a few of each.

**Tight, buried piles — flash ONCE per pile episode, not repeatedly.** Colour contrast beats IR contrast,
so a coban edge that merges with fur in IR can be obvious in the colour frame; one flash pulls out
whatever is partly visible and anchors the pile's composition for the tracker. Do not flash the same
pile again until it has reshuffled.

**How a buried pile gets its labels at all (this is the key to the ten earlier days):** not from its own
frames — a buried marker is invisible in colour too, so this is not an IR-vs-colour limitation and
auto would not have helped. Identity in a tight pile is INHERITED by tracking from the last moment the
markers were visible (the loose pile it formed from, or the animals that joined it). The classifier
only has to work at the visible moments; a tracker carries the labels across the buried ones. That is
why the transitions (loose → tight, tight → loose) are the moments worth catching.

**The one hard limit:** animals that reshuffle while buried and never surface a marker. Their
arrangement in that stretch is unrecoverable by any method. Even then two layers survive:
- **composition** (which animals are in the pile): WISER box occupancy minus the identified
  outsiders — already available for all ten days, no flash needed; answers who-sleeps-with-whom;
- **arrangement** (who is next to whom inside): from the visible moments + tracking — what this
  sampling buys;
- frame-by-frame identity inside a buried, reshuffled pile: not obtainable. Decide which layer the
  analysis actually needs; that bounds the sampling effort.

**Do not spend a flash on:**

- animals running and rearranging — the label dies in seconds;
- the same static configuration twice — wait until something has moved or the pile has reshuffled.

**Go / no-go before pressing the button:** loose pile or animals apart with markers showing → flash; a
tight pile → flash once for this episode if you have not already; the same unchanged configuration → wait.

**Enough (over the three days):** per animal ≥ 3 separated views at different angles, and ≥ 5 labelled
pile frames in which that animal's marker is visible. Stop when reached.

Flash length: 5 s in a sleeping pile (sleep is the experiment), up to 10 s when they are already awake
after a round. When to go and look: after the AM round (~07:30–08:00), midday (12:00–13:00, the
settled-pile window), after the PM round (~18:30–19:00).

### Per insert, record

- camera (CH07 / CH08), **ON time and OFF time to the second**, and how many animals are in frame.
- Anything unusual (an animal at the entrance, a rat out of frame, light bleeding from a door, etc).
- Give the list to Claude at the end of each block and it goes into `incident_log.md` + the
  from-field mirror; the segments are `E:\Reolink_record\CH07\CH07_<date>_<hh>-00-00_to_...mp4`
  (rig ffmpeg pulls, PC-time names).

### Analysis-side flags (must accompany the data)

- Each insert is a **calibration insert, not behaviour**: exclude those seconds from any
  luminance/motion-based measure on that channel, and make sure the CV pipeline does not read the
  exposure jump as activity.
- Each insert is also a **micro-disturbance**: a light pulse into a dark box. Check CH07/CH08 and
  WISER right after each one for a startle or a shelter exit, and note it if it happens.

## Thursday evening decision point — three questions, in order

1. **In the colour frames, can you tell the five apart?** (Sanity check; expected yes.)
2. **In the IR frames immediately before/after each insert, are the same five distinguishable** — by
   sticker/coban **pattern** (SF07 x, SF09 star, SF10 square-with-cross, SF12 two lines), by body
   size, or by grey level? Patterns are geometric and survive IR; colours may not.
3. **In the midday huddle frames specifically, can identity be assigned at all?**

Then:

- **3 works** → the method is proven. **Run all three blocks on Friday and Saturday too**: A/C cover
  appearance drift (coban shifts and gets dirty), and every extra B adds huddle configurations to the
  validation set for the ten earlier days (~3 configurations per day, ~9 over the three days).
- **3 fails but 2 works when separated** → honest conclusion: in-box IR ID is possible only when the
  animals are apart, not in a pile. Change what is measured for the huddle (e.g. number of animals
  in contact rather than who-with-whom), and skip further sampling — more samples will not fix it.
- **2 fails** → the markers are not IR-discriminable. Stop sampling immediately (no point spending
  disturbance). The only remaining lever is adding IR-visible markers at the next round while the
  animals are in hand — decide separately whether changing marker appearance mid-cohort is worth it.

## Notes

- Prefer a moment when the box is **empty** for any long/extra sample (background reference for
  subtraction); identity samples obviously need the animals in it.
- Keep every insert short. Sleep is the experiment.
- 2026-09-09 19:11 — first sample taken, CH07, ~3 s (before this plan existed). Segment
  `CH07_2026-09-09_19-00-00_to_20-00-00.mp4`. It sits inside the loggers' post-restart settle-in
  window (restarts 18:38–18:50), so it costs nothing extra.

## Branch (2026-09-09 evening) — DROPPED the same evening: auto day/night

**Not used.** Auto would optimise the remaining three days at the expense of the ten IR days already
recorded: a colour daytime removes the IR huddle frames from exactly the condition the classifier must
learn, and colour↔IR pairs would occur only at the two uncontrolled dawn/dusk switches. IR-locked +
short colour inserts keeps 13 days homogeneous in IR and labels them — strictly better for the
retroactive goal. The fps test below is therefore NOT run on 2026-09-10. Kept for the record only.

### (superseded) if auto day/night had given stable colour in the box

If CH07 on **auto** yields stable colour during the day, the daytime identity problem is solved
directly and the IR calibration is only needed for (a) the earlier IR-only days and (b) night-time
in-box bouts. The sampling discipline then simply inverts: brief **forced B&W** inserts (5 s) during
colour mode give the colour↔IR adjacent pairs, and the dawn auto-switch (animals usually in the box)
gives one free pair per day. Heterogeneity is acceptable: two predictable transitions per day, mode
detectable per frame, switch times logged. Hedge: auto on CH07 only, CH08 stays IR-locked.

**The one hard risk — exposure.** In a dim box, colour mode makes the camera lengthen the shutter
(Reolink can drop to 1/15–1/4 s). The container fps stays nominal (`-c copy`), but the sensor
delivers duplicated frames and motion-blurred ones — both fatal for tracking. IR mode is immune
(the LEDs supply the light).

**Test before adopting (2026-09-10):**
1. Check the camera's Exposure / Shutter setting; if a shutter floor exists, set it (≥ 1/30 s).
   A darker, noisier colour image is still colour for identity purposes.
2. Switch CH07 to auto ~07:30 after the AM round so the **08:00–09:00** segment is fully auto;
   once it closes at 09:00, measure on the closed file (no open-segment reads):
   unique-frame count by frame differencing (duplicates = stretched shutter), packet-timestamp
   gaps (dropped frames), and a visual check of frames with a moving animal (blur).
3. Verdict: full effective fps and no blur → adopt auto for the remaining days; fps drops but a
   shutter floor is available → set it and re-test one segment; neither → stay IR-locked and run
   the sampling plan above unchanged.

## Pilot 1 (2026-09-09 evening): manual labelling of one IR hour, CH07 2026-09-05 08:00–09:00

Purpose (operator): establish how hard in-box IR identity actually is and how to spend the remaining
sampling days — by MANUAL inspection only; no automatic detection or identification was attempted.

- Source: the operator's copy `D:\07_08_camera\CH07_2026-09-05_08-00-00_to_09-00-00.mp4` (2560×1920,
  20 fps, GOP 2 s). Nothing under `E:` was touched; the recorders were checked before and after each
  decode step (all channels GROWING, CPU 6–23%).
- Selection was by a keyframe motion trace only (0.5 fps, I-frames): three still stretches (08:04:44,
  08:11:10, 08:30:22), two motion onsets (08:15:10, 08:38:54), one active stretch (08:25:40), the round
  start (08:45:42). 08:00–08:40 is nearly flat — a sleeping pile can sit still for 30+ min.
- Materials in `D:\07_08_camera\pilot_CH07_2026-09-05_08h\`: `clips_fullres\` (seven 22-s stream-copied
  full-resolution clips + `manifest.json` with exact keyframe start times + the labeler), `frames\`
  (−10/−5/0/+5/+10 s full-res stills), `strip_*.png` (1 fps ±10 s thumbnails), the hour's contact sheet and
  motion trace, `LABELING_SHEET.md` (marker reference + the five pilot questions).
- Tool: `ir_identity_labeler.html` (repo root, single file, runs from disk, no server): pick the clip
  folder, frame-step the full-res video (←/→, Shift = 1 s), wheel-zoom, select a rat (1–6, 0 = unknown),
  click the head; cue + confidence + note per label; autosaves in the browser; exports CSV/JSON with
  absolute wall-clock time and source-pixel coordinates. Intended to be reused for the ten-day
  retroactive labelling.

## 2026-09-09 late evening: three label sources, colour is the most expensive one (plan approved)

Colour flashes are NOT the only way to put identity on the in-box IR footage. Ranked by cost:

1. **WISER box entry/exit events - free, retroactive, all ten days.** WISER cannot resolve position inside
   a box but it resolves WHICH box, so every crossing is a tag transition with a wall-clock time; the animal
   crossing the door on video at that time is that tag. Script `wiser_box_transitions.py` (analysis repo,
   `wiser_tracking_analysis/scripts/`; reads snapshots only). Calibration finding: the house rectangles in
   `wiser_rois.json` are ~1 in short of where the pile lies (the 9/7 pile at (628,732) is outside house_2's
   x-extent), so at the raw boundary a motionless pile flickers ENTER/EXIT dozens of times per hour;
   dilating the rect by 15 in + 6-s smoothing + 20-s minimum dwell removes it (9/5 08:00-08:47: all six
   inside, zero flicker). Validated on 9/5: all six EXIT house_2 together at 08:47:08 (taken out as a group
   after the BLE Stops 08:34-08:42); five ENTER house_2 one by one 09:49:49-09:50:15 (SF09, SF07, SF11,
   SF10, SF12; SF08 -> house_1) after the loggers were started outside 09:32-09:47. Placement order =
   identity order; pairs 2-3 s apart need the operator's release-order note.
2. **BLE round events - demoted to an order check.** Stop/Start are within +/-1-2 min of the WISER events
   but not in the same order (Stop = "connected and stopped" before the catch; Start = "started outside"
   before the placement). No RSSI history exists to read entries from signal strength.
3. **Colour flashes - Thu-Sat only.** Reserved for identity INSIDE a static pile (arrangement layer) and for
   validating labels carried into the pile by tracking from source 1. The dictionary of each animal's IR
   appearance comes for free from source 1 (crossings are separated, moving animals).

New habit from Thursday: **write down the release order and time at every round** (rat, box door, hh:mm:ss).

### Decision matrix: pilot answers -> Thu-Sat protocol
- **A. context helps (Q3 yes) and the huddle is assignable (Q4 yes):** sparse flashes only - one per settled
  loose pile and per one-apart-rest-piled moment (5 s), 3-5/day, all three days; effort goes into source 1.
- **B. Q3 yes, Q4 no:** arrangement layer abandoned; composition (who shares the pile) is already complete
  from source 1 for all ten days. Flashes only at one-apart-rest-piled moments (<= 2/day) to confirm the
  tracked boundary; no midday flashes; Fri/Sat optional.
- **C. Q3 no (labels die within seconds):** tracking cannot bridge -> pile identity unobtainable at any flash
  rate. Stop flashing after Thursday; analysis moves to crossing-based social measures (who enters whose
  box, co-occupancy, order), fully supported by source 1 for ten days.
- **D. Q2 no (nothing discriminable even when apart):** stop flashing; the only lever is a non-saturating
  IR marker (matte, e.g. dyed/shaved pattern) applied at Thursday's AM round while the animals are in hand
  - helps Thu-Sat only, changes appearance (segment the analysis), operator's call.

### Validation set for source 1 (pending the operator's labels)
`D:\07_08_camera\pilot_CH07_2026-09-05_08h\validation_clips\`: the 08:44:30-08:48:00 removal and the
09:49:20-09:50:45 release on CH07, manifest with wall-clock starts, README with the expected WISER events.
Questions: does CH07's box receive five animals at 09:49:49-09:50:15 (=> CH07 = house_2); video time of each
placement vs the WISER time (= WISER event precision); placed by hand vs walked in.
