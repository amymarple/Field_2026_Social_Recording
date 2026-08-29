<#
pc_drift_check.ps1 - passive PC-clock drift monitor (NEVER adjusts the clock).

Measures the offset between this PC's clock and public NTP servers using raw
read-only NTP client queries (UDP 123, built in .NET - works whether or not the
W32Time service is running), appends one row to a CSV, and re-renders a drift
plot PNG. With "Set time automatically" OFF during a cohort, the series is the
PC-vs-true-UTC drift curve:
  - validates the linear-drift assumption on the PC side (neurologger sync model)
  - provides a retroactive PC->UTC mapping for the whole rig (video, mics, WISER,
    wild_console, led_sync all follow this one PC clock)

Outputs (E:\recording_qc):
  pc_drift_log.csv   one row per run: local/UTC time, median offset_ms (PC minus
                     NTP; positive = PC fast), server, sample count, timezone id,
                     DST capability, W32Time service state, status
  pc_drift.png       offset vs time, with drift rate fitted over the last 7 days
                     (1 ppm = 86.4 ms/day)

Task cadence: 4x/day (installer). A run sends a handful of UDP packets - no load.
Exit codes: 0 = ok, 1 = warning (no NTP server reachable; row logged as FAIL),
2 = error.

  powershell -NoProfile -ExecutionPolicy Bypass -File .\pc_drift_check.ps1 -SelfTest
  powershell -NoProfile -ExecutionPolicy Bypass -File .\pc_drift_check.ps1 -DryRun
  powershell -NoProfile -ExecutionPolicy Bypass -File .\pc_drift_check.ps1
#>
param(
    [string]$LogCsv  = 'E:\recording_qc\pc_drift_log.csv',
    [string]$PlotPng = 'E:\recording_qc\pc_drift.png',
    [string[]]$Servers = @('time.windows.com', 'us.pool.ntp.org', 'time.nist.gov'),
    [int]$SamplesPerRun = 5,
    [switch]$DryRun,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$script:NtpEpoch = [datetime]::new(1900, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)

function ConvertFrom-NtpStamp([byte[]]$Bytes, [int]$Offset) {
    $sec  = ($Bytes[$Offset] * 16777216.0) + ($Bytes[$Offset + 1] * 65536.0) + ($Bytes[$Offset + 2] * 256.0) + $Bytes[$Offset + 3]
    $frac = ($Bytes[$Offset + 4] * 16777216.0) + ($Bytes[$Offset + 5] * 65536.0) + ($Bytes[$Offset + 6] * 256.0) + $Bytes[$Offset + 7]
    return $script:NtpEpoch.AddSeconds($sec + ($frac / 4294967296.0))
}

# One read-only NTP exchange. Returns @{OffsetMs; DelayMs} (offset = PC minus NTP;
# positive = PC fast) via the standard formula ((T2-T1)+(T3-T4))/2, or $null on
# failure. DelayMs is the round-trip minus server hold time - the sample with the
# SMALLEST delay is the most trustworthy (asymmetric-path error is bounded by it).
function Get-NtpOffsetMs([string]$Server, [int]$TimeoutMs = 3000) {
    $udp = New-Object System.Net.Sockets.UdpClient
    try {
        $udp.Client.ReceiveTimeout = $TimeoutMs
        $udp.Connect($Server, 123)
        $pkt = New-Object byte[] 48
        $pkt[0] = 0x1B                       # LI=0 VN=3 Mode=3 (client)
        $t1 = [datetime]::UtcNow
        [void]$udp.Send($pkt, 48)
        $ep = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
        $resp = $udp.Receive([ref]$ep)
        $t4 = [datetime]::UtcNow
        if ($resp.Length -lt 48) { return $null }
        $t2 = ConvertFrom-NtpStamp $resp 32  # server receive
        $t3 = ConvertFrom-NtpStamp $resp 40  # server transmit
        if ($t3.Year -lt 2000) { return $null }
        return @{
            OffsetMs = ((($t2 - $t1) + ($t3 - $t4)).TotalMilliseconds) / 2.0
            DelayMs  = (($t4 - $t1) - ($t3 - $t2)).TotalMilliseconds
        }
    } catch {
        return $null
    } finally {
        $udp.Close()
    }
}

function Get-Median([double[]]$Values) {
    $sorted = $Values | Sort-Object
    $n = $sorted.Count
    if ($n -eq 0) { return $null }
    if ($n % 2 -eq 1) { return $sorted[($n - 1) / 2] }
    return ($sorted[$n / 2 - 1] + $sorted[$n / 2]) / 2.0
}

# Least-squares slope of offset_ms vs elapsed ms -> drift in ppm (1 ppm = 86.4 ms/day).
function Get-DriftFit([datetime[]]$Times, [double[]]$Offsets) {
    $n = $Times.Count
    if ($n -lt 2 -or ($Times[$n - 1] - $Times[0]).TotalHours -lt 6) { return $null }
    $x = @(); foreach ($t in $Times) { $x += ($t - $Times[0]).TotalMilliseconds }
    $mx = ($x | Measure-Object -Average).Average
    $my = ($Offsets | Measure-Object -Average).Average
    $sxx = 0.0; $sxy = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx = $x[$i] - $mx
        $sxx += $dx * $dx
        $sxy += $dx * ($Offsets[$i] - $my)
    }
    if ($sxx -le 0) { return $null }
    $slope = $sxy / $sxx                     # ms offset per ms elapsed
    return [pscustomobject]@{ Ppm = $slope * 1e6; MsPerDay = $slope * 86400000.0 }
}

