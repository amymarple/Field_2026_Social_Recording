# -*- coding: utf-8 -*-
r"""The handoff cone sheet (HTML field sheet) from the numbers cone_supplement.py computed.

    python cone_sheet.py [--plan <cone_supplement.json>] --out <sheet.html>

Positions, the cameras that see each one, the scenario table and the never-labelled station cones all come
from the plan file (default <calibration root>\qc\cone_supplement\cone_supplement.json); only the
instructions are written here. "First" = the mid-points with the largest handoff gain (>= FIRST_GAIN),
plus the T7 cord and the two corners at the x = 480 end, where two cameras disagree most today.
The committed sheet is CALIB_CONE_SHEET_2026-09-26.html in the repository root.
"""
import json, sys
from pathlib import Path
from html import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_paths                                                           # noqa: E402

args = sys.argv[1:]
PLAN = Path(args[args.index("--plan") + 1]) if "--plan" in args else qc_paths.QC_ROOT / "cone_supplement" / "cone_supplement.json"
if "--out" not in args:
    raise SystemExit("usage: python cone_sheet.py [--plan <cone_supplement.json>] --out <sheet.html>")
OUT = Path(args[args.index("--out") + 1])
plan = json.loads(PLAN.read_text(encoding="utf-8"))

TRAIN_X = [24, 96, 168, 240, 312, 384, 456]
TICK_Y = [12, 66, 120, 174, 228]
VT_X = [60, 132, 204, 276, 348, 420]
VT_Y = [39, 93, 147, 201]
FIRST_GAIN = 70.0
WORDS = {i: w for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}

pos = {k: dict(x=r["x"], y=r["y"], cams=sorted(r["cams"]), gain=r["gain"]) for k, r in plan["positions"].items()}
pos = {k: pos[k] for k in plan["order"] + plan["no_gain"]}
FIRST = {k for k, v in pos.items() if v["gain"] >= FIRST_GAIN} | {"T71M", "T72M", "T73M", "T74M"}
EXTRA = {
    "C1": dict(how="From tick T11 (x 24, y 12), 12 in toward the x = 0 wall along y = 12"),
    "C2": dict(how="From tick T15 (x 24, y 228), 12 in toward the x = 0 wall along y = 228"),
    "C3": dict(how="From tick T71 (x 456, y 12), 12 in toward the x = 480 wall along y = 12"),
    "C4": dict(how="From tick T75 (x 456, y 228), 12 in toward the x = 480 wall along y = 228"),
    "E1": dict(how="On cord T6 (x 384), 9 in from tick T61 toward the y = 240 wall"),
    "E2": dict(how="On cord T2 (x 96), 15 in from tick T24 toward the y = 240 wall"),
}
for k, v in EXTRA.items():
    e = plan["extras"][k]
    v.update(x=e["x"], y=e["y"], cams=sorted(e["cams"]))
FIRST |= {"C3", "C4"}
N_FIRST = len(FIRST)
UNLAB = plan["unlabelled"]
N_UNLAB = sum(len(v) for v in UNLAB.values())
UNLAB_TXT = "; ".join(f"{c} {', '.join(v)}" for c, v in UNLAB.items())
SMALL = plan["scenarios"][0]["per_cam"]
SEEN_TXT = ", ".join(f"{c} {SMALL[c]['seen'] * 100:.1f} %" for c in ("CH03", "CH04", "CH05", "CH06"))
SHA = plan["fit_sha256"][:8]


def chips(cams):
    return "".join(f'<span class="cam">{c[2:]}</span>' for c in cams)


def cell(cid, sub):
    p = pos[cid]
    first = '<span class="first" title="place first">first</span>' if cid in FIRST else ""
    return (f'<td><label class="pos" for="ck-{cid}"><input type="checkbox" id="ck-{cid}" data-k="{cid}">'
            f'<span class="id">{cid}</span>{first}</label>'
            f'<div class="sub">{sub}</div><div class="cams">{chips(p["cams"])}</div></td>')


