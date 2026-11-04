# -*- coding: utf-8 -*-
"""
交割单（对账单流水）还原持仓。

为什么需要：券商「导出」最常给的是**交割单**，不是持仓表。
交割单每行是一笔成交（买入/卖出/银行转账/红利），没有「持仓数量」「成本价」这两列，
所以按持仓表规则解析必然识别不出来 —— 这不是列名没覆盖到，是表的语义不同。

还原方法：
- 持仓数量：按买入 +、卖出 − 累计净额；同时用「股份余额」列交叉校验（两者应一致）
- 成本价：移动加权平均，含佣金/过户费/印花税等实际费用
  卖出时按当时均价结转，不改变剩余持仓的单位成本（与券商「摊薄成本」口径一致）
- 清零的标的自动剔除（买卖相抵后为 0，说明已清仓）

口径说明：
- 这里算的是**含费成本**，比券商界面的「成本价」略高（券商有的口径不含费）
- 分红送转不在交割单的买卖流水里，若期间有送股，数量会与实际不符，
  此时以「股份余额」列为准并给出提示
"""
import re

CODE_RE = re.compile(r"^\d{6}$")

# 列名识别：交割单的列名在各家券商间差异较大，用关键词匹配
COLS = {
    "date":   ["交收日期", "发生日期", "成交日期", "日期", "清算日期"],
    "time":   ["发生时间", "成交时间", "时间"],
    "code":   ["证券代码", "股票代码", "代码"],
    "name":   ["证券名称", "股票名称", "证券简称", "名称"],
    "action": ["交易类别", "业务名称", "操作", "摘要", "业务标志", "交易类型"],
    "qty":    ["成交数量", "成交股数", "数量", "股数"],
    "price":  ["成交均价", "成交价格", "成交价", "价格"],
    "amount": ["成交金额", "发生金额"],
    "balance": ["股份余额", "剩余股份", "持仓数量", "股票余额"],
    "fee":    ["佣金", "手续费"],
    "fee2":   ["其他费用", "其他杂费", "杂费"],
    "tax":    ["印花税"],
    "transfer": ["过户费"],
}

BUY_WORDS = ("证券买入", "买入", "buy", "申购", "配股缴款")
SELL_WORDS = ("证券卖出", "卖出", "sell", "赎回")
# 这些流水与持仓数量无关，直接跳过
SKIP_WORDS = ("银行转证券", "证券转银行", "利息归本", "指定交易", "撤单",
              "股息红利差异扣税", "红利入账", "托管转入", "托管转出")


def _pick(columns, keys):
    """在列名列表里找第一个命中关键词的列名。"""
    for k in keys:
        for c in columns:
            if k == str(c).strip():
                return c
    for k in keys:
        for c in columns:
            if k in str(c):
                return c
    return None


def looks_like_statement(columns):
    """判断是不是交割单：有「交易类别」类列 + 有「成交数量」类列，
    且没有现成的「持仓数量/成本价」组合。"""
    cols = [str(c) for c in columns]
    has_action = _pick(cols, COLS["action"]) is not None
    has_qty = _pick(cols, COLS["qty"]) is not None
    has_date = _pick(cols, COLS["date"]) is not None
    return bool(has_action and has_qty and has_date)


def _classify(action):
    a = str(action or "").strip()
    low = a.lower()
    if any(w in a or w in low for w in SKIP_WORDS):
        return "skip"
    if any(w in a or w in low for w in BUY_WORDS):
        return "buy"
    if any(w in a or w in low for w in SELL_WORDS):
        return "sell"
    return "skip"


STATEMENT_FILES = [
    "交割单.xlsx", "交割单.csv", "对账单.xlsx", "对账单.csv",
    "statement.xlsx", "statement.csv", "Table_1091.xlsx",
]


def find_statement():
    """在当前账号目录找交割单并读成 DataFrame。找不到返回 None。
    多用户下只看本账号目录，不回落到项目根目录 —— 交割单是隐私数据。"""
    import glob
    import os

    import pandas as pd

    try:
        from .context import user_root
        base = user_root()
    except Exception:
        from .data import ROOT as base

    cands = [os.path.join(base, n) for n in STATEMENT_FILES]
    for pat in ("*交割单*.xls*", "*对账单*.xls*", "*流水*.xls*", "Table_*.xls*"):
        cands += sorted(glob.glob(os.path.join(base, pat)))
    for p in cands:
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_excel(p) if p.lower().endswith((".xlsx", ".xlsm")) \
                else pd.read_csv(p, dtype=str)
            if looks_like_statement(df.columns):
                return df
        except Exception:
            continue
    return None


