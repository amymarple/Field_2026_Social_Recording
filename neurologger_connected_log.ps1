<#
.SYNOPSIS
    Connected-telemetry logger: the advertisement replacement.

    FM63 firmware (2026-08-31) froze advertisement telemetry while recording, so the
    operator keeps the loggers CONNECTED in wild_console and this script turns their
    1 Hz 0xAF status heartbeats (logged by the console into ble_messages.csv) into:

      1. an append-only telemetry history (one row per logger per run):
             E:\recording_qc\neurologger_connected_telemetry.csv
         ts_local, device, label, volts, used_mb, rec_elapsed_s, hb_age_s
      2. a live status table rewritten every run, with computed ETAs:
             E:\recording_qc\neurologger_connected_status.txt
         battery drain rate + hours to the 3.50 V knee, card fill rate + hours to
         full (card sizes per cohort-3: SF07/08/09 = 512 GB, SF10/11/12 = 128 GB)

    Read-only on the console side (tail of ble_messages.csv only); writes only under
    E:\recording_qc. Runs fine alongside the 5-min alive-check (which pages on the
    same decoded battery values); this script is the fine-grained visibility layer.

    0xAF payload decode (validated 1:1 vs the console GUI 2026-08-31):
      bytes 0-3 rec elapsed s (LE u32) | 4-5 battery raw (LE u16, V = raw*2.0142e-4)
      | 6-9 used storage in 512-B sectors (LE u32)

.NOTES
    Task: 'Field Neurologger Connected Log' every 1 min (see installer).
    Exit codes: 0 ok, 1 = no fresh heartbeats (nothing connected), 2 = error.