# ---- step 1: T-cord mid-points
rows1 = []
for i, x in enumerate(TRAIN_X, 1):
    cells = "".join(cell(f"T{i}{j}M", f"tick T{i}{j} + 27 in") for j in range(1, 5))
    rows1.append(f'<tr><th scope="row">T{i}<span class="xv">x {x}</span></th>{cells}</tr>')

# ---- step 2: V/F column mid-points
rows2 = []
for i, x in enumerate(VT_X, 1):
    cs = []
    for j, y in enumerate([66, 120, 174], 1):
        cid = f"{'V' if (i + j) % 2 == 0 else 'F'}{i}{j}M"
        a, b = f"T{i}{j + 1}", f"T{i + 1}{j + 1}"
        cs.append(cell(cid, f"halfway {a}&ndash;{b}"))
    rows2.append(f'<tr><th scope="row">V/F{i}<span class="xv">x {x}</span></th>{"".join(cs)}</tr>')

# ---- step 3: corners + extras
rows3 = []
for k, v in EXTRA.items():
    first = '<span class="first">first</span>' if k in FIRST else ""
    rows3.append(f'<tr><td><label class="pos" for="ck-{k}"><input type="checkbox" id="ck-{k}" data-k="{k}">'
                 f'<span class="id">{k}</span>{first}</label></td><td class="num">{v["x"]}, {v["y"]}</td>'
                 f'<td>{escape(v["how"])}</td><td class="cams">{chips(v["cams"])}</td></tr>')

# ---- map (paddock inches; y up)
def Y(y):
    return 240 - y

svg = ['<svg viewBox="-44 -26 572 300" role="img" aria-label="Paddock map: T cords, new cone positions, optional new cords">',
       '<rect class="pad" x="0" y="0" width="480" height="240"/>']
for yy in (39, 201):
    svg.append(f'<line class="newcord" x1="0" y1="{Y(yy)}" x2="480" y2="{Y(yy)}"/>')
    svg.append(f'<text class="cordlab" x="484" y="{Y(yy) + 3}">Y{yy}</text>')
for xx in (60, 420):
    svg.append(f'<line class="newcord2" x1="{xx}" y1="0" x2="{xx}" y2="240"/>')
    svg.append(f'<text class="cordlab" x="{xx}" y="-6" text-anchor="middle">X{xx}</text>')
for i, x in enumerate(TRAIN_X, 1):
    svg.append(f'<line class="cord" x1="{x}" y1="0" x2="{x}" y2="240"/>')
    svg.append(f'<text class="axis" x="{x}" y="254" text-anchor="middle">T{i} · {x}</text>')
    for y in TICK_Y:
        svg.append(f'<line class="tick" x1="{x - 4}" y1="{Y(y)}" x2="{x + 4}" y2="{Y(y)}"/>')
for k, p in pos.items():
    on_cord = k.startswith("T")
    cls = "cone" + (" firstm" if k in FIRST else "")
    if on_cord:
        svg.append(f'<circle class="{cls}" cx="{p["x"]}" cy="{Y(p["y"])}" r="4.2"/>')
    else:
        svg.append(f'<circle class="{cls} ring" cx="{p["x"]}" cy="{Y(p["y"])}" r="4"/>')
    ly = Y(p["y"]) - 5 if p["y"] in (39, 201) else Y(p["y"]) + 2.6
    svg.append(f'<text class="lab" x="{p["x"] + 6}" y="{ly}">{k}</text>')
for k, v in EXTRA.items():
    cls = "cone sq" + (" firstm" if k in FIRST else "")
    svg.append(f'<rect class="{cls}" x="{v["x"] - 4}" y="{Y(v["y"]) - 4}" width="8" height="8"/>')
    anchor, dx = ("end", -7) if v["x"] > 400 else ("start", 7)
    svg.append(f'<text class="lab" x="{v["x"] + dx}" y="{Y(v["y"]) + 2.6}" text-anchor="{anchor}">{k}</text>')
