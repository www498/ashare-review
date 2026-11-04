# -*- coding: utf-8 -*-
"""
交易行为画像：从交割单历史还原「这个人是怎么做交易的」。

和市场分析的区别：市场分析讲"盘面怎么样"，这里讲"你自己做得怎么样"。
这是本产品区别于普通行情软件的核心——行情软件只给你看市场，不告诉你你的问题。

全部指标来自交割单的真实成交记录，FIFO 配对计算，可逐笔追溯。
不使用大模型，不做收益预测，只对已发生的行为做统计归纳。

口径说明（重要，避免误读）：
- 已实现盈亏：按 FIFO（先买先卖）配对，含双边手续费
- 持有天数：自然日（含周末），不是交易日
- 胜率：盈利笔数 / 已配对笔数，部分卖出算独立一笔
- 浮动盈亏不计入胜率，只在"知行合一"里与已实现对比
"""
import datetime as dt

FEE_COLS = ["佣金", "其他费用", "印花税", "过户费"]

BUY_WORDS = ("证券买入", "买入", "申购")
SELL_WORDS = ("证券卖出", "卖出", "赎回")


def _num(v):
    try:
        if v is None:
            return 0.0
        s = str(v).replace(",", "").strip()
        if not s or s in ("-", "--", "—"):
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def fifo_match(df, col):
    """FIFO 配对买卖，返回已实现交易列表。

    为什么用 FIFO 而不是移动加权：移动加权只能给出"总体成本"，
    无法还原"每一笔持有了多久、赚了多少"——而持有时长正是行为画像的核心。
    """
    import pandas as pd

    c_code, c_name = col["code"], col.get("name")
    c_act, c_qty, c_px = col["action"], col["qty"], col["price"]
    c_date = col.get("date")
    fees = [c for c in (col.get("fees") or []) if c]

    out = []
    for code, g in df.groupby(c_code, sort=False):
        lots = []          # 未卖出的买入批次 [剩余数量, 买价, 买入日, 单股买入费]
        name = str(g.iloc[-1][c_name]).strip() if c_name else ""
        for _, r in g.iterrows():
            act = str(r[c_act] or "")
            q, px = _num(r[c_qty]), _num(r[c_px])
            if q <= 0 or px <= 0:
                continue
            fee_total = sum(_num(r[c]) for c in fees)
            fee_per = fee_total / q if q else 0.0
            day = r[c_date] if c_date else None

            if any(w in act for w in BUY_WORDS):
                lots.append([q, px, day, fee_per])
            elif any(w in act for w in SELL_WORDS):
                left = q
                while left > 0 and lots:
                    lot = lots[0]
                    take = min(left, lot[0])
                    pnl = (px - lot[1]) * take - fee_per * take - lot[3] * take
                    hold = None
                    if day is not None and lot[2] is not None:
                        try:
                            hold = (day - lot[2]).days
                        except Exception:
                            hold = None
                    out.append({
                        "code": code, "name": name, "qty": take,
                        "buy_px": lot[1], "sell_px": px,
                        "buy_date": str(getattr(lot[2], "date", lambda: lot[2])()),
                        "sell_date": str(getattr(day, "date", lambda: day)()),
                        "hold_days": hold,
                        "pnl": pnl,
                        "ret_pct": (px / lot[1] - 1) * 100 if lot[1] else 0.0,
                    })
                    lot[0] -= take
                    left -= take
                    if lot[0] <= 1e-9:
                        lots.pop(0)
    return out


