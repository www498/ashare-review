# -*- coding: utf-8 -*-
"""
个股详情与昨日对比。

1. detail —— 点开自选股时展示：今日分时（腾讯 267 点，5 分钟采样）、近 20 日走势、
   昨日涨跌幅。全部预先算好塞进快照，页面本身不联网。
2. delta —— 与上一交易日的日环比，从 breadth_history.csv 取，不额外请求。
"""
import os
import pickle

import pandas as pd
import requests

from .data import ROOT, sym
from .history import HIST_CSV

MIN_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={sym}"
KLINE_CACHE = os.path.join(ROOT, "data", "klines_cache.pkl")
HDRS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
SAMPLE = 5   # 分时采样间隔（分钟）


def minute_series(sym, step=SAMPLE):
    """今日分时，返回 [[hhmm, price], ...]。拉不到返回空列表，页面自动省略这一块。"""
    try:
        r = requests.get(MIN_URL.format(sym=sym), headers=HDRS, timeout=10)
        rows = r.json()["data"][sym]["data"]["data"]
    except Exception:
        return []
    out, last = [], len(rows) - 1
    for i, line in enumerate(rows):
        parts = line.split()
        if len(parts) < 2:
            continue
        t = parts[0]
        try:
            mins = int(t[:2]) * 60 + int(t[2:])
        except Exception:
            continue
        if (mins - 570) % step == 0 or i == last:
            out.append([t, round(float(parts[1]), 2)])
    return out


def _load_cache():
    if not os.path.exists(KLINE_CACHE):
        return {}, None
    with open(KLINE_CACHE, "rb") as f:
        c = pickle.load(f)
    data = c.get("data", {})
    closes = {code: {d: px for d, px, _ in rows} for code, rows in data.items()}
    pct = None
    if closes:
        cdf = pd.DataFrame(closes).sort_index()
        pct = cdf.pct_change() * 100
        pct = pct.mask(pct.abs() > 21.5)   # 剔除除权跳空
    return data, pct


def watch_detail(codes, quotes, name_map=None):
    """为每只自选股准备详情。缓存只读一次。"""
    data, pct = _load_cache()
    name_map = name_map or {}
    out = {}
    for code in codes:
        q = quotes.get(code) or {}
        rows = data.get(code) or []
        # 近 20 日：19 个历史收盘 + 今日实时价
        hist = [[r[0][5:].replace("-", ""), round(r[1], 2)] for r in rows[-19:]]
        px = q.get("price")
        if px:
            hist.append(["TODAY", round(px, 2)])

        prev = None
        if pct is not None and code in pct.columns:
            col = pct[code].dropna()
            if len(col):
                prev = round(float(col.iloc[-1]), 2)

        out[code] = {
            "name": name_map.get(code) or q.get("name", code),
            "hist20": hist[-20:],
            "intraday": minute_series(sym(code)) if px else [],
            "prev_pct": prev,
            "prev_close": q.get("prev_close"),
        }
    return out


def prev_day_stats(date_str):
    """上一交易日的大盘指标（严格早于当日）"""
    if not os.path.exists(HIST_CSV):
        return None
    try:
        df = pd.read_csv(HIST_CSV, encoding="utf-8-sig")
        prev = df[df["date"].astype(str) < str(date_str)].tail(1)
        if prev.empty:
            return None
        r = prev.iloc[0]
        return {
            "date": str(r["date"]),
            "up": int(r["up"]), "down": int(r["down"]),
            "limit_up": int(r["limit_up"]), "limit_down": int(r["limit_down"]),
            "median_pct": float(r["median_pct"]),
            "amount_yi": float(r["amount_yi"]),
            "idx_pct": float(r["idx_pct"]),
            "temp": float(r["temp"]),
            "up_ratio": float(r["up_ratio"]),
        }
    except Exception:
        return None


def build_delta(ctx):
    """当日 vs 上一交易日"""
    prev = prev_day_stats(ctx["date"])
    if not prev:
        return None
    b, t = ctx["breadth"], ctx["temperature"]
    idx = ctx["indices"][0][1] if ctx["indices"] else {}
    return {
        "date": prev["date"],
        "temp": round(t["total"] - prev["temp"], 1),
        "temp_prev": prev["temp"],
        "amount_yi": round(b["amount_yi"] - prev["amount_yi"], 0),
        "amount_pct": round((b["amount_yi"] / prev["amount_yi"] - 1) * 100, 1) if prev["amount_yi"] else None,
        "amount_prev": prev["amount_yi"],
        "up": b["up"] - prev["up"],
        "down": b["down"] - prev["down"],
        "limit_up": b["limit_up"] - prev["limit_up"],
        "limit_up_prev": prev["limit_up"],
        "median_pct": round(b["median_pct"] - prev["median_pct"], 2),
        "median_prev": prev["median_pct"],
        "idx_pct_prev": prev["idx_pct"],
        "idx_pct": round(idx.get("pct", 0), 2),
    }
