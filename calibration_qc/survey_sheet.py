# -*- coding: utf-8 -*-
r"""The pre-teardown survey sheet (HTML field sheet): poles, houses, wall top, camera mounts, still ball.

    python survey_sheet.py --out <sheet.html>

Why (2026-10-01): every calibration observation so far lies on or near the ground (boards 6 mm, cones 50 mm, the
ball 105 mm), so the fit cannot tell a wrong lens model from a wrong pose or an uneven floor; the per-camera ground
warp absorbs all three on the ground and nowhere else. The operator's rigid landmarks (pole edges on the 09-18
reference frames, analysis repo `cv/configs/landmarks/2026c/`) show it: under the release model the long pole
edges in the panos bend by 5-13 arcmin (4-10 px) and stand 0.5-4 deg off vertical, CH03's corner poles 10-19 deg,
CH04's 4-5 deg. Poles at measured positions with bands at measured heights, the two houses (rigid boxes of
measurable size) and the wall top at measured heights are 3-D points and lines ABOVE the ground that several
cameras see - what a bundle needs to fix the lens models where the ground data cannot. All of it is gone after
the teardown. A still ball needs no clock (`refit_supplement.py --balls`: CH04's clock and position are confounded
on the moving sweep).

Pole design positions: 15 poles on a 10 ft grid (`field_layout.json`): rows A / B / C at y = 0 / 120 / 240 in,
columns 0-4 at x = 0..480 in. Houses: design footprint 24 5/8 x 18 in at (134.9, 120.0) and (347.0, 119.1) in,
long side along y. Which cameras see which pole: the operator's landmark labels (09-18). Camera positions and the
still-ball spots' cameras: the release fit (paddock_map.load()).
Revision 2 (2026-10-02) follows the two independent audits (`<root>\qc\AUDIT_ASTRA_2026-10-02.md`,
`AUDIT_FABLE_2026-10-02.md`): every height against ONE level datum (a floor-height map - the panos turn each cm of
floor error into 2.3-2.5 cm at the far end and no data constrains it), still ball 8-10 s per spot with the far end
first, a +y and a -y pass with stops, a staff with marks at known low heights, a clock event all cameras see, and
an IR <-> colour switch with the scene still; the field steps that need the cameras recording come first.
Revision 3 (2026-10-02): no spot is seen by all six cameras (CH03 / CH04 look at opposite ends, CH05 / CH06 at
their houses), so the clock check is four jumps, each where both panos and one other camera see it; optional,
since the 20 Hz ball already gives the offsets (ball_sync20.py).
The committed sheet is PRETEARDOWN_SURVEY_SHEET_2026-10-01.html in the repository root.
"""
import sys, math
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paddock_map as pm                                                  # noqa: E402

args = sys.argv[1:]
if "--out" not in args:
    raise SystemExit("usage: python survey_sheet.py --out <sheet.html>")
OUT = Path(args[args.index("--out") + 1])

ROWS = {"A": 0, "B": 120, "C": 240}
POLES = {f"{r}{i}": (120 * i, y) for r, y in ROWS.items() for i in range(5)}
SEEN = {"A0": "01 02 03", "A4": "02 04", "B0": "01 02 03", "B1": "01 02", "B2": "01 02", "B3": "01 02",
        "B4": "02 04", "C0": "01 03", "C1": "01"}                       # operator's landmark labels, 09-18
CARRY = {"B1": "CH03", "B2": "CH01, CH02", "B3": "CH04"}                 # nearest pole to each camera in the fit
HOUSES = {"west": dict(c=(134.9, 120.0), cam="CH05", pole="B1", apole="A1"),
          "east": dict(c=(347.0, 119.1), cam="CH06", pole="B3", apole="A3")}
HX, HY = 18.0 / 2, 24.625 / 2                                             # half footprint, x and y (in)

cams = pm.load()
CAM = {c: v.centre / 25.4 for c, v in sorted(cams.items())}


def seen_by(xy, z=105.0):
    return [c[2:] for c, v in sorted(cams.items()) if v.sees(np.array([xy], float), z_mm=z, units="in", margin=40)[0]]


# still-ball spots, in the order to walk them
TICKS = [12, 66, 120, 174, 228]
SPOTS = []
for grp, xs in (("Far end", (456, 420)), ("x = 0 end", (24, 60))):
    for j, x in enumerate(xs):
        for y in (TICKS if j % 2 == 0 else TICKS[::-1]):
            SPOTS.append((grp, x, y))
for name, h in HOUSES.items():
    cx, cy = h['c']
    for side, (x, y) in (("W", (cx - HX - 14, cy)), ("N", (cx, cy + HY + 14)), ("E", (cx + HX + 14, cy)), ("S", (cx, cy - HY - 14))):
        SPOTS.append((f"Around the {name} house", round(x), round(y)))
SPOTS = [(g, x, y, seen_by((x, y))) for g, x, y in SPOTS]
SPOTS = [(f"S{i + 1}", g, x, y, s) for i, (g, x, y, s) in enumerate(t for t in SPOTS if len(t[3]) >= 2)]   # a tie needs two cameras
STAFF = set()
for grp, every in (("Far end", 2), ("x = 0 end", 4)):
    STAFF |= {k for i, (k, g, x, y, s) in enumerate([t for t in SPOTS if t[1] == grp]) if i % every == 0}
STAFF |= {next(k for k, g, x, y, s in SPOTS if g == f"Around the {n} house") for n in HOUSES}


