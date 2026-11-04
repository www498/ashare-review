# -*- coding: utf-8 -*-
"""多日涨跌归因：把一只股票过去 N 个交易日的涨跌拆成「大盘 / 行业 / 个股自身」。

为什么需要
----------
用户真正想知道的是「我的票为什么涨、为什么跌」，而单日涨跌幅回答不了。
按恒等式把日收益拆开：

    r_i = m  +  (s_j - m)  +  (r_i - s_j)
          ↑        ↑              ↑
        大盘     行业超额       个股超额

逐日累加后就能说清楚：「这 5 天跌了 8.2%，大盘贡献 -1.1pp、板块 -2.3pp、
个股自己 -4.8pp —— 板块在退潮，而它比板块还多跌了 4.8 个点」。

基准口径
--------
- 大盘 m：全市场个股日收益的**中位数**（等权，不被权重股绑架）
- 行业 s：该行业个股日收益的中位数
两者都从本地日K缓存离线算出，不额外请求任何接口。

关于「简单加总」
----------------
贡献值按日算术相加，累计涨跌也用算术和，保证三项之和严格等于累计值。
5~20 日区间内与复利结果的差异通常在 0.1 个百分点以内，换来的是每一项都能对上。
"""
import os
import pickle

from .data import ROOT

CACHE = os.path.join(ROOT, "data", "klines_cache.pkl")

# 判定"放量"的阈值：当日成交量 / 前 20 日均量
HEAVY_VOL = 1.8
THIN_VOL = 0.6


def _load(klines=None):
    if klines is not None:
        return klines
    if not os.path.exists(CACHE):
        return {}
    with open(CACHE, "rb") as f:
        obj = pickle.load(f)
    return obj.get("data") or {}


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    n = len(vals)
    if not n:
        return None
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2


def build(klines=None, mapping=None, min_days=25):
    """算出每天的「大盘中位数收益」与「各行业中位数收益」。

    返回 dict：
        dates        交易日列表（升序）
        market       {date: 全市场中位数涨跌幅 %}
        industry     {行业: {date: 中位数涨跌幅}}
        closes       {code: {date: close}}
        vols         {code: {date: volume}}
        latest       缓存里最新交易日
        n_stocks     参与计算的有效个股数
    """
    data = _load(klines)
    mapping = mapping or {}

    closes, vols = {}, {}
    for code, rows in data.items():
        if not rows or len(rows) < min_days:
            continue
        closes[code] = {d: px for d, px, _ in rows if px}
        vols[code] = {d: v for d, _, v in rows}

    if not closes:
        return None

    # 交易日历取所有个股日期的并集，升序
    dates = sorted({d for m in closes.values() for d in m})
    if len(dates) < 3:
        return None

    # 逐日横截面收益：{date: [pct, ...]}
    prev = {}
    daily = {d: [] for d in dates[1:]}
    for code, m in closes.items():
        ds = sorted(m)
        for i in range(1, len(ds)):
            d0, d1 = ds[i - 1], ds[i]
            p0 = m[d0]
            if p0:
                daily.setdefault(d1, []).append((m[d1] / p0 - 1) * 100)

    market = {}
    ind_raw = {}
    for d, arr in daily.items():
        if not arr:
            continue
        med = _median(arr)
        if med is not None:
            market[d] = med

    # 行业基准：按行业分组，逐日取中位数
    by_ind = {}
    for code in closes:
        ind = mapping.get(code)
        if ind:
            by_ind.setdefault(ind, []).append(code)

    for ind, codes in by_ind.items():
        if len(codes) < 3:
            continue
        series = {}
        for i in range(1, len(dates)):
            d0, d1 = dates[i - 1], dates[i]
            arr = []
            for c in codes:
                p0 = closes[c].get(d0)
                p1 = closes[c].get(d1)
                if p0 and p1:
                    arr.append((p1 / p0 - 1) * 100)
            if len(arr) >= 3:
                series[d1] = _median(arr)
        if series:
            ind_raw[ind] = series

    return {
        "dates": dates,
        "market": market,
        "industry": ind_raw,
        "closes": closes,
        "vols": vols,
        "latest": dates[-1],
        "n_stocks": len(closes),
    }


