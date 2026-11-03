# -*- coding: utf-8 -*-
"""
生成项目首页 reports/index.html：把历史趋势页和所有日期的复盘看板串成一个入口。

用法：python -m ashare.site
"""
import os
import re

from .data import ROOT
from .web import CSS
from . import config as C

MK = C.MARKET_NAME

REPORTS = os.path.join(ROOT, "reports")


def _scan():
    """收集所有已生成的产物，按日期倒序"""
    items = {}
    if not os.path.isdir(REPORTS):
        return []
    for fn in os.listdir(REPORTS):
        m = re.match(r"dashboard_(\d{8})_(am|pm)\.html", fn)
        if m:
            d, s = m.group(1), m.group(2)
            items.setdefault(d, {}).setdefault("dash", {})[s] = fn
            continue
        m = re.match(r"(\d{8})_(am|pm)\.md", fn)
        if m:
            d, s = m.group(1), m.group(2)
            items.setdefault(d, {}).setdefault("md", {})[s] = fn
    out = []
    for d in sorted(items, reverse=True):
        row = {"date": d, "label": f"{d[:4]}-{d[4:6]}-{d[6:]}", **items[d]}
        out.append(row)
    return out


def render():
    items = _scan()
    has_hist = os.path.exists(os.path.join(REPORTS, "history.html"))

    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append("<title>{MK} 复盘 · 存档</title>")
    h.append(f"<style>{CSS}"
             ".entry{display:flex;align-items:center;justify-content:space-between;"
             "padding:14px 16px;border-bottom:1px solid #f2f3f5}"
             ".entry:last-child{border-bottom:none}"
             ".entry .d{font-size:14px;font-weight:500;color:#1f2328;font-variant-numeric:tabular-nums}"
             ".link{display:inline-block;padding:4px 12px;border-radius:7px;font-size:12.5px;"
             "text-decoration:none;background:#eef2f8;color:#1a4d8f;margin-left:8px}"
             ".link:hover{background:#e2eaf6}"
             ".link.mut{background:#f4f5f7;color:#6b7280}"
             ".big{display:block;padding:18px 20px;border-radius:12px;background:#f0f5fc;"
             "text-decoration:none;color:#1a4d8f;font-size:14px;font-weight:500}"
             ".big span{display:block;font-size:12px;font-weight:400;color:#5f7ba8;margin-top:3px}"
             "</style></head><body><div class='wrap'>")
    h.append('<div class="hd"><h1>{MK} 复盘</h1>'
             '<span class="sub">市场宽度 · 资金结构 · 连板梯队 · 波动区间</span></div>')

    if has_hist:
        h.append('<div class="card" style="padding:14px">'
                 '<a class="big" href="history.html">市场温度历史趋势'
                 '<span>121 个交易日的温度、涨跌家数、涨停数、成交额</span></a></div>')

    h.append('<div class="card" style="padding:0">')
    if not items:
        h.append('<div class="entry"><span class="d">还没有任何报告</span>'
                 '<span class="link mut">先运行 run_review.py</span></div>')
    for row in items:
        dash = row.get("dash", {})
        md = row.get("md", {})
        links = []
        if "am" in dash:
            links.append(f'<a class="link" href="{dash["am"]}">午盘看板</a>')
        if "pm" in dash:
            links.append(f'<a class="link" href="{dash["pm"]}">收盘看板</a>')
        if not links:
            for s, lab in (("am", "午盘"), ("pm", "收盘")):
                if s in md:
                    links.append(f'<a class="link mut" href="{md[s]}">{lab}文字版</a>')
        h.append(f'<div class="entry"><span class="d">{row["label"]}</span>'
                 f'<span>{"".join(links)}</span></div>')
    h.append("</div>")

    h.append('<div class="ft">看板为单文件静态页，可离线打开、可直接分享　·　'
             '数据：腾讯财经 / 新浪 / baostock　·　不构成投资建议</div>')
    h.append("</div></body></html>")
    return "".join(h).replace("{MK}", MK)


def main():
    html = render()
    os.makedirs(REPORTS, exist_ok=True)
    out = os.path.join(REPORTS, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {out}")


if __name__ == "__main__":
    main()
