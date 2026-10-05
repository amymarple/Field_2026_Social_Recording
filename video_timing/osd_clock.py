# -*- coding: utf-8 -*-
r"""Frame index -> the camera's own burned-in OSD clock, per hourly video file (step S1 of the analysis repo's
implementation_plan/2026-10-05-video-clock-sync.md).

Why: the RTSP recordings (rtsp_record.ps1: -use_wallclock_as_timestamps 1, -reset_timestamps 1) store each frame's
ARRIVAL time at the PC, bursty (0.04-0.09 s rms, up to 0.57 s) and reset to 0 in every hourly file whose start is
known only from its name, to 1 s. Every frame also carries the camera's OSD clock (HH:MM:SS); its seconds tick is a
clean clock of that camera (osd_tick_test.py, calibration_qc: one tick per second, none missed). This tool turns each
file into t_osd(i) = c0 + p * i (seconds of the OSD day), so all files of a camera sit on one continuous clock. The
cameras' OSD clocks differ from each other by up to 0.4 s and from the PC by ~59.5 min: the per-camera offset to the
ephys clock is step S2 (analysis repo), not this tool.

How, per file:
  1. frame index <-> stored timestamp from the fragmented MP4's box headers only (moof / traf / tfdt / trun; the
     video payload is skipped) - checked against ffprobe on whole files (--check-index);
  2. N_WIN windows of WIN_S seconds spread over the file, decoded on the GPU (ffmpeg -hwaccel cuda), cropped to the
     OSD time text (per camera, CAMS below; the pano text runs down the stored frame and is turned upright);
  3. every frame's seconds-units digit is recognised (edge-magnitude features, nearest exemplar over +-3 px shifts,
     exemplars in osd_templates.npz, learned with --learn from operator-read windows); a tick = the first frame of a
     new digit that holds for >= 3 frames; the full HH:MM:SS is read per second (majority over its frames) and must
     advance by exactly one second per tick;
  4. t_osd = c0 + p * i fitted to the ticks (each tick at i - 0.5, the change happened between two frames);
     residuals per tick, the fit's offset per window (a dropped / duplicated frame between windows shows as a step
     of ~50 ms), and the camera's apparent PC - OSD offset from the file name (to 1 s; the name is truncated).

Usage:
  python osd_clock.py --learn                                  # build osd_templates.npz from LEARN (below)
  python osd_clock.py --check-read                             # read the sibling cameras' labelled windows
  python osd_clock.py --check-index <file.mp4>                 # box-header index vs ffprobe
  python osd_clock.py --root F:\3rd_rat --dates 2026-09-05[,..] [--cams CH01,..] [--out <dir>] [--jobs 2]
     (default out F:\calibration\video_timing - the lab PC's rule: new outputs under F:\calibration)
Output: <out>\osd_clock_<CAM>.csv (one row per file, appended; files already listed are skipped) and
        <out>\osd_clock_<CAM>_ticks.jsonl (every tick: file, frame index, OSD second, residual).
"""
import sys, os, json, struct, subprocess, csv, time
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
FF = os.environ.get("FFMPEG", r"F:\calibration\bin\ffmpeg.exe")
TEMPLATES = HERE / "osd_templates.npz"
WIN_S, N_WIN, SHIFT, HOLD = 20.0, 5, 3, 3
# per camera: OSD time-text crop in the STORED frame (x0, x1, y0, y1), turn upright, digit cells (x0 of HH MM SS),
# cell width, cell rows, font family (exemplars are per family)
CAMS = {
    "CH01": dict(crop=(1950, 2160, 3700, 4500), rot=True, cells=(87, 154, 254, 323, 423, 490), w=56, y=(37, 124), fam="pano"),
    "CH02": dict(crop=(1950, 2160, 3700, 4500), rot=True, cells=(87, 154, 254, 323, 423, 490), w=56, y=(37, 124), fam="pano"),
    "CH03": dict(crop=(2150, 2700, 20, 150), rot=False, cells=(53, 120, 220, 289, 389, 456), w=56, y=(17, 104), fam="rlc"),
    "CH04": dict(crop=(2150, 2700, 20, 150), rot=False, cells=(53, 120, 220, 289, 389, 456), w=56, y=(17, 104), fam="rlc"),
    "CH05": dict(crop=(1240, 1530, 5, 75), rot=False, cells=(17, 49, 113, 145, 209, 241), w=28, y=(12, 52), fam="px"),
    "CH06": dict(crop=(1240, 1530, 5, 75), rot=False, cells=(17, 49, 113, 145, 209, 241), w=28, y=(12, 52), fam="px"),
}
# operator-read windows (2026-10-05): file, seek s, the OSD time shown by the window's FIRST frame. The first camera of
# each pair teaches (--learn), the second is the test (--check-read).
LEARN = {
    "CH01": [("CH01|14", 1800, "13:30:09"), ("CH01|04", 1800, "03:30:08")],
    "CH03": [("CH03|14", 1800, "13:30:05"), ("CH03|04", 1800, "03:30:07")],
    "CH05": [("CH05|14", 1800, "13:30:08"), ("CH05|04", 1800, "03:30:06")],
}
CHECK = {"CH02": [("CH02|14", 1800, "13:30:09"), ("CH02|04", 1800, "03:30:08")],
         "CH04": [("CH04|14", 1800, "13:30:07"), ("CH04|04", 1800, "03:30:06")],
         "CH06": [("CH06|14", 1800, "13:30:09"), ("CH06|04", 1800, "03:30:09")]}


