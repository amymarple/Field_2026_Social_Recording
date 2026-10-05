# video_timing - each camera's video on its own continuous clock (step S1)

Step S1 of the analysis repo's `implementation_plan/2026-10-05-video-clock-sync.md` (video frames on the ephys / PC
clock). Built 2026-10-05 in the recording repo because it reads the raw recordings; S2 (per-camera offset to the ephys
clock from the head IMU) belongs to the analysis repo.

## The problem

`rtsp_record.ps1` records with `-use_wallclock_as_timestamps 1 -reset_timestamps 1`: a frame's stored timestamp is its
ARRIVAL time at the PC, bursty (0.04-0.09 s rms, up to 0.57 s), reset to 0 in every hourly file, and the file's start
is only in its name, to 1 s. So video is on the PC clock only to about +-1 s, with an effectively random offset per
file.

## What `osd_clock.py` does

Every frame carries the camera's burned-in OSD clock (HH:MM:SS). Per hourly file:
1. frame index <-> stored timestamp from the fragmented MP4's box headers only (moof / traf / tfdt / trun; the
   payload is skipped) - identical to ffprobe (`--check-index`: 72,000 frames, 0.000 ms difference);
2. five 20-s windows over the file, decoded on the GPU and cropped to the OSD time text; the OSD line is centred and
   moves sideways between days (CH01-CH04: +16 px on 08-30 / 08-31 / 09-11 / 09-12, 0 on 09-01 .. 09-06; CH05 / CH06
   never), so each window first finds the time string's offset (+-48 px, +-24 for CH05 / CH06);
3. ticks = the first frame of each new second (the seconds-units cell changes; white glyph core and dark outline as
   two channels, so the text reads on white walls at night too); each tick's second counted from the frame spacing;
   HH:MM:SS read on three frames after each tick (nearest exemplar, +-3 px shifts, `osd_templates.npz`) and the
   window's time = the median over its ticks of (read value - count);
4. `t_osd(i) = c0 + p * i` fitted to all ticks (each tick at i - 0.5); misreads (> 0.5 s) and late / false ticks
   (> 0.1 s) dropped.

Output per camera (default `F:\calibration\video_timing\`): `osd_clock_<CAM>.csv`, one row per file - `fps_osd`
(the camera's frame rate on its own clock), `c0_osd_s` / `osd_frame0` (OSD time of frame 0), `s_per_frame`,
`resid_rms_ms`, `window_offsets_ms` (the fit's offset per window: a dropped frame shows as a step), `read_agreement`
per window, `pc_name_minus_osd_s` (file-name start minus the OSD time of frame 0, to [0, 1) s), `status`
(ok / check / too few readable ticks / error) - and `osd_clock_<CAM>_ticks.jsonl` (every tick). Reruns skip files
already in the CSV.

## Validation (2026-10-05)

- Reading: exemplars learned from CH01, CH03 and CH05 (one day and one night window each, operator-read); tested on
  the sibling cameras CH02, CH04, CH06 (never seen in learning), day and night: all six windows read the correct time
  (single-tick reads agree 0.65-1.00; the window consensus correct in every case).
- Every date (08-30 .. 09-12, one window per camera and day, 60 windows): the window consensus readable in all,
  single-tick reads agree 0.53-1.00 (CH03 by day the weakest).
- Whole files (2026-09-05 04:00, all six cameras): 99-101 ticks per file, readings agreed 100 % in 29 of 30 windows,
  fit residual rms 16-25 ms (the frame interval's own quantisation is 14 ms), camera rates on their own clocks CH01 /
  CH02 19.997, CH03 / CH04 19.984, CH05 / CH06 20.000 fps (as the 20 Hz ball found).
- Resolution: CH05 / CH06 run at exactly 20.000 fps on their OSD clocks, so a tick's phase within the frame never
  moves and cannot be averaged out: their OSD time is known to +-25 ms (one frame); the others dither, ~10 ms.
- The cameras' OSD clocks are NOT one clock: on the 2026-09-30 ball session they tick 0-0.4 s apart
  (`calibration_qc/osd_tick_test.py`: against CH02, CH04 +2, CH06 -22, CH05 +218, CH01 -250, CH03 -409 ms). This tool
  puts each camera on its own continuous clock; S2 ties each camera to the ephys clock.

## Usage

    python osd_clock.py --root F:\3rd_rat --dates 2026-09-05,2026-09-06 [--cams CH01,CH02] [--jobs 3]
    python osd_clock.py --check-read          # the sibling-camera reading test
    python osd_clock.py --learn               # rebuild osd_templates.npz from the LEARN windows
    python osd_clock.py --check-index <file>  # box-header index vs ffprobe

Needs ffmpeg with CUDA (`F:\calibration\bin\ffmpeg.exe`, or `FFMPEG=`), numpy, opencv. CH07 / CH08 and the thermal
cameras are not configured (their OSD boxes were never measured).
