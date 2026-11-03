# -*- coding: utf-8 -*-
"""分析层：沪A 全量宽度、市场温度打分、异动检测、结论生成。纯计算，不含 LLM。"""
import math
from statistics import median
from . import config as C


def _ok(q):
    return q and q.get("price", 0) > 0 and not math.isnan(q.get("pct", float("nan")))


def _scale(x, lo, hi, maxv):
    x = max(lo, min(hi, x))
    return (x - lo) / (hi - lo) * maxv


def breadth(quotes):
    """沪A 全量宽度。quotes 为 {code: dict}"""
    qs = [q for q in quotes.values() if _ok(q)]
    if not qs:
        return {}
    up = sum(1 for q in qs if q["pct"] > 0.05)
    down = sum(1 for q in qs if q["pct"] < -0.05)
    flat = len(qs) - up - down
    lu = [q for q in qs if q["limit_up"] > 0 and abs(q["price"] - q["limit_up"]) < 0.011]
    ld = [q for q in qs if q["limit_down"] > 0 and abs(q["price"] - q["limit_down"]) < 0.011]
    # 展示用：剔除 ST（5% 涨停，混进去会误导）
    lu_show = [q for q in lu if "ST" not in q["name"]]
    pcts = sorted(q["pct"] for q in qs)
    amps = sorted(q["amp"] for q in qs if not math.isnan(q["amp"]))
    amount = sum(q["amount"] for q in qs) / 1e4  # 万元 -> 亿元
    return {
        "n": len(qs),
        "up": up, "down": down, "flat": flat,
        "up_ratio": up / len(qs),
        "limit_up": len(lu), "limit_down": len(ld),
        "limit_up_names": [q["name"] for q in sorted(lu_show, key=lambda x: -x["pct"])][:12],
        "median_pct": median(pcts),
        "p90": pcts[int(len(pcts) * 0.9)],
        "p10": pcts[int(len(pcts) * 0.1)],
        "amount_yi": amount,
        "median_amp": median(amps) if amps else float("nan"),
        "amp_over8": sum(1 for a in amps if a > 8),
    }


def elapsed_share(quote_ts):
    """按行情时点估算『当日已走完全天的比例』。
    上午整段占 53%（开盘成交密集，略高于按分钟平分的 50%），下午按分钟补齐剩余 47%。
    盘中时点必须按分钟线性折算：原来 11:30 之前直接返回 0.53，
    等于假设「上午已走完」，9:35 跑会把量能算成实际的 1/5，报告反而自信地说「缩量」。"""
    try:
        hh, mm = (int(x) for x in str(quote_ts).split(":"))
    except Exception:
        return 1.0
    cur = hh * 60 + mm
    AM_OPEN, AM_CLOSE = 9 * 60 + 30, 11 * 60 + 30
    PM_OPEN, PM_CLOSE = 13 * 60, 15 * 60
    am = C.AM_VOLUME_SHARE
    if cur <= AM_OPEN:
        return 0.0
    if cur < AM_CLOSE:        # 上午盘中：按已走分钟折算 53% 中的对应部分
        return am * (cur - AM_OPEN) / (AM_CLOSE - AM_OPEN)
    if cur <= PM_OPEN:        # 午休：上午已走完
        return am
    if cur < PM_CLOSE:        # 下午盘中
        return min(1.0, am + (cur - PM_OPEN) / (PM_CLOSE - PM_OPEN) * (1 - am))
    return 1.0


def volume_ratio(quote_ts, today_vol, prev_vol):
    """量能比 = 当日成交量 / (昨日全日成交量 × 已走完比例)。
    基准由行情时点决定，不依赖调用参数，避免传错时段导致分数虚高。
    开盘前（比例 0）返回 None，由上层显示「基准缺失」而不是算出无穷大。"""
    if not prev_vol or prev_vol <= 0:
        return None
    share = elapsed_share(quote_ts)
    if share <= 0.02:
        return None
    base = prev_vol * share
    return today_vol / base if base > 0 else None