def resolve(spec):
    """'CHxx|HH' -> that camera's 2026-09-05 file starting in hour HH (the operator-read windows)."""
    if "|" not in spec:
        return Path(spec)
    cam, hh = spec.split("|")
    return sorted(Path(rf"F:\3rd_rat\2026-09-05\{cam}").glob(f"{cam}_2026-09-05_{hh}-*_to_*.mp4"))[0]


# ---------------------------------------------------------------- frame index from the fragmented MP4's box headers
def _boxes(f, end):
    while f.tell() < end:
        start = f.tell(); hdr = f.read(8)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack(">I4s", hdr)
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
        elif size == 0:
            size = end - start
        yield typ.decode("latin1"), start, size, f.tell()
        f.seek(start + size)


def frame_times(path):
    """stored (arrival) time of every video frame in decode order, s, from moov (timescale, track) + moof/trun."""
    vid, ts, out = None, None, []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        for typ, start, bsize, body in _boxes(f, size):
            if typ == "moov":
                for t2, s2, z2, b2 in _boxes(f, start + bsize):
                    if t2 != "trak":
                        continue
                    tid, scale, hdlr = None, None, None
                    stack = [(s2, z2)]
                    while stack:
                        s3, z3 = stack.pop(); f.seek(s3 + 8)
                        for t4, s4, z4, b4 in _boxes(f, s3 + z3):
                            here = f.tell()
                            if t4 in ("mdia", "minf", "stbl"):
                                stack.append((s4, z4))
                            elif t4 == "tkhd":
                                f.seek(b4); v = f.read(1)[0]; f.seek(b4 + (20 if v == 1 else 12)); tid = struct.unpack(">I", f.read(4))[0]
                            elif t4 == "mdhd":
                                f.seek(b4); v = f.read(1)[0]; f.seek(b4 + (20 if v == 1 else 12)); scale = struct.unpack(">I", f.read(4))[0]
                            elif t4 == "hdlr":
                                f.seek(b4 + 8); hdlr = f.read(4).decode("latin1")
                            f.seek(here)
                    if hdlr == "vide":
                        vid, ts = tid, scale
                f.seek(start + bsize)
            elif typ == "moof":
                for t2, s2, z2, b2 in _boxes(f, start + bsize):
                    if t2 != "traf":
                        continue
                    tid, base, defdur, durs = None, None, None, None
                    for t3, s3, z3, b3 in _boxes(f, s2 + z2):
                        here = f.tell(); f.seek(b3)
                        vf = struct.unpack(">I", f.read(4))[0]; ver, flags = vf >> 24, vf & 0xFFFFFF
                        if t3 == "tfhd":
                            tid = struct.unpack(">I", f.read(4))[0]
                            if flags & 0x1: f.read(8)
                            if flags & 0x2: f.read(4)
                            if flags & 0x8: defdur = struct.unpack(">I", f.read(4))[0]
                        elif t3 == "tfdt":
                            base = struct.unpack(">Q" if ver == 1 else ">I", f.read(8 if ver == 1 else 4))[0]
                        elif t3 == "trun":
                            n = struct.unpack(">I", f.read(4))[0]
                            if flags & 0x1: f.read(4)
                            if flags & 0x4: f.read(4)
                            per = [(0x100, 4), (0x200, 4), (0x400, 4), (0x800, 4)]
                            rec = sum(sz for bit, sz in per if flags & bit)
                            raw = f.read(rec * n); durs = []
                            for k in range(n):
                                o = k * rec
                                durs.append(struct.unpack(">I", raw[o:o + 4])[0] if flags & 0x100 else defdur)
                        f.seek(here)
                    if tid == vid and base is not None and durs is not None:
                        out.append(base + np.concatenate([[0], np.cumsum(durs[:-1])]))
                f.seek(start + bsize)
    if not out:
        return np.zeros(0)
    t = np.concatenate(out).astype(np.float64) / ts
    return t


