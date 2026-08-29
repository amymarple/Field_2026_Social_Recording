<#
led_sync.ps1 - PC-clock LED sync pulser (video <-> wild_console ephys alignment).

Drives an LED on a Raspberry Pi Pico (MicroPython over USB serial, default COM11)
at 1 Hz using THIS computer's clock, and logs every rising edge with a precise PC
timestamp into hourly TXT files. The LED sits in the cameras' view; wild_console
stamps ephys with the same PC clock, so matching an LED-onset frame to its logged
timestamp puts video and ephys on one common timebase.

Design notes
  - The PC is the timebase. The Pico stores NOTHING: on start this script injects
    a tiny listener into Pico RAM via the MicroPython raw REPL ('1'=LED on,
    '0'=LED off, 'q'=quit). A power-cycled Pico is re-armed simply by restarting
    this script (it also auto-reconnects if the port drops mid-run).
  - GP14 AND GP15 are both driven (operator unsure which pin the LED is on), plus
    the onboard LED as a visual heartbeat. Driving the unused pin is harmless.
  - The rising edge is the sync mark: sent at the top of each PC second (sleep to
    ~40 ms before the boundary, then spin-wait to sub-ms). offset_ms in the log is
    how late the serial write completed after the intended boundary; USB CDC adds
    ~1-3 ms before the LED physically lights. Falling edge (+DutyMs) is not logged.
  - Log files roll on the hour: E:\led_sync\LEDSYNC_YYYY-MM-DD_HH-00-00.txt
    (~3600 lines/hour, trivial write load; opened with shared read).

Run from a terminal; Ctrl+C stops cleanly (LED off, "# STOP" line in the log):

  powershell -NoProfile -ExecutionPolicy Bypass -File .\led_sync.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\led_sync.ps1 -TestSeconds 10

Exit codes: 0 = ok, 2 = fatal (port missing / not a MicroPython device).
#>
param(
    [string]$Port        = 'COM11',
    [string]$LogDir      = 'E:\led_sync',
    [int]   $DutyMs      = 500,   # LED on-time per second; rising edge is the sync mark
    [int]   $TestSeconds = 0,     # >0: pulse N seconds with console feedback, then exit
    [switch]$SelfTest             # offline logic check: no COM, no files
)

$ErrorActionPreference = 'Stop'

# MicroPython listener injected into Pico RAM (raw REPL). Byte commands over USB
# serial: '1' pins high, '0' pins low, 'q' pins low + exit.
$script:PicoListener = @(
    'import sys',
    'from machine import Pin',
    'ps=[Pin(14,Pin.OUT,value=0),Pin(15,Pin.OUT,value=0)]',
    'try:',
    ' ps.append(Pin("LED",Pin.OUT,value=0))',
    'except:',
    ' pass',
    'while True:',
    ' c=sys.stdin.buffer.read(1)',
    " if c==b'1':",
    '  for p in ps: p.value(1)',
    " elif c==b'0':",
    '  for p in ps: p.value(0)',
    " elif c==b'q':",
    '  for p in ps: p.value(0)',
    '  break'
) -join "`n"

function Get-NextSecond {
    # next whole second of the PC clock (local time, sub-ms via precise UtcNow source)
    [long]$t = ([math]::Floor([datetime]::Now.Ticks / 10000000) + 1) * 10000000
    return [datetime]::new($t)
}

function Get-HourLogPath([datetime]$b) {
    return (Join-Path $LogDir ('LEDSYNC_{0:yyyy-MM-dd_HH}-00-00.txt' -f $b))
}

if ($SelfTest) {
    $fake = [datetime]::new(2026, 8, 29, 13, 59, 59, 750)
    [long]$ft = ([math]::Floor($fake.Ticks / 10000000) + 1) * 10000000
    $b = [datetime]::new($ft)
    $ok = $true
    if ($b -ne [datetime]::new(2026, 8, 29, 14, 0, 0)) { Write-Host 'FAIL boundary math'; $ok = $false }
    if ((Split-Path (Get-HourLogPath $b) -Leaf) -ne 'LEDSYNC_2026-08-29_14-00-00.txt') { Write-Host 'FAIL log name'; $ok = $false }
    $line = '{0} RISE sched={1:HH:mm:ss} offset_ms={2:+0.0;-0.0;0.0}' -f $b.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'), $b, 2.34
    if ($line -notmatch 'RISE sched=14:00:00 offset_ms=\+2\.3$') { Write-Host "FAIL line format: $line"; $ok = $false }
    if ($ok) { Write-Host 'SelfTest PASS (boundary math, hourly filename, log line format)'; exit 0 }
    exit 2
}

function Read-SerialUntil([System.IO.Ports.SerialPort]$S, [string]$Pattern, [int]$TimeoutMs = 3000) {
    $t = [Diagnostics.Stopwatch]::StartNew(); $buf = ''
    while ($t.ElapsedMilliseconds -lt $TimeoutMs) {
        Start-Sleep -Milliseconds 50
        $buf += $S.ReadExisting()
        if ($buf -match $Pattern) { return $buf }
    }
    return $null
}