def build(df, col, positions=None, quotes=None):
    """生成完整画像。

    df/col: 交割单与列映射（由 statement 模块提供）
    positions: {code: {shares, cost}} 当前持仓，用于"知行合一"对比
    quotes: {code: 行情} 当前价，用于算浮动盈亏
    返回 dict，键都是可直接渲染的结构。
    """
    import numpy as np

    trades = fifo_match(df, col)
    if not trades:
        return None

    pnl = np.array([t["pnl"] for t in trades], dtype=float)
    rets = np.array([t["ret_pct"] for t in trades], dtype=float)
    holds = np.array([t["hold_days"] for t in trades if t["hold_days"] is not None],
                     dtype=float)
    win_mask = pnl > 0
    loss_mask = pnl < 0
    n = len(trades)

    gross_win = float(pnl[win_mask].sum()) if win_mask.any() else 0.0
    gross_loss = float(abs(pnl[loss_mask].sum())) if loss_mask.any() else 0.0

    w_hold = np.array([t["hold_days"] for t in trades
                       if t["pnl"] > 0 and t["hold_days"] is not None], dtype=float)
    l_hold = np.array([t["hold_days"] for t in trades
                       if t["pnl"] < 0 and t["hold_days"] is not None], dtype=float)

    core = {
        "n_closed": n,
        "realized_pnl": float(pnl.sum()),
        "win_rate": float(win_mask.mean()) if n else None,
        "n_win": int(win_mask.sum()), "n_loss": int(loss_mask.sum()),
        "gross_win": gross_win, "gross_loss": gross_loss,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "avg_win": float(pnl[win_mask].mean()) if win_mask.any() else None,
        "avg_loss": float(pnl[loss_mask].mean()) if loss_mask.any() else None,
        "avg_win_pct": float(rets[win_mask].mean()) if win_mask.any() else None,
        "avg_loss_pct": float(rets[loss_mask].mean()) if loss_mask.any() else None,
        "best_pct": float(rets.max()) if n else None,
        "worst_pct": float(rets.min()) if n else None,
        "hold_avg": float(holds.mean()) if len(holds) else None,
        "hold_median": float(np.median(holds)) if len(holds) else None,
        "hold_win": float(w_hold.mean()) if len(w_hold) else None,
        "hold_loss": float(l_hold.mean()) if len(l_hold) else None,
    }

    # 费用：高频交易的隐性成本，很多人完全没概念
    fees = [c for c in (col.get("fees") or []) if c]
    fee_sum = float(sum(_num(v) for c in fees for v in df[c])) if fees else 0.0
    turnover = float(sum(_num(v) for v in df[col["qty"]] * df[col["price"]])) \
        if col.get("qty") and col.get("price") else 0.0
    core["fee_total"] = fee_sum
    core["turnover"] = turnover
    core["fee_ratio"] = (fee_sum / turnover) if turnover else None
    core["fee_vs_pnl"] = (fee_sum / abs(core["realized_pnl"])) \
        if core["realized_pnl"] else None

    # 交易节奏
    c_date = col.get("date")
    if c_date:
        days = sorted({str(getattr(v, "date", lambda: v)()) for v in df[c_date]})
        span = None
        if len(days) >= 2:
            try:
                d0 = dt.date.fromisoformat(days[0])
                d1 = dt.date.fromisoformat(days[-1])
                span = (d1 - d0).days
            except Exception:
                span = None
        core["active_days"] = len(days)
        core["span_days"] = span
        core["trades_total"] = int(len(df))
        core["trades_per_active_day"] = len(df) / len(days) if days else None
        core["first_day"], core["last_day"] = days[0], days[-1]

    # 分标的表现：看是不是在同一只票上反复犯错
    by_code = {}
    for t_ in trades:
        r = by_code.setdefault(t_["code"], {"name": t_["name"], "n": 0, "pnl": 0.0,
                                            "win": 0, "holds": []})
        r["n"] += 1
        r["pnl"] += t_["pnl"]
        r["win"] += 1 if t_["pnl"] > 0 else 0
        if t_["hold_days"] is not None:
            r["holds"].append(t_["hold_days"])
    per_stock = []
    for code, r in by_code.items():
        per_stock.append({
            "code": code, "name": r["name"], "n": r["n"],
            "pnl": round(r["pnl"], 2),
            "win_rate": r["win"] / r["n"] if r["n"] else None,
            "hold_avg": (sum(r["holds"]) / len(r["holds"])) if r["holds"] else None,
        })
    per_stock.sort(key=lambda x: x["pnl"])

    # 知行合一：已实现 vs 当前浮动。
    # 典型问题是"赚的卖掉、亏的留着"，这会让已实现为正而账户实际亏钱。
    unreal = None
    if positions and quotes:
        tot = 0.0
        for code, p in positions.items():
            q = quotes.get(code) or {}
            px = q.get("price")
            if px and p.get("shares") and p.get("cost"):
                tot += (px - p["cost"]) * p["shares"]
        unreal = tot
    core["unrealized_pnl"] = unreal

    tags = _tags(core, per_stock)
    return {"core": core, "trades": trades, "per_stock": per_stock,
            "tags": tags, "findings": _findings(core, per_stock),
            "persona": persona(core, per_stock, tags),
            "playbook": playbook(core, trades, per_stock, positions, quotes)}


