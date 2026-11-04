# -*- coding: utf-8 -*-
"""
个股诊断：对自选股逐只给出「现在什么位置、什么状态、要盯什么」。

全部基于可计算的指标，不用大模型编。口径：
- 20 日高低点用**收盘价**计算（本地日K缓存只有收盘和成交量，没有日内高低）
- 均线为收盘价均线
- 波动率来自 forecast 模块的 HAR-RV 预测

输出给看板和报告渲染，不做买卖建议，只描述状态和需要验证的条件。
"""
import math

from .detail import _load_cache


def _ma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def _pct(a, b):
    return (a / b - 1) * 100 if b else None


def _fmt(x, nd=2, suffix=""):
    return f"{x:+.{nd}f}{suffix}" if x is not None else "—"


def build_one(code, q, klines, attr=None, fc=None, pos=None):
    """klines: [(date, close, volume), ...] 由旧到新"""
    if not q or not q.get("price"):
        return None
    px = q["price"]
    closes = [r[1] for r in klines]
    vols = [r[2] for r in klines]
    if len(closes) < 21:
        return None

    p5 = _pct(px, closes[-6]) if len(closes) >= 6 else None
    p20 = _pct(px, closes[-21])
    hi20, lo20 = max(closes[-20:]), min(closes[-20:])
    pos20 = (px - lo20) / (hi20 - lo20) if hi20 > lo20 else 0.5
    ma5, ma10, ma20, ma60 = (_ma(closes, n) for n in (5, 10, 20, 60))
    vol5 = sum(vols[-5:]) / 5 if len(vols) >= 5 else None
    vol20 = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
    vol_trend = vol5 / vol20 if vol5 and vol20 else None

    # ---- 状态判定（每条都有明确阈值，可被复核）----
    state, notes = [], []

    if ma5 and ma20:
        if px > ma5 > ma20:
            state.append("多头排列")
        elif px < ma5 < ma20:
            state.append("空头排列")
        elif px > ma20:
            state.append("站上20日线")
        else:
            state.append("跌破20日线")

    if pos20 >= 0.98:
        notes.append(f"创 20 日收盘新高（区间 100% 分位），新高之上没有套牢盘但也没有支撑，"
                     f"回踩 {ma5:,.2f}（5 日线）是第一道观察位" if ma5 else
                     "创 20 日收盘新高，留意回落时的承接")
    elif pos20 >= 0.85:
        notes.append(f"接近 20 日高点 {hi20:,.2f}（{pos20:.0%} 分位），突破需放量，否则易冲高回落")
    elif pos20 <= 0.02:
        notes.append(f"创 20 日收盘新低（区间 0% 分位），下跌趋势中，先看能否站回 {ma5:,.2f}"
                     if ma5 else "创 20 日收盘新低，等止跌信号")
    elif pos20 <= 0.15:
        notes.append(f"处于 20 日区间底部（{pos20:.0%} 分位），下方参考 {lo20:,.2f}")
    else:
        notes.append(f"处于 20 日区间 {pos20:.0%} 分位，上有 {hi20:,.2f} 下有 {lo20:,.2f}，方向未明")

    if ma20 and px < ma20:
        notes.append(f"现价低于 20 日线 {ma20:,.2f}（差 {_fmt((px / ma20 - 1) * 100, 1, '%')}），"
                     f"反弹先看能否收复")
    elif ma20 and ma5 and ma5 > ma20:
        notes.append(f"5 日线 {ma5:,.2f} 在 20 日线 {ma20:,.2f} 上方，短期结构偏多，"
                     f"回踩 20 日线不破可继续持有")
    elif ma60 and px > ma60:
        notes.append(f"在 60 日线 {ma60:,.2f} 上方，中期趋势未破")

    vr = q.get("vol_ratio")
    if vr and vr >= 2:
        notes.append(f"量比 {vr:.1f}，明显放量，注意是否有事件驱动")
    elif vr and vr <= 0.7:
        notes.append(f"量比 {vr:.1f}，缩量，方向性不足")

    if vol_trend:
        if vol_trend >= 1.3:
            notes.append(f"5 日均量为 20 日均量的 {vol_trend:.0%}，资金在持续进场")
        elif vol_trend <= 0.7:
            notes.append(f"5 日均量降到 20 日均量的 {vol_trend:.0%}，热度在退")

    # 行业对比
    if attr:
        if attr["verdict"] in ("强于板块", "弱于板块"):
            notes.append(f"今日 {attr['gap']:+.2f}pp 于「{attr['industry']}」行业中位数，"
                         f"属个股独立因素，需要看公告或资金面")
        else:
            notes.append(f"与「{attr['industry']}」板块同步（偏离 {attr['gap']:+.2f}pp），明日跟板块走")

    # 波动率
    if fc:
        notes.append(f"未来 5 日预计波动 ±{fc['sigma_5d'] * math.sqrt(5) * 100:.1f}%，"
                     f"80% 区间 {fc['lo']:,.2f} ~ {fc['hi']:,.2f}")

    # 持仓视角
    if pos:
        if pos.get("weight") and pos["weight"] >= 30:
            notes.append(f"单一持仓占比 {pos['weight']:.0f}%，集中度偏高，注意单一标的风险")
        if pos.get("pnl_pct") is not None and pos["pnl_pct"] <= -10:
            notes.append(f"当前浮亏 {pos['pnl_pct']:.1f}%，对照自己的止损线，别让亏损扩大")
        elif pos.get("pnl_pct") is not None and pos["pnl_pct"] >= 20:
            notes.append(f"浮盈 {pos['pnl_pct']:.1f}%，可考虑分批兑现而非一次性卖出")

    # 一句话总结：只陈述可核对的事实，不贴「走强/走弱」这类容易误导的标签
    # （例：今天 +5.19% 但 5 日累计 -0.5%，说「走弱」是错的）
    today_word = ""
    if q.get("pct") is not None:
        today_word = f"今日 {q['pct']:+.2f}%，"
    summary = (f"{today_word}近 5 日 {_fmt(p5, 1, '%')}、近 20 日 {_fmt(p20, 1, '%')}；"
               f"当前处于 20 日收盘区间 {pos20:.0%} 分位，{'、'.join(state) or '方向不明'}。")

    return {
        "code": code, "name": q.get("name", code), "price": px, "pct": q.get("pct"),
        "summary": summary,
        "metrics": [
            ("近 5 日", _fmt(p5, 1, "%")),
            ("近 20 日", _fmt(p20, 1, "%")),
            ("20日收盘分位", f"{pos20:.0%}"),
            ("20日收盘高/低", f"{hi20:,.2f} / {lo20:,.2f}"),
            ("MA5 / MA20", f"{ma5:,.2f} / {ma20:,.2f}" if ma5 and ma20 else "—"),
            ("量比", f"{vr:.1f}" if vr else "—"),
            ("5日/20日均量", f"{vol_trend:.0%}" if vol_trend else "—"),
        ],
        "state": state,
        "watch": notes[:5],
    }