function Connect-Pico([string]$PortName) {
    $s = New-Object System.IO.Ports.SerialPort($PortName, 115200, 'None', 8, 'One')
    $s.ReadTimeout = 1000; $s.WriteTimeout = 1000
    $s.DtrEnable = $true; $s.RtsEnable = $true   # CDC needs DTR or stdin/stdout stall
    $s.Open()
    Start-Sleep -Milliseconds 200
    $s.DiscardInBuffer()
    $s.Write(("`r" + [char]3 + [char]3))         # Ctrl-C x2: interrupt anything running
    Start-Sleep -Milliseconds 300
    $s.DiscardInBuffer()
    $s.Write(("`r" + [char]1))                   # Ctrl-A: raw REPL
    if (-not (Read-SerialUntil $s 'raw REPL')) {
        $s.Close(); throw "no raw-REPL prompt on $PortName - is this the MicroPython Pico?"
    }
    $s.Write($script:PicoListener)
    $s.Write([string][char]4)                    # Ctrl-D: compile + run listener
    if (-not (Read-SerialUntil $s 'OK')) {
        $s.Close(); throw 'Pico did not accept the listener program'
    }
    return $s
}

function Disconnect-Pico([System.IO.Ports.SerialPort]$S) {
    try {
        $S.Write('0'); Start-Sleep -Milliseconds 50
        $S.Write('q'); Start-Sleep -Milliseconds 150
        $S.Write([string][char]2)                # Ctrl-B: back to friendly REPL
    } catch { }
    try { $S.Close() } catch { }
}

function Open-HourLog([datetime]$b) {
    if ($script:logWriter) { try { $script:logWriter.Close() } catch { } }
    $p = Get-HourLogPath $b
    $isNew = -not (Test-Path $p)
    $script:logWriter = New-Object IO.StreamWriter($p, $true, [Text.Encoding]::ASCII)  # append, shared read
    $script:logWriter.AutoFlush = $true
    if ($isNew) {
        $script:logWriter.WriteLine("# LEDSYNC rising-edge log  host=$env:COMPUTERNAME  port=$Port  pins=GP14+GP15+onboard  duty_ms=$DutyMs")
        $script:logWriter.WriteLine('# columns: <PC send-complete timestamp> RISE sched=<intended second> offset_ms=<send lag after boundary>')
    }
    $script:logHour = $b.ToString('yyyyMMddHH')
    $script:logPath = $p
}

function Write-Log([string]$line) { if ($script:logWriter) { $script:logWriter.WriteLine($line) } }
function Stamp { return [datetime]::Now.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') }

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$script:logWriter = $null
$sp = $null
try {
    $sp = Connect-Pico $Port
    Open-HourLog ([datetime]::Now)
    Write-Log ("# START {0} pid=$PID" -f (Stamp))
    Write-Host "led_sync: pulsing 1 Hz on $Port (GP14+GP15+onboard), duty $DutyMs ms"
    Write-Host "led_sync: logging rising edges to $($script:logPath)  (Ctrl+C to stop)"

    $n = 0
    while ($true) {
        $next = Get-NextSecond
        if ($next.ToString('yyyyMMddHH') -ne $script:logHour) {
            Open-HourLog $next
            Write-Host "led_sync: rolled to $($script:logPath)"
        }
        $lead = ($next - [datetime]::Now).TotalMilliseconds - 40
        if ($lead -gt 0) { Start-Sleep -Milliseconds ([int]$lead) }
        while ([datetime]::Now -lt $next) { }    # spin the last <=40 ms to the boundary
        try {
            $sp.Write('1')
            $stamp = [datetime]::Now
            $off = ($stamp - $next).TotalMilliseconds
            Write-Log ('{0} RISE sched={1:HH:mm:ss} offset_ms={2:+0.0;-0.0;0.0}' -f $stamp.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'), $next, $off)
            if ($TestSeconds -gt 0) { Write-Host ('  pulse {0:HH:mm:ss} offset_ms={1:+0.0;-0.0;0.0}' -f $next, $off) }
            Start-Sleep -Milliseconds $DutyMs
            $sp.Write('0')
        } catch {
            Write-Log ('# DROP {0} serial write failed: {1}' -f (Stamp), $_.Exception.Message)
            Write-Host "led_sync: serial dropped ($($_.Exception.Message)) - reconnecting every 5 s..."
            try { $sp.Close() } catch { }
            $sp = $null
            while (-not $sp) {
                Start-Sleep -Seconds 5
                try { $sp = Connect-Pico $Port } catch { $sp = $null }
            }
            Write-Log ('# RECONNECT {0}' -f (Stamp))
            Write-Host 'led_sync: reconnected'
            continue
        }
        $n++
        if ($TestSeconds -gt 0 -and $n -ge $TestSeconds) { break }
    }
    if ($TestSeconds -gt 0) { Write-Host "led_sync: test done ($n pulses)" }
} finally {
    if ($sp) { Disconnect-Pico $sp }
    if ($script:logWriter) {
        try { $script:logWriter.WriteLine('# STOP {0}' -f (Stamp)); $script:logWriter.Close() } catch { }
    }
}
exit 0