def persona(c, per_stock, tags=None):
    """把指标翻译成「人格速写」：一个类型名、一句解释、几条硬事实、一条最该改的事。

    原则：只用已经算出来的指标组合，不做心理侧写。
    每个判断都能回溯到具体数字，避免「你是一个谨慎的投资者」这种没有信息量的废话。
    """
    wr, pf = c.get("win_rate"), c.get("profit_factor")
    h = c.get("hold_avg")
    hw, hl = c.get("hold_win"), c.get("hold_loss")
    aw, al = c.get("avg_win"), c.get("avg_loss")

    # ---- 节奏：按平均持有天数 ----
    if h is None:
        pace, pace_note = "节奏未知", ""
    elif h <= 3:
        pace, pace_note = "超短", f"平均 {h:.1f} 天就出手，几乎不留隔夜"
    elif h <= 10:
        pace, pace_note = "短线", f"平均拿 {h:.1f} 天，多数交易在一两周内结束"
    elif h <= 30:
        pace, pace_note = "波段", f"平均持有 {h:.1f} 天，跟一段趋势"
    else:
        pace, pace_note = "持有", f"平均持有 {h:.0f} 天，接近中线配置"

    # ---- 盈亏结构：胜率 × 盈亏比 的四种组合 ----
    if wr is None or pf is None:
        style, style_note = "样本不足", "交易记录还不够多，先积累到 20 笔以上再谈风格"
    elif wr >= 0.55 and pf >= 1.5:
        # 盈亏比高不代表「让利润跑」：如果是靠选股准、同时亏损单反而拖得更久，
        # 那是另一种画像，不能笼统说成「又准又狠」，否则和下面的 C 维度自相矛盾
        if hw and hl and hl > hw * 1.3:
            style = "准但拖亏"
            style_note = ("胜率和盈亏比都好看，但亏损单拿得比盈利单久 —— "
                          "钱是靠挑得准赚来的，不是靠拿得住")
        else:
            style, style_note = "又准又狠", "既能挑对，也能让盈利跑得比亏损远 —— 这是最稀缺的组合"
    elif wr >= 0.55:
        style, style_note = "准但保守", "十次有六次以上做对，可惜赢得不够大，利润被提前落袋"
    elif pf >= 1.5:
        style, style_note = "少而重", "做对的次数不算多，但一次赚的能盖住好几次亏"
    else:
        style, style_note = "两头都欠", "做对的次数偏少，赢的时候也没多赚，结构上需要先降频"

    # ---- 硬事实：每一条都能直接对上交割单 ----
    facts = []
    if c.get("best_pct") is not None:
        facts.append(("最赚的一笔", f'{c["best_pct"]:+.1f}%', "单笔收益率上限"))
    if c.get("worst_pct") is not None:
        facts.append(("最亏的一笔", f'{c["worst_pct"]:+.1f}%', "单笔收益率下限"))
    if aw and al and aw > 0:
        facts.append(("一次失手", f"{abs(al) / aw:.1f} 倍于均盈",
                      "亏损单平均亏的钱 ÷ 盈利单平均赚的钱"))
    if per_stock:
        worst = min(per_stock, key=lambda x: x["pnl"])
        if worst["pnl"] < 0:
            facts.append(("最拖后腿", f'{worst["name"]} {worst["pnl"]:+.0f} 元',
                          f'交易 {worst["n"]} 次，累计亏损'))

    # ---- 一条最该改的事：按「对盈亏影响最大」排序，只给一条 ----
    fix = None
    if hw and hl and hw > 0 and hl > hw * 1.5:
        fix = (f"亏损单平均拿 {hl:.0f} 天，盈利单只拿 {hw:.0f} 天。"
               f"先给每笔交易定一条止损线，别让亏损单的持有时间超过盈利单。")
    elif pf is not None and pf < 1:
        fix = (f"盈亏比 {pf:.2f}，每亏 1 元只赚回 {pf:.2f} 元。"
               f"比起找更好的票，更该先砍掉那个反复亏损的标的。")
    elif c.get("fee_vs_pnl") is not None and c["fee_vs_pnl"] >= 0.4:
        fix = (f"手续费已相当于已实现盈亏的 {c['fee_vs_pnl']:.0%}。"
               f"降低交易频率，比你多抓一个涨停更能改善净值。")
    elif wr is not None and wr >= 0.55 and aw and al and abs(al) > aw:
        fix = (f"胜率 {wr:.0%} 说明选股没问题，问题在止盈："
               f"平均赚 {aw:,.0f} 元就跑，平均亏 {abs(al):,.0f} 元。把止盈放宽一档。")
    elif c.get("hold_avg") is not None:
        fix = (f"当前节奏是{pace}（平均 {c['hold_avg']:.1f} 天）。"
               f"在这个周期里，最大的风险不是选错票，而是频繁换手带来的成本。")

    return {
        "title": f"{pace} · {style}",
        "sub": style_note,
        "pace_note": pace_note,
        "facts": facts,
        "fix": fix,
    }


