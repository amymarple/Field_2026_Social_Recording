<#
.SYNOPSIS
    Continuous audio recorder supervisor for the Dodotronic UltraMic384K USB
    ultrasound microphone. Launches one WASAPI capture child per mic
    (ultramic_wasapi_capture.ps1) and writes hourly clock-aligned WAV segments
    per mic into its OWN isolated root, e.g.:

        E:\ultramic_record\MIC01\MIC01_2026-07-17_20-00-00_to_21-00-00.wav
        E:\ultramic_record\MIC01\MIC01_2026-07-17_21-00-00.wav   (still recording)

    This is the AUDIO counterpart to the camera recorders (rtsp_record.ps1,
    extra_cam_record.ps1, thermal_record.ps1). It is a SEPARATE instance: its own
    mutex, its own log, its own scheduled task, and its own root directory.

    *** COMPLETELY INDEPENDENT OF THE VIDEO RECORDERS. ***
    - The audio path does not use ffmpeg AT ALL (capture is WASAPI via an embedded
      C# class), so it shares zero components with the camera pipeline. It never
      touches ffmpeg processes, the camera tasks, or their footage.
    - Why not ffmpeg: measured on this PC 2026-07-17, ffmpeg's only Windows audio
      input (DirectShow) opens this mic at max 96 kHz, and WASAPI *shared* mode
      only gives the Windows default format (48 kHz here). WASAPI EXCLUSIVE mode
      opens the device at its true native 384000 Hz / 1 ch / 16-bit - that is
      what the capture child uses (see README_ultramic.md).
    - It writes to a dedicated root (E:\ultramic_record by default), kept OUT of
      E:\Reolink_record / E:\thermal_record so the video QC/copy/delete tooling
      never sees these audio files (mirrors the gui_record precedent).
    - Retention / disk-guard are OFF by default and, if enabled, scoped to ONLY
      this recorder's own mic folders.

.PARAMETER ConfigPath
    Path to ultramic.config.psd1 (kept OUT of git, on E:). See
    ultramic.config.example.psd1 in this repo for the template.

.PARAMETER ListDevices
    Read-only. Enumerate WASAPI capture endpoints with their native + shared
    formats, so you can put the right name in the config. Records nothing.

.PARAMETER SelfTest
    Offline sanity check: config parses, capture script present, output root
    writable, per-mic launch command lines, _to_ finalize-rename logic. Does NOT
    open the device. Exit 0 = pass, 2 = problems.

.PARAMETER DryRun
    Print the exact capture command that WOULD be launched for each mic, then
    exit. Opens/records nothing.

.PARAMETER TestClip
    Capture ONE short clip (the number of seconds you pass, e.g. -TestClip 5)
    from each mic into its mic folder and report the file, to prove the device
    captures before you install the 24/7 task. This DOES open the device.

.NOTES
    Meant to be launched by a SYSTEM scheduled task (install_ultramic_task_system.ps1),
    NOT from a Claude session. Windows PowerShell 5.1 compatible.
#>

param(
    [string]$ConfigPath = 'E:\ultramic_record\ultramic.config.psd1',
    [switch]$ListDevices,
    [switch]$SelfTest,
    [switch]$DryRun,
    [int]$TestClip = 0
)

$ErrorActionPreference = 'Continue'

$base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$CaptureScript = Join-Path $base 'ultramic_wasapi_capture.ps1'

# ---------------------------------------------------------------------------
# -ListDevices : read-only WASAPI endpoint enumeration (no config needed)
# ---------------------------------------------------------------------------
if ($ListDevices) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $CaptureScript -ListDevices
    Write-Host ""
    Write-Host "Put the EXACT full endpoint name (preferred; a unique substring also works" -ForegroundColor Yellow
    Write-Host "while only one mic matches it) into the Streams[].Device field of $ConfigPath" -ForegroundColor Yellow
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Write-Error "Config not found: $ConfigPath  (copy ultramic.config.example.psd1 to this path and fill it in)"
    exit 2
}
$cfg = Import-PowerShellDataFile -Path $ConfigPath

# effective per-run settings with defaults
$StoreFormat = if ($cfg.StoreFormat) { $cfg.StoreFormat } else { 'int16' }
$CaptureMode = if ($cfg.Mode)        { $cfg.Mode }        else { 'auto' }

