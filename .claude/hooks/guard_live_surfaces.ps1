# PreToolUse guard for the live recording rig.
# Contract: stdin = tool-call JSON; exit 0 = allow, exit 2 = block (stderr is shown
# to Claude as the reason). Wired in .claude\settings.json (matcher Bash|PowerShell|Read|Grep).
#
# 2026-08-19 operator orders, after two agent-caused data losses the same day:
#   - a "verify" content-read against E: starved recorder writes -> 01:40-03:21 video outage
#   - a 2-min unindexed query on the live WISER DB held the SQLite SHARED lock past the
#     wiserex writer's 5 s busy_timeout -> 150 s of tracking fixes dropped (18:26-18:29)
#   - (evening) "every original file: do not directly read, always make a copy; the ONLY
#     exception is the user specifically asks to read the original to check a stream"
#
# Policy this enforces:
#   D:\Wiser\data  -> NOTHING opens files there, ever (no override). Use the
#                     E:\Wiser_backup snapshots for any analysis.
#   E:\{Reolink_record,thermal_record,ultramic_record,nvr_rescue,WILD}
#                  -> no direct content reads. Copy the ONE file you need to the session
#                     scratchpad (single-file Copy-Item / cp is allowed) and read the COPY.
#                     Directory/metadata listings stay allowed. *.config.psd1 is exempt
#                     (tiny, never producer-written; Edit requires a direct Read).
#   Override (live stream check, ONLY when the user just explicitly asked for one):
#     New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force
#     Expires 15 minutes after creation. Never unlocks D:\Wiser\data.

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
# Both Windows (E:\...) and Git-Bash (/e/...) spellings.
$eRoots    = '(?i)(E:[\\/]+|/e/)(Reolink_record|thermal_record|ultramic_record|nvr_rescue|WILD\b)'

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
            if ($p -match '(?i)\.config\.psd1$') { continue }
            if ($override) { continue }
            Block "direct read of a live recording surface: $p. Copy-first rule (operator order 2026-08-19): Copy-Item that ONE file to the session scratchpad and read the COPY. Sole exception - the user JUST explicitly asked to check a live stream: arm the 15-min override with  New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force  and retry."
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

# ---- LIVE E: RECORDING ROOTS ---------------------------------------------------------
# Allowed without override: directory/metadata listings (Get-ChildItem sorted on Name),
# and a single-file Copy-Item / cp out to a non-E: destination - that IS the sanctioned
# copy-first step. Blocked: anything streaming content in place (ffprobe/hash/python/
# Get-Content/cat/...), open-handle probes (IO.File - Get-HandleLen is a stream check,
# so it belongs behind the override), and bulk copiers (robocopy/xcopy/Copy-Item -Recurse).
if ($cmd -match $eRoots -and -not $override) {
    $eReaders = '(?i)(ffprobe|ffmpeg|Get-FileHash|certutil|\bmd5|sha(1|256)sum|python|sqlite|Get-Content|Select-String|Import-Csv|findstr|IO\.File|FileStream|StreamReader|Compress|robocopy|xcopy|\bdd\b|\btype\b|\bcat\b|\bhead\b|\btail\b|\bstrings\b)'
    if ($cmd -match $eReaders -or $cmd -match '(?i)Copy-Item[^|;]*-Recurse') {
        Block "content read / bulk copy against a live E: recording root - sustained reads starved the recorders 2026-08-19 (01:40-03:21 outage). Copy-first rule: single-file Copy-Item the ONE file you need to the scratchpad in its own command, then analyze the COPY there. Metadata listings are fine. Sole exception - the user JUST explicitly asked to check a live stream: arm the 15-min override with  New-Item -ItemType File 'C:\Users\Cornell\.claude\allow-live-read' -Force  and retry."
    }
}

exit 0
