# -*- coding: utf-8 -*-
"""个股主力资金流：今天到底是主力在买，还是散户在接。

为什么值得单独接一个接口
------------------------
量比只能说明「放量了」，说明不了「谁在买」。同样是放量上涨，
主力净流入 8 亿和主力净流出 8 亿是两件相反的事。
东方财富按单笔金额把成交拆成大单/超大单/中小单，主力 = 大单 + 超大单，
这是目前公开数据里最接近「谁在动手」的口径。

口径与限制
----------
- 主力 = 超大单 + 大单；散户 = 中单 + 小单。各家定义的金额门槛不同，
  东财的口径是超大单 > 100 万、大单 20~100 万，实际以接口为准。
- 这是**按成交金额倒推的估算**，不是真实的席位数据。它能说明方向，
  不能证明某个人在买卖。页面上必须标明来源与口径。
- 只取当日。历史多日接口不稳定，而且对「今天为什么」这个问题没有增量。
- 接口失败就返回 None，不阻塞复盘：资金流是增强项，不是主链路。
"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
URL = ("https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
       "?lmt=0&klt=101&fields1=f1,f2,f3,f7"
       "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
       "&secid={secid}")


def secid(code):
    """6 位代码 → 东财 secid。沪市前缀 1，深市与北交所前缀 0。"""
    c = str(code).zfill(6)
    return ("1." if c[0] == "6" else "0.") + c


def fetch_one(code, timeout=6):
    """返回今日资金流（单位：元）。失败返回 None。"""
    try:
        r = requests.get(URL.format(secid=secid(code)), headers=HDRS, timeout=timeout)
        d = (r.json() or {}).get("data") or {}
        rows = d.get("klines") or []
        if not rows:
            return None
        p = str(rows[-1]).split(",")
        if len(p) < 6:
            return None
        f = [float(x) if x not in ("", "-", None) else None for x in p[1:6]]
        return {"date": p[0], "main": f[0], "small": f[1], "mid": f[2],
                "big": f[3], "super": f[4]}
    except Exception:
        return None


def fetch_many(codes, workers=6, budget=25.0):
    """并发拉一批，整体有时间预算。

    单只失败不影响其他只；整体超时就返回已经拿到的部分。
    复盘不能因为某只票的接口挂住而停在这一步。
    """
    codes = [c for c in codes if c]
    if not codes:
        return {}
    out, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_one, c): c for c in codes}
        for fut, c in futures.items():
            left = budget - (time.time() - t0)
            if left <= 0.5:
                break
            try:
                r = fut.result(timeout=max(0.5, left))
            except Exception:
                r = None
            if r:
                out[c] = r
    return out


def describe(ff):
    """把资金流翻译成一句话。数值单位统一成亿。"""
    if not ff or ff.get("main") is None:
        return None
    m = ff["main"] / 1e8
    sup = (ff.get("super") or 0) / 1e8
    sm = (ff.get("small") or 0) / 1e8
    if abs(m) < 0.05:
        return "主力资金基本持平"
    side = "净流入" if m > 0 else "净流出"
    txt = f"主力资金{side} {abs(m):.2f} 亿"
    if abs(sup) >= 0.3:
        txt += f"（其中超大单 {sup:+.2f} 亿）"
    if abs(sm) >= 0.3 and (m > 0) != (sm > 0):
        txt += f"，散户{('净流出' if sm < 0 else '净流入')} {abs(sm):.2f} 亿"
    return txt