# builds the argument list for one mic's capture child (also shown by -SelfTest/-DryRun)
function Get-CaptureArgs($s, [int]$clipSeconds = 0) {
    $dir = Join-Path $cfg.Root $s.Name
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $CaptureScript),
           '-Device', ('"{0}"' -f $s.Device),
           '-OutDir', ('"{0}"' -f $dir),
           '-Prefix', $s.Name,
           '-SegmentSeconds', $cfg.SegmentSeconds,
           '-StoreFormat', $StoreFormat,
           '-Mode', $CaptureMode)
    if ($clipSeconds -gt 0) { $a += @('-Seconds', $clipSeconds) }
    return $a
}

# ---------------------------------------------------------------------------
# -SelfTest / -DryRun : offline validation, no capture
# ---------------------------------------------------------------------------
if ($SelfTest -or $DryRun) {
    $ok = $true
    Write-Host ("=== UltraMic recorder {0} ===" -f ($(if ($DryRun) { 'DRY RUN' } else { 'SELF-TEST' }))) -ForegroundColor Cyan

    if (Test-Path -LiteralPath $CaptureScript) { Write-Host "  [OK]   capture script: $CaptureScript" }
    else { Write-Host "  [FAIL] capture script missing: $CaptureScript" -ForegroundColor Red; $ok = $false }

    $root = $cfg.Root
    if (-not $root) { Write-Host "  [FAIL] config Root is empty" -ForegroundColor Red; $ok = $false }
    else {
        try {
            New-Item -ItemType Directory -Force -Path $root -ErrorAction Stop | Out-Null
            $probe = Join-Path $root ('.write_probe_{0}.tmp' -f $PID)
            Set-Content -LiteralPath $probe -Value 'x' -ErrorAction Stop
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
            Write-Host "  [OK]   output root writable: $root"
        } catch { Write-Host "  [FAIL] output root NOT writable: $root  ($_)" -ForegroundColor Red; $ok = $false }
    }

    if ($StoreFormat -notin 'int16','float32') { Write-Host "  [FAIL] StoreFormat must be int16 or float32" -ForegroundColor Red; $ok = $false }
    if ($CaptureMode -notin 'auto','exclusive','shared') { Write-Host "  [FAIL] Mode must be auto/exclusive/shared" -ForegroundColor Red; $ok = $false }

    if (-not $cfg.Streams -or $cfg.Streams.Count -eq 0) { Write-Host "  [FAIL] no Streams configured" -ForegroundColor Red; $ok = $false }
    $seen = @{}
    foreach ($s in $cfg.Streams) {
        if (-not $s.Name)   { Write-Host "  [FAIL] a stream has no Name" -ForegroundColor Red; $ok = $false; continue }
        if (-not $s.Device) { Write-Host ("  [FAIL] {0}: no Device (run -ListDevices)" -f $s.Name) -ForegroundColor Red; $ok = $false }
        if ($seen[$s.Name]) { Write-Host ("  [FAIL] duplicate stream Name: {0}" -f $s.Name) -ForegroundColor Red; $ok = $false }
        $seen[$s.Name] = $true
        Write-Host ("  [{0}] would launch:" -f $s.Name) -ForegroundColor Green
        Write-Host ("      powershell.exe {0}" -f ((Get-CaptureArgs $s) -join ' ')) -ForegroundColor DarkGray
    }

    # synthetic check of the finalize (_to_) rename logic
    $prev = 'MIC01_2026-07-17_20-00-00.wav'
    $next = 'MIC01_2026-07-17_21-00-00.wav'
    $endT = ([System.IO.Path]::GetFileNameWithoutExtension($next) -split '_')[-1]
    $expected = [System.IO.Path]::GetFileNameWithoutExtension($prev) + '_to_' + $endT + '.wav'
    if ($expected -eq 'MIC01_2026-07-17_20-00-00_to_21-00-00.wav') { Write-Host "  [OK]   finalize-rename logic" }
    else { Write-Host "  [FAIL] finalize-rename produced '$expected'" -ForegroundColor Red; $ok = $false }

    if ($ok) { Write-Host "SELF-TEST PASS" -ForegroundColor Green; exit 0 }
    else     { Write-Host "SELF-TEST FAILED" -ForegroundColor Red; exit 2 }
}

