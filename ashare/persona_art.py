# -*- coding: utf-8 -*-
"""给交易人格配一个卡通形象。

为什么是 16 个
--------------
人格不是四选一，是四个维度各二选一，共 2^4 = 16 种组合。
只画 4 张图会让「节奏 × 盈亏」之外的归因、持仓两个维度完全看不见，
等于把四维人格压缩成二维——这正是上一版最大的问题。

形象参照 MBTI 十六型的卡通表达方式：圆头、简笔五官、粗描边、平涂纯色，
用姿态和道具表达性格，而不是靠一张脸。四个色系对应四组打法：

    珊瑚橙  F+C  抢一波就走
    钢蓝    F+R  下手快也敢拿
    沙棕    S+C  拿得住却先落袋
    松绿    S+R  让时间和利润一起走

图片内嵌策略
------------
单文件看板要求零外部依赖，所以 PNG 走 base64 内嵌。
但只嵌当前那一个型（约 25KB），不是 16 个全嵌——
页面上永远只显示自己的形象，全嵌会让 HTML 多 400KB。
图片缺失时回落到手绘 SVG，保证没有素材也能正常显示。
"""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "assets", "persona")
_IMG_CACHE = {}

# 四组色系，按（节奏, 盈亏）分。和 profile.TYPES 的注释分组一致。
TONE = {
    "FC": ("#f5b99b", "#d9613a"),
    "FR": ("#a8c4e8", "#3d6aa8"),
    "SC": ("#d9c39c", "#8a6a3c"),
    "SR": ("#9ed4cd", "#2c7d76"),
}
FALLBACK = ("#c3ccd8", "#7d8797")


def _tone(code):
    """从代号推色系：只看节奏（F/S）和盈亏（C/R）两个字母。

    不能按位置取——缺维度时代号会缩短（如缺归因的 FCK），
    第 3 位就不再是盈亏维度了。
    """
    code = code or ""
    pace = "F" if "F" in code else ("S" if "S" in code else "")
    pnl = "C" if "C" in code else ("R" if "R" in code else "")
    return TONE.get(pace + pnl, FALLBACK)


def badge(code, name="", size=84):
    """返回形象 HTML。优先 AI 生成的 PNG（按代号 > 按旧名），否则手绘 SVG。"""
    for key in (code, name):
        if not key:
            continue
        fp = os.path.join(IMG_DIR, f"{key}.png")
        if os.path.exists(fp):
            if fp not in _IMG_CACHE:
                with open(fp, "rb") as f:
                    _IMG_CACHE[fp] = base64.b64encode(f.read()).decode()
            return (f'<img src="data:image/png;base64,{_IMG_CACHE[fp]}" '
                    f'width="{size}" height="{size}" alt="{name or code}" '
                    f'style="display:block;margin:0 auto 6px">')
    return _svg(code, name, size)


def _svg(code, name="", size=84):
    """回退用的矢量形象：卡通头 + 两个维度标记。

    没有 AI 素材时也要能区分 16 个型，所以道具不是装饰：
        归因 B=田字格（跟着板块排列）  A=星芒（独立发光）
        持仓 K=一个大圆（压一处）      D=三个小圆（摊开）
        盈亏 C=水平围巾（收口）        R=上扬围巾（放出去）
    """
    c1, c2 = _tone(code)
    uid = abs(hash(code or name or "x")) % 9999
    left = _MARK_B if "B" in (code or "") else _MARK_A
    right = _MARK_K if "K" in (code or "") else _MARK_D
    scarf = _SCARF_C if "C" in (code or "") else _SCARF_R

    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 120 120" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{name or code}">'
        f'<defs><linearGradient id="pg{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
        f'</linearGradient></defs>'
        f'<rect width="120" height="120" rx="18" fill="url(#pg{uid})"/>'
        # 头
        '<circle cx="60" cy="49" r="21" fill="#ffffff" opacity=".97"/>'
        '<circle cx="53" cy="46" r="2.5" fill="#2b3a4a"/>'
        '<circle cx="67" cy="46" r="2.5" fill="#2b3a4a"/>'
        '<path d="M53 55 q7 6 14 0" fill="none" stroke="#2b3a4a" stroke-width="2.4" '
        'stroke-linecap="round"/>'
        # 肩
        '<path d="M36 96 q24 -20 48 0 z" fill="#ffffff" opacity=".85"/>'
        + scarf + left + right + '</svg>'
    )


# 归因：B 是整齐的小格子（板块），A 是一颗星（自己发光）
_MARK_B = ('<g opacity=".9"><rect x="34" y="74" width="7" height="7" rx="1.6" fill="#fff"/>'
           '<rect x="43" y="74" width="7" height="7" rx="1.6" fill="#fff" opacity=".55"/>'
           '<rect x="34" y="83" width="7" height="7" rx="1.6" fill="#fff" opacity=".55"/>'
           '<rect x="43" y="83" width="7" height="7" rx="1.6" fill="#fff"/></g>')
_MARK_A = ('<path d="M40 76 L43 84 L51 87 L43 90 L40 98 L37 90 L29 87 L37 84 Z" '
           'fill="#fff" opacity=".9"/>')

# 持仓：K 一个大圆，D 三个小圆
_MARK_K = '<circle cx="85" cy="86" r="8" fill="#fff" opacity=".9"/>'
_MARK_D = ('<g fill="#fff" opacity=".85"><circle cx="78" cy="80" r="4.6"/>'
           '<circle cx="90" cy="82" r="4.6" opacity=".7"/>'
           '<circle cx="84" cy="92" r="4.6" opacity=".85"/></g>')

# 盈亏：C 围巾平收，R 围巾上扬
_SCARF_C = ('<path d="M46 68 q14 7 28 0 q-2 6 -14 6 q-12 0 -14 -6 z" '
            'fill="#ffffff" opacity=".9"/>')
_SCARF_R = ('<path d="M46 68 q14 7 28 0 q6 -6 12 -12 q-3 9 -8 16 q-16 6 -32 0 z" '
            'fill="#ffffff" opacity=".85"/>')