def where(x, y):
    if x == 456:
        return f"on cord T7 at tick y {y}"
    if x == 24:
        return f"on cord T1 at tick y {y}"
    if x == 420:
        return f"half-way T6&ndash;T7 (x 420), level with tick y {y}"
    if x == 60:
        return f"half-way T1&ndash;T2 (x 60), level with tick y {y}"
    return f"x {x}, y {y}: 14 in out from the middle of the house side"


# pole-to-pole network: long lines, row and column neighbours, cell diagonals
PAIRS = [("A0", "A4"), ("C0", "C4"), ("A0", "C0"), ("A4", "C4"), ("A0", "C4"), ("C0", "A4")]
PAIRS += [(f"{r}{i}", f"{r}{i + 1}") for r in "ABC" for i in range(4)]
PAIRS += [(f"{a}{i}", f"{b}{i}") for i in range(5) for a, b in (("A", "B"), ("B", "C"))]
PAIRS += [p for i in range(4) for a, b in (("A", "B"), ("B", "C")) for p in ((f"{a}{i}", f"{b}{i + 1}"), (f"{b}{i}", f"{a}{i + 1}"))]


def nominal(p, q):
    return math.dist(POLES[p], POLES[q])


WALL = []
for r, y in (("A", 0), ("C", 240)):
    for i in range(5):
        WALL.append((f"{r}{i}", 120 * i, y))
        if i < 4:
            WALL.append((f"{r}{i}&ndash;{r}{i + 1}", 120 * i + 60, y))
for x, c in ((0, "0"), (480, "4")):
    WALL += [(f"A{c}&ndash;B{c}", x, 60), (f"B{c}", x, 120), (f"B{c}&ndash;C{c}", x, 180)]


STAFF_TAG = '<div class="tag">staff here too (step 2)</div>'
NONE_TAG, WARN_TAG, FIRST_TAG = '<span class="muted">none</span>', '<div class="warn">carries {}</div>', '<span class="first">first</span>'


def chips(s):
    return "".join(f'<span class="cam">{c}</span>' for c in (s.split() if isinstance(s, str) else s))


def inp(key, ph, label, cls="t"):
    return f'<input class="{cls}" id="{key}" data-k="{key}" type="text" inputmode="decimal" placeholder="{ph}" aria-label="{label}">'


def ck(key, label):
    return f'<input class="ck" type="checkbox" id="{key}" data-k="{key}" aria-label="{label}">'


# ---------------------------------------------------------------- map (paddock inches, y up)
def Y(y):
    return 240 - y


svg = ['<svg viewBox="-46 -30 576 306" role="img" aria-label="Paddock map: poles, houses, cameras, still-ball spots, distance network">',
       '<rect class="pad" x="0" y="0" width="480" height="240"/>']
for p, q in PAIRS:
    (x1, y1), (x2, y2) = POLES[p], POLES[q]
    svg.append(f'<line class="net" x1="{x1}" y1="{Y(y1)}" x2="{x2}" y2="{Y(y2)}"/>')
for name, h in HOUSES.items():
    cx, cy = h['c']
    svg.append(f'<rect class="house" x="{cx - HX:.1f}" y="{Y(cy + HY):.1f}" width="{2 * HX:.1f}" height="{2 * HY:.1f}"/>')
    svg.append(f'<text class="hlab" x="{cx:.1f}" y="{Y(cy) + 3:.1f}" text-anchor="middle">{name}</text>')
for k, g, x, y, s in SPOTS:
    svg.append(f'<circle class="spot" cx="{x}" cy="{Y(y)}" r="3.6"/>')
    svg.append(f'<text class="slab" x="{x + 5}" y="{Y(y) - 4}">{k}</text>')
for p, (x, y) in POLES.items():
    cls = "pole" + ("" if p in SEEN else " survey")
    svg.append(f'<circle class="{cls}" cx="{x}" cy="{Y(y)}" r="5.2"/>')
    ty = Y(y) + (15 if y == 0 else -9)
    svg.append(f'<text class="plab" x="{x}" y="{ty}" text-anchor="middle">{p}</text>')
for c, v in CAM.items():
    x, y = float(v[0]), float(v[1])
    svg.append(f'<path class="camm" d="M{x:.1f},{Y(y) - 4.5:.1f} l4.2,7.5 l-8.4,0 z"/>')
    svg.append(f'<text class="clab" x="{x + 6:.1f}" y="{Y(y) + 7:.1f}">{c}</text>')
svg += ['<text class="wall" x="240" y="-16" text-anchor="middle">y = 240 wall · row C</text>',
        '<text class="wall" x="240" y="272" text-anchor="middle">y = 0 wall · row A</text>',
        '<text class="wall" x="-24" y="120" text-anchor="middle" transform="rotate(-90 -24 120)">x = 0 wall</text>',
        '<text class="wall" x="504" y="120" text-anchor="middle" transform="rotate(90 504 120)">x = 480 wall</text>',
        '</svg>']
svg = "\n".join(svg)