# ---------------------------------------------------------------------------
# -TestClip : capture one short clip per mic to prove the device works
# ---------------------------------------------------------------------------
if ($TestClip -gt 0) {
    $anyFail = $false
    foreach ($s in $cfg.Streams) {
        Write-Host ("Recording {0}s test clip from {1} ({2})..." -f $TestClip, $s.Name, $s.Device) -ForegroundColor Cyan
        & powershell @(Get-CaptureArgs $s $TestClip)
        if ($LASTEXITCODE -ne 0) { Write-Host ("  [FAIL] {0}: capture exit {1}" -f $s.Name, $LASTEXITCODE) -ForegroundColor Red; $anyFail = $true }
        else {
            $dir = Join-Path $cfg.Root $s.Name
            $nf = Get-ChildItem $dir -File -Filter '*.wav' -EA SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
            if ($nf) { Write-Host ("  [OK] {0}  ->  {1:N0} bytes  ({2})" -f $s.Name, $nf.Length, $nf.FullName) -ForegroundColor Green }
        }
    }
    if ($anyFail) { exit 2 } else { exit 0 }
}

# ===========================================================================
# NORMAL MODE : continuous supervised recording
# ===========================================================================

# single-instance guard (distinct name from every camera recorder)
try   { $script:umMutex = New-Object System.Threading.Mutex($false, 'Global\FieldUltraMicRecorder') }
catch { $script:umMutex = New-Object System.Threading.Mutex($false, 'FieldUltraMicRecorder') }
if (-not $script:umMutex.WaitOne(0)) { Write-Host 'UltraMic recorder already running; exiting.'; exit 0 }

$root   = $cfg.Root
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$masterLog = Join-Path $logDir 'ultramic_recorder.log'

# ONLY this recorder's own mic dirs -> retention / disk-guard can never touch anything else.
$OwnChannels = @($cfg.Streams | ForEach-Object { $_.Name })

function Log([string]$m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Write-Host $line
    Add-Content -Path $masterLog -Value $line
}

function Get-FreeGB { $name = (Split-Path $root -Qualifier).TrimEnd(':'); [math]::Round((Get-PSDrive -Name $name).Free / 1GB, 1) }

# Scoped to $OwnChannels ONLY - this recorder never enumerates other channels' files.
function Get-AllRecordings {
    foreach ($n in $OwnChannels) {
        $d = Join-Path $root $n
        if (Test-Path -LiteralPath $d) { Get-ChildItem $d -File -Filter '*.wav' -EA SilentlyContinue }
    }
}
function Invoke-Retention {
    if ($cfg.RetentionDays -le 0) { return }
    $cut = (Get-Date).AddDays(-$cfg.RetentionDays)
    Get-AllRecordings | Where-Object { $_.LastWriteTime -lt $cut } |
        ForEach-Object { try { Remove-Item $_.FullName -Force; Log ("retention removed " + $_.Name) } catch {} }
}
function Invoke-DiskGuard {
    if ($cfg.MinFreeGB -le 0) { return }
    if (Get-FreeGB -ge $cfg.MinFreeGB) { return }
    Log ("DISK GUARD: only {0} GB free (< {1}); deleting oldest (own mics only)" -f (Get-FreeGB), $cfg.MinFreeGB)
    foreach ($f in (Get-AllRecordings | Sort-Object LastWriteTime)) {
        if (Get-FreeGB -ge $cfg.MinFreeGB) { break }
        try { Remove-Item $f.FullName -Force; Log ("DISK GUARD removed " + $f.Name) } catch {}
    }
}

function Get-NewestFile([string]$dir) {
    Get-ChildItem $dir -File -Filter '*.wav' -EA SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
}
function Get-HandleLen([string]$path, [double]$fallback = 0) {
    try { $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite); $len = $fs.Length; $fs.Dispose(); return $len }
    catch { return $fallback }
}

