<#
.SYNOPSIS
    Near-real-time "LOGGER MISSING" Slack alert for the Neurologger (CE64X) fleet.

    wild_console continuously rewrites a snapshot CSV of every logger it can hear
    over BLE (last_seen, battery, storage). This watchdog reads that CSV and pages
    when a logger has not been seen for -StaleMinutes (default 60 - per the field
    protocol, shorter dropouts are normal BLE flakiness), when the CSV feed itself
    stops updating (wild_console closed / scan stopped on the main PC), and sends
    one-shot warnings for low battery or high on-board storage.

    Read-only: it reads ONE csv file and sends Slack messages. It never talks BLE,
    never touches the loggers, and never touches any recording.

.PARAMETER CsvPath           discovered_devices.csv written by wild_console
                             (%LOCALAPPDATA%\CE32_console of the console user; the
                             default is the Cornell profile because the SYSTEM task
                             has its own LOCALAPPDATA).
.PARAMETER StaleMinutes      Page when a logger's last_seen is older than this
                             (default 60 - matches the Notion Daily Checks rule
                             "missing >= 1 hour -> be alert").
.PARAMETER FeedStaleMinutes  Page when the CSV itself has not been rewritten for
                             this long (default 15): wild_console is closed or its
                             BLE scan stopped, so logger status is unknown.
.PARAMETER BatteryWarnVolts  One-shot warning below this voltage (default 3.60).
.PARAMETER BatteryCriticalVolts  One-shot CRITICAL page below this voltage (default
                             3.50 - the LiPo discharge knee; below it the cell drops
                             fast, so this means "hours left, swap now").
.PARAMETER StorageWarnPercent One-shot warning above this used-% (default 90).
.PARAMETER ConfigPath        Slack creds (reused from the overexposure QC config).
                             Optional key NeurologgerDevices = @{ device_name = 'label' }
                             overrides the built-in cohort roster without reinstalling.
.PARAMETER RealertHours      While loggers stay missing, re-alert at most this often.
.PARAMETER ReminderTimes     Local HH:mm slots; once per day per slot (within a 30-min
                             window after it) a Slack reminder of the battery-round
                             sync ritual is sent (default 05:40 + 17:40, 20 min before
                             the cohort-3 rounds). Fires even when the console feed is
                             down - the reminder is for the humans doing the round.
                             Pass @() to disable.
.PARAMETER HistoryPath       Append-only telemetry time series (one row per logger per
                             run: battery V, storage %, recording elapsed s). Trend
                             data only - nothing alerts on it yet.
.PARAMETER DryRun            Print status only; send nothing, update no state.
.PARAMETER TestSlack         Send a test message to the configured destinations, then exit.
.PARAMETER SelfTest          Offline logic check on synthetic CSV rows (no Slack, no state).

.NOTES
    Exit codes: 0 all healthy, 1 warnings (missing logger / battery / storage),
    2 errors (feed stale or unreadable, no roster).
    State: healthy->missing pages once, re-pages every RealertHours, recovery note
    when all loggers are seen again. Battery/storage warn once per excursion.
#>

