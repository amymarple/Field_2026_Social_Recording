# -*- coding: utf-8 -*-
"""Generate the printable CH01/02 calibration record sheet (diagram + log table)."""
import io

FIELD_X, FIELD_Y = 1219.2, 609.6
TRAIN_X = [60, 240, 420, 600, 780, 960, 1140]
TRAIN_Y = [30, 150, 270, 390, 510]
VT_X = [150, 330, 510, 690, 870, 1050]
VT_Y = [90, 210, 330, 450]
POLES = {  # name -> (x, y)
    **{f"A{i}": (i * 304.8, 0.0) for i in range(5)},
    **{f"B{i}": (i * 304.8, 304.8) for i in range(5)},
    **{f"C{i}": (i * 304.8, 609.6) for i in range(5)},
}
SHELTERS = [  # (cx, cy, w, h) after 90-deg orientation: long axis along y
    (342.6, 304.8, 45.72, 62.55),
    (881.5, 302.4, 45.72, 62.55),
]
CAMS = [("CH01", 599.8, 148.7, +1), ("CH02", 632.8, 459.6, -1)]  # aim ~ +y / -y

stations = []  # (id, set, x, y)
for li, x in enumerate(TRAIN_X, 1):
    for si, y in enumerate(TRAIN_Y, 1):
        stations.append((f"T{li}{si}", "训练", x, y))
for i, x in enumerate(VT_X, 1):
    for j, y in enumerate(VT_Y, 1):
        s = "验证" if (i + j) % 2 == 0 else "终测"
        stations.append((f"{'V' if s=='验证' else 'F'}{i}{j}", s, x, y))

n_train = sum(1 for s in stations if s[1] == "训练")
n_val = sum(1 for s in stations if s[1] == "验证")
n_tst = sum(1 for s in stations if s[1] == "终测")
assert (n_train, n_val, n_tst) == (35, 12, 12), (n_train, n_val, n_tst)

# ---------------- SVG diagram (y flipped: field y up = svg y down inverted) ----------
M = 46  # margin
W, H = FIELD_X + 2 * M, FIELD_Y + 2 * M
def sx(x): return M + x
def sy(y): return M + (FIELD_Y - y)

svg = io.StringIO()
svg.write(f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" '
          f'font-family="Arial, sans-serif">\n')
svg.write(f'<rect x="{sx(0)}" y="{sy(FIELD_Y)}" width="{FIELD_X}" height="{FIELD_Y}" '
          f'fill="none" stroke="#000" stroke-width="2.5"/>\n')
# measuring lines (training x-lines)
for x in TRAIN_X:
    svg.write(f'<line x1="{sx(x)}" y1="{sy(0)}" x2="{sx(x)}" y2="{sy(FIELD_Y)}" '
              f'stroke="#999" stroke-width="0.8" stroke-dasharray="6 5"/>\n')
    svg.write(f'<text x="{sx(x)}" y="{sy(0)+16}" font-size="12" text-anchor="middle">x={x}</text>\n')
# y ticks on left edge
for y in TRAIN_Y + VT_Y:
    svg.write(f'<text x="{sx(0)-6}" y="{sy(y)+4}" font-size="12" text-anchor="end">{y}</text>\n')
# poles
for name, (x, y) in POLES.items():
    svg.write(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="5.5" fill="#000"/>\n')
    dy = -9 if y < FIELD_Y else 18
    svg.write(f'<text x="{sx(x)}" y="{sy(y)+dy}" font-size="14" font-weight="bold" text-anchor="middle">{name}</text>\n')
# shelters
for cx, cy, w, h in SHELTERS:
    svg.write(f'<rect x="{sx(cx)-w/2}" y="{sy(cy)-h/2}" width="{w}" height="{h}" '
              f'fill="none" stroke="#000" stroke-width="1.5"/>\n')
    svg.write(f'<text x="{sx(cx)}" y="{sy(cy)+4}" font-size="9" text-anchor="middle">箱</text>\n')
# cameras + approx seam trace
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
    if st == "训练":
        svg.write(f'<rect x="{X-5}" y="{Y-5}" width="10" height="10" fill="#000"/>\n')
        lab_dy = -8
    elif st == "验证":
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
            '<td class="w"></td><td class="w"></td><td class="c"></td>'
            '<td class="c"></td><td class="c"></td><td class="note"></td></tr>')

rows = [row(*s[:2], s[2], s[3]) for s in stations]
for i in range(1, 7):
    rows.append(row(f"S{i}", "接缝*", None, None))
for i in range(1, 7):
    rows.append(row(f"X{i}", "补/移", None, None))

def table(rws):
    return ('<table><thead><tr><th>ID</th><th>集合</th><th>目标x</th><th>目标y</th>'
            '<th>实测x (cm)</th><th>实测y (cm)</th><th>两点对齐</th><th>放稳8-10s</th>'
            '<th>QC过</th><th>备注 (遮挡/移位/高度)</th></tr></thead><tbody>'
            + "".join(rws) + '</tbody></table>')

