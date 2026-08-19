# PreToolUse guard for the live recording rig.
# Contract: stdin = tool-call JSON; exit 0 = allow, exit 2 = block (stderr is shown
# to Claude as the reason). Wired in .claude\settings.json (matcher Bash|PowerShell|Read|Grep).
#
# 2026-08-19 operator orders (v3, relaxed the same evening from blanket copy-first):
#   "just don't read a file that is actively writing - for example video, mic, or some
#    streaming - because there has already been a case where the agent read a live file
#    and data was lost. The only exception: I specifically ask for a live stream check."
#
# What this blocks:
#   1) D:\Wiser\data  - the LIVE WISER DB, actively written at all times. NOTHING opens
#      files there, ever, no override (a reader's SQLite SHARED lock past the writer's
#      5 s busy_timeout DROPPED 150 s of fixes on 2026-08-19). Use E:\Wiser_backup snapshots.
#   2) OPEN recording segments under E:\{Reolink_record,thermal_record,ultramic_record,
#      nvr_rescue,WILD}. The filename contract identifies them: a .mp4/.wav WITHOUT "_to_"
#      in its name is still being written and must never be touched (read, copy, probe,
#      or open-handle). Closed segments (with "_to_"), logs, configs: direct reads are fine.
#      Recursive content-grep of a whole root directory is also blocked - it would sweep
#      the open segment along with the rest.
#
# Override (ONLY when the user just explicitly asked to check a live stream):
#   New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force
#   Expires 15 minutes after creation. Never unlocks D:\Wiser\data.

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $call = $raw | ConvertFrom-Json } catch { exit 0 }
$tool = [string]$call.tool_name

function Block([string]$msg) {
    [Console]::Error.WriteLine("BLOCKED by guard_live_surfaces.ps1: $msg")
    exit 2
}

# Override flag: armed by the agent only on an explicit user request to check a live
# stream; honored for 15 minutes from LastWriteTime, then dead until re-armed.
$flagPath = 'C:\Users\Cornell\.claude\allow-live-read'
$override = $false
if (Test-Path $flagPath) {
    if (((Get-Date) - (Get-Item $flagPath).LastWriteTime).TotalMinutes -lt 15) { $override = $true }
}

$wiserLive = '(?i)Wiser[\\/]+data'
# Windows (E:\...) and Git-Bash (/e/...) spellings of the recording roots.
$eRoots    = '(?i)(E:[\\/]+|/e/)(Reolink_record|thermal_record|ultramic_record|nvr_rescue|WILD\b)'

$openMsg = "that segment has NO '_to_' in its name = the recorder still has it open (filename contract). Touching a live segment has lost data before. Use the previous closed (_to_) segment, or wait for rollover. Sole exception - the user JUST explicitly asked to check a live stream: arm the 15-min override with  New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force  and retry."

# ---- File tools (Read / Grep): judge the actual target paths, not the whole input,
# so a Grep whose PATTERN merely mentions these strings does not false-trip.
if ($tool -eq 'Read' -or $tool -eq 'Grep') {
    foreach ($k in @('file_path', 'path')) {
        $p = [string]$call.tool_input.$k
        if (-not $p) { continue }
        if ($p -match $wiserLive) {
            Block 'D:\Wiser\data is the LIVE WISER DB - readers starve the wiserex writer (150 s of fixes lost 2026-08-19). Use the E:\Wiser_backup snapshots instead. No override exists for this path.'
        }
        if ($p -match $eRoots) {
            if ($override) { continue }
            $leaf = Split-Path $p -Leaf
            if ($leaf -match '(?i)\.(mp4|wav)$' -and $leaf -notmatch '_to_') {
                Block "open segment: $p - $openMsg"
            }
            if ($tool -eq 'Grep' -and $leaf -notmatch '(?i)\.[a-z0-9]{1,5}$') {
                Block "recursive content search under a live recording root ($p) would sweep the currently-open segment too. Grep a specific closed (_to_) file, or copy files out first."
            }
        }
    }
    exit 0
}

if ($tool -ne 'Bash' -and $tool -ne 'PowerShell') { exit 0 }
$cmd = [string]$call.tool_input.command
if (-not $cmd) { exit 0 }

# ---- LIVE WISER DB: nothing may OPEN a file there - even a plain file-copy of a hot
# SQLite is torn AND competes with the writer. The override does NOT apply here.
if ($cmd -match $wiserLive) {
    $wiserOpeners = '(?i)(python|sqlite|Get-Content|Select-String|Import-Csv|IO\.File|FileStream|Copy-Item|robocopy|xcopy|Compress|Get-FileHash|certutil|\btype\b|\bcat\b|\bcp\b|\bdd\b|\bhead\b|\btail\b)'
    if ($cmd -match $wiserOpeners) {
        Block 'this would OPEN a file under D:\Wiser\data (LIVE WISER DB - readers starve the writer; 150 s of fixes lost 2026-08-19). Query the E:\Wiser_backup snapshot instead. Pure directory listings are the only thing allowed here.'
    }
}

# ---- OPEN SEGMENTS under the E: recording roots -------------------------------------
# Only fires when the command BOTH (a) contains something that opens/streams file content
# and (b) names a media file token that is (or may be) an open segment: a .mp4/.wav
# whose filename lacks "_to_" - including wildcards like *.wav, which would sweep the
# open file in. Listings (Get-ChildItem etc.), closed (_to_) segments, logs, configs,
# and whole-directory copy tools (which skip open files by design) pass untouched.
if ($cmd -match $eRoots -and -not $override) {
    $openers = '(?i)(ffprobe|ffmpeg|Get-Content|Select-String|Import-Csv|Get-FileHash|certutil|\bmd5|sha(1|256)sum|python|IO\.File|FileStream|StreamReader|Copy-Item|robocopy|xcopy|Compress|\btype\b|\bcat\b|\bcp\b|\bdd\b|\bhead\b|\btail\b|\bstrings\b|findstr)'
    if ($cmd -match $openers) {
        $tokens = [regex]::Matches($cmd, '(?i)[^\s"''<>|;]+\.(mp4|wav)\b') | ForEach-Object { $_.Value }
        foreach ($t in $tokens) {
            if ($t -notmatch '_to_') {
                Block "command touches a possibly-open segment ($t) - $openMsg"
            }
        }
    }
}

exit 0
