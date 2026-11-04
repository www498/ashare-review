# -*- coding: utf-8 -*-
"""给交易人格画一个徽章。

为什么用 SVG 而不是图片
----------------------
看板从第一天起就是「单文件、零依赖、断网可开」。四张 PNG 内嵌会让
HTML 从 120KB 涨到 600KB，还破坏纯文本可 diff 的性质。
这里用几何图形画徽章，整组不到 3KB，且能跟着主题色走。

四个形象对应四种人格组合（节奏 × 盈亏处理）：

    快刀手 F+C   出手快、赚一点就跑
    狙击手 F+R   出手快、但让利润跑
    守株人 S+C   拿得久、却先割盈利
    钓鱼者 S+R   拿得久、也等得到收获

画面元素是**行为隐喻**，不是随便配的图标：
    刀 = 果断了结    准星 = 精确择时
    沙漏 = 时间成本  鱼钩 = 等待与收获
"""
COLORS = {
    "快刀手": ("#f0a07a", "#d9613a"),
    "狙击手": ("#8fb3e0", "#3d6aa8"),
    "守株人": ("#c4a882", "#8a6a3c"),
    "钓鱼者": ("#7cc4bd", "#2c7d76"),
}

FALLBACK = ("#b9c2ce", "#7d8797")


def badge(name, size=84):
    """返回一段独立 SVG。name 为四种昵称之一，其余走中性灰。"""
    c1, c2 = COLORS.get(name, FALLBACK)
    inner = _ICONS.get(name, _ICONS["_default"])

    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 120 120" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{name}">'
        f'<defs><linearGradient id="pg{abs(hash(name)) % 9999}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
        f'</linearGradient></defs>'
        f'<circle cx="60" cy="60" r="56" fill="url(#pg{abs(hash(name)) % 9999})"/>'
        f'<circle cx="60" cy="60" r="56" fill="none" stroke="#ffffff" stroke-opacity=".45" '
        f'stroke-width="2"/>'
        + inner +
        '</svg>'
    )


# 刀：斜置的刀刃 + 速度线，表达「一到价就走」
_KNIFE = (
    '<path d="M78 30 L92 44 L54 82 L40 68 Z" fill="#ffffff" opacity=".96"/>'
    '<path d="M40 68 L54 82 L44 92 L30 78 Z" fill="#ffffff" opacity=".62"/>'
    '<path d="M22 46 L36 46 M18 58 L32 58 M24 70 L34 70" stroke="#ffffff" '
    'stroke-width="3.4" stroke-linecap="round" opacity=".8"/>'
)

# 准星：同心圆 + 十字 + 断开的刻度，表达「只在最有把握时出手」
_CROSSHAIR = (
    '<circle cx="60" cy="60" r="26" fill="none" stroke="#ffffff" stroke-width="3.2" opacity=".95"/>'
    '<circle cx="60" cy="60" r="9" fill="none" stroke="#ffffff" stroke-width="2.6" opacity=".8"/>'
    '<path d="M60 26 L60 44 M60 76 L60 94 M26 60 L44 60 M76 60 L94 60" '
    'stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" opacity=".95"/>'
    '<circle cx="60" cy="60" r="2.6" fill="#ffffff"/>'
)

# 沙漏：时间在流走，表达「拿得久，但时间也是成本」
_HOURGLASS = (
    '<path d="M42 28 H78 L62 60 L78 92 H42 L58 60 Z" fill="none" '
    'stroke="#ffffff" stroke-width="3.4" stroke-linejoin="round" opacity=".96"/>'
    '<path d="M50 36 H70 L60 52 Z" fill="#ffffff" opacity=".9"/>'
    '<path d="M52 84 H68 L60 70 Z" fill="#ffffff" opacity=".62"/>'
    '<path d="M34 28 H86 M34 92 H86" stroke="#ffffff" stroke-width="3.6" '
    'stroke-linecap="round" opacity=".85"/>'
)

# 鱼钩：等待与收获，表达「拿得久，也等得到」
_HOOK = (
    '<path d="M74 26 V58 a18 18 0 0 1 -36 0 v-6" fill="none" stroke="#ffffff" '
    'stroke-width="4" stroke-linecap="round" opacity=".96"/>'
    '<path d="M38 52 l0 12 l11 -6 Z" fill="#ffffff" opacity=".9"/>'
    '<path d="M24 86 q9 -7 18 0 t18 0 t18 0 t18 0" fill="none" stroke="#ffffff" '
    'stroke-width="3" stroke-linecap="round" opacity=".6"/>'
    '<path d="M24 96 q9 -7 18 0 t18 0 t18 0 t18 0" fill="none" stroke="#ffffff" '
    'stroke-width="3" stroke-linecap="round" opacity=".38"/>'
)

_SPARK = (
    '<path d="M60 34 L66 54 L86 60 L66 66 L60 86 L54 66 L34 60 L54 54 Z" '
    'fill="#ffffff" opacity=".92"/>'
)

_ICONS = {
    "快刀手": _KNIFE,
    "狙击手": _CROSSHAIR,
    "守株人": _HOURGLASS,
    "钓鱼者": _HOOK,
    "_default": _SPARK,
}
