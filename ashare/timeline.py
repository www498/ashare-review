# -*- coding: utf-8 -*-
"""
历史趋势页：把 breadth_history.csv 里 120 个交易日的宽度数据渲染成一张图。

这是唯一有足够历史样本的视图，回答的是「今天的温度处在什么位置」，
而不是「今天怎么样」。四联图共享横轴：
    温度 / 涨跌家数（上下对称） / 涨停家数 / 成交额

用法：python -m ashare.timeline
输出：reports/history.html
"""
import os

import pandas as pd

from .data import ROOT
from .history import HIST_CSV
from .web import CSS
from . import config as C

MK = C.MARKET_NAME

PAD_L, PAD_R, PAD_T = 46, 14, 12


def _x(i, n, W):
    if n <= 1:
        return PAD_L
    return PAD_L + i / (n - 1) * (W - PAD_L - PAD_R)


def _axis_dates(dates, W, y):
    n = len(dates)
    step = max(1, n // 8)
    out = []
    for i in range(0, n, step):
        anchor = "start" if i == 0 else ("end" if i >= n - step else "middle")
        out.append(f'<text x="{_x(i, n, W):.1f}" y="{y}" text-anchor="{anchor}" '
                   f'font-size="10" fill="#a0a5ad">{dates[i]}</text>')
    return "".join(out)


def _line_panel(vals, dates, W, H, color, fill, refs=(), fmt="{:.0f}", ymax=None, title=""):
    n = len(vals)
    lo, hi = 0, ymax or max(vals) * 1.12 or 1
    ph = H - PAD_T - 26

    def y(v):
        return PAD_T + ph - (v - lo) / (hi - lo) * ph

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">']
    for r in refs:
        out.append(f'<line x1="{PAD_L}" y1="{y(r):.1f}" x2="{W - PAD_R}" y2="{y(r):.1f}" '
                   f'stroke="#eef0f3" stroke-width="1" stroke-dasharray="3 3"/>')
        out.append(f'<text x="{PAD_L - 5}" y="{y(r) + 3:.1f}" text-anchor="end" font-size="9.5" '
                   f'fill="#b0b5bd">{r}</text>')
    pts = " ".join(f"{_x(i, n, W):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    out.append(f'<polygon points="{_x(0, n, W):.1f},{y(lo):.1f} {pts} '
               f'{_x(n - 1, n, W):.1f},{y(lo):.1f}" fill="{fill}" opacity="0.75"/>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6" '
               f'stroke-linejoin="round"/>')
    out.append(f'<circle cx="{_x(n - 1, n, W):.1f}" cy="{y(vals[-1]):.1f}" r="3.2" fill="{color}"/>')
    out.append(f'<text x="{_x(n - 1, n, W) - 4:.1f}" y="{y(vals[-1]) - 7:.1f}" text-anchor="end" '
               f'font-size="11" font-weight="600" fill="{color}">{fmt.format(vals[-1])}</text>')
    out.append(_axis_dates(dates, W, H - 8))
    out.append("</svg>")
    return "".join(out)


def _mirror_panel(up, down, dates, W, H, title=""):
    n = len(up)
    ph = H - PAD_T - 26
    mid = PAD_T + ph / 2
    mx = max(max(up), max(down)) or 1

    def y(v, is_up):
        h = v / mx * (ph / 2)
        return mid - h if is_up else mid + h

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">']
    out.append(f'<line x1="{PAD_L}" y1="{mid:.1f}" x2="{W - PAD_R}" y2="{mid:.1f}" '
               f'stroke="#e6e8eb" stroke-width="1"/>')
    pu = " ".join(f"{_x(i, n, W):.1f},{y(v, True):.1f}" for i, v in enumerate(up))
    pd = " ".join(f"{_x(i, n, W):.1f},{y(v, False):.1f}" for i, v in enumerate(down))
    out.append(f'<polygon points="{_x(0, n, W):.1f},{mid:.1f} {pu} '
               f'{_x(n - 1, n, W):.1f},{mid:.1f}" fill="#e8b4b0" opacity="0.8"/>')
    out.append(f'<polygon points="{_x(0, n, W):.1f},{mid:.1f} {pd} '
               f'{_x(n - 1, n, W):.1f},{mid:.1f}" fill="#a8d5bd" opacity="0.8"/>')
    out.append(f'<text x="{PAD_L - 5}" y="{mid - ph / 2 + 10:.1f}" text-anchor="end" '
               f'font-size="9.5" fill="#b0b5bd">{mx:.0f}</text>')
    out.append(f'<text x="{PAD_L - 5}" y="{mid + ph / 2:.1f}" text-anchor="end" '
               f'font-size="9.5" fill="#b0b5bd">{mx:.0f}</text>')
    out.append(_axis_dates(dates, W, H - 8))
    out.append("</svg>")
    return "".join(out)


def _bar_panel(vals, dates, W, H, color, fmt="{:.0f}"):
    n = len(vals)
    ph = H - PAD_T - 26
    mx = max(vals) or 1
    bw = max(1.5, (W - PAD_L - PAD_R) / n * 0.62)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">']
    for i, v in enumerate(vals):
        h = v / mx * ph
        out.append(f'<rect x="{_x(i, n, W) - bw / 2:.1f}" y="{PAD_T + ph - h:.1f}" '
                   f'width="{bw:.1f}" height="{max(0.8, h):.1f}" fill="{color}" opacity="0.85"/>')
    out.append(f'<text x="{PAD_L - 5}" y="{PAD_T + 8}" text-anchor="end" font-size="9.5" '
               f'fill="#b0b5bd">{mx:.0f}</text>')
    out.append(_axis_dates(dates, W, H - 8))
    out.append("</svg>")
    return "".join(out)


def render():
    if not os.path.exists(HIST_CSV):
        return None
    df = pd.read_csv(HIST_CSV, encoding="utf-8-sig").sort_values("date").reset_index(drop=True)
    if len(df) < 5:
        return None

    dates = [str(d)[5:] for d in df["date"]]
    temp = [float(x) for x in df["temp"]]
    up = [int(x) for x in df["up"]]
    down = [int(x) for x in df["down"]]
    lu = [int(x) for x in df["limit_up"]]
    amt = [float(x) for x in df["amount_yi"]]

    W, H = 900, 168
    up_days = sum(1 for x, y in zip(up, down) if x > y)
    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append("<title>{MK} 市场温度历史</title>")
    h.append(f"<style>{CSS}</style></head><body><div class='wrap'>")
    h.append('<div class="hd"><h1>{MK} 市场温度</h1>'
             f'<span class="sub">近 {len(df)} 个交易日　{dates[0]} — {dates[-1]}</span></div>')

    h.append('<div class="kpis">')
    for lab, val, sub, cls in [
        ("当前温度", f"{temp[-1]:.1f}", "", "up" if temp[-1] >= 62 else ""),
        ("区间均值", f"{sum(temp) / len(temp):.1f}", "", ""),
        ("最高 / 最低", f"{max(temp):.0f} / {min(temp):.0f}", "", ""),
        ("上涨天数占比", f"{up_days / len(df):.0%}", "", ""),
        ("日均成交额", f"{sum(amt) / len(amt):,.0f}", " 亿", ""),
    ]:
        h.append(f'<div class="kpi"><div class="lab">{lab}</div>'
                 f'<div class="val {cls}">{val}<small>{sub}</small></div></div>')
    h.append("</div>")

    h.append('<div class="card"><h2>市场温度</h2>'
             '<div class="hint">虚线为分档阈值 25 / 45 / 62 / 85，80 以上为过热</div>')
    h.append(_line_panel(temp, dates, W, H, "#2f5fa8", "#e8f0fe",
                         refs=(25, 45, 62, 85), fmt="{:.1f}", ymax=100))
    h.append("</div>")

    h.append('<div class="card"><h2>涨跌家数</h2>'
             '<div class="hint">上半为上涨家数，下半为下跌家数，中间为零轴</div>')
    h.append(_mirror_panel(up, down, dates, W, H))
    h.append("</div>")

    h.append('<div class="two">')
    h.append('<div class="card"><h2>涨停家数</h2>'
             '<div class="hint">单日涨停数量，反映短线情绪强弱</div>')
    h.append(_bar_panel(lu, dates, W // 2, 130, "#c5221f"))
    h.append("</div>")
    h.append('<div class="card"><h2>{MK} 成交额</h2>'
             '<div class="hint">单位：亿元</div>')
    h.append(_line_panel(amt, dates, W // 2, 130, "#5f6b7a", "#eceff3", fmt="{:,.0f}"))
    h.append("</div></div>")

    # 多日对比：今日 / 昨日 / 5 日前 / 20 日前
    picks = [("今日", -1), ("昨日", -2), ("5 日前", -6), ("20 日前", -21)]
    picks = [(lab, i) for lab, i in picks if len(df) >= abs(i)]
    if len(picks) >= 2:
        h.append('<div class="card"><h2>多日对比</h2>'
                 '<div class="hint">同一组指标在不同交易日的读数，用来看变化方向</div>')
        head = "".join(f'<th class="n">{lab}<br><span style="font-weight:400;color:#b0b5bd">'
                       f'{df["date"].iloc[i]}</span></th>' for lab, i in picks)
        h.append(f'<table><tr><th>指标</th>{head}</tr>')
        rows = [
            ("市场温度", "temp", "{:.1f}"),
            ("上涨家数", "up", "{:.0f}"),
            ("下跌家数", "down", "{:.0f}"),
            ("涨停家数", "limit_up", "{:.0f}"),
            ("涨幅中位数", "median_pct", "{:+.2f}%"),
            ("上证涨跌", "idx_pct", "{:+.2f}%"),
            ("成交额", "amount_yi", "{:,.0f} 亿"),
        ]
        for label, col, fmt in rows:
            cells = "".join(f'<td class="n">{fmt.format(float(df[col].iloc[i]))}</td>'
                            for _, i in picks)
            h.append(f"<tr><td>{label}</td>{cells}</tr>")
        h.append("</table></div>")

    h.append('<div class="ft">数据：新浪日K 回补 + 每日快照累积　·　'
             '温度是自建相对指标，只在纵向比较时才有意义　·　不构成投资建议</div>')
    h.append("</div></body></html>")
    return "".join(h).replace("{MK}", MK)


def main():
    html = render()
    if not html:
        raise SystemExit("没有历史数据，先运行 python -m ashare.history")
    try:
        from .context import reports_dir
        _rd = reports_dir()
    except Exception:
        _rd = os.path.join(ROOT, "reports")
    out = os.path.join(_rd, "history.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {out}（{len(html) / 1024:.0f} KB）")


if __name__ == "__main__":
    main()
