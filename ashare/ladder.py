# -*- coding: utf-8 -*-
"""
连板梯队与晋级率。

全部从本地日K缓存（data/klines_cache.pkl）离线计算，零网络请求。
连板口径：主板 / 科创板按各自涨停阈值识别，ST 股 5% 的涨停会被漏计（见口径说明）。

核心指标：
- 最高板高度、各板位家数（梯队结构）
- 晋级率：昨日 N 板 → 今日 N+1 板的比例，衡量接力意愿
- 昨日涨停股今日表现：平均涨幅、红盘率，衡量打板赚钱效应
"""
import os
import pickle

import numpy as np
import pandas as pd

from .data import ROOT

CACHE = os.path.join(ROOT, "data", "klines_cache.pkl")
LIMIT_MAIN = 9.85
LIMIT_STAR = 19.85
ABNORMAL_PCT = 21.5


def _busdays_between(a, b):
    """a 到 b 之间的交易日数，带交易日历。日历不可用时退回自然日。"""
    try:
        from .tcal import trading_days_between
        return trading_days_between(a, b)
    except Exception:
        return (b - a).days


def load_matrix():
    """返回 (pct矩阵, 涨停标记矩阵, 日期索引)"""
    if not os.path.exists(CACHE):
        return None
    with open(CACHE, "rb") as f:
        c = pickle.load(f)
    data = c["data"]
    close = {code: {d: px for d, px, _ in rows} for code, rows in data.items()}
    cdf = pd.DataFrame(close).sort_index()
    pct = cdf.pct_change() * 100
    from .data import limit_pct
    # 除权阈值按各板块自己的涨跌停幅度定：主板 12%、创业板/科创 22%、北交所 32%
    cap = pd.Series({c_: limit_pct(c_) + 2.0 for c_ in pct.columns})
    pct = pct.mask(pct.abs().gt(cap, axis=1))

    # 涨停用价格口径（与实时、history 一致）：涨停价 = round(前收 × (1+幅度), 2)。
    # 阈值口径会漏掉低价股的一字板，连板数会因此断档。
    prev_close = cdf.shift(1)
    lim_rate = pd.Series({c_: limit_pct(c_) for c_ in cdf.columns})
    lu_price = prev_close.mul(1 + lim_rate / 100).round(2)
    limit = (cdf.ge(lu_price - 1e-9) & prev_close.notna() & pct.notna()).fillna(False)
    return pct, limit, cdf


def streak_matrix(limit):
    """每格 = 截至该日连续涨停天数"""
    out = pd.DataFrame(0, index=limit.index, columns=limit.columns, dtype=int)
    for col in limit.columns:
        s = limit[col].astype(int)
        grp = (s == 0).cumsum()
        out[col] = s.groupby(grp).cumsum()
    return out


