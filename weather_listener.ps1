<#
.SYNOPSIS
    Local weather logger for the Ambient Weather console - no cloud in the loop.

.DESCRIPTION
    The AMBWeatherPro console can push every reading to ANY http address via its
    "Customized upload" setting (Ecowitt protocol = HTTP POST, form-encoded; the
    Wunderground protocol = HTTP GET with a query string). This script is that
    address: a tiny HttpListener on the field PC that accepts both protocols and
    appends each packet to a daily CSV using the SAME 27-column schema as the
    ambientweather.net export files already in D:\weather_data, so the analysis
    loader (wiser_analysis_utils.load_weather) reads local and cloud files alike.
    Every packet is also kept verbatim as one JSON line (nothing lossy).

    Independent of every recorder (own mutex, own task, own root); it only ever
    writes under its Root. Built after the 2026-09-02/03 outage, when 18 h of
    weather vanished because the console lost its uplink and ambientweather.net
    never backfills.

    Files under Root (default D:\weather_data\local):
        <StationLabel>_YYYY-MM-DD.csv     AWN-schema rows, one file per LOCAL day
        raw\<StationLabel>_YYYY-MM-DD.jsonl   every packet, every field, verbatim
        weather_listener_state.json       heartbeat: last packet time/age, counts
        logs\weather_listener.log

.PARAMETER ConfigPath
    Optional psd1 (see weather.config.example.psd1). Missing file = built-in defaults
    (port 8085, path /data/report/, Root D:\weather_data\local).

.PARAMETER SelfTest
    Offline: pushes a synthetic Ecowitt POST and a Wunderground GET through the
    parser + CSV writer into a temp folder and checks the result. No socket, no D:.

.PARAMETER Status
    Print the last packet age from the state file. Exit 0 fresh, 1 stale
    (> -StaleMinutes), 2 never received / no state.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -SelfTest
    powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -Status

.NOTES
    Binding http://+:PORT/ needs admin or SYSTEM - it is meant to run as the
    "Field Weather Listener" SYSTEM task (install_weather_listener_task_system.ps1),
    which also opens the firewall port for the local subnet only.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = 'D:\weather_data\weather.config.psd1',
    [switch]$SelfTest,
    [switch]$Status,
    [int]$StaleMinutes = 10
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Web

# ------------------------------------------------------------------ config ----
$cfg = @{
    Root         = 'D:\weather_data\local'
    Port         = 8085
    Path         = '/data/report/'
    StationLabel = 'AWN-F8B3B78DEAC9'
}
if (Test-Path -LiteralPath $ConfigPath) {
    $user = Import-PowerShellDataFile -Path $ConfigPath
    foreach ($k in $user.Keys) { $cfg[$k] = $user[$k] }
}
if (-not $cfg.Path.StartsWith('/')) { $cfg.Path = '/' + $cfg.Path }
if (-not $cfg.Path.EndsWith('/'))   { $cfg.Path = $cfg.Path + '/' }

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# The ambientweather.net export header, verbatim, so local files load like cloud ones.
$script:Columns = @(
    'Date', 'Simple Date', 'Outdoor Temperature (°C)', 'Feels Like (°C)', 'Dew Point (°C)',
    'Wind Speed (mph)', 'Wind Gust (mph)', 'Max Daily Gust (mph)', 'Wind Direction (°)',
    'Rain Rate (mm/hr)', 'Event Rain (mm)', 'Daily Rain (mm)', 'Weekly Rain (mm)',
    'Monthly Rain (mm)', 'Yearly Rain (mm)', 'Relative Pressure (mmHg)', 'Humidity (%)',
    'Ultra-Violet Radiation Index', 'Solar Radiation (W/m^2)', 'Indoor Temperature (°C)',
    'Indoor Humidity (%)', 'Avg Wind Direction (10 mins) (°)', 'Outdoor Battery',
    'Absolute Pressure (mmHg)', 'Indoor Battery', 'Indoor Feels Like (°C)', 'Indoor Dew Point (°C)'
)

