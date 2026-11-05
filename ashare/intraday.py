# -*- coding: utf-8 -*-
"""成交时点合理性：只看成交那一刻之前的盘面，判断这一手当时该不该做。

为什么需要
----------
原来的逐笔复盘只有日线级别的判断（当日涨跌幅、20 日分位、量比），
能回答「这只票当时在什么位置」，回答不了「你为什么在 10:35 卖」。
同样一只票，早盘冲高卖和尾盘跳水卖，是两件完全不同的事。

数据
----
东方财富分时（trends2），一次取 5 个交易日，1 分钟一条。缓存到
data/intraday/<date>_<code>.json，重渲染不再请求网络。

口径（这一条最重要）
--------------------
所有特征只取成交时点 t 及之前的分时，**绝不使用 t 之后的价格**。
事后涨跌只在「卖出后表现」里出现，且与这里的评分分开算。
"""

import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "intraday")


def _secid(code):
    return ("1." if code[:1] in "69" else "0.") + code


def fetch_day(code, date, retry=1):
    """取某只票某日的 1 分钟分时。返回 [(HH:MM, 价格, 成交量手), ...]。

    东财 trends2 的 ndays=5 覆盖最近 5 个交易日；更早的日期取不到，
    这时返回 None，调用方退回日线判断，不会让整张表缺行。
    """
    fp = os.path.join(CACHE, f"{date}_{code}.json")
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = ("https://push2his.eastmoney.com/api/qt/stock/trends2/get"
           f"?secid={_secid(code)}&fields1=f1,f2,f3"
           "&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=5&iscr=0")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    for i in range(retry + 1):
        try:
            raw = urllib.request.urlopen(req, timeout=12).read()
            data = json.loads(raw.decode("utf-8"))
            trends = (data.get("data") or {}).get("trends") or []
            rows = []
            for line in trends:
                p = line.split(",")
                if len(p) < 6 or not p[0].startswith(date):
                    continue
                try:
                    rows.append([p[0][11:], float(p[2]), float(p[5] or 0)])
                except ValueError:
                    continue
            if rows:
                os.makedirs(CACHE, exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(rows, f, ensure_ascii=False)
                return rows
        except Exception:
            if i < retry:
                time.sleep(0.8)
    return None


def _to_min(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _from_min(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _at(rows, t):
    """t 时点或之前最后一分钟的价格与成交量。"""
    m = _to_min(t)
    got = None
    for x in rows:
        if _to_min(x[0]) <= m:
            got = x
        else:
            break
    return got


def features(rows, prev_close, t, price):
    """成交时点 t 的盘面特征。只用 t 之前的数据。

    price 用真实成交价，而不是分时收盘价 —— 成交可能落在两分钟之间。
    """
    if not rows or not prev_close:
        return None
    cur = _at(rows, t)
    if not cur:
        return None
    m = _to_min(t)
    upto = [x for x in rows if _to_min(x[0]) <= m]
    if len(upto) < 5:
        return None

    px = price or cur[1]
    pct_now = (px / prev_close - 1) * 100

    # 前 30 分钟动量：t-30 之前最后一分钟 → 现在
    back = None
    for x in upto:
        if _to_min(x[0]) <= m - 30:
            back = x
    pct_30 = (px / back[1] - 1) * 100 if back else 0.0

    hi = max(x[1] for x in upto)
    lo = min(x[1] for x in upto)
    hi, lo = max(hi, px), min(lo, px)
    pos_day = (px - lo) / (hi - lo) if hi > lo else 0.5
    dd_high = (px / hi - 1) * 100 if hi else 0.0

    # 日内均价：用成交量加权（分时接口的成交额/成交量更准，这里用价格近似）
    vsum = sum(x[2] for x in upto)
    vwap = (sum(x[1] * x[2] for x in upto) / vsum) if vsum else px
    vwap_gap = (px / vwap - 1) * 100 if vwap else 0.0

    # 最近 30 分钟量能 / 开盘以来每分钟均量
    recent = [x for x in upto if _to_min(x[0]) > m - 30]
    vol30 = sum(x[2] for x in recent) / max(len(recent), 1)
    vol_avg = vsum / max(len(upto), 1)
    vol_ratio = (vol30 / vol_avg) if vol_avg else 1.0

    return {
        "time": t, "px": px, "pct_now": pct_now, "pct_30": pct_30,
        "pos_day": pos_day, "dd_high": dd_high, "vwap_gap": vwap_gap,
        "vol_ratio": vol_ratio, "mins_open": m - 570,
    }


def _clamp(x, lo=5, hi=95):
    return max(lo, min(hi, x))


def judge(feat, side):
    """时点评分。返回 (0-100, 标签, 依据[])。

    side: 'sell' / 'buy'。
    分数不是「赚没赚」，而是「以成交前的盘面看，这个点位做这个动作合不合理」。
    """
    if not feat:
        return None
    s = 50.0
    why = []
    pos, mom = feat["pos_day"], feat["pct_30"]
    dd, gap, vr = feat["dd_high"], feat["vwap_gap"], feat["vol_ratio"]

    if side == "sell":
        if pos >= 0.8:
            s += 12
            why.append(f"卖在当日 {pos:.0%} 分位的高位")
        elif pos <= 0.2:
            s -= 14
            why.append(f"卖在当日 {pos:.0%} 分位的低位")
        else:
            s += 2
            why.append(f"卖在当日 {pos:.0%} 分位")

        if dd >= -0.5:
            s += 6
            why.append("距日内高点不到 0.5%，兑现位置不差")
        elif dd <= -3:
            s -= 10
            why.append(f"已从日内高点回落 {abs(dd):.1f}%，属于跌下来才卖")

        if mom >= 1.5:
            s -= 10
            why.append(f"成交前 30 分钟仍在涨 {mom:+.1f}%，卖在拉升途中")
        elif mom <= -1.5:
            s += 8
            why.append(f"成交前 30 分钟跌 {abs(mom):.1f}%，属于跟跌减仓")

        if gap >= 0.3:
            s += 3
            why.append("成交价在日内均价上方，兑现的是浮盈")
        elif gap <= -0.3:
            s -= 4
            why.append("成交价跌到日内均价下方，弱势里卖出")

        if vr >= 1.8 and mom > 0:
            s -= 5
            why.append(f"最近 30 分钟量能是均量 {vr:.1f} 倍，放量拉升中卖出容易卖早")

        if feat["mins_open"] <= 15:
            s -= 3
            why.append("开盘 15 分钟内成交，盘口噪声大")

        s = _clamp(s)
        if s >= 75:
            label = "卖在高位"
        elif s >= 60:
            label = "时点尚可"
        elif s >= 45:
            label = "时点中性"
        elif mom > 0 or pos >= 0.6:
            label = "卖得偏早"
        else:
            label = "卖得偏晚"
        return round(s), label, why

    # 买入
    if pos <= 0.2:
        s += 8
        why.append(f"买在当日 {pos:.0%} 分位的低位")
    elif pos >= 0.85:
        s -= 12
        why.append(f"买在当日 {pos:.0%} 分位的高位")
    else:
        why.append(f"买在当日 {pos:.0%} 分位")

    if mom >= 2:
        s -= 8
        why.append(f"成交前 30 分钟已涨 {mom:+.1f}%，属于追涨")
    elif mom <= -1.5:
        s += 4
        why.append(f"成交前 30 分钟跌 {abs(mom):.1f}%，是回调里接")

    if gap <= -0.3:
        s += 4
        why.append("成交价低于日内均价，成本不差")
    elif gap >= 0.5:
        s -= 4
        why.append("成交价高于日内均价，买在强势末端")

    if vr >= 1.5 and mom > 0 and pos < 0.85:
        s += 8
        why.append(f"最近 30 分钟量能 {vr:.1f} 倍，放量向上时跟进")

    if feat["mins_open"] <= 15:
        s -= 3
        why.append("开盘 15 分钟内成交，盘口噪声大")

    s = _clamp(s)
    if s >= 75:
        label = "买点较好"
    elif s >= 60:
        label = "时点尚可"
    elif s >= 45:
        label = "时点中性"
    elif pos >= 0.8 and mom > 0:
        label = "追高买入"
    else:
        label = "买点偏差"
    return round(s), label, why


def match_time(rows, price, prefer=None):
    """按成交价在分时里反推成交时间（用于没有时间列的历史交割单）。

    只接受偏差 0.3% 以内的分钟；同价位有多个时点时，按 prefer 给的
    时段偏好挑一个，避免所有成交都挤在收盘前。
    """
    if not rows or not price:
        return None
    cand = [(x[0], abs(x[1] / price - 1) * 100) for x in rows]
    cand = [c for c in cand if c[1] <= 0.3]
    if not cand:
        return None
    bias = prefer or {"09:30-11:30": 0.05, "13:00-15:00": 0.0}
    def score(c):
        t, d = c
        pen = 0.0
        for span, p in bias.items():
            a, b = span.split("-")
            if _to_min(a) <= _to_min(t) <= _to_min(b):
                pen = p
                break
        return d + pen
    return sorted(cand, key=score)[0][0]
