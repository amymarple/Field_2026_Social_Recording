<#
.SYNOPSIS
    Interactive GUI recorder for RTSP security cameras (WinForms, click Start / click Stop).
    NOT a system service: runs in your session, shows live per-camera status, and only ever
    stops ffmpeg processes it started itself.

.DESCRIPTION
    - Auto-discovers ALL existing cameras across the three connection paths:
        NVR-bridged : CH01-CH06 via the Reolink NVR (recorder.config.psd1 -> Preview_0N_main)
        direct-IP   : CH07/CH08 in-box sleep cams (extra_cam.config.psd1, Dahua URL format)
        direct-IP   : 108/109 EmpireTech thermal+visual, 4 streams (thermal.config.psd1)
      plus any custom cameras listed in gui_recorder.config.psd1.
    - "Start All" spawns one ffmpeg per camera: RTSP over TCP, -c copy (no re-encode),
      hourly fragmented-MP4 segments (crash-safe) under <OutputRoot>\<Name>\.
    - SAFETY: a camera already being recorded by the production SYSTEM task shows as
      SERVICE and is skipped/locked - the GUI never double-pulls a stream and never
      touches service-owned ffmpeg processes. Stop All stops only GUI-owned recorders.
    - Light supervision: a 5 s timer watches file growth; a stalled GUI recording is
      auto-restarted (checkbox to disable).
    - Closing the window asks whether to stop GUI recordings or leave them running.

.EXAMPLE
    powershell -STA -ExecutionPolicy Bypass -File .\interactive_recorder_gui.ps1
    .\interactive_recorder_gui.ps1 -SelfTest     # headless config/ffmpeg/URL check, no GUI
    .\interactive_recorder_gui.ps1 -AutoStart    # open GUI and immediately Start All
#>

[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$SelfTest,
    [switch]$AutoStart
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------ config ----

$base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ConfigPath) { $ConfigPath = Join-Path $base 'gui_recorder.config.psd1' }

$defaults = @{
    OutputRoot               = 'E:\gui_record'
    FfmpegPath               = ''
    ImportProductionChannels = $true
    ProductionConfig         = 'E:\Reolink_record\recorder.config.psd1'
    ExtraCamConfig           = 'E:\Reolink_record\extra_cam.config.psd1'
    ThermalConfig            = 'E:\thermal_record\thermal.config.psd1'
    Cameras                  = @()
    SegmentSeconds           = 3600
    StallSeconds             = 60
}
$cfg = $defaults.Clone()
if (Test-Path -LiteralPath $ConfigPath) {
    $user = Import-PowerShellDataFile -LiteralPath $ConfigPath
    foreach ($k in $user.Keys) { $cfg[$k] = $user[$k] }
}

function Get-FfmpegPath {
    if ($cfg.FfmpegPath -and (Test-Path -LiteralPath $cfg.FfmpegPath)) { return $cfg.FfmpegPath }
    $pinned = 'E:\Reolink_record\bin\ffmpeg.exe'
    if (Test-Path -LiteralPath $pinned) { return $pinned }
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    throw 'ffmpeg not found (config FfmpegPath, E:\Reolink_record\bin, PATH)'
}

function Hide-Creds([string]$u) { return ($u -replace '^rtsp://[^@/]*@', 'rtsp://') }