function Start-Stream($s) {
    $dir = Join-Path $root $s.Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $outLog = Join-Path $logDir ("{0}.capture.log" -f $s.Name)
    # -RedirectStandardOutput truncates on each start, so archive the previous
    # child's log first - it holds the reason the last capture died.
    if (Test-Path -LiteralPath $outLog) {
        $hist = Join-Path $logDir ("{0}.capture.history.log" -f $s.Name)
        try {
            Add-Content -Path $hist -Value ('---- archived {0} ----' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
            Get-Content -LiteralPath $outLog -ErrorAction Stop | Add-Content -Path $hist
        } catch {}
    }
    Start-Process -FilePath 'powershell.exe' -ArgumentList (Get-CaptureArgs $s) `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -PassThru
}

# Kill an orphaned capture child for one of OUR mics (matched by capture script +
# prefix in the command line). Never touches anything else - and never ffmpeg.
function Stop-OrphanCapture([string]$name) {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*-File*ultramic_wasapi_capture.ps1*" -and $_.CommandLine -like "*-Prefix $name*" -and $_.ProcessId -ne $PID } |
        ForEach-Object {
            Log ("{0} killing orphaned capture (pid {1})" -f $name, $_.ProcessId)
            try { Stop-Process -Id $_.ProcessId -Force } catch {}
        }
}

# --- device self-recovery (added 2026-07-18 after a USB wedge: PnP status went ---
# --- 'Unknown' mid-capture and only re-enumeration could revive the mic)       ---

# What killed the last capture child? 'device-missing' = the WASAPI enumeration
# no longer finds the mic (USB wedge) -> a PnP cycle can revive it.
function Get-CaptureFailReason([string]$name) {
    $l = Join-Path $logDir ("{0}.capture.log" -f $name)
    try {
        $tail = Get-Content -LiteralPath $l -Tail 3 -ErrorAction Stop
        if ($tail -match 'no active capture device') { return 'device-missing' }
    } catch {}
    return 'other'
}

# Re-enumerate the wedged USB device. Runs as SYSTEM (the scheduled task), which
# has the rights for Disable/Enable-PnpDevice. Level 2 also restarts Audiosrv.
function Invoke-MicDeviceRecovery([string]$pattern, [int]$level) {
    Log ("RECOVERY level {0}: cycling PnP device(s) matching '*{1}*'" -f $level, $pattern)
    try {
        $devs = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -like "*$pattern*" })
        if ($devs.Count -eq 0) { Log "RECOVERY: no PnP device matches (mic unplugged or dead port)"; return $false }
        foreach ($d in $devs) {
            try { Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; Log ("RECOVERY disabled: {0}" -f $d.FriendlyName) }
            catch { Log ("RECOVERY disable failed ({0}): {1}" -f $d.FriendlyName, $_.Exception.Message) }
        }
        Start-Sleep -Seconds 4
        foreach ($d in $devs) {
            try { Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; Log ("RECOVERY enabled: {0}" -f $d.FriendlyName) }
            catch { Log ("RECOVERY enable failed ({0}): {1}" -f $d.FriendlyName, $_.Exception.Message) }
        }
        Start-Sleep -Seconds 6
        if ($level -ge 2) {
            try { Restart-Service Audiosrv -Force -ErrorAction Stop; Log 'RECOVERY: Audiosrv restarted'; Start-Sleep -Seconds 5 }
            catch { Log ("RECOVERY: Audiosrv restart failed: {0}" -f $_.Exception.Message) }
        }
        return $true
    } catch { Log ("RECOVERY error: {0}" -f $_.Exception.Message); return $false }
}

# Minimal Slack sender reusing the shared QC credentials (best-effort; logs only on failure).
function Send-MicSlack([string]$text) {
    $cfgPath = 'E:\recording_qc\overexposure.config.psd1'
    if (-not (Test-Path -LiteralPath $cfgPath)) { Log 'Slack: no QC config; alert not sent'; return }
    try {
        $sc = Import-PowerShellDataFile -LiteralPath $cfgPath
        if (-not $sc.SlackBotToken -or -not $sc.SlackChannels) { return }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $h = @{ Authorization = "Bearer $($sc.SlackBotToken)"; 'Content-Type' = 'application/json; charset=utf-8' }
        foreach ($t in @($sc.SlackChannels)) {
            $cid = $t
            if ($t -match '^[UW]') {
                $r = Invoke-RestMethod -Uri 'https://slack.com/api/conversations.open' -Method Post -Headers $h -Body ([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json @{ users = $t })))
                if (-not $r.ok) { continue }
                $cid = $r.channel.id
            }
            [void](Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' -Method Post -Headers $h -Body ([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json @{ channel = $cid; text = $text }))))
        }
        Log 'Slack alert sent'
    } catch { Log ("Slack send failed: {0}" -f $_.Exception.Message) }
}

# TRUE if some capture process (an orphan from a crashed supervisor, or a child whose
# exit code we can't read - a PS 5.1 quirk of Start-Process -RedirectStandardOutput)
# currently holds this mic's capture mutex, i.e. is actively recording this mic.
function Test-CaptureMutexHeld([string]$name) {
    $m = $null
    try {
        $m = [System.Threading.Mutex]::OpenExisting(("Global\FieldUltraMicCapture_{0}" -f $name))
        try {
            if ($m.WaitOne(0)) { $m.ReleaseMutex(); return $false }   # we could take it -> nobody recording
            return $true                                              # held by a live capture process
        } catch [System.Threading.AbandonedMutexException] {
            try { $m.ReleaseMutex() } catch {}
            return $false                                             # holder died mid-wait
        }
    } catch { return $false }                                         # mutex doesn't exist -> no capture
    finally { if ($m) { $m.Dispose() } }
}

Log ("=== ultramic recorder starting: {0} mic(s) [{1}], mode {2}, store {3}, segment {4}s, retention {5}d ===" -f `
    $cfg.Streams.Count, ($OwnChannels -join ','), $CaptureMode, $StoreFormat, $cfg.SegmentSeconds, $cfg.RetentionDays)
Log ("free space: {0} GB" -f (Get-FreeGB))

$procs = @{}; $lastSize = @{}; $lastGrew = @{}; $lastName = @{}; $adopted = @{}
# device self-recovery state (per mic)
$failStreak = @{}; $lastStartAt = @{}; $recoveryLevel = @{}; $alerted = @{}; $backoffUntil = @{}
$StallSeconds = if ($cfg.StallSeconds -and [int]$cfg.StallSeconds -gt 0) { [int]$cfg.StallSeconds } else { 240 }
$lastMaint = (Get-Date).AddHours(-1)

while ($true) {
    foreach ($s in $cfg.Streams) {
        $name = $s.Name
        $dir  = Join-Path $root $name
        $alive = $procs.ContainsKey($name) -and (-not $procs[$name].HasExited)

        # Our child isn't running, but a capture process still holds this mic's mutex
        # (orphan from a crashed supervisor, or our child exited 3 because such an
        # orphan exists). It IS recording - adopt it instead of double-pulling the
        # device; the stall-watchdog below reaps it if it stops producing data.
        $orphan = $false
        if (-not $alive) {
            $orphan = Test-CaptureMutexHeld $name
            if ($orphan -and -not $adopted[$name]) {
                Log ("{0} adopting active capture (mutex held by another process)" -f $name)
                $adopted[$name] = $true
                if (-not $lastGrew.ContainsKey($name)) { $lastGrew[$name] = Get-Date }
            }
        }
        if ($alive) { $adopted[$name] = $false }

        if ($alive -or $orphan) {
            $nf = Get-NewestFile $dir
            if ($nf) {
                if ($nf.Name -ne $lastName[$name]) {
                    if ($lastName[$name]) {
                        # backstop only: the capture child renames on rollover itself; this
                        # catches segments left open by a killed/crashed child.
                        $prev = Join-Path $dir $lastName[$name]
                        if ((Test-Path -LiteralPath $prev) -and ($lastName[$name] -notlike '*_to_*')) {
                            $endT = ($nf.BaseName -split '_')[-1]
                            $newBn = [System.IO.Path]::GetFileNameWithoutExtension($lastName[$name]) + '_to_' + $endT + '.wav'
                            try { Rename-Item -LiteralPath $prev -NewName $newBn -ErrorAction Stop; Log ("{0} finalized {1}" -f $name, $newBn) } catch {}
                        }
                    }
                    $lastName[$name] = $nf.Name; $lastSize[$name] = 0; $lastGrew[$name] = Get-Date
                }
                $sz = Get-HandleLen $nf.FullName $lastSize[$name]
                if ($sz -gt $lastSize[$name]) {
                    $lastSize[$name] = $sz; $lastGrew[$name] = Get-Date
                    # data is flowing again -> clear the failure/recovery state
                    # (also when alerted/backoff persists with streak already zeroed by
                    #  the slow-retry cadence - seen in the 2026-07-19 recovery)
                    if ($failStreak[$name] -gt 0 -or $alerted[$name] -or $backoffUntil.ContainsKey($name)) {
                        Log ("{0} capture healthy again (streak {1} cleared)" -f $name, $failStreak[$name])
                        if ($alerted[$name]) { Send-MicSlack (":white_check_mark: UltraMic {0} recovered and recording again ({1})." -f $name, (Get-Date).ToString('HH:mm')) }
                        $failStreak[$name] = 0; $recoveryLevel[$name] = 0; $alerted[$name] = $false
                        $backoffUntil.Remove($name)
                    }
                }
            }
            # no file yet counts as "not growing": the stall window covers both cases
            if (((Get-Date) - $lastGrew[$name]).TotalSeconds -gt $StallSeconds) {
                Log ("{0} stalled ({1}s no growth); restarting" -f $name, $StallSeconds)
                if ($alive) { try { Stop-Process -Id $procs[$name].Id -Force } catch {} }
                Stop-OrphanCapture $name
                $alive = $false; $orphan = $false; $adopted[$name] = $false
                if ($procs.ContainsKey($name)) { $procs.Remove($name) }
            }
        }

        if (-not ($alive -or $orphan)) {
            # after an alert we keep retrying, but only every 5 min (no restart storm)
            if ($backoffUntil.ContainsKey($name) -and ((Get-Date) -lt $backoffUntil[$name])) { continue }

            if ($procs.ContainsKey($name)) {
                Log ("{0} capture stopped; restarting" -f $name)
                # rapid-death streak: child died within 45 s of starting
                if ($lastStartAt[$name] -and (((Get-Date) - $lastStartAt[$name]).TotalSeconds -lt 45)) {
                    $failStreak[$name] = 1 + $(if ($failStreak[$name]) { $failStreak[$name] } else { 0 })
                } else { $failStreak[$name] = 0; $recoveryLevel[$name] = 0 }

                # escalation ladder (device wedge -> PnP cycle -> +Audiosrv -> page + backoff)
                $reason = Get-CaptureFailReason $name
                if ($failStreak[$name] -ge 6 -and $reason -eq 'device-missing' -and (-not $recoveryLevel[$name] -or $recoveryLevel[$name] -lt 1)) {
                    [void](Invoke-MicDeviceRecovery $s.Device 1); $recoveryLevel[$name] = 1
                }
                elseif ($failStreak[$name] -ge 12 -and $reason -eq 'device-missing' -and $recoveryLevel[$name] -lt 2) {
                    [void](Invoke-MicDeviceRecovery $s.Device 2); $recoveryLevel[$name] = 2
                }
                elseif ($failStreak[$name] -ge 18 -and -not $alerted[$name]) {
                    Send-MicSlack (":rotating_light: UltraMic {0} DOWN - capture failing ({1}); automatic PnP recovery did not revive it. Likely needs a physical replug or PC reboot. Will keep retrying every 5 min." -f $name, $reason)
                    $alerted[$name] = $true
                }
                if ($alerted[$name]) { $backoffUntil[$name] = (Get-Date).AddMinutes(5) }
            }
            $procs[$name]    = Start-Stream $s
            $lastSize[$name] = 0
            $lastGrew[$name] = Get-Date
            $lastStartAt[$name] = Get-Date
            Log ("{0} started (pid {1})" -f $name, $procs[$name].Id)
            Start-Sleep -Seconds 2
        }
    }

    if (((Get-Date) - $lastMaint).TotalMinutes -ge 60) {
        $lastMaint = Get-Date
        Invoke-Retention
        Invoke-DiskGuard
        Log ("heartbeat: free {0} GB" -f (Get-FreeGB))
    }
    Start-Sleep -Seconds 15
}