def column_map(df):
    """返回画像模块需要的列映射。与 rebuild 用同一套识别规则。"""
    cols = list(df.columns)
    return {
        "code": _pick(cols, COLS["code"]),
        "name": _pick(cols, COLS["name"]),
        "action": _pick(cols, COLS["action"]),
        "qty": _pick(cols, COLS["qty"]),
        "price": _pick(cols, COLS["price"]),
        "date": _pick(cols, COLS["date"]),
        "time": _pick(cols, COLS["time"]),
        "fees": [_pick(cols, COLS[k]) for k in ("fee", "fee2", "tax", "transfer")],
    }


def prepare(df):
    """清洗出「只含股票买卖」的 DataFrame，并按时间排序。画像与还原共用。"""
    import pandas as pd

    col = column_map(df)
    d = df.copy()
    d["__code"] = d[col["code"]].astype(str).str.strip()
    d = d[d["__code"].str.match(CODE_RE)]
    d = d[~d["__code"].str.startswith("799")]
    if col["date"]:
        d["__date"] = pd.to_datetime(d[col["date"]], errors="coerce")
        keys = ["__date"] + ([col["time"]] if col["time"] else [])
        d = d.sort_values(keys)
    col = dict(col)
    col["code"] = "__code"
    if col["date"]:
        col["date"] = "__date"
    return d, col


def rebuild(df):
    """从交割单 DataFrame 还原持仓。

    返回 (rows, meta)：
      rows: [{code, name, shares, cost, total_cost, buy, sell, balance_col, trades}]
      meta: {trades, span, skipped, mismatch}
    """
    cols = list(df.columns)
    c_code = _pick(cols, COLS["code"])
    c_act = _pick(cols, COLS["action"])
    c_qty = _pick(cols, COLS["qty"])
    c_px = _pick(cols, COLS["price"])
    if not all([c_code, c_act, c_qty, c_px]):
        raise ValueError("交割单缺少必要列（证券代码 / 交易类别 / 成交数量 / 成交均价）")

    c_name = _pick(cols, COLS["name"])
    c_date = _pick(cols, COLS["date"])
    c_time = _pick(cols, COLS["time"])
    c_bal = _pick(cols, COLS["balance"])
    fee_cols = [_pick(cols, COLS[k]) for k in ("fee", "fee2", "tax", "transfer")]
    fee_cols = [c for c in fee_cols if c]

    d = df.copy()
    d["__code"] = d[c_code].astype(str).str.strip()
    d = d[d["__code"].str.match(CODE_RE)]
    # 799999「指定登记」之类的伪代码不是股票
    d = d[~d["__code"].str.startswith("799")]
    if c_date:
        d["__d"] = d[c_date].astype(str)
        sort_keys = ["__d"] + (["__t"] if c_time else [])
        if c_time:
            d["__t"] = d[c_time].astype(str)
        d = d.sort_values(sort_keys)

    def num(v):
        try:
            if v is None:
                return 0.0
            s = str(v).replace(",", "").strip()
            if not s or s in ("-", "--", "—"):
                return 0.0
            return float(s)
        except Exception:
            return 0.0

    rows, skipped, mismatch = [], 0, []
    for code, g in d.groupby("__code", sort=False):
        shares = 0.0
        cost = 0.0            # 剩余持仓的累计含费成本
        buy_q = sell_q = 0.0
        trades = 0
        for _, r in g.iterrows():
            kind = _classify(r[c_act])
            if kind == "skip":
                skipped += 1
                continue
            q, px = num(r[c_qty]), num(r[c_px])
            if q <= 0:
                continue
            fee = sum(num(r[c]) for c in fee_cols)
            trades += 1
            if kind == "buy":
                cost += q * px + fee
                shares += q
                buy_q += q
            else:
                if shares > 0:
                    unit = cost / shares
                    take = min(q, shares)
                    cost -= take * unit     # 按当时均价结转，剩余单位成本不变
                    shares -= take
                sell_q += q

        if shares <= 0:
            continue        # 已清仓

        bal = None
        if c_bal is not None and len(g):
            bal = num(g.iloc[-1][c_bal])
        if bal is not None and bal > 0 and abs(bal - shares) > 0.5:
            mismatch.append({"code": code, "computed": int(shares), "balance": int(bal)})

        rows.append({
            "code": code,
            "name": (str(g.iloc[-1][c_name]).strip() if c_name else ""),
            "shares": int(round(shares)),
            "cost": round(cost / shares, 4),
            "total_cost": round(cost, 2),
            "buy": int(buy_q), "sell": int(sell_q),
            "balance_col": int(bal) if bal is not None else None,
            "trades": trades,
        })

    rows.sort(key=lambda x: -x["total_cost"])
    span = None
    if c_date and len(d):
        span = (str(d["__d"].min()), str(d["__d"].max()))
    return rows, {"trades": int(len(d)), "span": span,
                  "skipped": skipped, "mismatch": mismatch,
                  "fee_included": bool(fee_cols)}
