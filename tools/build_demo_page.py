# -*- coding: utf-8 -*-
"""把某天的单日看板导出成静态演示页 docs/demo.html。

做四件事：
1. 注入「答辩视图」：首屏价值主张、关键数字、章节导航、卡片层级、投屏/打印样式；
2. 加顶部横幅，说明这是演示账号、行情是真实收盘、交易是模拟交割单；
3. 同步画像数据到 docs/profile_demo.json；
4. 调用 inject_demo_profile 注入画像卡与 16 型图鉴（幂等，可重复跑）。

只改演示页，不动产品看板本身；样式增强全部走 .hero/.jump 等新类名，
不和 ashare/web.py 的 CSS 打架。

跑法：python tools/build_demo_page.py 2026-11-04 pm demo
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.inject_demo_profile import main as inject_main  # noqa: E402

BANNER = (
    '<div class="banner" style="background:#122a52;color:#c8d8f0;'
    'font:12.5px/1.7 -apple-system,Segoe UI,Microsoft YaHei,sans-serif;padding:9px 18px;'
    'text-align:center;letter-spacing:.3px">'
    '演示账号静态看板　·　行情为真实收盘数据，交易为演示用模拟交割单　·　'
    '含人物性格画像与 16 型图鉴　·　本地运行可导入自己的交割单</div>'
)

CSS = """
/* ---- 答辩视图：只作用于 docs/demo.html ---- */
html,body{overflow-x:hidden}
body{background:#f4f6f9}
.banner{white-space:normal}
.wrap{max-width:1100px}
.hd{display:none}
.hero{position:relative;overflow:hidden;margin:18px 0 0;padding:42px 44px 34px;
  border-radius:16px;color:#fff;
  background:linear-gradient(132deg,#0a1a37 0%,#14325c 58%,#1c4271 100%)}
.hero:after{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);
  background-size:46px 46px}
.hero>*{position:relative;z-index:1}
.hero .htag{font-size:12px;letter-spacing:1.5px;color:#8fb0dd}
.hero h1{margin:10px 0 6px;font-size:42px;font-weight:700;letter-spacing:3px}
.hero .sub{font-size:17px;color:#cddcf2;letter-spacing:.5px}
.hero .lead{margin-top:14px;font-size:15px;line-height:2;color:#a9c1e2;max-width:720px}
.hero .nums{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;
  margin-top:26px;padding-top:20px;border-top:1px solid rgba(255,255,255,.16)}
.hero .nums b{display:block;font-size:30px;font-weight:700;
  font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.hero .nums span{font-size:12px;color:#93aed3}
.hero .cta{margin-top:24px;display:flex;gap:12px;flex-wrap:wrap}
.hero .cta a{display:inline-block;padding:9px 20px;border-radius:8px;font-size:13.5px;
  text-decoration:none;background:#fff;color:#14294a;font-weight:600}
.hero .cta a.ghost{background:transparent;color:#cfe0f6;border:1px solid rgba(255,255,255,.35)}

.jump{position:sticky;top:0;z-index:96;display:flex;gap:2px;overflow-x:auto;
  margin:0 -20px 16px;padding:0 20px;background:rgba(255,255,255,.95);
  border-bottom:1px solid #e6eaf0;backdrop-filter:blur(8px)}
.jump a{padding:11px 13px;font-size:12.5px;color:#5f6b7a;text-decoration:none;
  border-bottom:2px solid transparent;white-space:nowrap}
.jump a:hover{color:#1a3a6b;border-bottom-color:#b9c9e0}

.card{border-color:#e8ecf2;box-shadow:0 1px 2px rgba(16,24,40,.04),
  0 10px 26px rgba(16,24,40,.045)}
.card>h2{font-size:15px;letter-spacing:.2px}
.kpi{border-color:#e8ecf2;box-shadow:0 1px 2px rgba(16,24,40,.035)}
.card:hover{box-shadow:0 2px 4px rgba(16,24,40,.05),0 14px 34px rgba(16,24,40,.07)}
.card,.kpi{transition:box-shadow .2s ease}

@media(max-width:860px){
  .banner{font-size:11.5px;line-height:1.6;padding:8px 12px}
  .hero{padding:30px 22px 26px;border-radius:12px}
  .hero .lead,.hero .sub,.hero .htag{max-width:100%}
  .hero h1{font-size:30px;letter-spacing:1px}
  .hero .sub{font-size:14px}
  .hero .lead{font-size:13px;line-height:1.9}
  .hero .nums{grid-template-columns:repeat(2,1fr);gap:14px}
  .hero .nums b{font-size:24px}
  .jump{margin:0 -14px 14px;padding:0 14px}
  .card{overflow-x:auto;padding:14px 13px}
  table{font-size:11.5px}
}

@media print{
  body{background:#fff;padding:0}
  .banner,.jump,.hero .cta,.foldbar{display:none!important}
  .hero{background:#fff!important;color:#111;border:1px solid #ddd;padding:18px 0}
  .hero:after{display:none}
  .hero .htag,.hero .sub,.hero .lead,.hero .nums span{color:#333}
  .hero .nums b{color:#111}
  .hero .nums{border-top-color:#ddd}
  .card{break-inside:avoid;box-shadow:none;border-color:#ddd}
}
"""

# 章节锚点：给卡片加 id，导航和 CTA 才能跳转
ANCHORS = [
    ('<div class="card"><h2>持仓', '<div class="card" id="sec-pos"><h2>持仓'),
    ('<div class="card"><h2>今日交易复盘',
     '<div class="card" id="sec-journal"><h2>今日交易复盘'),
    ('<div class="card"><h2>自选股', '<div class="card" id="sec-watch"><h2>自选股'),
    ('<div class="card"><h2>市场概况', '<div class="card" id="sec-market"><h2>市场概况'),
]


def hero(ctx):
    p = ctx.get("profile") or {}
    n_closed = (p.get("core") or {}).get("n_closed") or 0
    n_today = (ctx.get("journal") or {}).get("summary", {}).get("n") or 0
    uni = ctx.get("n_universe") or 0
    t = ctx.get("temperature") or {}
    tag = f'{ctx.get("date", "")} 收盘'
    if t:
        tag += f'　·　{t.get("band", "")} {t.get("total", 0):.1f}'
    return (
        '<section class="hero" id="top">'
        f'<div class="htag">{tag}　·　演示账号</div>'
        '<h1>复盘台</h1>'
        '<div class="sub">A 股市场复盘 × 个人交易画像</div>'
        '<div class="lead">收盘后你看到的是 5577 只票的涨跌。'
        '我们回答的是：这些数字和你的账户、和你的每一笔操作，有什么关系。</div>'
        '<div class="nums">'
        f'<div><b>{uni:,}</b><span>只个股覆盖（沪深京）</span></div>'
        f'<div><b>{n_closed}</b><span>笔成交 FIFO 配对</span></div>'
        f'<div><b>{n_today}</b><span>手当日操作逐笔复盘</span></div>'
        '<div><b>16</b><span>型交易人格</span></div>'
        '</div>'
        '<div class="cta"><a href="#sec-profile">看交易画像</a>'
        '<a class="ghost" href="#sec-journal">看逐笔复盘</a></div>'
        '</section>'
    )


NAV = (
    '<nav class="jump">'
    '<a href="#top">概览</a>'
    '<a href="#sec-profile">交易画像</a>'
    '<a href="#sec-pos">持仓</a>'
    '<a href="#sec-journal">逐笔复盘</a>'
    '<a href="#sec-watch">自选股</a>'
    '<a href="#sec-market">市场</a>'
    '</nav>'
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

    snap = os.path.join(base, "snapshots", day.replace("-", "") + f"_{session}.json")
    with open(snap, encoding="utf-8") as f:
        ctx = json.load(f)

    if "<body>" not in html:
        sys.exit("看板结构变了：找不到 <body>")

    # 1) 横幅 + 首屏 + 导航
    html = html.replace("<body>", "<body>" + BANNER, 1)
    html = html.replace("<div class='wrap'>",
                        "<div class='wrap'>" + hero(ctx) + NAV, 1)

    # 2) 章节锚点
    for old, new in ANCHORS:
        html = html.replace(old, new, 1)

    # 3) 答辩视图样式
    html = html.replace("</style>", CSS + "</style>", 1)
    # 手机浏览器默认按 980px 布局再缩放，看起来像「右侧被裁」；补 viewport 才会按设备宽度排版
    html = html.replace("<meta charset=\"utf-8\">",
                        "<meta charset=\"utf-8\"><meta name=\"viewport\" "
                        "content=\"width=device-width,initial-scale=1\">", 1)
    html = html.replace("<title>", "<title>复盘台 · 11-04 案例 ", 1)

    out = os.path.join(ROOT, "docs", "demo.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"写出 {os.path.relpath(out, ROOT)}  {len(html) // 1024}KB")

    # 4) 画像数据同步：体验页的画像卡从这份 json 读，不依赖 users/ 目录
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