# ---------------------------------------------------------------- OSD crops, features, recognition
def window(path, cam, ss, nframes):
    c = CAMS[cam]; x0, x1, y0, y1 = c["crop"]; w, h = x1 - x0, y1 - y0
    raw = subprocess.run([FF, "-v", "error", "-hwaccel", "cuda", "-ss", f"{ss:.3f}", "-i", str(path), "-frames:v", str(nframes),
                          "-map", "0:v:0", "-fps_mode", "passthrough", "-vf", f"crop={w}:{h}:{x0}:{y0},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8)[: (len(raw) // (w * h)) * w * h].reshape(-1, h, w)
    return np.ascontiguousarray(np.rot90(fr, 1, axes=(1, 2))) if c["rot"] else fr


def feat(g):
    """two channels: the glyph's white core and its dark outline - one of them carries the shape on any background
    (white text on a white wall leaves the outline; on dark grass the core)."""
    return np.stack([(g > 210), (g < 60)]).astype(np.float32)


def ticks(fr, cam):
    """first frame of each new second: the units-of-seconds cell changes (both channels), at most one per 0.6 s."""
    F = np.stack([feat(c) for c in cell(fr, cam, 5, pad=0)])
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2, 3))
    thr = max(0.02, 6 * float(np.median(d)))
    out = []
    for i in np.where(d > thr)[0] + 1:
        if not out or i - out[-1] >= 12:
            out.append(int(i))
    return out


def cell(fr, cam, k, pad=SHIFT):
    c = CAMS[cam]; x = c["cells"][k]; y0, y1 = c["y"]
    return fr[:, max(0, y0 - pad):y1 + pad, max(0, x - pad):x + c["w"] + pad]


def _norm(a):
    """zero mean, unit norm per sample over (channel, row, column)."""
    a = a - a.mean(axis=(-3, -2, -1), keepdims=True)
    return a / (np.linalg.norm(a.reshape(*a.shape[:-3], -1), axis=-1)[..., None, None, None] + 1e-6)


_EX = None


def exemplars(fam):
    global _EX
    if _EX is None:
        z = np.load(TEMPLATES)
        _EX = {k: z[k] for k in z.files}
    return _EX[fam + "_x"], _EX[fam + "_y"]


