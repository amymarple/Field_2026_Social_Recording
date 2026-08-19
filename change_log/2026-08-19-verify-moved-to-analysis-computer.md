# 2026-08-19 — Verification moved OFF the field PC entirely

## Why
The field-side `-Verify` (SHA-256 both sides from this PC) starved the recorders:
its hash workers read E: at ~80 MB/s and tonight's 02:03-03:15 all-channel video
instability was exactly that (see incident_log correction entry). Per user
decision: verification now runs ON the analysis computer only.

## Changes
- `copy_to_analysis.ps1`: `-Verify` + repair machinery REMOVED. In its place, every
  non-dry run writes `copy_manifest_<date>.csv` (dest-relative path + source size)
  to the destination root - **directory metadata only, zero content reads on E:**,
  safe while recording - and refreshes `verify_on_analysis.ps1` at the dest root so
  the analysis machine always has the current verifier.
- NEW `verify_on_analysis.ps1` (repo + auto-dropped at dest): standalone PS 5.1,
  runs on the analysis computer against its LOCAL copy tree. Checks per file:
  (1) manifest presence + size -> ERROR = copy problem (re-run the field copy;
  it self-heals); (2) actual media duration vs the duration encoded in the
  filename (`_to_` span): WAV via native RIFF/RF64 header parse (no tools needed),
  MP4 via auto-detected ffprobe (skipped with notice if absent). Duration shortfall
  = WARNING labeled "recording-side gap, not a copy error" (a faithfully-copied
  gappy segment is the source's fault). Manifest entries missing locally = ERROR.
  Exit 0/1/2 per repo convention.

## Verified live
Field side: audio-only 8/15 run wrote a 13-entry manifest + dropped the verifier at
`\\192.168.50.2\audio_in`. Analysis side (executed from the share): 13/13 manifest
size checks pass; flagged exactly the 2 genuinely-short mic fragments from the 8/15
re-plug window as warnings (true positives, correctly classified); 11 clean hourly
files pass; exit 1 (warnings only).

## Usage (on the analysis computer)
    powershell -ExecutionPolicy Bypass -File <localpath>\verify_on_analysis.ps1 -Root <local audio_in folder> -Date 2026-08-17

Mirrored to `Field_2026_Social\reolink_record\`.

## Addendum (2026-08-19 PM): nvr_rescue is now a copy modality
`copy_to_analysis.ps1` mirrors `E:\nvr_rescue\` -> `<Dest>\nvr_rescue\` on every run
(additive, like WISER; `-SkipRescue` to omit; rescue root added to the dest-drive
guard). Prompted by the 2026-08-19 rescue footage existing only on E: - rescued data
must never be single-copy. First backup of the 37-file/29 GB tree ran the same day.