svg += ['<text class="wall" x="240" y="-12" text-anchor="middle">y = 240 wall</text>',
        '<text class="wall" x="240" y="270" text-anchor="middle">y = 0 wall</text>',
        '<text class="wall" x="-10" y="120" text-anchor="middle" transform="rotate(-90 -10 120)">x = 0 wall</text>',
        '<text class="wall" x="498" y="120" text-anchor="middle" transform="rotate(90 498 120)">x = 480 wall</text>',
        '</svg>']
svg = "\n".join(svg)

# ---- what it buys
SC_LABELS = ["Today", "+ 28 cones on the T cords (step 1)", "+ 18 V/F mid-points, 4 corners (steps 2&ndash;3)",
             "+ long cords Y39, Y201 (step 5)", "+ cross cords X60, X420 (step 5)"]
SC = [(lab, *(f"{s[k] * 100:.1f}" for k in ("mapped_by_0", "mapped_by_1", "mapped_by_2plus")),
       *(f"{s['per_cam'][c]['mapped'] * 100:.1f}" for c in ("CH03", "CH04", "CH05", "CH06")))
      for lab, s in zip(SC_LABELS, plan["scenarios"])]
sc_rows = "".join("<tr><th scope=\"row\">" + s[0] + "</th>" + "".join(f'<td class="num">{v}%</td>' for v in s[1:]) + "</tr>" for s in SC)

