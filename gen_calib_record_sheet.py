# -*- coding: utf-8 -*-
"""Generate the printable CH01/02 calibration record sheet (stakeout map + log tables).

Field coordinates on the sheet are in INCHES (operator rule 2026-09-18: the field is
natively imperial - 40x20 ft, 10-ft pole grid, WISER reports inches, US tapes).
The analysis pipeline converts x2.54 to cm. The ChArUco board itself stays metric
(60 mm print pitch). Only cross-width cords are used: each cord fixes x via its two
wall-end marks, and pre-taped flags along the cord give y - length-wise cords would
add no information.
"""
import io

FIELD_X, FIELD_Y = 480.0, 240.0            # inches (40 x 20 ft)
TRAIN_X = [24, 96, 168, 240, 312, 384, 456]   # 7 cords: 2 ft margins, 6 ft apart
TRAIN_Y = [12, 66, 120, 174, 228]             # flags: 1 ft margins, 54 in apart
VT_X = [60, 132, 204, 276, 348, 420]          # interleaved cords (midpoints)
VT_Y = [39, 93, 147, 201]                     # interleaved flags (midpoints)
POLES = {  # name -> (x, y) inches; 10-ft grid, exact by design
    **{f"A{i}": (i * 120.0, 0.0) for i in range(5)},
    **{f"B{i}": (i * 120.0, 120.0) for i in range(5)},
    **{f"C{i}": (i * 120.0, 240.0) for i in range(5)},
}
SHELTERS = [  # (cx, cy, w, h) inches; footprint 18 x 24-5/8 in, long axis along y
    (134.9, 120.0, 18.0, 24.63),
    (347.0, 119.1, 18.0, 24.63),
]
CAMS = [("CH01", 236.1, 58.5, +1), ("CH02", 249.1, 180.9, -1)]  # aim ~ +y / -y

stations = []  # (id, set, x, y)
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1):
        stations.append((f"T{li}{si}", "TRAIN", x, y))
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1):
        s = "VAL" if (i + j) % 2 == 0 else "TEST"
        stations.append((f"{'V' if s=='VAL' else 'F'}{i}{j}", s, x, y))

n_train = sum(1 for s in stations if s[1] == "TRAIN")
n_val = sum(1 for s in stations if s[1] == "VAL")
n_tst = sum(1 for s in stations if s[1] == "TEST")
assert (n_train, n_val, n_tst) == (35, 12, 12), (n_train, n_val, n_tst)

# ---------------- SVG stakeout map (drawn at 2.54 units/inch; y axis flipped) -------
K = 2.54
M = 46  # margin, drawing units
W, H = FIELD_X * K + 2 * M, FIELD_Y * K + 2 * M
def sx(x): return M + x * K
def sy(y): return M + (FIELD_Y - y) * K

svg = io.StringIO()
svg.write(f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" '
          f'font-family="Arial, sans-serif">\n')
svg.write(f'<rect x="{sx(0)}" y="{sy(FIELD_Y)}" width="{FIELD_X*K}" height="{FIELD_Y*K}" '
          f'fill="none" stroke="#000" stroke-width="2.5"/>\n')
# training cords (cross-width lines)
for x in TRAIN_X:
    svg.write(f'<line x1="{sx(x)}" y1="{sy(0)}" x2="{sx(x)}" y2="{sy(FIELD_Y)}" '
              f'stroke="#999" stroke-width="0.8" stroke-dasharray="6 5"/>\n')
    svg.write(f'<text x="{sx(x)}" y="{sy(0)+16}" font-size="12" text-anchor="middle">x={x}"</text>\n')
# y flag values on left edge
for y in TRAIN_Y + VT_Y:
    svg.write(f'<text x="{sx(0)-6}" y="{sy(y)+4}" font-size="12" text-anchor="end">{y}</text>\n')
