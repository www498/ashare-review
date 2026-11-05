# -*- coding: utf-8 -*-
"""给 docs/demo.html（GitHub Pages 静态体验页）补上「人物性格画像」。

为什么要单独一个脚本
--------------------
demo.html 是从演示账号看板导出的静态快照，将来重新导出会覆盖手工改动。
所以用标记包裹 + 幂等替换：重导之后跑一次就能把画像加回来，不会重复插入。

数据：docs/profile_demo.json（从 users/demo 快照里抽出的 profile 字段，已入库），
     clone 仓库后不依赖本机 users/ 目录也能重跑。
图片：当前型由 persona_art.badge() 以 base64 内嵌，页面零外部依赖；
     16 型画廊用 docs/assets/persona/*.png（相对路径，Pages 与本地都能开）。

跑法：python tools/inject_demo_profile.py
"""
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ashare import web, profile as prof  # noqa: E402

DEMO = os.path.join(ROOT, "docs", "demo.html")
DATA = os.path.join(ROOT, "docs", "profile_demo.json")
SRC_IMG = os.path.join(ROOT, "assets", "persona")
DST_IMG = os.path.join(ROOT, "docs", "assets", "persona")

B_START = "<!-- PROFILE_BLOCK_START -->"
B_END = "<!-- PROFILE_BLOCK_END -->"
C_START = "/* PROFILE_CSS_START */"
C_END = "/* PROFILE_CSS_END */"

CSS = """
.pgal{display:grid;grid-template-columns:repeat(8,1fr);gap:9px;margin-top:12px}
@media(max-width:900px){.pgal{grid-template-columns:repeat(4,1fr)}}
.pgal .pi{border:1px solid #e6ebf3;border-radius:10px;background:#fff;
  padding:8px 4px 9px;text-align:center}
.pgal .pi.on{border-color:#4a6fa5;background:#eef3fa;box-shadow:0 0 0 1px #4a6fa5 inset}
.pgal .pi img{width:100%;max-width:92px;height:92px;object-fit:contain;
  display:block;margin:0 auto}
.pgal .pi b{display:block;font-size:11px;color:#24405f;letter-spacing:1px;margin-top:2px}
.pgal .pi span{font-size:10.5px;color:#7b8595}
"""


def load_ctx():
    if os.path.exists(DATA):
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    # 本机开发时可以直接从演示账号最新快照读，顺手把数据导出一份入库
    import glob
    fps = sorted(glob.glob(os.path.join(ROOT, "users", "demo", "snapshots", "*.json")))
    if not fps:
        sys.exit("缺少 docs/profile_demo.json，也没有 users/demo 快照")
    with open(fps[-1], encoding="utf-8") as f:
        snap = json.load(f)
    ctx = {"profile": snap["profile"]}
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, separators=(",", ":"))
    print("导出", os.path.relpath(DATA, ROOT))
    return ctx


def copy_art():
    """16 张 AI 卡通形象复制到 docs/ 下，Pages 的相对路径才取得不到仓库根目录。"""
    os.makedirs(DST_IMG, exist_ok=True)
    n = 0
    for code in prof.TYPES:
        src = os.path.join(SRC_IMG, code + ".png")
        if not os.path.exists(src):
            continue
        dst = os.path.join(DST_IMG, code + ".png")
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
            n += 1
    return n


def profile_card(ctx):
    """复用产品里同一个渲染函数，保证体验页和真实看板长得一模一样。"""
    h = []
    web._sec_profile(h, ctx, compact=True)
    block = "".join(h)
    # 静态页里 16 型全谱直接展开，不用评委再点一下
    block = block.replace('<details class="fold mb16">',
                          '<details class="fold mb16" open>')
    # 图鉴链接改指向本页下方的画廊
    block = block.replace('href="../../../persona.html" target="_blank"',
                          'href="#persona-gallery"')
    # 演示数据是模拟交割单，别让评委以为是真实账户
    block = block.replace("全部来自交割单真实记录",
                          "演示账号的模拟交割单，产品里换成你自己的即可")
    # 演示页的章节导航要跳到画像卡，先给卡片一个锚点 id
    block = block.replace(
        '<div class="card"><h2>交易行为画像',
        '<div class="card" id="sec-profile"><h2>交易行为画像', 1)
    block = block.replace(
        "<h2>交易行为画像</h2>",
        '<h2>交易行为画像<span style="font-size:11px;color:#8a8f98;'
        'font-weight:400;margin-left:10px">主页常驻 · 不随日期变化</span></h2>', 1)
    return block


def gallery_card(ctx):
    mb = (ctx.get("profile") or {}).get("mbti") or {}
    cur = mb.get("full") or mb.get("code")
    cells = []
    for code, (name, tag) in prof.TYPES.items():
        cls = " on" if code == cur else ""
        cells.append(
            f'<div class="pi{cls}" title="{tag}">'
            f'<img src="assets/persona/{code}.png" alt="{name}" loading="lazy">'
            f'<b>{code}</b><span>{name}</span></div>')
    return (
        '<div class="card" id="persona-gallery"><h2>16 型形象图鉴</h2>'
        '<div class="hint">四维各二选一，共 16 型。同一行色系代表同一种打法：'
        '珊瑚橙抢一波就走、钢蓝下手快也敢拿、沙棕拿得住却先落袋、松绿让时间和利润一起走。'
        f'　当前演示账号是 <b>{cur} {mb.get("name") or ""}</b>（蓝色高亮）。</div>'
        '<div class="pgal">' + "".join(cells) + "</div>"
        '<div class="hint" style="margin:12px 0 0">形象由 AI 绘制，代号、昵称与四维口径'
        '由程序从成交流水计算；图片只负责让类型好认，不参与任何判断。</div></div>')


def main():
    ctx = load_ctx()
    if not ctx.get("profile"):
        sys.exit("profile_demo.json 里没有 profile 字段")
    copied = copy_art()

    with open(DEMO, encoding="utf-8") as f:
        s = f.read()

    block = (B_START + "\n" + profile_card(ctx) + "\n" + gallery_card(ctx) + "\n" + B_END)
    css = C_START + CSS + C_END

    # CSS：幂等替换，没有就补在 </style> 前
    if C_START in s:
        s = re.sub(re.escape(C_START) + r".*?" + re.escape(C_END),
                   lambda _: css, s, count=1, flags=re.S)
    else:
        s = s.replace("</style>", css + "\n</style>", 1)

    # 画像卡：幂等替换，没有就插在 foldbar 之后（持仓之前）
    if B_START in s:
        s = re.sub(re.escape(B_START) + r".*?" + re.escape(B_END),
                   lambda _: block, s, count=1, flags=re.S)
    else:
        m = re.search(r'(<div class="foldbar" id="foldbar">.*?</div>)', s, re.S)
        if not m:
            sys.exit("找不到 foldbar，demo.html 结构变了")
        s = s[:m.end()] + "\n" + block + s[m.end():]

    with open(DEMO, "w", encoding="utf-8") as f:
        f.write(s)
    print("注入完成", os.path.relpath(DEMO, ROOT), len(s), "字符；复制图片", copied, "张")


if __name__ == "__main__":
    main()
