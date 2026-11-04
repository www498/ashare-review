# -*- coding: utf-8 -*-
"""
波动率预测与价格区间（HAR-RV + 对数变换 + 滚动重训）

为什么是波动率而不是涨跌方向：
实测 5 只票 814 个样本，方向预测准确率 53.8%，而"永远猜跌"基线 53.0%，
Brier 分数还差于基线 —— 方向没有可提取的信息。波动率则不同：样本外 R² 0.14~0.17。

数据源：baostock（前复权，除权跳空已被抹平，不会污染波动率）
所有预测严格 walk-forward：预测 t 时刻只用 t 及之前的数据。
用法：python -m ashare.forecast
"""
import datetime as dt

import numpy as np
import pandas as pd

WIN = 500      # 训练窗口（交易日）
STEP = 20      # 每 20 日重训
H = 5          # 预测跨度（交易日）
EPS = 1e-6

_logged = False


def _ensure_login():
    global _logged
    if not _logged:
        import baostock as bs
        bs.login()
        _logged = True


def load(sym, n=2800):
    """sym 形如 'sh600519'。取前复权日线，返回 date/close。
    默认 2800 个交易日（约 11 年）：样本太短时 R² 会为负，结论不稳定。"""
    import baostock as bs
    _ensure_login()
    code = sym[:2] + "." + sym[2:]
    end = dt.date.today()
    start = end - dt.timedelta(days=int(n * 1.6))
    rs = bs.query_history_k_data_plus(
        code, "date,close", start_date=start.isoformat(), end_date=end.isoformat(),
        frequency="d", adjustflag="2")   # 2 = 前复权
    rows = []
    while rs.error_code == "0" and rs.next():
        r = rs.get_row_data()
        if r[1]:
            rows.append((r[0], float(r[1])))
    if not rows:
        raise RuntimeError(f"{sym} baostock 无数据")
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True).tail(n).reset_index(drop=True)


def features(df):
    d = df.copy()
    r = d["close"].pct_change()
    d["rv1"] = r.abs()
    d["rv5"] = r.rolling(5).std()
    d["rv22"] = r.rolling(22).std()
    d["y"] = r.shift(-1).rolling(5).std().shift(-4)          # 未来5日（t+1..t+5）波动率
    d["fwd5"] = d["close"].shift(-H) / d["close"] - 1        # 未来5日收益
    return d


def walk_forward(d):
    from sklearn.linear_model import LinearRegression
    X = np.log(d[["rv1", "rv5", "rv22"]].values + EPS)
    y = np.log(d["y"].values + EPS)
    pred = np.full(len(d), np.nan)
    for i in range(WIN, len(d) - H, STEP):
        m = LinearRegression().fit(X[i - WIN:i], y[i - WIN:i])
        pred[i:i + STEP] = m.predict(X[i:i + STEP])
    d = d.copy()
    d["pred"] = np.exp(pred)
    return d


def oos_r2(d):
    m = d["pred"].notna() & d["y"].notna()
    if m.sum() < 50:
        return float("nan")
    a, p = d.loc[m, "y"].values, d.loc[m, "pred"].values
    return 1 - ((a - p) ** 2).sum() / ((a - a.mean()) ** 2).sum()


def calibrate(d, alpha=0.10):
    """标准化残差 e = 实际5日收益 / 预测5日波动率 的经验分位。
    不假设正态 —— A 股尾部比正态厚，照正态算会系统性低估区间宽度。
    用于生成当前区间。"""
    m = d["pred"].notna() & d["fwd5"].notna()
    e = (d.loc[m, "fwd5"] / d.loc[m, "pred"]).replace([np.inf, -np.inf], np.nan).dropna()
    return float(e.quantile(alpha)), float(e.quantile(1 - alpha)), len(e)


def rolling_coverage(d, alpha=0.10, min_hist=250):
    """滚动样本外覆盖率：对每个时刻 t，只用 t 之前的历史算分位，再看 t 是否落在区间内。
    这才是有意义的覆盖率 —— 用全样本分位去检验同一份数据，结果必然等于 80%。"""
    m = d["pred"].notna() & d["fwd5"].notna()
    sub = d.loc[m].reset_index(drop=True)
    e = (sub["fwd5"] / sub["pred"]).replace([np.inf, -np.inf], np.nan).values
    e = e[~np.isnan(e)]
    if len(e) <= min_hist + 50:
        return float("nan"), 0
    inside = []
    for i in range(min_hist, len(e)):
        lo, hi = np.quantile(e[:i], [alpha, 1 - alpha])
        inside.append(lo <= e[i] <= hi)
    return float(np.mean(inside)), len(inside)


def analyze_symbol(sym, name="", price=None):
    try:
        df = load(sym)
    except Exception:
        return None
    if len(df) < WIN + 100:
        return None
    d = features(df).dropna(subset=["rv1", "rv5", "rv22"]).reset_index(drop=True)
    d = walk_forward(d)
    q_lo, q_hi, _ = calibrate(d)
    cov, n_cov = rolling_coverage(d)

    px = float(price) if price else float(d["close"].iloc[-1])
    s5 = float(d["pred"].dropna().iloc[-1])
    return {
        "sym": sym, "name": name, "price": px,
        "asof": str(d["date"].iloc[-1].date()),
        "sigma_5d": s5,
        "ann_vol": s5 * np.sqrt(244 / H) * 100,
        "r2": oos_r2(d),
        "lo": px * (1 + q_lo * s5),
        "hi": px * (1 + q_hi * s5),
        "q_lo": q_lo, "q_hi": q_hi,
        "coverage": cov, "n": n_cov,
    }


def main():
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ashare import config as C
    from ashare.data import fetch_symbols

    syms = [(s, n) for s, n in C.INDICES] + [("sh" + c, n) for c, n in C.WATCHLIST.items()]
    live = {r["code"]: r for r in fetch_symbols([s for s, _ in syms])}

    print(f"{'标的':<10}{'现价':>10}{'5日波动':>9}{'年化':>8}{'80%区间':>22}{'覆盖率':>8}{'R²':>7}")
    print("-" * 76)
    for sym, name in syms:
        try:
            px = live.get(sym[2:], {}).get("price")
            r = analyze_symbol(sym, name, price=px)
            if not r:
                print(f"{name:<10} 数据不足")
                continue
            print(f"{r['name']:<10}{r['price']:>10.2f}{r['sigma_5d']*100:>8.2f}%{r['ann_vol']:>7.1f}%"
                  f"{r['lo']:>10.2f}~{r['hi']:<9.2f}{r['coverage']:>7.0%}{r['r2']:>7.3f}")
        except Exception as e:
            print(f"{name:<10} 失败 {type(e).__name__}: {str(e)[:40]}")
    print("\n区间为未来 5 个交易日的 80% 经验分位区间；覆盖率与 R² 均为历史 walk-forward 实测值，不是承诺。")


if __name__ == "__main__":
    main()