def temperature(b, idx_pct, vratio):
    """0-100 分，五个分项各 20 分，全部可解释。"""
    sub = {}
    sub["breadth"] = _scale(b["up_ratio"], 0.15, 0.85, C.WEIGHTS["breadth"])
    # 用「每千只净涨停数」而非绝对家数：绝对家数会随市场范围变化而失真
    # （沪A 68 家涨停与沪深京 130 家涨停其实是同一强度）
    net_per_1k = (b["limit_up"] - b["limit_down"]) / max(1, b["n"]) * 1000
    sub["limit"] = _scale(net_per_1k, -8, 24, C.WEIGHTS["limit"])
    sub["index"] = _scale(idx_pct, -3.0, 3.0, C.WEIGHTS["index"])
    if vratio is None:
        sub["volume"] = C.WEIGHTS["volume"] / 2
    else:
        sub["volume"] = _scale(vratio, 0.7, 1.3, C.WEIGHTS["volume"])
    sub["median"] = _scale(b["median_pct"], -2.0, 2.0, C.WEIGHTS["median"])
    total = sum(sub.values())
    band = next(name for hi, name in C.TEMP_BANDS if total < hi)
    return {"total": round(total, 1), "sub": {k: round(v, 1) for k, v in sub.items()}, "band": band}


def anomalies(quotes, watchlist):
    """自选股异动：涨跌幅超阈值或振幅超阈值"""
    out = []
    for code, name in watchlist.items():
        q = quotes.get(code)
        if not _ok(q):
            continue
        reasons = []
        if abs(q["pct"]) >= C.ANOMALY_PCT:
            reasons.append(f"涨跌幅 {q['pct']:+.2f}%")
        if q["amp"] >= C.ANOMALY_AMP:
            reasons.append(f"振幅 {q['amp']:.2f}%")
        if q["vol_ratio"] >= 2:
            reasons.append(f"量比 {q['vol_ratio']:.1f}")
        out.append({**q, "name": name, "reasons": reasons, "hot": bool(reasons)})
    return sorted(out, key=lambda x: -abs(x["pct"]))


def sector_flow(top=5):
    """板块资金流（东财，可选）。失败返回 None，不阻塞主流程。
    东财返回的行业分类混排了申万一级/二级/三级（银行 / 银行Ⅱ / 城商行Ⅲ），
    按去掉层级后缀后的名称去重，避免同一板块重复上榜。"""
    try:
        import akshare as ak
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        col = [c for c in df.columns if "主力净流入-净额" in c][0]
        df = df.sort_values(col, ascending=False)
        seen, picked = set(), []
        for _, r in df.iterrows():
            nm = str(r["名称"]).rstrip("ⅠⅡⅢ")
            if nm in seen:
                continue
            seen.add(nm)
            picked.append([nm, float(r["今日涨跌幅"]), float(r[col])])
        return {"top": picked[:top], "bottom": picked[-top:][::-1], "col": col}
    except Exception:
        return None


def distribution(quotes):
    """涨跌幅九档分布，对标行情软件的「市场概况」柱状图。

    比单纯的涨跌家数多出结构信息：同样是 2000 家上涨，
    集中在 0~1% 和集中在 5% 以上是完全不同的market。
    档位按绝对涨跌幅切分，与涨停/跌停单列，避免把涨停混进 5% 档。
    """
    buckets = [("涨停", 0), ("涨停-5%", 0), ("5-1%", 0), ("1-0%", 0), ("平盘", 0),
               ("0--1%", 0), ("-1--5%", 0), ("-5%-跌停", 0), ("跌停", 0)]
    b = dict(buckets)
    for q in quotes.values():
        if not _ok(q):
            continue
        p = q["pct"]
        lu, ld = q.get("limit_up", 0), q.get("limit_down", 0)
        px = q["price"]
        if lu and lu > 0 and abs(px - lu) < 0.011:
            b["涨停"] += 1
        elif ld and ld > 0 and abs(px - ld) < 0.011:
            b["跌停"] += 1
        elif p >= 5:
            b["涨停-5%"] += 1
        elif p >= 1:
            b["5-1%"] += 1
        elif p > 0.05:
            b["1-0%"] += 1
        elif p >= -0.05:
            b["平盘"] += 1
        elif p > -1:
            b["0--1%"] += 1
        elif p > -5:
            b["-1--5%"] += 1
        else:
            b["-5%-跌停"] += 1
    order = [k for k, _ in buckets]
    return {"labels": order, "counts": [b[k] for k in order],
            "total": sum(b.values())}