def build(quotes, names=None):
    """quotes: {code: dict} 实时行情；返回梯队结果 dict"""
    m = load_matrix()
    if m is None:
        return None
    pct, limit, cdf = m
    st = streak_matrix(limit)
    last_date = st.index[-1]

    # 缓存可能已经包含今天（收盘后回补），此时 st 的最后一行就是今日连板数，
    # 不能再“+1”，否则连板数整体虚增一级
    import datetime as _dt
    has_today = str(last_date) == _dt.date.today().isoformat()
    if has_today and len(st) >= 2:
        today_streak = st.iloc[-1]
        prev_streak = st.iloc[-2]
        y_limit_row = limit.iloc[-2]
    else:
        today_streak = st.iloc[-1] + 1
        prev_streak = st.iloc[-1]
        y_limit_row = limit.iloc[-1]

    # 今日涨停：用实时行情的涨停价判定（比阈值更准，能识别 ST 5%）
    today_lu = {}
    for code, q in quotes.items():
        if not q or q.get("price", 0) <= 0:
            continue
        lu = q.get("limit_up", 0)
        if lu and lu > 0 and abs(q["price"] - lu) < 0.011:
            today_lu[code] = q

    # 梯队：今日连板数 = 1 + 截至昨日连板数
    ladder = {}
    for code, q in today_lu.items():
        b = int(today_streak.get(code, 0))
        if b <= 0:
            b = 1     # 兜底：实时判定为涨停但缓存没算出来（如 ST 5%、复牌首日）
        ladder.setdefault(b, []).append((code, q.get("name", code), q.get("pct", 0)))

    # 晋级率：昨日 N 板 → 今日 N+1 板
    y_lu = [c for c in limit.columns if bool(y_limit_row.get(c, False))]
    promo = {}
    for code in y_lu:
        b = int(prev_streak.get(code, 0))
        if b <= 0:
            continue
        rec = promo.setdefault(b, {"total": 0, "ok": 0})
        rec["total"] += 1
        if code in today_lu:
            rec["ok"] += 1

    # 昨日涨停股今日表现（打板赚钱效应）
    perf_pct = []
    for code in y_lu:
        q = quotes.get(code)
        if q and q.get("price", 0) > 0 and not np.isnan(q.get("pct", np.nan)):
            perf_pct.append(q["pct"])
    perf = {
        "n": len(perf_pct),
        "avg": float(np.mean(perf_pct)) if perf_pct else None,
        "red": float(np.mean([1 if p > 0 else 0 for p in perf_pct])) if perf_pct else None,
    }

    ladder_sorted = sorted(ladder.items(), key=lambda kv: -kv[0])
    # 缓存必须含「今日」或「上一交易日」，否则 today_streak 会把几天前的连板数 +1 当成今天。
    # 原来按 >5 自然日判断，会让第 1~5 天静默算错而不报警。
    stale, stale_msg = False, None
    try:
        import datetime as _dt
        last = _dt.date.fromisoformat(str(last_date))
        today = _dt.date.today()
        gap = _busdays_between(last, today)
        if not has_today and gap > 1:
            stale = True
            stale_msg = (f"日K缓存最后日期为 {last}，距今已有 {gap} 个交易日，"
                         f"连板数可能失真。请运行 python -m ashare.history 刷新。")
    except Exception:
        pass
    return {
        "asof": str(last_date),
        "has_today": has_today,
        "stale": stale,
        "stale_msg": stale_msg,
        "max_board": ladder_sorted[0][0] if ladder_sorted else 0,
        "ladder": ladder_sorted,
        "promotion": sorted(promo.items()),
        "perf": perf,
        "n_today_lu": len(today_lu),
    }


def summarize(r, topn=3):
    """把梯队结果压缩成几条可读结论"""
    if not r:
        return []
    out = []
    if r["max_board"] >= 3:
        top = r["ladder"][0]
        out.append(f"最高 {top[0]} 板：{'、'.join(n for _, n, _ in top[1][:topn])}，"
                   f"是当前承接力最强的位置。")
    else:
        out.append(f"今日最高仅 {r['max_board']} 板，没有形成连板梯队，接力意愿弱。")

    promo = {b: v for b, v in r["promotion"]}
    parts = []
    for b in sorted(promo, reverse=True)[:3]:
        v = promo[b]
        if v["total"] >= 3:
            parts.append(f"{b} 板晋级 {v['ok']}/{v['total']}（{v['ok']/v['total']:.0%}）")
    if parts:
        out.append("晋级率：" + "，".join(parts) + "。")

    p = r["perf"]
    if p["n"] >= 5:
        tone = "赚钱效应尚可" if (p["avg"] or 0) > 1 else ("打板亏钱" if (p["avg"] or 0) < -1 else "分化")
        out.append(f"昨日涨停股今日平均 {p['avg']:+.2f}%、红盘率 {p['red']:.0%}（{p['n']} 只），{tone}。")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ashare import data

    uni = data.universe()
    q = data.fetch_quotes(uni)
    r = build(q)
    print(f"截至 {r['asof']}，今日涨停 {r['n_today_lu']} 只，最高 {r['max_board']} 板\n")
    for b, items in r["ladder"]:
        names = "、".join(n for _, n, _ in items[:6])
        print(f"{b:>2} 板  {len(items):>2} 家   {names}")
    print("\n晋级率：")
    for b, v in r["promotion"]:
        if v["total"] >= 2:
            print(f"  {b} 板 → {b+1} 板  {v['ok']}/{v['total']} = {v['ok']/v['total']:.0%}")
    for line in summarize(r):
        print("\n·", line)
