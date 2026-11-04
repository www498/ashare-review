# -*- coding: utf-8 -*-
"""
报告层：把分析结果渲染成 Markdown。

午盘与收盘是两份不同的报告，不是同一份换个标题：
    午盘 → 回答「下午怎么走」，用半日量能、上午收盘位置、炸板率（收盘后即消失）
    收盘 → 回答「明天怎么准备」，用全天量能、连板梯队、温度趋势、明日波动区间
"""
from . import config as C


def _fmt_yi(x):
    return f"{x:,.0f} 亿"


def _pct(v, nd=2):
    return f"{v:+.{nd}f}%" if v is not None else "—"


def _spark(vals):
    """把一串温度值渲成方块迷你图"""
    chars = "▁▂▃▄▅▆▇█"
    if not vals:
        return ""
    mn, mx = min(vals), max(vals)
    if mx - mn < 1e-9:
        return chars[3] * len(vals)
    return "".join(chars[min(7, int((v - mn) / (mx - mn) * 7.999))] for v in vals)


def _sec_indices(L, ctx, idxs):
    tag = "上午" if ctx["session"] == "am" else ""
    L.append(f"## 一、指数{tag}")
    L.append("")
    L.append("| 指数 | 现价 | 涨跌幅 | 成交额 |")
    L.append("|---|---:|---:|---:|")
    for name, q in idxs:
        amt = q["amount"] / 1e4 if q["amount"] else 0
        L.append(f"| {name} | {q['price']:,.2f} | {q['pct']:+.2f}% | {amt:,.0f} 亿 |")
    L.append("")


def _sec_breadth(L, ctx, b, session):
    label = "上午" if session == "am" else "全天"
    L.append(f"## 二、{C.MARKET_NAME} {label}宽度（{b['n']} 只）")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---:|")
    L.append(f"| 上涨 / 下跌 / 平盘 | {b['up']} / {b['down']} / {b['flat']} |")
    L.append(f"| 上涨家数占比 | {b['up_ratio']:.1%} |")
    L.append(f"| 涨停 / 跌停 | {b['limit_up']} / {b['limit_down']} |")
    L.append(f"| 涨幅中位数 | {b['median_pct']:+.2f}% |")
    L.append(f"| 涨幅 90 / 10 分位 | {b['p90']:+.2f}% / {b['p10']:+.2f}% |")
    L.append(f"| {C.MARKET_NAME} 成交额 | {_fmt_yi(b['amount_yi'])} |")
    L.append(f"| 振幅中位数 | {b['median_amp']:.2f}% |")
    L.append(f"| 振幅超 8% 家数 | {b['amp_over8']} |")
    L.append("")
    if b["limit_up_names"]:
        L.append(f"涨停代表：{'、'.join(b['limit_up_names'])}")
        L.append("")


def _sec_am_panel(L, ctx):
    """午盘专属：上午盘面特征。收盘后这些数据就没了。"""
    st, bk = ctx.get("strength"), ctx.get("broken")
    L.append("## 三、上午盘面特征")
    L.append("")
    if st:
        L.append("| 上午收盘位置 | 数值 | 含义 |")
        L.append("|---|---:|---|")
        L.append(f"| 中位数 | {st['median']:.2f} | 1=收在上午最高，0=收在最低 |")
        L.append(f"| 贴近最高（>0.8） | {st['near_high']} 只（{st['near_high_ratio']:.0%}） | 上午走强 |")
        L.append(f"| 贴近最低（<0.2） | {st['near_low']} 只（{st['near_low_ratio']:.0%}） | 上午走弱 |")
        L.append("")
    if bk and bk["hit"]:
        rate = bk["rate"] or 0
        L.append(f"**炸板率 {rate:.0%}** —— 上午有 {bk['hit']} 只摸过涨停，"
                 f"其中 {bk['sealed']} 只封住、{bk['broken']} 只炸板。")
        L.append("")
        if bk["names"]:
            L.append("炸板个股：" + "、".join(f"{n}（{p:+.2f}%）" for n, p in bk["names"]))
            L.append("")
        L.append("> 炸板率是短线情绪转弱的领先信号：封板资金不坚决，下午高位股容易退潮。")
        L.append("")