def _vol_ratio(vols, code, date, dates, back=20):
    """当日量 / 此前 20 日均量。用前 20 日做基准，不含当日，避免自己抬高阈值。"""
    v = vols.get(code) or {}
    cur = v.get(date)
    if not cur:
        return None
    try:
        i = dates.index(date)
    except ValueError:
        return None
    hist = [v.get(dates[j]) for j in range(max(0, i - back), i)]
    hist = [x for x in hist if x]
    if len(hist) < 5:
        return None
    base = sum(hist) / len(hist)
    return (cur / base) if base else None


def decompose(code, fac, name="", n=5, mapping=None):
    """把某只个股最近 n 个交易日的涨跌拆成大盘 / 行业 / 个股三部分。

    返回 None 表示数据不足（新股、长期停牌、无行业归属等）。
    """
    if not fac or not code:
        return None
    from .data import limit_pct

    closes = fac["closes"].get(code)
    if not closes or len(closes) < n + 2:
        return None

    dates = fac["dates"]
    # 该股自己的交易日（可能停牌缺日），只保留最近 n+1 个，用于算 n 天收益
    own = sorted(closes)
    if len(own) < n + 1:
        return None
    tail = own[-(n + 1):]

    ind = (mapping or {}).get(code)
    ind_series = (fac["industry"].get(ind) or {}) if ind else {}

    days = []
    for i in range(1, len(tail)):
        d0, d1 = tail[i - 1], tail[i]
        p0, p1 = closes.get(d0), closes.get(d1)
        if not p0 or not p1:
            continue
        r = (p1 / p0 - 1) * 100
        m = fac["market"].get(d1)
        s = ind_series.get(d1)

        # 缺基准时该日不硬凑：把缺口记为 None，用 0 会让人误以为「大盘没动」
        if m is None:
            mkt_part = None
            ind_part = None
            firm_part = None
        elif s is None:
            mkt_part = m
            ind_part = None
            firm_part = r - m
        else:
            mkt_part = m
            ind_part = s - m
            firm_part = r - s

        vr = _vol_ratio(fac["vols"], code, d1, dates)
        lim = limit_pct(code) if limit_pct else 10.0
        tag = ""
        if r >= lim - 0.3:
            tag = "涨停"
        elif r <= -(lim - 0.3):
            tag = "跌停"
        elif vr and vr >= HEAVY_VOL:
            tag = "放量上涨" if r > 0 else "放量下跌"
        elif vr and vr <= THIN_VOL:
            tag = "缩量"

        days.append({
            "date": d1, "pct": r,
            "market": mkt_part, "industry": ind_part, "firm": firm_part,
            "vol_ratio": vr, "tag": tag,
            "is_last": d1 == tail[-1],
        })

    if not days:
        return None

    # 累计涨跌必须是复利真实涨幅（首尾收盘价），不能用日收益算术和：
    # 这几天里有 +10% 与 -5.8% 交替时，算术和 -2.76% 而真实是 -3.55%，差 0.8pp，
    # 用户拿股价一对就发现对不上。
    p_first = closes.get(tail[0])
    p_last = closes.get(tail[-1])
    if not p_first or not p_last:
        return None
    total = (p_last / p_first - 1) * 100

    arith = sum(d["pct"] for d in days)
    mkt_sum = sum(d["market"] for d in days if d["market"] is not None)
    ind_sum = sum(d["industry"] for d in days if d["industry"] is not None)
    firm_sum = sum(d["firm"] for d in days if d["firm"] is not None)

    # 三项贡献按比例缩放到真实累计，保证「大盘 + 板块 + 个股 = 总涨跌」严格成立。
    # 缩放系数偏离 1 太远（剧烈震荡导致算术和趋近 0）时不缩放，宁可诚实标注。
    scaled = False
    if abs(arith) > 0.3:
        k = total / arith
        if 0.55 <= k <= 1.8:
            mkt_sum, ind_sum, firm_sum = mkt_sum * k, ind_sum * k, firm_sum * k
            scaled = True

    # 驱动归因：按三者绝对值占比判断谁说了算
    parts = {"大盘": abs(mkt_sum), "板块": abs(ind_sum), "个股": abs(firm_sum)}
    denom = sum(parts.values())
    driver, share = ("波动太小", 0.0)
    if denom > 0.3:                      # 涨跌幅太小就不硬下结论
        key = max(parts, key=parts.get)
        share = parts[key] / denom
        if share >= 0.45:
            driver = f"{key}主导"
        elif share >= 0.33:
            driver = f"{key}因素相对突出"
        else:
            driver = "三方面影响接近"

    # 最关键的交易日：对累计涨跌贡献最大的那天
    key_day = max(days, key=lambda d: abs(d["pct"]))

    # 连续同向：最近 3 天是否同涨同跌
    tail3 = [d["pct"] for d in days[-3:]]
    streak = ""
    if len(tail3) == 3:
        if all(x > 0 for x in tail3):
            streak = "连续 3 日上涨"
        elif all(x < 0 for x in tail3):
            streak = "连续 3 日下跌"

    return {
        "code": code, "name": name, "industry": ind or "未分类",
        "n": len(days), "asof": days[-1]["date"],
        "start": days[0]["date"], "end": days[-1]["date"],
        "total": total,
        "market": mkt_sum, "industry_part": ind_sum, "firm": firm_sum,
        "driver": driver, "driver_share": share, "scaled": scaled,
        "key_day": key_day, "streak": streak,
        "days": days,
        "text": _narrate(name or code, ind or "未分类", days, total,
                         mkt_sum, ind_sum, firm_sum, driver, key_day, streak),
    }


