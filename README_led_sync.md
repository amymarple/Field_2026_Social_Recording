# LED sync pulser (`led_sync.ps1`)

Blinks an LED on a Raspberry Pi Pico at **1 Hz driven by the PC clock**, and logs every
rising edge with a precise PC timestamp. The LED sits inside the cameras' field of view;
wild_console stamps the neurologger ephys with the same PC clock — so matching an
LED-onset video frame to its logged timestamp aligns **video ↔ ephys on one timebase**.

## Hardware

- Raspberry Pi Pico running MicroPython, on **COM11** (VID_2E8A&PID_0005, board serial
  E66488C15F133839), plugged into a direct PC root port (USB-fabric rule).
- LED + series resistor (220–330 Ω) from **GP14 or GP15** to GND — **both pins are
  driven identically**, so either wiring works. The Pico's onboard LED blinks too,
  as a visual heartbeat.
- Nothing is installed on the Pico. The script injects a tiny listener into Pico RAM
  over the MicroPython raw REPL each time it starts (`'1'`=on, `'0'`=off, `'q'`=quit).
  After a Pico power-cycle, just restart the script.

## Run / stop (plain terminal, foreground)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\led_sync.ps1                  # run until Ctrl+C
powershell -NoProfile -ExecutionPolicy Bypass -File .\led_sync.ps1 -TestSeconds 10  # visual check
powershell -NoProfile -ExecutionPolicy Bypass -File .\led_sync.ps1 -SelfTest       # offline logic test
```

**Ctrl+C stops cleanly**: LED forced off, Pico returned to its REPL, `# STOP` line
written. If the serial port drops mid-run the script logs `# DROP`, retries every 5 s,
and logs `# RECONNECT` (pulses missing in between — visible as gaps in the log).

Params: `-Port COM11`, `-LogDir E:\led_sync`, `-DutyMs 500` (LED on-time per second).

## Log format — `E:\led_sync\LEDSYNC_YYYY-MM-DD_HH-00-00.txt` (rolls hourly)

```
# LEDSYNC rising-edge log  host=...  port=COM11  pins=GP14+GP15+onboard  duty_ms=500
2026-08-29T10:52:02.000-04:00 RISE sched=10:52:02 offset_ms=+0.6
```

- One `RISE` line per second — the moment the serial "on" command finished sending,
  local time with ms. `offset_ms` = lag after the intended second boundary (measured
  +0.3 to +1.4 ms on this PC; USB adds ~1–3 ms more before the LED physically lights).
- Event lines start with `#`: `START`, `STOP`, `DROP`, `RECONNECT`, headers.
- ~3600 lines (≈260 KB) per hour; files open with shared read, safe to copy any time.

## Analysis recipe

1. In the video, find a frame where the LED turns on; note the segment's filename
   start time + frame index (recorders stamp segments with the same PC clock).
2. Look up that second's `RISE` line — that is the PC-clock time of the optical edge
   (±USB latency, well under one frame at 15–25 fps).
3. wild_console CSV rows are already PC-clock — subtract. For sub-frame work, use
   many edges across an hour and fit; single edges are frame-quantized.

## Caveats

- The 1 Hz pattern has no absolute marker — a lone frame tells you the phase, the
  segment filename tells you which second. Don't trim/re-encode video before reading
  edges (timestamps live in the container + filename).
- The scheduling loop sleeps to ~40 ms before each boundary then spin-waits, so it
  holds ±1–2 ms even under load; real lateness is visible per-pulse in `offset_ms`.
- Serial writes are 2 bytes/s — negligible USB traffic, but the Pico still lives on
  the protected USB fabric: direct root port, no hubs.
