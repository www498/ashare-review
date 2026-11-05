# -*- coding: utf-8 -*-
"""给没有「成交时间」列的交割单补时间（只补指定日期）。

很多券商的导出只有日期、没有时分，导致「10:35 卖得早不早」这类判断做不了。
这里用当日真实分时反推：只有在分时里出现过该成交价（偏差 ≤0.3%）的分钟
才会被选中，所以补出来的时间与价格自洽，不是随手编一个。

跑法：
    python tools/fill_trade_time.py users/demo/statement.csv 2026-11-04
"""

import csv
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ashare import intraday  # noqa: E402


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "users", "demo", "statement.csv")
    day = sys.argv[2] if len(sys.argv) > 2 else "2026-11-04"
    if not os.path.exists(path):
        sys.exit(f"找不到 {path}")

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []
    if not rows:
        sys.exit("交割单是空的")
    if "成交时间" not in fields:
        at = fields.index("成交均价") + 1 if "成交均价" in fields else len(fields)
        fields.insert(at, "成交时间")

    todo = [r for r in rows if str(r.get("发生日期", "")).strip()[:10] == day]
    print(f"{os.path.basename(path)}：{day} 共 {len(todo)} 笔")
    filled = miss = 0
    for r in todo:
        if str(r.get("成交时间") or "").strip():
            continue
        code = str(r.get("证券代码", "")).strip()
        try:
            px = float(r.get("成交均价") or 0)
        except ValueError:
            px = 0
        rows_k = intraday.fetch_day(code, day)
        t = intraday.match_time(rows_k, px) if rows_k else None
        if t:
            r["成交时间"] = t
            filled += 1
            print(f"  {r.get('证券名称',''):<6} {px:>8.2f} → {t}")
        else:
            r["成交时间"] = ""
            miss += 1
            print(f"  {r.get('证券名称',''):<6} {px:>8.2f} → 无匹配（保持空）")

    if filled == 0:
        print("没有可补的时间，文件未改动")
        return

    shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"写入 {filled} 笔，未匹配 {miss} 笔；原文件备份为 {os.path.basename(path)}.bak")


if __name__ == "__main__":
    main()