# ------------------------------------------------------------------ helpers ---
function Write-Log([string]$msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    try {
        $dir = Join-Path $cfg.Root 'logs'
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        [IO.File]::AppendAllText((Join-Path $dir 'weather_listener.log'), $line + "`r`n", $script:Utf8NoBom)
    } catch { }
}

function Parse-Form([string]$text) {
    # form-encoded or query-string -> ordered hashtable (keys kept in packet order)
    $h = [ordered]@{}
    if (-not $text) { return $h }
    foreach ($pair in ($text.TrimStart('?') -split '&')) {
        if (-not $pair) { continue }
        $kv = $pair -split '=', 2
        $k = [System.Web.HttpUtility]::UrlDecode($kv[0])
        $v = if ($kv.Count -gt 1) { [System.Web.HttpUtility]::UrlDecode($kv[1]) } else { '' }
        $h[$k] = $v
    }
    return $h
}

function Get-Num($h, [string[]]$keys) {
    foreach ($k in $keys) {
        if ($h.Contains($k) -and $h[$k] -ne '' -and $h[$k] -ne $null) {
            $d = 0.0
            if ([double]::TryParse([string]$h[$k], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$d)) { return $d }
        }
    }
    return $null
}

function R1($x) { if ($x -eq $null) { return '' }; return ([math]::Round([double]$x, 1)).ToString([Globalization.CultureInfo]::InvariantCulture) }
function R0($x) { if ($x -eq $null) { return '' }; return ([math]::Round([double]$x, 0)).ToString([Globalization.CultureInfo]::InvariantCulture) }
function FtoC($f) { if ($f -eq $null) { return $null }; return ($f - 32) * 5 / 9 }

function Get-DewPointC($tC, $rh) {
    # Magnus formula (Alduchov & Eskridge constants)
    if ($tC -eq $null -or $rh -eq $null -or $rh -le 0) { return $null }
    $a = 17.625; $b = 243.04
    $g = [math]::Log($rh / 100.0) + ($a * $tC) / ($b + $tC)
    return ($b * $g) / ($a - $g)
}

