<#
.SYNOPSIS
    Twice-daily neurologger battery forecast -> Slack: who auto-stops when, and by when
    to START the battery round. Reads only E:\recording_qc\neurologger_telemetry_history.csv
    (the 5-min advertisement snapshots written by neurologger_alive_check.ps1). Never
    touches the console files or any live surface.

.DESCRIPTION
    Per logger, on the CURRENT cell (segment since the last upward voltage jump >= 150 mV
    = a battery swap):
      - slope over the last SlopeWindowHours (needs >= MinSpanHours of span; the advertised
        voltage is 20 mV quantized, so the quoted +/- is 20 mV / span),
      - projected auto-stop with the two-phase model calibrated on cohort-3 (2026-09-03/04):
          plateau: linear at the measured slope down to KneeVolts (3.68 V),
          dive:    KneeVolts -> auto-stop (~3.40 V) takes ~2.0 h for a regular cell (they reach
                   the knee at ~10-12 h of age) and ~4 h for a 1000 mAh cell (knee at ~14-17 h);
                   chosen by the cell's AGE at the knee, not by slope (a low slope can also just
                   be a light load),
      - swap-by = auto-stop minus MarginHours,
      - card: fill rate from the segment (fallback 1.74 %/h = 2.48 MB/s on 512 GB), time to full.
    Fleet advice: "start the round by" = earliest swap-by; swap order = ascending auto-stop;
    plus a check against the next planned round (RoundHours) - warns if anyone dies or any
    card fills before it.

    Why 01:02 / 13:02: evening cells (~19:30-20:00) are ~5 h old at 01:00 and morning cells
    (~08:15) ~4.75 h old at 13:00 - past the surface-charge phase, so the slope is the steady
    one (install-hour slopes are inflated; lesson of 2026-09-02).

.PARAMETER RoundHours   Planned round start times as decimal local hours (default 8.25, 19.75
                        = 08:15 / 19:45). The forecast checks every logger against the NEXT one.
.NOTES
    Exit codes: 0 ok, 1 warning (someone dies or a card fills before the next round), 2 no data.
    Mute: E:\recording_qc\neurologger_alive_MUTED.txt (the shared logger-paging mute).
    Outputs: E:\recording_qc\neurologger_battery_forecast.txt (latest) + _log.txt (one line/run).
