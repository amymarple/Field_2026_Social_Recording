# -*- coding: utf-8 -*-
r"""Recover an Atom 2 video that was never finalised ("moov atom not found", e.g. PTSC_0018 of 2026-10-02: the
recording stopped without its index). The mdat is intact and self-describing: after ftyp (24 B), the 64-bit mdat
header (16 B), a 'camb' box (80 B) and a 'ptmt' box (40 B incl. its first frame header), every video frame is
    20-byte header (u32 1, u32 key flag, u32 0, u32 clock, u32 frame size) + the frame (AVCC: u32 length + NAL ...)
(layout read off PTSC_0017, whose index ffprobe confirms: the header's size field equals each packet's size).
The camera writes in 20 MiB chunks of ~2 s: after a chunk's last frame comes zero padding up to the next 20 MiB
boundary, which opens with a small per-chunk sample-table box (u32 size, 'tbgp'); the frames continue after it.
SPS / PPS travel in-band with every key frame, so the frames rewritten as an Annex-B H.264 stream and remuxed by
ffmpeg at 30000/1001 fps play as the original. The source file is only read.

Usage: python drone_recover_mp4.py <broken.MP4> <out.mp4> [--fps 30000/1001]
"""
import sys, struct, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                          # noqa: E402

args = sys.argv[1:]
SRC, OUT = Path(args[0]), Path(args[1])
FPS = args[args.index("--fps") + 1] if "--fps" in args else "30000/1001"
START_CODE = bytes([0, 0, 0, 1])
START, CHUNK = 24 + 16 + 80 + 30, 20 << 20                               # first 20-byte frame header (offset 150); chunk size
n = keys = bad = chunks = 0
with open(SRC, "rb") as f, tempfile.NamedTemporaryFile(suffix=".h264", dir=OUT.parent, delete=False) as es:
    size = f.seek(0, 2); f.seek(START); end = START
    while f.tell() + 20 <= size:
        h = f.read(20)
        one, key, zero, clock, fs = struct.unpack(">5I", h)
        if one != 1 or zero != 0 or fs <= 4 or f.tell() + fs > size:   # end of a chunk: jump to the next 20 MiB boundary
            nxt = (f.tell() - 20) // CHUNK * CHUNK + CHUNK
            if nxt + 8 > size:
                break
            f.seek(nxt); bs, typ = struct.unpack(">I4s", f.read(8))
            if typ != b"tbgp" or not 8 < bs < 1 << 16:
                break                                                    # nothing more was written
            f.seek(nxt + bs); chunks += 1; continue
        frame = f.read(fs); p = 0; ok = True; nal = []
        while p + 4 <= fs:
            ln = struct.unpack(">I", frame[p:p + 4])[0]
            if ln == 0 or p + 4 + ln > fs or frame[p + 4] & 0x80:
                ok = False; break
            nal.append(frame[p + 4:p + 4 + ln]); p += 4 + ln
        if not ok or p != fs:
            bad += 1; continue
        es.write(b"".join(START_CODE + x for x in nal))
        n += 1; keys += key; end = f.tell()
    tail = size - end
print(f"{SRC.name}: {n} frames ({keys} key) in {chunks + 1} chunks, {bad} malformed skipped, {tail} bytes after the last whole frame")
subprocess.run([qc_paths.FFMPEG, "-v", "error", "-y", "-r", FPS, "-i", es.name, "-c", "copy", str(OUT)], check=True)
Path(es.name).unlink()
print("->", OUT)
