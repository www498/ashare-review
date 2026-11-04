# -*- coding: utf-8 -*-
"""
持仓自动导入：识别券商/行情软件导出的持仓表，自动映射列。

为什么不做「直接读客户端数据库」：
东方财富、同花顺的本地持仓是私有加密格式，且需要登录态，逆向既不稳妥也不合规。
但它们都支持导出对账单/持仓表（CSV / Excel），这是官方给的出口，解析它是正路。

支持：
    东方财富  持仓 → 右键导出 / 复制整表
    同花顺    持仓 → 导出数据
    各券商    App 里的「对账单」「交割单」

处理逻辑：
1. 找表头行（含「代码」「名称」「持仓」等关键词的那一行）
2. 按关键词把列映射成 代码 / 名称 / 数量 / 成本价 / 现价
3. 没有表头时退回按位置解析（代码,名称,数量,成本）
4. 只保留沪深京 A 股，基金/转债/港股通自动跳过

用法：
    python -m ashare.positions --check        看识别结果
    python -m ashare.positions --template     查看支持的文件名与格式
"""
import argparse
import os
import re

from .data import ROOT, is_a_share

# 候选文件（放在项目根目录，按顺序找第一个存在的）
# 持仓表与交割单都支持：parse_text 会自动判别，交割单按流水还原持仓
FILES = [
    "positions.csv", "positions.txt", "positions.xlsx",
    "持仓.csv", "持仓.txt", "持仓.xlsx",
    "对账单.csv", "对账单.txt", "对账单.xlsx",
    "交割单.csv", "交割单.txt", "交割单.xlsx",
    "statement.csv", "statement.xlsx",
]

# 表头关键词 -> 内部字段。顺序有讲究：先匹配更具体的
COLUMN_RULES = [
    ("code",   ["证券代码", "股票代码", "合约代码", "代码"]),
    ("name",   ["证券名称", "股票名称", "证券简称", "股票简称", "名称"]),
    ("shares", ["当前持仓", "持仓数量", "持股数量", "股票余额", "证券数量",
                "持股", "股数", "余额", "持仓", "数量"]),
    ("cost",   ["摊薄成本", "持仓成本", "参考成本", "成本价", "保本价", "成本"]),
    ("price",  ["最新价", "现价", "市价", "当前价"]),
]

CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("￥", "").replace("¥", "").strip()
    if not s or s in ("-", "--", "—"):
        return None
    m = NUM_RE.search(s)
    return float(m.group()) if m else None


def _split(line):
    """一行切成单元格。优先按 Tab，其次按逗号，最后按多个空格。"""
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    if "," in line:
        return [c.strip() for c in line.split(",")]
    return [c.strip() for c in re.split(r"\s{2,}", line)]


def _map_header(cells):
    """根据表头识别列索引，返回 {字段: 列号}"""
    idx = {}
    for field, keys in COLUMN_RULES:
        for i, cell in enumerate(cells):
            if i in idx.values():
                continue
            if any(k in cell for k in keys):
                idx[field] = i
                break
    return idx


def _try_statement(text):
    """先按交割单（流水）解析。券商导出的往往是交割单而非持仓表：
    每行是一笔成交、没有「持仓数量/成本价」列，按持仓表规则必然识别为 0 条。
    返回 (watch, positions, meta) 或 None（不是交割单）。"""
    try:
        import io

        import pandas as pd

        from . import statement as stmt
        # parse_text 收到的始终是 CSV 文本（xlsx 已在 _read_file 里转过）
        df = pd.read_csv(io.StringIO(text), dtype=str)
        if not stmt.looks_like_statement(df.columns):
            return None
        rows, meta = stmt.rebuild(df)
        if not rows:
            return None
        watch, positions, prices = {}, {}, {}
        for r in rows:
            code = r["code"]
            watch[code] = r["name"] or code
            positions[code] = {"shares": r["shares"], "cost": r["cost"]}
        return watch, positions, {
            "rows": len(rows), "header": True, "columns": {},
            "prices": prices, "kind": "statement",
            "trades": meta.get("trades"), "span": meta.get("span"),
            "mismatch": meta.get("mismatch") or [],
            "fee_included": meta.get("fee_included"),
            "detail": rows,
        }
    except Exception:
        return None


