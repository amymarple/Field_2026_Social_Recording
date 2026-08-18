# 2026-08-09 — Wake-on-LAN sender for the field mini PC

## What

Added `wake_on_lan.ps1` at the repo root: broadcasts standard WoL magic packets
(6 x 0xFF + 16 x MAC, UDP 9 and 7) from **every** active IPv4 interface on the
recording PC (main LAN `.159`, IP Camera NIC `.20`, analysis link `192.168.50.1`),
to both 255.255.255.255 and each subnet broadcast. Default target is the field
mini PC's wired NIC:

```
MAC 68-1D-EF-44-8A-7B
```

## Why

Remote-access chain: RustDesk (host = this recording PC, installed as service
2026-08-09) → run `wake_on_lan.ps1` → mini PC powers up → RustDesk into the
mini PC. Lets the mini PC sleep/shut down between uses instead of running 24/7.

## Usage

```
powershell -NoProfile -ExecutionPolicy Bypass -File wake_on_lan.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File wake_on_lan.ps1 -WaitFor 192.168.1.40
```

(`-WaitFor` pings the given IP for up to 60 s to confirm the wake; useful once
the mini PC's wired NIC has its planned static IP `192.168.1.40`.)

## Target-side requirements (mini PC — not yet confirmed done)

- NIC driver: "Wake on Magic Packet" enabled + Power Management "allow this
  device to wake" / "only magic packet".
- Windows Fast Startup OFF (required for wake-from-shutdown).
- BIOS: Wake on LAN / Power On By Onboard LAN enabled.
- Ethernet link LED must stay lit while the machine is off — that's the tell
  the NIC is powered and listening.

## Notes

- WoL is L2 broadcast: works only from inside the LAN, which is fine — the
  sender is this always-on recording PC, reached via RustDesk.
- Sender verified 2026-08-09 (packets sent from all 3 interfaces). Full
  wake cycle NOT yet verified — target MAC was not present on the LAN during
  the test (mini PC off or wired NIC not connected/armed).
