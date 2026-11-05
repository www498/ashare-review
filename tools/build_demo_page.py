# -*- coding: utf-8 -*-
"""把某天的单日看板导出成 GitHub Pages 用的静态体验页 docs/demo.html。

处理三件事：
1. 加顶部横幅，说明这是演示账号、行情是真实收盘、交易是模拟交割单；
2. 把画像数据同步到 docs/profile_demo.json（体验页的画像卡从它读）；
3. 调用 inject_demo_profile 注入画像卡与 16 型图鉴（幂等，可重复跑）。

跑法：python tools/build_demo_page.py 2026-11-04 pm demo
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.inject_demo_profile import main as inject_main  # noqa: E402

BANNER = (
    '<div style="position:sticky;top:0;z-index:99;background:#1a3a6b;color:#dbe7fa;'
    'font:13px/1.7 -apple-system,Segoe UI,Microsoft YaHei,sans-serif;padding:9px 18px;'
    'text-align:center;letter-spacing:.3px">'
    '这是<b style="color:#fff">演示账号</b>的静态看板（行情为真实收盘数据，'
    '交易为演示用模拟交割单）　·　含人物性格画像与 16 型图鉴　·　'
    '项目仓库 <b style="color:#fff">github.com/www498/ashare-review</b>　·　'
    '本地运行可导入自己的交割单</div>'
)


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-11-04"
    session = sys.argv[2] if len(sys.argv) > 2 else "pm"
    uid = sys.argv[3] if len(sys.argv) > 3 else "demo"

    base = os.path.join(ROOT, "users", uid)
    src = os.path.join(base, "reports",
                       f"dashboard_{day.replace('-', '')}_{session}.html")
    if not os.path.exists(src):
        sys.exit(f"找不到 {src}，先跑 tools/rerender_demo.py")
    with open(src, encoding="utf-8") as f:
        html = f.read()

    # 顶部横幅：插在 body 之后、wrap 之前
    if "<body>" not in html:
        sys.exit("看板结构变了：找不到 <body>")
    html = html.replace("<body>", "<body>" + BANNER, 1)
    html = html.replace("<title>", "<title>复盘台 · 演示账号 ", 1)

    out = os.path.join(ROOT, "docs", "demo.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"写出 {os.path.relpath(out, ROOT)}  {len(html) // 1024}KB")

    # 画像数据同步：体验页的画像卡从这份 json 读，不依赖 users/ 目录
    snap = os.path.join(base, "snapshots", day.replace("-", "") + f"_{session}.json")
    with open(snap, encoding="utf-8") as f:
        ctx = json.load(f)
    prof = ctx.get("profile")
    if not prof:
        sys.exit("快照里没有 profile，先跑 tools/refresh_profile.py")
    with open(os.path.join(ROOT, "docs", "profile_demo.json"), "w",
              encoding="utf-8") as f:
        json.dump({"profile": prof}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"同步画像 {prof['mbti']['code']} {prof['mbti']['name']}，"
          f"建议 {len(prof.get('playbook') or [])} 条")

    inject_main()


if __name__ == "__main__":
    main()
