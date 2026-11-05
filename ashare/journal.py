# -*- coding: utf-8 -*-
"""当日交易复盘：逐笔回答「这一手该不该买 / 该不该卖，为什么」。

与画像的区别
------------
画像看的是几十笔交易的统计规律（你是怎样的交易者）；
这里看的是**今天这一手**在当时的位置上做，合不合理。

两层判断，分开给分
------------------
1. 位置层：当日涨跌幅、收盘价在 20 日区间的分位、距 20 日均线的偏离、量能。
   回答「这只票当时在什么位置」。
2. 时点层：成交时间之前 30 分钟的走势、当日分位、距日内高点、相对均价、量能。
   回答「为什么在这个时间点动手」。

时点层只取成交时点及之前的分时，**绝不使用之后的走势**。事后涨跌只在
「卖出后表现」里出现，且与这里的合理性分数分开算。

结论不是非黑即白：每笔给 0–100 的合理性分数，再落到「合理 / 偏合理 / 中性 /
偏弱 / 不合理」五档。位置层与时点层按 45% / 55% 加权——一手交易做得好不好，
「什么时候动手」比「这只票当时在什么位置」更能说明问题。
"""

from .data import limit_pct
from . import intraday

# 判定阈值。集中放在这里，方便回测调参。
CHASE_PCT = 5.0        # 当日涨幅超过这个就算「追」
CHASE_POS = 0.80       # 且收盘在 20 日区间 80% 分位以上
DIP_PCT = -3.0         # 当日跌幅超过这个算「低吸」
DIP_POS = 0.30
FAR_MA = 0.10          # 高于 20 日线 10% 视为偏离过远
HEAVY_VOL = 2.0
THIN_VOL = 0.8

# 原 score(-2..2) 折算成 0-100 的位置层基线
BASE = {-2: 25, -1: 40, 0: 55, 1: 70, 2: 85}


def _load(klines=None):
    if klines is not None:
        return klines
    from . import mover
    return mover._load()


def _ctx(rows, date):
    """某只票在指定日期的位置指标。rows 为 [(date, close, vol), ...] 升序。"""
    if not rows:
        return None
    dates = [r[0] for r in rows]
    # 取 <= 当日的最后一根；当日停牌就退到最近一个交易日
    idx = -1
    for i, d in enumerate(dates):
        if d <= date:
            idx = i
        else:
            break
    if idx < 0:
        return None
    win = rows[max(0, idx - 19): idx + 1]
    closes = [r[1] for r in win]
    if len(closes) < 6:
        return None

    px = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else px
    pct = (px / prev - 1) * 100 if prev else 0.0
    hi, lo = max(closes), min(closes)
    pos = (px - lo) / (hi - lo) if hi > lo else 0.5
    ma20 = sum(closes) / len(closes)
    ma_gap = (px / ma20 - 1) * 100 if ma20 else 0.0

    vols = [r[2] for r in rows[max(0, idx - 20): idx]]
    vr = None
    if vols:
        base = sum(vols) / len(vols)
        cur = rows[idx][2]
        vr = (cur / base) if base else None

    return {"pct": pct, "pos20": pos, "ma20": ma20, "ma_gap": ma_gap,
            "vol_ratio": vr, "close": px, "prev_close": prev,
            "date": dates[idx], "bars": len(closes)}