[CmdletBinding()]
param(
    [string]$CsvPath = 'C:\Users\Cornell\AppData\Local\CE32_console\discovered_devices.csv',
    [int]$StaleMinutes = 60,
    [int]$FeedStaleMinutes = 15,
    [double]$BatteryWarnVolts = 3.60,
    [double]$BatteryCriticalVolts = 3.50,
    [int]$StorageWarnPercent = 90,
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$StatePath = 'E:\recording_qc\neurologger_alive_state.json',
    [string]$LogPath = 'E:\recording_qc\neurologger_alive_log.txt',
    [string]$HistoryPath = 'E:\recording_qc\neurologger_telemetry_history.csv',
    [int]$RealertHours = 1,
    [string[]]$ReminderTimes = @('05:40', '17:40'),
    [switch]$DryRun,
    [switch]$TestSlack,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

# --- kill switch: drop this file to silence the whole watchdog (no admin needed);
# delete it to resume. Used during battery swaps / logger handling.
$MutePath = 'E:\recording_qc\neurologger_alive_MUTED.txt'
if (Test-Path -LiteralPath $MutePath) {
    Say "MUTED via $MutePath - exiting without checks or alerts." Yellow
    exit 0
}

# --- cohort roster: device_name -> label. Override with NeurologgerDevices in the
# QC config (read each run - no task re-install when the cohort changes).
$Roster = [ordered]@{
    'CE64X_F0EC3F3364C4' = 'SF01 Delta'
    'CE64X_A7FABDB0B216' = 'SF02 Puffy'
    'CE64X_1292FFF360C0' = 'SF03 Theta'
    'CE64X_A2C96D606437' = 'SF04 Ripples'
    'CE64X_A7F8EDC4A051' = 'SF05 Maria'
    'CE64X_CACB6D600151' = 'SF06 Barrs'
}

# --- Slack config (token + destinations live in the QC config, kept out of git) ---
$Slack = @{ Token = $null; Channels = @(); Recovery = $true }
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $c = Import-PowerShellDataFile -LiteralPath $ConfigPath
        if ($c.SlackBotToken) { $Slack.Token = $c.SlackBotToken }
        if ($c.SlackChannels) { $Slack.Channels = $c.SlackChannels }
        if ($null -ne $c.SendRecovery) { $Slack.Recovery = $c.SendRecovery }
        if ($c.NeurologgerDevices) {
            $Roster = [ordered]@{}
            foreach ($k in $c.NeurologgerDevices.Keys) { $Roster[$k] = $c.NeurologgerDevices[$k] }
        }
    } catch { Say "WARNING: could not read $ConfigPath : $($_.Exception.Message)" Yellow }
} else { Say "No Slack config at $ConfigPath (will print only)." Yellow }

function Resolve-SlackChannelId([string]$Token, [string]$Dest) {
    if ($Dest -match '^[UW]') {
        try {
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                -Body (@{ users = $Dest } | ConvertTo-Json)
            if ($r.ok) { return $r.channel.id }
            Say "  conversations.open($Dest) failed: $($r.error)" Yellow; return $null
        } catch { Say "  conversations.open($Dest) error: $($_.Exception.Message)" Yellow; return $null }
    }
    return $Dest
}

function Send-SlackText([string]$Token, [string[]]$Dests, [string]$Text) {
    $any = $false
    foreach ($d in $Dests) {
        $cid = Resolve-SlackChannelId $Token $d
        if (-not $cid) { continue }
        try {
            $r = Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json; charset=utf-8' `
                -Body (@{ channel = $cid; text = $Text } | ConvertTo-Json)
            if ($r.ok) { $any = $true } else { Say "  chat.postMessage($d) failed: $($r.error)" Yellow }
        } catch { Say "  chat.postMessage($d) error: $($_.Exception.Message)" Yellow }
    }
    return $any
}

function Get-ShortId([string]$name) {
    if ($name.Length -ge 4) { return $name.Substring($name.Length - 4) }
    return $name
}

# The console reports a logger as 'CE64X_<12 hex>' when it resolved the advertised
# name, but falls back to 'WILD device XX:XX:XX:XX:XX:XX' (BLE MAC, byte-REVERSED
# relative to the hex form) when the name scan-response is lost - common at weak
# RSSI, and the SAME logger can flip between forms across snapshots (seen at
# cohort-3 start 2026-08-30). Reduce both to one canonical 12-hex id for matching.
function Get-CanonicalDeviceId([string]$name) {
    if (-not $name) { return $null }
    if ($name -match '(?i)^CE64X_([0-9A-F]{12})$') { return $matches[1].ToUpper() }
    if ($name -match '(?i)WILD\s*device\s+((?:[0-9A-F]{2}:){5}[0-9A-F]{2})') {
        $bytes = $matches[1] -split ':'
        [array]::Reverse($bytes)
        return ($bytes -join '').ToUpper()
    }
    return $name.ToUpper()
}