def _max_loss_streak(trades):
    """最长连续亏损笔数。用来定「连亏几笔该降仓」这条规则。"""
    mx = cur = 0
    for t in trades:
        if (t.get("pnl") or 0) < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def playbook(c, trades, per_stock, positions=None, quotes=None):
    """应对手册：把画像指标翻译成「什么情况下做什么」。

    与 persona 的分工：persona 回答「你是什么样的人」，playbook 回答「下次遇到怎么办」。
    每条都必须绑定他自己的数字（平均亏损幅度、平均持有天数、最大连亏笔数），
    否则就是「要止损、要拿住」这种谁都会说的空话。
    """
    out = []
    al = c.get("avg_loss_pct")
    aw = c.get("avg_win_pct")
    hw, hl = c.get("hold_win"), c.get("hold_loss")

    # 1) 止损线：用他自己的平均亏损幅度定，不套通用的 -5%
    if al is not None and al < -1:
        line = round(al * 0.6, 1)
        tail = ""
        if hw and hl:
            tail = (f"你过去的亏损单平均拿到 {hl:.0f} 天、亏 {abs(al):.1f}%，"
                    f"而盈利单只拿 {hw:.0f} 天 —— 拖延是你亏钱的主要方式。")
        out.append({
            "when": f"单笔浮亏到 {line:.1f}%",
            "what": f"收盘前减掉一半或全部，不要等回本。{tail}",
            "tone": "warn",
        })

    # 2) 止盈：他平均赚多少就跑，但最大赚过多少
    if aw is not None and aw > 1:
        out.append({
            "when": f"盈利到 +{aw * 1.6:.1f}%",
            "what": (f"先卖一半，剩下的用回落止盈拿着。你平均只赚 {aw:.1f}% 就跑，"
                     f"但最大赚过 {c.get('best_pct') or 0:.1f}% —— "
                     f"拿得住的能力你有，只是没给它机会。"),
            "tone": "good",
        })

    # 3) 连亏降仓
    streak = _max_loss_streak(trades)
    if streak >= 2:
        out.append({
            "when": f"连续 {streak} 笔亏损之后",
            "what": ("把仓位降到平时的一半，重新做对 2 笔再加回来。"
                     "连亏时判断已经和行情脱节，这时候放大仓位只会放大错误。"),
            "tone": "warn",
        })

    # 4) 费用摩擦
    fr = c.get("fee_vs_pnl")
    if fr is not None and fr >= 0.4:
        out.append({
            "when": "同一个月内第 3 次买同一只票",
            "what": (f"停手。你的手续费已相当于已实现盈亏的 {fr:.0%}，"
                     f"再高的胜率也补不回摩擦成本。"),
            "tone": "warn",
        })

    # 5) 集中度
    if positions and quotes:
        mv = {}
        for code, p in positions.items():
            px = (quotes.get(code) or {}).get("price")
            if px and p.get("shares"):
                mv[code] = px * p["shares"]
        tot = sum(mv.values())
        if tot > 0:
            top_code, top_val = max(mv.items(), key=lambda kv: kv[1])
            share = top_val / tot
            if share >= 0.35:
                nm = (quotes.get(top_code) or {}).get("name") or top_code
                out.append({
                    "when": f"{nm} 占比已到 {share:.0%}",
                    "what": ("加仓前先问自己：这是主动判断，还是因为它涨得好所以没卖？"
                             "单票超过三分之一时，一次意外就能抹掉几个月的胜率优势。"),
                    "tone": "warn",
                })

    # 6) 区分板块与个股：这条接的是多日归因
    if per_stock:
        worst = min(per_stock, key=lambda x: x["pnl"])
        if worst["pnl"] < 0 and worst["n"] >= 2:
            out.append({
                "when": f"{worst['name']} 再次下跌",
                "what": (f"先看所属板块当天是不是也在跌。板块在涨它独跌（归因里「个股超额」为负），"
                         f"就去查公告和资金，不要补仓摊平 —— 你已经在这只票上交易 "
                         f"{worst['n']} 次、累计 {worst['pnl']:+.0f} 元。"),
                "tone": "info",
            })
    return out