#>
[CmdletBinding()]
param(
    [string]$BleLogPath = 'C:\Users\Cornell\AppData\Local\CE32_console\ble_messages.csv',
    [string]$OutCsv     = 'E:\recording_qc\neurologger_connected_telemetry.csv',
    [string]$StatusPath = 'E:\recording_qc\neurologger_connected_status.txt',
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [int]$FreshMinutes  = 10,
    [int]$TailLines     = 1500,
    [double]$KneeVolts  = 3.50,
    [string]$StatePath  = 'E:\recording_qc\neurologger_connected_state.json',
    # Slack pages on connection drop/reconnect. Default OFF since 2026-09-02: the
    # cohort switched from keep-connected to touch-at-rounds, so every intentional
    # disconnect fired a useless DROPPED page 10 min later. Re-enable by adding
    # -DropAlerts to the task args if a keep-connected regime ever returns.
    [switch]$DropAlerts,
    [switch]$DryRun,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'

# cohort-3 card sizes (GB) - last confirmed mapping 2026-09-01 (3x125 + 3x512).
# NB: cards get shuffled at offloads; only the physical read-off is authoritative -
# update here when the mapping changes, it only affects the hours-to-full ETA.
$CardGB = @{ 'SF07' = 125; 'SF08' = 512; 'SF09' = 512; 'SF10' = 125; 'SF11' = 512; 'SF12' = 125 }

function Get-CanonicalDeviceId([string]$name) {
    if (-not $name) { return $null }
    if ($name -match '(?i)^CE64X_([0-9A-F]{12})$') { return $matches[1].ToUpper() }
    if ($name -match '(?i)WILD\s*device\s+((?:[0-9A-F]{2}:){5}[0-9A-F]{2})') {
        $bytes = $matches[1] -split ':'; [array]::Reverse($bytes); return ($bytes -join '').ToUpper()
    }
    return $name.ToUpper()
}

function ConvertFrom-AfPayload([string]$hex) {
    if (-not $hex -or $hex.Length -lt 20) { return $null }
    $b = for ($i = 0; $i -lt 20; $i += 2) { [Convert]::ToInt32($hex.Substring($i, 2), 16) }
    [pscustomobject]@{
        RecSeconds = $b[0] + ($b[1] * 256) + ($b[2] * 65536) + ($b[3] * 16777216)
        Volts      = [math]::Round(($b[4] + ($b[5] * 256)) * 2.0142e-4, 3)
        UsedMB     = [math]::Round(($b[6] + ($b[7] * 256) + ($b[8] * 65536) + ($b[9] * 16777216)) * 512.0 / 1MB, 1)
    }
}

# Linear rate over a series of (time, value): units per hour; $null if span < minSpanH
function Get-RatePerHour($times, $values, [double]$minSpanH = 0.5) {
    $n = @($times).Count
    if ($n -lt 2) { return $null }
    $spanH = ($times[$n - 1] - $times[0]).TotalHours
    if ($spanH -lt $minSpanH) { return $null }
    return ($values[$n - 1] - $values[0]) / $spanH
}

if ($SelfTest) {
    $ok = $true
    $af = ConvertFrom-AfPayload '13050000204F3EB96400'
    if (-not ($af.RecSeconds -eq 1299 -and [math]::Abs($af.Volts - 4.08) -lt 0.005 -and [math]::Abs($af.UsedMB - 3223.2) -lt 1.0)) { Write-Host 'FAIL decode'; $ok = $false }
    $t0 = [datetime]'2026-08-31 20:00'
    $r = Get-RatePerHour @($t0, $t0.AddHours(2)) @(4.00, 3.90)
    if ([math]::Abs($r - (-0.05)) -gt 1e-9) { Write-Host 'FAIL rate'; $ok = $false }
    if ($null -ne (Get-RatePerHour @($t0, $t0.AddMinutes(10)) @(4.0, 3.9))) { Write-Host 'FAIL min-span'; $ok = $false }
    Write-Host $(if ($ok) { 'SelfTest PASS (decode, rate, min-span)' } else { 'SelfTest FAIL' })
    exit $(if ($ok) { 0 } else { 2 })
}

# label map from the shared QC config roster
$labels = @{}
try {
    $c = Import-PowerShellDataFile -LiteralPath $ConfigPath
    if ($c.NeurologgerDevices) {
        foreach ($k in $c.NeurologgerDevices.Keys) { $labels[(Get-CanonicalDeviceId $k)] = $c.NeurologgerDevices[$k] }
    }
} catch { }

$now = Get-Date

# ---- decode fresh heartbeats -----------------------------------------------------
if (-not (Test-Path -LiteralPath $BleLogPath)) { Write-Host "no BLE log at $BleLogPath"; exit 1 }
$latest = @{}
foreach ($line in (Get-Content -LiteralPath $BleLogPath -Tail $TailLines)) {
    $p = $line -split ','
    if ($p.Count -lt 6 -or $p[3] -ne '0xAF') { continue }
    $dec = ConvertFrom-AfPayload $p[5]
    if (-not $dec) { continue }
    $ts = $null
    try { $ts = ([datetimeoffset]::Parse($p[0], [Globalization.CultureInfo]::InvariantCulture)).LocalDateTime } catch { continue }
    if (($now - $ts).TotalMinutes -gt $FreshMinutes) { continue }
    $cid = Get-CanonicalDeviceId $p[2]
    if (-not $latest.ContainsKey($cid) -or $ts -gt $latest[$cid].Seen) {
        $latest[$cid] = [pscustomobject]@{ Seen = $ts; Dev = $p[2]; Volts = $dec.Volts; UsedMB = $dec.UsedMB; RecS = $dec.RecSeconds }
    }
}
if ($latest.Count -eq 0) { Write-Host 'no fresh 0xAF heartbeats - nothing connected?'; exit 1 }

# ---- append history rows ---------------------------------------------------------
if (-not (Test-Path -LiteralPath $OutCsv)) {
    if (-not $DryRun) { Set-Content -LiteralPath $OutCsv -Encoding ASCII -Value 'ts_local,device,label,volts,used_mb,rec_elapsed_s,hb_age_s' }
}
$rowsOut = foreach ($cid in ($latest.Keys | Sort-Object)) {
    $x = $latest[$cid]
    $lbl = if ($labels.ContainsKey($cid)) { $labels[$cid] } else { $cid }
    '{0},{1},{2},{3},{4},{5},{6:F0}' -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $x.Dev, ($lbl -replace ',', ' '), $x.Volts, $x.UsedMB, $x.RecS, ($now - $x.Seen).TotalSeconds
}
if (-not $DryRun) { Add-Content -LiteralPath $OutCsv -Encoding ASCII -Value $rowsOut }

# ---- rates + ETAs from our own recent history ------------------------------------
$hist = @()
try {
    $hist = Get-Content -LiteralPath $OutCsv -Tail 2500 | Select-Object -Skip 0 | ForEach-Object {
        $p = $_ -split ','
        if ($p.Count -ge 6 -and $p[0] -match '^\d{4}-') {
            [pscustomobject]@{ T = [datetime]$p[0]; Label = $p[2]; V = [double]$p[3]; MB = [double]$p[4] }
        }
    } | Where-Object { $_ -and ($now - $_.T).TotalHours -le 3 }
} catch { }

$statusLines = @()
$statusLines += "NEUROLOGGER CONNECTED TELEMETRY (advertisement replacement)  updated $($now.ToString('yyyy-MM-dd HH:mm:ss'))"
$statusLines += "source: wild_console 0xAF heartbeats; rates fitted over the last <=3 h of samples"
$statusLines += ('-' * 100)
$statusLines += '{0,-6} {1,7} {2,12} {3,10} {4,12} {5,11} {6,12} {7,8}' -f 'rat','V','V-rate mV/h','hrs->3.50','used GB','GB/h','hrs->full','hb age'
foreach ($cid in ($latest.Keys | Sort-Object { if ($labels.ContainsKey($_)) { $labels[$_] } else { $_ } })) {
    $x = $latest[$cid]
    $lbl = if ($labels.ContainsKey($cid)) { $labels[$cid] } else { $cid }
    $ser = @($hist | Where-Object { $_.Label -eq ($lbl -replace ',', ' ') } | Sort-Object T)
    $vRate = Get-RatePerHour @($ser | ForEach-Object T) @($ser | ForEach-Object V)
    $mRate = Get-RatePerHour @($ser | ForEach-Object T) @($ser | ForEach-Object MB)
    $vEta = 'n/a'; $vR = 'n/a'
    if ($null -ne $vRate -and $vRate -lt -0.001) {
        $vR = '{0:F0}' -f ($vRate * 1000)
        $vEta = '{0:F1}' -f (($x.Volts - $KneeVolts) / (-$vRate))
    }
    $mEta = 'n/a'; $mR = 'n/a'
    $cardMB = $null
    $lblKey = ($lbl -split ' ')[0]
    if ($CardGB.ContainsKey($lblKey)) { $cardMB = $CardGB[$lblKey] * 1024.0 }
    if ($null -ne $mRate -and $mRate -gt 1) {
        $mR = '{0:F2}' -f ($mRate / 1024)
        if ($cardMB) { $mEta = '{0:F1}' -f (($cardMB - $x.UsedMB) / $mRate) }
    }
    $statusLines += '{0,-6} {1,7:F2} {2,12} {3,10} {4,12} {5,11} {6,12} {7,7:F0}s' -f $lbl, $x.Volts, $vR, $vEta, ('{0:F1}/{1:F0}' -f ($x.UsedMB/1024), $(if ($cardMB) { $cardMB/1024 } else { 0 })), $mR, $mEta, ($now - $x.Seen).TotalSeconds
}
$missing = @($CardGB.Keys | Where-Object { $lb = $_; -not ($latest.Keys | Where-Object { $labels.ContainsKey($_) -and ($labels[$_] -split ' ')[0] -eq $lb }) })
if ($missing) { $statusLines += ''; $statusLines += "NOT CONNECTED (no fresh heartbeat): $(($missing | Sort-Object) -join ', ')" }

if (-not $DryRun) { Set-Content -LiteralPath $StatusPath -Encoding ASCII -Value ($statusLines -join "`r`n") }
$statusLines | ForEach-Object { Write-Host $_ }

# ---- disconnect alert (transition-based; the alive-check may be muted in the
# everyone-connected regime, so this is the pager for dropped connections) --------
$nowLabels = @($latest.Keys | ForEach-Object { if ($labels.ContainsKey($_)) { ($labels[$_] -split ' ')[0] } else { $_ } } | Sort-Object)
$prev = @()
if (Test-Path -LiteralPath $StatePath) {
    try { $prev = @((Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json).connected) } catch { }
}
$dropped = @($prev | Where-Object { $nowLabels -notcontains $_ })
$joined  = @($nowLabels | Where-Object { $prev -notcontains $_ })
if (-not $DryRun) {
    # One mute switch for ALL logger paging: the alive-check's mute file also
    # silences these drop/reconnect alerts (telemetry logging continues regardless).
    $muted = Test-Path -LiteralPath 'E:\recording_qc\neurologger_alive_MUTED.txt'
    if ($DropAlerts -and -not $muted -and ($dropped.Count -gt 0 -or $joined.Count -gt 0)) {
        $tok = $null; $ch = @()
        try { $c2 = Import-PowerShellDataFile -LiteralPath $ConfigPath; $tok = $c2.SlackBotToken; $ch = @($c2.SlackChannels) } catch { }
        if ($tok -and $ch.Count) {
            $parts = @()
            if ($dropped.Count) { $parts += (":warning: logger BLE connection DROPPED: {0} - reconnect in wild_console (keep-connected mode, no advertisement telemetry)" -f ($dropped -join ', ')) }
            if ($joined.Count -and $prev.Count) { $parts += (":white_check_mark: reconnected: {0}" -f ($joined -join ', ')) }
            $body = $parts -join "`n"
            foreach ($d in $ch) {
                $cid = $d
                try {
                    if ($d -match '^[UW]') {
                        $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post -Headers @{ Authorization = "Bearer $tok" } -ContentType 'application/json; charset=utf-8' -Body (@{ users = $d } | ConvertTo-Json)
                        if (-not $r.ok) { continue }
                        $cid = $r.channel.id
                    }
                    [void](Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post -Headers @{ Authorization = "Bearer $tok" } -ContentType 'application/json; charset=utf-8' -Body (@{ channel = $cid; text = $body } | ConvertTo-Json))
                } catch { }
            }
        }
    }
    (@{ connected = $nowLabels; ts = $now.ToString('o') } | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8
}
exit 0
