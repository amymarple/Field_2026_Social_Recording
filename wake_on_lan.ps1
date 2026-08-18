<#
.SYNOPSIS
    Send Wake-on-LAN magic packets to wake a machine on the local network.

.DESCRIPTION
    Builds the standard WoL magic packet (6 x 0xFF + 16 x target MAC) and
    broadcasts it out of every active IPv4 interface on this PC, to both the
    limited broadcast (255.255.255.255) and each interface's subnet broadcast,
    on UDP ports 9 and 7. Sending from every interface avoids the
    multi-NIC-routing problem on this PC (main LAN / IP Camera / analysis link).

    Default target is the field mini PC's wired NIC (68-1D-EF-44-8A-7B).

    Intended use: RustDesk into this PC, run this script, wait ~30 s, then
    RustDesk into the mini PC.

    The magic packet only works if the target has WoL enabled in BIOS and in
    the NIC driver ("Wake on Magic Packet"), and — for wake-from-shutdown —
    Windows Fast Startup turned off. See README/change_log.

.PARAMETER Mac
    Target MAC address. Accepts 68-1D-EF-44-8A-7B, 68:1D:EF:44:8A:7B or
    681DEF448A7B.

.PARAMETER Count
    How many rounds of packets to send (default 3, spaced 1 s apart).

.PARAMETER WaitFor
    Optional IP to ping after sending, to confirm the target woke up
    (e.g. 192.168.1.40 if the mini PC wired NIC is set static). Pings for up
    to ~60 s.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File wake_on_lan.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File wake_on_lan.ps1 -WaitFor 192.168.1.40
#>
param(
    [string]$Mac = '68-1D-EF-44-8A-7B',
    [int]$Count = 3,
    [string]$WaitFor = ''
)

$ErrorActionPreference = 'Stop'

# --- parse MAC -> 6 bytes ---
$clean = ($Mac -replace '[^0-9A-Fa-f]', '')
if ($clean.Length -ne 12) { Write-Host "Bad MAC '$Mac' (need 12 hex digits)" -ForegroundColor Red; exit 2 }
$macBytes = New-Object byte[] 6
for ($i = 0; $i -lt 6; $i++) { $macBytes[$i] = [Convert]::ToByte($clean.Substring($i * 2, 2), 16) }

# --- magic packet: 6 x 0xFF then MAC x 16 ---
$packet = New-Object byte[] 102
for ($i = 0; $i -lt 6; $i++) { $packet[$i] = 0xFF }
for ($r = 0; $r -lt 16; $r++) { [Array]::Copy($macBytes, 0, $packet, 6 + $r * 6, 6) }

# --- collect local IPv4 interfaces to send from (skip loopback/APIPA) ---
$srcIps = @(
    [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
    Where-Object { $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -ne 'Loopback' } |
    ForEach-Object { $_.GetIPProperties().UnicastAddresses } |
    Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' -and -not $_.Address.ToString().StartsWith('169.254.') } |
    ForEach-Object {
        $ip   = $_.Address
        $mask = $_.IPv4Mask
        $ipB  = $ip.GetAddressBytes(); $mB = $mask.GetAddressBytes()
        $bc   = New-Object byte[] 4
        for ($i = 0; $i -lt 4; $i++) { $bc[$i] = $ipB[$i] -bor (-bnot $mB[$i] -band 0xFF) }
        [pscustomobject]@{ Ip = $ip; SubnetBroadcast = ([System.Net.IPAddress]$bc) }
    }
)
if ($srcIps.Count -eq 0) { Write-Host 'No active IPv4 interfaces found.' -ForegroundColor Red; exit 2 }

$macPretty = ($clean -split '(..)' | Where-Object { $_ }) -join '-'
Write-Host "Waking $macPretty ..." -ForegroundColor Cyan

for ($round = 1; $round -le $Count; $round++) {
    foreach ($src in $srcIps) {
        foreach ($destIp in @([System.Net.IPAddress]::Broadcast, $src.SubnetBroadcast)) {
            foreach ($port in 9, 7) {
                try {
                    $udp = New-Object System.Net.Sockets.UdpClient(
                        (New-Object System.Net.IPEndPoint($src.Ip, 0)))
                    $udp.EnableBroadcast = $true
                    [void]$udp.Send($packet, $packet.Length,
                        (New-Object System.Net.IPEndPoint($destIp, $port)))
                    $udp.Close()
                } catch {
                    Write-Host "  send failed from $($src.Ip) to ${destIp}:${port} : $_" -ForegroundColor Yellow
                }
            }
        }
        Write-Host "  round ${round}: sent from $($src.Ip) (bcast $($src.SubnetBroadcast))"
    }
    if ($round -lt $Count) { Start-Sleep -Seconds 1 }
}
Write-Host 'Magic packets sent.' -ForegroundColor Green

# --- optional wake confirmation ---
if ($WaitFor) {
    Write-Host "Waiting for $WaitFor to answer ping (up to 60 s) ..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Test-Connection -ComputerName $WaitFor -Count 1 -Quiet) {
            Write-Host "$WaitFor is up." -ForegroundColor Green; exit 0
        }
        Start-Sleep -Seconds 3
    }
    Write-Host "$WaitFor did not respond within 60 s (it may still be booting, or WoL is not armed on the target)." -ForegroundColor Yellow
    exit 1
}
exit 0