def market_overview(b, dist, vratio, prev_amount=None, amount_ma60=None):
    """市场概况汇总：对标行情软件首页，但每项都带「这意味着什么」。"""
    up, down = b["up"], b["down"]
    rows = []
    rows.append({
        "key": "涨跌分布", "value": f"{up}:{b['flat']}:{down}",
        "tone": "up" if up > down else "down",
        "note": f"上涨家数占比 {b['up_ratio']:.1%}。"
                f"{'多数个股上涨，赚钱效应好' if up > down * 1.5 else ''}"
                f"{'普跌格局，个股操作难度大' if down > up * 1.5 else ''}"
                f"{'涨跌互现，结构性行情' if 0.67 <= up / max(down, 1) <= 1.5 else ''}",
        "impact": "涨跌家数比反映的是「随机买一只票赚钱的概率」，"
                  "比指数更贴近实际体感。指数由权重股决定，宽度由全部个股决定。",
    })
    net = b["limit_up"] - b["limit_down"]
    rows.append({
        "key": "涨停 / 跌停", "value": f"{b['limit_up']} / {b['limit_down']}",
        "tone": "up" if net > 0 else "down",
        "note": f"净涨停 {net:+d}，每千只 {net / max(1, b['n']) * 1000:+.1f} 只。",
        "impact": "涨停数代表短线资金的做多强度，跌停数代表恐慌程度。"
                  "净涨停由正转负往往领先于指数见顶。",
    })
    rows.append({
        "key": "涨幅中位数", "value": f"{b['median_pct']:+.2f}%",
        "tone": "up" if b["median_pct"] > 0 else "down",
        "note": f"90 分位 {b['p90']:+.2f}%，10 分位 {b['p10']:+.2f}%。",
        "impact": "中位数是「中间那只票」的涨跌幅，不受极端值影响。"
                  "它和指数的差值能判断是权重拉指数还是个股普涨。",
    })
    amt = b["amount_yi"]
    note = f"全市场 {amt:,.0f} 亿。"
    if prev_amount:
        dv = amt - prev_amount
        note += f"较上一交易日{'放量' if dv > 0 else '缩量'} {abs(dv):,.0f} 亿（{dv / prev_amount:+.2%}）。"
    if amount_ma60:
        note += f"近 60 日均值 {amount_ma60:,.0f} 亿（{amt / amount_ma60 - 1:+.2%}）。"
    rows.append({
        "key": "成交额", "value": f"{amt:,.0f} 亿",
        "tone": "up" if (vratio or 1) >= 1 else "down",
        "note": note,
        "impact": "成交额是行情的燃料。缩量上涨难以持续，放量下跌说明分歧在兑现；"
                  "持续低于 60 日均值意味着增量资金不足。",
    })
    rows.append({
        "key": "振幅中位数", "value": f"{b['median_amp']:.2f}%",
        "tone": "flat",
        "note": f"振幅超 8% 的有 {b['amp_over8']} 只。",
        "impact": "振幅衡量日内波动空间。振幅放大意味着分歧加剧，"
                  "做短线机会多但容错率低；振幅收敛通常是变盘前兆。",
    })
    return rows


def intraday_strength(quotes):
    """盘面强弱：现价在「当日最高—最低」区间中的位置。
    0 = 收在最低，1 = 收在最高。这个指标只有盘中/刚收盘才有意义，
    它反映的是「最后一小时的动能」，收盘后就再也拿不到了。"""
    pos = []
    near_high = near_low = 0
    for q in quotes.values():
        if not _ok(q):
            continue
        hi, lo, px = q.get("high", 0), q.get("low", 0), q["price"]
        if hi <= lo or hi <= 0:
            continue
        p = (px - lo) / (hi - lo)
        pos.append(p)
        if p > 0.8:
            near_high += 1
        elif p < 0.2:
            near_low += 1
    if not pos:
        return {}
    return {
        "median": median(pos),
        "near_high": near_high,
        "near_low": near_low,
        "n": len(pos),
        "near_high_ratio": near_high / len(pos),
        "near_low_ratio": near_low / len(pos),
    }


def broken_boards(quotes):
    """炸板统计：盘中触及涨停价但没能封住。
    炸板率高说明封板资金不坚决，是短线情绪转弱的领先信号。"""
    hit = broken = sealed = 0
    names = []
    for q in quotes.values():
        if not _ok(q):
            continue
        lu = q.get("limit_up", 0)
        if not lu or lu <= 0:
            continue
        hi = q.get("high", 0)
        px = q["price"]
        if hi >= lu - 0.011:                 # 盘中摸到过涨停
            hit += 1
            if px < lu - 0.011:              # 但现在没封住
                broken += 1
                if len(names) < 8:
                    names.append((q.get("name", ""), round(q.get("pct", 0), 2)))
            else:
                sealed += 1
    return {
        "hit": hit, "sealed": sealed, "broken": broken,
        "rate": (broken / hit) if hit else None,
        "names": names,
    }


