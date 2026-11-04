# -*- coding: utf-8 -*-
"""当日交易复盘：逐笔回答「这一手该不该买 / 该不该卖，为什么」。

与画像的区别
------------
画像看的是几十笔交易的统计规律（你是怎样的交易者）；
这里看的是**今天这一手**在当时的位置上做，合不合理。

判断依据全部来自当时可得的数据：
- 当日涨跌幅、收盘价在 20 日区间的分位、距 20 日均线的偏离
- 当日量能相对前 20 日均量的倍数
- 卖出笔还会用 FIFO 配对结果拿到持有天数与这笔的盈亏

不做「事后诸葛亮」式的评价：不因为次日涨了就说买对，
只判断**买入那一刻的位置与量能**是否属于常见的追高/低吸形态。
"""
import datetime as _dt

from .data import limit_pct

# 判定阈值。集中放在这里，方便回测调参。
CHASE_PCT = 5.0        # 当日涨幅超过这个就算「追」
CHASE_POS = 0.80       # 且收盘在 20 日区间 80% 分位以上
DIP_PCT = -3.0         # 当日跌幅超过这个算「低吸」
DIP_POS = 0.30
FAR_MA = 0.10          # 高于 20 日线 10% 视为偏离过远
HEAVY_VOL = 2.0
THIN_VOL = 0.8


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
            "vol_ratio": vr, "close": px, "date": dates[idx], "bars": len(closes)}


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

    刻意与 score 分开：score 只评价「卖出那一刻」的位置与量能，
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
        match = None
        if act == "sell":
            lst = sell_match.get(code) or []
            if lst:
                match = lst.pop(0)

        if act == "buy":
            verdict, score, reasons = _judge_buy(c, code, px)
        else:
            verdict, score, reasons = _judge_sell(c, code, px, match)

        after = _outcome(kl.get(code) or [], day, px) if act == "sell" else None

        rows_out.append({
            "code": code, "name": name,
            "time": str(r.get(c_time, "") or "") if c_time else "",
            "action": act, "qty": qty, "price": px, "amount": qty * px,
            "pct": c["pct"], "pos20": c["pos20"], "ma_gap": c["ma_gap"],
            "vol_ratio": c["vol_ratio"],
            "hold_days": (match or {}).get("hold_days"),
            "ret_pct": (match or {}).get("ret_pct"),
            "verdict": verdict, "score": score, "reasons": reasons,
            "after": after,
        })

    if not rows_out:
        return None

    buys = [x for x in rows_out if x["action"] == "buy"]
    sells = [x for x in rows_out if x["action"] == "sell"]
    bad = [x for x in rows_out if x["score"] <= -1]
    good = [x for x in rows_out if x["score"] >= 1]
    avg_pos = sum(x["pos20"] for x in rows_out) / len(rows_out)

    if bad:
        head = f"今天 {len(rows_out)} 手，其中 {len(bad)} 手位置不理想（{bad[0]['verdict']}等）。"
    elif good:
        head = f"今天 {len(rows_out)} 手，整体位置合理，{len(good)} 手属于低吸或突破形态。"
    else:
        head = f"今天 {len(rows_out)} 手，位置基本在中性区间，没有明显追高。"

    return {
        "day": day,
        "rows": rows_out,
        "summary": {
            "n": len(rows_out), "buys": len(buys), "sells": len(sells),
            "good": len(good), "bad": len(bad),
            "avg_pos": avg_pos, "head": head,
            "amount": sum(x["amount"] for x in rows_out),
        },
    }


def review_sells(df, col, klines=None, trades=None, days=20, limit=6):
    """回看最近卖出的实际结果：卖完之后是涨了还是跌了。

    和「今日复盘」分开的理由：
    今日复盘评价「卖的那一刻合不合理」，只用当时的信息；
    这里回答「卖完之后事实如何」。两者常常相反 —— 决策合理但卖飞了，
    或者决策草率却侥幸躲过。分开摆，才不会被结果带偏判断。

    只保留已经有 3 个交易日后续数据的记录，否则谈不上回看。
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
    c_name, c_time = col.get("name"), col.get("time")
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
        elif t3 < -3:
            verdict = "躲过"
        else:
            verdict = "无差别"

        rows_out.append({
            "date": d, "code": code, "name": name, "price": px, "qty": qty,
            "ret_pct": (match or {}).get("ret_pct"),
            "hold_days": (match or {}).get("hold_days"),
            "after3": t3, "after5": after.get(5),
            "verdict": verdict,
        })

    if not rows_out:
        return None
    rows_out.sort(key=lambda x: -(x["after3"] or 0))
    return rows_out[:limit]
