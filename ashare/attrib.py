# -*- coding: utf-8 -*-
"""
归因文字生成：把结构化事实交给 LLM，产出可读解读，并做数字溯源校验。

调用链：
    facts（代码算的） → prompt（只许引用 facts 里的数字） → LLM → 校验 → 通过才展示
校验不通过则带上违规清单重试一次；仍不通过就标记为「未通过校验」并原样展示，
让问题暴露出来，而不是悄悄放行。
"""
import json

from . import llm

SYSTEM = """你是一名 A 股复盘助手。你的任务是把给定的结构化数据翻译成简洁、有判断的中文解读。

严格规则：
1. 只能使用输入 JSON 中已给出的数字，绝对不要自己计算或推测任何新数字。
2. 不要给出买入、卖出、目标价之类的投资建议。
3. 不要使用"必然""一定""肯定"这类绝对化措辞。
4. 输出 4 条要点，每条 40 字以内，直接给判断，不要复述数据本身。
5. 只输出 JSON：{"points": ["...", "...", "...", "..."]}
"""


def build_facts(ctx):
    """把报告用到的关键数字整理成一份扁平的事实表"""
    b = ctx["breadth"]
    t = ctx["temperature"]
    idx = ctx["indices"][0][1] if ctx["indices"] else {}
    facts = {
        "日期": ctx["date"],
        "时段": "午盘" if ctx["session"] == "am" else "收盘",
        "市场温度": {"总分": t["total"], "档位": t["band"],
                     "上涨家数占比": round(b["up_ratio"] * 100, 1),
                     "个股涨幅中位数": round(b["median_pct"], 2),
                     "涨停数": b["limit_up"], "跌停数": b["limit_down"],
                     "量能比": round(ctx["vratio"] * 100, 1) if ctx.get("vratio") else None},
        "上证": {"涨跌幅": round(idx.get("pct", 0), 2)},
        "自选股": [{"名称": a["name"], "涨跌幅": round(a["pct"], 2),
                    "现价": round(a["price"], 2),
                    "振幅": round(a.get("amp") or 0, 2),
                    "行业": (a.get("attr") or {}).get("industry"),
                    "行业中位数": round((a.get("attr") or {}).get("ind_median", 0), 2),
                    "判断": (a.get("attr") or {}).get("verdict")}
                   for a in ctx.get("anomalies", [])],
    }
    lad = ctx.get("ladder")
    if lad:
        facts["连板"] = {"最高板": lad["max_board"],
                         "晋级": [{"板位": bd, "成功": v["ok"], "总数": v["total"]}
                                  for bd, v in lad["promotion"]],
                         "昨日涨停今日平均涨幅": round(lad["perf"]["avg"], 2) if lad["perf"]["avg"] is not None else None}

    # 下面这些原来没进 facts，导致模型引用「传媒净流入 55.49 亿」这类真实数字
    # 反而被 verify_numbers 判成幻觉。真话被标红比假话漏过更伤可信度。
    sec = ctx.get("sector")
    if sec:
        facts["板块资金流"] = {
            "流入": [{"板块": nm, "涨跌幅": round(p, 2), "净流入亿": round(a / 1e8, 2)}
                     for nm, p, a in sec.get("top", [])],
            "流出": [{"板块": nm, "涨跌幅": round(p, 2), "净流入亿": round(a / 1e8, 2)}
                     for nm, p, a in sec.get("bottom", [])],
        }

    tr = ctx.get("trend")
    if tr:
        facts["温度趋势"] = {k: (round(tr[k], 1) if isinstance(tr.get(k), (int, float)) else tr.get(k))
                             for k in ("cur", "ma5", "ma10", "ma20", "pctile", "chg5", "n")
                             if tr.get(k) is not None}

    fc = ctx.get("forecast")
    if fc:
        facts["波动区间"] = [{"名称": r["name"], "现价": round(r["price"], 2),
                             "预期5日波动": round(r["sigma_5d"] * 100, 2),
                             "区间下": round(r["lo"], 2), "区间上": round(r["hi"], 2),
                             "覆盖率": round(r["coverage"] * 100, 1),
                             "R2": round(r["r2"], 3)} for r in fc]

    br = ctx.get("breadth") or {}
    facts["宽度补充"] = {k: round(br[k], 2) for k in ("amount_yi", "median_amp", "p90", "p10")
                         if isinstance(br.get(k), (int, float))}
    facts["宽度补充"]["振幅超8%家数"] = br.get("amp_over8")
    facts["宽度补充"]["标的数"] = br.get("n")

    strg = ctx.get("strength") or {}
    if strg:
        facts["盘面强弱"] = {"收盘位置中位数": round(strg.get("median", 0), 2),
                             "贴近最高占比": round(strg.get("near_high_ratio", 0) * 100, 1),
                             "贴近最低占比": round(strg.get("near_low_ratio", 0) * 100, 1)}
    bk = ctx.get("broken") or {}
    if bk.get("rate") is not None:
        facts["炸板"] = {"炸板率": round(bk["rate"] * 100, 1),
                         "摸板数": bk.get("hit"), "炸板数": bk.get("broken")}

    pf = ctx.get("portfolio")
    if pf:
        facts["持仓"] = {k: round(pf[k], 2) for k in ("market_value", "pnl", "pnl_pct", "today_pnl")
                         if isinstance(pf.get(k), (int, float))}
    return facts