def _sec_ladder(L, ctx, lad):
    _lbl = "今日" if lad.get("has_today") else f"今日，历史基准 {lad['asof']}"
    L.append(f"## 三、连板梯队（{_lbl}）")
    L.append("")
    if lad.get("stale"):
        msg = lad.get("stale_msg") or (
            f"日K 缓存最后一天是 {lad['asof']}，连板数可能不准，"
            f"运行 `python -m ashare.history` 刷新后再看。")
        L.append(f"> ⚠️ {msg}")
        L.append("")
    L.append("| 板位 | 家数 | 代表 |")
    L.append("|---|---:|---|")
    for board, items in lad["ladder"]:
        names = "、".join(n for _, n, _ in items[:8])
        more = f" 等 {len(items)} 只" if len(items) > 8 else ""
        L.append(f"| {board} 板 | {len(items)} | {names}{more} |")
    L.append("")
    promo = [(bd, v) for bd, v in lad["promotion"] if v["total"] >= 2]
    if promo:
        L.append("| 晋级 | 比例 | 家数 |")
        L.append("|---|---:|---:|")
        for bd, v in sorted(promo, key=lambda x: -x[0]):
            L.append(f"| {bd} 板 → {bd+1} 板 | {v['ok']/v['total']:.0%} | {v['ok']}/{v['total']} |")
        L.append("")
    pf = lad["perf"]
    if pf["n"]:
        L.append(f"昨日涨停股今日平均 {pf['avg']:+.2f}%，红盘率 {pf['red']:.0%}"
                 f"（{pf['n']} 只），这是短线打板赚钱效应的直接读数。")
        L.append("")


def _sec_temperature(L, ctx, b, temp, idxs):
    L.append("## 四、市场温度拆解")
    L.append("")
    L.append("| 分项 | 得分 | 满分 | 说明 |")
    L.append("|---|---:|---:|---|")
    vref = "昨日同期" if ctx["session"] == "am" else "昨日"
    desc = {
        "breadth": f"上涨家数占比 {b['up_ratio']:.1%}",
        "limit": f"净涨停 {b['limit_up'] - b['limit_down']}（涨停 {b['limit_up']} / 跌停 {b['limit_down']}）",
        "index": f"上证 {idxs[0][1]['pct']:+.2f}%",
        "volume": f"量能为{vref}的 {ctx['vratio']:.0%}" if ctx["vratio"] else "量能基准缺失",
        "median": f"个股涨幅中位数 {b['median_pct']:+.2f}%",
    }
    label = {"breadth": "宽度", "limit": "涨跌停结构", "index": "指数",
             "volume": "量能", "median": "个股中位数"}
    for k in ["breadth", "limit", "index", "volume", "median"]:
        L.append(f"| {label[k]} | {temp['sub'][k]} | {C.WEIGHTS[k]} | {desc[k]} |")
    L.append(f"| **合计** | **{temp['total']}** | **100** | **{temp['band']}** |")
    L.append("")
    L.append("> 温度是自建相对指标，五个分项各 20 分，**没有绝对意义**。"
             "单看某一天容易误导，建议对比最近 5~10 个交易日的变化趋势。")
    L.append("")

    # 趋势只在收盘报告里画：午盘写历史会污染口径
    tr = ctx.get("trend")
    if ctx["session"] == "pm" and tr:
        L.append(f"### 温度趋势（截至 {tr['asof']}，近 {len(tr['series'])} 个交易日）")
        L.append("")
        L.append("```")
        L.append(f"{_spark([float(x[1]) for x in tr['series']])}   当前 {tr['cur']:.1f}")
        L.append(f"{tr['series'][0][0]}  →  {tr['series'][-1][0]}")
        L.append("```")
        L.append("")
        ma20 = f"{tr['ma20']:.1f}" if tr["ma20"] is not None else "—"
        chg5 = f"{tr['chg5']:+.1f}" if tr["chg5"] is not None else "—"
        L.append("| 当前 | 5 日均 | 10 日均 | 20 日均 | 历史分位 | 5 日变化 |")
        L.append("|---:|---:|---:|---:|---:|---:|")
        L.append(f"| **{tr['cur']:.1f}** | {tr['ma5']:.1f} | {tr['ma10']:.1f} | {ma20} | "
                 f"{tr['pctile']:.0f}% | {chg5} |")
        L.append("")
        note = f"> 历史分位指当前温度在已记录的 {tr['n']} 个交易日中高于百分之多少的日子。"
        if tr["asof"] != ctx["date"]:
            note += f"趋势表只收录已收盘的交易日，故截至 {tr['asof']}，与上方当日温度可能不同。"
        L.append(note)
        L.append("")


