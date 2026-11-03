# -*- coding: utf-8 -*-
"""
第二步：放弃"训练模型"，改测三件事的真实可预测性
A. 简单条件概率（分位数分箱）在样本外是否稳定  -> 支撑"依据"
B. 波动率是否可预测（HAR-RV）                   -> 支撑"仓位/风险"
C. 指数方向 vs 个股方向，哪个更可预测
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import akshare as ak

STOCKS = ["sh600519", "sz000001", "sz300750", "sz002594", "sh601318", "sh600036",
          "sz000858", "sh601899", "sz002415", "sh600030"]
START, END = "20190101", "20261101"
H = 5


def kl(sym):
    df = ak.stock_zh_a_daily(symbol=sym, start_date=START, end_date=END, adjust="qfq")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def feat(d):
    c = d["close"]
    d["ret5"] = c.pct_change(5)
    d["ret20"] = c.pct_change(20)
    d["ma20_dev"] = c / c.rolling(20).mean() - 1
    d["vol_ratio"] = d["volume"] / d["volume"].rolling(20).mean()
    d["vol20"] = c.pct_change().rolling(20).std()
    d["fwd5"] = c.shift(-H) / c.shift(-1) - 1
    return d


# ---------- A. 条件概率的样本外稳定性 ----------
pool = []
for s in STOCKS:
    try:
        pool.append(feat(kl(s)))
    except Exception:
        pass
df = pd.concat(pool, ignore_index=True).dropna(subset=["ret5", "ret20", "ma20_dev", "vol_ratio", "fwd5"])
df = df.sort_values("date")

cut = pd.Timestamp("2024-01-01")
tr, te = df[df["date"] < cut], df[df["date"] >= cut]
print(f"样本内 {len(tr)} 条 ({tr.date.min().date()}~{tr.date.max().date()})   样本外 {len(te)} 条 ({te.date.min().date()}~{te.date.max().date()})\n")

print("=== A1. 按 5 日动量分五档：未来5日上涨概率 ===")
print(f"{'档位':<8}{'样本内概率':>10}{'样本外概率':>10}{'样本内n':>8}{'样本外n':>8}{'稳定性':>8}")
q = tr["ret5"].quantile([0, .2, .4, .6, .8, 1]).values
for i in range(5):
    lo, hi = q[i], q[i + 1]
    a = tr[(tr.ret5 >= lo) & (tr.ret5 <= hi if i == 4 else tr.ret5 < hi)]
    b = te[(te.ret5 >= lo) & (te.ret5 <= hi if i == 4 else te.ret5 < hi)]
    pa, pb = (a.fwd5 > 0).mean(), (b.fwd5 > 0).mean()
    flag = "一致" if (pa - 0.5) * (pb - 0.5) > 0 else "翻转"
    print(f"{i+1:<8}{pa:>9.1%}{pb:>10.1%}{len(a):>8}{len(b):>8}{flag:>9}")

print("\n=== A2. 均线偏离度分五档 ===")
q = tr["ma20_dev"].quantile([0, .2, .4, .6, .8, 1]).values
for i in range(5):
    lo, hi = q[i], q[i + 1]
    a = tr[(tr.ma20_dev >= lo) & (tr.ma20_dev <= hi if i == 4 else tr.ma20_dev < hi)]
    b = te[(te.ma20_dev >= lo) & (te.ma20_dev <= hi if i == 4 else te.ma20_dev < hi)]
    pa, pb = (a.fwd5 > 0).mean(), (b.fwd5 > 0).mean()
    print(f"{i+1:<8}{pa:>9.1%}{pb:>10.1%}{len(a):>8}{len(b):>8}{'一致' if (pa-.5)*(pb-.5)>0 else '翻转':>9}")

# ---------- B. 波动率可预测性 ----------
print("\n=== B. 波动率预测 (HAR-RV: 用日/周/月已实现波动率预测未来5日) ===")
res = []
for s in ["sh000001", "sh600519", "sz300750"]:
    try:
        if s.startswith("sh000"):
            d = ak.stock_zh_index_daily(symbol=s)
            d["date"] = pd.to_datetime(d["date"]); d = d[d.date >= pd.Timestamp(START)].sort_values("date").reset_index(drop=True)
        else:
            d = kl(s)
        r = d["close"].pct_change()
        d["rv1"] = r.abs()
        d["rv5"] = r.rolling(5).std()
        d["rv22"] = r.rolling(22).std()
        d["y"] = r.shift(-1).rolling(5).std().shift(-4)   # 未来5日波动率
        d = d.dropna(subset=["rv1", "rv5", "rv22", "y"])
        X = d[["rv1", "rv5", "rv22"]].values
        y = d["y"].values
        sp = int(len(d) * 0.7)
        from sklearn.linear_model import LinearRegression
        m = LinearRegression().fit(X[:sp], y[:sp])
        p = m.predict(X[sp:])
        ss_res = ((y[sp:] - p) ** 2).sum(); ss_tot = ((y[sp:] - y[sp:].mean()) ** 2).sum()
        r2 = 1 - ss_res / ss_tot
        # 方向：明天波动比今天大吗
        res.append((s, round(r2, 3), len(d) - sp))
    except Exception as e:
        res.append((s, str(e)[:30], 0))
for x in res:
    print(f"  {x[0]:<12} 样本外 R² = {x[1]}   n={x[2]}")

# ---------- C. 市场层面 vs 个股 ----------
print("\n=== C. 预测目标换成指数，方向准确率如何 ===")
d = ak.stock_zh_index_daily(symbol="sh000001")
d["date"] = pd.to_datetime(d["date"]); d = d[d.date >= pd.Timestamp(START)].sort_values("date").reset_index(drop=True)
c = d["close"]
d["ret5"] = c.pct_change(5); d["ma20_dev"] = c / c.rolling(20).mean() - 1
d["up_ratio_proxy"] = c.pct_change() > 0
d["y5"] = (c.shift(-H) / c.shift(-1) - 1 > 0).astype(int)
d["y1"] = (c.shift(-1) / c - 1 > 0).astype(int)
d = d.dropna()
for tgt in ["y1", "y5"]:
    base = d[tgt].mean()
    # 简单规则：5日动量向上的时候猜涨
    sig = (d["ret5"] > 0).astype(int)
    acc = (sig == d[tgt]).mean()
    print(f"  指数 {tgt}: 基准(猜涨)={base:.1%}  用'5日动量>0'规则准确率={acc:.1%}  n={len(d)}")