NICK = {
    ("F", "C"): "快刀手",
    ("F", "R"): "狙击手",
    ("S", "C"): "守株人",
    ("S", "R"): "钓鱼者",
}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def mbti(c, per_stock, movers=None, positions=None, quotes=None):
    """交易人格四维代号，MBTI 式的四个字母 + 强弱条。

    四个维度都来自已有指标，不引入新计算：
      节奏 F/S  平均持有天数（≤7 天为快）
      归因 B/A  板块能解释多少涨跌（相对大盘超额 vs 个股超额）
      盈亏 C/R  亏损单比盈利单拿得久 → 截断利润(C)；反之让利润跑(R)
      持仓 K/D  单票最大占比（≥40% 为集中）

    字母顺序固定 F/S → B/A → C/R → K/D，方便一句话传播。
    """
    dims = []

    # 1) 节奏
    h = c.get("hold_avg")
    if h is None:
        dims.append({"dim": "节奏", "letter": "—", "pct": 0.5, "note": "无数据"})
        pace = None
    else:
        fast = h <= 7
        dims.append({
            "dim": "节奏", "letter": "F" if fast else "S",
            "left": "F 出手快", "right": "S 拿得久",
            "pct": _clamp(0.5 + (h - 7) / 30),
            "note": f"平均 {h:.1f} 天",
        })
        pace = "F" if fast else "S"

    # 2) 归因：板块解释力
    if movers:
        vals = []
        for m in movers.values():
            ind, firm = abs(m.get("industry_part") or 0), abs(m.get("firm") or 0)
            if ind + firm > 0.3:
                vals.append(ind / (ind + firm))
        if vals:
            share = sum(vals) / len(vals)
            dims.append({
                "dim": "归因", "letter": "B" if share >= 0.5 else "A",
                "left": "B 跟板块", "right": "A 走独立",
                "pct": _clamp(1 - share),
                "note": f"板块解释 {share:.0%}",
            })
        else:
            dims.append({"dim": "归因", "letter": "—", "pct": 0.5, "note": "无归因数据"})
    else:
        dims.append({"dim": "归因", "letter": "—", "pct": 0.5, "note": "无归因数据"})

    # 3) 盈亏处理
    hw, hl = c.get("hold_win"), c.get("hold_loss")
    if hw and hl:
        ratio = hl / hw
        cut = ratio >= 1.3
        dims.append({
            "dim": "盈亏", "letter": "C" if cut else "R",
            "left": "C 截断利润", "right": "R 让利润跑",
            "pct": _clamp(0.5 - (ratio - 1.3) / 2),
            "note": f"亏 {hl:.0f} 天 / 盈 {hw:.0f} 天",
        })
    else:
        cut = None
        dims.append({"dim": "盈亏", "letter": "—", "pct": 0.5, "note": "无数据"})

    # 4) 持仓集中度
    share = None
    if positions and quotes:
        mv = {}
        for code, pos in positions.items():
            px = (quotes.get(code) or {}).get("price")
            if px and pos.get("shares"):
                mv[code] = px * pos["shares"]
        tot = sum(mv.values())
        if tot > 0:
            share = max(mv.values()) / tot
    if share is not None:
        dims.append({
            "dim": "持仓", "letter": "K" if share >= 0.4 else "D",
            "left": "K 集中", "right": "D 分散",
            "pct": _clamp(0.5 - (share - 0.4) / 0.5),
            "note": f"最大 {share:.0%}",
        })
    else:
        dims.append({"dim": "持仓", "letter": "—", "pct": 0.5, "note": "无持仓"})

    code = "".join(d["letter"] for d in dims if d["letter"] != "—")
    name = NICK.get((pace, "C" if cut else "R")) if pace and cut is not None else "观察中"
    return {"code": code or "—", "name": name, "dims": dims}


