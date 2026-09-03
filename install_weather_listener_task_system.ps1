<#
.SYNOPSIS
    Install the local weather listener as a SYSTEM scheduled task + open its port.

.DESCRIPTION
    Run once from an ELEVATED Administrator PowerShell. Registers a SYSTEM task that
    runs weather_listener.ps1 at startup and self-heals (repeats every 5 min; the
    listener's own mutex makes duplicate launches exit immediately), and adds an
    inbound firewall rule for the listener port restricted to the LOCAL SUBNET (the
    console lives on the router LAN). Independent of every recorder.

    Before installing:
        powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -SelfTest

    After installing, point the console at this PC (README_weather_listener.md) and
    check packets are landing:
        powershell -NoProfile -ExecutionPolicy Bypass -File weather_listener.ps1 -Status
#>
[CmdletBinding()]
param(
    [string]$TaskName   = 'Field Weather Listener',
    [string]$ScriptPath,
    [string]$ConfigPath = 'D:\weather_data\weather.config.psd1',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) {
    $base = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ScriptPath = Join-Path $base 'weather_listener.ps1'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Worker script not found: $ScriptPath" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) { Write-Host 'NOT ELEVATED. Re-open PowerShell as Administrator and run again.' -ForegroundColor Red; exit 1 }

# port from the config if there is one (defaults mirror weather_listener.ps1)
$port = 8085
if (Test-Path -LiteralPath $ConfigPath) {
    $c = Import-PowerShellDataFile -Path $ConfigPath
    if ($c.Port) { $port = [int]$c.Port }
} else {
    Write-Host "No config at $ConfigPath - using built-in defaults (port $port, D:\weather_data\local). Copy weather.config.example.psd1 there to change them." -ForegroundColor Yellow
}

# firewall: inbound TCP on the port, local subnet only
$ruleName = "Field Weather Listener (TCP $port)"
Get-NetFirewallRule -DisplayName 'Field Weather Listener*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port `
    -RemoteAddress LocalSubnet -Profile Any -Description 'Ambient Weather console -> local weather_listener.ps1' | Out-Null
Write-Host ("Firewall rule added: {0} (local subnet only)" -f $ruleName) -ForegroundColor Green

$arg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', ('"{0}"' -f $ScriptPath), '-ConfigPath', ('"{0}"' -f $ConfigPath)) -join ' '

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
# At startup + repeat every 5 min for self-heal (mutex prevents duplicate instances).
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = 'PT0S'   # no time limit (runs continuously)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Installed SYSTEM task: {0}" -f $TaskName) -ForegroundColor Green
Write-Host ("  runs: powershell.exe {0}" -f $arg) -ForegroundColor DarkGray

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started now. Set the console's Customized upload to this PC (README_weather_listener.md), then run weather_listener.ps1 -Status." -ForegroundColor Cyan
}
