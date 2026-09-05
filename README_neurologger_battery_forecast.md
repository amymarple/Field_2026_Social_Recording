# Neurologger battery forecast (twice daily -> Slack)

`neurologger_battery_forecast.ps1` reads the 5-min advertisement history that the alive
check already writes (`E:\recording_qc\neurologger_telemetry_history.csv`), fits each
logger's drain on its **current cell**, and posts to Slack at **01:02 and 13:02**:

- per logger: voltage, slope (mV/h, with the 20 mV-quantization error bar), projected
  **auto-stop time**, **swap-by** time (auto-stop minus 1 h), card % and time-to-full;
- fleet advice: **"start the round by HH:MM"** (earliest swap-by), the swap **order**
  (ascending auto-stop), and a check against the **next planned round** - it warns when
  anyone would auto-stop or any card would fill before that round.

## Model (calibrated on cohort-3, 2026-09-03/04)

1. **Current cell** = samples since the last upward jump >= 150 mV (a swap).
2. **Slope** = first-to-last over the last 4 h of that cell (needs >= 1.5 h of span).
   Advertised voltage is 20 mV-quantized, so error ~ 20 mV / span.
3. **Reference discharge curve** (900 mAh cell on an EVO 512 card, mean of the 9/2 and 9/3
   nights; life to auto-stop 14.2 h): 4.18 V at install, 4.04 @2 h, 3.93 @4 h, 3.83 @6 h,
   3.77 @8 h, 3.71 @10 h, 3.65 @12 h, 3.58 @13 h, 3.45 @14 h, 3.40 @14.2 h. The cell is
   **placed on the curve by its voltage** (a weaker cell simply sits further along), so the
   LiPo nonlinearity - steep 4.1->3.9, flat plateau 3.9->3.7, then the knee - is built in.
   (The first version extrapolated the 4-h slope linearly to the knee and, at 4 h of age,
   predicted 05:52 for cells that the curve puts at ~09:50. Never extrapolate the steep part.)
4. **Drain-rate factor**: remaining time on the curve is scaled by (curve slope over the same
   span) / (measured slope), clamped **x0.6 .. x1.5** - a high-power SD card shortens, a
   1000 mAh cell (or a light load) lengthens. Knee = the curve's 3.68 V age, scaled the same way.
5. **Why 01:02 / 13:02**: evening cells (~19:30-20:00) are ~5 h old at 01:00, morning cells
   (~08:15) ~4.75 h old at 13:00 - past the surface-charge phase, so the slope is steady.
   Install-hour slopes are inflated (lesson of 2026-09-02); never forecast from them.

Also flags **STOPPED** (recording-elapsed frozen over 3 samples), **STALE** (no ad for
20 min) and **SHORT** (< 1.5 h on a fresh cell - no slope yet).

## Install / test

```powershell
# prove it from a normal PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -SelfTest
powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File neurologger_battery_forecast.ps1 -TestSlack

# register (ELEVATED PowerShell); planned rounds default to 08:15 / 19:45
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install_neurologger_battery_forecast_task_system.ps1 -RunNow
# other round times, e.g. 08:00 / 20:00:
.\install_neurologger_battery_forecast_task_system.ps1 -RoundHours 8,20 -RunNow
```

Outputs: `E:\recording_qc\neurologger_battery_forecast.txt` (latest table + advice) and
`neurologger_battery_forecast_log.txt` (one line per run). Mute with the shared
`E:\recording_qc\neurologger_alive_MUTED.txt`. Exit codes: 0 ok, 1 warning, 2 no data.
Read-only on everything except `E:\recording_qc`.