def _judge_buy(c, code, price):
    """买入判定。返回 (verdict, score, reasons[])。score: -2 很差 ~ +2 很好。"""
    reasons = []
    lim = limit_pct(code)
    pct, pos, vr, gap = c["pct"], c["pos20"], c["vol_ratio"], c["ma_gap"]

    # 涨停价追入：最典型的高风险动作
    if pct >= lim - 0.3:
        reasons.append(f"当日已涨停（{pct:+.1f}%），在涨停价附近成交")
        reasons.append("涨停买点的次日溢价没有稳定规律，且当日已无法止损")
        return "涨停追入", -2, reasons

    if pct >= CHASE_PCT and pos >= CHASE_POS:
        reasons.append(f"当日已涨 {pct:+.1f}%，且收盘在 20 日区间 {pos:.0%} 分位")
        reasons.append(f"距 20 日均线偏离 {gap:+.1f}%，属于短线上沿")
        return "追高买入", -2, reasons

    if pct <= DIP_PCT and pos <= DIP_POS:
        reasons.append(f"当日下跌 {pct:.1f}%，收盘在 20 日区间 {pos:.0%} 分位（下沿）")
        if vr and vr >= HEAVY_VOL:
            reasons.append(f"但量能是前 20 日均量的 {vr:.1f} 倍，属于放量下跌，接刀需谨慎")
            return "逆势接刀", -1, reasons
        reasons.append(f"量能 {vr:.1f} 倍，缩量下跌通常比放量下跌更接近尾声" if vr
                       else "缩量回落，位置偏低")
        return "低位低吸", 1, reasons

    if gap >= FAR_MA * 100:
        reasons.append(f"成交价高于 20 日均线 {gap:.1f}%，偏离较大")
        return "偏离均线", -1, reasons

    if vr and vr >= HEAVY_VOL and pct > 2 and pos < 0.75:
        reasons.append(f"放量上涨（量能 {vr:.1f} 倍），且尚未到 20 日区间上沿"
                       f"（{pos:.0%} 分位）")
        return "放量突破", 1, reasons

    if pos <= 0.35 and (vr or 1) <= THIN_VOL:
        reasons.append(f"处于 20 日区间 {pos:.0%} 分位，缩量（{vr:.1f} 倍）"
                       if vr else f"处于 20 日区间 {pos:.0%} 分位")
        reasons.append("位置不高但缺少放量确认，等一根放量阳线更稳")
        return "低位待确认", 0, reasons

    reasons.append(f"当日 {pct:+.1f}%，20 日区间 {pos:.0%} 分位，"
                   f"距均线 {gap:+.1f}%" + (f"，量能 {vr:.1f} 倍" if vr else ""))
    reasons.append("位置与量能都在中性区间，没有明显的追高或低吸特征")
    return "常规买入", 0, reasons


def _judge_sell(c, code, price, match):
    """卖出判定。match 为 FIFO 配对结果（可能为 None）。"""
    reasons = []
    pct, pos = c["pct"], c["pos20"]

    if match:
        hold = match.get("hold_days")
        ret = match.get("ret_pct")
        if hold is not None and ret is not None:
            if ret < 0 and hold <= 2:
                reasons.append(f"持有 {hold} 天、亏损 {ret:.1f}% 就离场")
                reasons.append("止损及时，没有把小亏拖成大亏")
                return "及时止损", 1, reasons
            if ret <= -5 and hold >= 15:
                reasons.append(f"持有 {hold} 天才卖，期间已亏 {ret:.1f}%")
                reasons.append("这是典型的拖延止损：亏损单拿得比盈利单久")
                return "止损过晚", -2, reasons
            if ret >= 5 and hold <= 5:
                reasons.append(f"持有 {hold} 天、赚 {ret:.1f}% 兑现")
                reasons.append("短线兑现本身没错，但要留意是否打断了正在走的趋势")
                return "短线兑现", 1, reasons
            if ret >= 3 and hold >= 10:
                reasons.append(f"持有 {hold} 天、赚 {ret:.1f}% 后离场")
                return "正常了结", 0, reasons
            reasons.append(f"持有 {hold} 天，本笔 {ret:+.1f}%")
            return "普通卖出", 0, reasons

    # 当日缩量下跌：更像洗盘而不是转弱，这时候卖出容易卖在半山腰
    vr = c.get("vol_ratio")
    if pct < 0 and vr and vr < 0.9 and pos > 0.25:
        reasons.append(f"当天跌 {pct:.1f}% 但量能只有前 20 日均量的 {vr:.1f} 倍")
        reasons.append("缩量回调通常是洗盘而不是转势，此时离场容易卖在上涨中途")
        return "卖在缩量回调", -1, reasons

    # 没有配对记录（卖出的是更早的底仓，或数据不全）
    if pos >= 0.85 and pct > 0:
        reasons.append(f"卖在 20 日区间 {pos:.0%} 分位、当日上涨 {pct:.1f}%")
        reasons.append("位置偏高的兑现，属于合理的分批减仓时点")
        return "高位减仓", 1, reasons
    if pos <= 0.2 and pct < 0:
        reasons.append(f"卖在 20 日区间 {pos:.0%} 分位、当日下跌 {pct:.1f}%")
        reasons.append("在区间下沿卖出，若没有基本面变化，容易卖在阶段低点")
        return "低位卖出", -1, reasons
    reasons.append(f"当日 {pct:+.1f}%，20 日区间 {pos:.0%} 分位")
    return "普通卖出", 0, reasons