function Write-DriftPlot([string]$CsvPath, [string]$PngPath) {
    $rows = @(Import-Csv $CsvPath | Where-Object { $_.status -match '^OK' })
    if ($rows.Count -lt 2) { return $false }
    $times = @(); $offsets = @()
    foreach ($r in $rows) {
        $times += [datetime]::Parse($r.local_time, $null, [Globalization.DateTimeStyles]::RoundtripKind)
        $offsets += [double]$r.offset_ms
    }
    $cut = ([datetime]$times[-1]).AddDays(-7)
    $fitTimes = @(); $fitOffsets = @()
    for ($i = 0; $i -lt $times.Count; $i++) {
        if ($times[$i] -ge $cut) { $fitTimes += $times[$i]; $fitOffsets += $offsets[$i] }
    }
    $fit = Get-DriftFit $fitTimes $fitOffsets
    $fitText = 'drift: n/a (need >=6 h of points)'
    if ($fit) { $fitText = ('drift last 7d: {0:+0.0;-0.0} ms/day ({1:+0.00;-0.00} ppm)' -f $fit.MsPerDay, $fit.Ppm) }

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Windows.Forms.DataVisualization
    $chart = New-Object System.Windows.Forms.DataVisualization.Charting.Chart
    $chart.Width = 1400; $chart.Height = 500
    $area = New-Object System.Windows.Forms.DataVisualization.Charting.ChartArea
    $area.AxisX.LabelStyle.Format = 'MM-dd HH:mm'
    $area.AxisX.MajorGrid.LineColor = [System.Drawing.Color]::Gainsboro
    $area.AxisY.MajorGrid.LineColor = [System.Drawing.Color]::Gainsboro
    $area.AxisY.Title = 'PC minus NTP (ms); positive = PC fast'
    $chart.ChartAreas.Add($area)
    $series = New-Object System.Windows.Forms.DataVisualization.Charting.Series
    $series.ChartType = [System.Windows.Forms.DataVisualization.Charting.SeriesChartType]::Line
    $series.XValueType = [System.Windows.Forms.DataVisualization.Charting.ChartValueType]::DateTime
    $series.MarkerStyle = [System.Windows.Forms.DataVisualization.Charting.MarkerStyle]::Circle
    $series.MarkerSize = 5
    $series.BorderWidth = 2
    for ($i = 0; $i -lt $times.Count; $i++) { [void]$series.Points.AddXY($times[$i], $offsets[$i]) }
    $chart.Series.Add($series)
    $title = 'PC clock vs NTP  -  latest {0:+0.0;-0.0} ms @ {1:MM-dd HH:mm}  -  {2}' -f $offsets[-1], $times[-1], $fitText
    [void]$chart.Titles.Add($title)
    $chart.SaveImage($PngPath, 'Png')
    $chart.Dispose()
    return $true
}