# split rows across pages: 36 / rest
t1, t2 = table(rows[:36]), table(rows[36:])

html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>CH01/02 标定放板记录表</title>
<style>
 @page {{ size: letter landscape; margin: 9mm; }}
 body {{ font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 11px; margin: 0; color: #000; }}
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
 <h1>CH01/CH02 标定放板 — 放样图 &nbsp;<span style="font-weight:normal;font-size:12px">
 (PLAN_CH01_CH02_pano_ground_map.md v2 · 板: ChArUco 12×9 @60mm, DICT_5X5_100 · 长边72cm沿+x)</span></h1>
 <div class="meta">
  <div>日期:</div><div>操作者:</div><div>天气/光线:</div><div>手机−PC钟差: ______ s</div>
  <div>连续5格实测 x向: ____ mm (应300)</div><div>y向: ____ mm</div><div>板厚: ____ mm</div><div>草高(典型): ____ cm</div>
  <div>场地长边1: ______ cm</div><div>长边2: ______ cm</div><div>对角线1: ______ cm</div><div>对角线2: ______ cm</div>
  <div>线离地高度(典型): ____ cm</div><div>地面点标记方式: 漆 / 粉笔 / ____</div><div></div><div></div>
 </div>
 {svg_str}
 <div class="legend" style="margin-top:2px">
  <span>■ 训练 T (35)</span><span>○ 验证 V (12)</span><span>◇+ 终测 F (12)</span>
  <span>● 杆 (A/B/C 0-4)</span><span>◆ 相机</span><span>┊ 接缝走向(近似, 以预检帧为准)</span>
 </div>
 <div class="rules">
  <b>每个板位:</b> ① 板原点角 + 长边第二参考点 两点对齐实测标记(只量原点会丢旋转) ② 压稳贴草, 板面平
  ③ 人不遮挡任何相机到板的视线(侧移2–3米即可, 入镜无妨) ④ 保持 8–10 秒 ⑤ 表上勾选并记实测坐标(偏离目标就写实际值) 。
  <b>铁律:</b> 场上永远只有一块板 · 锥桶只做找位参考不进画面控制点 · 目标坐标≠记录坐标, 一律记实测 ·
  接缝S行位置由预检帧现场定 · 每完成一批呼叫远程QC验角点再继续 · 离场前等 _to_ 闭合并验收+备份。
  <b>地面板位同时服务 CH03/04</b>(全相机同录, 集合归属共享), 无需重复放板。
  <b>标记纪律:</b> 全场一切哑光, 严禁反光带(炸高光/IR blooming 毁角点) · 站位识别靠 时间+顺序+位置自洽,
  相机无需看到ID(可选: 每条线开始举哑光号码纸2秒) · 线贴地拉紧只做放样和直线验证;
  每个刻度垂直向下用哑光标记漆点到地面, <u>对齐与测量一律以地面漆点为准</u>(真z=0), 并记线离地高度。
 </div>
 <h2 style="margin-top:6px">CH03/04 内参扫板(插在放板批次间的等待里做)</h2>
 <table>
  <thead><tr><th>相机</th><th>开始时间</th><th>结束时间</th><th>有效姿态数 (目标20–30)</th>
  <th>覆盖画面边缘?</th><th>QC过</th><th>备注</th></tr></thead>
  <tbody>
   <tr><td class="id">CH03</td><td class="w"></td><td class="w"></td><td></td><td class="c"></td><td class="c"></td><td class="note"></td></tr>
   <tr><td class="id">CH04</td><td class="w"></td><td class="w"></td><td></td><td class="c"></td><td class="c"></td><td class="note"></td></tr>
  </tbody>
 </table>
 <div class="foot">扫板: 手持板在相机前变 距离/上下左右/倾角(±30–45°), 每姿态停稳1–2秒; 先 CH03 → 远程QC确认检出质量 → 再 CH04。板勿反光角度直对太阳。</div>
</div>

<div class="page">
 <h2>记录表 1/2 — 训练 T11–T75 (35) + 验证/终测起始</h2>
 {t1}
 <div class="foot">集合规则: V/F 按棋盘格交替预分配, 不得现场改集合; 移位的板位记实测坐标, 集合不变。</div>
</div>

<div>
 <h2>记录表 2/2 — 验证/终测(续) + 接缝 S1–S6 + 补拍/移位 X1–X6</h2>
 {t2}
 <div class="foot">* 接缝行: 先看两台预检帧确定接缝实际落点, 近/中/远各一组, 两侧都采; 坐标现场实测填入。
 QC过 = 远程抽帧确认该板位角点合格。</div>
</div>

</body></html>"""

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CALIB_RECORD_SHEET_CH0102.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("stations:", len(stations), "train/val/test:", n_train, n_val, n_tst)
print("wrote", out)