def _outcome(rows, date, sell_px, horizons=(3, 5)):
    """卖出之后这只票怎么走了。

    刻意与合理性分数分开：分数只评价「卖出那一刻」的位置与盘面，
    这里记录「卖完之后的事实」。两者可能相反 —— 决策合理但卖飞了，
    那恰恰是最值得看的一类复盘。
    """
    dates = [r[0] for r in rows]
    if date not in dates:
        return None
    i = dates.index(date)
    out = {}
    for h in horizons:
        j = i + h
        if j < len(rows):
            out[h] = (rows[j][1] / sell_px - 1) * 100 if sell_px else None
    # 卖出后到最新一天的最大涨幅，用来判断「有没有走掉一大段」
    after = [r[1] for r in rows[i + 1:]]
    if after:
        out["max"] = (max(after) / sell_px - 1) * 100 if sell_px else None
    return out or None


def _rate_label(x):
    if x >= 70:
        return "合理"
    if x >= 55:
        return "偏合理"
    if x >= 45:
        return "中性"
    if x >= 30:
        return "偏弱"
    return "不合理"


def _sell_note(x):
    """卖出的思考总结。

    关键：不把「后来涨了」直接等同于「卖错了」。总结要指向下次能改的动作，
    所以先看当时是什么形态（缩量回调 / 放量滞涨 / 亏损割肉），再看结果。
    """
    a3, ret = x.get("after3"), x.get("ret_pct")
    pct, vr = x.get("pct"), x.get("vol_ratio")
    if a3 is None:
        return ""
    if a3 > 3:
        if ret is not None and ret <= -5:
            return "亏损单卖在低位后反弹：问题不在这一卖，而在没在 -5% 时先减一半。"
        if pct is not None and pct < 0 and vr and vr < 0.9:
            return "缩量回调里离场，多半卖在洗盘上；下次等放量跌破前低再走。"
        if pct is not None and pct > 3:
            return "当天已经大涨还卖，属于提前兑现；板块仍强时留三分之一跟趋势。"
        return "卖后继续走强，方向看早了；按板块三日强弱分批减，能少卖飞一半。"
    if a3 < -3:
        if ret is not None and ret <= 0:
            return "亏损单及时离场、躲过后续下跌，这笔执行是对的，别因为少亏而怀疑。"
        return "盈利单卖在转弱前，落袋干净。"
    if a3 < -1:
        if ret is not None and ret <= 0:
            return "卖后小幅回落，少亏了几个点；止损方向对，点位还可以等一根阴线确认。"
        return "卖后小幅回落，兑现略早于转弱，属于可接受的范围。"
    if a3 > 1:
        return "卖后小幅走强，少赚了几个点；不算卖错，但下次可以留三分之一。"
    if ret is not None and ret <= -5:
        return "卖后走平但仍亏着：这次只是止损，不是卖飞，别用反弹安慰自己。"
    if ret is not None and ret >= 5:
        return "卖后走平，利润已经落袋；这笔的关键是把浮盈变成了现金。"
    return "卖后基本走平，这笔的成败不在点位，而在于当时是否需要这笔资金。"


