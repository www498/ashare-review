# -*- coding: utf-8 -*-
"""个股单日涨跌解释：把「今天这一下为什么」落到可核对的事实上。

和 mover 的分工
--------------
mover 回答「最近五天为什么涨跌」，是趋势视角。
这里回答「今天为什么」，直接对应你今天的那笔操作。

三条线索
--------
1. **分解**：今日涨跌 = 大盘 + 板块超额 + 个股超额。用全市场涨跌幅中位数
   当大盘基准，比上证指数更贴近个股实际处境。三项可直接相加。
2. **量价**：量比、换手、振幅、收盘在日内区间的位置、跳空幅度。
   这些能把「涨了」拆成「主动买盘推上去」和「缩量没人卖所以涨」，
   后者往往第二天就还回去。
3. **矛盾**：板块普涨它独跌、高开低走、消息偏正面却下跌、利空反而上涨。
   反常才是信息量最大的部分——正常跟涨跟跌不需要解释。

不预测涨跌，也不编原因。算不出来的就明说「大盘和板块都解释不了」，
并指出该去查什么（公告、龙虎榜、大宗交易），而不是给一个听起来合理的猜测。
"""
# 消息面情绪词。只用于判断「消息方向与股价方向是否背离」，
# 不做情感强度打分——标题里抽不出强度，硬打分会显得精确但不可靠。
POS_WORDS = ("中标", "涨价", "提价", "增持", "回购", "超预期", "创新高", "获批",
             "签订", "订单", "扭亏", "预增", "利好", "突破", "上调", "增长",
             "扩产", "投产", "合作", "补贴", "鸽派", "降息", "降准", "宽松",
             "提振", "刺激", "回暖")
NEG_WORDS = ("立案", "减持", "亏损", "下调", "终止", "诉讼", "停产", "预亏",
             "退市", "处罚", "警示", "问询", "下滑", "暴跌", "违约", "爆仓",
             "商誉", "计提", "质押", "鹰派", "加息", "收紧", "缩表", "关税",
             "制裁", "衰退")


def _tone(news):
    """新闻整体方向：正=偏利好，负=偏利空，0=中性或没有消息。"""
    if not news:
        return 0, None
    best_s, best_t = 0, None
    for n in news:
        t = n.get("title") or ""
        s = (sum(1 for w in POS_WORDS if w in t)
             - sum(1 for w in NEG_WORDS if w in t))
        if abs(s) > abs(best_s):
            best_s, best_t = s, t
    return best_s, best_t


def _vol(pct, vr, to, amp):
    """量价形态。同一根阳线，放量和缩量的含义完全相反。"""
    vr = vr or 0.0
    to = to or 0.0
    if vr >= 1.8:
        if pct >= 2:
            return ("放量上涨", "good",
                    f"量比 {vr:.1f}、换手 {to:.1f}%，是主动买盘推上去的")
        if pct <= -2:
            return ("放量下跌", "bad",
                    f"量比 {vr:.1f}、换手 {to:.1f}%，卖压是主动的，不是没人接")
        if abs(pct) < 1:
            return ("放量滞涨", "warn",
                    f"量比 {vr:.1f} 但只 {pct:+.1f}%，这么大的量没换来价格，有人在借量出货")
        return ("放量整理", "mid", f"量比 {vr:.1f}、换手 {to:.1f}%，多空分歧加大")
    if vr >= 1.3:
        if pct >= 1:
            return ("温和放量上涨", "good", f"量比 {vr:.1f}，买盘比平时积极")
        if pct <= -1:
            return ("温和放量下跌", "warn", f"量比 {vr:.1f}，卖压略高于平常")
        return ("温和放量", "mid", f"量比 {vr:.1f}，多空都有动作但没分出方向")
    if vr <= 0.6:
        if pct >= 1:
            return ("明显缩量上涨", "mid",
                    f"量比只有 {vr:.1f}，抛压很轻，少量买盘就能推高，但承接不厚")
        if pct <= -1:
            return ("明显缩量下跌", "mid",
                    f"量比 {vr:.1f}，卖压不重，更像无人接盘而不是集中抛售")
        return ("明显缩量", "mid", f"量比 {vr:.1f}，多空都没发力")
    if vr <= 0.85:
        return ("小幅缩量", "mid", f"量比 {vr:.1f}，参与度低于平常")
    if to >= 5:
        return ("换手活跃", "mid", f"换手 {to:.1f}%、量比 {vr:.1f}%，筹码交换充分")
    return ("量能持平", "mid", f"量比 {vr:.1f}、换手 {to:.1f}%，与近几日基本相当")