def am_watch(b, strength, broken, vratio, idx, temp):
    """午盘专属：下午怎么盯。只产出「可被下午验证」的判断。"""
    out = []
    if strength:
        m = strength["median"]
        if m >= 0.65:
            out.append(f"上午多数个股收在高位（收盘位置中位数 {m:.2f}，"
                       f"{strength['near_high_ratio']:.0%} 贴近当日最高），动能向上，"
                       f"下午关注能否放量突破上午高点。")
        elif m <= 0.35:
            out.append(f"上午多数个股收在低位（收盘位置中位数 {m:.2f}，"
                       f"{strength['near_low_ratio']:.0%} 贴近当日最低），"
                       f"下午先看能否收复上午低点，否则容易lower low。")
        else:
            out.append(f"上午个股收盘位置中位数 {m:.2f}，多空分歧，"
                       f"下午的方向由量能决定，先看 1:30 那半小时。")

    if broken and broken["rate"] is not None:
        if broken["rate"] >= 0.3:
            out.append(f"炸板率 {broken['rate']:.0%}（{broken['broken']}/{broken['hit']} 只摸过涨停没封住），"
                       f"封板资金不坚决，下午注意高位股能不能扛住。")
        elif broken["rate"] <= 0.15:
            out.append(f"炸板率仅 {broken['rate']:.0%}，封板质量好，"
                       f"下午若涨停家数继续增加，短线情绪会进一步升温。")
        else:
            out.append(f"炸板率 {broken['rate']:.0%}（{broken['broken']}/{broken['hit']} 只），"
                       f"封板质量一般，下午看炸板股能不能收回，收不回就是退潮前兆。")

    if vratio is not None:
        if vratio >= 1.15:
            out.append(f"半日量能已达昨日同期的 {vratio:.0%}，资金在场内，"
                       f"下午重点是「量能能否维持」而不是「有没有量」。")
        elif vratio <= 0.85:
            out.append(f"半日量能仅为昨日同期的 {vratio:.0%}，缩量明显，"
                       f"下午若量能不回来，指数多半只能横着走，普涨需要增量资金。")
        else:
            out.append(f"半日量能是昨日同期的 {vratio:.0%}，属于正常水平 —— "
                       f"下午若量能明显放大，方向才有延续性；否则视为盘中反弹。")

    gap = b["median_pct"] - idx["pct"]
    if abs(gap) > 0.6:
        side = "中小市值" if gap > 0 else "权重"
        out.append(f"结构上{side}明显强于指数（中位数与指数差 {gap:+.2f}pp），"
                   f"下午盯{side}能不能延续，这决定尾盘的方向。")
    return out


def _temp_reversion(trend, hot=True):
    """用历史表实测「当前温度档位之后 2 日温度回落/回升」的频率。
    返回 (概率, 样本数) 或 None。不编造概率 —— 算不出来就不说。"""
    try:
        import os
        import pandas as pd
        from .history import HIST_CSV
        if not os.path.exists(HIST_CSV):
            return None
        df = pd.read_csv(HIST_CSV, encoding="utf-8-sig").sort_values("date")
        t = df["temp"].astype(float).reset_index(drop=True)
        fwd = t.shift(-2)
        m = fwd.notna() & ((t >= 75) if hot else (t <= 30))
        if m.sum() < 5:
            return None
        hit = (fwd[m] < t[m]) if hot else (fwd[m] > t[m])
        return float(hit.mean()), int(m.sum())
    except Exception:
        return None