# poles
for name, (x, y) in POLES.items():
    svg.write(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="5.5" fill="#000"/>\n')
    dy = -9 if y < FIELD_Y else 18
    svg.write(f'<text x="{sx(x)}" y="{sy(y)+dy}" font-size="14" font-weight="bold" text-anchor="middle">{name}</text>\n')
# shelters
for cx, cy, w, h in SHELTERS:
    svg.write(f'<rect x="{sx(cx)-w*K/2}" y="{sy(cy)-h*K/2}" width="{w*K}" height="{h*K}" '
              f'fill="none" stroke="#000" stroke-width="1.5"/>\n')
    svg.write(f'<text x="{sx(cx)}" y="{sy(cy)+4}" font-size="9" text-anchor="middle">box</text>\n')
# cameras + approximate seam trace
for name, x, y, dirn in CAMS:
    svg.write(f'<rect x="{sx(x)-7}" y="{sy(y)-7}" width="14" height="14" fill="#000" '
              f'transform="rotate(45 {sx(x)} {sy(y)})"/>\n')
    svg.write(f'<text x="{sx(x)+12}" y="{sy(y)+4}" font-size="13" font-weight="bold">{name}</text>\n')
    y2 = FIELD_Y if dirn > 0 else 0
    svg.write(f'<line x1="{sx(x)}" y1="{sy(y)}" x2="{sx(x)}" y2="{sy(y2)}" '
              f'stroke="#000" stroke-width="0.8" stroke-dasharray="2 4"/>\n')
# stations
for sid, st, x, y in stations:
    X, Y = sx(x), sy(y)
    if st == "TRAIN":
        svg.write(f'<rect x="{X-5}" y="{Y-5}" width="10" height="10" fill="#000"/>\n')
        lab_dy = -8
    elif st == "VAL":
        svg.write(f'<circle cx="{X}" cy="{Y}" r="6" fill="#fff" stroke="#000" stroke-width="1.6"/>\n')
        lab_dy = -9
    else:
        svg.write(f'<rect x="{X-6}" y="{Y-6}" width="12" height="12" fill="#fff" stroke="#000" '
                  f'stroke-width="1.6" transform="rotate(45 {X} {Y})"/>\n')
        svg.write(f'<line x1="{X-3.5}" y1="{Y}" x2="{X+3.5}" y2="{Y}" stroke="#000" stroke-width="1.2"/>\n')
        lab_dy = -10
    svg.write(f'<text x="{X}" y="{Y+lab_dy}" font-size="13" font-weight="bold" text-anchor="middle">{sid}</text>\n')
svg.write('</svg>\n')
svg_str = svg.getvalue()

# ---------------- log table rows ----------------
def row(sid, st, x, y):
    tx = f"{x:g}" if x is not None else ""
    ty = f"{y:g}" if y is not None else ""
    return (f'<tr><td class="id">{sid}</td><td>{st}</td><td>{tx}</td><td>{ty}</td>'
            '<td></td><td class="c"></td><td class="c"></td>'
            '<td class="w"></td><td class="note"></td></tr>')

rows = [row(*s[:2], s[2], s[3]) for s in stations]
for i in range(1, 7):
    rows.append(row(f"S{i}", "SEAM*", None, None))
for i in range(1, 7):
    rows.append(row(f"X{i}", "EXTRA", None, None))

def table(rws):
    return ('<table><thead><tr><th>ID</th><th>Set</th><th>Target x (in)</th><th>Target y (in)</th>'
            '<th style="width:120px">On cord @ flag &#10003;</th><th>Held 8-10 s</th>'
            '<th>QC ok</th><th>Measured x,y (moved only)*</th><th>Notes</th></tr></thead><tbody>'
            + "".join(rws) + '</tbody></table>')

# per-cord wall-end measurement table (the construction chain's ONLY tape work)
line_rows = "".join(
    f'<tr><td class="id">L{i}</td><td>{x}</td><td class="w"></td><td class="w"></td>'
    f'<td class="c"></td><td class="note"></td></tr>'
    for i, x in enumerate(TRAIN_X, 1))
vt_note = ", ".join(str(x) for x in VT_X)
line_table = ('<table><thead><tr><th>Cord</th><th>Target x (in)</th><th>Wall-A end: measured x</th>'
              '<th>Wall-C end: measured x</th><th>Taut + flags OK</th><th>Notes</th></tr></thead><tbody>'
              + line_rows + '</tbody></table>'
              f'<div class="foot">VAL/TEST cords (x = {vt_note} in) same method, flags @ 39/93/147/201 in. '
              'Cords stay down all session (straightness validation); cones weight the ends. '
              'NO length-wise cords - the flags on the cross cords already carry y.</div>')

# survey page: poles + cameras (the real tape-measure work)
pole_rows = "".join(
    f'<tr><td class="id">{n}</td><td>{p[0]:g}</td><td>{p[1]:g}</td>'
    f'<td class="w"></td><td class="w"></td><td class="note"></td></tr>'
    for n, p in sorted(POLES.items()))
pole_table = ('<table><thead><tr><th>Pole</th><th>Design x (in)</th><th>Design y (in)</th>'
              '<th>Measured x</th><th>Measured y</th><th>Notes</th></tr></thead><tbody>'
              + pole_rows + '</tbody></table>')
cam_rows = "".join(
    f'<tr><td class="id">CH0{i}</td><td class="note"></td><td class="w"></td><td class="w"></td>'
    f'<td class="w"></td><td class="note"></td></tr>' for i in range(1, 7))
cam_table = ('<table><thead><tr><th>Channel</th><th>Mount description (pole/wall)</th><th>Measured x</th>'
             '<th>Measured y</th><th>Lens height (in)</th><th>Aim / notes</th></tr></thead><tbody>'
             + cam_rows + '</tbody></table>')

# split rows across pages: 36 / rest
t1, t2 = table(rows[:36]), table(rows[36:])

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>CH01/02 Calibration Record Sheet</title>
<style>
 @page {{ size: letter landscape; margin: 9mm; }}
 body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 0; color: #000; }}
 .page {{ page-break-after: always; }}
 h1 {{ font-size: 17px; margin: 2px 0 4px; }}
 h2 {{ font-size: 13px; margin: 6px 0 3px; }}
 .meta {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px 14px; margin: 4px 0; }}
 .meta div {{ border-bottom: 1px solid #000; padding: 1px 2px; min-height: 15px; }}
 .rules {{ border: 1.5px solid #000; padding: 4px 8px; margin: 5px 0; line-height: 1.45; }}
 .legend span {{ margin-right: 18px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #000; padding: 1px 4px; text-align: center; height: 15.5px; }}
 th {{ background: #ddd; font-size: 10.5px; }}
 td.id {{ font-weight: bold; }}
 td.w {{ min-width: 58px; }}
 td.c {{ width: 44px; }}
 td.note {{ min-width: 150px; }}
 svg {{ width: 100%; height: auto; }}
 .foot {{ font-size: 9.5px; margin-top: 3px; }}
</style></head><body>

<div class="page">
 <h1>CH01/CH02 Calibration - Stakeout Map &nbsp;<span style="font-weight:normal;font-size:12px">
 (PLAN_CH01_CH02_pano_ground_map.md v2 &middot; board: ChArUco 12&times;9 @60 mm, DICT_5X5_100, 72 cm long edge along +x
 &middot; ALL FIELD COORDINATES IN INCHES; pipeline converts &times;2.54 to cm)</span></h1>
 <div class="meta">
  <div>Date:</div><div>Operator:</div><div>Weather / light:</div><div>Phone&minus;PC clock offset: ______ s</div>
  <div>5-square span, x-dir: ____ mm (expect 300)</div><div>y-dir: ____ mm</div><div>Board thickness: ____ mm</div><div>Typical grass height: ____ in</div>
  <div>Field long edge 1: ______ in (expect 480)</div><div>Long edge 2: ______ in</div><div>Diagonal 1: ______ in (expect ~536.7)</div><div>Diagonal 2: ______ in</div>
  <div>Cord height above ground (typ.): ____ in</div><div>Train cords: flags @ 12/66/120/174/228 in pre-taped &#10003;: ___</div><div>VAL/TEST cords: flags @ 39/93/147/201 in pre-taped &#10003;: ___</div><div></div>
 </div>
 {svg_str}
 <div class="legend" style="margin-top:2px">
  <span>&#9632; TRAIN T (35)</span><span>&#9675; VAL V (12)</span><span>&#9671;+ TEST F (12)</span>
  <span>&#9679; pole (A/B/C 0-4)</span><span>&#9670; camera</span><span>&#9482; approx. seam trace (verify on preflight stills)</span>
 </div>
 <div class="rules">
  <b>Stakeout flow (checkbox by default - no per-station taping):</b>
  &#9450; indoors: tape 5 flags on each of the 7 train cords @ 12/66/120/174/228 in, measured from the cord's wall-A
  zero mark under deployment tension (measure once - all cords identical)
  &#9312; on site: tape each cord's x from the corners along BOTH long walls, mark the wall ends (table below)
  &#9313; stretch the cord taut at soil level, wall-A zero mark at the wall face, <b>cones weighting both ends</b>
  &#9314; place the board: <b>54 cm short edge hugging the cord, origin corner at the flag</b>, +x arrow toward the far
  end (A4) &rarr; position + orientation aligned in one motion &rarr; checkbox
  &#9315; only a board that cannot land at its flag (obstruction) gets moved and hand-measured (the * column)
  &#9316; do not block any camera's line of sight to the board (step 2-3 m aside; being in frame is harmless), hold 8-10 s.
  <b>Only cross-width cords are used</b> - flags carry y, so length-wise cords add nothing.
  <b>IDs are paper bookkeeping only</b> (T34 = cord 3, flag 4); no ID marks on the field, cameras never need to see
  them - identification = time + order + position self-consistency.
  <b>Cones:</b> weight cord ends + mark upcoming stations for wayfinding; <u>never a precision datum</u> (a cone base is
  &plusmn;several cm ambiguous).
  <b>Iron rules:</b> exactly ONE board on the field at any time &middot; everything matte, NO retroreflective tape
  (glare / IR blooming kills nearby corner detection) &middot; SEAM rows are placed after checking preflight stills &middot;
  call remote QC after each batch before continuing &middot; before leaving: wait for _to_ closure, verify + back up &middot;
  ground stations serve CH03/04 too (all cameras record together).
 </div>
 <h2 style="margin-top:6px">Cord wall-end measurements (the construction chain's foundation - two numbers per cord)</h2>
 {line_table}
 <h2 style="margin-top:6px">CH03/04 intrinsics sweep (during waits between placement batches)</h2>
 <table>
  <thead><tr><th>Camera</th><th>Start</th><th>End</th><th>Valid poses (target 20-30)</th>
  <th>Frame edges covered?</th><th>QC ok</th><th>Notes</th></tr></thead>
  <tbody>
   <tr><td class="id">CH03</td><td class="w"></td><td class="w"></td><td></td><td class="c"></td><td class="c"></td><td class="note"></td></tr>
   <tr><td class="id">CH04</td><td class="w"></td><td class="w"></td><td></td><td class="c"></td><td class="c"></td><td class="note"></td></tr>
  </tbody>
 </table>
 <div class="foot">Sweep: hand-hold the board in front of the camera varying distance / position / tilt (&plusmn;30-45&deg;),
 holding each pose still 1-2 s; CH03 first &rarr; remote QC confirms detection quality &rarr; then CH04. Avoid sun-glare angles.</div>
</div>

<div class="page">
 <h2>Log 1/2 - TRAIN T11-T75 (35) + start of VAL/TEST</h2>
 {t1}
 <div class="foot">Set rule: V/F alternate in a checkerboard pattern, pre-assigned - never reassign on site; a moved
 station keeps its set, only its coordinates change.</div>
</div>

<div class="page">
 <h2>Log 2/2 - VAL/TEST (cont.) + SEAM S1-S6 + re-shoot/moved X1-X6</h2>
 {t2}
 <div class="foot">* Measured columns only when the board could not land at its flag; "On cord @ flag" checked =
 coordinates are the target values. SEAM rows: locate the actual seam on preflight stills first; one group each
 near / mid / far, sample BOTH sides, coordinates hand-measured. QC ok = remote frame-pull confirmed usable corners.</div>
</div>

<div>
 <h2>Survey (must measure before teardown) - poles &amp; cameras CH01-CH06</h2>
 <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px">
  <div>{pole_table}</div>
  <div>{cam_table}
   <div class="foot" style="margin-top:6px">CH07/08 (in-box) deferred by operator decision; box positions are
   recoverable from video. <b>But interior clear dims + wall thickness are NOT recoverable from video</b> -
   tape-measure the boxes before disposal (keep them after teardown, or measure-then-discard; 5 minutes).</div>
  </div>
 </div>
</div>

</body></html>"""

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CALIB_RECORD_SHEET_CH0102.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("stations:", len(stations), "train/val/test:", n_train, n_val, n_tst)
print("wrote", out)