# --- core evaluation (pure - also used by -SelfTest) ---
# rows: objects with device_name, last_seen_local, battery_voltage_volts, used_storage_percent
# returns per-logger status + warn lists
function Get-FleetStatus($rows, $roster, [datetime]$now, [int]$staleMin, [double]$battWarn, [int]$storWarn, [double]$battCrit = 0, $lastKnown = @{}) {
    # key rows by canonical id; when both name forms of one logger appear, keep the
    # row with the newest last_seen
    $byName = @{}
    foreach ($r in $rows) {
        if (-not $r.device_name) { continue }
        $cid = Get-CanonicalDeviceId $r.device_name
        if ($byName.ContainsKey($cid)) {
            try {
                $tNew = [datetimeoffset]::Parse($r.last_seen_local, [Globalization.CultureInfo]::InvariantCulture)
                $tOld = [datetimeoffset]::Parse($byName[$cid].last_seen_local, [Globalization.CultureInfo]::InvariantCulture)
                if ($tNew -gt $tOld) { $byName[$cid] = $r }
            } catch { $byName[$cid] = $r }
        } else { $byName[$cid] = $r }
    }
    $known = @{}
    foreach ($k in $lastKnown.Keys) { $known[(Get-CanonicalDeviceId $k)] = $lastKnown[$k] }
    $missing = @(); $battLow = @(); $battCritical = @(); $storHigh = @(); $detail = @()
    foreach ($devKey in $roster.Keys) {
        $dev = Get-CanonicalDeviceId $devKey
        $label = $roster[$devKey]; $sid = Get-ShortId $devKey
        if (-not $byName.ContainsKey($dev)) {
            # No row in the snapshot. A wild_console restart wipes the discovered list
            # and devices repopulate over minutes - grant grace if our own telemetry
            # history saw this device within the stale window (false-page fix 2026-08-23).
            if ($known.ContainsKey($dev) -and (($now - $known[$dev]).TotalMinutes -le $staleMin)) {
                $detail += ("{0} ok(no row yet, history {1:F0}m ago - console list rebuilding)" -f $label, ($now - $known[$dev]).TotalMinutes)
                continue
            }
            $missing += ("{0} (...{1}, not in list)" -f $label, $sid)
            $detail += ("{0} MISSING(no row)" -f $label)
            continue
        }
        $row = $byName[$dev]
        $ageMin = $null
        try {
            $seen = [datetimeoffset]::Parse($row.last_seen_local, [Globalization.CultureInfo]::InvariantCulture)
            $ageMin = [math]::Round(($now - $seen.LocalDateTime).TotalMinutes, 1)
        } catch { }
        if ($null -eq $ageMin) {
            $missing += ("{0} (...{1}, unreadable last_seen)" -f $label, $sid)
            $detail += ("{0} MISSING(bad timestamp)" -f $label)
            continue
        }
        if ($ageMin -gt $staleMin) {
            $missing += ("{0} (...{1}, last seen {2} min ago)" -f $label, $sid, $ageMin)
            $detail += ("{0} MISSING({1}m)" -f $label, $ageMin)
        } else {
            $detail += ("{0} ok({1}m)" -f $label, $ageMin)
        }
        $v = 0.0
        if ([double]::TryParse($row.battery_voltage_volts, [ref]$v)) {
            if ($v -gt 0 -and $v -lt $battWarn) { $battLow += ("{0} {1:F2} V" -f $label, $v) }
            if ($v -gt 0 -and $battCrit -gt 0 -and $v -lt $battCrit) { $battCritical += ("{0} {1:F2} V" -f $label, $v) }
        }
        $p = 0
        if ([int]::TryParse($row.used_storage_percent, [ref]$p)) {
            if ($p -ge $storWarn) { $storHigh += ("{0} {1}% used" -f $label, $p) }
        }
    }
    return [pscustomobject]@{ Missing = $missing; BattLow = $battLow; BattCritical = $battCritical; StorHigh = $storHigh; Detail = $detail }
}

# Which reminder slot (HH:mm) is due: within windowMin after the slot time and not
# already sent today (sentMap: slot -> 'yyyy-MM-dd'). Returns the slot or $null.
function Get-DueReminderSlot([datetime]$now, [string[]]$slots, $sentMap, [int]$windowMin = 30) {
    foreach ($slot in $slots) {
        $parts = $slot -split ':'
        if ($parts.Count -ne 2) { continue }
        $slotTime = $now.Date.AddHours([int]$parts[0]).AddMinutes([int]$parts[1])
        if ($now -ge $slotTime -and ($now - $slotTime).TotalMinutes -le $windowMin) {
            $already = $null
            if ($sentMap -and $sentMap.ContainsKey($slot)) { $already = [string]$sentMap[$slot] }
            if ($already -ne $now.ToString('yyyy-MM-dd')) { return $slot }
        }
    }
    return $null
}