function Get-FeelsLikeC($tF, $rh, $windMph) {
    # ambientweather.net convention: heat index above 80 F, wind chill at/below 50 F
    # with wind over 3 mph, otherwise the air temperature.
    if ($tF -eq $null) { return $null }
    if ($tF -ge 80 -and $rh -ne $null) {
        $T = $tF; $H = $rh
        $hi = -42.379 + 2.04901523*$T + 10.14333127*$H - 0.22475541*$T*$H - 0.00683783*$T*$T `
              - 0.05481717*$H*$H + 0.00122874*$T*$T*$H + 0.00085282*$T*$H*$H - 0.00000199*$T*$T*$H*$H
        return (FtoC $hi)
    }
    if ($tF -le 50 -and $windMph -ne $null -and $windMph -gt 3) {
        $wc = 35.74 + 0.6215*$tF - 35.75*[math]::Pow($windMph, 0.16) + 0.4275*$tF*[math]::Pow($windMph, 0.16)
        return (FtoC $wc)
    }
    return (FtoC $tF)
}

function Convert-PacketToRow($h) {
    # Field names: Ecowitt protocol first, Wunderground protocol as fallback.
    $utcText = [string]$h['dateutc']
    $utc = $null
    if ($utcText -and $utcText -ne 'now') {
        $fmt = 'yyyy-MM-dd HH:mm:ss'
        $tmp = [datetime]::MinValue
        if ([datetime]::TryParseExact($utcText, $fmt, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal, [ref]$tmp)) { $utc = $tmp }
    }
    if (-not $utc) { $utc = (Get-Date).ToUniversalTime() }
    $local = [TimeZoneInfo]::ConvertTimeFromUtc($utc, [TimeZoneInfo]::Local)
    $off = [TimeZoneInfo]::Local.GetUtcOffset($local)
    $dateIso = $local.ToString('yyyy-MM-ddTHH:mm:ss') + ('{0}{1:00}:{2:00}' -f $(if ($off.Ticks -lt 0) { '-' } else { '+' }), [math]::Abs($off.Hours), [math]::Abs($off.Minutes))

    $tF     = Get-Num $h @('tempf')
    $rh     = Get-Num $h @('humidity')
    $wind   = Get-Num $h @('windspeedmph')
    $gust   = Get-Num $h @('windgustmph')
    $tInF   = Get-Num $h @('tempinf', 'indoortempf')
    $rhIn   = Get-Num $h @('humidityin', 'indoorhumidity')
    $tC     = FtoC $tF
    $tInC   = FtoC $tInF
    $dewC   = Get-Num $h @('dewptf'); if ($dewC -ne $null) { $dewC = FtoC $dewC } else { $dewC = Get-DewPointC $tC $rh }
    $relIn  = Get-Num $h @('baromrelin', 'baromin')
    $absIn  = Get-Num $h @('baromabsin')
    # batteries: Ecowitt sends 0 = OK / 1 = low; the AWN export shows 1 = OK. Flip to match.
    $battOut = Get-Num $h @('wh65batt', 'battout', 'wh68batt', 'wh80batt', 'wh90batt')
    $battIn  = Get-Num $h @('wh25batt', 'wh26batt', 'battin')
    $mm = 25.4

    $row = [ordered]@{}
    $row['Date']                              = $dateIso
    $row['Simple Date']                       = $local.ToString('yyyy-MM-dd HH:mm:ss')
    $row['Outdoor Temperature (°C)']          = R1 $tC
    $row['Feels Like (°C)']                   = R1 (Get-FeelsLikeC $tF $rh $wind)
    $row['Dew Point (°C)']                    = R1 $dewC
    $row['Wind Speed (mph)']                  = R1 $wind
    $row['Wind Gust (mph)']                   = R1 $gust
    $row['Max Daily Gust (mph)']              = R1 (Get-Num $h @('maxdailygust'))
    $row['Wind Direction (°)']                = R0 (Get-Num $h @('winddir'))
    $row['Rain Rate (mm/hr)']                 = R1 ($(if (($v = Get-Num $h @('rainratein')) -ne $null) { $v * $mm } else { $null }))
    $row['Event Rain (mm)']                   = R1 ($(if (($v = Get-Num $h @('eventrainin')) -ne $null) { $v * $mm } else { $null }))
    $row['Daily Rain (mm)']                   = R1 ($(if (($v = Get-Num $h @('dailyrainin')) -ne $null) { $v * $mm } else { $null }))
    $row['Weekly Rain (mm)']                  = R1 ($(if (($v = Get-Num $h @('weeklyrainin')) -ne $null) { $v * $mm } else { $null }))
    $row['Monthly Rain (mm)']                 = R1 ($(if (($v = Get-Num $h @('monthlyrainin')) -ne $null) { $v * $mm } else { $null }))
    $row['Yearly Rain (mm)']                  = R1 ($(if (($v = Get-Num $h @('yearlyrainin')) -ne $null) { $v * $mm } else { $null }))
    $row['Relative Pressure (mmHg)']          = R1 ($(if ($relIn -ne $null) { $relIn * $mm } else { $null }))
    $row['Humidity (%)']                      = R0 $rh
    $row['Ultra-Violet Radiation Index']      = R0 (Get-Num $h @('uv', 'UV'))
    $row['Solar Radiation (W/m^2)']           = R1 (Get-Num $h @('solarradiation'))
    $row['Indoor Temperature (°C)']           = R1 $tInC
    $row['Indoor Humidity (%)']               = R0 $rhIn
    $row['Avg Wind Direction (10 mins) (°)']  = R0 (Get-Num $h @('winddir_avg10m', 'winddir'))
    $row['Outdoor Battery']                   = $(if ($battOut -ne $null) { R0 (1 - $battOut) } else { '' })
    $row['Absolute Pressure (mmHg)']          = R1 ($(if ($absIn -ne $null) { $absIn * $mm } else { $null }))
    $row['Indoor Battery']                    = $(if ($battIn -ne $null) { R0 (1 - $battIn) } else { '' })
    $row['Indoor Feels Like (°C)']            = R1 (Get-FeelsLikeC $tInF $rhIn 0)
    $row['Indoor Dew Point (°C)']             = R1 (Get-DewPointC $tInC $rhIn)
    return @{ Row = $row; Utc = $utc; Local = $local }
}

function Csv-Escape([string]$s) {
    if ($s -match '[",\r\n]') { return '"' + ($s -replace '"', '""') + '"' }
    return $s
}

function Write-Packet($h, [string]$root, [string]$label) {
    $r = Convert-PacketToRow $h
    $day = $r.Local.ToString('yyyy-MM-dd')
    $csv = Join-Path $root ("{0}_{1}.csv" -f $label, $day)
    $rawDir = Join-Path $root 'raw'
    if (-not (Test-Path -LiteralPath $rawDir)) { New-Item -ItemType Directory -Force -Path $rawDir | Out-Null }
    if (-not (Test-Path -LiteralPath $csv)) {
        $header = ($script:Columns | ForEach-Object { '"' + $_ + '"' }) -join ','
        [IO.File]::AppendAllText($csv, $header + "`r`n", $script:Utf8NoBom)
    }
    $line = ($script:Columns | ForEach-Object { Csv-Escape ([string]$r.Row[$_]) }) -join ','
    [IO.File]::AppendAllText($csv, $line + "`r`n", $script:Utf8NoBom)
    $raw = [ordered]@{ received_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); fields = $h }
    [IO.File]::AppendAllText((Join-Path $rawDir ("{0}_{1}.jsonl" -f $label, $day)), ($raw | ConvertTo-Json -Compress -Depth 3) + "`n", $script:Utf8NoBom)
    return $r
}

function Write-State([string]$root, $extra) {
    $state = [ordered]@{ updated_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); pid = $PID; port = $cfg.Port; path = $cfg.Path }
    foreach ($k in $extra.Keys) { $state[$k] = $extra[$k] }
    $tmp = Join-Path $root 'weather_listener_state.json.tmp'
    [IO.File]::WriteAllText($tmp, ($state | ConvertTo-Json), $script:Utf8NoBom)
    Move-Item -LiteralPath $tmp -Destination (Join-Path $root 'weather_listener_state.json') -Force
}

