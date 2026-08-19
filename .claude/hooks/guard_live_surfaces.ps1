# PreToolUse guard for the live recording rig.
# Contract: stdin = tool-call JSON; exit 0 = allow, exit 2 = block (stderr is shown
# to Claude as the reason). Wired in .claude\settings.json.
#
# Installed 2026-08-19 by operator order after TWO agent-caused data losses that day:
#   - a "verify" content-read against E: starved recorder writes -> 01:40-03:21 video outage
#   - a 2-min unindexed query on the live WISER DB held the SQLite SHARED lock past the
#     wiserex writer's 5 s busy_timeout -> 150 s of tracking fixes dropped (18:26-18:29)
# Live producer surfaces are NOT analysis surfaces. Reads there are not harmless.

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $call = $raw | ConvertFrom-Json } catch { exit 0 }
$tool = [string]$call.tool_name
try { $in = $call.tool_input | ConvertTo-Json -Depth 12 -Compress } catch { $in = [string]$call.tool_input }
if (-not $in) { exit 0 }

function Block([string]$msg) {
    [Console]::Error.WriteLine("BLOCKED by guard_live_surfaces.ps1: $msg")
    exit 2
}

# Path patterns as they appear inside JSON-serialized tool input (doubled backslashes ok).
$wiserLive = '(?i)Wiser[\\/]+data'
$eRoots    = '(?i)E:[\\/]+(Reolink_record|thermal_record|ultramic_record|nvr_rescue)'

# ---- 1) LIVE WISER DB (D:\Wiser\data): nothing may OPEN a file there, ever -------
# SQLite rollback-journal readers block the writer's commits; wiserex drops fixes
# after 5 s. Analysis reads go to the E:\Wiser_backup snapshots instead.
if ($in -match $wiserLive) {
    if ($tool -eq 'Read' -or $tool -eq 'Grep') {
        Block 'D:\Wiser\data is the LIVE WISER DB - readers starve the wiserex writer (150 s of fixes lost 2026-08-19). Use the E:\Wiser_backup snapshot, or hand the command to the user.'
    }
    if ($tool -eq 'Bash' -or $tool -eq 'PowerShell') {
        $wiserOpeners = '(?i)(python|sqlite|Get-Content|Select-String|Import-Csv|IO\.File|FileStream|Copy-Item|robocopy|xcopy|Compress|Get-FileHash|certutil|\btype\b|\bcat\b|\bcp\b|\bdd\b|\bhead\b|\btail\b)'
        if ($in -match $wiserOpeners) {
            Block 'this would OPEN a file under D:\Wiser\data (LIVE WISER DB - readers starve the writer; 150 s of fixes lost 2026-08-19). Query the E:\Wiser_backup snapshot instead. Pure directory listings are the only thing allowed here.'
        }
    }
}

# ---- 2) LIVE E: RECORDING ROOTS: no content reads --------------------------------
# Sustained reads starve recorder writes (caused the 01:40-03:21 outage 2026-08-19).
# Allowed: directory/metadata listings, log tails, and the sanctioned Get-HandleLen
# open-file length idiom. Everything that streams file CONTENT is blocked; if the
# user wants it, the user runs it.
if ($in -match $eRoots) {
    if ($tool -eq 'Bash' -or $tool -eq 'PowerShell') {
        $eReaders = '(?i)(ffprobe|ffmpeg|Get-FileHash|certutil|robocopy|xcopy|Copy-Item|Compress|python|\bdd\b|\bcp\b|\bmd5|sha(1|256)sum)'
        if ($in -match $eReaders) {
            Block 'content read against a live E: recording root - sustained reads starve recorder writes (01:40-03:21 outage 2026-08-19). Metadata listings and Get-HandleLen are fine; content reads (hash/ffprobe/copy) are user-run only.'
        }
    }
    if ($tool -eq 'Read' -and $in -match '(?i)\.(mp4|wav)') {
        Block 'reading media content under a live E: recording root. If this is needed, the user runs it.'
    }
}

exit 0