def _sec_watch(L, ctx, name):
    L.append(f"## 五、{name}")
    L.append("")

    # 持仓概览（只在填了数量+成本时出现）
    p = ctx.get("portfolio")
    if p and p.get("rows"):
        L.append("### 持仓")
        L.append("")
        L.append(f"总市值 **{p['total_mv']:,.0f}** 元　·　"
                 f"总浮盈 **{p['total_pnl']:+,.0f}** 元（{p['total_pnl_pct']:+.2f}%）　·　"
                 f"今日 **{p['total_today']:+,.0f}** 元（{p['total_today_pct']:+.2f}%）")
        L.append("")
        L.append("| 名称 | 数量 | 成本 | 现价 | 市值 | 浮盈 | 盈亏率 | 占比 |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in p["rows"]:
            L.append(f"| {r['name']} | {r['shares']:,.0f} | {r['cost']:,.2f} | {r['price']:,.2f} | "
                     f"{r['mv']:,.0f} | {r['pnl']:+,.0f} | {_pct(r['pnl_pct'])} | "
                     f"{r['weight']:.0f}% |")
        L.append("")
        wm = ctx.get("watch_meta") or {}
        if wm.get("kind") == "statement":
            L.append("> 成本由交割单按移动加权还原，**已含佣金/过户费/印花税**；"
                     "期间分红送转不在买卖流水内，若有送股请核对数量。"
                     "今日盈亏按（现价 − 昨收）× 数量估算。")
        else:
            L.append("> 成本按导入值计算（交割单导入的已含手续费，手填的未计）；"
                     "分红送转未计入。今日盈亏按（现价 − 昨收）× 数量估算。")
        L.append("")

    L.append("| 名称 | 代码 | 现价 | 涨跌幅 | 振幅 | 量比 | 状态 |")
    L.append("|---|---|---:|---:|---:|---:|---|")
    for a in ctx["anomalies"]:
        state = "关注" if a["hot"] else "平稳"
        L.append(f"| {a['name']} | {a['code']} | {a['price']:,.2f} | {a['pct']:+.2f}% | "
                 f"{a['amp']:.1f}% | {a['vol_ratio']:.1f} | {state} |")
    L.append("")

    # 个股诊断
    cards = ctx.get("cards") or {}
    if cards:
        L.append("### 个股诊断")
        L.append("")
        order = [a["code"] for a in ctx["anomalies"] if a["code"] in cards]
        for code in order:
            c = cards[code]
            L.append(f"**{c['name']}** {c['price']:,.2f}　{_pct(c['pct'])}")
            L.append("")
            L.append(c["summary"])
            L.append("")
            L.append("　".join(f"{k} {v}" for k, v in c["metrics"]))
            L.append("")
            for n in c["watch"][:4]:
                L.append(f"- {n}")
            L.append("")

    hot = [a for a in ctx["anomalies"] if a.get("hot")]
    if hot:
        L.append("### 异动归因（个股 vs 所属行业）")
        L.append("")
        L.append("| 标的 | 涨跌幅 | 所属行业 | 行业中位数 | 偏离 | 判断 |")
        L.append("|---|---:|---|---:|---:|---|")
        for a in hot:
            at = a.get("attr")
            if not at:
                L.append(f"| {a['name']} | {a['pct']:+.2f}% | — | — | — | 行业数据缺失 |")
                continue
            L.append(f"| {a['name']} | {a['pct']:+.2f}% | {at['industry']} | "
                     f"{at['ind_median']:+.2f}% | {at['gap']:+.2f}pp | {at['verdict']} |")
        L.append("")
        L.append("> 判断规则：个股涨跌幅与所属行业中位数偏离在 1 个百分点以内视为跟随板块；"
                 "超出则说明是个股独立因素（公告、业绩、资金），需要单独找原因。")
        L.append("")

    fc = ctx.get("forecast")
    if fc:
        L.append("### 未来 5 日波动与区间（80%）")
        L.append("")
        L.append("| 标的 | 现价 | 预期日波动 | 80% 区间 | 区间实测覆盖率 | 模型样本外 R² |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for r in fc:
            L.append(f"| {r['name']} | {r['price']:,.2f} | {r['sigma_5d'] * 100:.2f}% | "
                     f"{r['lo']:,.2f} ~ {r['hi']:,.2f} | {r['coverage']:.0%} | {r['r2']:.2f} |")
        L.append("")
        L.append("> 不预测涨跌方向，只给波动包络。覆盖率是**滚动样本外**实测值（本应覆盖 80%，"
                 "越接近说明标定越准）；R² 在 0.00~0.13 之间，个别标的为负表示该标的波动率不可预测。")
        L.append("")


def _sec_action(L, ctx, num_cn):
    """午盘=下午观察，收盘=明日准备。这是两份报告的核心差异。"""
    am = ctx["session"] == "am"
    view = ctx.get("session_view")
    L.append(f"## {num_cn}、{'下午观察' if am else '明日准备'}")
    L.append("")

    if ctx.get("conclusion"):
        L.append("### 盘面结论")
        L.append("")
        for line in ctx["conclusion"]:
            L.append(f"- {line}")
        L.append("")

    if not view:
        return
    L.append(f"### {'下午盯这几点' if am else '明天做这几件事'}")
    L.append("")
    if am:
        L.append("> 下面每条都可以在下午收盘前被验证。判断错了，收盘那份报告会对上。")
    else:
        L.append("> 下面每条都是明天开盘后可以直接执行的动作，不是感想。")
    L.append("")
    for i, line in enumerate(view, 1):
        L.append(f"{i}. {line}")
    L.append("")


def _sec_overview(L, ctx):
    """市场概况：每个指标都说明它意味着什么。"""
    ov = ctx.get("overview")
    dist = ctx.get("dist")
    if not ov and not dist:
        return
    L.append("## 〇、市场概况")
    L.append("")
    if dist and dist.get("total"):
        L.append("### 涨跌幅分布")
        L.append("")
        L.append("| " + " | ".join(dist["labels"]) + " |")
        L.append("|" + "---:|" * len(dist["labels"]))
        L.append("| " + " | ".join(str(c) for c in dist["counts"]) + " |")
        L.append("")
        cnt = dict(zip(dist["labels"], dist["counts"]))
        strong = cnt.get("涨停", 0) + cnt.get("涨停-5%", 0) + cnt.get("5-1%", 0)
        weak = cnt.get("跌停", 0) + cnt.get("-5%-跌停", 0) + cnt.get("-1--5%", 0)
        L.append(f"> 涨幅 1% 以上 **{strong}** 只，跌幅 1% 以上 **{weak}** 只。"
                 f"分布形态比涨跌家数更能说明问题：同样是普涨，"
                 f"集中在 0~1% 是«搭便车式反弹»，集中在 5% 以上才是真正的赚钱效应。")
        L.append("")
    if ov:
        L.append("### 关键指标与含义")
        L.append("")
        for r in ov:
            L.append(f"**{r['key']}　{r['value']}**")
            L.append("")
            if r.get("note"):
                L.append(f"- 读数：{r['note']}")
            L.append(f"- 影响：{r['impact']}")
            L.append("")


def _sec_profile(L, ctx):
    """交易行为画像：基于历史交割单，不只看今天。"""
    p = ctx.get("profile")
    if not p:
        return
    c = p["core"]
    L.append("## 八、交易行为画像")
    L.append("")
    span = ""
    if c.get("first_day"):
        span = f"（{c['first_day']} ~ {c['last_day']}，共 {c.get('span_days', 0)} 天）"
    L.append(f"> 基于 **{c.get('trades_total', 0)}** 笔历史成交{span}，"
             f"FIFO 配对出 **{c['n_closed']}** 笔已完成交易。"
             f"全部来自交割单真实记录，可逐笔追溯。")
    L.append("")

    if p.get("tags"):
        L.append("### 行为标签")
        L.append("")
        for name, basis, level in p["tags"]:
            mark = {"warn": "⚠️", "good": "✅", "info": "·"}.get(level, "·")
            L.append(f"- {mark} **{name}** —— {basis}")
        L.append("")

    L.append("### 核心指标")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---:|")
    L.append(f"| 已实现盈亏 | {c['realized_pnl']:+,.2f} 元 |")
    if c.get("unrealized_pnl") is not None:
        L.append(f"| 当前持仓浮动 | {c['unrealized_pnl']:+,.2f} 元 |")
        L.append(f"| 合计 | {c['realized_pnl'] + c['unrealized_pnl']:+,.2f} 元 |")
    if c.get("win_rate") is not None:
        L.append(f"| 胜率 | {c['win_rate']:.1%}（{c['n_win']}/{c['n_closed']}） |")
    if c.get("profit_factor") is not None:
        L.append(f"| 盈亏比 | {c['profit_factor']:.2f} |")
    if c.get("avg_win") is not None:
        L.append(f"| 平均盈利 / 亏损 | {c['avg_win']:+,.0f} / {c['avg_loss']:+,.0f} 元 |")
    if c.get("hold_avg") is not None:
        L.append(f"| 平均持有 | {c['hold_avg']:.1f} 天（中位数 {c['hold_median']:.0f}） |")
    if c.get("hold_win") and c.get("hold_loss"):
        L.append(f"| 盈利单 / 亏损单持有 | {c['hold_win']:.1f} / {c['hold_loss']:.1f} 天 |")
    L.append(f"| 累计手续费 | {c['fee_total']:,.2f} 元 |")
    L.append("")

    if p.get("findings"):
        L.append("### 逐项解读")
        L.append("")
        for title, value, impact in p["findings"]:
            L.append(f"**{title}：{value}**")
            L.append("")
            L.append(f"- {impact}")
            L.append("")

    if p.get("per_stock"):
        L.append("### 分标的表现")
        L.append("")
        L.append("| 标的 | 已完成 | 累计盈亏 | 胜率 | 平均持有 |")
        L.append("|---|---:|---:|---:|---:|")
        for s in p["per_stock"]:
            hold = f"{s['hold_avg']:.1f} 天" if s.get("hold_avg") is not None else "—"
            wr = f"{s['win_rate']:.0%}" if s.get("win_rate") is not None else "—"
            L.append(f"| {s['name']} | {s['n']} 笔 | {s['pnl']:+,.2f} | {wr} | {hold} |")
        L.append("")
        L.append("> 按累计盈亏升序。排在最前的是最需要复盘的标的 —— "
                 "如果同一只票反复亏损，问题通常不在行情而在交易方式。")
        L.append("")


def render(ctx):
    session = ctx["session"]
    tag = "午盘" if session == "am" else "收盘"
    b, temp, idxs = ctx["breadth"], ctx["temperature"], ctx["indices"]
    L = []

    L.append(f"# {C.MARKET_NAME} 复盘 · {ctx['date']} · {tag}总结")
    L.append("")
    L.append(f"> **市场温度 {temp['total']} / 100　·　{temp['band']}**　"
             f"（行情时点 {ctx.get('quote_ts', '--:--')}，取数耗时 {ctx.get('latency', '-')}）")
    L.append("")
    if ctx.get("warning"):
        L.append(f"> ⚠️ **{ctx['warning']}**")
        L.append("")

    _sec_overview(L, ctx)
    _sec_indices(L, ctx, idxs)
    _sec_breadth(L, ctx, b, session)

    if session == "am":
        _sec_am_panel(L, ctx)
    elif ctx.get("ladder") and ctx["ladder"]["ladder"]:
        _sec_ladder(L, ctx, ctx["ladder"])

    _sec_temperature(L, ctx, b, temp, idxs)
    _sec_watch(L, ctx, "自选股（上午）" if session == "am" else "自选股")
    _sec_action(L, ctx, "六")

    # 七、板块
    if ctx.get("sector"):
        sec = ctx["sector"]
        L.append("## 七、板块资金流（行业）")
        L.append("")
        L.append("| 方向 | 板块 | 涨跌幅 | 主力净流入 |")
        L.append("|---|---|---:|---:|")
        for nm, pct, amt in sec["top"]:
            L.append(f"| 流入 | {nm} | {pct:+.2f}% | {amt / 1e8:,.2f} 亿 |")
        for nm, pct, amt in sec["bottom"]:
            L.append(f"| 流出 | {nm} | {pct:+.2f}% | {amt / 1e8:,.2f} 亿 |")
        L.append("")

    _sec_profile(L, ctx)

    L.append("---")
    L.append("")
    L.append("**数据口径说明**")
    L.append("")
    L.append(f"- 行情：腾讯财经接口（{C.MARKET_NAME} 全量实时快照），与东财盘口存在秒级差异")
    L.append(f"- 宽度统计覆盖 {C.MARKET_NAME} 全部在市个股，含 ST")
    L.append("- 涨停判定：现价达到当日涨停价（主板 10%、创业板/科创板 20%、北交所 30%）；"
             "历史回补用涨跌幅阈值，两套口径一致")
    L.append("- 历史回补：新浪日K（不复权，剔除 |涨跌幅| > 21.5% 的除权跳空）；波动率模型用 baostock 前复权")
    if session == "am":
        L.append("- 上午收盘位置 =（现价 − 上午最低）/（上午最高 − 上午最低），衡量上午最后一小时的动能")
    if ctx["vratio"]:
        from .analyze import elapsed_share
        share = elapsed_share(ctx.get("quote_ts", "15:00"))
        L.append(f"- 量能基准：按行情时点折算已走完全天的 {share:.0%}（上午记 53%、下午按分钟补齐），"
                 f"再与昨日全日成交量对比")
    L.append("- 本报告为历史与实时数据的统计描述，不构成投资建议")
    return "\n".join(L)