def classify(cells, cam):
    """cells: (n, h + 2 SHIFT, w + 2 SHIFT) grey -> digit and margin per frame (nearest exemplar over shifts)."""
    X, Y = exemplars(CAMS[cam]["fam"]); n = len(cells); h, w = X.shape[2:]
    F = np.stack([feat(c) for c in cells])                               # (n, 2, H, W)
    best = np.full((n, 10), -2.0)
    Xn = _norm(X).reshape(len(X), -1)
    for dy in range(0, F.shape[2] - h + 1):
        for dx in range(0, F.shape[3] - w + 1):
            P = _norm(F[:, :, dy:dy + h, dx:dx + w]).reshape(n, -1)
            S = P @ Xn.T                                                 # (n, n_exemplars)
            for d in range(10):
                m = Y == d
                if m.any():
                    best[:, d] = np.maximum(best[:, d], S[:, m].max(1))
    o = np.sort(best, 1)
    return best.argmax(1), o[:, -1] - o[:, -2]


def read_hms(fr, cam):
    """HH:MM:SS (seconds of day) from a few frames of one second, or None."""
    digs = []
    for p in range(6):
        d, _ = classify(cell(fr, cam, p), cam)
        digs.append(int(np.bincount(d, minlength=10).argmax()))
    hh, mm, ss = 10 * digs[0] + digs[1], 10 * digs[2] + digs[3], 10 * digs[4] + digs[5]
    return 3600 * hh + 60 * mm + ss if hh < 24 and mm < 60 and ss < 60 else None


def read_window(fr, cam, fps=20.0):
    """-> ([(tick frame, seconds of day)], agreement): ticks by change detection, each tick's second counted from the
    frame spacing (a missed tick does not shift the count), the window's second = the median over its ticks of
    (read value - count); agreement = the fraction of reads equal to that."""
    T = ticks(fr, cam)
    if len(T) < 3:
        return [], 0.0
    K = [int(round((t - T[0]) / fps)) for t in T]
    off = []
    for t, k in zip(T, K):
        pick = [i for i in (t + 2, t + 5, t + 8) if i < len(fr)]
        v = read_hms(fr[pick], cam) if pick else None
        if v is not None:
            off.append(v - k)
    if not off:
        return [(t, None) for t in T], 0.0
    c = int(np.median(off)); agree = float(np.mean(np.array(off) == c)) * len(off) / len(T)
    return [(t, c + k) for t, k in zip(T, K)], agree