def _narrate(name, ind, days, total, mkt, ins, firm, driver, key_day, streak):
    """规则版叙述。有 LLM 时会被更自然的版本替换，无 key 也必须有话说。"""
    n = len(days)
    word = "上涨" if total > 0 else ("下跌" if total < 0 else "持平")
    out = [f"近 {n} 个交易日{word} {abs(total):.2f}%。"]

    if abs(total) >= 0.3:
        bits = []
        if abs(mkt) >= 0.2:
            bits.append(f"大盘 {mkt:+.1f}pp")
        if abs(ins) >= 0.2:
            bits.append(f"板块超额 {ins:+.1f}pp（相对大盘）")
        if abs(firm) >= 0.2:
            bits.append(f"个股超额 {firm:+.1f}pp（相对板块）")
        if bits:
            out.append("拆开看：" + "、".join(bits) + f"，{driver}。")

        # 个股与板块的相对位置 —— 用户最关心「到底是不是它自己的问题」
        if abs(firm) >= 1.0:
            if total > 0 and firm < 0:
                out.append(f"板块整体在涨，它反而落后 {abs(firm):.1f}pp，属于个股层面的独立走弱。")
            elif ins < 0 < firm:
                out.append(f"板块同期在跌（{ins:+.1f}pp），它逆势强于板块 {firm:.1f}pp，"
                           f"跌幅明显小于同行。")
            elif firm > 0:
                out.append(f"它比所属板块多涨了 {firm:.1f}pp，是板块里的强势个体。")
            else:
                out.append(f"它比所属板块多跌了 {abs(firm):.1f}pp，板块之外还有个股自身的原因。")

    kd = key_day
    seg = f"波动最大的是 {kd['date']}，单日 {kd['pct']:+.1f}%"
    if kd.get("vol_ratio"):
        seg += f"，量能是前 20 日均量的 {kd['vol_ratio']:.1f} 倍"
    if kd.get("tag"):
        seg += f"（{kd['tag']}）"
    seg += "。"
    if abs(total) > 0.5 and abs(kd["pct"]) > 0:
        ratio = abs(kd["pct"]) / abs(total)
        if ratio >= 1.0:
            seg += "单这一天的幅度就超过了整段累计，其余交易日有反向回补。"
        elif ratio >= 0.5:
            seg += f"这一天的贡献占了整段波动的 {ratio:.0%}，是主要来源。"
    out.append(seg)

    if streak:
        out.append(f"{streak}，短期方向已经比较一致。")
    return "".join(out)


def build_many(codes, klines=None, mapping=None, n=5, names=None):
    """批量归因，共享同一份基准，避免每只股票重复算全市场中位数。"""
    fac = build(klines=klines, mapping=mapping)
    if not fac:
        return {}, None
    names = names or {}
    out = {}
    for code in codes:
        r = decompose(code, fac, name=names.get(code, ""), n=n, mapping=mapping)
        if r:
            out[code] = r
    return out, fac