html = f"""<title>Handoff Cone Sheet</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&display=swap">
<style>
:root {{
  --ground:#F5F6F2; --paper:#FFFFFF; --ink:#1C231F; --muted:#59645E; --rule:#D5DBD3;
  --grass:#E8EEE3; --cone:#D2581A; --cone-soft:#FCE6D8; --cord:#2C6798; --cord-soft:#DCE8F2;
  --display:"Barlow Semi Condensed", "Arial Narrow", Arial, sans-serif;
  --body:"Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  --mono:"IBM Plex Mono", Consolas, "Courier New", monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --ground:#101412; --paper:#171C19; --ink:#E3E8E2; --muted:#9AA59D; --rule:#2B332E;
    --grass:#16201A; --cone:#F0873F; --cone-soft:#3B2417; --cord:#6FA7D8; --cord-soft:#1B2A37;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --ground:#101412; --paper:#171C19; --ink:#E3E8E2; --muted:#9AA59D; --rule:#2B332E;
  --grass:#16201A; --cone:#F0873F; --cone-soft:#3B2417; --cord:#6FA7D8; --cord-soft:#1B2A37;
}}
body {{ background:var(--ground); color:var(--ink); font-family:var(--body); font-size:16px; line-height:1.5;
  padding-inline:16px; padding-block:24px 56px; }}
.wrap {{ max-width:960px; margin:0 auto; display:flex; flex-direction:column; gap:28px; }}
h1, h2 {{ font-family:var(--display); font-weight:700; line-height:1.1; text-wrap:balance; margin:0; }}
h1 {{ font-size:clamp(30px, 5vw, 42px); letter-spacing:.2px; }}
h2 {{ font-size:23px; display:flex; gap:10px; align-items:baseline; }}
h2 .step {{ font-family:var(--mono); font-size:14px; font-weight:500; color:var(--cone); border:1.5px solid var(--cone);
  border-radius:4px; padding:0 6px; }}
p {{ margin:0; max-width:68ch; }}
.eyebrow {{ font-family:var(--display); font-weight:600; text-transform:uppercase; letter-spacing:1.4px; font-size:13px; color:var(--muted); }}
header {{ display:flex; flex-direction:column; gap:10px; }}
section {{ display:flex; flex-direction:column; gap:12px; }}
.muted {{ color:var(--muted); }}
.facts {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:10px 22px; padding:14px 16px;
  background:var(--paper); border:1px solid var(--rule); border-radius:6px; }}
.facts div {{ display:flex; flex-direction:column; }}
.facts b {{ font-family:var(--display); font-size:20px; font-weight:600; }}
.facts span {{ font-size:14px; color:var(--muted); }}
.map {{ overflow-x:auto; background:var(--paper); border:1px solid var(--rule); border-radius:6px; padding:10px; }}
.map svg {{ display:block; width:100%; min-width:760px; height:auto; }}
.pad {{ fill:var(--grass); stroke:var(--ink); stroke-width:1.6; }}
.cord {{ stroke:var(--ink); stroke-width:.8; opacity:.55; }}
.tick {{ stroke:var(--ink); stroke-width:1.4; }}
.newcord {{ stroke:var(--cord); stroke-width:1.3; stroke-dasharray:6 4; fill:none; }}
.newcord2 {{ stroke:var(--cord); stroke-width:1; stroke-dasharray:2 4; fill:none; }}
.cone {{ fill:var(--cone); stroke:var(--paper); stroke-width:1; }}
.cone.ring {{ fill:var(--paper); stroke:var(--cone); stroke-width:2; }}
.cone.firstm {{ stroke:var(--ink); stroke-width:1.4; }}
.cone.ring.firstm {{ stroke:var(--cone); stroke-width:2.6; }}
.lab {{ font-family:var(--mono); font-size:7.5px; fill:var(--ink); }}
.axis, .cordlab {{ font-family:var(--mono); font-size:8.5px; fill:var(--muted); }}
.cordlab {{ fill:var(--cord); }}
.wall {{ font-family:var(--display); font-size:10px; font-weight:600; letter-spacing:1px; fill:var(--muted); text-transform:uppercase; }}
.legend {{ display:flex; flex-wrap:wrap; gap:8px 20px; font-size:14px; color:var(--muted); }}
.legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.legend svg {{ width:22px; height:14px; }}
.tbl {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; background:var(--paper); font-size:14.5px; }}
th, td {{ border:1px solid var(--rule); padding:7px 9px; vertical-align:top; text-align:left; }}
thead th {{ font-family:var(--display); font-weight:600; font-size:14px; letter-spacing:.6px; text-transform:uppercase; color:var(--muted); background:var(--ground); }}
tbody th {{ font-family:var(--display); font-weight:600; font-size:17px; white-space:nowrap; }}
.xv {{ display:block; font-family:var(--mono); font-size:12px; font-weight:400; color:var(--muted); }}
.pos {{ display:flex; align-items:center; gap:7px; cursor:pointer; }}
.pos input {{ width:18px; height:18px; accent-color:var(--cone); margin:0; }}
.pos input:focus-visible {{ outline:2px solid var(--cord); outline-offset:2px; }}
.id {{ font-family:var(--mono); font-weight:500; }}
.first {{ font-family:var(--display); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.8px;
  color:var(--cone); background:var(--cone-soft); border-radius:3px; padding:0 5px; }}
.sub {{ font-family:var(--mono); font-size:12.5px; color:var(--muted); margin-top:2px; }}
.cams {{ display:flex; flex-wrap:wrap; gap:3px; margin-top:4px; }}
.cam {{ font-family:var(--mono); font-size:11.5px; border:1px solid var(--rule); border-radius:3px; padding:0 4px; color:var(--ink); }}
.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; }}
td:has(input:checked) {{ background:var(--cone-soft); }}
ol, ul {{ margin:0; padding-left:22px; max-width:70ch; display:flex; flex-direction:column; gap:6px; }}
.rec {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px 18px; }}
.rec label {{ display:flex; flex-direction:column; gap:4px; font-size:14px; color:var(--muted); }}
.rec input, .rec textarea {{ font-family:var(--mono); font-size:15px; padding:6px 8px; border:1px solid var(--rule); border-radius:4px;
  background:var(--paper); color:var(--ink); }}
.rec input:focus-visible, .rec textarea:focus-visible {{ outline:2px solid var(--cord); outline-offset:1px; }}
.note {{ font-size:14.5px; color:var(--muted); max-width:72ch; }}
.callout {{ background:var(--paper); border:1px solid var(--rule); border-left:3px solid var(--cone); border-radius:4px; padding:10px 14px; }}
.optional {{ border-left-color:var(--cord); }}
footer {{ font-size:13.5px; color:var(--muted); border-top:1px solid var(--rule); padding-top:14px; display:flex; flex-direction:column; gap:8px; }}
code {{ font-family:var(--mono); font-size:.9em; }}
</style>

<div class="wrap">
<header>
  <div class="eyebrow">Field 2026 · camera calibration supplement · written 2026-09-26</div>
  <h1>Handoff cone sheet</h1>
  <p>Cones only, no board. Each cone below sits where two or more cameras see the ground, so after labelling,
  every camera is pinned to the same physical points where a rat passes from one camera to the next. The
  positions come from the released calibration: which cameras see each point, and where each camera's mapped
  area is thinnest today.</p>
  <div class="facts">
    <div><b>52 positions</b><span>28 on the existing T cords, 18 between them, 6 corner and edge cones</span></div>
    <div><b>{N_FIRST} marked first</b><span>the largest gain for the handoffs; place these first if time runs short</span></div>
    <div><b>Tape measure only</b><span>every position is a half-way point between ticks, or a short distance from one</span></div>
    <div><b>Cameras untouched</b><span>do not lean on poles or shelters; everyone out of view while recording</span></div>
  </div>
</header>

<section>
  <div class="map">{svg}</div>
  <div class="legend">
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="4.5" fill="var(--cone)"/></svg>on an existing T cord</span>
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="4" fill="var(--paper)" stroke="var(--cone)" stroke-width="2"/></svg>between cords, measured tick to tick</span>
    <span><svg viewBox="0 0 22 14"><rect x="7" y="3" width="8" height="8" fill="var(--cone)"/></svg>corner / edge cone</span>
    <span><svg viewBox="0 0 22 14"><circle cx="11" cy="7" r="4.5" fill="var(--cone)" stroke="var(--ink)" stroke-width="1.6"/></svg>dark outline = first</span>
    <span><svg viewBox="0 0 22 14"><line x1="1" y1="7" x2="21" y2="7" stroke="var(--cord)" stroke-width="2" stroke-dasharray="5 3"/></svg>optional new cord</span>
    <span><svg viewBox="0 0 22 14"><line x1="7" y1="7" x2="15" y2="7" stroke="var(--ink)" stroke-width="2"/></svg>existing tick (y 12, 66, 120, 174, 228)</span>
  </div>
  <p class="note">All numbers are inches in the paddock frame: x along the 40 ft length from the x = 0 end wall,
  y across the 20 ft width from the y = 0 side wall. Camera chips under each position are the cameras that
  should see it according to the fit (CH01/CH02 panoramas, CH03/CH04 end cameras, CH05/CH06 shelter cameras);
  a house or pole can still hide one, which does no harm.</p>
</section>

<section>
  <h2><span class="step">0</span>Check the cords before measuring</h2>
  <p>The cameras have not moved; the old cones have. Every position below is measured from the T-cord ticks,
  so the cords are now the only reference. Before placing anything, walk each of the seven T cords: taut, both
  ends on their original stakes, ticks still readable. If a cord has slipped, pull it back onto its stakes.
  If a stake itself has moved, note which one and do not re-measure it from the wall; tell Claude instead.
  The old cone positions are not lost: they were labelled from the 2026-09-18 footage.</p>
</section>

<section>
  <h2><span class="step">1</span>Cones on the T cords (28)</h2>
  <p>On each of the seven T cords, put a cone 27 in above each of the first four ticks (toward the y = 240 wall),
  so it sits half-way between two ticks. Measure the 27 in from the tick with the tape; do not eyeball it. The
  last tick (y 228) gets no cone. IDs are the lower station plus M (T11M sits between T11 and T12).</p>
  <div class="tbl"><table>
    <thead><tr><th>Cord</th><th>y 12 &rarr; 39</th><th>y 66 &rarr; 93</th><th>y 120 &rarr; 147</th><th>y 174 &rarr; 201</th></tr></thead>
    <tbody>{"".join(rows1)}</tbody>
  </table></div>
</section>

<section>
  <h2><span class="step">2</span>Place the cones between the cords (18)</h2>
  <p>These have no cord of their own. Stretch the tape between the two ticks at the same y on the neighbouring
  T cords (72 in apart) and put the cone at 36 in, half-way. Keep the tape straight and taut; the two ticks
  fix both the distance and the direction.</p>
  <div class="tbl"><table>
    <thead><tr><th>Column</th><th>y 66</th><th>y 120</th><th>y 174</th></tr></thead>
    <tbody>{"".join(rows2)}</tbody>
  </table></div>
</section>

<section>
  <h2><span class="step">3</span>Corner and edge cones (6)</h2>
  <p>The four corners are the only ground no camera can map today. E1 and E2 widen the area CH04 and CH05
  can map. If a rounded corner leaves no flat ground at the spot, skip that cone and note it.</p>
  <div class="tbl"><table>
    <thead><tr><th>ID</th><th>x, y</th><th>How to place</th><th>Seen by</th></tr></thead>
    <tbody>{"".join(rows3)}</tbody>
  </table></div>
</section>

<section>
  <h2><span class="step">4</span>Record the new cone set</h2>
  <p>Everyone out of every camera view for 60 s, in daylight (colour, not IR). Check the NVR live view that no
  one is in frame, then write the PC clock time.</p>
  <div class="rec">
    <label for="t-step4">Step 4, new cone set: PC time<input id="t-step4" type="text" placeholder="HH:MM:SS – HH:MM:SS" data-k="t-step4"></label>
    <label for="t-skipped">Cones skipped or moved off position (ID and why)<input id="t-skipped" type="text" placeholder="e.g. C2 no flat ground" data-k="t-skipped"></label>
  </div>
</section>

<section>
  <h2>The ground is not flat, and that is fine</h2>
  <p>The model puts every camera onto one flat plane. Where the real ground is higher or lower by h, an oblique
  camera (CH01&ndash;CH04) reads the point about 0.9&thinsp;h too far from or too close to itself; a shelter camera
  (CH05, CH06) only about 0.1&thinsp;h. Two cameras looking from opposite sides are pushed in opposite directions,
  so a 5 cm bump can put them up to about 9 cm apart. Part of today's 6&ndash;7 cm median disagreement at the
  handoffs is probably this, not the calibration.</p>
  <p>The cones stand on the real ground, grass and all, so every labelled cone carries its own local height. The
  ground correction is fitted to those cones, which puts every camera on the right spot at each cone whatever the
  bump; between cones it interpolates. That is why the cones are dense (27&ndash;36 in apart), and no height has to
  be measured for it to work. Where two cameras see the same cone, their two rays also give the height of the ground
  there, so the new set yields a coarse terrain map for free. Nothing about the ground is measured in the field.</p>
</section>

<section class="callout optional">
  <h2><span class="step">5</span>Optional: new cords</h2>
  <p>Cords are traced along their whole length in every camera, so a cord gives many more points than a cone.
  The two long cords matter most: every camera today has cords only across the paddock (they fix x), and only the
  side walls fix y. Do this after step 4 is recorded.</p>
  <ol>
    <li><b>Y39 and Y201</b> (along the length, x = 0 wall to x = 480 wall). Lift the seven cones on that line
    first; their positions are already on video. Tie the cord so it crosses every T cord exactly at the 39 in
    (or 201 in) mark: 27 in above tick 12, or 27 in above tick 174. Keep it taut and on the ground.</li>
    <li><b>X60 and X420</b> (across, lower value): 36 in inside cords T1 and T7, wall to wall, through the
    V/F1 and V/F6 cone positions.</li>
    <li>Everyone out of view 60 s again and write the time.</li>
  </ol>
  <div class="rec">
    <label for="t-step5">Step 5, cords: which ones, PC time<input id="t-step5" type="text" placeholder="Y39 Y201 · HH:MM:SS – HH:MM:SS" data-k="t-step5"></label>
  </div>
</section>

<section>
  <h2>What this changes</h2>
  <p>Share of the paddock by how many cameras can map a rat's back there, and the mapped share for the four
  small cameras. A camera maps only inside the area its own labels surround, so cones at the edge of its view
  widen it. Areas mapped by two or more cameras are where the tracks can be cross-checked and blended at a
  handoff instead of switched.</p>
  <div class="tbl"><table>
    <thead><tr><th>After</th><th>0 cameras</th><th>1 camera</th><th>2+ cameras</th><th>CH03</th><th>CH04</th><th>CH05</th><th>CH06</th></tr></thead>
    <tbody>{sc_rows}</tbody>
  </table></div>
  <p class="note">What the four small cameras can see at all: {SEEN_TXT}
  of the paddock. More coverage does not by itself mean smaller jumps: the new cones first measure how far apart
  two cameras put the same point, then the ground correction is refitted with them. The worst place today is the
  x = 480 end (around T74 and T75 two cameras put the same board corner 15&ndash;23 cm apart; CH01 against CH04 is the worst pair overall), which is why the T7 cones and C3, C4 are marked first.</p>
</section>

<footer>
  <div><b>After the field</b> (desk work, no cameras touched): label the cones in all six cameras with
  <code>cone_gui.py</code> on the step 4 frame, trace any new cords with <code>line_gui.py</code>, then refit only
  the ground correction (<code>frame_correction.py</code>) and rerun the three checks. The board bundle does not
  change. {WORDS.get(N_UNLAB, N_UNLAB).capitalize()} station cones that were visible on 2026-09-18 but never labelled can still be labelled from that footage ({UNLAB_TXT}). Code to add first: the new cone IDs in <code>fit_data.LATTICE</code>, Y cords in
  <code>line_gui.py</code> and <code>frame_correction.py</code>, and a guard so the extra cord points do not switch
  CH03/CH04 from an affine to a degree-3 correction by accident.</div>
  <div>Source: coverage analysis of the 2026-09-24 release fit (<code>camera_fit.npz</code>, sha {SHA}…), reproduced
  on the lab PC 2026-09-26 with the same mapping to within 0.1 mm. Positions and numbers: <code>calibration_qc/cone_supplement.py</code>, sheet: <code>cone_sheet.py</code>. Visibility threshold: a cone at least 12 px per 10 cm in the image.</div>
</footer>
</div>

<script>
(function () {{
  var KEY = "handoff-cone-sheet-v1", state = {{}};
  try {{ state = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{ state = {{}}; }}
  function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}} }}
  document.querySelectorAll("[data-k]").forEach(function (el) {{
    var k = el.getAttribute("data-k");
    if (el.type === "checkbox") {{
      if (state[k]) el.checked = true;
      el.addEventListener("change", function () {{ state[k] = el.checked; save(); }});
    }} else {{
      if (state[k]) el.value = state[k];
      el.addEventListener("input", function () {{ state[k] = el.value; save(); }});
    }}
  }});
}})();
</script>
"""
OUT.write_text(html, encoding="utf-8")
print("->", OUT, len(html), "bytes;", N_FIRST, "first:", sorted(FIRST))