def _tags(c, per_stock):
    """行为标签。每个标签都绑定触发它的具体数值，可追溯。"""
    out = []
    h = c.get("hold_avg")
    if h is not None:
        if h <= 3:
            out.append(("超短线", f"平均持有 {h:.1f} 天", "warn"))
        elif h <= 10:
            out.append(("短线波段", f"平均持有 {h:.1f} 天", "info"))
        elif h <= 30:
            out.append(("中短线", f"平均持有 {h:.1f} 天", "info"))
        else:
            out.append(("中长线", f"平均持有 {h:.1f} 天", "good"))

    hw, hl = c.get("hold_win"), c.get("hold_loss")
    if hw and hl and hl > hw * 1.5:
        out.append(("持亏惜售", f"亏损单持有 {hl:.1f} 天 vs 盈利单 {hw:.1f} 天", "warn"))

    wr = c.get("win_rate")
    aw, al = c.get("avg_win"), c.get("avg_loss")
    if wr is not None and wr >= 0.6 and aw and al and abs(al) > aw:
        out.append(("高胜率低赔率", f"胜率 {wr:.0%} 但单笔均亏是均盈的 "
                                    f"{abs(al) / aw:.1f} 倍", "warn"))
    pf = c.get("profit_factor")
    if pf is not None:
        if pf >= 2:
            out.append(("盈亏比健康", f"盈亏比 {pf:.2f}", "good"))
        elif pf < 1:
            out.append(("盈亏比失衡", f"盈亏比 {pf:.2f}（<1 为净亏）", "warn"))

    tpd = c.get("trades_per_active_day")
    if tpd and tpd >= 3:
        out.append(("交易频繁", f"活跃日均 {tpd:.1f} 笔", "warn"))

    fr = c.get("fee_vs_pnl")
    if fr is not None and fr >= 0.5:
        out.append(("费用侵蚀", f"手续费相当于已实现盈亏的 {fr:.0%}", "warn"))

    worst = min((s for s in per_stock), key=lambda x: x["pnl"], default=None)
    if worst and worst["pnl"] < 0 and worst["n"] >= 3:
        out.append(("单票反复亏损", f"{worst['name']} 交易 {worst['n']} 次累计 "
                                    f"{worst['pnl']:+.0f} 元", "warn"))
    return out