# ---------------------------------------------------------------- tables
band_rows = "".join(
    f'<tr><th scope="row">{p}<span class="xv">x {x}, y {y}</span></th><td>{chips(SEEN.get(p, "")) or NONE_TAG}'
    f'{WARN_TAG.format(CARRY[p]) if p in CARRY else ""}</td>'
    f'<td>{inp(f"pole.{p}.band120", "cm", p + " lower band top edge, cm")}</td><td>{inp(f"pole.{p}.band200", "cm", p + " upper band top edge, cm")}</td>'
    f'<td>{inp(f"pole.{p}.circ", "cm", p + " circumference, cm")}</td><td>{inp(f"pole.{p}.lean_x", "deg", p + " lean toward +x, deg")}</td>'
    f'<td>{inp(f"pole.{p}.lean_y", "deg", p + " lean toward +y, deg")}</td>'
    f'<td>{inp(f"pole.{p}.foot_datum", "cm", p + " ground at the foot vs datum, cm")}</td></tr>'
    for p, (x, y) in POLES.items())
spot_rows, last = [], None
for k, g, x, y, s in SPOTS:
    if g != last:
        spot_rows.append(f'<tr class="grp"><th colspan="5" scope="rowgroup">{g}</th></tr>')
        last = g
    spot_rows.append(f'<tr><th scope="row"><label class="pos">{ck("spot." + k, k + " done")}<span class="id">{k}</span></label></th>'
                     f'<td class="num">{x}, {y}</td><td>{where(x, y)}{STAFF_TAG if k in STAFF else ""}</td>'
                     f'<td><div class="cams">{chips(s)}</div></td><td>{inp("spot." + k + ".datum", "cm", k + " ground vs datum, cm")}</td></tr>')
spot_rows = "".join(spot_rows)
FIRST_PAIRS = {(p, q) for p, q in PAIRS if p in SEEN and q in SEEN}
pair_rows = "".join(
    f'<tr><th scope="row"><label class="pos">{ck(f"dist.{p}-{q}.done", p + " to " + q + " done")}<span class="id">{p}&ndash;{q}</span>'
    f'{FIRST_TAG if (p, q) in FIRST_PAIRS else ""}</label></th>'
    f'<td class="num">{nominal(p, q):.1f} in<span class="xv">{nominal(p, q) * 2.54:.0f} cm</span></td>'
    f'<td>{inp(f"dist.{p}-{q}.1", "cm", p + " to " + q + " shot 1, cm")}</td><td>{inp(f"dist.{p}-{q}.2", "cm", p + " to " + q + " shot 2, cm")}</td></tr>'
    for p, q in PAIRS)
wall_rows = "".join(
    f'<tr><th scope="row">{n}</th><td class="num">{x}, {y}</td><td>{inp(f"wall.{x}.{y}.foot_datum", "cm", "ground at the wall foot vs datum at " + str(x) + ", " + str(y))}</td>'
    f'<td>{inp(f"wall.{x}.{y}.top", "cm", "wall top above that ground at " + str(x) + ", " + str(y) + ", cm")}</td></tr>'
    for n, x, y in WALL)
house_blocks = []
for name, h in HOUSES.items():
    cx, cy = h['c']
    bp, ap = h['pole'], h['apole']
    corners = "".join(
        f'<tr><th scope="row">{cn}</th><td>{inp(f"house.{name}.{cn}.height", "cm", name + " house " + cn + " top height, cm")}</td>'
        f'<td>{inp(f"house.{name}.{cn}.to_{bp}", "cm", name + " house " + cn + " to " + bp + ", cm")}</td>'
        f'<td>{inp(f"house.{name}.{cn}.to_{ap}", "cm", name + " house " + cn + " to " + ap + ", cm")}</td>'
        f'<td>{inp(f"house.{name}.{cn}.datum", "cm", name + " house " + cn + " ground vs datum, cm")}</td></tr>'
        for cn in ("SW", "SE", "NE", "NW"))
    house_blocks.append(f"""
  <div class="house-card">
    <h3>{name.capitalize()} house <span class="muted">under {h['cam']}, design centre x {cx}, y {cy}</span></h3>
    <div class="rec">
      <label>Length along y, base outside (cm){inp(f"house.{name}.len_y", "cm", name + " house length along y")}</label>
      <label>Width along x, base outside (cm){inp(f"house.{name}.wid_x", "cm", name + " house width along x")}</label>
      <label>Roof overhang beyond the walls (cm, each side){inp(f"house.{name}.overhang", "e.g. 2 / 2 / 0 / 0", name + " house overhang")}</label>
      <label>Moved since 2026-09-30? When?{inp(f"house.{name}.moved", "no / date", name + " house moved", "t wide")}</label>
    </div>
    <div class="tbl"><table>
      <thead><tr><th scope="col">Corner</th><th scope="col">Top surface above ground (cm)</th>
      <th scope="col">To {h['pole']} face (cm)</th><th scope="col">To {h['apole']} face (cm)</th><th scope="col">Ground vs datum (cm)</th></tr></thead>
      <tbody>{corners}</tbody></table></div>
  </div>""")
house_blocks = "".join(house_blocks)
MOUNT = {"CH01": "pano, beside B2 (y 85)", "CH02": "pano, beside B2 (y 159)", "CH03": "end camera at B1, facing x = 0",
         "CH04": "end camera at B3, facing x = 480", "CH05": "above the west house", "CH06": "above the east house"}
