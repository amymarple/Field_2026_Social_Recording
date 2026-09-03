# Local weather listener (`weather_listener.ps1`)

**Why:** on 2026-09-02 21:10 the Ambient Weather console lost its uplink for ~18 h.
ambientweather.net never backfills from the console, so those 18 hours of on-site
weather are gone from the cloud forever. The console can, however, push every
reading to *any* HTTP address on the LAN ("Customized upload"). This listener is
that address on the field PC — the cloud stays as a mirror, the local file is the
record.

**Independence:** own SYSTEM task, own `Global\FieldWeatherListener` mutex, own root.
It writes only under its root (default `D:\weather_data\local`) and never touches
E: or any recorder.

## Files

| path | what |
|---|---|
| `D:\weather_data\local\AWN-F8B3B78DEAC9_YYYY-MM-DD.csv` | one file per **local** day, the exact 27-column schema of the ambientweather.net exports already in `D:\weather_data` (units: °C, mph, mm, mmHg; `Date` = local ISO with offset, e.g. `2026-09-03T15:20:00-04:00`) |
| `D:\weather_data\local\raw\AWN-F8B3B78DEAC9_YYYY-MM-DD.jsonl` | every packet verbatim, every field the console sent (lossless) |
| `D:\weather_data\local\weather_listener_state.json` | heartbeat: last packet time, packets today, errors |
| `D:\weather_data\local\logs\weather_listener.log` | start/stop, one line per 60 packets, ignored requests, errors |

The analysis loader (`wiser_analysis_utils.load_weather` / `load_weather_multi`) reads
the local files exactly like the cloud exports; `load_weather_multi` de-duplicates on
UTC timestamp, so overlapping cloud + local files are safe to pass together.

Columns the console does not send are computed the way the cloud does it: dew point
(Magnus), feels-like (NOAA heat index ≥ 80 °F, wind chill ≤ 50 °F & wind > 3 mph,
else air temperature). Battery columns follow the export convention `1 = OK`
(the Ecowitt packet uses `0 = OK`, the listener flips it).

## Install (once, elevated PowerShell)

```powershell
cd C:\Users\Cornell\Documents\GitHub\Field_2026_Social_Recording
powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -SelfTest        # offline check
powershell -NoProfile -ExecutionPolicy Bypass -File install_weather_listener_task_system.ps1 -RunNow
```

The installer registers the SYSTEM task **Field Weather Listener** (at startup +
5-minute self-heal, no time limit) and adds an inbound firewall rule for TCP 8085
restricted to the local subnet **and to the router-LAN adapter only** (`Ethernet`).
The field PC has three interfaces numbered inside 192.168.1.0/24 (router LAN `.159`,
camera jack `.20`, WISER jack `.10`); the console lives on the router LAN, so the
camera and WISER segments never see the listener's port. Verified 2026-09-03: no
device on either of those segments answers as `.159`. Optional config: copy
`weather.config.example.psd1` to `D:\weather_data\weather.config.psd1` (port, path,
root, station label, LAN interface alias).

## Point the console at the PC

On the console (or its local web UI at `http://192.168.1.166`, or the Ambient Weather
app → device → *Customized*): **Customized upload → Enable**

| setting | value |
|---|---|
| Protocol | **Ecowitt** (Wunderground also works — the listener accepts both) |
| Server IP / hostname | `192.168.1.159` (the field PC's LAN address — the Realtek "Ethernet" port) |
| Path | `/data/report/` |
| Port | `8085` |
| Upload interval | `60` s (16 s minimum; 60 matches the cloud's 5-minute export well enough and keeps the files small) |

Save, wait one interval, then verify from any PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -Status
```

`OK: last packet … (0.4 min ago)` = done. Exit codes: 0 fresh, 1 stale (> 10 min),
2 nothing received yet (check the console settings / firewall / that the PC's LAN
address is still `192.168.1.159`).

## Caveats

- The console posts in real time only; it does not buffer. A field-PC reboot loses
  the packets during the reboot (a few minutes) — the cloud usually still has those.
- If the PC's LAN address changes (DHCP), the console's target must change with it.
  Reserve `192.168.1.159` on the router, or set the console to the PC's hostname.
- The listener is not yet wired into the Slack alive-check; `-Status` is the manual
  check (exit 1 = stale) and can be scheduled like the other watchdogs when wanted.