def _findings(c, per_stock):
    """逐条发现：结论 + 数据依据 + 这个指标意味着什么。
    每条都是 (标题, 数值, 含义/影响)，渲染层直接用。"""
    f = []
    wr, pf = c.get("win_rate"), c.get("profit_factor")
    if wr is not None:
        f.append(("胜率", f"{wr:.0%}（{c['n_win']}/{c['n_closed']} 笔盈利）",
                  "胜率高只说明「做对的次数多」，不等于赚钱。"
                  "它必须和盈亏比一起看：胜率 70% 但亏损单亏得比盈利单多，账户照样缩水。"))
    if pf is not None:
        verdict = ("每亏 1 元能赚回 %.2f 元，长期可持续" % pf) if pf >= 1.5 else (
            "每亏 1 元只赚回 %.2f 元，容错空间很小" % pf if pf >= 1
            else "每亏 1 元只赚回 %.2f 元，这个结构长期必然亏损" % pf)
        f.append(("盈亏比（Profit Factor）", f"{pf:.2f}",
                  f"总盈利 ÷ 总亏损。{verdict}。"
                  f"比胜率更能决定最终结果，2.0 以上算健康。"))
    hw, hl = c.get("hold_win"), c.get("hold_loss")
    if hw and hl:
        ratio = hl / hw if hw else None
        if ratio and ratio > 1.5:
            f.append(("持仓时长反差", f"盈利单平均 {hw:.1f} 天，亏损单平均 {hl:.1f} 天"
                                      f"（{ratio:.1f} 倍）",
                      "这是「截断利润、让亏损奔跑」的典型信号，行为金融学里叫处置效应："
                      "赚一点就急着卖、亏了却不断等反弹。"
                      "它会系统性压低盈亏比——因为盈利被提前锁死，亏损却有充分时间扩大。"))
        else:
            f.append(("持仓时长", f"盈利单 {hw:.1f} 天，亏损单 {hl:.1f} 天",
                      "两者接近，说明卖出决策没有被盈亏情绪明显绑架，这是好信号。"))
    aw, al = c.get("avg_win_pct"), c.get("avg_loss_pct")
    if aw is not None and al is not None:
        f.append(("单笔盈亏幅度", f"平均盈利 {aw:+.2f}%，平均亏损 {al:+.2f}%",
                  "理想状态是盈利幅度大于亏损幅度。若相反，"
                  "意味着止盈太早、止损太晚或根本没有止损线。"))
    h = c.get("hold_avg")
    tpd = c.get("trades_per_active_day")
    if h is not None:
        f.append(("交易周期", f"平均持有 {h:.1f} 天，中位数 {c['hold_median']:.0f} 天"
                              + (f"，活跃日均 {tpd:.1f} 笔" if tpd else ""),
                  "持有期越短，收益越依赖择时精度，手续费与冲击成本占比也越高；"
                  "同时短周期里个股涨跌更接近随机，可提取的信息更少。"))
    fr, ratio = c.get("fee_ratio"), c.get("fee_vs_pnl")
    if fr is not None:
        extra = ""
        if ratio is not None:
            extra = f"，相当于已实现盈亏的 {ratio:.0%}"
        f.append(("交易成本", f"累计手续费 {c['fee_total']:,.2f} 元，"
                              f"占成交额 {fr:.3%}{extra}",
                  "手续费是确定性支出，和行情无关。"
                  "换手越频繁，这块对净收益的侵蚀越大，它不会随市场好转而消失。"))
    ur = c.get("unrealized_pnl")
    rp = c.get("realized_pnl")
    if ur is not None and rp is not None:
        if rp > 0 and ur < 0:
            f.append(("已实现 vs 浮动", f"已实现 {rp:+,.0f} 元，当前浮动 {ur:+,.0f} 元",
                      "已实现为正但持仓浮亏，是「把赚钱的卖了、亏钱的留着」的直接证据。"
                      "账户真实损益要看两者之和，不能只看卖出记录带来的成就感。"))
        else:
            f.append(("已实现 vs 浮动", f"已实现 {rp:+,.0f} 元，当前浮动 {ur:+,.0f} 元",
                      "两者方向一致，说明卖出决策与持仓质量没有明显背离。"))
    return f
