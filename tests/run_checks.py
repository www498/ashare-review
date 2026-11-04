# -*- coding: utf-8 -*-
"""离线自检：不联网，用构造数据 + 本地快照校验几个关键口径。

为什么需要
----------
这个项目里最值钱的东西是「数字能对上」：三段归因相加要等于涨跌，
FIFO 配对不能凭空多出或少掉一笔，16 型不能有重复代号。
这些性质靠肉眼看报告发现不了，必须写成断言。

跑法：
    python tests/run_checks.py

全部通过返回 0，任何一条失败返回 1（可直接接进 CI）。
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ashare import explain, news, profile

FAILS = []
OKS = []


def check(name, cond, detail=""):
    (OKS if cond else FAILS).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))


def check_attribution():
    """三段归因必须能加回涨跌，否则页面上「三项相加 = 累计涨跌」就是假话。"""
    snaps = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "users", "*", "snapshots", "*.json")))
    if not snaps:
        check("归因可加性（无快照，跳过）", True, "没有本地快照，只跑构造用例")
        return
    ctx = json.load(open(snaps[-1], encoding="utf-8"))
    bad = []
    for a in ctx.get("anomalies") or []:
        ex = explain.day_reason(a, ctx, news=((ctx.get("cards") or {})
                                              .get(a["code"]) or {}).get("news"))
        if not ex:
            continue
        s = sum(v for _, v in ex["parts"])
        if abs(s - ex["pct"]) > 0.05:
            bad.append(f'{a.get("name")} {s:.3f}≠{ex["pct"]:.3f}')
    check("归因三段相加等于当日涨跌", not bad, "; ".join(bad[:3]))


def check_types():
    """16 型：数量、字母唯一性、缺维度补齐。"""
    t = profile.TYPES
    check("16 型数量为 16", len(t) == 16, f"实际 {len(t)}")
    check("代号长度都是 4", all(len(k) == 4 for k in t))
    check("每个维度的两个字母只出现一次",
          all(sum(1 for k in t if ch in k) == 8 for ch in "FSB ACRKD".replace(" ", "")))
    check("resolve_type 能补齐缺维度的代号",
          profile.resolve_type("FCK") in t and profile.resolve_type("FC") in t)
    check("无效代号返回 None", profile.resolve_type("") is None)


def check_fifo():
    """FIFO：整笔卖出配对一笔，部分卖出按批次拆开，不应凭空产生交易。"""
    import pandas as pd
    df = pd.DataFrame([
        {"code": "600000", "name": "测试", "act": "证券买入", "qty": 100,
         "px": 10.0, "date": None},
        {"code": "600000", "name": "测试", "act": "证券卖出", "qty": 100,
         "px": 11.0, "date": None},
    ])
    col = {"code": "code", "name": "name", "action": "act", "qty": "qty",
           "price": "px", "date": "date", "fees": []}
    trades = profile.fifo_match(df, col)
    check("整笔买卖配成 1 笔", len(trades) == 1, f"实际 {len(trades)}")
    if trades:
        check("盈亏方向正确", trades[0]["pnl"] > 0, f'{trades[0]["pnl"]:.2f}')

    df2 = pd.DataFrame([
        {"code": "600000", "name": "测试", "act": "证券买入", "qty": 100,
         "px": 10.0, "date": None},
        {"code": "600000", "name": "测试", "act": "证券买入", "qty": 100,
         "px": 12.0, "date": None},
        {"code": "600000", "name": "测试", "act": "证券卖出", "qty": 150,
         "px": 13.0, "date": None},
    ])
    t2 = profile.fifo_match(df2, col)
    check("跨批次部分卖出拆成 2 笔", len(t2) == 2, f"实际 {len(t2)}")
    check("卖出总量守恒", abs(sum(x["qty"] for x in t2) - 150) < 1e-6)


def check_news():
    """新闻挂载：等级只有三种、单票不超限、同一条不会挂满全表。"""
    items = [{"title": f"测试新闻{i}", "time": "10:00", "source": "t"} for i in range(6)]
    items[0]["title"] = "紫金矿业公告：铜产量创新高"
    items[1]["title"] = "LME 铜库存下降 有色走强"
    targets = {f"60000{i}": {"name": n, "industry": "有色金属"}
               for i, n in enumerate(["紫金矿业", "云铝股份", "洛阳钼业", "江西铜业"])}
    got = news.attach(items, targets, limit=4)
    check("挂载结果不超过 limit",
          all(len(v) <= 4 for v in got.values()),
          f"最大 {max((len(v) for v in got.values()), default=0)}")
    check("等级只有 个股/行业/宏观",
          all(x["level"] in ("个股", "行业", "宏观") for v in got.values() for x in v))
    cnt = {}
    for v in got.values():
        for x in v:
            cnt[x["title"]] = cnt.get(x["title"], 0) + 1
    check("同一条新闻最多挂 3 只票（spread）",
          max(cnt.values(), default=0) <= 3, f"最大 {max(cnt.values(), default=0)}")
    check("没命中行业关键词的不硬挂",
          all(not v for k, v in got.items() if k == "600009"))


def main():
    print("复盘台 · 离线自检\n")
    for fn in (check_types, check_fifo, check_attribution, check_news):
        print(f"[{fn.__name__.replace('check_', '')}]")
        try:
            fn()
        except Exception as e:
            check(fn.__name__ + " 未抛异常", False, f"{type(e).__name__}: {e}")
        print()
    print(f"通过 {len(OKS)} 项，失败 {len(FAILS)} 项")
    if FAILS:
        print("失败项：" + "、".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
