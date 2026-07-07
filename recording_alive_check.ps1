<#
.SYNOPSIS
    Near-real-time "RECORDING STOPPED" Slack alert. Watches that each recording
    group's newest MP4 is still GROWING; if a group goes stale (no new data for
    -StaleMinutes), it Slack-alerts the team channel + the user's DM. Catches the
    failure mode the daily continuity check misses: the recorder process is alive
    but writing nothing (e.g. the NVR became unreachable / changed IP, a stream
    stalled and could not self-heal).

    Read-only: it only reads file timestamps and sends Slack messages. It NEVER
    touches recordings or the recorder.

.PARAMETER StaleMinutes   A group is "stalled" if its newest file has not been
                          written for this many minutes (default 10 — safely above
                          the recorder's own 240 s self-heal and the Sunday NVR
                          reboot, so normal transient restarts do not alert).
.PARAMETER ReolinkRoot    Root holding CH** folders (default E:\Reolink_record).
.PARAMETER ThermalRoot    Root holding thermal/visual folders (default E:\thermal_record).
.PARAMETER ConfigPath     Slack creds (reused from the overexposure QC config).
.PARAMETER RealertHours   While groups stay stalled, re-alert at most this often (default 1).
.PARAMETER DryRun         Print status only; send nothing, update no state.
.PARAMETER TestSlack      Send a test message to the configured destinations, then exit.
.PARAMETER SelfTest       Offline logic check on synthetic group dirs (no Slack, no disk state).

.NOTES
    One aggregated alert lists ALL stalled groups (not one msg per channel). De-duped:
    alert on healthy->stalled, re-alert every RealertHours while stalled, recovery note
    when all groups are healthy again. Exit: 0 all healthy, 1 one or more stalled.
#>

[CmdletBinding()]
param(
    [int]$StaleMinutes = 6,   # tightened 2026-07-03 to page on flapping outages (still > the recorder's 240s self-heal)
    [string]$ReolinkRoot = 'E:\Reolink_record',
    [string]$ThermalRoot = 'E:\thermal_record',
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$StatePath = 'E:\recording_qc\recording_alive_state.json',
    [string]$LogPath = 'E:\recording_qc\recording_alive_log.txt',
    [int]$RealertHours = 1,
    [switch]$DryRun,
    [switch]$TestSlack,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

# --- Slack config (token + destinations live in the QC config, kept out of git) ---
$Slack = @{ Token = $null; Channels = @(); Recovery = $true }
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $c = Import-PowerShellDataFile -LiteralPath $ConfigPath
        if ($c.SlackBotToken) { $Slack.Token = $c.SlackBotToken }
        if ($c.SlackChannels) { $Slack.Channels = $c.SlackChannels }
        if ($null -ne $c.SendRecovery) { $Slack.Recovery = $c.SendRecovery }
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

# --- discover the recording groups to watch (folder per channel/sensor) ---
function Get-Groups([string]$reolink, [string]$thermal) {
    $g = @()
    if (Test-Path -LiteralPath $reolink) {
        Get-ChildItem -LiteralPath $reolink -Directory -Filter 'CH*' -EA SilentlyContinue |
            ForEach-Object { $g += [pscustomobject]@{ Name = $_.Name; Path = $_.FullName } }
    }
    if (Test-Path -LiteralPath $thermal) {
        Get-ChildItem -LiteralPath $thermal -Directory -EA SilentlyContinue |
            Where-Object { $_.Name -match '^\d' } |
            ForEach-Object { $g += [pscustomobject]@{ Name = $_.Name; Path = $_.FullName } }
    }
    return $g
}

# --- evaluate one group: newest mp4 age in minutes (or $null if no files) ---
function Get-GroupAgeMin([string]$path, [datetime]$now) {
    $f = Get-ChildItem -LiteralPath $path -File -Filter '*.mp4' -EA SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $f) { return $null }
    return [math]::Round(($now - $f.LastWriteTime).TotalMinutes, 1)
}