def pm_prep(b, strength, broken, vratio, idx, temp, anom, lad, trend):
    """收盘专属：明天准备什么。只产出「明天能执行」的动作。"""
    out = []
    if lad and lad.get("ladder"):
        top = lad["ladder"][0]
        out.append(f"明日第一件事：盯 {top[0]} 板那 {len(top[1])} 只"
                   f"（{'、'.join(n for _, n, _ in top[1][:3])}）能否续板 —— "
                   f"它是当前情绪的唯一高点，断了就说明这轮短线结束。")

    promo = {bd: v for bd, v in (lad or {}).get("promotion", [])}
    if promo:
        bd = max(promo)
        v = promo[bd]
        if v["total"] >= 3:
            r = v["ok"] / v["total"]
            tone = "接力意愿强" if r >= 0.5 else ("接力偏弱" if r < 0.3 else "接力一般")
            out.append(f"今日 {bd} 板晋级率 {r:.0%}（{v['ok']}/{v['total']}），{tone}，"
                       f"明天开板后的承接力度可以拿这个当基准。")

    hot = [a for a in anom if a.get("hot")]
    if hot:
        names = "、".join(a["name"] for a in hot[:3])
        out.append(f"明日第二件事：核对 {names} 的公告与龙虎榜 —— "
                   f"今天它们是自选股里偏离最大的，独立因素没查清之前不要加仓。")

    # 温度均值回归：只说「温度」会回落，不说「指数」会跌。
    # 实测上证未来 2 日下跌概率 67%（n=9）vs 基线 57%，优势仅 10pp、样本太小，
    # 这正是本项目否决方向预测的同一个理由，所以不写进结论。
    # 温度自身的回归则显著（89% vs 基线 50%），且表述上不构成方向预测。
    if temp["total"] >= 75:
        rev = _temp_reversion(trend, hot=True)
        if rev:
            p, n = rev
            out.append(f"温度 {temp['total']} 分已到偏热区。历史同档位（≥75 分）共 {n} 次，"
                       f"其中 {p:.0%} 在 2 个交易日内温度回落（全样本基线 50%），"
                       f"明天优先做减法而不是加法。注意这是温度回落频率，不是指数涨跌预测。")
        else:
            out.append(f"温度 {temp['total']} 分已到偏热区，历史样本不足无法给出回落频率，"
                       f"明天优先做减法而不是加法。")
    elif temp["total"] <= 30:
        rev = _temp_reversion(trend, hot=False)
        if rev:
            p, n = rev
            out.append(f"温度 {temp['total']} 分在冰点区。历史同档位（≤30 分）共 {n} 次，"
                       f"其中 {p:.0%} 在 2 个交易日内温度回升，"
                       f"明天可以开始留意超跌反弹的第一根阳线。")
        else:
            out.append(f"温度 {temp['total']} 分在冰点区，这个位置通常意味着恐慌已释放，"
                       f"明天可以开始留意超跌反弹的第一根阳线。")

    if strength and strength["median"] >= 0.65:
        out.append(f"今天收盘位置中位数 {strength['median']:.2f}，收在高位，"
                   f"明天高开的概率偏大，注意高开后的抛压。")

    if trend and trend.get("pctile") is not None:
        out.append(f"温度处于近 {trend['n']} 个交易日的 {trend['pctile']:.0f}% 分位，"
                   f"明天的仓位可以按这个分位对照自己的风险承受度来定。")
    return out
def conclusion(session, b, temp, idx, vratio, anom):
    """把数字翻译成判断。规则化生成，不调用大模型。"""
    s = []
    tag = "午盘" if session == "am" else "收盘"
    band = temp["band"]
    s.append(f"{C.MARKET_NAME} {b['n']} 只个股中 {b['up']} 涨 / {b['down']} 跌，涨幅中位数 {b['median_pct']:+.2f}%，"
             f"市场温度 {temp['total']} 分（{band}）。")

    gap = b["median_pct"] - idx["pct"]
    if gap > 0.6:
        s.append(f"结构上个股强于指数：涨幅中位数比上证高 {gap:.2f} 个百分点，"
                 f"说明权重股拖累指数、中小市值更活跃，是典型的『指数弱于体感』的一天。")
    elif gap < -0.6:
        s.append(f"结构上指数强于个股：涨幅中位数比上证低 {abs(gap):.2f} 个百分点，"
                 f"上涨由权重贡献，实际赚钱效应比指数看起来差。")

    if vratio is not None:
        ref = "昨日同期" if session == "am" else "昨日"
        if vratio > 1.15:
            s.append(f"量能明显放大，为{ref}的 {vratio:.0%}，资金参与度高。")
        elif vratio < 0.85:
            s.append(f"量能萎缩，仅为{ref}的 {vratio:.0%}，观望情绪重。")
        else:
            s.append(f"量能与{ref}基本持平（{vratio:.0%}）。")

    if b["limit_up"] >= 60:
        s.append(f"涨停 {b['limit_up']} 家、跌停 {b['limit_down']} 家，短线情绪偏活跃。")
    elif b["limit_up"] <= 20:
        s.append(f"涨停仅 {b['limit_up']} 家，短线赚钱效应偏弱。")

    hot = [a for a in anom if a["hot"]]
    if hot:
        names = "、".join(a["name"] for a in hot[:4])
        tail = " 等" if len(hot) > 4 else ""
        s.append(f"自选股中 {len(hot)} 只异动：{names}{tail}，需要看是板块联动还是个股独立事件。")
    else:
        s.append("自选股整体平稳，无显著异动。")
    return s
