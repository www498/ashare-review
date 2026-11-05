# -*- coding: utf-8 -*-
"""按历史快照重渲染某一天的看板，不重新联网取行情。

使用场景
--------
改了渲染逻辑（表格列、建议文案、成交时点评分）之后，要把历史某天的报告
按新口径重出一遍。行情、持仓、归因全部沿用当天快照，只有画像与逐笔复盘
用交割单重算——因为这两块的口径变了。

口径保护
--------
默认把交割单截断到报告当天（含），避免用之后的成交影响当天的 FIFO 配对
和「最近卖出」列表。要关闭用 --no-truncate。

跑法：
    python tools/rerender_demo.py 2026-11-04 pm demo
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from ashare import statement as stmt, profile as prof, journal, web  # noqa: E402


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-11-04"
    session = sys.argv[2] if len(sys.argv) > 2 else "pm"
    uid = sys.argv[3] if len(sys.argv) > 3 else "demo"
    truncate = "--no-truncate" not in sys.argv

    base = os.path.join(ROOT, "users", uid)
    snap_fp = os.path.join(base, "snapshots", day.replace("-", "") + f"_{session}.json")
    if not os.path.exists(snap_fp):
        sys.exit(f"找不到快照 {snap_fp}")
    with open(snap_fp, encoding="utf-8") as f:
        ctx = json.load(f)

    stmt_fp = os.path.join(base, "statement.csv")
    if not os.path.exists(stmt_fp):
        sys.exit(f"找不到交割单 {stmt_fp}")
    raw = pd.read_csv(stmt_fp, dtype=str, encoding="utf-8-sig")
    d, col = stmt.prepare(raw)

    if truncate and col.get("date"):
        before = len(d)
        d = d[pd.to_datetime(d[col["date"]], errors="coerce") <= pd.Timestamp(day)]
        print(f"交割单截断到 {day}：{before} → {len(d)} 行")

    positions = ctx.get("positions") or {}
    quotes = ctx.get("watch_quotes") or {}

    p = prof.build(d, col, positions=positions, quotes=quotes)
    if not p:
        sys.exit("画像构建失败：交割单里没有可配对的成交")
    p["mbti"] = prof.mbti(p.get("core") or {}, p.get("per_stock"),
                          movers=ctx.get("movers"), positions=positions, quotes=quotes)
    ctx["profile"] = p

    jr = journal.build(d, col, trades=p["trades"], day=day)
    if jr:
        ctx["journal"] = jr
    sr = journal.review_sells(d, col, trades=p["trades"], days=25, limit=8)
    if sr:
        ctx["sell_review"] = sr

    # 回写快照：主页、截图工具、后续重渲染都从快照取数，
    # 只写 HTML 不回写会造成「页面是新的、快照是旧的」。
    if "--no-write" not in sys.argv:
        with open(snap_fp, "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False, separators=(",", ":"))

    html = web.render_html(ctx)
    out = os.path.join(base, "reports", f"dashboard_{day.replace('-', '')}_{session}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"写出 {os.path.relpath(out, ROOT)}  {len(html) // 1024}KB")
    if jr:
        print(f"逐笔 {jr['summary']['n']} 手，合理性中位数 {jr['summary']['median_rate']}；"
              f"{jr['summary']['bad']} 手偏弱")
    if sr:
        print(f"卖出回看 {len(sr)} 笔：" + "、".join(
            f"{x['name']}{x['verdict']}" for x in sr[:5]))
    print(f"画像 {p['mbti']['code']} {p['mbti']['name']}；建议 {len(p['playbook'])} 条")


if __name__ == "__main__":
    main()