# ---------------------------------------------------------------- template learning and the reading check
def learn():
    X, Y, fams = {}, {}, {}
    for cam, wins in LEARN.items():
        fam = CAMS[cam]["fam"]
        for spec, ss, first in wins:
            fr = window(resolve(spec), cam, ss, int(WIN_S * 20))
            T = ticks(fr, cam); K = [int(round((t - T[0]) / 20.0)) for t in T]
            h0, m0, s0 = (int(x) for x in first.split(":")); t0 = 3600 * h0 + 60 * m0 + s0
            segs = [(0, T[0], t0)] + [(t, (T[j + 1] if j + 1 < len(T) else len(fr)), t0 + 1 + k) for j, (t, k) in enumerate(zip(T, K))]
            for a, b, v in segs:                                         # every digit position of a known second
                hh, mm, sc = v // 3600, (v // 60) % 60, v % 60
                digs = (hh // 10, hh % 10, mm // 10, mm % 10, sc // 10, sc % 10)
                for i in range(a + 2, b - 2, 4):
                    for p, dg in enumerate(digs):
                        X.setdefault(fam, []).append(feat(cell(fr[i:i + 1], cam, p, pad=0)[0])); Y.setdefault(fam, []).append(dg)
        print(cam, fam, "exemplars", len(Y[fam]), "digits", sorted(set(Y[fam])))
    for fam in list(X):                                                  # at most 16 per digit, evenly spread
        xs, ys = np.array(X[fam]), np.array(Y[fam]); keep = []
        for d in range(10):
            idx = np.where(ys == d)[0]
            keep += list(idx[np.linspace(0, len(idx) - 1, min(16, len(idx))).astype(int)]) if len(idx) else []
        X[fam], Y[fam] = list(xs[keep]), list(ys[keep])
    np.savez_compressed(TEMPLATES, **{f"{k}_x": np.array(v, np.float32) for k, v in X.items()}, **{f"{k}_y": np.array(v) for k, v in Y.items()})
    print("->", TEMPLATES)


def check_read():
    for cam, wins in CHECK.items():
        for spec, ss, first in wins:
            fr = window(resolve(spec), cam, ss, int(WIN_S * 20))
            r, agree = read_window(fr, cam)
            h, m, s = (int(x) for x in first.split(":")); t0 = 3600 * h + 60 * m + s
            T = [a for a, _ in r]
            want = [t0 + 1 + int(round((a - T[0]) / 20.0)) for a in T] if T else []   # the first tick ends the first frame's second
            ok = sum(v == w_ for (_, v), w_ in zip(r, want))
            gaps = np.diff(T) if len(T) > 1 else []
            print(f"{cam} {spec}: {len(r)} ticks (spacing {min(gaps) if len(gaps) else '-'}-{max(gaps) if len(gaps) else '-'} frames), "
                  f"single reads agree {agree:.2f}; window time {'CORRECT' if ok == len(r) and r else 'WRONG'} ({ok}/{len(r)})")


# ---------------------------------------------------------------- one file
def process(path, cam):
    t = frame_times(path); n = len(t)
    if n < 200:
        return None, []
    dur = t[-1]
    starts = np.linspace(2.0, max(2.0, dur - WIN_S - 2.0), N_WIN)
    tk, agrees = [], []
    for w, ss in enumerate(starts):
        i0 = int(np.searchsorted(t, ss - 1e-6))
        fr = window(path, cam, ss, int(WIN_S * 20))
        got, agree = read_window(fr, cam); agrees.append(agree)
        for a, v in got:                                                 # a window whose digits are not agreed on gives no time
            tk.append((w, i0 + a, v if agree >= 0.5 else None))
    good = [(w, i, v) for w, i, v in tk if v is not None]
    row = dict(camera=cam, file=Path(path).name, n_frames=n, stored_dur_s=round(float(dur), 3), n_windows=N_WIN,
               n_ticks=len(tk), n_read=len(good), read_agreement=";".join(f"{x:.2f}" for x in agrees))
    if len(good) < 10:
        row["status"] = "too few readable ticks"; return row, tk
    W = np.array([g[0] for g in good]); I = np.array([g[1] for g in good], float) - 0.5; V = np.array([g[2] for g in good], float)
    V = V + 86400 * (V < V[0] - 43200)                                   # midnight inside the file
    keep = np.ones(len(V), bool)
    for lim in (0.5, 0.5, 0.1, 0.1):                                     # robust line: misreads (> 0.5 s), then late / false
        A = np.c_[np.ones(keep.sum()), I[keep]]; c0, p = np.linalg.lstsq(A, V[keep], rcond=None)[0]   # ticks (> 2 frames)
        r = V - (c0 + p * I); keep = np.abs(r) < lim
    A = np.c_[np.ones(keep.sum()), I[keep]]; c0, p = np.linalg.lstsq(A, V[keep], rcond=None)[0]; r = (V - (c0 + p * I)) * 1000
    woff = [float(np.median(r[keep & (W == w)])) for w in range(N_WIN) if (keep & (W == w)).any()]
    # the file name's start (PC, truncated to 1 s) minus the OSD time of frame 0: the PC - OSD offset, to [0, 1) s
    stem = Path(path).stem.split("_"); hh, mm, ss_ = (int(x) for x in stem[2].split("-"))
    row.update(c0_osd_s=round(float(c0), 4), osd_frame0=time.strftime("%H:%M:%S", time.gmtime(c0 % 86400)) + f".{int((c0 % 1) * 1000):03d}",
               s_per_frame=round(float(p), 9), fps_osd=round(1.0 / p, 5), fps_stored=round((n - 1) / dur, 5),
               resid_rms_ms=round(float(np.sqrt(np.mean(r[keep] ** 2))), 1), resid_p90_ms=round(float(np.percentile(np.abs(r[keep]), 90)), 1),
               misreads=int((~keep).sum()), window_offsets_ms=";".join(f"{x:+.0f}" for x in woff),
               window_step_max_ms=round(float(np.max(np.abs(np.diff(woff)))) if len(woff) > 1 else 0.0, 1),
               pc_name_minus_osd_s=round(float(3600 * hh + 60 * mm + ss_ - c0), 3),
               status="ok" if (~keep).sum() <= 0.05 * len(V) and np.sqrt(np.mean(r[keep] ** 2)) < 40 else "check")
    return row, [(int(i + 0.5), float(v), round(float(x), 1)) for (i, v, x) in zip(I, V, r)]


def run(root, dates, cams, outdir, jobs):
    outdir.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor
    for cam in cams:
        csvp = outdir / f"osd_clock_{cam}.csv"; done = set()
        if csvp.exists():
            done = {r["file"] for r in csv.DictReader(open(csvp, encoding="utf-8"))}
        files = [f for d in dates for f in sorted((Path(root) / d / cam).glob(f"{cam}_*_to_*.mp4")) if f.name not in done]
        print(cam, len(files), "files to do", flush=True)

        def one(f):
            t0 = time.time()
            try:
                row, ticks = process(f, cam)
            except Exception as e:                                       # a broken file is reported, never fatal
                row, ticks = dict(camera=cam, file=f.name, status=f"error: {e}"), []
            return f, row, ticks, time.time() - t0
        with ThreadPoolExecutor(jobs) as ex:
            for f, row, ticks, dt in ex.map(one, files):
                if row is None:
                    continue
                new = not csvp.exists()
                keys = ["camera", "file", "status", "n_frames", "stored_dur_s", "fps_stored", "fps_osd", "s_per_frame", "c0_osd_s",
                        "osd_frame0", "pc_name_minus_osd_s", "n_windows", "n_ticks", "n_read", "misreads", "resid_rms_ms",
                        "resid_p90_ms", "window_offsets_ms", "window_step_max_ms"]
                with open(csvp, "a", newline="", encoding="utf-8") as fo:
                    wr = csv.DictWriter(fo, keys, extrasaction="ignore")
                    if new:
                        wr.writeheader()
                    wr.writerow(row)
                with open(outdir / f"osd_clock_{cam}_ticks.jsonl", "a", encoding="utf-8") as fo:
                    fo.write(json.dumps(dict(file=f.name, ticks=ticks)) + "\n")
                print(f"{cam} {f.name}: {row.get('status')} rms {row.get('resid_rms_ms')} ms, steps {row.get('window_offsets_ms')}, "
                      f"{dt:.0f} s", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if "--learn" in a:
        learn()
    elif "--check-read" in a:
        check_read()
    elif "--check-index" in a:
        p = Path(opt("--check-index")); t = frame_times(p)
        FP = str(Path(FF).with_name("ffprobe.exe"))
        q = np.array([float(x) for x in subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                                                        "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.split()])
        print(f"box headers {len(t)} frames, ffprobe {len(q)}; max |difference| {np.max(np.abs(t - q)) * 1000 if len(t) == len(q) else float('nan'):.3f} ms")
    else:
        root = opt("--root", r"F:\3rd_rat"); dates = opt("--dates").split(",")
        cams = opt("--cams", ",".join(CAMS)).split(","); out = Path(opt("--out", r"F:\calibration\video_timing"))
        run(root, dates, cams, out, int(opt("--jobs", "2")))
