# -*- coding: utf-8 -*-
"""
历史宽度回补：用沪A 全量日K 反算过去 N 个交易日的涨跌家数、涨停数、中位数、量能与温度，
产出 data/breadth_history.csv，供报告展示温度趋势。

数据源：新浪历史日K（稳定、不限流），腾讯日K 作备用。
口径与实时一致（都用 pct 阈值判涨停），避免历史与现在对不上。
用法：python -m ashare.history --days 120
"""
import argparse, os, pickle, time
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor

from . import analyze
from .data import ROOT, universe, sym, limit_pct

SINA_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={n}")
TX_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
HIST_CSV = os.path.join(ROOT, "data", "breadth_history.csv")

LIMIT_MAIN = 9.85
LIMIT_STAR = 19.85
ABNORMAL_PCT = 21.5   # 超过此值视为除权/复牌异常，剔除，不参与统计


def _kline_sina(sym, n, retry=2):
    for i in range(retry):
        try:
            r = requests.get(SINA_URL.format(sym=sym, n=n), headers=HEADERS, timeout=12)
            arr = r.json()
            if not arr:
                raise ValueError("empty")
            # 新浪 volume 单位为「股」
            return sym[2:], [(x["day"], float(x["close"]), float(x["volume"])) for x in arr]
        except Exception:
            time.sleep(0.3 * (i + 1))
    return sym[2:], []


def _kline_tx(sym, n):
    try:
        r = requests.get(TX_URL.format(sym=sym, n=n), headers=HEADERS, timeout=12)
        arr = r.json()["data"][sym]
        arr = arr.get("qfqday") or arr.get("day") or []
        return sym[2:], [(x[0], float(x[2]), float(x[5]) * 100) for x in arr]  # 手 -> 股
    except Exception:
        return sym[2:], []


def fetch_all(codes, n, workers=8, cache=True):
    cache_fp = os.path.join(ROOT, "data", "klines_cache.pkl")
    today = time.strftime("%Y-%m-%d")
    if cache and os.path.exists(cache_fp):
        with open(cache_fp, "rb") as f:
            c = pickle.load(f)
        if c.get("date") == today and c.get("n") == n and len(c.get("data", {})) > len(codes) * 0.9:
            print(f"命中当日缓存（{len(c['data'])} 只）")
            return c["data"]

    syms = [sym(c) for c in codes]
    out, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (code, rows) in enumerate(ex.map(lambda s: _kline_sina(s, n), syms), 1):
            if rows:
                out[code] = rows
            if i % 500 == 0:
                print(f"  ...{i}/{len(syms)}  成功 {len(out)}  已用 {time.time()-t0:.0f}s")
    rate = len(out) / max(1, len(syms))
    print(f"新浪源成功率 {rate:.1%}（{len(out)}/{len(syms)}）")
    if rate < 0.85:
        raise SystemExit(f"成功率过低（{rate:.0%}），数据源可能被限流，稍后重跑")
    if cache:
        with open(cache_fp, "wb") as f:
            pickle.dump({"n": n, "date": today, "data": out}, f)
    return out