def build(df, col, klines=None, mapping=None, trades=None, day=None):
    """生成当日逐笔复盘。返回 None 表示当天没有成交记录。"""
    import pandas as pd

    kl = _load(klines)
    if not kl:
        return None

    date_col = col.get("date")
    if date_col and date_col in df.columns:
        ser = pd.to_datetime(df[date_col], errors="coerce")
        if day is None:
            mx = ser.max()
            if pd.isna(mx):
                return None
            day = str(mx.date())
        mask = ser.dt.strftime("%Y-%m-%d") == day
        today = df[mask]
    else:
        return None

    if today.empty:
        return None

    c_code, c_act = col.get("code"), col.get("action")
    c_qty, c_px = col.get("qty"), col.get("price")
    c_name, c_time = col.get("name"), col.get("time")
    if not all([c_code, c_act, c_qty, c_px]):
        return None

    from .statement import _classify

    # 卖出笔需要用 FIFO 配对拿到持有天数与这笔的盈亏
    sell_match = {}
    for t in (trades or []):
        if str(t.get("sell_date"))[:10] == day:
            sell_match.setdefault(t.get("code"), []).append(t)

    rows_out = []
    for _, r in today.iterrows():
        raw_act = str(r.get(c_act, "")).strip()
        act = _classify(raw_act)
        if act not in ("buy", "sell"):
            continue
        code = str(r.get(c_code, "")).strip()
        if not code:
            continue
        try:
            qty = float(r.get(c_qty) or 0)
            px = float(r.get(c_px) or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or px <= 0:
            continue

        c = _ctx(kl.get(code) or [], day)
        if not c:
            continue

        name = str(r.get(c_name, "") or code) if c_name else code
        time_str = str(r.get(c_time, "") or "").strip() if c_time else ""
        match = None
        if act == "sell":
            lst = sell_match.get(code) or []
            if lst:
                match = lst.pop(0)

        if act == "buy":
            verdict, score, reasons = _judge_buy(c, code, px)
        else:
            verdict, score, reasons = _judge_sell(c, code, px, match)

        # ---- 时点层：只取成交时点之前的分时 ----
        feat = timing = None
        if time_str:
            series = intraday.fetch_day(code, day)
            feat = intraday.features(series, c.get("prev_close"), time_str, px)
            if feat:
                timing = intraday.judge(feat, act)

        base = BASE.get(score, 55)
        if timing:
            rate = int(round(base * 0.45 + timing[0] * 0.55))
            t_score, t_label, t_why = timing
        else:
            rate = base
            t_score, t_label, t_why = None, "", []

        after = _outcome(kl.get(code) or [], day, px) if act == "sell" else None

        rows_out.append({
            "code": code, "name": name, "time": time_str,
            "action": act, "qty": qty, "price": px, "amount": qty * px,
            # 卖出笔的成本来自 FIFO 配对；买入笔的成本就是成交价
            "cost": (match or {}).get("buy_px") if act == "sell" else px,
            "pct": c["pct"], "pos20": c["pos20"], "ma_gap": c["ma_gap"],
            "vol_ratio": c["vol_ratio"],
            "hold_days": (match or {}).get("hold_days"),
            "ret_pct": (match or {}).get("ret_pct"),
            "verdict": verdict, "score": score, "reasons": reasons,
            "timing": ({"score": t_score, "label": t_label, "why": t_why,
                        "feat": feat} if timing else None),
            "rate": rate, "rate_label": _rate_label(rate),
            "after": after,
        })

    if not rows_out:
        return None

    # 按成交时间排：复盘看的是「这一天的操作顺序」，交割单原始行序没有意义。
    # 没有时间列的老数据排在最后，保持相对顺序。
    rows_out.sort(key=lambda x: (x.get("time") or "99:99"))

    buys = [x for x in rows_out if x["action"] == "buy"]
    sells = [x for x in rows_out if x["action"] == "sell"]
    weak = [x for x in rows_out if x["rate"] < 50]
    strong = [x for x in rows_out if x["rate"] >= 70]
    rates = sorted(x["rate"] for x in rows_out)
    med = rates[len(rates) // 2]
    avg_pos = sum(x["pos20"] for x in rows_out) / len(rows_out)

    if weak:
        head = (f"今天 {len(rows_out)} 手，{len(weak)} 手位置或时点偏弱"
                f"（{weak[0]['verdict']}等），合理性中位数 {med}。")
    elif strong:
        head = (f"今天 {len(rows_out)} 手，{len(strong)} 手合理，"
                f"合理性中位数 {med}。")
    else:
        head = f"今天 {len(rows_out)} 手，多数在中性区间，合理性中位数 {med}。"

    return {
        "day": day,
        "rows": rows_out,
        "summary": {
            "n": len(rows_out), "buys": len(buys), "sells": len(sells),
            "good": len(strong), "bad": len(weak),
            "avg_pos": avg_pos, "median_rate": med, "head": head,
            "amount": sum(x["amount"] for x in rows_out),
        },
    }


def review_sells(df, col, klines=None, trades=None, days=20, limit=8):
    """回看最近卖出的实际结果：卖完之后是涨了还是跌了。

    和「今日复盘」分开的理由：
    今日复盘评价「卖的那一刻合不合理」，只用当时的信息；
    这里回答「卖完之后事实如何」。两者常常相反 —— 决策合理但卖飞了，
    或者决策草率却侥幸躲过。分开摆，才不会被结果带偏判断。

    口径写清楚：本笔 = 相对成本；卖后 N 日 = 相对卖价；
    「若持有至今」= 最新收盘相对成本。三个百分比基准不同，混着看必然误读。
    """
    import pandas as pd

    kl = _load(klines)
    if not kl:
        return None

    date_col = col.get("date")
    if not date_col or date_col not in df.columns:
        return None
    ser = pd.to_datetime(df[date_col], errors="coerce")
    dates = sorted(ser.dropna().dt.strftime("%Y-%m-%d").unique())
    if len(dates) < 2:
        return None
    recent = set(dates[-days:])

    from .statement import _classify

    c_code, c_act = col.get("code"), col.get("action")
    c_qty, c_px = col.get("qty"), col.get("price")
    c_name = col.get("name")
    if not all([c_code, c_act, c_qty, c_px]):
        return None

    sell_match = {}
    for t in (trades or []):
        sell_match.setdefault(str(t.get("sell_date"))[:10], []).append(t)

    rows_out = []
    for _, r in df.iterrows():
        d = str(ser.loc[_])[:10]
        if d not in recent:
            continue
        if _classify(r.get(c_act)) != "sell":
            continue
        code = str(r.get(c_code, "")).strip()
        try:
            px = float(r.get(c_px) or 0)
            qty = float(r.get(c_qty) or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        rows_k = kl.get(code) or []
        after = _outcome(rows_k, d, px, horizons=(3, 5))
        if not after or after.get(3) is None:
            continue

        name = str(r.get(c_name) or code) if c_name else code
        match = None
        lst = sell_match.get(d) or []
        for t in lst:
            if t.get("code") == code:
                match = t
                break

        t3 = after.get(3)
        if t3 > 3:
            verdict = "卖飞"
        elif t3 > 1:
            verdict = "小幅卖飞"
        elif t3 < -3:
            verdict = "躲过"
        elif t3 < -1:
            verdict = "小幅躲过"
        else:
            verdict = "无差别"

        cost = (match or {}).get("buy_px")
        hold_now = None
        if cost and rows_k:
            hold_now = (rows_k[-1][1] / cost - 1) * 100
        c = _ctx(rows_k, d)

        row = {
            "date": d, "code": code, "name": name, "price": px, "qty": qty,
            "cost": cost,
            "ret_pct": (match or {}).get("ret_pct"),
            "hold_days": (match or {}).get("hold_days"),
            "after3": t3, "after5": after.get(5), "max_up": after.get("max"),
            "hold_now": hold_now,
            "pct": c["pct"] if c else None,
            "vol_ratio": c["vol_ratio"] if c else None,
            "pos20": c["pos20"] if c else None,
            "verdict": verdict,
        }
        row["note"] = _sell_note(row)
        rows_out.append(row)

    if not rows_out:
        return None
    rows_out.sort(key=lambda x: -(x["after3"] or 0))
    return rows_out[:limit]
