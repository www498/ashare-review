# -*- coding: utf-8 -*-
"""给某天的快照补齐全部自选股的未来 5 日波动区间。

为什么单独跑：HAR-RV 每只票要重训 500 日窗口、每 20 日滚动，单只约 35 秒，
11 只就是 6 分钟，不能塞进复盘主流程。单独跑完写回快照，重渲染直接读。

跑法（依赖 baostock，用装了它的解释器）：
    python tools/fill_forecast.py demo 2026-11-04 pm
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ashare import forecast  # noqa: E402


def sym_of(code):
    c = str(code)
    if c[:1] == "6":
        return "sh" + c
    if c[:1] in "48":
        return "bj" + c
    return "sz" + c


def main():
    uid = sys.argv[1] if len(sys.argv) > 1 else "demo"
    day = sys.argv[2] if len(sys.argv) > 2 else "2026-11-04"
    session = sys.argv[3] if len(sys.argv) > 3 else "pm"

    fp = os.path.join(ROOT, "users", uid, "snapshots",
                      day.replace("-", "") + f"_{session}.json")
    with open(fp, encoding="utf-8") as f:
        ctx = json.load(f)

    targets = ctx.get("anomalies") or []
    print(f"{len(targets)} 只自选股，开始逐个重训（单只约 35 秒）", flush=True)
    out, fail = [], []
    for i, a in enumerate(targets, 1):
        sym = sym_of(a["code"])
        r, err = None, ""
        try:
            r = forecast.analyze_symbol(sym, a["name"], price=a.get("price"))
        except Exception as e:
            err = f"（{type(e).__name__}: {str(e)[:40]}）"
        if r:
            out.append(r)
            print(f"  [{i}/{len(targets)}] {a['name']:<6} 区间 {r['lo']:.2f}~{r['hi']:.2f} "
                  f"覆盖 {r['coverage']:.0%} R² {r['r2']:.3f}", flush=True)
        else:
            fail.append(a["name"])
            print(f"  [{i}/{len(targets)}] {a['name']:<6} 跳过{err}", flush=True)

    if not out:
        sys.exit("全部失败，快照未改动")
    ctx["forecast"] = out
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, separators=(",", ":"))

    cov = sorted(x["coverage"] for x in out)
    r2 = sorted(x["r2"] for x in out)
    print(f"\n写入 {len(out)} 只，失败 {len(fail)} 只")
    print(f"覆盖率：中位数 {cov[len(cov) // 2]:.0%}，范围 {cov[0]:.0%}~{cov[-1]:.0%}（目标 80%）")
    print(f"R²：中位数 {r2[len(r2) // 2]:.3f}，为负 {sum(1 for x in r2 if x <= 0)} 只")
    print("覆盖率达标说明区间宽度可信；R² 低说明只能当包络，不能当方向。")


if __name__ == "__main__":
    main()
