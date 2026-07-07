<#
.SYNOPSIS
    Slack DISK-SPACE warning for the recording drive. Auto-delete on the recorders
    is intentionally OFF, so this is the safety net: it alerts (Slack channel + DM)
    when the drive crosses 50% / 80% / 90% full, with weeks of lead time, so footage
    can be backed up and space freed before recording is ever at risk.

    Read-only: it only reads free/used space and sends Slack messages. It never
    deletes or touches recordings.

.PARAMETER Drive       Drive letter to watch (default E).
.PARAMETER Thresholds  Percent-full levels that trigger an alert (default 50,80,90).
.PARAMETER ConfigPath  Slack creds (reused from the overexposure QC config).
.PARAMETER DryRun      Print status only; send nothing, update no state.
.PARAMETER TestSlack   Send a test message to the configured destinations, then exit.

.NOTES
    De-duped: alerts when it crosses UP into a higher band, then at most once per
    RealertHours while it stays there; resets (with an optional "recovered" note)
    if space is freed back below all thresholds. Exit: 0 ok, 1 at/above a threshold.
#>

[CmdletBinding()]
param(
    [string]$Drive = 'E',
    [int[]]$Thresholds = @(50, 80, 90),
    [string]$ConfigPath = 'E:\recording_qc\overexposure.config.psd1',
    [string]$StatePath = 'E:\recording_qc\disk_space_state.json',
    [string]$LogPath = 'E:\recording_qc\disk_space_log.txt',
    [int]$RealertHours = 24,
    [switch]$DryRun,
    [switch]$TestSlack
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

# --- drive measurement ---
$dr = Get-PSDrive -Name $Drive -ErrorAction Stop
$free = [double]$dr.Free; $used = [double]$dr.Used; $total = $free + $used
if ($total -le 0) { Say "Drive $Drive : cannot read size." Red; exit 2 }
$pct = [math]::Round($used / $total * 100, 1)
$freeTB = [math]::Round($free / 1TB, 2); $usedTB = [math]::Round($used / 1TB, 2); $totTB = [math]::Round($total / 1TB, 2)
$status = "$Drive`: $pct% full  ($usedTB / $totTB TB used, $freeTB TB free)"
Say $status Cyan

if ($TestSlack) {
    if (-not $Slack.Token -or $Slack.Channels.Count -eq 0) { Say "TestSlack: set SlackBotToken/SlackChannels in $ConfigPath first." Red; exit 2 }
    $ok = Send-SlackText $Slack.Token $Slack.Channels (":satellite: Disk-space check test - $status ({0})." -f (Get-Date).ToString('yyyy-MM-dd HH:mm'))
    Say ("TestSlack: {0}" -f $(if ($ok) { 'delivered' } else { 'FAILED' })) $(if ($ok) { 'Green' } else { 'Red' })
    exit $(if ($ok) { 0 } else { 2 })
}

# --- which band are we in? (highest crossed threshold; 0 = below all) ---
$sorted = @($Thresholds | Sort-Object)
$level = 0
foreach ($t in $sorted) { if ($pct -ge $t) { $level = $t } }

# --- state ---
$state = @{ level = 0; lastAlert = $null }
if (Test-Path -LiteralPath $StatePath) {
    try { $s = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json; $state.level = [int]$s.level; $state.lastAlert = $s.lastAlert } catch {}
}
$prevLevel = [int]$state.level
$lastAlert = if ($state.lastAlert) { [datetime]$state.lastAlert } else { $null }

function Build-Msg([int]$lvl) {
    $head = if ($lvl -ge 90) { ":rotating_light: *CRITICAL* - {0} drive {1}% full" -f $Drive, $pct }
            else { ":warning: {0} drive {1}% full" -f $Drive, $pct }
    $tail = if ($lvl -ge 90) { "recording will STOP when the disk fills - free space NOW." }
            elseif ($lvl -ge 80) { "auto-delete is OFF - back up and free space soon." }
            else { "auto-delete is OFF - plan a backup/cleanup." }
    "{0} ({1} / {2} TB used, {3} TB free). {4}" -f $head, $usedTB, $totTB, $freeTB, $tail
}

$sent = $false; $action = 'none'
if (-not $DryRun) {
    if ($level -gt $prevLevel) {
        # crossed up into a new, higher band -> always alert
        if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Msg $level) }
        else { Say "(no Slack creds; would alert: $(Build-Msg $level))" DarkYellow }
        $state.level = $level; $state.lastAlert = (Get-Date).ToString('o'); $action = "alert-up($level)"
    }
    elseif ($level -gt 0 -and $level -eq $prevLevel) {
        # still in a band -> re-alert at most every RealertHours
        $due = (-not $lastAlert) -or (((Get-Date) - $lastAlert).TotalHours -ge $RealertHours)
        if ($due) {
            if ($Slack.Token -and $Slack.Channels.Count) { $sent = Send-SlackText $Slack.Token $Slack.Channels (Build-Msg $level) }
            else { Say "(no Slack creds; would re-alert: $(Build-Msg $level))" DarkYellow }
            $state.lastAlert = (Get-Date).ToString('o'); $action = "re-alert($level)"
        } else { $action = "hold($level)" }
    }
    elseif ($level -lt $prevLevel) {
        # space was freed -> step down (recovery note only when back below all thresholds)
        if ($level -eq 0 -and $Slack.Recovery -and $Slack.Token -and $Slack.Channels.Count) {
            [void](Send-SlackText $Slack.Token $Slack.Channels (":white_check_mark: $Drive drive back to $pct% full ($freeTB TB free)."))
        }
        $state.level = $level; if ($level -eq 0) { $state.lastAlert = $null }; $action = "down($level)"
    }
    # persist state + log
    ($state | ConvertTo-Json) | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ("{0}  {1}  level={2} prev={3} action={4} sent={5}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $status, $level, $prevLevel, $action, $sent)
}

Say ("level={0}  action={1}{2}" -f $level, $action, $(if ($DryRun) { '  (DRY RUN - nothing sent/written)' } else { '' })) Gray
exit $(if ($level -gt 0) { 1 } else { 0 })