def parse_text(text):
    """解析整张表，返回 (watch{code:name}, positions{code:{shares,cost}}, meta)"""
    lines = [l.rstrip("\n\r") for l in text.splitlines() if l.strip()]
    if not lines:
        return {}, {}, {"rows": 0}

    st = _try_statement(text)
    if st:
        return st

    header_idx = None
    for i, line in enumerate(lines[:12]):
        cells = _split(line)
        if any(("代码" in c or "名称" in c) for c in cells):
            header_idx = i
            break

    watch, positions, prices = {}, {}, {}
    mapping = _map_header(_split(lines[header_idx])) if header_idx is not None else {}
    data_lines = lines[header_idx + 1:] if header_idx is not None else lines

    for line in data_lines:
        cells = _split(line)
        code = None
        if "code" in mapping and mapping["code"] < len(cells):
            m = CODE_RE.search(cells[mapping["code"]])
            code = m.group(1) if m else None
        if not code:
            for c in cells:
                m = CODE_RE.search(c)
                if m:
                    code = m.group(1)
                    break
        if not code or not is_a_share(code):
            continue

        name = ""
        if "name" in mapping and mapping["name"] < len(cells):
            nm = cells[mapping["name"]].strip()
            if re.search(r"[\u4e00-\u9fa5A-Za-z]", nm) and not CODE_RE.search(nm):
                name = nm
        watch[code] = name or code

        if mapping:
            shares = _to_num(cells[mapping["shares"]]) if "shares" in mapping and mapping["shares"] < len(cells) else None
            cost = _to_num(cells[mapping["cost"]]) if "cost" in mapping and mapping["cost"] < len(cells) else None
            if "price" in mapping and mapping["price"] < len(cells):
                pv = _to_num(cells[mapping["price"]])
                if pv:
                    prices[code] = pv
        else:
            # 没有表头：按「代码, 名称, 数量, 成本」的位置猜
            shares = cost = None
            if len(cells) >= 4:
                a_, b_ = _to_num(cells[2]), _to_num(cells[3])
                if a_ is not None and b_ is not None and a_ > 0 and b_ > 0:
                    shares, cost = a_, b_
        if shares and shares > 0 and cost and cost > 0:
            positions[code] = {"shares": shares, "cost": cost}

    return watch, positions, {
        "rows": len(data_lines),
        "header": header_idx is not None,
        "columns": mapping,
        "prices": prices,
    }


def _read_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            import pandas as pd
            df = pd.read_excel(path, dtype=str)
            return df.to_csv(index=False)
        except Exception as e:
            raise SystemExit(f"读取 {path} 失败（{e}）。请另存为 CSV 后再试。")
    if ext == ".xls":
        raise SystemExit(f"{path} 是老版 Excel 格式，请在软件里另存为 CSV 或 xlsx。")
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def find_file():
    """当前账号的持仓文件。多用户下在 users/<uid>/ 里找，
    单用户兼容模式回退项目根目录。"""
    try:
        from .context import user_root
        base = user_root()
    except Exception:
        base = ROOT
    for name in FILES:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    if base != ROOT:
        return None          # 多用户模式不回落到全局，避免读到别人的持仓
    return None


def load():
    """返回 (watch, positions, meta)。没有持仓文件时返回空。"""
    fp = find_file()
    if not fp:
        return {}, {}, None
    watch, positions, meta = parse_text(_read_file(fp))
    meta["file"] = os.path.basename(fp)
    return watch, positions, meta


TEMPLATE = """把东方财富/同花顺/券商的持仓表直接粘到这里，或另存为 positions.csv 放在项目根目录。
支持 CSV / TXT / xlsx，表头列名自动识别（代码 / 名称 / 持仓 / 成本价 / 现价 任意顺序）。

示例（东财「持仓」复制出来的样子，Tab 分隔）：

证券代码\t证券名称\t持仓数量\t可用数量\t成本价\t现价\t市值\t盈亏
600519\t贵州茅台\t100\t100\t1392.05\t1439.10\t143910.00\t4705.00
601318\t中国平安\t1000\t1000\t48.30\t53.12\t53120.00\t4820.00
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--template", action="store_true")
    a = ap.parse_args()

    if a.template:
        print(TEMPLATE)
        return

    watch, positions, meta = load()
    if not meta:
        print("没有找到持仓文件。可用的文件名：")
        for f in FILES:
            print("  ", f)
        print("\n把导出的表另存为其中之一，放在项目根目录即可。")
        return

    print(f"文件：{meta['file']}　数据行：{meta['rows']}　"
          f"表头：{'识别到' if meta['header'] else '未识别，按位置解析'}")
    if meta["columns"]:
        rev = {v: k for k, v in meta["columns"].items()}
        print("列映射：" + "　".join(f"{k}=第{v+1}列" for k, v in meta["columns"].items()))
    print()
    for code, name in watch.items():
        p = positions.get(code)
        tag = f"　{p['shares']:,.0f} 股 @ {p['cost']:.3f}" if p else "　（无持仓数量/成本）"
        print(f"  {code}  {name}{tag}")
    print(f"\n共 {len(watch)} 只，其中 {len(positions)} 只有完整持仓")


if __name__ == "__main__":
    main()
