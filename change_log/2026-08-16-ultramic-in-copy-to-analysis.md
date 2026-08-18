# 2026-08-16 — copy_to_analysis.ps1 gains UltraMic audio (MIC01 + MIC02)

## What
`copy_to_analysis.ps1` now copies every `MIC*` folder under `E:\ultramic_record`
(new `[UltraMic audio]` section between thermal and WISER; new `-SkipAudio` /
`-UltramicRoot` params). Audio uses the same rules as video: closed files only
(`*_to_*`), per-date filters from `-Date` (wav + flac patterns), `-IncludeActive`
override, copy-only robocopy with the /MIR-/MOV-/PURGE hard block. `$UltramicRoot`
added to the "destination must not be a recording drive" guard. Previously the mic
needed a separate hand-written robocopy (as used for the 8/15 copy).

## Verified
Parse clean + live `-DryRun -Date 2026-08-15,2026-08-16` against the real share:
MIC01 lists only the 23 new 8/16 hours (its already-copied 8/15 files skip as
in-sync), MIC02 lists all 7 segments since its 16:29 activation, video/thermal/WISER
sections unchanged, nothing written.

## Mirror
Copy mirrored to `Field_2026_Social\reolink_record\copy_to_analysis.ps1` (hashes match).
