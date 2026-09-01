<#
.SYNOPSIS
    Near-real-time WISER acquisition watchdog (Slack pager). Metadata-only by design.

    Pages when: (1) the wiserex process is not running; (2) the watched live DB's
    LastWriteTime goes stale (acquisition hung / not committing); (3) one-shot warn
    when the newest-written .sqlite in the data dir is NOT the watched DB (wiserex
    rolled to a new file or a new cohort DB - the backup/plot tasks then point at a
    stale file and must be re-registered).

    SAFETY: this script NEVER opens any file under the live WISER data dir - no
    query, no read, no copy (readers starve the wiserex writer; 150 s of fixes were
    dropped 2026-08-19). It uses Get-Process and directory METADATA only, which is
    the sole allowed touch per CLAUDE.md.

.PARAMETER DbPath        The live cohort DB to watch (LastWriteTime freshness).
.PARAMETER StaleMinutes  Page when the DB file hasn't been written for this long
                         (default 30 - commits normally land every few minutes;
                         a quiet field during handling shouldn't false-page).
.PARAMETER ProcessName   Acquisition process name (default wiserex).
.PARAMETER ConfigPath    Slack creds (shared QC config).
.PARAMETER RealertHours  While a problem persists, re-page at most this often.
.PARAMETER DryRun / TestSlack / SelfTest   Same conventions as the other checks.

.NOTES
    Exit codes: 0 healthy, 1 warning (name mismatch only), 2 problem (process down
    or DB stale). Mute file: E:\recording_qc\wiser_alive_MUTED.txt (drop to
    silence, delete to resume).
#>
[CmdletBinding()]
param(
    [string]$DbPath = 'D:\Wiser\data\3rdcohort_Spike_2026_3.sqlite',
    # wiserex creates a NEW .sqlite on every session restart (three rolls observed
    # 2026-09-01 alone). -FollowNewest watches whichever .sqlite in the DbPath
    # directory was written most recently, so the watchdog never goes stale on a
    # roll (the fixed-path backup/plot tasks still need re-registering per roll -
    # the name-change info line in the log is the cue).
    [switch]$FollowNewest,
    [int]$StaleMinutes = 30,
    [string]$ProcessName = 'wiserex',
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$StatePath = 'E:\recording_qc\wiser_alive_state.json',
    [string]$LogPath = 'E:\recording_qc\wiser_alive_log.txt',
    [int]$RealertHours = 1,
    [switch]$DryRun,
    [switch]$TestSlack,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }

$MutePath = 'E:\recording_qc\wiser_alive_MUTED.txt'
if (Test-Path -LiteralPath $MutePath) { Say "MUTED via $MutePath - exiting." Yellow; exit 0 }

# --- pure evaluation (also used by -SelfTest) -------------------------------------
function Get-WiserStatus([bool]$procRunning, [bool]$dbExists, $dbAgeMin, [int]$staleMin, [string]$newestName, [string]$expectedName) {
    $problems = @(); $warns = @()
    if (-not $procRunning) { $problems += 'wiserex process NOT RUNNING - tracking is down' }
    if (-not $dbExists) {
        $problems += "watched DB does not exist: $expectedName"
    } elseif ($null -ne $dbAgeMin -and $dbAgeMin -gt $staleMin) {
        $problems += ("watched DB not written for {0:F0} min (> {1}) - acquisition hung or not committing" -f $dbAgeMin, $staleMin)
    }
    if ($newestName -and $expectedName -and ($newestName -ne (Split-Path $expectedName -Leaf))) {
        $warns += ("newest-written sqlite is '{0}', not the watched '{1}' - wiserex rolled files? Re-register backup/plot/watchdog at the new DB" -f $newestName, (Split-Path $expectedName -Leaf))
    }
    return [pscustomobject]@{ Problems = $problems; Warns = $warns }
}

if ($SelfTest) {
    $ok = $true
    $s1 = Get-WiserStatus $true  $true  5   30 'a.sqlite' 'D:\x\a.sqlite'   # healthy
    $s2 = Get-WiserStatus $false $true  5   30 'a.sqlite' 'D:\x\a.sqlite'   # proc down
    $s3 = Get-WiserStatus $true  $true  45  30 'a.sqlite' 'D:\x\a.sqlite'   # stale
    $s4 = Get-WiserStatus $true  $true  5   30 'b.sqlite' 'D:\x\a.sqlite'   # rolled file
    $s5 = Get-WiserStatus $true  $false $null 30 'a.sqlite' 'D:\x\missing.sqlite' # db gone
    if (@($s1.Problems).Count -ne 0 -or @($s1.Warns).Count -ne 0) { Say 'FAIL healthy'; $ok = $false }
    if (@($s2.Problems).Count -ne 1 -or $s2.Problems[0] -notmatch 'NOT RUNNING') { Say 'FAIL proc-down'; $ok = $false }
    if (@($s3.Problems).Count -ne 1 -or $s3.Problems[0] -notmatch 'not written') { Say 'FAIL stale'; $ok = $false }
    if (@($s4.Warns).Count -ne 1 -or $s4.Warns[0] -notmatch 'rolled') { Say 'FAIL mismatch'; $ok = $false }
    if (@($s5.Problems).Count -ne 1 -or $s5.Problems[0] -notmatch 'does not exist') { Say 'FAIL missing-db'; $ok = $false }
    Say ("SelfTest: {0}" -f $(if ($ok) { 'PASS (healthy, proc-down, stale, rolled-file, missing-db)' } else { 'FAIL' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# --- Slack plumbing (same conventions as the other checks) ------------------------
$Slack = @{ Token = $null; Channels = @(); Recovery = $true }
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $c = Import-PowerShellDataFile -LiteralPath $ConfigPath
        if ($c.SlackBotToken) { $Slack.Token = $c.SlackBotToken }
        if ($c.SlackChannels) { $Slack.Channels = $c.SlackChannels }
        if ($null -ne $c.SendRecovery) { $Slack.Recovery = $c.SendRecovery }
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
    $ok = Send-SlackText $Slack.Token $Slack.Channels (":satellite: WISER alive check test ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# --- gather facts (METADATA ONLY - never open files under the live data dir) ------
$procRunning = [bool](Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
if ($FollowNewest) {
    $newestNow = Get-ChildItem -LiteralPath (Split-Path $DbPath -Parent) -Filter '*.sqlite' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($newestNow) { $DbPath = $newestNow.FullName }
}
$dbItem = Get-Item -LiteralPath $DbPath -ErrorAction SilentlyContinue
$dbExists = [bool]$dbItem
$dbAgeMin = $null
if ($dbExists) { $dbAgeMin = ((Get-Date) - $dbItem.LastWriteTime).TotalMinutes }
$dataDir = Split-Path $DbPath -Parent
$newest = Get-ChildItem -LiteralPath $dataDir -Filter '*.sqlite' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime | Select-Object -Last 1
$newestName = if ($newest) { $newest.Name } else { $null }

$fs = Get-WiserStatus $procRunning $dbExists $dbAgeMin $StaleMinutes $newestName $DbPath
$statusLine = "proc={0} dbAge={1} newest={2} problems={3} warns={4}" -f $procRunning,
    $(if ($null -ne $dbAgeMin) { '{0:F1}m' -f $dbAgeMin } else { 'n/a' }), $newestName,
    (@($fs.Problems).Count), (@($fs.Warns).Count)
Say $statusLine $(if (@($fs.Problems).Count) { 'Red' } elseif (@($fs.Warns).Count) { 'Yellow' } else { 'Green' })
foreach ($p in $fs.Problems) { Say "  PROBLEM: $p" Red }
foreach ($w in $fs.Warns) { Say "  warn: $w" Yellow }

# --- state / paging ---------------------------------------------------------------
$state = @{ down = $false; lastAlert = $null; mismatchWarned = $false }
if (Test-Path -LiteralPath $StatePath) {
    try {
        $s = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        $state.down = [bool]$s.down; $state.lastAlert = $s.lastAlert
        $state.mismatchWarned = [bool]$s.mismatchWarned
    } catch {}
}

if (-not $DryRun) {
    $sent = $false
    if (@($fs.Problems).Count -gt 0) {
        $due = $true
        if ($state.down -and $state.lastAlert) { $due = ((Get-Date) - [datetime]$state.lastAlert).TotalHours -ge $RealertHours }
        if ($due -and $Slack.Token -and $Slack.Channels.Count) {
            $sent = Send-SlackText $Slack.Token $Slack.Channels (":rotating_light: *WISER TRACKING DOWN* - {0}" -f ($fs.Problems -join '; '))
            $state.lastAlert = (Get-Date).ToString('o')
        }
        $state.down = $true
    } elseif ($state.down) {
        if ($Slack.Recovery -and $Slack.Token -and $Slack.Channels.Count) {
            [void](Send-SlackText $Slack.Token $Slack.Channels (":white_check_mark: WISER tracking healthy again ({0})." -f (Get-Date).ToString('HH:mm')))
        }
        $state.down = $false; $state.lastAlert = $null
    }
    if (@($fs.Warns).Count -gt 0 -and -not $state.mismatchWarned) {
        if ($Slack.Token -and $Slack.Channels.Count) {
            [void](Send-SlackText $Slack.Token $Slack.Channels (":warning: WISER file-roll warning: {0}" -f ($fs.Warns -join '; ')))
        }
        $state.mismatchWarned = $true
    } elseif (@($fs.Warns).Count -eq 0) {
        $state.mismatchWarned = $false
    }
    ($state | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ("{0}  {1}  sent={2}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $statusLine, $sent)
}

if (@($fs.Problems).Count) { exit 2 }
if (@($fs.Warns).Count) { exit 1 }
exit 0
