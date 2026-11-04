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