def day_reason(a, ctx, news=None, sector=None):
    """返回单日归因结构，数据不足时返回 None。

    a     : 自选股行情 + attr（行业归因），来自 analyze.anomalies
    news  : 该股挂到的快讯列表，可为空
    sector: analyze.sector_flow() 的结果，用于补板块资金流
    """
    pct = a.get("pct")
    if pct is None:
        return None

    b = ctx.get("breadth") or {}
    mkt = b.get("median_pct")
    mkt = 0.0 if mkt is None else float(mkt)
    at = a.get("attr") or {}
    ind_med = at.get("ind_median")
    ind_up = at.get("ind_up_ratio")

    # ---- 1) 三段分解 ----
    if ind_med is None:
        parts = [("大盘", mkt), ("个股超额", pct - mkt)]
        ind_part, firm = 0.0, pct - mkt
    else:
        ind_med = float(ind_med)
        parts = [("大盘", mkt), ("板块超额", ind_med - mkt), ("个股超额", pct - ind_med)]
        ind_part, firm = ind_med - mkt, pct - ind_med

    # ---- 2) 量价形态 ----
    vol_tag, vol_tone, vol_text = _vol(pct, a.get("vol_ratio"),
                                       a.get("turnover"), a.get("amp"))

    # 涨跌停是最强的价格信号，提前算好，结论和标记都要用
    limit_up, limit_down = a.get("limit_up"), a.get("limit_down")
    px_now = a.get("price")
    is_up_limit = bool(limit_up and px_now and px_now >= limit_up - 0.011)
    is_dn_limit = bool(limit_down and px_now and px_now <= limit_down + 0.011)

    # 封板时量价要单独说：涨停日量比 1.2 和普通日量比 1.2 完全不是一回事
    vr0 = a.get("vol_ratio") or 0
    if is_up_limit:
        if vr0 >= 2.0:
            vol_tag, vol_tone = "放量封板", "good"
            vol_text = f"量比 {vr0:.1f}，是带着量封上去的，封板前换手充分"
        elif vr0 >= 1.2:
            vol_tag, vol_tone = "放量涨停", "good"
            vol_text = f"量比 {vr0:.1f}，成交量比平时大，属于有资金参与的涨停"
        else:
            vol_tag, vol_tone = "缩量封板", "good"
            vol_text = (f"量比只有 {vr0:.1f}，卖盘不多、封得轻松。"
                        f"这种涨停要看次日承接：没人卖也可能没人接")
    elif is_dn_limit:
        vol_tag, vol_tone = "跌停", "bad"
        vol_text = f"量比 {vr0:.1f}，卖单堆在跌停价上，没有对手盘"

    # ---- 3) 收盘位置：判断尾盘是承接还是砸盘 ----
    pos = None
    hi, lo, px, amp = a.get("high"), a.get("low"), a.get("price"), a.get("amp") or 0
    if hi and lo and px and hi > lo and amp >= 2 and not (is_up_limit or is_dn_limit):
        r = (px - lo) / (hi - lo)
        if r >= 0.75:
            pos = ("收在日内高位", "尾盘买盘占优，当天的涨是被认下来的")
        elif r <= 0.25:
            pos = ("收在日内低位", "尾盘被砸下来，抛压延续到了收盘")
        else:
            pos = ("收在日内中段", "多空当天没分出胜负")

    # ---- 4) 跳空：高开低走是最典型的「借消息出货」形态 ----
    gap = None
    op, pc = a.get("open"), a.get("prev_close")
    if op and pc:
        gap = (op / pc - 1) * 100

    # ---- 5) 矛盾与反常：这部分才是真正有信息量的 ----
    flags = []

    # 涨跌停要单独认：它是最强的价格信号，不该被当成「解释不了」的异动
    if is_up_limit:
        flags.append(("封涨停", "good",
                      f"收盘价 {px_now:,.2f} 就是涨停价，封在板上。"
                      f"其中 {ind_part:+.1f}pp 是板块顺势推力，{firm:+.1f}pp 来自个股自身。"
                      f"涨停后要看的是次日能不能承接住开盘的抛压。"))
    elif is_dn_limit:
        flags.append(("封跌停", "warn",
                      f"收盘价 {px_now:,.2f} 是跌停价，卖单没有对手盘。"
                      f"这种位置不要猜底，先弄清是什么消息导致的。"))

    vr_now = a.get("vol_ratio") or 0
    if ind_med is not None and ind_part >= 1.0 and firm <= -1.5 and not is_up_limit:
        tail = f"，板块内上涨家数占 {ind_up:.0%}" if ind_up is not None else ""
        if pct < 0:
            flags.append(("板块普涨它独跌", "warn",
                          f"所属行业今天中位数 {ind_med:+.1f}%{tail}，它却 {pct:+.1f}%，"
                          f"个股超额 {firm:+.1f}pp。板块解释不了，问题在它自己身上。"))
        elif vr_now >= 1.8:
            # 放量却跑输板块，是最典型的「借板块强势出货」形态
            flags.append(("放量跑输板块", "warn",
                          f"所属行业 {ind_med:+.1f}%{tail}，它只 {pct:+.1f}%，"
                          f"偏偏量比还有 {vr_now:.1f}。板块给的顺风没接住、量却放大了，"
                          f"通常是有资金在借着板块热度往外卖。"))
        else:
            flags.append(("跑输板块", "mid",
                          f"所属行业 {ind_med:+.1f}%{tail}，它 {pct:+.1f}%，"
                          f"跑输 {abs(firm):.1f}pp。跟涨但弹性不足，说明买盘不如板块里其他票强。"))
    elif ind_med is not None and ind_part <= -1.0 and firm >= 1.5:
        flags.append(("板块普跌它独涨", "good",
                      f"所属行业今天中位数 {ind_med:+.1f}%，它逆势 {pct:+.1f}%，"
                      f"个股超额 {firm:+.1f}pp。有独立于板块的资金在买。"))

    if gap is not None and gap >= 1.0 and pct <= -1.0:
        flags.append(("高开低走", "warn",
                      f"高开 {gap:+.1f}% 之后一路走弱，收在 {pct:+.1f}%。"
                      f"这种形态通常是有人借着开盘的情绪往外卖，消息面的利好可能已经被提前消化。"))
    elif gap is not None and gap <= -1.0 and pct >= 1.0:
        flags.append(("低开高走", "good",
                      f"低开 {gap:+.1f}% 后翻上来收 {pct:+.1f}%，盘中有资金在承接。"))

    # 只用「点名这只票」的消息判断背离。
    # 行业级新闻说的是同行（比如江淮汽车挂到「沃尔沃销量下滑」），
    # 拿它来判断「利好不涨」会把同行的事算到这只票头上。
    own_news = [n for n in (news or []) if n.get("level") == "个股"]
    tone, hit = _tone(own_news)
    if tone > 0 and pct <= -1.5:
        flags.append(("利好不涨", "warn",
                      f"相关消息偏正面（「{hit[:28]}」），股价却跌 {pct:+.1f}%。"
                      f"要么利好已经提前反映，要么抛压比消息更强——这种背离比单纯下跌更值得警惕。"))
    elif tone < 0 and pct >= 1.5:
        flags.append(("利空不跌", "good",
                      f"相关消息偏负面（「{hit[:28]}」），股价反涨 {pct:+.1f}%。"
                      f"坏消息砸不下去，说明筹码已经被消化得差不多。"))

    if (abs(pct) >= 5 and abs(firm) >= 4.0 and not flags
            and not is_up_limit and not is_dn_limit):
        flags.append(("个股级异动", "info",
                      f"{pct:+.1f}% 的波动，大盘和板块都解释不了（个股超额 {firm:+.1f}pp）。"
                      f"这种幅度通常来自公司层面：查公告、龙虎榜、大宗交易或股东增减持。"))
    elif abs(pct) >= 5 and ind_part <= -2.0 and not flags:
        flags.append(("跟随板块杀跌", "warn",
                      f"跌幅里有 {ind_part:+.1f}pp 来自板块整体，属于行业性下跌，"
                      f"先看这个板块今天出了什么事，别急着判断个股。"))

    # ---- 6) 板块资金流（有就补一句，没有不提） ----
    flow = None
    ind_name = at.get("industry") or ""
    if sector and ind_name:
        for bucket in ("top", "bottom"):
            for row in (sector.get(bucket) or []):
                try:
                    nm, net = row[0], float(row[2])
                except Exception:
                    continue
                if nm and (nm in ind_name or ind_name in nm):
                    direction = "净流入" if net >= 0 else "净流出"
                    flow = f"{nm} 板块主力{direction} {abs(net) / 1e8:.1f} 亿"
                    break
            if flow:
                break

    # ---- 7) 一句话结论：按贡献最大的那一项定性 ----
    if abs(firm) >= 2.0 and abs(firm) > abs(ind_part):
        lead = "个股自身"
        lead_txt = f"个股超额 {firm:+.1f}pp，不是板块带的"
    elif abs(ind_part) >= 1.0:
        lead = "板块"
        lead_txt = f"板块贡献 {ind_part:+.1f}pp"
    else:
        lead = "大盘"
        lead_txt = f"跟大盘走（{mkt:+.1f}%）"

    if is_up_limit:
        verdict = (f"涨停封板（{px_now:,.2f}）。其中板块 {ind_part:+.1f}pp、"
                   f"个股自身 {firm:+.1f}pp。")
    elif is_dn_limit:
        verdict = (f"跌停（{px_now:,.2f}），卖单没有对手盘。"
                   f"板块 {ind_part:+.1f}pp、个股自身 {firm:+.1f}pp。")
    else:
        head = "涨" if pct >= 0 else "跌"
        verdict = f"今天{head} {abs(pct):.1f}%，主要来自{lead}（{lead_txt}）。{vol_tag}。"

    # 「跟大盘走」时，大盘为什么动也得有个交代，否则等于没解释。
    # 两个约束：
    # 1) 只引用方向一致的宏观消息。欧洲央行转鹰对 A 股是利空，
    #    拿它来解释「今天涨 2.8%」是自打嘴巴。
    # 2) 国内政策优先于海外。海外央行的措辞对 A 股是二阶影响。
    macro = (ctx.get("news") or {}).get("macro") or []
    macro_hit = None
    if lead == "大盘" and macro:
        cn = ("中国", "央行", "证监会", "财政部", "国常会", "政治局",
              "国务院", "发改委", "工信部", "统计局")
        ranked = sorted(macro, key=lambda t: 0 if any(k in t for k in cn) else 1)
        for t in ranked[:4]:
            mt = _tone([{"title": t}])[0]
            same = (mt == 0) or (mt > 0 and pct >= 0) or (mt < 0 and pct <= 0)
            if same:
                macro_hit = t
                break
        if macro_hit:
            verdict += f" 大盘层面的背景：「{macro_hit[:30]}」。"
        else:
            # 找不到能对上的消息就直说，不要硬套一条方向相反的新闻
            verdict += " 大盘层面没有找到能对上的公开消息，属于普涨。"

    # 板块层面的消息：回答「这个板块今天为什么动」。
    # 用户问的是「有色金属为什么强」，个股相对板块的分解回答不了这一层。
    ind_news = [n.get("title") for n in (news or [])
                if n.get("level") == "行业" and n.get("title")]

    return {
        "pct": pct, "parts": parts, "total": pct,
        "ind_news": ind_news[:2],
        "market": mkt, "industry_part": ind_part, "firm": firm,
        "vol": {"tag": vol_tag, "tone": vol_tone, "text": vol_text},
        "pos": pos, "gap": gap, "flow": flow,
        "flags": flags, "verdict": verdict, "lead": lead, "macro": macro_hit,
    }
