# -*- coding: utf-8 -*-
"""按最新口径重算用户所有快照里的「交易行为画像」。

为什么需要：画像里的建议文案、四维标签、AI 标注都在代码里，
快照里存的还是旧结构。主页从最新快照读画像，不重算就会显示旧文案。

只改快照里的 profile 字段，行情、持仓、归因、逐笔复盘全部不动。
跑法：python tools/refresh_profile.py demo
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from ashare import statement as stmt, profile as prof  # noqa: E402


def main():
    uid = sys.argv[1] if len(sys.argv) > 1 else "demo"
    base = os.path.join(ROOT, "users", uid)
    files = sorted(glob.glob(os.path.join(base, "snapshots", "*.json")))
    if not files:
        sys.exit(f"{base}/snapshots 下没有快照")

    stmt_fp = os.path.join(base, "statement.csv")
    raw = pd.read_csv(stmt_fp, dtype=str, encoding="utf-8-sig")
    d, col = stmt.prepare(raw)

    for fp in files:
        with open(fp, encoding="utf-8") as f:
            ctx = json.load(f)
        day = ctx.get("date") or ""
        dd = d
        if day and col.get("date"):
            # 每个快照只看它当天及之前的成交，避免未来数据污染
            dd = d[pd.to_datetime(d[col["date"]], errors="coerce") <= pd.Timestamp(day)]
        positions = ctx.get("positions") or {}
        quotes = ctx.get("watch_quotes") or {}
        p = prof.build(dd, col, positions=positions, quotes=quotes)
        if not p:
            print(f"  跳过 {os.path.basename(fp)}：没有可配对的成交")
            continue
        p["mbti"] = prof.mbti(p.get("core") or {}, p.get("per_stock"),
                              movers=ctx.get("movers"), positions=positions, quotes=quotes)
        ctx["profile"] = p
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  {os.path.basename(fp)}：{p['mbti']['code']} {p['mbti']['name']}，"
              f"建议 {len(p['playbook'])} 条")


if __name__ == "__main__":
    main()