def explain(ctx, retries=1):
    if not llm.available():
        return None
    facts = build_facts(ctx)
    user = "以下是今日复盘的结构化数据，请按规则输出解读：\n" + json.dumps(facts, ensure_ascii=False, indent=1)

    txt, bad = None, []
    for attempt in range(retries + 1):
        try:
            raw = llm.chat([{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": user}], json_mode=True)
            txt = raw
            pts = json.loads(raw).get("points", [])
            txt = "\n".join(f"- {p}" for p in pts) if pts else raw
        except Exception as e:
            return {"text": f"（生成失败：{type(e).__name__}: {str(e)[:60]}）", "verified": False, "bad": []}

        bad = llm.verify_numbers(txt, facts)
        if not bad:
            return {"text": txt, "verified": True, "bad": []}
        user += (f"\n\n上一版输出包含这些无法溯源的数字：{bad}。"
                 f"请删掉它们或改用给定数据中的数字，重新输出。")

    return {"text": txt, "verified": False, "bad": bad}


SYSTEM_PERSONAL = """你是一个交易复盘教练，正在帮一个普通投资者看自己的交割单。

基于给定的统计数据，写两段中文点评。严格规则：
1. 只能用给定数据里出现的数字，不得自行计算、估算、换算或引用任何外部行情。
2. 不预测涨跌，不给买卖建议，不承诺收益，不用「必涨」「暴富」「血洗」这类词。
3. 具体优于华丽：说「亏损单平均拿 12 天，盈利单只拿 4 天」比说「你有处置效应」有用。
4. 语气像一个了解他的朋友，可以直接，但不刻薄。
5. 两段都控制在 60~110 字。

输出 JSON，不要 markdown 代码块：
{"profile": "对这个人的交易风格点评：先说做得好的地方，再说最该改的一件事",
 "stocks": {"股票名称": "这只票近期涨跌的最主要原因，一句话说清是跟大盘、跟板块，还是个股自身"}}
"""


def personal(ctx):
    """生成「个人点评 + 个股归因短评」。没有 key 或调用失败时返回 None。

    与市场解读分开调用的原因：这两块的数据来源是交割单与自选股，
    而市场解读用的是盘面指标，混在一个 prompt 里模型容易张冠李戴。
    """
    if not llm.available():
        return None
    p = ctx.get("profile") or {}
    c = p.get("core") or {}
    per = p.get("persona") or {}

    facts = {"画像": {
        "已完成交易笔数": c.get("n_closed"),
        "胜率": round((c.get("win_rate") or 0) * 100, 1),
        "盈亏比": round(c.get("profit_factor") or 0, 2),
        "已实现盈亏元": round(c.get("realized_pnl") or 0, 2),
        "盈利单平均持有天": round(c.get("hold_win") or 0, 1),
        "亏损单平均持有天": round(c.get("hold_loss") or 0, 1),
        "平均盈利元": round(c.get("avg_win") or 0, 2),
        "平均亏损元": round(c.get("avg_loss") or 0, 2),
        "累计手续费元": round(c.get("fee_total") or 0, 2),
    }}
    if per.get("title"):
        facts["风格判定"] = per["title"]

    mv = ctx.get("movers") or {}
    if mv:
        arr = []
        for code, m in mv.items():
            arr.append({
                "名称": m.get("name") or code,
                "行业": m.get("industry"),
                "近5日涨跌": round(m.get("total") or 0, 2),
                "大盘贡献pp": round(m.get("market") or 0, 2),
                "板块贡献pp": round(m.get("industry_part") or 0, 2),
                "个股自身pp": round(m.get("firm") or 0, 2),
                "主导因素": m.get("driver"),
                "最大波动日": (m.get("key_day") or {}).get("date"),
                "最大单日涨跌": round((m.get("key_day") or {}).get("pct") or 0, 2),
            })
        facts["自选股近5日归因"] = arr

    if len(facts) == 1 and not mv:
        return None

    user = ("以下是这个人的交易画像与自选股归因数据：\n"
            + json.dumps(facts, ensure_ascii=False, indent=1))

    txt, bad = None, []
    for _ in range(2):
        try:
            raw = llm.chat([{"role": "system", "content": SYSTEM_PERSONAL},
                            {"role": "user", "content": user}],
                           temperature=0.5, json_mode=True, timeout=90)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:80]}", "profile": None,
                    "stocks": {}}
        try:
            obj = json.loads(raw)
        except Exception:
            # 模型偶尔会带 ```json 包裹，剥一层再试
            cleaned = raw.strip().strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            try:
                obj = json.loads(cleaned)
            except Exception:
                return {"error": "输出不是合法 JSON", "profile": None, "stocks": {}}

        txt = json.dumps(obj, ensure_ascii=False)
        bad = llm.verify_numbers(txt, facts)
        if not bad:
            return {"profile": obj.get("profile"), "stocks": obj.get("stocks") or {},
                    "verified": True, "bad": []}
        user += (f"\n\n上一版包含这些在给定数据里找不到的数字：{bad}。"
                 f"请删掉或改用给定的数字后重新输出 JSON。")

    return {"profile": txt, "stocks": {}, "verified": False, "bad": bad}