def build_all(watch, quotes, attrs=None, forecasts=None, portfolio=None):
    """批量诊断。attrs 为 {code: attr}，forecasts 为 {code: 预测dict}，portfolio 为持仓汇总。"""
    data, _ = _load_cache()
    attrs = attrs or {}
    forecasts = forecasts or {}
    pos_map = {}
    if portfolio:
        for r in portfolio.get("rows", []):
            pos_map[r["code"]] = r

    out = {}
    for code, name in watch.items():
        q = quotes.get(code)
        if not q:
            continue
        rows = data.get(code) or []
        if len(rows) < 25:
            continue
        card = build_one(code, {**q, "name": q.get("name") or name}, rows,
                         attr=attrs.get(code), fc=forecasts.get(code),
                         pos=pos_map.get(code))
        if card:
            out[code] = card
    return out


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ashare import data, watchlist as wl

    watch, positions, _ = wl.load()
    q = data.fetch_quotes(list(watch.keys()))
    w = wl.fill_names(watch, q)
    cards = build_all(w, q)
    for code, c in cards.items():
        print(f"\n【{c['name']} {code}】{c['price']:,.2f}  {c['pct']:+.2f}%")
        print("  " + c["summary"])
        for k, v in c["metrics"]:
            print(f"    {k:<12} {v}")
        for n in c["watch"]:
            print("  · " + n)
