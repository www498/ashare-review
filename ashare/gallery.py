# -*- coding: utf-8 -*-
"""16 型人格图鉴：把 16 个形象并排铺开。

为什么单独一页
--------------
看板要保证「单文件、零依赖」，只能内嵌自己那一个形象。
但 16 型人格的价值在于**坐标系**——只看自己那一格，无法判断
「我这样算正常吗」。图鉴页解决这个问题：16 个形象按色系铺开，
一眼能看出自己站在哪一组、相邻的型差在哪两个字母。

图片走相对路径引用 assets/persona，不内嵌——
这一页本来就要跟着仓库走，不是拷走单文件看的那种场景。
"""
import html
import os

from . import profile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "persona.html")

# 四个色系分组，和 profile.TYPES 的注释分组一一对应
GROUPS = [
    ("FC", "抢一波就走", "出手快，赚到心理价立刻落袋。强项是效率，风险是永远吃不到主升段。",
     ("FBCK", "FBCD", "FACK", "FACD")),
    ("FR", "下手快，也敢拿", "出手快但不急着卖。强项是能咬住肉，风险是回撤时容易把利润还回去。",
     ("FBRK", "FBRD", "FARK", "FARD")),
    ("SC", "拿得住，却先落袋", "能守住一个方向，但涨一点就想换钱。强项是耐心，风险是利润被提前截断。",
     ("SBCK", "SBCD", "SACK", "SACD")),
    ("SR", "让时间和利润一起走", "拿得久也让利润跑。强项是复利，风险是判断错了也不肯走。",
     ("SBRK", "SBRD", "SARK", "SARD")),
]

CSS = """
:root{--ink:#1f2328;--mute:#6b7686;--line:#e8eef6;--bg:#f7f9fc}
*{box-sizing:border-box}
body{margin:0;background:#f4f6f9;color:var(--ink);
  font:14px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:38px 22px 70px}
h1{font-size:26px;margin:0 0 8px;letter-spacing:-.4px}
.lead{color:var(--mute);font-size:13.5px;line-height:1.9;margin:0 0 6px;max-width:760px}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 30px}
.legend span{font-size:12px;padding:5px 11px;border-radius:999px;background:#fff;
  border:1px solid var(--line);color:#4a5058}
.legend b{color:#243043}
.grp{margin-bottom:26px;background:#fff;border:1px solid var(--line);border-radius:14px;
  padding:18px 20px 20px}
.gh{display:flex;align-items:baseline;gap:12px;margin-bottom:4px}
.gh .dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;transform:translateY(-1px)}
.gh h2{font-size:15.5px;margin:0;font-weight:700;letter-spacing:-.2px}
.gh em{font-style:normal;font-size:11.5px;color:#9aa3b0;letter-spacing:1.4px}
.gd{font-size:12.5px;color:var(--mute);margin:0 0 14px 22px;line-height:1.8}
.row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:820px){.row{grid-template-columns:repeat(2,1fr)}}
.t{background:var(--bg);border:1px solid #eef2f8;border-radius:12px;padding:12px 10px 13px;
  text-align:center;transition:transform .18s ease,box-shadow .18s ease}
.t:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(30,45,70,.08)}
.t img{width:100%;max-width:132px;height:auto;display:block;margin:0 auto 4px}
.t .cd{font-size:13px;font-weight:800;letter-spacing:3px;color:#243043}
.t .nm{font-size:12.5px;color:#3c4043;font-weight:600;margin-top:1px}
.t .tg{font-size:11.5px;color:var(--mute);line-height:1.65;margin-top:5px;min-height:3.3em}
.foot{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);
  font-size:12px;color:#9aa3b0;line-height:1.9}
.foot b{color:#6b7686;font-weight:600}
"""


def _card(code, name, tagline, base):
    img = os.path.join(base, "assets", "persona", f"{code}.png")
    pic = (f'<img src="assets/persona/{code}.png" alt="{html.escape(name)}">'
           if os.path.exists(img) else
           '<div style="height:132px"></div>')
    return (f'<div class="t">{pic}'
            f'<div class="cd">{code}</div>'
            f'<div class="nm">{html.escape(name)}</div>'
            f'<div class="tg">{html.escape(tagline)}</div></div>')


def render():
    from . import persona_art
    h = [f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>16 型交易人格图鉴 · 复盘台</title>'
         f'<style>{CSS}</style></head><body><div class="wrap">']
    h.append('<h1>16 型交易人格</h1>')
    h.append('<p class="lead">四个维度各二选一，共 16 种组合。'
             '和一个 MBTI 代号一样，单个字母没有意义，'
             '有意义的是它在坐标系里的位置——以及相邻那一格只差哪个字母。</p>')
    h.append('<div class="legend">'
             '<span><b>节奏</b>　F 出手快（≤7 天）／S 拿得久</span>'
             '<span><b>归因</b>　B 跟板块／A 走独立</span>'
             '<span><b>盈亏</b>　C 赚了就走／R 赚了能拿</span>'
             '<span><b>持仓</b>　K 押得集中／D 分得开</span></div>')

    for key, title, desc, codes in GROUPS:
        c1, c2 = persona_art.TONE.get(key, ("#c3ccd8", "#7d8797"))
        h.append('<div class="grp">')
        h.append(f'<div class="gh"><span class="dot" style="background:{c2}"></span>'
                 f'<h2>{title}</h2><em>{codes[0][0]}{codes[0][2]}</em></div>')
        h.append(f'<p class="gd">{desc}</p><div class="row">')
        for code in codes:
            nm, tg = profile.TYPES[code]
            h.append(_card(code, nm, tg, ROOT))
        h.append('</div></div>')

    h.append('<div class="foot">'
             '<b>怎么读</b>：先看第一个字母（节奏），再看第三个（盈亏处理），'
             '这两个决定赚钱方式；第二个（归因）和第四个（持仓）决定风险集中在哪里。'
             '同一行四张图共享色系，说明它们在同一战场，差别只在后两个字母。'
             '<br>形象由 AI 生成，性格结论全部来自你自己的交割单统计，不做心理侧写。'
             '</div>')
    h.append('</div></body></html>')
    return "".join(h)


def write(path=None):
    p = path or OUT
    with open(p, "w", encoding="utf-8") as f:
        f.write(render())
    return p