# --- SELF TEST: synthetic fresh + stale groups, no Slack, no real disk state ---
if ($SelfTest) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("ralive_selftest_" + [guid]::NewGuid().ToString('N'))
    $r = Join-Path $tmp 'Reolink'; $t = Join-Path $tmp 'Thermal'
    New-Item -ItemType Directory -Force -Path (Join-Path $r 'CH01'), (Join-Path $r 'CH02'), (Join-Path $t '108_thermal') | Out-Null
    $now = Get-Date
    # CH01 fresh, CH02 stale (20 min old), 108_thermal empty
    $a = New-Item -ItemType File -Force -Path (Join-Path $r 'CH01\CH01_x.mp4'); $a.LastWriteTime = $now
    $b = New-Item -ItemType File -Force -Path (Join-Path $r 'CH02\CH02_x.mp4'); $b.LastWriteTime = $now.AddMinutes(-20)
    $groups = Get-Groups $r $t
    $stale = @(); foreach ($grp in $groups) {
        $age = Get-GroupAgeMin $grp.Path $now
        $isStale = ($null -eq $age) -or ($age -gt $StaleMinutes)
        if ($isStale) { $stale += $grp.Name }
    }
    Remove-Item -LiteralPath $tmp -Recurse -Force -EA SilentlyContinue
    $expected = @('CH02', '108_thermal')
    $ok = (@(Compare-Object ($stale | Sort-Object) ($expected | Sort-Object)).Count -eq 0)
    Say ("SelfTest groups found: {0}" -f ($groups.Name -join ', '))
    Say ("SelfTest stalled detected: {0}" -f ($stale -join ', '))
    Say ("SelfTest expected stalled: {0}" -f ($expected -join ', '))
    Say ("SelfTest: {0}" -f $(if ($ok) { 'PASS' } else { 'FAIL' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

if ($TestSlack) {
    if (-not $Slack.Token -or $Slack.Channels.Count -eq 0) { Say "TestSlack: set SlackBotToken/SlackChannels in $ConfigPath first." Red; exit 2 }
    $ok = Send-SlackText $Slack.Token $Slack.Channels (":satellite: Recording-alive check test - watchdog wired up ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# --- evaluate all groups ---
$now = Get-Date
$groups = Get-Groups $ReolinkRoot $ThermalRoot
if ($groups.Count -eq 0) { Say "No recording groups found under $ReolinkRoot / $ThermalRoot." Red; exit 2 }

$stalled = @(); $detail = @()
foreach ($grp in $groups) {
    $age = Get-GroupAgeMin $grp.Path $now
    if ($null -eq $age) { $stalled += $grp.Name; $detail += ("{0} (NO FILES)" -f $grp.Name) }
    elseif ($age -gt $StaleMinutes) { $stalled += $grp.Name; $detail += ("{0} ({1} min)" -f $grp.Name, $age) }
    else { $detail += ("{0} ok({1}m)" -f $grp.Name, $age) }
}
$nStale = $stalled.Count
$status = "{0}/{1} groups stalled (> {2} min). [{3}]" -f $nStale, $groups.Count, $StaleMinutes, ($detail -join ' ')
Say $status $(if ($nStale -gt 0) { 'Red' } else { 'Green' })

# --- state / de-dup ---
$state = @{ stalled = $false; lastAlert = $null }
if (Test-Path -LiteralPath $StatePath) {
    try { $s = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json; $state.stalled = [bool]$s.stalled; $state.lastAlert = $s.lastAlert } catch {}
}
$wasStalled = [bool]$state.stalled
$lastAlert = if ($state.lastAlert) { [datetime]$state.lastAlert } else { $null }

function Build-Alert([string[]]$names) {
    ":rotating_light: *RECORDING STOPPED* - no new data on {0} for >{1} min: {2}. The recorder process may be up but writing nothing (check the NVR is reachable / its IP, and `recorder.log`)." -f `
        $(if ($names.Count -eq 1) { '1 stream' } else { "$($names.Count) streams" }), $StaleMinutes, ($names -join ', ')
}

$sent = $false; $action = 'none'
if (-not $DryRun) {
    if ($nStale -gt 0 -and -not $wasStalled) {
        if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Alert $stalled) }
        else { Say "(no Slack creds; would alert: $(Build-Alert $stalled))" DarkYellow }
        $state.stalled = $true; $state.lastAlert = (Get-Date).ToString('o'); $action = "alert($nStale)"
    }
    elseif ($nStale -gt 0 -and $wasStalled) {
        $due = (-not $lastAlert) -or (((Get-Date) - $lastAlert).TotalHours -ge $RealertHours)
        if ($due) {
            if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Alert $stalled) }
            else { Say "(no Slack creds; would re-alert: $(Build-Alert $stalled))" DarkYellow }
            $state.lastAlert = (Get-Date).ToString('o'); $action = "re-alert($nStale)"
        } else { $action = "hold($nStale)" }
    }
    elseif ($nStale -eq 0 -and $wasStalled) {
        if ($Slack.Recovery -and $Slack.Token -and $Slack.Channels.Count) {
            [void](Send-SlackText $Slack.Token $Slack.Channels (":white_check_mark: Recording recovered - all {0} streams writing again ({1})." -f $groups.Count, (Get-Date).ToString('HH:mm')))
        }
        $state.stalled = $false; $state.lastAlert = $null; $action = 'recovered'
    }
    ($state | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ("{0}  {1}  action={2} sent={3}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $status, $action, $sent)
}

Say ("action={0}{1}" -f $action, $(if ($DryRun) { '  (DRY RUN - nothing sent/written)' } else { '' })) Gray
exit $(if ($nStale -gt 0) { 1 } else { 0 })
