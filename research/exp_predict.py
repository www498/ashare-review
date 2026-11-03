# -*- coding: utf-8 -*-
"""
预测能力真实测：严格 walk-forward，禁止任何未来函数。
问题定义：在 t 日收盘后，预测 t+1..t+5 的 5 日收益是否为正。
特征只用到 t 日及之前的数据；标签用 t+1 起的未来数据。
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import akshare as ak
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler

STOCKS = [("sh600519", "贵州茅台"), ("sz000001", "平安银行"),
          ("sz300750", "宁德时代"), ("sz002594", "比亚迪"),
          ("sh601318", "中国平安")]
START, END = "20200101", "20261101"
H = 5          # 预测跨度
TRAIN_WIN = 750  # 训练窗口（交易日）
STEP = 20      # 每 20 天重训一次


def get_kline(sym):
    df = ak.stock_zh_a_daily(symbol=sym, start_date=START, end_date=END, adjust="qfq")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def build_features(df, mkt):
    d = df.copy()
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    d["ret1"] = c.pct_change()
    d["ret5"] = c.pct_change(5)
    d["ret20"] = c.pct_change(20)
    d["vol20"] = d["ret1"].rolling(20).std()
    d["ma20_dev"] = c / c.rolling(20).mean() - 1
    d["ma60_dev"] = c / c.rolling(60).mean() - 1
    d["vol_ratio"] = v / v.rolling(20).mean()
    # RSI14
    diff = c.diff()
    up = diff.clip(lower=0).rolling(14).mean()
    dn = (-diff.clip(upper=0)).rolling(14).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # ATR%
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr_pct"] = tr.rolling(14).mean() / c
    # 距 20 日高点位置
    d["pos20"] = c / h.rolling(20).max()
    d["vol_z"] = (d["vol20"] - d["vol20"].rolling(60).mean()) / d["vol20"].rolling(60).std()
    # 市场状态
    d = d.merge(mkt, on="date", how="left")
    # 标签：未来 5 日收益（t+1 买入，t+5 收盘）
    d["fwd5"] = c.shift(-H) / c.shift(-1) - 1
    d["y"] = (d["fwd5"] > 0).astype(int)
    return d


def walk_forward(d, feats, model_fn):
    """滚动前推。第 i 次训练只用 [i-TRAIN_WIN, i) 的数据，预测 [i, i+STEP)。"""
    X, y = d[feats].values, d["y"].values
    idx = np.arange(len(d))
    preds = []
    for start in range(TRAIN_WIN, len(d) - H, STEP):
        tr = idx[start - TRAIN_WIN:start]
        te = idx[start:min(start + STEP, len(d) - H)]
        tr = tr[~np.isnan(X[tr]).any(axis=1)]
        te = te[~np.isnan(X[te]).any(axis=1)]
        if len(tr) < 200 or len(te) == 0 or len(np.unique(y[tr])) < 2:
            continue
        sc = StandardScaler().fit(X[tr])
        m = model_fn()
        m.fit(sc.transform(X[tr]), y[tr])
        p = m.predict_proba(sc.transform(X[te]))[:, 1]
        preds.append(pd.DataFrame({"i": te, "p": p, "y": y[te]}))
    if not preds:
        return None
    return pd.concat(preds).drop_duplicates("i").sort_values("i")


FEATS = ["ret1", "ret5", "ret20", "vol20", "ma20_dev", "ma60_dev",
         "vol_ratio", "rsi", "atr_pct", "pos20", "vol_z", "mkt_ret5", "mkt_ma20_dev"]

print("拉取数据...")
mkt = ak.stock_zh_index_daily(symbol="sh000001")
mkt["date"] = pd.to_datetime(mkt["date"])
mkt = mkt[mkt["date"] >= pd.Timestamp("2019-06-01")].copy()
mkt["mkt_ret5"] = mkt["close"].pct_change(5)
mkt["mkt_ma20_dev"] = mkt["close"] / mkt["close"].rolling(20).mean() - 1
mkt = mkt[["date", "mkt_ret5", "mkt_ma20_dev"]]

rows = []
for sym, name in STOCKS:
    try:
        d = get_kline(sym)
        d = build_features(d, mkt)
        d = d.dropna(subset=FEATS + ["fwd5"]).reset_index(drop=True)
        for mname, fn in [("逻辑回归", lambda: LogisticRegression(max_iter=1000, C=0.5)),
                          ("梯度提升", lambda: HistGradientBoostingClassifier(max_depth=3, max_iter=120, learning_rate=0.06, random_state=0))]:
            r = walk_forward(d, FEATS, fn)
            if r is None or len(r) < 100:
                continue
            acc = ((r["p"] > 0.5) == (r["y"] == 1)).mean()
            auc = roc_auc_score(r["y"], r["p"])
            bs = brier_score_loss(r["y"], r["p"])
            base = r["y"].mean()                      # 永远猜涨的准确率
            base_bs = brier_score_loss(r["y"], np.full(len(r), base))
            rows.append(dict(股票=name, 模型=mname, 样本=len(r),
                             方向准确率=round(acc * 100, 1), 永远猜涨=round(base * 100, 1),
                             AUC=round(auc, 3), Brier=round(bs, 4), 基线Brier=round(base_bs, 4)))
            if sym == "sh600519" and mname == "梯度提升":
                keep = r.copy()
    except Exception as e:
        print("skip", name, type(e).__name__, str(e)[:60])

res = pd.DataFrame(rows)
print("\n=== 单票方向预测（5 日） walk-forward ===")
print(res.to_string(index=False))

print("\n=== 汇总 ===")
print(res.groupby("模型")[["方向准确率", "永远猜涨", "AUC", "Brier"]].mean().round(3).to_string())

# 概率校准检查
print("\n=== 概率校准（茅台-梯度提升）：我说 p 的时候，实际涨的比例 ===")
d = get_kline("sh600519"); d = build_features(d, mkt)
d = d.dropna(subset=FEATS + ["fwd5"]).reset_index(drop=True)
r = walk_forward(d, FEATS, lambda: HistGradientBoostingClassifier(max_depth=3, max_iter=120, learning_rate=0.06, random_state=0))
r["bin"] = pd.cut(r["p"], [0, .4, .45, .5, .55, .6, 1.0])
cal = r.groupby("bin", observed=True).agg(预测概率=("p", "mean"), 实际上涨率=("y", "mean"), 样本数=("y", "size"))
print(cal.round(3).to_string())