# --- SELF TEST: synthetic rows, no Slack, no disk state ---
if ($SelfTest) {
    $now = Get-Date
    $off = (Get-Date).ToString('zzz')  # local offset like -04:00
    function New-Row([string]$n, [datetime]$seen, [string]$v, [string]$p) {
        [pscustomobject]@{ device_name = $n; last_seen_local = $seen.ToString('yyyy-MM-ddTHH:mm:ss.fffffff') + $off; battery_voltage_volts = $v; used_storage_percent = $p }
    }
    $tr = [ordered]@{ 'CE64X_AAAA' = 'SF01 T'; 'CE64X_BBBB' = 'SF02 T'; 'CE64X_CCCC' = 'SF03 T'; 'CE64X_DDDD' = 'SF04 T'; 'CE64X_EEEE' = 'SF05 T'; 'CE64X_FFFF' = 'SF06 T' }
    $rows = @(
        (New-Row 'CE64X_AAAA' $now                    '3.78' '35')   # fresh, healthy
        (New-Row 'CE64X_BBBB' $now.AddMinutes(-120)   '3.78' '35')   # stale 2 h
        # CE64X_CCCC: no row at all
        (New-Row 'CE64X_DDDD' $now                    '3.55' '35')   # fresh, warn-band battery
        (New-Row 'CE64X_EEEE' $now                    '3.78' '95')   # fresh, storage high
        (New-Row 'CE64X_FFFF' $now.AddMinutes(-5)     '3.44' '35')   # fresh, CRITICAL battery
    )
    $s = Get-FleetStatus $rows $tr $now 60 3.60 90 3.50
    $gotMissing = @($s.Missing | ForEach-Object { ($_ -split ' ')[0] }) -join ','
    $okMissing = ($gotMissing -eq 'SF02,SF03')
    # console-restart grace: SF03 has no row but history saw it 10 min ago -> not missing
    $s2 = Get-FleetStatus $rows $tr $now 60 3.60 90 3.50 @{ 'CE64X_CCCC' = $now.AddMinutes(-10) }
    $gotMissing2 = @($s2.Missing | ForEach-Object { ($_ -split ' ')[0] }) -join ','
    $okGrace = ($gotMissing2 -eq 'SF02')
    Say ("SelfTest restart-grace: [{0}] expected [SF02] -> {1}" -f $gotMissing2, $(if ($okGrace) { 'PASS' } else { 'FAIL' }))
    $gotBatt = @($s.BattLow | ForEach-Object { ($_ -split ' ')[0] }) -join ','
    $okBatt = ($gotBatt -eq 'SF04,SF06')
    $okCrit = (@($s.BattCritical).Count -eq 1 -and $s.BattCritical[0] -like 'SF06*')
    $okStor = (@($s.StorHigh).Count -eq 1 -and $s.StorHigh[0] -like 'SF05*')
    Say ("SelfTest detail: {0}" -f ($s.Detail -join ' | '))
    Say ("SelfTest missing: [{0}] expected [SF02,SF03] -> {1}" -f $gotMissing, $(if ($okMissing) { 'PASS' } else { 'FAIL' }))
    Say ("SelfTest battery warn: [{0}] expected [SF04,SF06] -> {1}" -f $gotBatt, $(if ($okBatt) { 'PASS' } else { 'FAIL' }))
    Say ("SelfTest battery CRIT: [{0}] expected [SF06] -> {1}" -f ($s.BattCritical -join ','), $(if ($okCrit) { 'PASS' } else { 'FAIL' }))
    Say ("SelfTest storage: [{0}] -> {1}" -f ($s.StorHigh -join ','), $(if ($okStor) { 'PASS' } else { 'FAIL' }))
    # canonical-id matching: MAC form is byte-reversed relative to the CE64X_ hex form
    $c1 = Get-CanonicalDeviceId 'CE64X_1DFE7F77721C'
    $c2 = Get-CanonicalDeviceId 'WILD device 1C:72:77:7F:FE:1D'
    $c3 = Get-CanonicalDeviceId 'WILD device 51:01:60:6D:CB:CA'
    $okCanon = ($c1 -eq '1DFE7F77721C') -and ($c2 -eq '1DFE7F77721C') -and ($c3 -eq 'CACB6D600151')
    $trC = [ordered]@{ 'CE64X_CACB6D600151' = 'SF10 T' }
    $rowsC = @([pscustomobject]@{ device_name = 'WILD device 51:01:60:6D:CB:CA'; last_seen_local = $now.ToString('yyyy-MM-ddTHH:mm:ss.fffffff') + $off; battery_voltage_volts = '4.10'; used_storage_percent = '10' })
    $sC = Get-FleetStatus $rowsC $trC $now 60 3.60 90 3.50
    $okCanonMatch = (@($sC.Missing).Count -eq 0)
    Say ("SelfTest canonical id: forms {0} + MAC-form roster match {1}" -f $(if ($okCanon) { 'PASS' } else { "FAIL [$c1|$c2|$c3]" }), $(if ($okCanonMatch) { 'PASS' } else { 'FAIL' }))
    $rt = @('05:40', '17:40')
    $r1 = Get-DueReminderSlot ([datetime]'2026-08-29 05:50') $rt @{}
    $r2 = Get-DueReminderSlot ([datetime]'2026-08-29 05:50') $rt @{ '05:40' = '2026-08-29' }
    $r3 = Get-DueReminderSlot ([datetime]'2026-08-29 06:30') $rt @{}
    $r4 = Get-DueReminderSlot ([datetime]'2026-08-29 17:41') $rt @{ '05:40' = '2026-08-29' }
    $r5 = Get-DueReminderSlot ([datetime]'2026-08-30 05:45') $rt @{ '05:40' = '2026-08-29' }  # new day -> due again
    $okRem = ($r1 -eq '05:40') -and ($null -eq $r2) -and ($null -eq $r3) -and ($r4 -eq '17:40') -and ($r5 -eq '05:40')
    Say ("SelfTest reminders: due/sent/late/evening/next-day -> {0}" -f $(if ($okRem) { 'PASS' } else { "FAIL [$r1|$r2|$r3|$r4|$r5]" }))
    $ok = $okMissing -and $okBatt -and $okCrit -and $okStor -and $okGrace -and $okRem -and $okCanon -and $okCanonMatch
    Say ("SelfTest: {0}" -f $(if ($ok) { 'PASS' } else { 'FAIL' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

if ($TestSlack) {
    if (-not $Slack.Token -or $Slack.Channels.Count -eq 0) { Say "TestSlack: set SlackBotToken/SlackChannels in $ConfigPath first." Red; exit 2 }
    $ok = Send-SlackText $Slack.Token $Slack.Channels (":satellite: Neurologger alive check test - watchdog wired up ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

if ($Roster.Keys.Count -eq 0) { Say 'Roster is empty - nothing to watch.' Red; exit 2 }

# --- load state (de-dup / re-alert / recovery) ---
$state = @{ missing = $false; lastAlert = $null; feedDown = $false; feedLastAlert = $null; battWarned = @(); battCritWarned = @(); storWarned = @(); reminded = @{} }
if (Test-Path -LiteralPath $StatePath) {
    try {
        $s = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        $state.missing = [bool]$s.missing; $state.lastAlert = $s.lastAlert
        $state.feedDown = [bool]$s.feedDown; $state.feedLastAlert = $s.feedLastAlert
        if ($s.PSObject.Properties['battWarned']) { $state.battWarned = @($s.battWarned) }
        if ($s.PSObject.Properties['battCritWarned']) { $state.battCritWarned = @($s.battCritWarned) }
        if ($s.PSObject.Properties['storWarned']) { $state.storWarned = @($s.storWarned) }
        if ($s.PSObject.Properties['reminded']) {
            foreach ($p in $s.reminded.PSObject.Properties) { $state.reminded[$p.Name] = [string]$p.Value }
        }
    } catch {}
}
function Save-State { if (-not $DryRun) { ($state | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8 } }
function Log-Line([string]$status, [string]$action, $sent) {
    if (-not $DryRun) { Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ("{0}  {1}  action={2} sent={3}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $status, $action, $sent) }
}

$now = Get-Date

# --- twice-daily battery-round sync reminder (before the feed checks on purpose:
# it must fire even when wild_console is closed - it reminds the HUMANS) ---
$dueSlot = Get-DueReminderSlot $now $ReminderTimes $state.reminded
if ($dueSlot) {
    $remind = ":alarm_clock: *Battery round soon - logger sync steps (per rat):*`n" +
        "1) BEFORE pulling the battery: Connect in wild_console, write the ``Sync[Live] dev=`` value into the daily table (that IS the closing session's clock offset), stay connected ~1 min so time anchors land.`n" +
        "2) Swap the battery.`n" +
        "3) Reconnect -> Reset -> wait ``Cmd:`` >= 256 -> ``Sync[Live] err`` within a few ms (else Resync) -> *Record Start* (Recording time walks + Storage grows) -> preview ON.`n" +
        "4) After any SD offload: ``python WILD_generate_pc_time.py <folder> --summary-plot`` -> anchors at BOTH ends, flat residuals. Log misses in the Notion notes."
    if ($DryRun) {
        Say "DryRun: reminder due for slot $dueSlot (not sent)" Yellow
    } else {
        $rSent = $false
        if ($Slack.Token -and $Slack.Channels.Count) { $rSent = Send-SlackText $Slack.Token $Slack.Channels $remind }
        else { Say "(no Slack creds; reminder would be: $remind)" DarkYellow }
        $state.reminded[$dueSlot] = $now.ToString('yyyy-MM-dd')
        Save-State
        Log-Line "sync reminder slot $dueSlot" 'reminder' $rSent
    }
}

# --- read snapshot + robust feed freshness ---
# wild_console rewrites the CSV every few seconds; a read that races the rewrite can
# see FILETIME zero (1601-01-01) or a half-written file. Freshness is therefore the
# NEWER of (a) fs LastWriteTime, ignored unless sane (>= 2020), and (b) the newest
# last_seen_local inside the content. Only page when a sane timestamp is truly old.
$feedProblem = $null
$rows = $null
# existence check with retries: the console rewrites via delete+recreate, so a single
# Test-Path can land in the sub-second gap where the file does not exist (seen 08-18 21:00)
$csvPresent = $false
for ($try = 1; $try -le 5; $try++) {
    if (Test-Path -LiteralPath $CsvPath) { $csvPresent = $true; break }
    if ($try -lt 5) { Start-Sleep -Seconds 2 }
}
if (-not $csvPresent) {
    $feedProblem = "discovered_devices.csv NOT FOUND at $CsvPath (absent through 5 checks over 10 s)"
} else {
    for ($try = 1; $try -le 3; $try++) {
        try { $rows = @(Import-Csv -LiteralPath $CsvPath); if ($rows.Count -gt 0) { break } } catch { }
        if ($try -lt 3) { Start-Sleep -Seconds 2 }
    }
    $fresh = $null
    try {
        $t = (Get-Item -LiteralPath $CsvPath).LastWriteTime
        if ($t.Year -ge 2020) { $fresh = $t }
    } catch { }
    if ($rows) {
        foreach ($r in $rows) {
            try {
                $seen = [datetimeoffset]::Parse($r.last_seen_local, [Globalization.CultureInfo]::InvariantCulture).LocalDateTime
                if ($null -eq $fresh -or $seen -gt $fresh) { $fresh = $seen }
            } catch { }
        }
    }
    if ($null -eq $fresh) {
        # neither metadata nor content yielded a sane timestamp: rewrite collision -
        # skip this run silently, the next one (5 min) will decide
        Say 'No sane feed timestamp this run (rewrite collision) - skipping.' Yellow
        Save-State; Log-Line 'feed timestamp unreadable (transient)' 'skip' $false
        exit 0
    }
    $feedAgeMin = [math]::Round(($now - $fresh).TotalMinutes, 1)
    if ($feedAgeMin -gt $FeedStaleMinutes) { $feedProblem = "discovered_devices.csv not updated for $feedAgeMin min (wild_console closed or BLE scan stopped?)" }
}
if ($feedProblem) {
    Say "FEED: $feedProblem" Red
    $due = $true
    if ($state.feedDown -and $state.feedLastAlert) { $due = ((Get-Date) - [datetime]$state.feedLastAlert).TotalHours -ge $RealertHours }
    $sent = $false
    if (-not $DryRun -and $due) {
        if ($Slack.Token -and $Slack.Channels.Count) {
            $sent = Send-SlackText $Slack.Token $Slack.Channels (":warning: *NEUROLOGGER FEED STALE* - {0}. Logger status is UNKNOWN until wild_console is running its BLE scan on the main PC." -f $feedProblem)
        }
        $state.feedLastAlert = (Get-Date).ToString('o')
    }
    $state.feedDown = $true
    Save-State; Log-Line "FEED-STALE: $feedProblem" $(if ($due) { 'feed-alert' } else { 'feed-hold' }) $sent
    exit 2
} elseif ($state.feedDown) {
    if (-not $DryRun -and $Slack.Recovery -and $Slack.Token -and $Slack.Channels.Count) {
        [void](Send-SlackText $Slack.Token $Slack.Channels (":white_check_mark: Neurologger feed is updating again ({0})." -f (Get-Date).ToString('HH:mm')))
    }
    $state.feedDown = $false; $state.feedLastAlert = $null
}

if ($null -eq $rows -or $rows.Count -eq 0) {
    # feed is fresh but the content read raced the rewrite (empty/half-written) -
    # skip instead of declaring all loggers missing on a glitch
    Say 'CSV content unreadable/empty this run (rewrite collision) - skipping.' Yellow
    Save-State; Log-Line 'CSV read collision (transient)' 'skip' $false
    exit 0
}

# --- last-known sightings from our own telemetry history (console-restart grace) ---
$lastKnown = @{}
if (Test-Path -LiteralPath $HistoryPath) {
    try {
        foreach ($line in (Get-Content -LiteralPath $HistoryPath -Tail 600)) {
            $p = $line -split ','
            if ($p.Count -ge 2 -and $p[0] -match '^\d{4}-') {
                try { $lastKnown[$p[1]] = [datetime]$p[0] } catch { }
            }
        }
    } catch { }
}

# --- evaluate the fleet ---
$fs = Get-FleetStatus $rows $Roster $now $StaleMinutes $BatteryWarnVolts $StorageWarnPercent $BatteryCriticalVolts $lastKnown
$nMissing = @($fs.Missing).Count
$status = "{0}/{1} loggers missing (>{2} min). [{3}]" -f $nMissing, $Roster.Keys.Count, $StaleMinutes, ($fs.Detail -join ' ')
Say $status $(if ($nMissing -gt 0) { 'Red' } else { 'Green' })

$wasMissing = [bool]$state.missing
$lastAlert = $null; if ($state.lastAlert) { $lastAlert = [datetime]$state.lastAlert }

function Build-Alert($names, [int]$total, [int]$staleMin) {
    (":rotating_light: *NEUROLOGGER MISSING* - {0}/{1} loggers not seen over BLE for >{2} min: {3}. " -f @($names).Count, $total, $staleMin, ($names -join '; ')) + `
    "Phone check: take the rat-05 phone near the paddock -> WILD Control Panel -> Scan (do NOT connect!). Seen on the phone = PC-side signal only; not seen = start troubleshooting."
}

$sent = $false; $action = 'none'
if (-not $DryRun) {
    if ($nMissing -gt 0 -and -not $wasMissing) {
        if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Alert $fs.Missing $Roster.Keys.Count $StaleMinutes) }
        else { Say "(no Slack creds; would alert: $(Build-Alert $fs.Missing $Roster.Keys.Count $StaleMinutes))" DarkYellow }
        $state.missing = $true; $state.lastAlert = (Get-Date).ToString('o'); $action = "alert($nMissing)"
    }
    elseif ($nMissing -gt 0 -and $wasMissing) {
        $due = (-not $lastAlert) -or (((Get-Date) - $lastAlert).TotalHours -ge $RealertHours)
        if ($due) {
            if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Alert $fs.Missing $Roster.Keys.Count $StaleMinutes) }
            $state.lastAlert = (Get-Date).ToString('o'); $action = "re-alert($nMissing)"
        } else { $action = "hold($nMissing)" }
    }
    elseif ($nMissing -eq 0 -and $wasMissing) {
        if ($Slack.Recovery -and $Slack.Token -and $Slack.Channels.Count) {
            [void](Send-SlackText $Slack.Token $Slack.Channels (":white_check_mark: All {0} Neurologgers seen over BLE again ({1})." -f $Roster.Keys.Count, (Get-Date).ToString('HH:mm')))
        }
        $state.missing = $false; $state.lastAlert = $null; $action = 'recovered'
    }

    # --- battery / storage: one page per device per excursion, silent auto-clear ---
    $battNow = @(); foreach ($b in $fs.BattLow) { $battNow += ($b -split ' ')[0] }
    $newBatt = @($fs.BattLow | Where-Object { $state.battWarned -notcontains (($_ -split ' ')[0]) })
    if ($newBatt.Count -gt 0 -and $Slack.Token -and $Slack.Channels.Count) {
        [void](Send-SlackText $Slack.Token $Slack.Channels (":battery: Neurologger low battery (warn < {0:F2} V): {1}. At ~4 mV/h that is roughly a day to the discharge knee - plan the swap." -f $BatteryWarnVolts, ($newBatt -join '; ')))
    }
    $state.battWarned = $battNow

    # critical tier: below the LiPo knee the cell drops fast - page urgently, once per excursion
    $critNow = @(); foreach ($b in $fs.BattCritical) { $critNow += ($b -split ' ')[0] }
    $newCrit = @($fs.BattCritical | Where-Object { $state.battCritWarned -notcontains (($_ -split ' ')[0]) })
    if ($newCrit.Count -gt 0 -and $Slack.Token -and $Slack.Channels.Count) {
        [void](Send-SlackText $Slack.Token $Slack.Channels (":rotating_light: *NEUROLOGGER BATTERY CRITICAL* (< {0:F2} V - LiPo knee, hours left, voltage will now fall fast): {1}. Swap/charge ASAP." -f $BatteryCriticalVolts, ($newCrit -join '; ')))
    }
    $state.battCritWarned = $critNow

    $storNow = @(); foreach ($s2 in $fs.StorHigh) { $storNow += ($s2 -split ' ')[0] }
    $newStor = @($fs.StorHigh | Where-Object { $state.storWarned -notcontains (($_ -split ' ')[0]) })
    if ($newStor.Count -gt 0 -and $Slack.Token -and $Slack.Channels.Count) {
        [void](Send-SlackText $Slack.Token $Slack.Channels (":floppy_disk: Neurologger storage high (warn >= {0}%): {1}." -f $StorageWarnPercent, ($newStor -join '; ')))
    }
    $state.storWarned = $storNow

    # --- telemetry history: one row per rostered logger per run. Trend data only -
    # nothing alerts on it yet (storage-growth checks can be added once history exists).
    if (-not (Test-Path -LiteralPath $HistoryPath)) {
        Set-Content -LiteralPath $HistoryPath -Encoding UTF8 -Value 'ts_local,device,label,age_min,battery_v,storage_pct,rec_elapsed_s'
    }
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $hist = foreach ($dev in $Roster.Keys) {
        $cidWant = Get-CanonicalDeviceId $dev
        $row = $rows | Where-Object { (Get-CanonicalDeviceId $_.device_name) -eq $cidWant } | Select-Object -First 1
        if ($row) {
            $age = ''
            try { $age = [math]::Round(((Get-Date) - [datetimeoffset]::Parse($row.last_seen_local, [Globalization.CultureInfo]::InvariantCulture).LocalDateTime).TotalMinutes, 1) } catch { }
            '{0},{1},{2},{3},{4},{5},{6}' -f $ts, $dev, ($Roster[$dev] -replace ',', ' '), $age, $row.battery_voltage_volts, $row.used_storage_percent, $row.recording_elapsed_seconds
        }
    }
    if ($hist) { Add-Content -LiteralPath $HistoryPath -Encoding UTF8 -Value $hist }

    Save-State
    Log-Line $status $action $sent
}

Say ("action={0}{1}" -f $action, $(if ($DryRun) { '  (DRY RUN - nothing sent/written)' } else { '' })) Gray
$warnAny = ($nMissing -gt 0) -or (@($fs.BattLow).Count -gt 0) -or (@($fs.StorHigh).Count -gt 0)
exit $(if ($warnAny) { 1 } else { 0 })
