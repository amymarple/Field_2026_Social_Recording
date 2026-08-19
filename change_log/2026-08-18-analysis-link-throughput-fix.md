# 2026-08-18 — Analysis-link throughput: 3 stacked causes found, ~20 -> ~60 MB/s

Copies to \\192.168.50.2 (analysis mini PC) ran at ~2-20 MB/s. Measured diagnosis,
in order of discovery:

1. **Traffic bypassed the direct link entirely.** SMB multichannel/IPv6 preferred a
   path via the main-LAN NIC (both machines have LAN presence since the mini PC's
   wake-on-LAN setup; field router hands out IPv6 - the session showed a 2600::/
   pair on port 445) at ~17 MB/s effective, while the dedicated 1 Gbps USB-GbE link
   (192.168.50.1 -> .2, 1 ms ping) idled at 0.
   **Fix (persistent, applied by user, elevated):**
   `New-SmbMultichannelConstraint -ServerName 192.168.50.2 -InterfaceAlias "Ethernet 2"`
2. **robocopy `/Z` (restartable) cost ~3x on writes**: /Z copy 20 MB/s while a
   concurrent plain buffered write did 60 MB/s. `copy_to_analysis.ps1` now defaults
   to non-restartable; new `-Restartable` switch re-enables /Z for flaky links.
   Re-runs still skip completed files, so interruption cost = one in-flight file.
3. Residual ceiling ~60-80 MB/s is SMB signing (`RequireSecuritySignature=True`,
   enterprise-managed - left alone deliberately) + adapter overhead. Good enough:
   ~500 GB/day copies in ~2.5 h; the 6 TB cohort-1 copy ≈ ~28 h.

Ruled out by measurement: source disk (E: reads 144 MB/s during 13-stream recording),
USB attach speed (combined 68+ MB/s duplex through the adapter), link health (1 Gbps,
1 ms, 0 loss). No recording was affected by any of this (0/14 stalled throughout,
including through the user's ethernet reset).

Mirrored to `Field_2026_Social\reolink_record\copy_to_analysis.ps1`.

## Addendum (same day): /XO removed - Ctrl+C-safe re-runs
A mid-file Ctrl+C leaves a partial dest file with a NEWER timestamp than the source;
with `/XO` the next run would skip it forever (silent truncation). `/XO` removed:
robocopy default still skips in-sync ("Same") files but now re-copies partials -
source is the truth. Full size audit of the 8/16 copy at the dest: all files match
source exactly (today's interrupts left no damage). Mirrored to sibling repo.

## Addendum 2 (same day): -Verify switch (SHA-256 + auto-repair)
`copy_to_analysis.ps1 -Verify` hashes every source file in scope (video/thermal/
audio, honoring -Date/-Channels/Skip*) against its destination copy after the
normal copy pass, force-re-copies mismatches (robocopy include-flags IS/IT/IM -
measured: a same-size, same-write-time corrupted file classifies as robocopy
"Modified" and needs IM; IS alone skips it), then re-hashes to confirm. Reads all
bytes on both sides (~doubles a copy's cost) - intended before delete_day and for
archival transfers. End-to-end tested with synthetic trees: truncation heals in
the plain copy phase; metadata-identical bit rot is caught and repaired only by
-Verify ("1 repaired, 0 UNRESOLVED", exit 0). Unrepairable mismatches exit 2.
Mirrored to sibling repo. (Test leftover: D:\_copytest, ~16 MB - delete manually;
the agent sandbox declines to remove top-level D: folders.)

## Addendum 4 (2026-08-19): GENTLE is now the default; -Fast opts into full speed
User decision after the overnight NVR incident: default = 2 robocopy threads +
/IPG pacing (~15-30 MB/s, minimal E: seek pressure while recording; a ~500 GB day
copies overnight). `-Fast` = 8 threads, no pacing (~118 MB/s wire limit, day in
~75 min); explicit -Threads always wins. Measurements showed even full speed never
disturbed capture - the gentle default is deliberate margin, protecting the
irreplaceable night-activity recordings (nocturnal animals; daytime = low-stakes
window, per the rig's existing maintenance-window convention). Verified via dry
runs (banner shows GENTLE/FAST + thread count). Mirrored to sibling repo.

## Addendum 3 (same day): -Verify parallelized (~3-4x faster)
First -Verify implementation hashed each pair sequentially (src read, then dest
pulled back over the link) -> ~4 h per recording day. Now two Start-Job workers
hash ALL source files and ALL destination files concurrently (E: reads overlap the
link pulls; progress printed every 30 s), then hashes are compared from manifests.
Wall-clock ~= the slower side alone: ~1.2 h per ~500 GB day, ~13 h for the 6 TB
cohort-1 set. Detect/force-re-copy/re-hash repair path unchanged and re-tested
(bit-rot synthetic: "1 repaired, 0 UNRESOLVED", exit 0). Mirrored to sibling repo.
