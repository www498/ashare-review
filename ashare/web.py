# -*- coding: utf-8 -*-
"""
静态看板生成器：把一份快照渲染成单文件 HTML。

为什么是单文件静态页：
- 演示现场断网也能打开，不依赖 CDN、不需要起服务
- 一份文件就能拷给别人看，截图也干净
- 图表全部手绘 SVG，没有外部依赖

用法：python -m ashare.web [--session am|pm] [--date 20261102]
"""
import argparse
import datetime as dt
import json
import os

from .data import ROOT
from . import config as C

MK = C.MARKET_NAME

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;
     color:#1f2328;line-height:1.6;padding:28px 20px 60px}
.wrap{max-width:1080px;margin:0 auto}
.hd{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}
h1{font-size:22px;font-weight:600;letter-spacing:-.3px}
.sub{color:#6b7280;font-size:13px}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:500}
.b-hot{background:#fdecea;color:#b3261e}
.b-cool{background:#e8f0fe;color:#1a56b3}
.b-mid{background:#f1f3f4;color:#5f6368}
.warn{background:#fff8e1;border-left:3px solid #f0b429;padding:10px 14px;border-radius:6px;
      font-size:13px;margin:14px 0;color:#7a5c00}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}
.kpi{background:#fff;border:1px solid #e6e8eb;border-radius:12px;padding:14px 16px}
.kpi .lab{font-size:12px;color:#6b7280;margin-bottom:4px}
.kpi .val{font-size:24px;font-weight:600;letter-spacing:-.5px}
.kpi .val small{font-size:13px;font-weight:400;color:#6b7280;margin-left:3px}
.up{color:#c5221f}.down{color:#0b8043}.flat{color:#5f6368}
.card{background:#fff;border:1px solid #e6e8eb;border-radius:12px;padding:18px 20px;margin-bottom:14px}
.card h2{font-size:14px;font-weight:600;color:#3c4043;margin-bottom:2px}
/* 板块折叠：标题可点，整体收起/展开。用 class 控制而非内联 style，
   避免和各板块自己的内联样式打架 */
.card > h2{cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.card > h2::before{content:"";display:inline-block;width:0;height:0;flex:0 0 auto;
  border-left:5px solid #9aa0a8;border-top:4px solid transparent;
  border-bottom:4px solid transparent;transform:rotate(90deg);
  transition:transform .18s}
.card.fold > h2::before{transform:rotate(0deg)}
.card > h2:hover::before{border-left-color:#2f5fa8}
.card.fold > *:not(h2){display:none !important}
.card.fold{padding-bottom:16px}
.foldbar{display:flex;gap:8px;justify-content:flex-end;margin-bottom:10px}
.foldbar button{background:#fff;border:1px solid #dfe3e8;border-radius:7px;
  color:#5f6368;font-size:12px;padding:5px 12px;cursor:pointer;font-family:inherit}
.foldbar button:hover{border-color:#2f5fa8;color:#1a4d8f}
.card .hint{font-size:12px;color:#8a8f98;margin-bottom:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.two{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-weight:500;color:#6b7280;font-size:12px;padding:6px 8px;
   border-bottom:1px solid #eceef1}
td{padding:8px;border-bottom:1px solid #f4f5f7}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
.tag{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11.5px;background:#f1f3f4;color:#5f6368}
.tag.warn2{background:#fdecea;color:#b3261e}
ol.acts{list-style:none;counter-reset:a}
ol.acts li{counter-increment:a;position:relative;padding:10px 0 10px 34px;font-size:13.5px;
           border-bottom:1px dashed #eef0f2}
ol.acts li:last-child{border-bottom:none}
ol.acts li::before{content:counter(a);position:absolute;left:0;top:10px;width:22px;height:22px;
   border-radius:50%;background:#e8f0fe;color:#1a56b3;font-size:12px;font-weight:600;
   display:flex;align-items:center;justify-content:center}
.ft{color:#8a8f98;font-size:12px;margin-top:24px;line-height:1.9}
.legend{display:flex;gap:16px;font-size:12px;color:#6b7280;margin-top:10px}
.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.dstrip{display:grid;grid-template-columns:repeat(3,1fr);gap:18px 24px}
@media(max-width:700px){.dstrip{grid-template-columns:repeat(2,1fr)}}
.ditem .dl{font-size:11.5px;color:#8a8f98;margin-bottom:3px}
.ditem .dv{font-size:13px;color:#3c4043;font-variant-numeric:tabular-nums}
.ditem .dv b{font-size:15px;font-weight:600}
.ar{display:inline-block;margin-left:6px;font-size:11.5px;padding:1px 6px;border-radius:9px}
.ar.up{background:#fdecea;color:#b3261e}.ar.down{background:#e6f4ea;color:#0b5c31}
.ar.nm{background:#f1f3f4;color:#5f6368}
tr.exp{cursor:pointer}
tr.exp:hover{background:#fafbfc}
tr.exp .car{color:#c2c7cf;font-size:9px;margin-left:5px;display:inline-block;
            transition:transform .15s ease,color .15s}
tr.exp.on .car{transform:rotate(90deg);color:#2f5fa8}
tr.det{display:none}
tr.det.open{display:table-row}
tr.det>td{background:#fbfcfd;border-bottom:1px solid #eef0f3;padding:0}
.detbox{padding:14px 16px;display:flex;gap:26px;flex-wrap:wrap;align-items:flex-start}
.dcell{min-width:120px;flex:0 0 auto}
.dcell .t{font-size:11.5px;color:#8a8f98;margin-bottom:5px}
.dhint{font-size:12px;color:#8a8f98;margin-top:12px}
.ovgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(252px,1fr));
  gap:10px;margin-top:14px}
.ovitem{border:1px solid #eef0f3;border-radius:10px;padding:11px 13px;background:#fcfdfe}
.ovk{font-size:11.5px;color:#8a8f98;margin-bottom:3px}
.ovv{font-size:19px;font-weight:650;color:#1f2328;font-variant-numeric:tabular-nums}
.ovv.up{color:#d94b4b}.ovv.down{color:#2b8560}
.ovn{font-size:12px;color:#5f6368;margin-top:5px;line-height:1.65}
.ovi{font-size:11.5px;color:#8a8f98;margin-top:6px;line-height:1.7;
  padding-top:6px;border-top:1px dashed #eef0f3}
.tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.tg{font-size:12px;padding:4px 11px;border-radius:999px;cursor:default;font-weight:500}
.tg.warn{background:#fdecea;color:#b3261e}
.tg.good{background:#e7f5ec;color:#0b5c31}
.tg.info{background:#eef2f8;color:#1a4d8f}
.findings{margin-top:14px;display:flex;flex-direction:column;gap:9px}
.fd{border-left:3px solid #e4e7ec;padding:2px 0 2px 11px}
.fdt{font-size:13px;color:#1f2328;font-weight:600}
.fdt b{color:#1a4d8f;font-weight:600;margin-left:7px;font-variant-numeric:tabular-nums}
.fdi{font-size:12px;color:#5f6368;line-height:1.75;margin-top:4px}
.hbar{display:flex;align-items:center;gap:9px;margin-bottom:6px}
.hbar .hl{font-size:12px;color:#5f6368;width:50px;flex:0 0 auto}
.hbar .hb{flex:1;height:15px;background:#f2f4f6;border-radius:4px;overflow:hidden}
.hbar .hb i{display:block;height:100%;border-radius:4px}
.hbar .hv{font-size:12px;color:#3c4043;width:56px;text-align:right;flex:0 0 auto;
  font-variant-numeric:tabular-nums}
"""

NOTE_STYLE = "font-size:12px;color:#8a8f98;margin-top:10px"


def _c(v):
    """涨跌配色：A股习惯红涨绿跌"""
    if v is None:
        return "flat"
    return "up" if v > 0.005 else ("down" if v < -0.005 else "flat")


def _pct(v, nd=2):
    return f"{v:+.{nd}f}%" if v is not None else "—"


def _yi(v):
    return f"{v:,.0f}"


# ---------------- 图表 ----------------

def chart_temperature(total, band):
    segs = [(0, 25, "#cfe0f5", "冰点"), (25, 45, "#a9c6ea", "偏冷"),
            (45, 62, "#e3e6ea", "中性"), (62, 85, "#f2b8b2", "偏热"),
            (85, 100, "#dd8b84", "过热")]
    W, H = 600, 74
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img">']
    for lo, hi, color, _ in segs:
        x, w = lo / 100 * W, (hi - lo) / 100 * W
        active = lo <= total < hi or (total >= 100 and hi == 100)
        stroke = ' stroke="#1f2328" stroke-width="1.5"' if active else ""
        out.append(f'<rect x="{x:.1f}" y="30" width="{w:.1f}" height="22" fill="{color}"{stroke}/>')
    mx = total / 100 * W
    out.append(f'<polygon points="{mx:.1f},20 {mx - 5:.1f},28 {mx + 5:.1f},28" fill="#1f2328"/>')
    out.append(f'<line x1="{mx:.1f}" y1="30" x2="{mx:.1f}" y2="52" stroke="#1f2328" stroke-width="2"/>')
    out.append(f'<text x="{mx:.1f}" y="13" text-anchor="middle" font-size="13" '
               f'font-weight="700" fill="#1f2328">{total:.1f}</text>')
    for lo, hi, _, name in segs:
        cx = (lo + hi) / 2 / 100 * W
        active = lo <= total < hi or (total >= 100 and hi == 100)
        out.append(f'<text x="{cx:.1f}" y="66" text-anchor="middle" font-size="11" '
                   f'font-weight="{"600" if active else "400"}" '
                   f'fill="{"#1f2328" if active else "#93989f"}">{name}</text>')
    out.append("</svg>")
    return "".join(out)


def chart_breadth(b):
    W, H = 600, 46
    tot = max(1, b["up"] + b["down"] + b["flat"])
    wu, wf = b["up"] / tot * W, b["flat"] / tot * W
    wd = W - wu - wf
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">']
    out.append(f'<rect x="0" y="8" width="{wu:.1f}" height="20" fill="#e8b4b0"/>')
    out.append(f'<rect x="{wu:.1f}" y="8" width="{wf:.1f}" height="20" fill="#dadce0"/>')
    out.append(f'<rect x="{wu + wf:.1f}" y="8" width="{wd:.1f}" height="20" fill="#a8d5bd"/>')
    if wu > 60:
        out.append(f'<text x="{wu / 2:.1f}" y="22" text-anchor="middle" font-size="11.5" '
                   f'fill="#8c1d18">{b["up"]} 涨</text>')
    if wd > 60:
        out.append(f'<text x="{wu + wf + wd / 2:.1f}" y="22" text-anchor="middle" font-size="11.5" '
                   f'fill="#0b5c31">{b["down"]} 跌</text>')
    out.append(f'<text x="0" y="44" font-size="11" fill="#8a8f98">'
               f'上涨占比 {b["up_ratio"]:.1%}　平盘 {b["flat"]} 只</text>')
    out.append("</svg>")
    return "".join(out)


def chart_trend(series):
    if not series or len(series) < 3:
        return ""
    W, H, PAD = 600, 170, 26
    vals = [float(x[1]) for x in series]
    n = len(vals)
    xs = [PAD + i / (n - 1) * (W - 2 * PAD) for i in range(n)]
    ys = [H - 40 - (v / 100) * (H - 70) for v in vals]
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">']
    for g in (25, 45, 62, 85):
        gy = H - 40 - (g / 100) * (H - 70)
        out.append(f'<line x1="{PAD}" y1="{gy:.1f}" x2="{W - PAD}" y2="{gy:.1f}" '
                   f'stroke="#eef0f3" stroke-width="1" stroke-dasharray="3 3"/>')
        out.append(f'<text x="{PAD - 5}" y="{gy + 3:.1f}" text-anchor="end" font-size="9.5" '
                   f'fill="#b0b5bd">{g}</text>')
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    out.append(f'<polygon points="{xs[0]:.1f},{H - 40} {pts} {xs[-1]:.1f},{H - 40}" '
               f'fill="#e8f0fe" opacity="0.65"/>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="#2f5fa8" stroke-width="2" '
               f'stroke-linejoin="round"/>')
    out.append(f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4" fill="#2f5fa8"/>')
    out.append(f'<text x="{xs[-1]:.1f}" y="{ys[-1] - 10:.1f}" text-anchor="end" font-size="11.5" '
               f'font-weight="600" fill="#2f5fa8">{vals[-1]:.1f}</text>')
    out.append(f'<text x="{PAD}" y="{H - 12}" font-size="10" fill="#a0a5ad">{series[0][0]}</text>')
    out.append(f'<text x="{W - PAD}" y="{H - 12}" text-anchor="end" font-size="10" '
               f'fill="#a0a5ad">{series[-1][0]}</text>')
    out.append("</svg>")
    return "".join(out)


def chart_ladder(ladder):
    if not ladder:
        return ""
    rows = ladder
    mx = max(len(items) for _, items in rows) or 1
    out = ['<div style="display:flex;flex-direction:column;gap:8px">']
    for board, items in rows:
        w = 8 + 82 * (len(items) / mx) ** 0.45
        col = "#c5221f" if board >= 3 else ("#e07a5f" if board == 2 else "#f0c9c5")
        names = "、".join(n for _, n, _ in items[:7])
        if len(items) > 7:
            names += f" 等 {len(items)} 只"
        out.append(
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<div style="width:38px;text-align:right;font-size:12px;color:#6b7280">{board} 板</div>'
            f'<div style="flex:1;display:flex;align-items:center;gap:8px">'
            f'<div style="width:{w}%;height:22px;background:{col};border-radius:4px;min-width:22px"></div>'
            f'<span style="font-size:12px;color:#5f6368">{len(items)} 家　'
            f'<span style="color:#8a8f98">{names}</span></span></div></div>')
    out.append("</div>")
    return "".join(out)


def chart_range(fc):
    if not fc:
        return ""
    devs = []
    for r in fc:
        devs += [abs(r["lo"] / r["price"] - 1), abs(r["hi"] / r["price"] - 1)]
    mx = max(devs) * 100 if devs else 1
    W = 600
    out = []
    for r in fc:
        lo = (r["lo"] / r["price"] - 1) * 100
        hi = (r["hi"] / r["price"] - 1) * 100
        x0 = W / 2 + lo / mx * (W / 2 - 10)
        x1 = W / 2 + hi / mx * (W / 2 - 10)
        half = max(abs(lo), abs(hi))
        out.append(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:9px">'
            f'<div style="width:60px;font-size:12.5px;color:#3c4043">{r["name"]}</div>'
            f'<div style="flex:1"><svg viewBox="0 0 {W} 26" width="100%" height="26">'
            f'<line x1="10" y1="13" x2="{W - 10}" y2="13" stroke="#f0f2f5" stroke-width="1"/>'
            f'<line x1="{W / 2}" y1="5" x2="{W / 2}" y2="21" stroke="#d8dbe0" stroke-width="1" '
            f'stroke-dasharray="2 2"/>'
            f'<rect x="{x0:.1f}" y="8" width="{max(3, x1 - x0):.1f}" height="10" rx="5" '
            f'fill="#cfdff5"/>'
            f'<circle cx="{W / 2}" cy="13" r="3" fill="#2f5fa8"/>'
            f'</svg></div>'
            f'<div style="width:132px;text-align:right;font-size:12px;color:#6b7280;'
            f'font-variant-numeric:tabular-nums">{r["lo"]:,.2f} ~ {r["hi"]:,.2f}</div>'
            f'<div style="width:52px;text-align:right;font-size:12px;color:#8a8f98">'
            f'±{half:.1f}%</div></div>')
    return "".join(out)


def chart_industry(inds, top=6):
    """自有口径的行业涨幅榜。东财板块接口不可用时用它兜底，
    好处是与报告里的宽度指标完全同源，不会出现两套数字打架。
    跌榜只从真正为负的行业里取 —— 普涨日负值少，宁缺毋滥，不拿正数凑数。"""
    pos = [r for r in inds if r["median"] > 0][:top]
    neg = [r for r in inds if r["median"] < 0][-top:][::-1]
    rows = pos + neg
    if not rows:
        return ""
    mx = max(abs(r["median"]) for r in rows) or 1
    out = []
    for r in rows:
        w = max(1.2, abs(r["median"]) / mx * 46)
        is_pos = r["median"] >= 0
        col = "#c5221f" if is_pos else "#0b8043"
        left = "left:50%" if is_pos else f"left:{50 - w:.1f}%"
        out.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12.5px">'
            f'<div style="width:76px;text-align:right;color:#3c4043">{r["industry"]}</div>'
            f'<div style="flex:1;position:relative;height:18px">'
            f'<div style="position:absolute;left:50%;top:0;width:1px;height:18px;background:#e6e8eb"></div>'
            f'<div style="position:absolute;top:3px;height:12px;border-radius:3px;background:{col};'
            f'{left};width:{w:.1f}%"></div></div>'
            f'<div style="width:66px;text-align:right;color:#6b7280;font-variant-numeric:tabular-nums">'
            f'{r["median"]:+.2f}%</div></div>')
    return "".join(out)


def spark_hist(vals, w=150, h=36):
    """近 20 日收盘走势缩略图"""
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    if mx - mn < 1e-9:
        mx = mn + 1
    pts = " ".join(f"{i / (len(vals) - 1) * (w - 4) + 2:.1f},"
                   f"{h - 3 - (v - mn) / (mx - mn) * (h - 6):.1f}"
                   for i, v in enumerate(vals))
    col = "#c5221f" if vals[-1] >= vals[0] else "#0b8043"
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6" '
            f'stroke-linejoin="round"/></svg>')


def spark_intraday(pts, prev_close, w=180, h=44):
    """今日分时，以昨收为基准线：线上红、线下绿"""
    if not pts or not prev_close or len(pts) < 3:
        return ""
    vals = [p[1] for p in pts]
    lo, hi = min(min(vals), prev_close), max(max(vals), prev_close)
    if hi - lo < 1e-9:
        hi = lo + 1
    up = vals[-1] >= prev_close
    col = "#c5221f" if up else "#0b8043"
    fill = "#fbe9e7" if up else "#e6f4ea"
    y = lambda v: h - 3 - (v - lo) / (hi - lo) * (h - 6)
    line = " ".join(f"{i / (len(vals) - 1) * (w - 4) + 2:.1f},{y(v):.1f}"
                    for i, v in enumerate(vals))
    area = f"2,{h - 3} {line} {w - 2},{h - 3}"
    by = y(prev_close)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<polygon points="{area}" fill="{fill}" opacity="0.7"/>'
            f'<line x1="2" y1="{by:.1f}" x2="{w - 2}" y2="{by:.1f}" stroke="#c9ced6" '
            f'stroke-width="1" stroke-dasharray="3 3"/>'
            f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.6" '
            f'stroke-linejoin="round"/></svg>')


def _delta_chip(v, suffix="", digits=1, invert=False):
    if v is None:
        return ""
    good = (v <= 0) if invert else (v >= 0)
    cls = "up" if good else "down"
    return f'<span class="ar {cls}">{v:+.{digits}f}{suffix}</span>'


def _sec_delta(h, ctx):
    d = ctx.get("delta")
    if not d:
        return
    b = ctx["breadth"]
    h.append('<div class="card"><h2>日环比</h2>'
             f'<div class="hint">与上一交易日 {d["date"]} 对比</div>')
    h.append('<div class="dstrip">')
    items = [
        ("市场温度", f'{d["temp_prev"]:.1f} → <b>{ctx["temperature"]["total"]:.1f}</b>',
         _delta_chip(d["temp"])),
        ("涨停家数", f'{d["limit_up_prev"]} → <b>{b["limit_up"]}</b>',
         _delta_chip(d["limit_up"], "", 0)),
        ("{MK} 成交额", f'{d["amount_prev"]:,.0f} → <b>{b["amount_yi"]:,.0f}</b> 亿',
         _delta_chip(d["amount_pct"], "%")),
        ("涨幅中位数", f'{d["median_prev"]:+.2f}% → <b>{b["median_pct"]:+.2f}%</b>',
         _delta_chip(d["median_pct"], "pp", 2)),
        ("上涨家数", f'<b>{b["up"]}</b> 涨 / {b["down"]} 跌',
         _delta_chip(d["up"], "", 0)),
        ("上证涨跌", f'{d["idx_pct_prev"]:+.2f}% → <b>{d["idx_pct"]:+.2f}%</b>',
         _delta_chip(round(d["idx_pct"] - d["idx_pct_prev"], 2), "pp", 2)),
    ]
    for lab, val, chip in items:
        h.append(f'<div class="ditem"><div class="dl">{lab}</div>'
                 f'<div class="dv">{val}{chip}</div></div>')
    h.append("</div></div>")


def _sec_portfolio(h, ctx):
    p = ctx.get("portfolio")
    h.append('<div class="card"><h2>持仓'
             '<span class="wbp-slot" data-slot="pos"></span></h2>')
    if not p or not p.get("rows"):
        h.append('<div class="hint">还没有持仓数据。点上面的「导入持仓」，'
                 '粘贴券商导出的持仓表或交割单即可，数量与成本会自动算出来。</div>')
        h.append("</div>")
        return
    h.append('<div class="hint">只统计在持仓文件里填了「数量,成本价」的标的</div>')
    h.append('<div class="dstrip" style="margin-bottom:16px">')
    items = [
        ("总市值", f'<b>{p["total_mv"]:,.0f}</b> 元', ""),
        ("总浮盈", f'<b class="{_c(p["total_pnl"])}">{p["total_pnl"]:+,.0f}</b> 元',
         _delta_chip(p["total_pnl_pct"], "%", 2)),
        ("今日盈亏", f'<b class="{_c(p["total_today"])}">{p["total_today"]:+,.0f}</b> 元',
         _delta_chip(p["total_today_pct"], "%", 2)),
    ]
    for lab, val, chip in items:
        h.append(f'<div class="ditem"><div class="dl">{lab}</div><div class="dv">{val}{chip}</div></div>')
    h.append("</div>")

    h.append('<table><tr><th>名称</th><th class="n">数量</th><th class="n">成本</th>'
             '<th class="n">现价</th><th class="n">市值</th><th class="n">浮盈</th>'
             '<th class="n">盈亏率</th><th class="n">今日</th><th style="width:70px">占比</th></tr>')
    for r in p["rows"]:
        w = r["weight"] or 0
        h.append(f'<tr><td>{r["name"]}</td>'
                 f'<td class="n">{r["shares"]:,.0f}</td>'
                 f'<td class="n">{r["cost"]:,.2f}</td>'
                 f'<td class="n">{r["price"]:,.2f}</td>'
                 f'<td class="n">{r["mv"]:,.0f}</td>'
                 f'<td class="n {_c(r["pnl"])}">{r["pnl"]:+,.0f}</td>'
                 f'<td class="n {_c(r["pnl_pct"])}">{_pct(r["pnl_pct"])}</td>'
                 f'<td class="n {_c(r["today"])}">{r["today"]:+,.0f}</td>'
                 f'<td><div style="background:#f1f3f4;border-radius:3px;height:7px;width:100%">'
                 f'<div style="background:#9fb6d9;height:7px;border-radius:3px;width:{w:.0f}%"></div>'
                 f'</div><span style="font-size:10.5px;color:#8a8f98">{w:.0f}%</span></td></tr>')
    h.append("</table>")
    h.append(f'<div style="{NOTE_STYLE}">成本价按你填的数值计算，未考虑手续费与分红送转；'
             f'今日盈亏按（现价 − 昨收）× 数量估算。</div>')
    h.append("</div>")


def _sec_index_strip(h, ctx):
    """除上证外的其他指数，压成一行，避免 KPI 区被六个大卡片撑爆"""
    idxs = ctx.get("indices") or []
    if len(idxs) < 2:
        return
    h.append('<div class="card" style="padding:13px 18px">')
    h.append('<div style="display:flex;flex-wrap:wrap;gap:8px 28px;font-size:12.5px;'
             'align-items:baseline">')
    for name, q in idxs[1:]:
        h.append(f'<span style="color:#6b7280">{name}　'
                 f'<b style="color:#1f2328;font-variant-numeric:tabular-nums">'
                 f'{q["price"]:,.2f}</b>　'
                 f'<span class="{_c(q["pct"])}" style="font-variant-numeric:tabular-nums">'
                 f'{_pct(q["pct"])}</span></span>')
    h.append("</div></div>")


def chart_sector(sec):
    rows = [(n, p, a) for n, p, a in sec["top"]] + [(n, p, a) for n, p, a in sec["bottom"]]
    if not rows:
        return ""
    mx = max(abs(a) for _, _, a in rows) or 1
    out = []
    for n, p, a in rows:
        w = max(1.2, abs(a) / mx * 46)
        pos = a >= 0
        col = "#c5221f" if pos else "#0b8043"
        left = "left:50%" if pos else f"left:{50 - w:.1f}%"
        out.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12.5px">'
            f'<div style="width:76px;text-align:right;color:#3c4043">{n}</div>'
            f'<div style="flex:1;position:relative;height:18px">'
            f'<div style="position:absolute;left:50%;top:0;width:1px;height:18px;background:#e6e8eb"></div>'
            f'<div style="position:absolute;top:3px;height:12px;border-radius:3px;background:{col};'
            f'{left};width:{w:.1f}%"></div></div>'
            f'<div style="width:66px;text-align:right;color:#6b7280;font-variant-numeric:tabular-nums">'
            f'{a / 1e8:+.1f} 亿</div></div>')
    return "".join(out)


# ---------------- 组装 ----------------

def _kpi(lab, val, sub="", cls=""):
    return (f'<div class="kpi"><div class="lab">{lab}</div>'
            f'<div class="val {cls}">{val}<small>{sub}</small></div></div>')


def chart_dist(dist):
    """九档涨跌分布柱状图。红涨绿跌，与行情软件配色一致。"""
    labels, counts = dist["labels"], dist["counts"]
    if not counts or not any(counts):
        return ""
    W, H, PAD = 680, 150, 24
    n = len(counts)
    bw = (W - PAD * 2) / n
    mx = max(counts) or 1
    cols = ["#d94b4b", "#e4736b", "#eb8f87", "#f0aaa3", "#9aa0a8",
            "#86c6a4", "#5fb389", "#3f9c72", "#2b8560"]
    s = [f'<svg viewBox="0 0 {W} {H + 34}" width="100%" height="{H + 34}">']
    for i, c in enumerate(counts):
        bh = max(2.0, c / mx * (H - 26))
        x = PAD + i * bw + bw * 0.14
        w = bw * 0.72
        y = H - bh
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bh:.1f}" '
                 f'rx="3" fill="{cols[i]}"/>')
        s.append(f'<text x="{x + w / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                 f'font-size="11" fill="#3c4043" font-weight="600">{c}</text>')
        s.append(f'<text x="{x + w / 2:.1f}" y="{H + 15:.1f}" text-anchor="middle" '
                 f'font-size="10" fill="#8a8f98">{labels[i]}</text>')
    s.append("</svg>")
    return "".join(s)


def _sec_overview(h, ctx):
    """市场概况：九档分布 + 指标含义。对标行情软件首页但解释更完整。"""
    dist, ov = ctx.get("dist"), ctx.get("overview")
    if not dist and not ov:
        return
    h.append('<div class="card"><h2>市场概况</h2>')
    if dist and dist.get("total"):
        cnt = dict(zip(dist["labels"], dist["counts"]))
        strong = cnt.get("涨停", 0) + cnt.get("涨停-5%", 0) + cnt.get("5-1%", 0)
        weak = cnt.get("跌停", 0) + cnt.get("-5%-跌停", 0) + cnt.get("-1--5%", 0)
        h.append(f'<div class="hint">涨幅 1% 以上 {strong} 只，跌幅 1% 以上 {weak} 只。'
                 f'分布形态比涨跌家数更能说明问题</div>')
        h.append(chart_dist(dist))
    if ov:
        h.append('<div class="ovgrid">')
        for r in ov:
            cls = {"up": "up", "down": "down"}.get(r.get("tone"), "")
            h.append(f'<div class="ovitem"><div class="ovk">{r["key"]}</div>'
                     f'<div class="ovv {cls}">{r["value"]}</div>')
            if r.get("note"):
                h.append(f'<div class="ovn">{r["note"]}</div>')
            h.append(f'<div class="ovi">{r["impact"]}</div></div>')
        h.append("</div>")
    h.append("</div>")


def _sec_profile(h, ctx):
    """交易行为画像。产品差异点：不只分析市场，也分析用户自己。

    没有交割单时也渲染卡片：画像必须从成交流水算（持仓表只有「现在持有什么」，
    没有买卖记录，算不出胜率与持有天数）。整块静默消失会让人以为功能没了，
    所以给一个空状态和导入入口。
    """
    p = ctx.get("profile")
    if not p:
        h.append('<div class="card"><h2>交易行为画像'
                 '<span class="wbp-slot" data-slot="prof"></span></h2>')
        h.append('<div class="hint">还没有交割单。行为画像需要<b>成交流水</b>'
                 '（哪天买了什么、卖了多少），只有持仓表算不出来。</div>')
        h.append('<div class="hint" style="color:#8a8f98">'
                 '在券商 App 里导出「交割单 / 对账单」，点上面的「导入交割单」粘贴即可，'
                 '会自动还原持仓、含费成本，并算出胜率、盈亏比、持有天数。</div>')
        h.append("</div>")
        return
    c = p["core"]
    span = ""
    if c.get("first_day"):
        span = f'{c["first_day"]} ~ {c["last_day"]}，'
    h.append('<div class="card"><h2>交易行为画像</h2>'
             f'<div class="hint">{span}{c.get("trades_total", 0)} 笔成交，'
             f'FIFO 配对出 {c["n_closed"]} 笔已完成交易，全部来自交割单真实记录</div>')

    if p.get("tags"):
        h.append('<div class="tags">')
        for name, basis, level in p["tags"]:
            h.append(f'<span class="tg {level}" title="{basis}">{name}</span>')
        h.append("</div>")

    kpis = [("已实现盈亏", f'{c["realized_pnl"]:+,.0f}', "元",
             "up" if c["realized_pnl"] >= 0 else "down")]
    if c.get("unrealized_pnl") is not None:
        u = c["unrealized_pnl"]
        kpis.append(("持仓浮动", f"{u:+,.0f}", "元", "up" if u >= 0 else "down"))
        tot = c["realized_pnl"] + u
        kpis.append(("合计", f"{tot:+,.0f}", "元", "up" if tot >= 0 else "down"))
    if c.get("win_rate") is not None:
        kpis.append(("胜率", f'{c["win_rate"]:.0%}', f'{c["n_win"]}/{c["n_closed"]}', ""))
    if c.get("profit_factor") is not None:
        pf = c["profit_factor"]
        kpis.append(("盈亏比", f"{pf:.2f}", "总盈/总亏", "up" if pf >= 1.5 else "down"))
    if c.get("hold_avg") is not None:
        kpis.append(("平均持有", f'{c["hold_avg"]:.1f}', "天", ""))
    kpis.append(("累计手续费", f'{c["fee_total"]:,.0f}', "元", ""))
    h.append('<div class="kpis" style="margin-top:12px">')
    for lab, val, unit, tone in kpis:
        h.append(f'<div class="kpi"><div class="k">{lab}</div>'
                 f'<div class="v {tone}">{val}<span class="u">{unit}</span></div></div>')
    h.append("</div>")

    if c.get("hold_win") and c.get("hold_loss"):
        hw, hl = c["hold_win"], c["hold_loss"]
        mxv = max(hw, hl) or 1
        h.append('<div style="margin-top:14px">')
        h.append('<div class="t" style="margin-bottom:6px">盈利单 vs 亏损单 持有天数</div>')
        for lab, v, col in [("盈利单", hw, "#d94b4b"), ("亏损单", hl, "#3f9c72")]:
            h.append(f'<div class="hbar"><span class="hl">{lab}</span>'
                     f'<span class="hb"><i style="width:{v / mxv * 100:.0f}%;'
                     f'background:{col}"></i></span>'
                     f'<span class="hv">{v:.1f} 天</span></div>')
        h.append("</div>")

    if p.get("findings"):
        h.append('<div class="findings">')
        for title, value, impact in p["findings"]:
            h.append(f'<div class="fd"><div class="fdt">{title}'
                     f'<b>{value}</b></div><div class="fdi">{impact}</div></div>')
        h.append("</div>")

    if p.get("per_stock"):
        h.append('<table style="margin-top:14px"><tr><th>标的</th>'
                 '<th class="n">已完成</th><th class="n">累计盈亏</th>'
                 '<th class="n">胜率</th><th class="n">平均持有</th></tr>')
        for s in p["per_stock"]:
            cls = "up" if s["pnl"] >= 0 else "down"
            hold = f'{s["hold_avg"]:.1f} 天' if s.get("hold_avg") is not None else "—"
            wr = f'{s["win_rate"]:.0%}' if s.get("win_rate") is not None else "—"
            h.append(f'<tr><td>{s["name"]}</td><td class="n">{s["n"]}</td>'
                     f'<td class="n {cls}">{s["pnl"]:+,.0f}</td>'
                     f'<td class="n">{wr}</td><td class="n">{hold}</td></tr>')
        h.append("</table>")
        h.append(f'<div style="{NOTE_STYLE}">按累计盈亏升序，排最前的最需要复盘。'
                 f'同一只票反复亏损，问题通常不在行情而在交易方式。</div>')
    h.append("</div>")


def render_html(ctx):
    s = ctx["session"]
    tag = "午盘" if s == "am" else "收盘"
    b, t = ctx["breadth"], ctx["temperature"]
    idx = ctx["indices"][0]
    band_cls = "b-hot" if t["total"] >= 62 else ("b-cool" if t["total"] < 45 else "b-mid")

    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append(f'<title>{MK} 复盘 {ctx["date"]} {tag}</title>')
    h.append(f"<style>{CSS}</style></head><body><div class='wrap'>")

    h.append('<div class="hd">')
    h.append(f'<h1>{MK} {tag}复盘</h1>')
    h.append(f'<span class="sub">{ctx["date"]}　行情时点 {ctx.get("quote_ts", "--:--")}'
             f'　取数 {ctx.get("latency", "-")}</span>')
    h.append(f'<span class="badge {band_cls}">{t["band"]} {t["total"]:.1f}</span>')
    h.append('<span class="wbp-hdact"></span>')
    h.append("</div>")

    if ctx.get("warning"):
        h.append(f'<div class="warn">{ctx["warning"]}</div>')

    # KPI
    h.append('<div class="kpis">')
    h.append(_kpi("上证指数", f'{idx[1]["price"]:,.2f}',
                  f'　{_pct(idx[1]["pct"])}', _c(idx[1]["pct"])))
    h.append(_kpi("{MK} 成交额", _yi(b["amount_yi"]), " 亿"))
    h.append(_kpi("涨跌家数", f'{b["up"]} / {b["down"]}', " 涨/跌", "up"))
    h.append(_kpi("涨幅中位数", _pct(b["median_pct"]), "", _c(b["median_pct"])))
    h.append(_kpi("涨停 / 跌停", f'{b["limit_up"]} / {b["limit_down"]}', ""))
    h.append("</div>")

    _sec_index_strip(h, ctx)

    # 板块折叠工具条：放在所有卡片之前
    h.append('<div class="foldbar" id="foldbar">'
             '<button class="f-none" type="button">全部展开</button>'
             '<button class="f-all" type="button">全部收起</button>'
             '</div>')

    # 日环比（仅收盘：半日指标与昨日全日不可比）
    if s == "pm":
        _sec_delta(h, ctx)

    _sec_portfolio(h, ctx)

    _sec_overview(h, ctx)

    # 温度 + 宽度
    h.append('<div class="two">')
    h.append('<div class="card"><h2>市场温度</h2>'
             '<div class="hint">五项各 20 分，自建相对指标，看趋势不看绝对值</div>')
    h.append(chart_temperature(t["total"], t["band"]))
    sub = t["sub"]
    h.append('<div class="legend">')
    for k, lab in [("breadth", "宽度"), ("limit", "涨跌停"), ("index", "指数"),
                   ("volume", "量能"), ("median", "中位数")]:
        h.append(f'<span>{lab} {sub[k]:.0f}</span>')
    h.append("</div></div>")

    h.append('<div class="card"><h2>涨跌分布</h2>'
             f'<div class="hint">{b["n"]} 只{MK} 个股，含已停牌外的全部在市标的</div>')
    h.append(chart_breadth(b))
    h.append(f'<div style="{NOTE_STYLE}">涨幅 90 分位 {_pct(b["p90"])}　'
             f'10 分位 {_pct(b["p10"])}　振幅中位数 {b["median_amp"]:.2f}%</div>')
    h.append("</div></div>")

    # 趋势（仅收盘）
    tr = ctx.get("trend")
    if s == "pm" and tr:
        h.append('<div class="card"><h2>温度趋势</h2>'
                 f'<div class="hint">近 {len(tr["series"])} 个交易日，'
                 f'当前处于 {tr["pctile"]:.0f}% 分位　5 日均 {tr["ma5"]:.1f}　'
                 f'10 日均 {tr["ma10"]:.1f}</div>')
        h.append(chart_trend(tr["series"]))
        h.append("</div>")

    # 连板（收盘）/ 上午盘面（午盘）
    lad = ctx.get("ladder")
    if s == "pm" and lad and lad["ladder"]:
        h.append('<div class="card"><h2>连板梯队</h2>'
                 f'<div class="hint">{"数据截至今日" if lad.get("has_today") else "历史基准 " + lad["asof"]}　'
                 f'最高 {lad["max_board"]} 板　'
                 f'昨日涨停股今日平均 {lad["perf"]["avg"]:+.2f}%　'
                 f'红盘率 {lad["perf"]["red"]:.0%}</div>')
        h.append(chart_ladder(lad["ladder"]))
        promo = [(bd, v) for bd, v in lad["promotion"] if v["total"] >= 2]
        if promo:
            chips = "　".join(f"{bd}→{bd+1} 板 {v['ok']}/{v['total']}（{v['ok']/v['total']:.0%}）"
                             for bd, v in sorted(promo, key=lambda x: -x[0]))
            h.append(f'<div style="{NOTE_STYLE}">晋级率：{chips}</div>')
        h.append("</div>")

    if s == "am":
        st, bk = ctx.get("strength") or {}, ctx.get("broken") or {}
        h.append('<div class="card"><h2>上午盘面特征</h2>'
                 '<div class="hint">收盘后会消失的两个指标：上午收盘位置、炸板率</div>')
        h.append('<div class="two" style="gap:20px">')
        h.append('<div>')
        if st:
            h.append(f'<div class="kpi" style="border:none;padding:0">'
                     f'<div class="lab">上午收盘位置（中位数）</div>'
                     f'<div class="val">{st["median"]:.2f}</div>'
                     f'<div style="{NOTE_STYLE}">1 = 收在上午最高，0 = 收在最低　'
                     f'{st["near_high"]} 只贴近最高（{st["near_high_ratio"]:.0%}）</div></div>')
        h.append("</div><div>")
        if bk:
            h.append(f'<div class="kpi" style="border:none;padding:0">'
                     f'<div class="lab">炸板率</div>'
                     f'<div class="val">{(bk["rate"] or 0):.0%}</div>'
                     f'<div style="{NOTE_STYLE}">{bk["hit"]} 只摸过涨停，'
                     f'{bk["sealed"]} 只封住、{bk["broken"]} 只炸板</div></div>')
        h.append("</div></div>")
        if bk and bk.get("names"):
            h.append(f'<div style="{NOTE_STYLE}">炸板个股：'
                     + "、".join(f'{n}（{p:+.2f}%）' for n, p in bk["names"]) + "</div>")
        h.append("</div>")

    # 自选股（可点开看详情）
    det_all = ctx.get("detail") or {}
    h.append('<div class="card"><h2>自选股'
             '<span class="wbp-slot" data-slot="wl"></span></h2>'
             '<div class="hint">点击任意一行展开今日分时与近 20 日走势　·　'
             '偏离所属行业中位数 1 个百分点以内视为跟随板块</div>')
    h.append('<table><tr><th>名称</th><th class="n">现价</th><th class="n">涨跌幅</th>'
             '<th class="n">振幅</th><th class="n">量比</th><th>所属行业</th>'
             '<th class="n">行业中位数</th><th>判断</th></tr>')
    for a in ctx["anomalies"]:
        at = a.get("attr") or {}
        verdict = at.get("verdict", "—")
        vcls = "tag warn2" if verdict in ("强于板块", "弱于板块") else "tag"
        d = det_all.get(a["code"]) or {}
        has = bool(d.get("intraday") or d.get("hist20"))
        caret = '<span class="car">▸</span>' if has else ""
        h.append(f'<tr class="exp"><td>{a["name"]}{caret}</td>'
                 f'<td class="n">{a["price"]:,.2f}</td>'
                 f'<td class="n {_c(a["pct"])}">{_pct(a["pct"])}</td>'
                 f'<td class="n">{a["amp"]:.1f}%</td><td class="n">{a["vol_ratio"]:.1f}</td>'
                 f'<td>{at.get("industry", "—")}</td>'
                 f'<td class="n">{_pct(at["ind_median"]) if at else "—"}</td>'
                 f'<td><span class="{vcls}">{verdict}</span></td></tr>')

        if not has:
            continue
        h.append('<tr class="det"><td colspan="8"><div class="detbox">')
        if d.get("intraday"):
            h.append(f'<div class="dcell"><div class="t">今日分时（虚线为昨收 '
                     f'{d.get("prev_close") or 0:,.2f}）</div>'
                     f'{spark_intraday(d["intraday"], d.get("prev_close"))}</div>')
        if d.get("hist20"):
            vals = [x[1] for x in d["hist20"]]
            h.append(f'<div class="dcell"><div class="t">近 20 个交易日</div>'
                     f'{spark_hist(vals)}</div>')
        bits = []
        if d.get("prev_pct") is not None:
            bits.append(f'昨日 <b class="{_c(d["prev_pct"])}">{_pct(d["prev_pct"])}</b>')
        if at:
            bits.append(f'{at["industry"]} 行业中位数 {_pct(at["ind_median"])}，'
                        f'偏离 {at["gap"]:+.2f}pp → {verdict}')
        if a.get("reasons"):
            bits.append("触发条件：" + "、".join(a["reasons"]))
        h.append(f'<div class="dcell" style="min-width:260px;font-size:12.5px;color:#5f6368">'
                 f'<div class="t">明细</div>' + "<br>".join(bits) + "</div>")

        # 诊断块（整行宽）
        card = (ctx.get("cards") or {}).get(a["code"])
        if card:
            h.append('<div class="dcell" style="flex:1 0 100%;border-top:1px solid #eef0f3;'
                     'padding-top:12px;margin-top:4px">')
            h.append(f'<div class="t">诊断</div>'
                     f'<div style="font-size:12.5px;color:#3c4043;margin-bottom:9px;'
                     f'max-width:720px">{card["summary"]}</div>')
            h.append('<div style="display:flex;flex-wrap:wrap;gap:6px 20px;margin-bottom:10px">')
            for k, v in card["metrics"]:
                h.append(f'<span style="font-size:12px;color:#8a8f98">{k} '
                         f'<b style="color:#3c4043;font-variant-numeric:tabular-nums">{v}</b></span>')
            h.append("</div><ul style='margin:0;padding-left:16px;font-size:12.5px;color:#5f6368'>")
            for n in card["watch"]:
                h.append(f"<li style='margin-bottom:3px'>{n}</li>")
            h.append("</ul></div>")
        h.append("</div></td></tr>")
    h.append("</table>")
    if det_all:
        h.append('<div class="dhint">共 ' + str(len(ctx["anomalies"])) +
                 ' 只自选股，其中 ' + str(sum(1 for a in ctx["anomalies"]
                                              if (det_all.get(a["code"]) or {}).get("intraday"))) +
                 ' 只带分时数据。</div>')
    h.append("</div>")

    # 波动区间
    if ctx.get("forecast"):
        h.append('<div class="card"><h2>未来 5 日波动区间</h2>'
                 '<div class="hint">80% 经验分位区间，蓝点为现价。不预测方向，只给波动包络</div>')
        h.append(chart_range(ctx["forecast"]))
        cov = sum(r["coverage"] for r in ctx["forecast"]) / len(ctx["forecast"])
        r2s = sorted(r["r2"] for r in ctx["forecast"])
        r2_med = r2s[len(r2s) // 2]
        neg = sum(1 for x in r2s if x <= 0)
        h.append(f'<div style="{NOTE_STYLE}">滚动样本外覆盖率均值 {cov:.0%}（目标 80%）　'
                 f'模型 R² 中位数 {r2_med:.2f}'
                 f'{f"，{neg} 只标的为负（波动率不可预测）" if neg else ""}'
                 f'　区间宽度随个股波动率自动缩放</div>')
        h.append("</div>")

    # 板块：优先东财资金流，不可用时退回自有行业涨幅口径
    if ctx.get("sector"):
        h.append('<div class="card"><h2>板块资金流</h2>'
                 '<div class="hint">主力净流入，右为流入、左为流出</div>')
        h.append(chart_sector(ctx["sector"]))
        h.append("</div>")
    elif ctx.get("industry"):
        h.append('<div class="card"><h2>行业涨幅榜</h2>'
                 '<div class="hint">基于本次快照的{MK} 全量个股自算，与上方宽度指标同源</div>')
        h.append(chart_industry(ctx["industry"]))
        h.append(f'<div style="{NOTE_STYLE}">东财板块资金流接口暂不可用，此处改用自有行业口径（按行业中位数涨跌幅排序）</div>')
        h.append("</div>")

    # 行动
    view = ctx.get("session_view") or []
    if view:
        title = "下午盯这几点" if s == "am" else "明天做这几件事"
        h.append(f'<div class="card"><h2>{title}</h2>'
                 f'<div class="hint">{"每条都能在下午收盘前被验证" if s == "am" else "每条都是明天开盘可直接执行的动作"}</div>')
        h.append('<ol class="acts">')
        for line in view:
            h.append(f"<li>{line}</li>")
        h.append("</ol></div>")

    _sec_profile(h, ctx)

    if ctx.get("ai"):
        ai = ctx["ai"]
        ok = ai.get("verified")
        badge = "数字已校验" if ok else "未通过数字校验"
        h.append(f'<div class="card"><h2>AI 解读 <span class="tag">{badge}</span></h2>'
                 f'<div class="hint">大模型基于上述数据生成，所有数字来自计算层</div>')
        h.append('<div style="font-size:13.5px;white-space:pre-wrap">' + ai["text"] + "</div></div>")

    h.append('<div class="ft">'
             '数据：腾讯财经（{MK} 全量实时快照）· 新浪日K（历史回补）· baostock（前复权、行业分类）<br>'
             '涨停判定按当日涨停价（主板 10%、创业板/科创板 20%、北交所 30%）；量能基准按行情时点折算<br>'
             '本页为历史与实时数据的统计描述，不构成投资建议'
             "</div>")
    h.append("<script>"
             "document.querySelectorAll('tr.exp').forEach(function(tr){"
             "tr.addEventListener('click',function(){"
             "var d=tr.nextElementSibling;"
             "if(!d||!d.classList.contains('det'))return;"
             "d.classList.toggle('open');tr.classList.toggle('on');});});"
             "var KEY='ashare_fold_'+(document.title||'');"
             "var saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){}"
             "var cards=document.querySelectorAll('.card');"
             "cards.forEach(function(c,i){"
             "var h2=c.querySelector(':scope > h2');if(!h2)return;"
             "var id=(h2.textContent||'').trim()||('card'+i);"
             "if(saved[id]){c.classList.add('fold');}"
             "h2.addEventListener('click',function(){"
             "c.classList.toggle('fold');"
             "saved[id]=c.classList.contains('fold');"
             "try{localStorage.setItem(KEY,JSON.stringify(saved));}catch(e){}"
             "});});"
             "var bar=document.getElementById('foldbar');"
             "if(bar){"
             "bar.querySelector('.f-all').addEventListener('click',function(){"
             "cards.forEach(function(c,i){var h2=c.querySelector(':scope > h2');"
             "if(!h2)return;c.classList.add('fold');"
             "saved[(h2.textContent||'').trim()||('card'+i)]=true;});"
             "try{localStorage.setItem(KEY,JSON.stringify(saved));}catch(e){}});"
             "bar.querySelector('.f-none').addEventListener('click',function(){"
             "cards.forEach(function(c,i){var h2=c.querySelector(':scope > h2');"
             "if(!h2)return;c.classList.remove('fold');"
             "saved[(h2.textContent||'').trim()||('card'+i)]=false;});"
             "try{localStorage.setItem(KEY,JSON.stringify(saved));}catch(e){}});"
             "}"
             "</script>")
    h.append("</div></body></html>")
    return "".join(h).replace("{MK}", MK)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="pm", choices=["am", "pm"])
    ap.add_argument("--date", default=dt.date.today().strftime("%Y%m%d"))
    a = ap.parse_args()

    snap = os.path.join(ROOT, "data", "snapshots", f"{a.date}_{a.session}.json")
    if not os.path.exists(snap):
        raise SystemExit(f"没有快照 {snap}，先跑一次 run_review.py")
    with open(snap, encoding="utf-8") as f:
        ctx = json.load(f)

    html = render_html(ctx)
    try:
        from .context import reports_dir
        _rd = reports_dir()
    except Exception:
        _rd = os.path.join(ROOT, "reports")
    out = os.path.join(_rd, f"dashboard_{a.date}_{a.session}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {out}  （{len(html) / 1024:.0f} KB）")


if __name__ == "__main__":
    main()