def backfill(days=120, codes=None):
    codes = codes or universe()
    if not codes:
        raise SystemExit("沪A 成分表为空")
    print(f"拉取 {len(codes)} 只沪深京日K（{days+5} 个交易日）...")
    data = fetch_all(codes, days + 5)

    close, vol = {}, {}
    for code, rows in data.items():
        close[code] = {d: c for d, c, _ in rows}
        vol[code] = {d: v for d, _, v in rows}
    cdf = pd.DataFrame(close).sort_index()
    vdf = pd.DataFrame(vol).sort_index()

    pct = cdf.pct_change() * 100
    # 除权跳空剔除。阈值按各板块涨跌停幅度定，否则北交所 30% 涨停会被误删
    cap = pd.Series({c_: limit_pct(c_) + 2.0 for c_ in pct.columns})
    pct = pct.mask(pct.abs().gt(cap, axis=1))

    # 涨跌停改用「价格口径」与实时保持一致：涨停价 = round(前收 × (1+幅度), 2)。
    # 用涨跌幅阈值（如 9.85%）会漏掉低价股：2.04 × 1.10 = 2.244 → 2.24，实际只有 9.80%。
    prev_close = cdf.shift(1)
    lim_rate = pd.Series({c_: limit_pct(c_) for c_ in cdf.columns})
    lu_price = prev_close.mul(1 + lim_rate / 100).round(2)
    ld_price = prev_close.mul(1 - lim_rate / 100).round(2)
    valid = prev_close.notna() & pct.notna()
    is_lu = cdf.ge(lu_price - 1e-9) & valid
    is_ld = cdf.le(ld_price + 1e-9) & valid

    idx_rows = _kline_sina("sh000001", days + 5)[1]
    idx_pct = {d: (c / p - 1) * 100 for (d, c, _), (_, p, _) in zip(idx_rows[1:], idx_rows[:-1])}

    total_vol = vdf.sum(axis=1)
    prev_vol = total_vol.shift(1)

    rows, bad_codes = [], set()
    for d in pct.index[1:][-days:]:
        p = pct.loc[d].dropna()
        if len(p) < 200:
            continue
        lu, ld = int(is_lu.loc[d].sum()), int(is_ld.loc[d].sum())
        up, down = int((p > 0.05).sum()), int((p < -0.05).sum())
        flat = len(p) - up - down

        amt_s = (cdf.loc[d] * vdf.loc[d] / 1e8).dropna()   # 新浪 volume 为股 -> 元/1e8 = 亿元
        bad = amt_s[amt_s > 500]
        if len(bad):
            bad_codes.update(bad.index.tolist())
        amt = float(amt_s[amt_s <= 500].sum())

        vr = float(total_vol.loc[d] / prev_vol.loc[d]) if prev_vol.loc[d] else None
        b = {"n": len(p), "up": up, "down": down, "flat": flat, "up_ratio": up / len(p),
             "limit_up": lu, "limit_down": ld, "median_pct": float(p.median())}
        ip = idx_pct.get(d, 0.0)
        t = analyze.temperature(b, ip, vr)
        rows.append({"date": d, "up": up, "down": down, "flat": flat,
                     "up_ratio": round(b["up_ratio"], 4), "limit_up": lu, "limit_down": ld,
                     "median_pct": round(b["median_pct"], 2), "amount_yi": round(amt, 0),
                     "idx_pct": round(ip, 2), "vol_ratio": round(vr, 3) if vr else "",
                     "temp": t["total"], "band": t["band"]})

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(HIST_CSV), exist_ok=True)
    df.to_csv(HIST_CSV, index=False, encoding="utf-8-sig")
    print(f"\n已写入 {HIST_CSV}，共 {len(df)} 个交易日")
    if bad_codes:
        print(f"[警告] 剔除 {len(bad_codes)} 只成交额异常标的：{sorted(bad_codes)[:8]}")
    print(f"成交额区间 {df['amount_yi'].min():.0f} ~ {df['amount_yi'].max():.0f} 亿（合理区间约 3000~20000）")
    print(df.tail(10).to_string(index=False))
    return df


def upsert_today(ctx):
    """把当日收盘结果并入历史表（同一天重复跑则覆盖）。
    非交易日拒绝写入：否则节假日跑一次会把陈旧盘口当成新的一天，污染温度趋势与分位。"""
    try:
        from .tcal import is_trading_day
        if not is_trading_day(ctx["date"]):
            raise ValueError(f"{ctx['date']} 非交易日，拒绝写入历史表（避免污染趋势口径）")
    except ImportError:
        pass
    b = ctx["breadth"]
    row = {"date": ctx["date"], "up": b["up"], "down": b["down"], "flat": b["flat"],
           "up_ratio": round(b["up_ratio"], 4), "limit_up": b["limit_up"],
           "limit_down": b["limit_down"], "median_pct": round(b["median_pct"], 2),
           "amount_yi": round(b["amount_yi"], 0),
           "idx_pct": round(ctx["indices"][0][1]["pct"], 2),
           "vol_ratio": round(ctx["vratio"], 3) if ctx["vratio"] else "",
           "temp": ctx["temperature"]["total"], "band": ctx["temperature"]["band"]}
    if os.path.exists(HIST_CSV):
        df = pd.read_csv(HIST_CSV, encoding="utf-8-sig")
        df = df[df["date"] != row["date"]]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(HIST_CSV, index=False, encoding="utf-8-sig")
    return df


def trend(n=20):
    if not os.path.exists(HIST_CSV):
        return None
    df = pd.read_csv(HIST_CSV, encoding="utf-8-sig").sort_values("date")
    if len(df) < 2:
        return None
    t = df["temp"].astype(float)
    cur = float(t.iloc[-1])
    return {
        "n": len(df), "cur": cur, "asof": str(df["date"].iloc[-1]),
        "ma5": float(t.tail(5).mean()),
        "ma10": float(t.tail(10).mean()),
        "ma20": float(t.tail(20).mean()) if len(t) >= 20 else None,
        "pctile": float((t < cur).mean() * 100),
        "chg5": cur - float(t.iloc[-6]) if len(t) >= 6 else None,
        "series": df.tail(n)[["date", "temp", "band"]].values.tolist(),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    a = ap.parse_args()
    backfill(a.days)