#>
[CmdletBinding()]
param(
    [string]$HistoryPath = 'E:\recording_qc\neurologger_telemetry_history.csv',
    [string]$ConfigPath  = 'E:\recording_qc\overexposure.config.psd1',
    [string]$StatusPath  = 'E:\recording_qc\neurologger_battery_forecast.txt',
    [string]$LogPath     = 'E:\recording_qc\neurologger_battery_forecast_log.txt',
    $RoundHours = @(8.25, 19.75),   # decimal local hours; also ONE "8.25,19.75" string (how -File passes it)
    [double]$SlopeWindowHours = 4.0,
    [double]$MinSpanHours = 1.5,
    [double]$KneeVolts = 3.68,
    [double]$StopVolts = 3.40,
    [double]$MarginHours = 1.0,
    [double]$CardFillDefault = 1.74,
    [int]$StaleMinutes = 20,
    [int]$TailLines = 1500,
    [switch]$DryRun,
    [switch]$TestSlack,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

$MutePath = 'E:\recording_qc\neurologger_alive_MUTED.txt'

# -RoundHours arrives as a real array from a PowerShell session but as ONE string ("8.25,19.75")
# when the scheduled task runs 'powershell -File'; a [double[]] parameter then fails to bind, and a
# list without a second decimal point ("17,8.25") would silently parse as 178.25 h (thousands
# separator) -> "next round 10:15". Normalise here, culture-invariant. (Bug found 2026-09-05.)
function ConvertTo-HourList($Raw) {
    $out = @()
    foreach ($item in @($Raw)) {
        foreach ($tok in ("$item" -split '[,; ]+')) {
            if ($tok -eq '') { continue }
            $h = [double]::Parse($tok, [Globalization.CultureInfo]::InvariantCulture)
            if ($h -lt 0 -or $h -ge 24) { throw "RoundHours: '$tok' is not a local hour in 0..24" }
            $out += $h
        }
    }
    return $out
}
$RoundHours = @(ConvertTo-HourList $RoundHours)
if ($RoundHours.Count -eq 0) { $RoundHours = @(8.25, 19.75) }

# ---- reference discharge curve --------------------------------------------------------
# 900 mAh cell on an EVO 512 card, mean of the cohort-3 nights 9/2 and 9/3 (age since install
# in hours -> advertised volts). Steep 4.1->3.9, flat plateau 3.9->3.7, knee, then the dive.
# Life to auto-stop = 14.2 h. A cell is placed on this curve by VOLTAGE (so cell-to-cell
# quality shows up as "already further along"), and its remaining time is scaled by how fast
# it drains relative to the curve over the same span (x0.6 .. x1.5: high-power card .. 1000 mAh).
$script:RefCurve = @(@(0.0, 4.18), @(2.0, 4.04), @(4.0, 3.93), @(6.0, 3.83), @(8.0, 3.77),
                     @(10.0, 3.71), @(12.0, 3.65), @(13.0, 3.58), @(14.0, 3.45), @(14.2, 3.40))
$script:RefLifeH = 14.2
function Get-RefVolts([double]$age) {
    $c = $script:RefCurve
    if ($age -le $c[0][0]) { return [double]$c[0][1] }
    for ($i = 1; $i -lt $c.Count; $i++) {
        if ($age -le $c[$i][0]) {
            $f = ($age - $c[$i-1][0]) / ($c[$i][0] - $c[$i-1][0])
            return [double]($c[$i-1][1] + $f * ($c[$i][1] - $c[$i-1][1]))
        }
    }
    return [double]$c[$c.Count-1][1]
}
function Get-RefAge([double]$v) {
    $c = $script:RefCurve
    if ($v -ge $c[0][1]) { return 0.0 }
    for ($i = 1; $i -lt $c.Count; $i++) {
        if ($v -ge $c[$i][1]) {
            $f = ($c[$i-1][1] - $v) / ($c[$i-1][1] - $c[$i][1])
            return [double]($c[$i-1][0] + $f * ($c[$i][0] - $c[$i-1][0]))
        }
    }
    return [double]$script:RefLifeH
}

# ---- pure forecast core (also exercised by -SelfTest) ------------------------------
function Get-BatteryForecast {
    param([object[]]$Rows, [datetime]$Now, [double]$SlopeWindowHours, [double]$MinSpanHours,
          [double]$KneeVolts, [double]$StopVolts, [double]$MarginHours, [double]$CardFillDefault,
          [int]$StaleMinutes)
    $out = @()
    $labels = @($Rows | Where-Object { $_.Label } | ForEach-Object { $_.Label } | Sort-Object -Unique)
    foreach ($lab in $labels) {
        $lr = @($Rows | Where-Object { $_.Label -eq $lab -and $null -ne $_.Volts } | Sort-Object Ts)
        if ($lr.Count -eq 0) { continue }
        $last = $lr[-1]
        $ageMin = ($Now - $last.Ts).TotalMinutes
        $r = [ordered]@{ Label = $lab; Volts = $last.Volts; Pct = $last.Pct; Ts = $last.Ts
                         AgeMin = [math]::Round($ageMin, 1); Status = 'OK'; SlopeMvH = $null
                         SlopeErr = $null; SpanH = $null; SegH = $null; ExitAt = $null; StopAt = $null
                         SwapBy = $null; FullAt = $null; CardRate = $null; Note = '' }
        if ($ageMin -gt $StaleMinutes) {
            $r.Status = 'STALE'; $r.Note = ('last ad {0} min ago' -f [math]::Round($ageMin))
            $out += [pscustomobject]$r; continue
        }
        # auto-stopped: recording-elapsed frozen across the last 3 samples
        if ($lr.Count -ge 3) {
            $t3 = @($lr[($lr.Count-3)..($lr.Count-1)] | ForEach-Object { $_.Rec })
            if ($null -ne $t3[0] -and $t3[0] -gt 0 -and $t3[0] -eq $t3[1] -and $t3[1] -eq $t3[2]) {
                $r.Status = 'STOPPED'; $r.Note = ('rec frozen at {0} s - auto-stopped' -f $t3[2])
                $out += [pscustomobject]$r; continue
            }
        }
        # current-cell segment: after the last upward jump >= 0.15 V (= a swap)
        $segStart = 0
        for ($i = 1; $i -lt $lr.Count; $i++) { if (($lr[$i].Volts - $lr[$i-1].Volts) -ge 0.15) { $segStart = $i } }
        $seg = @($lr[$segStart..($lr.Count-1)])
        $r.SegH = [math]::Round(($last.Ts - $seg[0].Ts).TotalHours, 2)
        $winStart = $Now.AddHours(-$SlopeWindowHours)
        $win = @($seg | Where-Object { $_.Ts -ge $winStart })
        if ($win.Count -lt 2) { $win = $seg }
        $first = $win[0]
        $spanH = ($last.Ts - $first.Ts).TotalHours
        if ($spanH -lt $MinSpanHours) {
            $r.Status = 'SHORT'; $r.Note = ('only {0} h on this cell - slope not reliable yet' -f [math]::Round($spanH, 1))
            $out += [pscustomobject]$r; continue
        }
        $slope = ($first.Volts - $last.Volts) / $spanH * 1000.0     # mV/h, + = draining
        $r.SpanH = [math]::Round($spanH, 2); $r.SlopeMvH = [math]::Round($slope, 1)
        $r.SlopeErr = [math]::Round(20.0 / $spanH, 1)
        # Place the cell on the reference curve by voltage, then scale the remaining time by
        # its drain rate relative to the curve over the same span (clamped x0.6 .. x1.5).
        $ageT = Get-RefAge $last.Volts
        $remT = $script:RefLifeH - $ageT
        $a0 = [math]::Max(0.0, $ageT - $spanH)
        $sT = ((Get-RefVolts $a0) - (Get-RefVolts $ageT)) / [math]::Max($ageT - $a0, 0.25) * 1000.0
        $factor = 1.0
        if ($slope -le 8.0) { $factor = 1.5 } elseif ($sT -gt 0) { $factor = $sT / $slope }
        if ($factor -lt 0.6) { $factor = 0.6 }
        if ($factor -gt 1.5) { $factor = 1.5 }
        $hStop = $remT * $factor
        $kneeAgeT = Get-RefAge $KneeVolts
        $hExit = [math]::Max(0.0, ($kneeAgeT - $ageT) * $factor)
        $r.ExitAt = $Now.AddHours($hExit)
        $r.StopAt = $Now.AddHours($hStop)
        $r.SwapBy = $r.StopAt.AddHours(-$MarginHours)
        $r.Note = ('drain x{0:F2} of ref' -f (1.0 / $factor))
        if ($last.Volts -le $KneeVolts) { $r.Note = 'past the knee - diving; ' + $r.Note }
        if ($null -ne $last.Pct) {
            $cardRate = $CardFillDefault
            $pw = @($win | Where-Object { $null -ne $_.Pct })
            if ($pw.Count -ge 2) {
                $dp = $pw[-1].Pct - $pw[0].Pct; $dh = ($pw[-1].Ts - $pw[0].Ts).TotalHours
                if ($dh -ge 1.0 -and $dp -ge 0) { $cr = $dp / $dh; if ($cr -gt 0.5) { $cardRate = $cr } }
            }
            $r.CardRate = [math]::Round($cardRate, 2)
            $r.FullAt = $Now.AddHours((100.0 - $last.Pct) / $cardRate)
        }
        $out += [pscustomobject]$r
    }
    return $out
}

function Get-NextRound([datetime]$Now, [double[]]$RoundHours) {
    $cands = @()
    foreach ($d in 0, 1) { foreach ($h in $RoundHours) { $cands += $Now.Date.AddDays($d).AddHours($h) } }
    return ($cands | Where-Object { $_ -gt $Now } | Sort-Object | Select-Object -First 1)
}

# ---- self-test on synthetic data -----------------------------------------------------
if ($SelfTest) {
    $now = Get-Date '2026-09-04 13:02:00'
    $rows = @()
    # synthetic cells generated FROM the reference curve: rateMul = drain speed vs the curve,
    # ageOffset = where on the curve the cell starts
    function Add-Ref([string]$lab, [datetime]$t0, [double]$hours, [double]$rateMul, [double]$ageOffset, [double]$pct0, [double]$recStart) {
        $n = [int]($hours * 12)
        for ($k = 0; $k -le $n; $k++) {
            $t = $t0.AddMinutes(5 * $k); $age = $ageOffset + $rateMul * (5.0 * $k / 60.0)
            $script:rows += [pscustomobject]@{ Ts = $t; Label = $lab; Volts = (Get-RefVolts $age); Pct = ($pct0 + 1.74 * (5.0 * $k / 60.0)); Rec = ($recStart + 300 * $k) }
        }
    }
    Add-Ref 'A' $now.AddHours(-5) 5 1.0 0 30 1000        # exactly on the curve, 5 h old -> 14.2 - 5 = 9.2 h left
    Add-Ref 'B' $now.AddHours(-5) 5 1.0 8.5 30 1000      # on the curve at age 13.5 (past the knee) -> 0.7 h left
    Add-Ref 'C' $now.AddHours(-5) 5 0.5 0 30 1000        # drains at half the curve rate (1000 mAh / light load) -> x1.5 clamp -> 17.55 h
    Add-Ref 'G' $now.AddHours(-5) 5 2.0 0 30 1000        # drains at twice the curve rate (high-power card) -> x0.6 clamp -> 2.52 h
    Add-Ref 'D' $now.AddHours(-5) 2.5 1.0 10 30 1000     # old cell (age 10 -> 12.5), then swap:
    Add-Ref 'D' $now.AddHours(-2.5) 2.5 1.0 0 0 0        #   fresh, 2.5 h on the curve -> 11.7 h left
    Add-Ref 'E' $now.AddHours(-5) 5 1.0 0 30 1000        # E: frozen rec -> STOPPED
    $rows = @($rows | ForEach-Object { if ($_.Label -eq 'E') { $_.Rec = 47719 }; $_ })
    Add-Ref 'F' $now.AddHours(-5) 4.5 1.0 0 30 1000      # F: last sample 30 min old -> STALE
    $fc = Get-BatteryForecast $rows $now 4 1.5 3.68 3.40 1.0 1.74 20
    $ok = $true
    function Check([string]$lab, [double]$expH, [double]$tol) {
        $x = $fc | Where-Object { $_.Label -eq $lab }
        $got = ($x.StopAt - $now).TotalHours
        $pass = [math]::Abs($got - $expH) -le $tol
        Say ("SelfTest {0}: stop in {1:F2} h (expected {2:F2} +/- {3}) -> {4}" -f $lab, $got, $expH, $tol, $(if ($pass) { 'PASS' } else { 'FAIL' })) $(if ($pass) { 'Green' } else { 'Red' })
        if (-not $pass) { $script:ok = $false }
    }
    Check 'A' 9.2 0.25; Check 'B' 0.7 0.15; Check 'C' 17.55 0.4; Check 'D' 11.7 0.3; Check 'G' 2.52 0.3
    $e = $fc | Where-Object { $_.Label -eq 'E' }; $f = $fc | Where-Object { $_.Label -eq 'F' }
    Say ("SelfTest E (frozen rec): {0} -> {1}" -f $e.Status, $(if ($e.Status -eq 'STOPPED') { 'PASS' } else { 'FAIL' }))
    Say ("SelfTest F (stale ad):   {0} -> {1}" -f $f.Status, $(if ($f.Status -eq 'STALE') { 'PASS' } else { 'FAIL' }))
    if ($e.Status -ne 'STOPPED' -or $f.Status -ne 'STALE') { $ok = $false }
    $hl = @(ConvertTo-HourList '17,8.25'); $hl2 = @(ConvertTo-HourList @(8.25, 19.75))
    $hlOk = ($hl.Count -eq 2 -and $hl[0] -eq 17 -and $hl[1] -eq 8.25 -and $hl2.Count -eq 2 -and $hl2[1] -eq 19.75)
    Say ("SelfTest RoundHours parse: '17,8.25' -> {0}; array -> {1} -> {2}" -f ($hl -join '/'), ($hl2 -join '/'), $(if ($hlOk) { 'PASS' } else { 'FAIL' }))
    if (-not $hlOk) { $ok = $false }
    $nr = Get-NextRound $now @(8.25, 19.75)
    Say ("SelfTest next round from 13:02: {0:HH:mm} -> {1}" -f $nr, $(if ($nr.Hour -eq 19 -and $nr.Minute -eq 45) { 'PASS' } else { 'FAIL' }))
    if (-not ($nr.Hour -eq 19 -and $nr.Minute -eq 45)) { $ok = $false }
    Say ("SelfTest: {0}" -f $(if ($ok) { 'PASS' } else { 'FAIL' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# ---- Slack plumbing (same conventions as the other checks) --------------------------
$Slack = @{ Token = $null; Channels = @() }
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $c = Import-PowerShellDataFile -LiteralPath $ConfigPath
        if ($c.SlackBotToken) { $Slack.Token = $c.SlackBotToken }
        if ($c.SlackChannels) { $Slack.Channels = @($c.SlackChannels) }
    } catch { Say "WARNING: could not read $ConfigPath : $($_.Exception.Message)" Yellow }
}
function Send-SlackText([string]$Token, [string[]]$Dests, [string]$Text) {
    $any = $false
    foreach ($d in $Dests) {
        $cid = $d
        try {
            if ($d -match '^[UW]') {
                $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post `
                    -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                    -Body (@{ users = $d } | ConvertTo-Json)
                if (-not $r.ok) { continue }
                $cid = $r.channel.id
            }
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                -Body (@{ channel = $cid; text = $Text } | ConvertTo-Json)
            if ($r.ok) { $any = $true }
        } catch { Say "  Slack($d) error: $($_.Exception.Message)" Yellow }
    }
    return $any
}
if ($TestSlack) {
    if (-not $Slack.Token -or $Slack.Channels.Count -eq 0) { Say "TestSlack: no creds in $ConfigPath" Red; exit 2 }
    $ok = Send-SlackText $Slack.Token $Slack.Channels (":battery: Neurologger battery forecast test ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# ---- load the recent history (tail only; the file grows ~1700 rows/day) --------------
if (-not (Test-Path -LiteralPath $HistoryPath)) { Say "no history at $HistoryPath" Red; exit 2 }
$now = Get-Date
$rows = @()
foreach ($line in (Get-Content -LiteralPath $HistoryPath -Tail $TailLines)) {
    $f = $line -split ','
    if ($f.Count -lt 7 -or $f[0] -notmatch '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$') { continue }
    $ts = [datetime]::ParseExact($f[0], 'yyyy-MM-dd HH:mm:ss', $null)
    $lab = ($f[2] -split ' ')[0]
    $v = $null; $p = $null; $rec = $null; $tmp = 0.0
    if ([double]::TryParse($f[4], [ref]$tmp)) { $v = $tmp }
    if ([double]::TryParse($f[5], [ref]$tmp)) { $p = $tmp }
    if ([double]::TryParse($f[6], [ref]$tmp)) { $rec = $tmp }
    $rows += [pscustomobject]@{ Ts = $ts; Label = $lab; Volts = $v; Pct = $p; Rec = $rec }
}
if ($rows.Count -eq 0) { Say 'no parseable rows' Red; exit 2 }

$fc = Get-BatteryForecast $rows $now $SlopeWindowHours $MinSpanHours $KneeVolts $StopVolts $MarginHours $CardFillDefault $StaleMinutes
$nextRound = Get-NextRound $now $RoundHours
$alive = @($fc | Where-Object { $_.Status -eq 'OK' } | Sort-Object StopAt)
$dieBefore  = @($alive | Where-Object { $_.StopAt -lt $nextRound })
$cardBefore = @($alive | Where-Object { $null -ne $_.FullAt -and $_.FullAt -lt $nextRound })
$stopped = @($fc | Where-Object { $_.Status -eq 'STOPPED' })
$other   = @($fc | Where-Object { $_.Status -in 'STALE', 'SHORT' })

# ---- compose ------------------------------------------------------------------------
$lines = @()
$lines += ("NEUROLOGGER BATTERY FORECAST  {0:yyyy-MM-dd HH:mm}   next planned round {1:ddd HH:mm}" -f $now, $nextRound)
$lines += ('slope = last {0} h on the current cell (20 mV-quantized ads); model: cell placed by voltage on the 900 mAh/EVO reference curve (14.2 h), remaining time scaled by its drain rate vs the curve (x0.6..1.5); knee {1} V; swap-by = stop - {2} h' -f $SlopeWindowHours, $KneeVolts, $MarginHours)
$lines += ('-' * 100)
$lines += ('{0,-5} {1,6} {2,9} {3,7} {4,8} {5,8} {6,8} {7,6} {8,10}  {9}' -f 'rat', 'V', 'mV/h', 'cell h', 'knee', 'STOP', 'swap by', 'card%', 'full at', 'note')
foreach ($x in ($fc | Sort-Object { if ($_.StopAt) { $_.StopAt } else { [datetime]::MaxValue } })) {
    if ($x.Status -eq 'OK') {
        $lines += ('{0,-5} {1,6:F2} {2,5:F0}+/-{3,-3:F0} {4,7:F1} {5,8:HH:mm} {6,8:HH:mm} {7,8:HH:mm} {8,5:F0}% {9,10:ddd HH:mm}  {10}' -f $x.Label, $x.Volts, $x.SlopeMvH, $x.SlopeErr, $x.SegH, $x.ExitAt, $x.StopAt, $x.SwapBy, $x.Pct, $x.FullAt, $x.Note)
    } else {
        $lines += ('{0,-5} {1,6:F2} {2,-9} {3}' -f $x.Label, $x.Volts, $x.Status, $x.Note)
    }
}
$lines += ''
$advice = @()
if ($alive.Count) {
    $startBy = ($alive | ForEach-Object { $_.SwapBy } | Sort-Object | Select-Object -First 1)
    $first = $alive[0]
    $advice += ('START THE ROUND BY {0:HH:mm} ({1} auto-stops ~{2:HH:mm}). Swap order: {3}' -f $startBy, $first.Label, $first.StopAt, (($alive | ForEach-Object { '{0} {1:HH:mm}' -f $_.Label, $_.StopAt }) -join ' > '))
    if ($dieBefore.Count) {
        $advice += ('WARNING: {0} auto-stop BEFORE the {1:HH:mm} round - move the round up to {2:HH:mm} or accept the gap (auto-stop commits; end anchor lost).' -f (($dieBefore | ForEach-Object { $_.Label }) -join ', '), $nextRound, $startBy)
    } else {
        $advice += ('OK: everyone outlasts the {0:HH:mm} round (tightest margin {1} at {2:HH:mm}).' -f $nextRound, $first.Label, $first.StopAt)
    }
    if ($cardBefore.Count) {
        $advice += ('WARNING: card full BEFORE the round: {0}' -f (($cardBefore | ForEach-Object { '{0} ({1:F0}% -> full {2:HH:mm})' -f $_.Label, $_.Pct, $_.FullAt }) -join ', '))
    } else {
        $fullest = $alive | Sort-Object Pct -Descending | Select-Object -First 1
        $advice += ('Cards OK: fullest {0} at {1:F0}% (full ~{2:ddd HH:mm}) - format at the round.' -f $fullest.Label, $fullest.Pct, $fullest.FullAt)
    }
}
if ($stopped.Count) { $advice += ('ALREADY STOPPED: {0}' -f (($stopped | ForEach-Object { $_.Label }) -join ', ')) }
if ($other.Count)   { $advice += ('no forecast: {0}' -f (($other | ForEach-Object { '{0} ({1})' -f $_.Label, $_.Status }) -join ', ')) }
$lines += $advice
$text = $lines -join "`r`n"
$lines | ForEach-Object { Write-Host $_ }

$exit = 0
if ($dieBefore.Count -or $cardBefore.Count -or $stopped.Count) { $exit = 1 }

if (-not $DryRun) {
    Set-Content -LiteralPath $StatusPath -Encoding ASCII -Value $text
    $muted = Test-Path -LiteralPath $MutePath
    $sent = $false
    if (-not $muted -and $Slack.Token -and $Slack.Channels.Count) {
        $head = if ($exit -eq 1) { ':warning:' } else { ':battery:' }
        $per = ($fc | Where-Object { $_.Status -eq 'OK' } | Sort-Object StopAt | ForEach-Object { '{0} {1:F2}V {2:F0}mV/h -> stop ~{3:HH:mm} (card {4:F0}%)' -f $_.Label, $_.Volts, $_.SlopeMvH, $_.StopAt, $_.Pct }) -join "`n"
        $extra = @($fc | Where-Object { $_.Status -ne 'OK' } | ForEach-Object { '{0} {1}: {2}' -f $_.Label, $_.Status, $_.Note }) -join "`n"
        $msg = ('{0} *Neurologger battery forecast* {1:HH:mm} - next planned round {2:ddd HH:mm}' -f $head, $now, $nextRound) + "`n" + ($advice -join "`n") + "`n" + $per
        if ($extra) { $msg += "`n" + $extra }
        $sent = Send-SlackText $Slack.Token $Slack.Channels $msg
    }
    $summary = if ($advice.Count) { $advice[0] } else { 'no alive loggers' }
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ('{0:yyyy-MM-dd HH:mm:ss}  exit={1} muted={2} sent={3}  {4}' -f $now, $exit, $muted, $sent, $summary)
}
exit $exit
