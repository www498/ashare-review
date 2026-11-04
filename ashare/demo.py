# -*- coding: utf-8 -*-
"""生成演示账号用的交割单。

为什么需要
----------
评委看不到几十笔历史成交，就看不出画像与逐笔复盘的价值。真实账号里
一天最多两三笔，展示不出「当天十几次交易」的细节。

做法
----
所有价格都来自本地日K的真实收盘价，只加千分之一量级的滑点；日期全是
真实交易日 —— 归因、位置分位、量比算出来和真实数据同一套口径。

交易风格是**刻意设计**的：选股偏准（胜率约 2/3），但盈利单拿得短、
亏损单拖得久 —— 这正是产品想帮人发现的那种典型弱点。

几个必须守住的约束
------------------
1. T+1：今天买的不能今天卖；今天卖出的只能是更早的底仓。
2. 同一只票**清仓之后才允许再买**。否则 FIFO 会把卖出匹配到更早的批次，
   设计好的「3 天赚 5%」会变成「22 天亏 3%」，画像直接失真（第二版栽在这里）。
3. 单票数量设上限，否则低价股按目标金额折算出几万股，一眼不合常理。
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# 演示账号集中在三条主线：贵金属、有色、科技。
# 这样归因里的「板块超额」才有明显方向性，评委会看到「板块在涨它独跌」这种
# 有解释力的对比，而不是一堆不相关的行业各走各的。
POOL = [
    ("600988", "赤峰黄金"), ("600547", "山东黄金"), ("600489", "中金黄金"),
    ("601899", "紫金矿业"), ("603993", "洛阳钼业"), ("601168", "西部矿业"),
    ("603799", "华友钴业"), ("600111", "北方稀土"), ("688981", "中芯国际"),
    ("603501", "韦尔股份"), ("002371", "北方华创"), ("300308", "中际旭创"),
]

MAX_SHARES = 6000
FEE_RATE = 0.0003
MIN_FEE = 5.0
STAMP = 0.0005
TRANSFER = 0.00001
ROUNDS = 3          # 每只票最多 3 轮：2 轮完整买卖 + 1 轮留作底仓


def _rows(klines, code):
    return [r for r in (klines.get(code) or []) if r[1] and r[2]]


def _fee(amount, side):
    f = max(MIN_FEE, amount * FEE_RATE) + amount * TRANSFER
    if side == "sell":
        f += amount * STAMP
    return round(f, 2)


def build(days=60, today_buys=6, today_sells=8, seed=20261104):
    from ashare import mover

    kl = mover._load()
    rnd = random.Random(seed)

    all_dates = sorted({r[0] for rows in kl.values() for r in rows})
    today = all_dates[-1]
    hist = all_dates[-(days + 1):-1]
    hist_set = set(hist)

    records = []
    base = {}
    rounds = {}
    last_sell = {}          # code -> 上一轮卖出日期，下一轮买入必须晚于它

    # ---------- 历史成交：每只票按轮次来，清仓后才允许下一轮 ----------
    attempts = 0
    while attempts < 5000:
        attempts += 1
        left = [(c, n) for c, n in POOL if rounds.get(c, 0) < ROUNDS]
        if not left:
            break
        code, name = rnd.choice(left)
        rows = _rows(kl, code)
        dates = [r[0] for r in rows]
        cand = [d for d in dates if d in hist_set]
        if len(cand) < 14:
            continue

        r = rounds.get(code, 0)
        make_base = (r == ROUNDS - 1)      # 最后一轮建底仓，留给今天卖

        if make_base:
            d0 = rnd.choice(cand[-16:])    # 近期建仓，避免今天卖出时持有期过长
            if d0 <= last_sell.get(code, ""):
                continue
            i0 = dates.index(d0)
            p0 = rows[i0][1]
            qty = max(100, int(rnd.choice([90000, 120000, 150000]) / p0 / 100) * 100)
            qty = min(qty, MAX_SHARES)
            records.append({"date": rows[i0][0], "code": code, "name": name,
                            "side": "buy", "qty": qty, "price": round(p0 * 1.0008, 2)})
            base[code] = qty
            rounds[code] = r + 1
            continue

        # 赢单拿得短但幅度要够（4~10 天、至少 +4%）；
        # 亏单拿得久（10~20 天）但幅度受控（-2% ~ -9%）。
        # 这个组合既保留「盈利跑得早、亏损拖得久」的可诊断弱点，
        # 又不会让盈亏比掉到 1 以下 —— 第一版亏损单能亏到 -17%，整体就废了。
        # 先决定这一笔要赢还是要亏，再在候选日期里找符合幅度区间的组合。
        # 反过来「先随机日期、再筛收益」会把大部分赢单筛掉，
        # 最后统计出来胜率 54%，和设计的 70% 差很远。
        want_win = rnd.random() < 0.70
        d_pool = list(cand[:-12])
        rnd.shuffle(d_pool)
        picked = None
        for d0 in d_pool[:45]:
            if d0 <= last_sell.get(code, ""):
                continue
            i0 = dates.index(d0)
            hold = rnd.randint(4, 10) if want_win else rnd.randint(10, 20)
            i1 = min(i0 + hold, len(dates) - 1)
            if i1 <= i0 or rows[i1][0] not in hist_set:
                continue
            p0, p1 = rows[i0][1], rows[i1][1]
            ret = p1 / p0 - 1
            if want_win and not (0.04 <= ret <= 0.16):
                continue
            if (not want_win) and not (-0.09 <= ret <= -0.02):
                continue
            picked = (i0, i1)
            break
        if not picked:
            continue
        i0, i1 = picked
        p0, p1 = rows[i0][1], rows[i1][1]

        qty = max(100, int(rnd.choice([80000, 120000, 150000]) / p0 / 100) * 100)
        qty = min(qty, MAX_SHARES)
        records.append({"date": rows[i0][0], "code": code, "name": name,
                        "side": "buy", "qty": qty, "price": round(p0 * 1.0008, 2)})
        records.append({"date": rows[i1][0], "code": code, "name": name,
                        "side": "sell", "qty": qty, "price": round(p1 * 0.9992, 2)})
        last_sell[code] = rows[i1][0]
        rounds[code] = r + 1

    # ---------- 今日买入：挑当日涨幅最大的几只，制造「追高」样本 ----------
    info = []
    for code, name in POOL:
        rows = _rows(kl, code)
        if len(rows) < 21 or rows[-1][0] != today:
            continue
        prev = rows[-2][1]
        pct = (rows[-1][1] / prev - 1) * 100 if prev else 0
        info.append((pct, code, name, rows[-1][1]))
    info.sort(reverse=True)

    bought_today = set()
    for i in range(min(today_buys, len(info))):
        pct, code, name, px = info[i]
        qty = max(100, int(rnd.choice([50000, 80000, 100000]) / px / 100) * 100)
        qty = min(qty, MAX_SHARES)
        records.append({"date": today, "code": code, "name": name,
                        "side": "buy", "qty": qty, "price": round(px * 1.0012, 2)})
        bought_today.add(code)

    # ---------- 今日卖出：只能卖底仓，且不是今天刚买的 ----------
    names = dict((c, n) for c, n in POOL)
    hold = {c: q for c, q in base.items() if q > 0 and c not in bought_today}
    order = list(hold.keys())
    rnd.shuffle(order)
    sold = 0
    for _r in range(2):                    # 允许同一标的拆两笔减
        for code in order:
            if sold >= today_sells or hold.get(code, 0) < 100:
                continue
            rows = _rows(kl, code)
            if len(rows) < 21 or rows[-1][0] != today:
                continue
            qty = 100 if hold[code] < 300 else rnd.choice([100, 200])
            records.append({"date": today, "code": code, "name": names.get(code, code),
                            "side": "sell", "qty": qty,
                            "price": round(rows[-1][1] * 0.9988, 2)})
            hold[code] -= qty
            sold += 1

    # ---------- 排序并算余额 ----------
    records.sort(key=lambda x: (x["date"], 0 if x["side"] == "buy" else 1, x["code"]))
    bal = {}
    for x in records:
        cur = bal.get(x["code"], 0)
        bal[x["code"]] = cur + x["qty"] if x["side"] == "buy" else max(0, cur - x["qty"])
        x["balance"] = bal[x["code"]]

    out = []
    for x in records:
        amt = round(x["qty"] * x["price"], 2)
        out.append({
            "证券代码": x["code"], "证券名称": x["name"], "发生日期": x["date"],
            "交易类别": "证券买入" if x["side"] == "buy" else "证券卖出",
            "成交数量": x["qty"], "成交均价": f'{x["price"]:.2f}',
            "成交金额": f"{amt:.2f}", "股份余额": x["balance"],
            "佣金": f'{_fee(amt, x["side"]):.2f}',
            "印花税": f'{round(amt * STAMP, 2) if x["side"] == "sell" else 0:.2f}',
            "过户费": f'{round(amt * TRANSFER, 2):.2f}',
        })
    meta = {"today": today, "n": len(out),
            "today_n": sum(1 for x in records if x["date"] == today),
            "holdings": {c: q for c, q in bal.items() if q > 0}}
    return out, meta


def write(path, rows):
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    rows, meta = build()
    print(f'生成 {meta["n"]} 笔成交，其中今日（{meta["today"]}）{meta["today_n"]} 笔')
    print("收盘持仓:", meta["holdings"])
    out = os.path.join(os.path.dirname(HERE), "data", "demo_statement.csv")
    write(out, rows)
    print("已写入", out)