cam_rows = "".join(
    f'<tr><th scope="row">{c}<span class="xv">{MOUNT[c]}</span></th>'
    f'<td class="num">{v[2] * 2.54:.0f} cm<span class="xv">x {v[0]:.0f}, y {v[1]:.0f} in</span></td>'
    f'<td>{inp(f"cam.{c}.height", "cm", c + " lens height, cm")}</td>'
    f'<td>{inp(f"cam.{c}.mount", "pole / arm", c + " mount", "t wide")}</td>'
    f'<td>{inp(f"cam.{c}.offset", "cm, direction", c + " offset from pole face", "t wide")}</td>'
    f'<td>{inp(f"cam.{c}.datum", "cm", c + " ground below the camera vs datum, cm")}</td></tr>'
    for c, v in CAM.items())
N_SPOTS, N_PAIRS, N_WALL = len(SPOTS), len(PAIRS), len(WALL)

page = """<meta charset="utf-8">
<title>Teardown Survey Sheet</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&display=swap">
<style>
/* Layout: one reading column of numbered field steps; map first, then a record table per step (same family as the cone sheet). */
:root {
  --ground:#F5F6F2; --paper:#FFFFFF; --ink:#1C231F; --muted:#59645E; --rule:#D5DBD3;
  --grass:#E8EEE3; --pole:#8A5A2B; --pole-soft:#F3E7DA; --cord:#2C6798; --cord-soft:#DCE8F2; --ball:#6A4BA6; --warn:#B23B1E;
  --display:"Barlow Semi Condensed", "Arial Narrow", Arial, sans-serif;
  --body:"Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  --mono:"IBM Plex Mono", Consolas, "Courier New", monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground:#101412; --paper:#171C19; --ink:#E3E8E2; --muted:#9AA59D; --rule:#2B332E;
    --grass:#16201A; --pole:#D9A06A; --pole-soft:#33251A; --cord:#6FA7D8; --cord-soft:#1B2A37; --ball:#B49CE8; --warn:#F08A6C;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground:#101412; --paper:#171C19; --ink:#E3E8E2; --muted:#9AA59D; --rule:#2B332E;
  --grass:#16201A; --pole:#D9A06A; --pole-soft:#33251A; --cord:#6FA7D8; --cord-soft:#1B2A37; --ball:#B49CE8; --warn:#F08A6C;
}
body { background:var(--ground); color:var(--ink); font-family:var(--body); font-size:16px; line-height:1.5;
  padding-inline:16px; padding-block:24px 56px; }
.wrap { max-width:960px; margin:0 auto; display:flex; flex-direction:column; gap:28px; }
h1, h2, h3 { font-family:var(--display); font-weight:700; line-height:1.1; text-wrap:balance; margin:0; }
h1 { font-size:clamp(30px, 5vw, 42px); letter-spacing:.2px; }
h2 { font-size:23px; display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
h3 { font-size:19px; font-weight:600; }
h2 .step { font-family:var(--mono); font-size:14px; font-weight:500; color:var(--pole); border:1.5px solid var(--pole);
  border-radius:4px; padding:0 6px; }
h2 .when { font-family:var(--display); font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase;
  color:var(--cord); background:var(--cord-soft); border-radius:3px; padding:1px 6px; }
p, ol, ul { margin:0; max-width:70ch; }
ol, ul { padding-left:1.3em; display:flex; flex-direction:column; gap:6px; }
.eyebrow { font-family:var(--display); font-weight:600; text-transform:uppercase; letter-spacing:1.4px; font-size:13px; color:var(--muted); }
header, section { display:flex; flex-direction:column; gap:12px; }
.muted { color:var(--muted); font-weight:400; }
.facts { display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:10px 22px; padding:14px 16px;
  background:var(--paper); border:1px solid var(--rule); border-radius:6px; }
.facts div { display:flex; flex-direction:column; }
.facts b { font-family:var(--display); font-size:20px; font-weight:600; }
.facts span { font-size:14px; color:var(--muted); }
.map { overflow-x:auto; background:var(--paper); border:1px solid var(--rule); border-radius:6px; padding:10px; }
.map svg { display:block; width:100%; min-width:760px; height:auto; }
.pad { fill:var(--grass); stroke:var(--ink); stroke-width:1.6; }
.net { stroke:var(--cord); stroke-width:.7; opacity:.45; }
.house { fill:var(--paper); stroke:var(--ink); stroke-width:1.2; stroke-dasharray:3 2; }
.hlab { font-family:var(--display); font-size:8px; font-weight:600; letter-spacing:.6px; text-transform:uppercase; fill:var(--muted); }
.pole { fill:var(--pole); stroke:var(--paper); stroke-width:1.2; }
.pole.survey { fill:var(--paper); stroke:var(--pole); stroke-width:2; }
.plab { font-family:var(--mono); font-size:9px; font-weight:500; fill:var(--pole); }
.spot { fill:var(--ball); stroke:var(--paper); stroke-width:.8; }
.slab { font-family:var(--mono); font-size:6.5px; fill:var(--ball); }
.camm { fill:var(--ink); }
.clab { font-family:var(--mono); font-size:7px; fill:var(--ink); }
.wall { font-family:var(--display); font-size:10px; font-weight:600; letter-spacing:1px; fill:var(--muted); text-transform:uppercase; }
.legend { display:flex; flex-wrap:wrap; gap:8px 20px; font-size:14px; color:var(--muted); }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.legend svg { width:22px; height:14px; }
.tbl { overflow-x:auto; }
table { border-collapse:collapse; width:100%; background:var(--paper); font-size:14.5px; }
th, td { border:1px solid var(--rule); padding:6px 8px; vertical-align:top; text-align:left; }
thead th { font-family:var(--display); font-weight:600; font-size:14px; letter-spacing:.6px; text-transform:uppercase; color:var(--muted); background:var(--ground); }
tbody th { font-family:var(--display); font-weight:600; font-size:17px; white-space:nowrap; }
tr.grp th { font-size:14px; letter-spacing:.8px; text-transform:uppercase; color:var(--muted); background:var(--ground); }
.xv { display:block; font-family:var(--mono); font-size:12px; font-weight:400; color:var(--muted); }
.pos { display:flex; align-items:center; gap:7px; cursor:pointer; }
.ck { width:18px; height:18px; accent-color:var(--pole); margin:0; }
.ck:focus-visible { outline:2px solid var(--cord); outline-offset:2px; }
.id { font-family:var(--mono); font-weight:500; }
.first { font-family:var(--display); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.8px;
  color:var(--pole); background:var(--pole-soft); border-radius:3px; padding:0 5px; }
.warn { font-family:var(--display); font-size:12.5px; font-weight:600; color:var(--warn); margin-top:3px; }
.tag { font-family:var(--display); font-size:12.5px; font-weight:600; color:var(--cord); margin-top:3px; }
.part { font-family:var(--display); font-weight:700; font-size:15px; letter-spacing:1.2px; text-transform:uppercase;
  color:var(--muted); border-top:2px solid var(--rule); padding-top:10px; }
.cams { display:flex; flex-wrap:wrap; gap:3px; }
.cam { font-family:var(--mono); font-size:11.5px; border:1px solid var(--rule); border-radius:3px; padding:0 4px; color:var(--ink); }
.num { font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; }
input.t { font-family:var(--mono); font-size:14px; width:6.5em; padding:4px 6px; border:1px solid var(--rule); border-radius:4px;
  background:var(--paper); color:var(--ink); }
input.t.wide { width:11em; }
input.t:focus-visible { outline:2px solid var(--cord); outline-offset:1px; }
.rec { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px 18px; }
.rec label { display:flex; flex-direction:column; gap:4px; font-size:14px; color:var(--muted); }
.rec input.t { width:100%; box-sizing:border-box; }
.callout { background:var(--paper); border:1px solid var(--rule); border-left:3px solid var(--pole); border-radius:4px; padding:12px 16px;
  display:flex; flex-direction:column; gap:8px; }
.callout.why { border-left-color:var(--cord); }
.house-card { display:flex; flex-direction:column; gap:10px; }
.note { font-size:14.5px; color:var(--muted); max-width:72ch; }
.actions { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
button { font-family:var(--display); font-size:16px; font-weight:600; letter-spacing:.4px; padding:7px 16px; border-radius:4px;
  border:1.5px solid var(--pole); background:var(--pole); color:var(--paper); cursor:pointer; }
button:focus-visible { outline:2px solid var(--cord); outline-offset:2px; }
#copied { font-size:14px; color:var(--muted); }
#dump { width:100%; box-sizing:border-box; min-height:9em; font-family:var(--mono); font-size:13px; padding:8px; border:1px solid var(--rule);
  border-radius:4px; background:var(--paper); color:var(--ink); }
footer { font-size:13.5px; color:var(--muted); border-top:1px solid var(--rule); padding-top:14px; display:flex; flex-direction:column; gap:8px; }
code { font-family:var(--mono); font-size:.9em; }
</style>

<div class="wrap">
<header>
  <div class="eyebrow">Field 2026 · camera calibration · before teardown · revision 2, 2026-10-02</div>
  <h1>Pole, house and wall survey</h1>
  <p>What the calibration still needs from the field, in the order two independent reviews ranked it. Some of it
  needs the cameras recording, so that comes first. After the teardown none of it can be measured again.</p>
  <div class="facts">
    <div><b>About two hours</b><span>two people; steps 1&ndash;5 need the cameras recording (about 45 min), the rest does not</span></div>
    <div><b>One height datum</b><span>every height on this sheet is read against the same level reference</span></div>
    <div><b>@@NSPOTS@@ still-ball spots</b><span>8&ndash;10 s each, far end first; a still ball needs no clock</span></div>
    <div><b>Cameras untouched</b><span>B1, B2 and B3 carry cameras; never pull or lean on a pole</span></div>
  </div>
</header>

<section class="callout why">
  <h2>What the measurements are for</h2>
  <ul>
    <li><b>The floor.</b> The fit assumes one flat ground plane. At the far end the panoramas move a point
    2.3&ndash;2.5 cm sideways for every 1 cm the real ground is higher or lower, and nothing measured so far tells
    how flat it is. Both reviews put this first.</li>
    <li><b>Still targets at the CH04 end.</b> On the moving sweep, CH04's clock and its position error look the
    same. A still ball or staff needs no clock.</li>
    <li><b>IR and colour.</b> Switching the IR filter shifts the CH03/CH04 images by 10&ndash;18 px (2&ndash;5 cm on
    the ground). Night footage needs that shift, measured with the scene still.</li>
    <li><b>A clock event</b> that every camera sees gives the cameras' relative timing to one frame.</li>
    <li><b>Poles, houses, wall top</b> are fixed structures at heights the cameras see. They are also the only
    way to calibrate cohorts 1&ndash;2 afterwards.</li>
  </ul>
</section>

<section>
  <div class="map">@@MAP@@</div>
  <div class="legend">
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="5" fill="var(--pole)"/></svg>pole a camera sees</span>
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="4.5" fill="var(--paper)" stroke="var(--pole)" stroke-width="2"/></svg>pole for the survey network only</span>
    <span><svg viewBox="0 0 22 14"><line x1="1" y1="7" x2="21" y2="7" stroke="var(--cord)" stroke-width="1.4" opacity=".6"/></svg>pole-to-pole distance</span>
    <span><svg viewBox="0 0 22 14"><rect x="5" y="2" width="12" height="10" fill="var(--paper)" stroke="var(--ink)" stroke-dasharray="3 2"/></svg>house, design position</span>
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="4" fill="var(--ball)"/></svg>still-ball spot</span>
    <span><svg viewBox="0 0 22 14"><path d="M11,2 l5,9 l-10,0 z" fill="var(--ink)"/></svg>camera, as the fit places it</span>
  </div>
  <p class="note">Inches in the paddock frame: x along the 40 ft length from the x = 0 end wall (CH03's end), y
  across from the y = 0 side wall (row A). Compass words on this sheet: W = toward x = 0, E = toward x = 480,
  S = toward row A (y = 0), N = toward row C (y = 240). Camera chips = cameras that see that point.</p>
</section>

<section class="callout">
  <h2>Before going out</h2>
  <ol>
    <li><b>Start the calibration recorder</b> on the field PC (cmd, in the repository folder):
    <code>powershell -NoProfile -ExecutionPolicy Bypass -File calibration_record.ps1</code>. Check that every stream grows.</li>
    <li><b>All six ground cameras in colour</b> on the NVR live view. Daylight; dry domes. One person stays able to
    switch the cameras' IR mode (step 4).</li>
    <li><b>Bring:</b> laser rangefinder, 5 m tape, bright orange or red tape, a marker, a phone with a level app,
    the ball, a card to tape on a pole as a laser target, and:
      <ul>
        <li>a <b>level reference</b>: a clear hose 10 m or more filled with water (a water level), or a line laser on a tripod;</li>
        <li>a straight <b>staff</b> about 1.5 m long with tape marks whose lower edge is at 0 (the tip), 60, 105, 200 and
        300 mm, alternating colours.</li>
      </ul></li>
    <li><b>Pick the datum</b> before starting: one fixed mark that stays put, e.g. a pencil line on pole B2 at about
    50 cm. Every "vs datum" number on this sheet is the ground there minus the datum, in cm (negative = lower).</li>
    <li>Write the PC time of every recorded step. If anyone bumps a camera or its pole, write the time too.</li>
  </ol>
</section>

<div class="part">Part 1 · cameras recording</div>

<section>
  <h2><span class="step">1</span>Still ball <span class="when">cameras recording</span></h2>
  <ol>
    <li>Far end first. Put the ball on the ground at the spot (&plusmn;10 in is fine). Step 1.5 m sideways, away
    from the middle row of poles where the cameras hang, and crouch.</li>
    <li><b>Hold 8&ndash;10 s</b>, then move to the next spot. Write the PC time at the start of each group.</li>
    <li>After the far end: push the ball slowly along cord T7 (x 456) from y 12 to y 228, stopping 3 s at every
    tick, then back from y 228 to y 12, stopping again.</li>
    <li>Leave the "vs datum" column for step 6.</li>
  </ol>
  <div class="rec">
    <label>Far end, start (PC time)@@T1@@</label>
    <label>T7 push +y then -y, start and end@@T4@@</label>
    <label>x = 0 end, start@@T2@@</label>
    <label>Houses, start@@T3@@</label>
  </div>
  <div class="tbl"><table>
    <thead><tr><th scope="col">Spot</th><th scope="col">x, y (in)</th><th scope="col">Where</th><th scope="col">Seen by</th><th scope="col">Ground vs datum (cm, step 6)</th></tr></thead>
    <tbody>@@SPOTS@@</tbody></table></div>
</section>

<section>
  <h2><span class="step">2</span>Staff at known heights <span class="when">cameras recording</span></h2>
  <p>At every spot tagged "staff here too", stand the staff on the ground with its 0 mark at the bottom, held
  vertical (phone level against it), for 8&ndash;10 s. It shows each camera points at 0, 60, 105, 200 and 300 mm
  above the same ground: the height scale near rat height, with no clock involved.</p>
  <div class="rec"><label>Start and end (PC time)@@T5@@</label></div>
</section>

<section>
  <h2><span class="step">3</span>Clock check: four jumps <span class="when">cameras recording</span> <span class="when">optional</span></h2>
  <p>No spot is seen by all six cameras: CH03 looks only at the x = 0 end, CH04 only at the x = 480 end, CH05/CH06
  only around their houses. The two panoramas see everywhere, so each camera is tied to them where they overlap.
  The cameras' clock offsets are already measured from the 20 Hz ball; these jumps are an independent check.</p>
  <ol>
    <li>Everyone else out of view. One person jumps once, clearly, at each spot below, and writes the PC time to the second:
      <ul>
        <li>x 40, y 120 (the x = 0 end): CH01, CH02, CH03</li>
        <li>x 440, y 120 (the x = 480 end): CH01, CH02, CH04</li>
        <li>x 135, y 150 (north side of the west house): CH01, CH02, CH05</li>
        <li>x 347, y 90 (south side of the east house): CH01, CH02, CH06</li>
      </ul></li>
    <li>Hold a phone showing a network clock with seconds (e.g. time.is) in front of CH05 for 10 s and write the PC
    time. This ties the PC clock to what the cameras burn into their picture.</li>
  </ol>
  <div class="rec"><label>Jump times (PC), in the order above@@T6@@</label><label>Phone clock in front of CH05 (PC time)@@T7@@</label></div>
</section>

<section>
  <h2><span class="step">4</span>IR and colour, scene still <span class="when">cameras recording</span></h2>
  <ol>
    <li>Everyone out of view, nothing moving in the paddock.</li>
    <li>Switch all six cameras to black-and-white (IR) for 60 s, then back to colour for 60 s. Do it twice.</li>
    <li>Write the PC time of each switch. The cameras must not be touched; switch them from the NVR or the app.</li>
  </ol>
  <div class="rec"><label>Switch times (to IR, to colour, to IR, to colour)@@T8@@</label></div>
</section>

<section>
  <h2><span class="step">5</span>Bands on the poles <span class="when">cameras recording</span></h2>
  <p>Only if step 8 (pole positions) will be done too; bands without positions are of no use. On each pole a
  camera sees, wrap two turns of tape with the <b>top edge</b> at about 120 cm and 200 cm above the ground at the
  foot, then everyone out of view for 30 s. The exact heights are measured in step 8.</p>
  <div class="rec"><label>Clear field after the bands (PC time)@@CLEAR@@</label></div>
</section>

<div class="part">Part 2 · no recording needed</div>

<section>
  <h2><span class="step">6</span>Floor heights against the datum</h2>
  <ol>
    <li>Set up the level reference so it reaches the datum and as many spots as possible; move it as often as
    needed, re-reading the datum (or a point already read) after each move.</li>
    <li>At every still-ball spot (step 1 table), every pole foot (step 8 table), every house corner (step 7), the
    wall foot points (step 9) and below every camera (step 7): the height of the soil surface (grass pressed down)
    relative to the datum, in cm.</li>
    <li>Note roughly how tall the grass is where the ball sat at the far end.</li>
  </ol>
  <div class="rec"><label>Level used, and grass height at the far end@@T9@@</label></div>
</section>

<section>
  <h2><span class="step">7</span>Cameras and houses</h2>
  <p>Lens height above the ground directly below it (laser straight up, or the tape), what it hangs on, its
  horizontal offset from that pole's face, and the ground there vs the datum. The fit's value is there to catch
  a slip. One review reads the fit 6&ndash;12 cm above the taped heights for CH03 and CH04; this measurement settles it.</p>
  <div class="tbl"><table>
    <thead><tr><th scope="col">Camera</th><th scope="col">Fit says</th><th scope="col">Lens height (cm)</th><th scope="col">Mounted on</th><th scope="col">Offset from pole face</th><th scope="col">Ground vs datum (cm)</th></tr></thead>
    <tbody>@@CAMS@@</tbody></table></div>
  <ul>
    <li><b>Houses:</b> outside dimensions of the base; the top surface's height above the ground at each corner;
    any roof overhang; each base corner's distance to the nearest B pole and to the A pole of the same column,
    about 20 cm above the ground, pole face to the corner edge; the ground at each corner vs the datum.</li>
    <li>Do not move a house. If one was moved after 2026-09-30, say when.</li>
  </ul>
  @@HOUSES@@
</section>

<section>
  <h2><span class="step">8</span>Poles</h2>
  <ul>
    <li><b>Circumference</b> with the tape at about 120 cm, or the two widths if the pole is square (the images
    suggest about 14 cm across, a 6 x 6 in post; the base may be thicker).</li>
    <li><b>Lean</b> with the phone's level app held flat against the pole at about 150 cm: on the face toward +x (E)
    and on the face toward +y (N). Positive = the top leans that way.</li>
    <li><b>Bands</b> (if step 5 was done): the exact height of each band's top edge above the ground at the foot.</li>
    <li><b>Distances:</b> hold the rangefinder flat against pole P at the lower band and aim at the same height on
    pole Q, along the line between the centres (tape the card on Q if the beam misses). Face to face; shoot twice;
    if the two differ by more than 1 cm, shoot again. Rows marked <span class="first">first</span> join two of the
    nine poles the cameras see: do those, the rest only if time allows.</li>
  </ul>
  <div class="tbl"><table>
    <thead><tr><th scope="col">Pole</th><th scope="col">Seen by</th><th scope="col">Band ~120 (cm)</th>
    <th scope="col">Band ~200 (cm)</th><th scope="col">Circumference (cm)</th><th scope="col">Lean +x (deg)</th><th scope="col">Lean +y (deg)</th><th scope="col">Foot vs datum (cm)</th></tr></thead>
    <tbody>@@BANDS@@</tbody></table></div>
  <div class="tbl"><table>
    <thead><tr><th scope="col">Pair</th><th scope="col">Design, centres</th><th scope="col">Shot 1 (cm)</th><th scope="col">Shot 2 (cm)</th></tr></thead>
    <tbody>@@PAIRS@@</tbody></table></div>
</section>

<section>
  <h2><span class="step">9</span>Wall top</h2>
  <p>At every pole on the wall and half-way between (@@NWALL@@ points; design 97.8 cm): the ground at the wall
  foot vs the datum, and the top edge's height above that ground (tape, paddock side, grass pressed down). The
  corners and ends matter most.</p>
  <div class="tbl"><table>
    <thead><tr><th scope="col">At</th><th scope="col">x, y (in)</th><th scope="col">Foot vs datum (cm)</th><th scope="col">Top above ground (cm)</th></tr></thead>
    <tbody>@@WALL@@</tbody></table></div>
</section>

<section>
  <h2><span class="step">10</span>Photos</h2>
  <ul>
    <li>Each pole from two sides with the tape held against it from the ground past the upper band.</li>
    <li>Each house from all four sides with the tape along its edges, and one from above.</li>
    <li>The level setup and the datum mark; the grass at the far-end spots.</li>
    <li>Wide shots from each corner of the paddock that tie poles, houses and walls together.</li>
  </ul>
</section>

<section class="callout">
  <h2>When done</h2>
  <ol>
    <li>Stop the calibration recorder (Ctrl+C) and copy the session to the analysis PC before anything is taken down.</li>
    <li><b>Copy the entries below and paste them into the chat</b> before leaving the field. They live only in this
    browser on this device; clearing it or switching phones loses them.</li>
  </ol>
  <div class="actions"><button type="button" id="copy">Copy all entries</button><span id="copied" role="status"></span></div>
  <textarea id="dump" readonly hidden aria-label="All entries as text"></textarea>
</section>

<footer>
  <div>What happens with the numbers: the pole network gives each pole's centre to about 1 cm; the bands give
  points at two heights on each pole; the poles' edges, the house corners and the wall top enter the bundle
  (<code>fit_cameras.py</code>) as straight-line and 3-D constraints, the lens models are refitted, then the ground
  correction, and the three checks run again (boards, held-out cones, balls). The still-ball spots enter
  <code>refit_supplement.py --balls</code> as tie points that need no clock.</div>
  <div>Sources: pole grid and house design from <code>field_layout.json</code>; which camera sees which pole from the
  operator's landmark labels (2026-09-18); camera positions and the spots' cameras from the release fit. Sheet:
  <code>calibration_qc/survey_sheet.py</code>; checklist it serves: <code>PRE_TEARDOWN_CAPTURE_CHECKLIST.md</code>, section B.
  Entries stay in this browser only.</div>
</footer>
</div>

<script>
(function () {
  var KEY = "teardown-survey-sheet-v1", state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  var els = document.querySelectorAll("[data-k]");
  els.forEach(function (el) {
    var k = el.getAttribute("data-k");
    if (el.type === "checkbox") {
      if (state[k]) el.checked = true;
      el.addEventListener("change", function () { state[k] = el.checked; save(); });
    } else {
      if (state[k]) el.value = state[k];
      el.addEventListener("input", function () { state[k] = el.value; save(); });
    }
  });
  var btn = document.getElementById("copy"), out = document.getElementById("copied"), dump = document.getElementById("dump");
  btn.addEventListener("click", function () {
    var lines = ["teardown survey " + new Date().toISOString()], n = 0;
    els.forEach(function (el) {
      var k = el.getAttribute("data-k");
      if (el.type === "checkbox") { if (el.checked) { lines.push(k + "\\tdone"); n++; } }
      else if (el.value.trim()) { lines.push(k + "\\t" + el.value.trim()); n++; }
    });
    var text = lines.join("\\n");
    function fallback() {
      dump.hidden = false; dump.value = text; dump.focus(); dump.select();
      out.textContent = n + " entries below: select all and copy.";
    }
    try {
      navigator.clipboard.writeText(text).then(function () { out.textContent = "Copied " + n + " entries."; }, fallback);
    } catch (e) { fallback(); }
  });
})();
</script>
"""
page = (page.replace("@@MAP@@", svg).replace("@@BANDS@@", band_rows).replace("@@SPOTS@@", spot_rows)
        .replace("@@PAIRS@@", pair_rows).replace("@@WALL@@", wall_rows).replace("@@HOUSES@@", house_blocks)
        .replace("@@CAMS@@", cam_rows).replace("@@NPAIRS@@", str(N_PAIRS)).replace("@@NSPOTS@@", str(N_SPOTS))
        .replace("@@NWALL@@", str(N_WALL))
        .replace("@@CLEAR@@", inp("time.clear", "HH:MM:SS", "clear-field PC time"))
        .replace("@@T1@@", inp("time.far", "HH:MM:SS", "far end start", "t wide"))
        .replace("@@T2@@", inp("time.x0", "HH:MM:SS", "x = 0 end start", "t wide"))
        .replace("@@T3@@", inp("time.houses", "HH:MM:SS", "houses start", "t wide"))
        .replace("@@T4@@", inp("time.push", "start - end", "T7 push start and end", "t wide"))
        .replace("@@T5@@", inp("time.staff", "start - end", "staff start and end", "t wide"))
        .replace("@@T6@@", inp("time.jump", "4 times", "jump PC times", "t wide"))
        .replace("@@T7@@", inp("time.phone", "HH:MM:SS", "phone clock PC time", "t wide"))
        .replace("@@T8@@", inp("time.ir", "4 times", "IR switch times", "t wide"))
        .replace("@@T9@@", inp("level.note", "water hose / laser; grass cm", "level and grass", "t wide")))
OUT.write_text(page, encoding="utf-8")
print("->", OUT, len(page), "bytes;", N_SPOTS, "spots (staff at " + ", ".join(sorted(STAFF, key=lambda k: int(k[1:]))) + "),", N_PAIRS, "pairs,", N_WALL, "wall points;",
      "spots seen by < 2 cameras:", [k for k, g, x, y, s in SPOTS if len(s) < 2])
