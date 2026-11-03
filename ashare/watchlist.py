# -*- coding: utf-8 -*-
"""
自选股导入。

支持把东方财富的持仓/自选直接粘进来，格式越乱越好用：
    600519                      纯代码
    600519,贵州茅台              逗号分隔
    600519 贵州茅台              空格/Tab 分隔
    证券代码  证券名称  ...       表头行自动跳过
    600519.SH / SH600519 / sh600519

只保留沪A（60/68 开头），其余自动忽略并报告。
文件不存在时回退到 config.WATCHLIST。

用法：
    python -m ashare.watchlist --check     查看解析结果
    python -m ashare.watchlist --init      生成模板文件
"""
import argparse
import os
import re

from . import config as C
from .data import ROOT, is_a_share

FILES = [os.path.join(ROOT, "watchlist.txt"), os.path.join(ROOT, "watchlist.csv")]
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")   # 先抓 6 位数字，再用 is_a_share 过滤
NAME_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9*]*")


def _pick_file():
    for f in FILES:
        if os.path.exists(f):
            return f
    return None


def parse_line(line):
    """从一行任意格式的文本里抽出 (代码, 名称, 数量, 成本价)。支持沪深京全部 A 股。
    数量与成本可选：只写代码就是「关注」，写了才是「持仓」。"""
    s = line.strip().lstrip("\ufeff")
    if not s or s.startswith("#"):
        return None
    m = CODE_RE.search(s)
    if not m:
        return None
    code = m.group(1)
    if not is_a_share(code):
        return None          # 非 A 股个股：基金、可转债、B 股一律忽略

    # 先按分隔符切成列，能拿到 4 列就直接按列取值（东财持仓粘贴走这条）
    parts = [p.strip() for p in re.split(r"[,;\t]+", s) if p.strip()]
    shares = cost = None
    if (len(parts) >= 4
            and re.fullmatch(r"\d+(?:\.0+)?", parts[2] or "")
            and re.fullmatch(r"\d+(?:\.\d+)?", parts[3] or "")):
        try:
            shares, cost = float(parts[2]), float(parts[3])
        except ValueError:
            shares = cost = None

    rest = s[:m.start()] + " " + s[m.end():]
    cands = [n for n in NAME_RE.findall(rest)
             if not n.isdigit() and len(n) >= 2
             and n not in ("证券名称", "股票名称", "名称", "证券简称", "股票简称",
                           "代码", "证券代码", "SH", "SZ", "BJ")]
    cjk = [n for n in cands if re.search(r"[\u4e00-\u9fa5]", n)]
    name = cjk[0] if cjk else ""
    return code, name, shares, cost


def add_codes(codes):
    """往 watchlist.txt 追加自选股。codes 可为 ['600519', '600519,贵州茅台'] 等形式。
    返回 (added, skipped_existing, invalid)。保留原文件的注释与排版。"""
    fp = _pick_file() or FILES[0]
    existing, _, _ = load()
    added, dup, bad = [], [], []
    lines = []
    for raw in codes:
        r = parse_line(str(raw))
        if not r:
            bad.append(str(raw))
            continue
        code, name = r[0], r[1]
        if code in existing:
            dup.append(code)
            continue
        if code in added:
            continue
        added.append(code)
        lines.append(f"{code},{name}" if name else code)
    if lines:
        need_nl = False
        if os.path.exists(fp):
            with open(fp, encoding="utf-8-sig", errors="ignore") as f:
                need_nl = not f.read().endswith("\n")
        with open(fp, "a", encoding="utf-8") as f:
            if need_nl:
                f.write("\n")
            f.write("\n".join(lines) + "\n")
    return added, dup, bad


def remove_codes(codes):
    """从 watchlist.txt 删除指定代码。注释行与其他标的原样保留。
    返回 (removed, not_found)。"""
    fp = _pick_file()
    want = set()
    for c in codes:
        m = CODE_RE.search(str(c))
        if m:
            want.add(m.group(1))
    if not fp or not want:
        return [], sorted(want)
    with open(fp, encoding="utf-8-sig", errors="ignore") as f:
        src = f.readlines()
    kept, removed = [], []
    for line in src:
        s = line.strip()
        if s and not s.startswith("#"):
            r = parse_line(line)
            if r and r[0] in want:
                removed.append(r[0])
                continue
        kept.append(line)
    if removed:
        with open(fp, "w", encoding="utf-8") as f:
            f.writelines(kept)
    return removed, sorted(want - set(removed))


