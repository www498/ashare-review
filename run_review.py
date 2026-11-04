# -*- coding: utf-8 -*-
"""
双时段复盘：午盘（11:30 后）与收盘（15:00 后）
用法：
    python run_review.py --session am      # 午盘总结
    python run_review.py --session pm      # 收盘总结
    python run_review.py --session pm --offline   # 用最近一次快照重放（演示兜底）
    python run_review.py --session pm --force     # 强制刷新成分表
"""
import argparse, datetime as dt, json, os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ashare import (data, analyze, report, history, ladder, industry,
                    detail as detail_mod, watchlist as watchlist_mod, config as C)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def step(msg):
    """上报当前阶段。

    网页端靠它显示「正在做什么」，否则三分钟的等待里只有一个转圈，
    用户无法判断是在算还是已经卡死。前缀 [STEP] 是给 importer 解析用的，
    不要改格式。flush 必须加：stdout 接管道时默认块缓冲，不加等于没输出。
    """
    print(f"[STEP] {msg}", flush=True)


def _fmt_ts(ts):
    """腾讯时间戳 20261102141907 -> 14:19"""
    try:
        s = str(ts)
        return f"{s[8:10]}:{s[10:12]}"
    except Exception:
        return "--:--"


def mode_warning(session, quote_ts):
    """时段与行情时点不一致时给出明确提示，避免拿盘中数据当收盘总结。"""
    hh, mm = (int(x) for x in quote_ts.split(":"))
    cur = hh * 60 + mm
    if session == "am" and cur > 11 * 60 + 35:
        return f"当前行情时点为 {quote_ts}，不是 11:30 的午盘快照。午盘总结请在 11:30-13:00 之间运行。"
    if session == "pm" and cur < 15 * 60:
        return f"当前行情时点为 {quote_ts}，尚未收盘，以下为盘中数据，不是最终收盘快照。"
    return None


def prev_trading_volume(sym="sh000001"):
    """昨日成交量（手），用于量能对比。走新浪，避开腾讯的反爬拦截。
    注意：新浪指数成交量单位是「股」，腾讯实时是「手」，需 /100 统一。"""
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol=sym)
        today = dt.date.today().strftime("%Y-%m-%d")
        prev = df[df["date"].astype(str) != today]
        return float(prev["volume"].iloc[-1]) / 100.0 if len(prev) else None
    except Exception:
        return None