# ------------------------------------------------------------------ status ----
if ($Status) {
    $sp = Join-Path $cfg.Root 'weather_listener_state.json'
    if (-not (Test-Path -LiteralPath $sp)) { Write-Host "no state file at $sp - listener never ran / never received" -ForegroundColor Red; exit 2 }
    $s = Get-Content -LiteralPath $sp -Raw | ConvertFrom-Json
    if (-not $s.last_packet_local) { Write-Host "listener alive (pid $($s.pid), port $($s.port)) but NO packet received yet - check the console's Customized upload" -ForegroundColor Yellow; exit 2 }
    $age = (Get-Date) - [datetime]$s.last_packet_local
    $msg = 'last packet {0} ({1:n1} min ago), {2} packets today, station time {3} UTC, port {4}{5}' -f $s.last_packet_local, $age.TotalMinutes, $s.packets_today, $s.last_dateutc, $s.port, $s.path
    if ($age.TotalMinutes -gt $StaleMinutes) { Write-Host "STALE: $msg" -ForegroundColor Red; exit 1 }
    Write-Host "OK: $msg" -ForegroundColor Green; exit 0
}

# ---------------------------------------------------------------- selftest ----
if ($SelfTest) {
    $t = Join-Path $env:TEMP ('weather_selftest_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $t | Out-Null
    $ok = $true
    $ecowitt = 'PASSKEY=ABC&stationtype=AMBWeatherPro_V5.1.9&dateutc=2026-09-03+01:10:00&tempinf=82.9&humidityin=54&baromrelin=29.024&baromabsin=29.024&tempf=71.4&humidity=87&winddir=350&winddir_avg10m=168&windspeedmph=12.5&windgustmph=20.6&maxdailygust=21.7&rainratein=0.118&eventrainin=0.551&dailyrainin=0.551&weeklyrainin=1.520&monthlyrainin=1.020&yearlyrainin=11.323&solarradiation=0.0&uv=0&wh65batt=0&wh25batt=0&freq=915M&model=AMBWeatherPro'
    $wu = 'ID=X&PASSWORD=Y&dateutc=2026-09-03%2001%3A15%3A00&tempf=71.0&humidity=88&dewptf=67.3&windspeedmph=10&windgustmph=15&winddir=340&rainin=0.1&dailyrainin=0.6&baromin=29.03&UV=0&solarradiation=0&indoortempf=83&indoorhumidity=55&softwaretype=AMBWeatherPro'
    $r1 = Write-Packet (Parse-Form $ecowitt) $t 'TEST'
    $r2 = Write-Packet (Parse-Form $wu) $t 'TEST'
    $csvs = @(Get-ChildItem $t -Filter 'TEST_*.csv')
    if ($csvs.Count -ne 1) { Write-Host "  FAIL: expected 1 daily csv, got $($csvs.Count)" -ForegroundColor Red; $ok = $false }
    $lines = Get-Content -LiteralPath $csvs[0].FullName -Encoding UTF8
    $expectHeader = ($script:Columns | ForEach-Object { '"' + $_ + '"' }) -join ','
    if ($lines[0] -ne $expectHeader) { Write-Host '  FAIL: header differs from the AWN export schema' -ForegroundColor Red; $ok = $false }
    if ($lines.Count -ne 3) { Write-Host "  FAIL: expected header + 2 rows, got $($lines.Count) lines" -ForegroundColor Red; $ok = $false }
    $cols = ($lines[1] -split ',').Count
    if ($cols -ne 27) { Write-Host "  FAIL: row has $cols columns, expected 27" -ForegroundColor Red; $ok = $false }
    $row = $r1.Row
    if ($row['Outdoor Temperature (°C)'] -ne '21.9')      { Write-Host "  FAIL: 71.4 F -> $($row['Outdoor Temperature (°C)']) C (expected 21.9)" -ForegroundColor Red; $ok = $false }
    if ($row['Relative Pressure (mmHg)'] -ne '737.2')     { Write-Host "  FAIL: 29.024 inHg -> $($row['Relative Pressure (mmHg)']) mmHg (expected 737.2)" -ForegroundColor Red; $ok = $false }
    if ($row['Daily Rain (mm)'] -ne '14')                 { Write-Host "  FAIL: 0.551 in -> $($row['Daily Rain (mm)']) mm (expected 14)" -ForegroundColor Red; $ok = $false }
    if ($row['Dew Point (°C)'] -ne '19.6')                { Write-Host "  FAIL: dew point $($row['Dew Point (°C)']) (expected 19.6 for 21.9 C / 87 %)" -ForegroundColor Red; $ok = $false }
    if ($row['Outdoor Battery'] -ne '1')                  { Write-Host "  FAIL: battery flag $($row['Outdoor Battery']) (expected 1 = OK)" -ForegroundColor Red; $ok = $false }
    if ($row['Date'] -notmatch '^2026-09-0[23]T\d\d:10:00[+-]\d\d:\d\d$') { Write-Host "  FAIL: Date '$($row['Date'])' not local ISO with offset" -ForegroundColor Red; $ok = $false }
    if ($r2.Row['Indoor Temperature (°C)'] -ne '28.3')    { Write-Host "  FAIL: WU indoortempf 83 -> $($r2.Row['Indoor Temperature (°C)']) (expected 28.3)" -ForegroundColor Red; $ok = $false }
    $jsonl = Get-Content -LiteralPath (Join-Path $t ('raw\TEST_' + $r1.Local.ToString('yyyy-MM-dd') + '.jsonl'))
    if (@($jsonl).Count -lt 1 -or ($jsonl[0] | ConvertFrom-Json).fields.tempf -ne '71.4') { Write-Host '  FAIL: raw jsonl missing/incomplete' -ForegroundColor Red; $ok = $false }
    Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue
    if ($ok) { Write-Host 'SELF-TEST PASSED (Ecowitt POST + Wunderground GET -> AWN-schema CSV + raw JSONL)' -ForegroundColor Green; exit 0 }
    Write-Host 'SELF-TEST FAILED' -ForegroundColor Red; exit 2
}

# ---------------------------------------------------------------- listener ----
$mutex = New-Object System.Threading.Mutex($false, 'Global\FieldWeatherListener')
if (-not $mutex.WaitOne(0)) { Write-Host 'another weather_listener instance is running - exiting'; exit 0 }

if (-not (Test-Path -LiteralPath $cfg.Root)) { New-Item -ItemType Directory -Force -Path $cfg.Root | Out-Null }
$prefix = 'http://+:{0}{1}' -f $cfg.Port, $cfg.Path
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
# Also accept the Wunderground-protocol path and plain root so a mis-typed console path still lands.
$listener.Prefixes.Add(('http://+:{0}/weatherstation/' -f $cfg.Port))
$listener.Prefixes.Add(('http://+:{0}/' -f $cfg.Port))
try { $listener.Start() } catch { Write-Log "cannot bind $prefix : $($_.Exception.Message)  (run as SYSTEM task or admin)"; exit 2 }
Write-Log "listening on $prefix (also /weatherstation/ and /) -> $($cfg.Root)"

$lastPacketLocal = $null; $lastDateUtc = $null; $packetsToday = 0; $today = (Get-Date).ToString('yyyy-MM-dd'); $errors = 0
Write-State $cfg.Root @{ last_packet_local = $null; last_dateutc = $null; packets_today = 0; errors = 0 }
$lastHeartbeat = Get-Date

while ($true) {
    $task = $listener.GetContextAsync()
    while (-not $task.Wait(5000)) {
        if (((Get-Date) - $lastHeartbeat).TotalSeconds -ge 60) {
            Write-State $cfg.Root @{ last_packet_local = $lastPacketLocal; last_dateutc = $lastDateUtc; packets_today = $packetsToday; errors = $errors }
            $lastHeartbeat = Get-Date
        }
    }
    $ctx = $task.Result
    try {
        $req = $ctx.Request
        $body = ''
        if ($req.HasEntityBody) {
            $sr = New-Object IO.StreamReader($req.InputStream, $req.ContentEncoding)
            $body = $sr.ReadToEnd(); $sr.Close()
        }
        $fields = Parse-Form $body
        if ($fields.Count -eq 0) { $fields = Parse-Form $req.Url.Query }
        if ($fields.Contains('tempf') -or $fields.Contains('dateutc') -or $fields.Contains('PASSKEY')) {
            $r = Write-Packet $fields $cfg.Root $cfg.StationLabel
            $now = Get-Date
            if ($now.ToString('yyyy-MM-dd') -ne $today) { $today = $now.ToString('yyyy-MM-dd'); $packetsToday = 0 }
            $packetsToday++
            $lastPacketLocal = $now.ToString('yyyy-MM-dd HH:mm:ss'); $lastDateUtc = [string]$fields['dateutc']
            if ($packetsToday -eq 1 -or ($packetsToday % 60) -eq 0) {
                Write-Log ('packet #{0} today from {1}  T={2} C RH={3} %  station utc {4}' -f $packetsToday, $req.RemoteEndPoint.Address, $r.Row['Outdoor Temperature (°C)'], $r.Row['Humidity (%)'], $lastDateUtc)
            }
            Write-State $cfg.Root @{ last_packet_local = $lastPacketLocal; last_dateutc = $lastDateUtc; packets_today = $packetsToday; errors = $errors }
            $lastHeartbeat = Get-Date
        } else {
            Write-Log ('ignored {0} {1} from {2} (no weather fields)' -f $req.HttpMethod, $req.Url.PathAndQuery, $req.RemoteEndPoint.Address)
        }
        $bytes = [Text.Encoding]::ASCII.GetBytes('success')
        $ctx.Response.StatusCode = 200; $ctx.Response.ContentType = 'text/plain'
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } catch {
        $errors++
        Write-Log "request error: $($_.Exception.Message)"
        try { $ctx.Response.StatusCode = 500 } catch { }
    } finally {
        try { $ctx.Response.Close() } catch { }
    }
}