# TRUE size of a file ffmpeg is still writing. Plain Get-ChildItem .Length returns a
# stale value (often 0/old) because NTFS updates directory metadata lazily for open
# files - the standard Get-HandleLen idiom from the production QC scripts.
function Get-HandleLen([string]$Path) {
    try {
        $fs = [IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        $len = $fs.Length; $fs.Close(); return $len
    } catch { return -1 }
}

# Build the camera list: NVR channels + extra cams + custom entries.
function Get-CameraList {
    $cams = New-Object System.Collections.ArrayList
    if ($cfg.ImportProductionChannels -and (Test-Path -LiteralPath $cfg.ProductionConfig)) {
        $p = Import-PowerShellDataFile -LiteralPath $cfg.ProductionConfig
        $root = if ($p.Root) { $p.Root } else { 'E:\Reolink_record' }
        foreach ($n in $p.Channels) {
            $name = ('CH{0:00}' -f [int]$n)
            $url = ('rtsp://{0}:{1}@{2}:{3}/Preview_{4:00}_main' -f $p.User, $p.Pass, $p.NvrIp, $p.RtspPort, [int]$n)
            [void]$cams.Add([pscustomobject]@{ Name = $name; Url = $url; Type = 'NVR'; ProdDir = (Join-Path $root $name) })
        }
    }
    if ($cfg.ExtraCamConfig -and (Test-Path -LiteralPath $cfg.ExtraCamConfig)) {
        $e = Import-PowerShellDataFile -LiteralPath $cfg.ExtraCamConfig
        $root = if ($e.Root) { $e.Root } else { 'E:\Reolink_record' }
        foreach ($s in $e.Streams) {
            [void]$cams.Add([pscustomobject]@{ Name = $s.Name; Url = $s.Url; Type = 'EXTRA'; ProdDir = (Join-Path $root $s.Name) })
        }
    }
    if ($cfg.ThermalConfig -and (Test-Path -LiteralPath $cfg.ThermalConfig)) {
        $t = Import-PowerShellDataFile -LiteralPath $cfg.ThermalConfig
        $root = if ($t.Root) { $t.Root } else { 'E:\thermal_record' }
        foreach ($s in $t.Streams) {
            [void]$cams.Add([pscustomobject]@{ Name = $s.Name; Url = $s.Url; Type = 'THERMAL'; ProdDir = (Join-Path $root $s.Name) })
        }
    }
    foreach ($c in $cfg.Cameras) {
        [void]$cams.Add([pscustomobject]@{ Name = $c.Name; Url = $c.Url; Type = 'CUSTOM'; ProdDir = $null })
    }
    # de-duplicate by name (custom entries may intentionally override - last wins)
    $seen = @{}; $out = New-Object System.Collections.ArrayList
    foreach ($c in $cams) { $seen[$c.Name] = $c }
    foreach ($k in ($seen.Keys | Sort-Object)) { [void]$out.Add($seen[$k]) }
    return $out
}

function Get-FfmpegProcs {
    @(Get-CimInstance Win32_Process -Filter "Name='ffmpeg.exe'" -ErrorAction SilentlyContinue)
}

# Classify a camera against the running ffmpeg processes.
#   returns @{ Status = 'SERVICE'|'RECORDING'|'STOPPED'; ProcId = <int or 0> }
function Get-CamState {
    param($Cam, $Procs)
    foreach ($p in $Procs) {
        $cl = [string]$p.CommandLine
        if (-not $cl) { continue }
        $mine = ($cl -like ('*' + (Join-Path $cfg.OutputRoot $Cam.Name) + '*'))
        if ($mine) { return @{ Status = 'RECORDING'; ProcId = [int]$p.ProcessId } }
    }
    foreach ($p in $Procs) {
        $cl = [string]$p.CommandLine
        if (-not $cl) { continue }
        if ($cl.Contains($Cam.Url)) { return @{ Status = 'SERVICE'; ProcId = [int]$p.ProcessId } }
    }
    # SYSTEM-task ffmpeg command lines are NOT visible to a non-admin session, so the
    # authoritative service check is the camera's PRODUCTION folder. The open segment
    # (no _to_) is found by NAME sort (write-time metadata is lazy); if an exclusive
    # open on it fails with a sharing violation, a recorder is actively writing it.
    if ($Cam.ProdDir -and (Test-Path -LiteralPath $Cam.ProdDir)) {
        $newest = Get-ChildItem -LiteralPath $Cam.ProdDir -Filter '*.mp4' -File -ErrorAction SilentlyContinue |
                  Sort-Object Name -Descending | Select-Object -First 1
        if ($newest) {
            if ($newest.Name -notlike '*_to_*') {
                try {
                    $fs = [IO.File]::Open($newest.FullName, 'Open', 'Read', 'None')
                    $fs.Close()   # exclusive open succeeded -> nobody is writing it
                } catch { return @{ Status = 'SERVICE'; ProcId = 0 } }
            }
            if (((Get-Date) - $newest.LastWriteTime).TotalSeconds -lt 150) {
                return @{ Status = 'SERVICE'; ProcId = 0 }   # rollover window
            }
        }
    }
    return @{ Status = 'STOPPED'; ProcId = 0 }
}

function Start-Cam {
    param($Cam)
    $dir = Join-Path $cfg.OutputRoot $Cam.Name
    $logDir = Join-Path $cfg.OutputRoot 'logs'
    New-Item -ItemType Directory -Force -Path $dir, $logDir | Out-Null
    $outPat = Join-Path $dir ($Cam.Name + '_%Y-%m-%d_%H-%M-%S.mp4')
    $fargs = @(
        '-hide_banner', '-nostdin', '-loglevel', 'warning',
        '-rtsp_transport', 'tcp',
        '-i', ('"{0}"' -f $Cam.Url),
        '-c', 'copy', '-map', '0',
        '-f', 'segment',
        '-segment_time', $cfg.SegmentSeconds,
        '-segment_atclocktime', '1',
        '-reset_timestamps', '1',
        '-strftime', '1',
        '-segment_format_options', 'movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=2000000',
        ('"{0}"' -f $outPat)
    ) -join ' '
    $p = Start-Process -FilePath (Get-FfmpegPath) -ArgumentList $fargs -WindowStyle Hidden -PassThru `
         -RedirectStandardError (Join-Path $logDir ($Cam.Name + '.ffmpeg.log'))
    return $p.Id
}

function Get-NewestFile {
    param($Cam)
    $dir = Join-Path $cfg.OutputRoot $Cam.Name
    if (-not (Test-Path -LiteralPath $dir)) { return $null }
    Get-ChildItem -LiteralPath $dir -Filter '*.mp4' -File -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1   # name sort: metadata is lazy for the open file
}

# --------------------------------------------------------------- self test ----

if ($SelfTest) {
    Write-Host 'SelfTest: headless checks (no GUI, nothing started)' -ForegroundColor Cyan
    $ok = $true
    try { $ff = Get-FfmpegPath; Write-Host "  [PASS] ffmpeg: $ff" -ForegroundColor Green }
    catch { Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red; $ok = $false }
    $cams = Get-CameraList
    if ($cams.Count -gt 0) {
        Write-Host ("  [PASS] discovered {0} camera(s):" -f $cams.Count) -ForegroundColor Green
        foreach ($c in $cams) { Write-Host ("     {0,-6} {1,-7} {2}" -f $c.Name, $c.Type, (Hide-Creds $c.Url)) }
    } else { Write-Host '  [FAIL] no cameras discovered (check config paths)' -ForegroundColor Red; $ok = $false }
    try {
        New-Item -ItemType Directory -Force -Path $cfg.OutputRoot | Out-Null
        $probe = Join-Path $cfg.OutputRoot ('probe_{0}.tmp' -f $PID)
        Set-Content -LiteralPath $probe -Value 'x'; Remove-Item -LiteralPath $probe -Force
        Write-Host "  [PASS] output root writable: $($cfg.OutputRoot)" -ForegroundColor Green
    } catch { Write-Host "  [FAIL] output root: $($_.Exception.Message)" -ForegroundColor Red; $ok = $false }
    $procs = Get-FfmpegProcs
    Write-Host ("  [INFO] ffmpeg processes running now: {0}" -f $procs.Count)
    foreach ($c in $cams) {
        $st = Get-CamState -Cam $c -Procs $procs
        Write-Host ("     {0,-6} -> {1}" -f $c.Name, $st.Status)
    }
    if ($ok) { Write-Host 'SelfTest: ALL PASS' -ForegroundColor Green; exit 0 } else { exit 1 }
}

# ------------------------------------------------------------ single instance ----

$mutex = New-Object System.Threading.Mutex($false, 'Global\FieldGuiRecorder')
if (-not $mutex.WaitOne(0)) {
    [void][System.Windows.Forms.MessageBox]::Show('Another instance of the GUI recorder is already running.', 'Field RTSP Recorder')
    exit 1
}

# --------------------------------------------------------------------- GUI ----

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:cams  = Get-CameraList
$script:state = @{}   # name -> @{ LastSize; LastGrowth }

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Field RTSP Interactive Recorder'
$form.Size = New-Object System.Drawing.Size(860, 560)
$form.StartPosition = 'CenterScreen'

$lv = New-Object System.Windows.Forms.ListView
$lv.View = 'Details'; $lv.FullRowSelect = $true; $lv.GridLines = $true
$lv.Location = New-Object System.Drawing.Point(10, 10)
$lv.Size = New-Object System.Drawing.Size(824, 330)
$lv.Anchor = 'Top,Left,Right,Bottom'
[void]$lv.Columns.Add('Camera', 70)
[void]$lv.Columns.Add('Type', 65)
[void]$lv.Columns.Add('Status', 90)
[void]$lv.Columns.Add('Current file', 300)
[void]$lv.Columns.Add('Size (MB)', 80)
[void]$lv.Columns.Add('Note', 190)
foreach ($c in $script:cams) {
    $it = New-Object System.Windows.Forms.ListViewItem($c.Name)
    [void]$it.SubItems.Add($c.Type); [void]$it.SubItems.Add('...')
    [void]$it.SubItems.Add(''); [void]$it.SubItems.Add(''); [void]$it.SubItems.Add((Hide-Creds $c.Url))
    $it.Tag = $c
    [void]$lv.Items.Add($it)
}

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true; $log.ScrollBars = 'Vertical'; $log.ReadOnly = $true
$log.Location = New-Object System.Drawing.Point(10, 385)
$log.Size = New-Object System.Drawing.Size(824, 120)
$log.Anchor = 'Left,Right,Bottom'

function Add-Log([string]$m) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $m)
    $log.AppendText($line + [Environment]::NewLine)
}

function New-Btn([string]$text, [int]$x, [int]$w) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $text
    $b.Location = New-Object System.Drawing.Point($x, 348)
    $b.Size = New-Object System.Drawing.Size($w, 30)
    $b.Anchor = 'Left,Bottom'
    return $b
}
$btnStartAll = New-Btn 'Start All' 10 110
$btnStopAll  = New-Btn 'Stop All'  128 110
$btnStartSel = New-Btn 'Start Selected' 246 110
$btnStopSel  = New-Btn 'Stop Selected'  364 110
$btnOpen     = New-Btn 'Open Folder'    482 110
$chkAuto = New-Object System.Windows.Forms.CheckBox
$chkAuto.Text = 'Auto-restart stalled'
$chkAuto.Checked = $true
$chkAuto.Location = New-Object System.Drawing.Point(606, 353)
$chkAuto.Size = New-Object System.Drawing.Size(160, 22)
$chkAuto.Anchor = 'Left,Bottom'

$form.Controls.AddRange(@($lv, $btnStartAll, $btnStopAll, $btnStartSel, $btnStopSel, $btnOpen, $chkAuto, $log))

function Start-One {
    param($Item)
    $cam = $Item.Tag
    $st = Get-CamState -Cam $cam -Procs (Get-FfmpegProcs)
    if ($st.Status -eq 'SERVICE')   { Add-Log ("{0}: already recorded by the SYSTEM service - skipped (GUI never double-pulls)" -f $cam.Name); return }
    if ($st.Status -eq 'RECORDING') { Add-Log ("{0}: already recording (pid {1})" -f $cam.Name, $st.ProcId); return }
    try {
        $procId = Start-Cam -Cam $cam
        $script:state[$cam.Name] = @{ LastSize = -1; LastGrowth = (Get-Date) }
        Add-Log ("{0}: started (pid {1}) -> {2}" -f $cam.Name, $procId, (Join-Path $cfg.OutputRoot $cam.Name))
    } catch { Add-Log ("{0}: START FAILED - {1}" -f $cam.Name, $_.Exception.Message) }
}

function Stop-One {
    param($Item)
    $cam = $Item.Tag
    $st = Get-CamState -Cam $cam -Procs (Get-FfmpegProcs)
    if ($st.Status -eq 'SERVICE')  { Add-Log ("{0}: recorded by the SYSTEM service - the GUI will not stop it" -f $cam.Name); return }
    if ($st.Status -ne 'RECORDING') { Add-Log ("{0}: not recording" -f $cam.Name); return }
    try {
        Stop-Process -Id $st.ProcId -Force
        Add-Log ("{0}: stopped (pid {1}); the fragmented MP4 stays playable" -f $cam.Name, $st.ProcId)
    } catch { Add-Log ("{0}: STOP FAILED - {1}" -f $cam.Name, $_.Exception.Message) }
}

function Update-Grid {
    $procs = Get-FfmpegProcs
    foreach ($it in $lv.Items) {
        $cam = $it.Tag
        $st = Get-CamState -Cam $cam -Procs $procs
        $status = $st.Status
        $f = Get-NewestFile -Cam $cam
        $fname = ''; $fsize = ''
        $hl = -1
        if ($f) {
            $fname = $f.Name
            $hl = Get-HandleLen $f.FullName          # true size; .Length is stale for the open file
            if ($hl -lt 0) { $hl = $f.Length }
            $fsize = [string][math]::Round($hl / 1MB, 1)
        }
        if ($status -eq 'RECORDING') {
            if (-not $script:state.ContainsKey($cam.Name)) { $script:state[$cam.Name] = @{ LastSize = -1; LastGrowth = (Get-Date) } }
            $s = $script:state[$cam.Name]
            $sz = 0; if ($hl -ge 0) { $sz = $hl }
            if ($sz -gt $s.LastSize) { $s.LastSize = $sz; $s.LastGrowth = (Get-Date) }
            elseif (((Get-Date) - $s.LastGrowth).TotalSeconds -gt $cfg.StallSeconds) {
                $status = 'STALLED'
                if ($chkAuto.Checked) {
                    Add-Log ("{0}: no growth for {1}s - restarting" -f $cam.Name, $cfg.StallSeconds)
                    try { Stop-Process -Id $st.ProcId -Force } catch {}
                    try {
                        $procId = Start-Cam -Cam $cam
                        $script:state[$cam.Name] = @{ LastSize = -1; LastGrowth = (Get-Date) }
                        Add-Log ("{0}: restarted (pid {1})" -f $cam.Name, $procId)
                        $status = 'RECORDING'
                    } catch { Add-Log ("{0}: RESTART FAILED - {1}" -f $cam.Name, $_.Exception.Message) }
                }
            }
        }
        $it.SubItems[2].Text = $status
        $it.SubItems[3].Text = $fname
        $it.SubItems[4].Text = $fsize
        if ($status -eq 'RECORDING' -and -not $f) { $it.SubItems[5].Text = 'no data yet - camera on/reachable?' }
        elseif ($status -eq 'STALLED')            { $it.SubItems[5].Text = 'stream stopped delivering' }
        else                                       { $it.SubItems[5].Text = (Hide-Creds $cam.Url) }
        switch ($status) {
            'RECORDING' { $it.BackColor = [System.Drawing.Color]::FromArgb(215, 245, 215) }
            'SERVICE'   { $it.BackColor = [System.Drawing.Color]::FromArgb(215, 230, 250) }
            'STALLED'   { $it.BackColor = [System.Drawing.Color]::FromArgb(255, 235, 200) }
            default     { $it.BackColor = [System.Drawing.Color]::White }
        }
    }
}

$btnStartAll.Add_Click({ foreach ($it in $lv.Items) { Start-One -Item $it }; Update-Grid })
$btnStopAll.Add_Click({  foreach ($it in $lv.Items) { Stop-One  -Item $it }; Update-Grid })
$btnStartSel.Add_Click({ foreach ($it in $lv.SelectedItems) { Start-One -Item $it }; Update-Grid })
$btnStopSel.Add_Click({  foreach ($it in $lv.SelectedItems) { Stop-One  -Item $it }; Update-Grid })
$btnOpen.Add_Click({ Start-Process explorer.exe $cfg.OutputRoot })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.Add_Tick({ Update-Grid })
$timer.Start()

$form.Add_FormClosing({
    param($s, $e)
    $procs = Get-FfmpegProcs
    $mine = @()
    foreach ($c in $script:cams) {
        $st = Get-CamState -Cam $c -Procs $procs
        if ($st.Status -eq 'RECORDING') { $mine += @{ Cam = $c; ProcId = $st.ProcId } }
    }
    if ($mine.Count -gt 0) {
        $r = [System.Windows.Forms.MessageBox]::Show(
            ("{0} GUI recording(s) are running.`nYes = stop them and exit`nNo = leave them recording and exit`nCancel = stay open" -f $mine.Count),
            'Field RTSP Recorder', 'YesNoCancel', 'Question')
        if ($r -eq 'Cancel') { $e.Cancel = $true; return }
        if ($r -eq 'Yes') {
            foreach ($m in $mine) { try { Stop-Process -Id $m.ProcId -Force } catch {} }
        }
    }
    $timer.Stop()
})

Add-Log ("Discovered {0} camera(s). Output: {1}" -f $script:cams.Count, $cfg.OutputRoot)
Add-Log 'Blue SERVICE rows are recorded by the production SYSTEM task - the GUI leaves them alone.'
Update-Grid
if ($AutoStart) { foreach ($it in $lv.Items) { Start-One -Item $it }; Update-Grid }

[void]$form.ShowDialog()
$mutex.ReleaseMutex()