def build(session, force=False):
    t0 = time.time()
    step("拉取全市场成分与行情")
    uni = data.universe(force=force)
    if not uni:
        raise SystemExit(f"{C.MARKET_NAME} 成分表获取失败，检查网络后重试")

    # 指数（独立拉，避免与个股代码冲突）
    idx_syms = [s for s, _ in C.INDICES]
    idx_rows = {r["code"]: r for r in data.fetch_symbols(idx_syms)}

    # 全量成分
    qmap = data.fetch_quotes(uni)
    if len(qmap) < len(uni) * 0.8:
        print(f"[警告] 仅取到 {len(qmap)}/{len(uni)} 只，部分停牌或请求失败")

    step("计算宽度、情绪与分布")
    b = analyze.breadth(qmap)
    if not b:
        raise SystemExit("宽度统计为空，数据源异常")
    strength = analyze.intraday_strength(qmap)
    broken = analyze.broken_boards(qmap)
    dist = analyze.distribution(qmap)

    idx = idx_rows.get("000001") or idx_rows.get("sh000001")
    if not idx:
        raise SystemExit("上证指数行情缺失")

    pv = prev_trading_volume()
    qt = _fmt_ts(idx.get("ts", ""))
    vr = analyze.volume_ratio(qt, idx["vol"], pv)
    temp = analyze.temperature(b, idx["pct"], vr)

    # 自选股：优先读 watchlist.txt / .csv，没有就回退 config.WATCHLIST
    watch, positions, wmeta = watchlist_mod.load(verbose=True)
    watch = watchlist_mod.fill_names(watch, qmap)
    port = watchlist_mod.portfolio(positions, qmap, watch) if positions else None
    anom = analyze.anomalies(qmap, watch)
    sec = analyze.sector_flow()

    # 行业映射 + 异动归因（首次会拉 baostock 行业表，约 50s，之后缓存 30 天）
    ind_stats = []
    try:
        step("行业归因（首次约 50 秒，之后读缓存）")
        ind_map = industry.fetch()
        ind_stats = industry.industry_stats(qmap, ind_map)
        anom = industry.attribute_watchlist(anom, ind_map, ind_stats)
    except Exception as e:
        print(f"[警告] 行业归因失败：{e}")

    try:
        lad = ladder.build(qmap)
    except Exception as e:
        print(f"[警告] 连板梯队计算失败：{e}")
        lad = None

    # 个股详情：分时 + 近20日 + 昨日涨跌幅，供网页点开查看
    try:
        step("抓取自选股分时与近 20 日")
        det = detail_mod.watch_detail(list(watch.keys()), qmap, watch)
    except Exception as e:
        print(f"[警告] 个股详情抓取失败：{e}")
        det = {}

    ctx = {
        "date": dt.date.today().strftime("%Y-%m-%d"),
        "session": session,
        "run_at": now_str(),
        "latency": f"{time.time() - t0:.1f}s",
        "quote_ts": qt,
        "breadth": b,
        "temperature": temp,
        "vratio": vr,
        "anomalies": anom,
        "sector": sec,
        "ladder": lad,
        "industry": ind_stats,
        "strength": strength,
        "broken": broken,
        "dist": dist,
        "detail": det,
        "watchlist": watch,
        "watch_quotes": {c: qmap[c] for c in watch if c in qmap},
        "watch_meta": wmeta,
        "positions": positions,
        "portfolio": port,
        "indices": [(name, idx_rows.get(sym[2:]) or idx_rows.get(sym)) for sym, name in C.INDICES],
        "prev_vol": pv,
        "n_universe": len(uni),
    }
    ctx["indices"] = [(n, q) for n, q in ctx["indices"] if q]
    ctx["conclusion"] = analyze.conclusion(session, b, temp, idx, vr, anom)
    # 连板结论只在收盘报告里出现：半日数据算连板不准，午盘不呈现
    if lad and session == "pm":
        ctx["conclusion"] = ctx["conclusion"][:-1] + ladder.summarize(lad) + ctx["conclusion"][-1:]
    ctx["warning"] = mode_warning(session, ctx["quote_ts"])
    return ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["am", "pm"], required=True)
    ap.add_argument("--offline", action="store_true", help="用最近快照重放，不请求网络")
    ap.add_argument("--force", action="store_true", help="强制刷新成分表")
    ap.add_argument("--forecast", action="store_true", help="附加波动率预测与价格区间（较慢）")
    ap.add_argument("--llm", action="store_true",
                    help="附加 AI 解读（配置 key 后默认启用，此参数保留兼容）")
    ap.add_argument("--no-llm", action="store_true", help="关闭 AI 解读，只用规则文案")
    ap.add_argument("--user", default=None,
                    help="账号 uid。多用户模式下读写 users/<uid>/ 下的数据；"
                         "不传则使用项目根目录（单用户兼容）")
    args = ap.parse_args()

    # 必须在任何数据读写之前设定账号，否则会落到错误的目录
    from ashare import context
    context.set_user(args.user)

    snap_name = dt.date.today().strftime("%Y%m%d") + "_" + args.session
    replayed = False

    if args.offline:
        ctx = data.load_snapshot(snap_name)
        if ctx:
            print(f"[离线模式] 重放快照 {snap_name}")
        else:
            # 断网演示的关键兜底：今天没有快照时回退到最近一份可用的。
            # 绑死 today() 会让 --offline 恰好在最需要它的时候失败。
            alt = data.latest_snapshot(args.session)
            if not alt:
                have = data.list_snapshots()
                hint = ("，现有快照：" + "、".join(have[:6])) if have else ""
                raise SystemExit(
                    f"没有找到任何 {args.session} 时段的快照{hint}。先联网跑一次 "
                    f"python run_review.py --session {args.session}")
            ctx = data.load_snapshot(alt)
            snap_name = alt          # 报告文件名跟随快照日期，不要写成今天
            print(f"[离线模式] 今天（{dt.date.today():%Y-%m-%d}）没有 {args.session} 快照，"
                  f"回退重放最近一份：{alt}（{ctx.get('date', '?')} "
                  f"{'午盘' if args.session == 'am' else '收盘'}）")
            replayed = True
    else:
        ctx = build(args.session, force=args.force)

    # 重放的是历史快照，必须在报告里标明，否则旧数据会被当成今天的盘面
    if replayed:
        note = (f"本页为 {ctx.get('date', '?')} "
                f"{'午盘' if args.session == 'am' else '收盘'}快照的离线重放"
                f"（当前日期 {dt.date.today():%Y-%m-%d}），非实时数据。")
        ctx["warning"] = f"{note} {ctx['warning']}" if ctx.get("warning") else note
        ctx["replayed"] = True

    # 重放时重算规则化文字：快照里存的是生成当天的措辞，
    # 口径或表述修好之后，旧快照不该继续带着旧结论。数字仍全部来自快照。
    if args.offline and ctx.get("breadth") and ctx.get("indices"):
        try:
            idx_q = ctx["indices"][0][1]
            ctx["conclusion"] = analyze.conclusion(
                ctx["session"], ctx["breadth"], ctx["temperature"],
                idx_q, ctx.get("vratio"), ctx.get("anomalies") or [])
            if ctx["session"] == "pm" and ctx.get("ladder"):
                ctx["conclusion"] = (ctx["conclusion"][:-1]
                                     + ladder.summarize(ctx["ladder"])
                                     + ctx["conclusion"][-1:])
        except Exception as e:
            print(f"[警告] 结论重算失败，沿用快照内文本：{e}")

    # 旧快照里没有 cards（诊断曾在保存之后才算），重放时按快照数据补算，
    # 这样历史看板也有诊断块。
    if args.offline and not ctx.get("cards"):
        try:
            from ashare import stockcard
            attrs = {a["code"]: a["attr"] for a in ctx.get("anomalies", []) if a.get("attr")}
            fcm = {r["sym"][2:]: r for r in (ctx.get("forecast") or [])}
            # 更早的快照连 watch_quotes 都没有（字段是后来加的），
            # 这时用 anomalies 兜底 —— 它本身就是带完整行情的自选股列表。
            wq = ctx.get("watch_quotes") or {}
            if not wq:
                wq = {a["code"]: a for a in ctx.get("anomalies", []) if a.get("price")}
                if wq:
                    ctx["watch_quotes"] = wq
            ctx["cards"] = stockcard.build_all(
                ctx.get("watchlist") or {}, wq,
                attrs=attrs, forecasts=fcm, portfolio=ctx.get("portfolio"))
            if ctx["cards"]:
                print(f"[离线模式] 已补算 {len(ctx['cards'])} 只个股诊断")
            else:
                print("[离线模式] 诊断补算为空（快照缺少自选股行情或日K缓存不足）")
        except Exception as e:
            print(f"[警告] 诊断补算失败：{e}")

    # 收盘时段把当日结果并入历史表；午盘或未收盘时不写，避免盘中数据污染趋势
    if not args.offline and args.session == "pm" and not ctx.get("warning"):
        try:
            history.upsert_today(ctx)
        except Exception as e:
            print(f"[警告] 历史表写入失败：{e}")

    ctx["trend"] = history.trend()

    # 市场概况：九档分布 + 每项指标的含义，对标行情软件首页但解释更完整
    try:
        import pandas as _pd
        prev_amt = ma60 = None
        if os.path.exists(history.HIST_CSV):
            _h = _pd.read_csv(history.HIST_CSV, encoding="utf-8-sig").sort_values("date")
            _h = _h[_h["date"] != ctx["date"]]
            if len(_h):
                prev_amt = float(_h["amount_yi"].iloc[-1])
                ma60 = float(_h["amount_yi"].tail(60).mean())
        ctx["overview"] = analyze.market_overview(
            ctx["breadth"], ctx.get("dist"), ctx.get("vratio"),
            prev_amount=prev_amt, amount_ma60=ma60)
    except Exception as e:
        print(f"[警告] 市场概况生成失败：{e}")

    # 交易行为画像：从交割单还原「这个人怎么做交易」。
    # 这是本产品的差异点 —— 行情软件只分析市场，不分析用户自己。
    try:
        from ashare import profile as prof, statement as stmt
        step("分析交割单与交易画像")
        src = stmt.find_statement()
        if src is not None:
            _d, _col = stmt.prepare(src)
            ctx["profile"] = prof.build(
                _d, _col,
                positions=ctx.get("positions"),
                quotes=ctx.get("watch_quotes"))
            if ctx.get("profile"):
                print(f"[画像] 已分析 {ctx['profile']['core']['trades_total']} 笔历史交易")

            # 当日逐笔复盘：这一手该不该买/卖，为什么
            try:
                from ashare import journal
                jr = journal.build(_d, _col,
                                   trades=(ctx.get("profile") or {}).get("trades"))
                if jr:
                    ctx["journal"] = jr
                    try:
                        sr = journal.review_sells(
                            _d, _col, trades=(ctx.get("profile") or {}).get("trades"),
                            days=25, limit=8)
                        if sr:
                            ctx["sell_review"] = sr
                            _n = sum(1 for x in sr if x["verdict"] == "卖飞")
                            print(f"[卖出回看] {len(sr)} 笔，其中 {_n} 笔卖飞")
                    except Exception as _e:
                        print(f"[提示] 卖出回看失败：{_e}")
                    print(f"[交易复盘] {jr['day']} 共 {jr['summary']['n']} 手"
                          f"（买 {jr['summary']['buys']} / 卖 {jr['summary']['sells']}）")
            except Exception as e:
                print(f"[警告] 当日交易复盘失败：{e}")
    except Exception as e:
        print(f"[警告] 交易画像生成失败：{e}")

    # 日环比：与上一交易日对比
    try:
        ctx["delta"] = detail_mod.build_delta(ctx)
    except Exception as e:
        print(f"[警告] 日环比计算失败：{e}")

    # 时段视图：午盘产「下午怎么盯」，收盘产「明天怎么做」，两者用不同数据组合
    try:
        idx_q = ctx["indices"][0][1]
        if args.session == "am":
            ctx["session_view"] = analyze.am_watch(
                ctx["breadth"], ctx.get("strength"), ctx.get("broken"),
                ctx["vratio"], idx_q, ctx["temperature"])
        else:
            ctx["session_view"] = analyze.pm_prep(
                ctx["breadth"], ctx.get("strength"), ctx.get("broken"),
                ctx["vratio"], idx_q, ctx["temperature"],
                ctx["anomalies"], ctx.get("ladder"), ctx.get("trend"))
    except Exception as e:
        print(f"[警告] 时段视图生成失败：{e}")

    if not args.no_llm:
        try:
            from ashare import attrib, llm
            if llm.available():
                step("AI 解读盘面（约 30-60 秒）")
                ctx["ai"] = attrib.explain(ctx)
            else:
                print("[提示] 未配置 LLM key，AI 解读留空。"
                      "把 key 写进根目录 llm_key.txt 或设置 LLM_API_KEY 即可自动启用。")
        except Exception as e:
            print(f"[警告] AI 解读失败：{e}")

    if args.forecast and not args.offline:
        try:
            from ashare import forecast as fc
            live_px = {a["code"]: a["price"] for a in ctx["anomalies"]}
            wl = ctx.get("watchlist") or C.WATCHLIST
            # 逐票上报 + 单只超时 + 总预算。
            # baostock 的日线查询没有超时参数，某只票网络不通时会一直挂着，
            # 整个复盘就停在这一步 —— 这正是「一直显示生成中」的来源。
            # 所以宁可少算几只，也不能让整份报告卡死。
            rows, total = [], len(wl)
            t_fc = time.time()
            budget = 150.0

            def _one(sym, nm, px, wait=28.0):
                """在 daemon 线程里跑，超时就放弃这只。

                不用 ThreadPoolExecutor：它的 atexit 钩子会 join 所有 worker，
                一旦某只票永久卡在 socket 上，整个进程退不出去。
                daemon 线程放弃后不影响进程结束。
                """
                box = [None]

                def _run():
                    try:
                        box[0] = fc.analyze_symbol(sym, nm, price=px)
                    except Exception:
                        pass

                th = threading.Thread(target=_run, daemon=True)
                th.start()
                th.join(wait)
                return box[0]

            for i, (c, n) in enumerate(wl.items(), 1):
                left = budget - (time.time() - t_fc)
                if left <= 5:
                    print(f"[提示] 波动率预测超出 {budget:.0f} 秒预算，"
                          f"跳过剩余 {total - i + 1} 只（不影响其他部分）")
                    break
                step(f"波动率预测 {i}/{total} {n}")
                try:
                    r = _one(data.sym(c), n, live_px.get(c))
                except Exception:
                    print(f"[提示] {n} 波动率预测超时，跳过")
                    r = None
                if r:
                    rows.append(r)
            ctx["forecast"] = rows
            if rows:
                step(f"波动率预测完成 {len(rows)}/{total}")
        except Exception as e:
            print(f"[警告] 波动率预测失败：{e}")

    # 个股诊断：位置 / 均线 / 量能 / 相对行业 / 波动率 / 持仓风险
    # 必须在保存快照之前算：否则离线重放拿不到 cards，看板的诊断块会整块消失。
    try:
        from ashare import stockcard
        step("生成个股诊断")
        attrs = {a["code"]: a["attr"] for a in ctx.get("anomalies", []) if a.get("attr")}
        fcm = {r["sym"][2:]: r for r in (ctx.get("forecast") or [])}
        ctx["cards"] = stockcard.build_all(
            ctx.get("watchlist") or {}, ctx.get("watch_quotes") or {},
            attrs=attrs, forecasts=fcm, portfolio=ctx.get("portfolio"))
    except Exception as e:
        print(f"[警告] 个股诊断失败：{e}")

    # 多日涨跌归因：把每只自选股近 5 日的涨跌拆成「大盘 / 板块 / 个股自身」。
    # 这是产品差异化的核心 —— 用户问的是「为什么涨/为什么跌」，单日涨跌幅回答不了。
    try:
        from ashare import mover
        step("拆解近 5 日涨跌归因")
        wl = ctx.get("watchlist") or {}
        wq = ctx.get("watch_quotes") or {}
        codes = [c for c in wl if wq.get(c)]
        if codes:
            try:
                ind_map = industry.fetch()
            except Exception as _e:
                print(f"[提示] 行业分类暂不可用，板块项留空：{_e}")
                ind_map = {}
            mv, fac = mover.build_many(codes, mapping=ind_map, n=5, names=wl)
            ctx["movers"] = mv
            if fac:
                print(f"[归因] 已拆解 {len(mv)} 只自选股近 5 日涨跌"
                      f"（日K截至 {fac.get('latest', '?')}，基准为全市场中位数）")

            # 交易人格代号要用到「板块解释力」与「集中度」，所以在归因之后算
            if ctx.get("profile"):
                try:
                    from ashare import profile as prof_mod
                    ctx["profile"]["mbti"] = prof_mod.mbti(
                        ctx["profile"].get("core") or {},
                        ctx["profile"].get("per_stock"),
                        movers=ctx.get("movers"),
                        positions=ctx.get("positions"),
                        quotes=ctx.get("watch_quotes"))
                    print(f"[人格] 代号 {ctx['profile']['mbti']['code']} "
                          f"（{ctx['profile']['mbti']['name']}）")
                except Exception as e:
                    print(f"[警告] 交易人格计算失败：{e}")
    except Exception as e:
        print(f"[警告] 多日归因失败：{e}")

    # 消息面：当天公开财经快讯，直接挂到每只自选股上，不单独成块。
    # 单独一块的新闻对用户没用——他看到的是「今天有 8 条消息」，
    # 想知道的是「紫金矿业今天为什么跌」，所以必须落到个股。
    try:
        from ashare import news as news_mod
        step("抓取财经快讯并匹配到个股")
        _items = news_mod.fetch()
        if _items:
            _targets = {}
            for a in ctx.get("anomalies") or []:
                at = a.get("attr") or {}
                _targets[a["code"]] = {"name": a.get("name") or "",
                                       "industry": at.get("industry") or ""}
            _per = news_mod.attach(_items, _targets)
            _n = 0
            for _code, _arr in _per.items():
                _card = (ctx.get("cards") or {}).get(_code)
                if _card:
                    _card["news"] = _arr
                    _n += 1
            # 宏观背景单独存一份：个股归因里「主要跟大盘走」时需要解释大盘为什么动，
            # 但这类消息对所有票都一样，所以不挂到每只票上，只按需引用。
            _macro = news_mod.macro_headlines(_items, n=5)
            ctx["news"] = {"total": len(_items), "stocks": _n,
                           "macro": _macro[:5]}
            print(f"[消息面] 当天快讯 {len(_items)} 条，命中 {_n} 只自选股，"
                  f"宏观背景 {len(_macro[:5])} 条")
    except Exception as e:
        print(f"[警告] 消息面抓取失败：{e}")

    # 个人点评：交给大模型把画像与归因写成自然语言。
    # 数字仍由代码算好注入，输出要过数字溯源校验，编造的数字会被打回重写。
    if not args.no_llm and not ctx.get("offline_ai_written"):
        try:
            from ashare import attrib, llm
            if llm.available():
                step("AI 分析画象与个股归因（约 30-60 秒）")
                pers = attrib.personal(ctx)
                if pers and pers.get("error"):
                    print(f"[警告] 个人点评生成失败：{pers['error']}")
                elif pers and pers.get("profile"):
                    if ctx.get("profile"):
                        ctx["profile"].setdefault("persona", {})["ai"] = pers["profile"]
                    hit = 0
                    for _code, _m in (ctx.get("movers") or {}).items():
                        note = (pers.get("stocks") or {}).get(_m.get("name") or "")
                        if note:
                            _m["ai"] = note
                            hit += 1
                    print(f"[个人点评] 已生成画像点评，{hit} 只自选股附带归因解读"
                          f"（数字校验{'通过' if pers.get('verified') else '未通过'}）")

                # 个股级后续关注：落到「紫金矿业未来几天看什么」，
                # 而不是一份对所有票都一样的宏观摘要。
                # 全局消息面摘要已经取消——它回答不了「跟我这只票什么关系」，
                # 还多花一次 30-60 秒的模型调用。
                step("AI 生成个股后续关注点")
                outs = attrib.stock_outlook(ctx)
                if outs:
                    _hit = 0
                    for _a in ctx.get("anomalies") or []:
                        _card = (ctx.get("cards") or {}).get(_a["code"])
                        _tx = outs.get(_a.get("name") or "")
                        if _card and _tx:
                            _card["outlook"] = _tx
                            _hit += 1
                    print(f"[个股关注] 已生成 {_hit} 只自选股的后续关注点")
        except Exception as e:
            print(f"[警告] 个人点评失败：{e}")

    # 快照在全部增强完成后保存，这样离线重放也带趋势、预测、时段视图和诊断
    step("保存快照与报告")
    if not args.offline:
        data.save_snapshot(snap_name, ctx)

    md = report.render(ctx)

    outdir = context.reports_dir()
    os.makedirs(outdir, exist_ok=True)
    fp = os.path.join(outdir, snap_name + ".md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(md)

    step("渲染看板")

    print("\n" + "=" * 66)
    print(md)
    print("=" * 66)
    print(f"\n报告已保存：{fp}")

    # 同步生成静态看板
    try:
        from ashare import web as web_mod
        hp = os.path.join(outdir, f"dashboard_{snap_name}.html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(web_mod.render_html(ctx))
        print(f"看板已生成：{hp}")
    except Exception as e:
        print(f"[警告] 看板生成失败：{e}")

    # 历史趋势页 + 首页
    try:
        from ashare import timeline as tl, site as st
        hist_html = tl.render()
        if hist_html:
            with open(os.path.join(outdir, "history.html"), "w", encoding="utf-8") as f:
                f.write(hist_html)
        st.main()
    except Exception as e:
        print(f"[警告] 首页生成失败：{e}")

    # 16 型人格图鉴（放在项目根，图片走相对路径，只生成一次内容不变）
    try:
        from ashare import gallery
        gp = gallery.write()
        print(f"人格图鉴：{gp}")
    except Exception as e:
        print(f"[警告] 图鉴生成失败：{e}")


if __name__ == "__main__":
    main()