if ($SelfTest) {
    $ok = $true
    # NTP stamp decode: seconds=1, fraction=0.5 s after the 1900 epoch
    $b = New-Object byte[] 48
    $b[35] = 1; $b[36] = 0x80
    $dt = ConvertFrom-NtpStamp $b 32
    if ([math]::Abs((($dt - $script:NtpEpoch).TotalSeconds) - 1.5) -gt 1e-6) { Write-Host 'FAIL ntp stamp decode'; $ok = $false }
    # drift fit: +86.4 ms over 1 day = +1 ppm
    $t0 = [datetime]::new(2026, 8, 1, 0, 0, 0)
    $fit = Get-DriftFit @($t0, $t0.AddHours(12), $t0.AddDays(1)) @(0.0, 43.2, 86.4)
    if (-not $fit -or [math]::Abs($fit.Ppm - 1.0) -gt 0.001) { Write-Host 'FAIL drift fit'; $ok = $false }
    if ((Get-Median @(3.0, 1.0, 2.0)) -ne 2.0) { Write-Host 'FAIL median'; $ok = $false }
    if ($ok) { Write-Host 'SelfTest PASS (ntp decode, drift fit, median)'; exit 0 }
    exit 2
}

# ---- measure -------------------------------------------------------------------
# Query ALL servers, keep the single sample with the smallest round-trip delay
# (the standard NTP filter - path-asymmetry error is bounded by delay/2). Rows
# whose best delay is still >200 ms are flagged OK-noisy so analysis can weight
# or drop them.
$allSamples = @()
foreach ($server in $Servers) {
    for ($i = 0; $i -lt $SamplesPerRun; $i++) {
        $one = Get-NtpOffsetMs $server
        if ($one -ne $null) {
            $allSamples += [pscustomobject]@{ OffsetMs = $one.OffsetMs; DelayMs = $one.DelayMs; Server = $server }
        }
        Start-Sleep -Milliseconds 250
    }
}

$offsetMs = $null; $delayMs = $null; $usedServer = ''; $sampleCount = $allSamples.Count
$tz = Get-TimeZone
$w32 = 'unknown'
try { $w32 = (Get-Service W32Time -ErrorAction Stop).Status } catch { }
if ($sampleCount -gt 0) {
    $best = $allSamples | Sort-Object DelayMs | Select-Object -First 1
    $offsetMs = $best.OffsetMs
    $delayMs = $best.DelayMs
    $usedServer = $best.Server
    $status = 'OK'
    if ($delayMs -gt 200) { $status = 'OK-noisy' }
} else {
    $status = 'FAIL:no-ntp-response'
    $usedServer = ($Servers -join '|')
}

$row = [pscustomobject]@{
    local_time  = [datetime]::Now.ToString('yyyy-MM-ddTHH:mm:sszzz')
    utc_time    = [datetime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    offset_ms   = if ($offsetMs -ne $null) { [math]::Round($offsetMs, 1) } else { '' }
    delay_ms    = if ($delayMs -ne $null) { [math]::Round($delayMs, 1) } else { '' }
    server      = $usedServer
    samples     = $sampleCount
    tz_id       = $tz.Id
    dst_capable = $tz.SupportsDaylightSavingTime
    w32time     = $w32
    status      = $status
}

if ($DryRun) {
    Write-Host 'DryRun - would append:'
    $row | Format-List | Out-String | Write-Host
    if ($status -ne 'OK') { exit 1 }
    exit 0
}

$dir = Split-Path $LogCsv -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
if (-not (Test-Path $LogCsv)) {
    $row | Export-Csv -Path $LogCsv -NoTypeInformation -Encoding ASCII
} else {
    $line = ($row.PSObject.Properties | ForEach-Object { '"{0}"' -f ("$($_.Value)" -replace '"', '""') }) -join ','
    Add-Content -Path $LogCsv -Value $line -Encoding ASCII
}

try {
    [void](Write-DriftPlot $LogCsv $PlotPng)
} catch {
    Write-Host "warning: plot render failed ($($_.Exception.Message)); CSV row was written"
}

Write-Host ("pc_drift: {0}  offset_ms={1}  server={2}  samples={3}" -f $status, $row.offset_ms, $row.server, $row.samples)
if ($status -ne 'OK') { exit 1 }
exit 0