def load(verbose=False):
    """返回 (watchlist, positions, meta)。
    watchlist: {code: name}；positions: {code: {shares, cost}}，只含填了数量的。"""
    fp = _pick_file()
    if not fp:
        return dict(C.WATCHLIST), {}, {"source": "config.py", "file": None,
                                       "skipped": 0, "unnamed": 0, "pos": 0}
    mapping, positions, skipped, unnamed = {}, {}, 0, 0
    with open(fp, encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            r = parse_line(line)
            if not r:
                if line.strip() and CODE_RE.search(line):
                    skipped += 1
                continue
            code, name, shares, cost = r
            if not name:
                unnamed += 1
                name = code
            mapping[code] = name
            if shares and cost:
                positions[code] = {"shares": shares, "cost": cost}
    if not mapping:
        return dict(C.WATCHLIST), {}, {"source": "config.py（文件解析为空）", "file": fp,
                                       "skipped": skipped, "unnamed": unnamed, "pos": 0}
    # 再合并券商/行情软件导出的持仓表（positions.csv / 持仓.csv ...），持仓数据以此为准
    merged_note = None
    try:
        from . import positions as pos_mod
        pw, pp, pmeta = pos_mod.load()
        if pw:
            for code, nm in pw.items():
                if nm and nm != code:
                    mapping[code] = nm
                else:
                    mapping.setdefault(code, code)
            positions.update(pp)
            merged_note = pmeta.get("file")
    except Exception:
        pass

    if verbose:
        extra = f"，其中 {len(positions)} 只有持仓" if positions else ""
        src = os.path.basename(fp) + (f" + {merged_note}" if merged_note else "")
        print(f"从 {src} 读取 {len(mapping)} 只 A 股（忽略 {skipped} 条非个股{extra}）")
    return mapping, positions, {"source": os.path.basename(fp), "file": fp,
                                "skipped": skipped, "unnamed": unnamed,
                                "pos": len(positions), "merged": merged_note}


def fill_names(watch, quotes):
    """把纯代码的占位名换成真实名称"""
    out = {}
    for code, name in watch.items():
        if name == code:
            q = quotes.get(code) or {}
            out[code] = q.get("name") or name
        else:
            out[code] = name
    return out


def portfolio(positions, quotes, names=None):
    """持仓核算：市值、浮盈、今日盈亏、仓位占比。只对填了数量+成本的标的生效。"""
    names = names or {}
    rows = []
    for code, p in positions.items():
        q = quotes.get(code) or {}
        px, prev = q.get("price"), q.get("prev_close")
        if not px:
            continue
        shares = float(p["shares"])
        cost_px = float(p["cost"])
        mv = px * shares
        cost = cost_px * shares
        pnl = mv - cost
        today = (px - prev) * shares if prev else 0.0
        rows.append({
            "code": code, "name": names.get(code) or q.get("name", code),
            "shares": shares, "cost": cost_px, "price": px,
            "mv": mv, "pnl": pnl,
            "pnl_pct": (pnl / cost * 100) if cost else None,
            "today": today,
            "today_pct": q.get("pct"),
            "weight": None,
        })
    if not rows:
        return None
    total_mv = sum(r["mv"] for r in rows)
    total_cost = sum(r["shares"] * r["cost"] for r in rows)
    total_today = sum(r["today"] for r in rows)
    for r in rows:
        r["weight"] = r["mv"] / total_mv * 100 if total_mv else None
    rows.sort(key=lambda x: -x["mv"])
    return {
        "rows": rows,
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_pnl": total_mv - total_cost,
        "total_pnl_pct": ((total_mv - total_cost) / total_cost * 100) if total_cost else None,
        "total_today": total_today,
        "total_today_pct": (total_today / (total_mv - total_today) * 100)
        if (total_mv - total_today) else None,
    }


TEMPLATE = """# 自选股清单 —— 直接把东方财富的持仓/自选粘到下面就行，格式不限
# 支持：纯代码、代码+名称、Tab 分隔、带 .SH/.SZ 后缀；沪深京 A 股自动识别
# 想算盈亏就补上「数量,成本价」两列，不填就只做关注
# 以 # 开头的行为注释，会被忽略

600519,贵州茅台,100,1392.05
601318,中国平安
600036,招商银行
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="生成模板文件")
    ap.add_argument("--check", action="store_true", help="检查解析结果")
    a = ap.parse_args()

    if a.init:
        target = FILES[0]
        if os.path.exists(target):
            print(f"{target} 已存在，不覆盖")
        else:
            with open(target, "w", encoding="utf-8") as f:
                f.write(TEMPLATE)
            print(f"已生成模板：{target}")
        return

    watch, positions, meta = load(verbose=True)
    print(f"来源：{meta['source']}")
    for code, name in watch.items():
        p = positions.get(code)
        tag = f"　持仓 {p['shares']:.0f} 股 @ {p['cost']:.3f}" if p else ""
        print(f"  {code}  {name}{tag}")
    print(f"共 {len(watch)} 只，{len(positions)} 只有持仓")


if __name__ == "__main__":
    main()
