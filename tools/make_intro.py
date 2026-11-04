# -*- coding: utf-8 -*-
"""片头 25 秒：红绿数字冲刷 → 停住 → 问号 → 一句话。

为什么自己画而不是用风格化视频工具
--------------------------------
这一段要的是「行情软件的数字」——真实涨跌幅、真实家数、真实成交额。
用代码画这些数字，比让模型生成画面更准，也能精确控制节奏：
前 12 秒数字高速冲刷（观众只来得及感觉"信息很多"），
第 12 秒急停（留下空白），问号出现（制造疑问），最后一句把问题转到观众自己身上。

0–12s 底部压一条收盘播报字幕；12–20s 问号；问号淡出时文案上移居中定格。
输出 docs/intro.mp4（1280x720，25 秒），
再由 tools/make_final_video.py 无损拼到演示片前面。
"""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "intro.mp4")
W, H, FPS = 1280, 720, 30
DUR = 25.0

BG = (7, 12, 26)
UP = (214, 52, 44)      # 涨：红（A 股口径）
DOWN = (22, 156, 92)    # 跌：绿
DIM = (104, 118, 142)
WHITE = (238, 243, 250)

FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"

# 真实口径的数字：涨跌幅、涨跌家数、成交额、指数点位
TEXTS = ["+10.00%", "+6.56%", "-3.21%", "+2.04%", "-0.53%", "+1.88%",
         "5,577", "2,981 涨", "1,932 跌", "8,776 亿", "3,686.17",
         "+4.23%", "-1.20%", "涨停 68", "跌停 12", "+0.85%", "-2.44%"]


def font(size, bold=True):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, size)
    except Exception:
        return ImageFont.load_default()


_cache = {}


def sprite(text, color, size):
    """预渲染每个数字，避免逐帧重复排版（750 帧 × 上百个数字会慢到没法等）。"""
    key = (text, color, size)
    if key in _cache:
        return _cache[key]
    f = font(size)
    pad = 6
    bbox = f.getbbox(text)
    w, h = bbox[2] - bbox[0] + pad * 2, bbox[3] - bbox[1] + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - bbox[0], pad - bbox[1]), text, font=f, fill=color)
    _cache[key] = im
    return im


def make_field():
    """数字跑道：每列是一条纵向队列，数字等距排列，整列往下滚。

    关键约束是「同一列内绝不重叠」——最初按随机 Y 摆放，
    结果几百个数字糊在一起，看起来像噪点而不是行情。
    改成固定间距后，密度靠列数和字号控制，画面才干净。
    """
    rnd = random.Random(20261104)
    cols = []
    gap = 168
    for x in range(6, W + gap, gap):
        n = 18
        items = []
        for j in range(n):
            t = rnd.choice(TEXTS)
            if t.startswith("+") or t in ("2,981 涨", "涨停 68"):
                col = UP
            elif t.startswith("-") or t in ("1,932 跌", "跌停 12"):
                col = DOWN
            else:
                col = DIM
            items.append((t, col, rnd.choice([22, 26, 26, 30])))
        cols.append({"x": x, "items": items, "gap": 46,
                     "speed": rnd.uniform(0.55, 1.35), "phase": rnd.uniform(0, 46 * n)})
    return cols


FIELD = make_field()


def ease_out(t):
    """前段维持高速，末段迅速减速——「镜头停住」的感觉来自速度曲线，不是黑场。"""
    return 1 - (1 - t) ** 3


def frame(t):
    canvas = Image.new("RGB", (W, H), BG)

    # ---- 阶段 1：数字冲刷（0–12s），速度逐渐死掉 ----
    p = min(1.0, t / 12.0)
    travel = ease_out(p) * 2600
    fade = 1.0 if t < 10.5 else max(0.0, (12.0 - t) / 1.5)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for c in FIELD:
        n = len(c["items"])
        span = c["gap"] * n
        base = (c["phase"] + c["speed"] * travel) % span
        for j, (text, color, size) in enumerate(c["items"]):
            y = base + j * c["gap"] - 60
            if y > H + 40:
                y -= span
            if y < -60:
                y += span
            sp = sprite(text, color, size)
            a = int(232 * fade * (0.5 + 0.5 * (size - 20) / 10))
            if a <= 3:
                continue
            sp2 = sp.copy()
            sp2.putalpha(sp.getchannel("A").point(lambda v, a=a: v * a // 255))
            layer.alpha_composite(sp2, (c["x"], int(y)))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")

    # ---- 阶段 1 的字幕：把「数字」落到观众看到的收盘播报 ----
    if 0.5 <= t <= 11.6:
        a = min(1.0, (t - 0.5) / 0.8) * min(1.0, (11.6 - t) / 1.0)
        line = "每天收盘你看到的是这些：涨了多少家、成交多少亿"
        f = font(30)
        # 和上面的数字统一走独立透明图层，不依赖 ImageDraw 在 RGB 画布上的
        # RGBA 混合行为；底条用接近背景的深蓝，只把数字压住、托起白字。
        bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(bar)
        tw = d.textlength(line, font=f)
        bw, bh = int(tw) + 56, 58
        x0, y0 = (W - bw) // 2, H - bh - 44
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=10,
                            fill=(8, 16, 34, int(230 * a)))
        d.text((x0 + 28, y0 + 12), line, font=f,
               fill=(240, 245, 252, int(255 * a)))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), bar).convert("RGB")

    # ---- 阶段 2：问号（12–19s） ----
    if 11.6 <= t < 20.0:
        q = min(1.0, (t - 11.6) / 1.4)
        scale = 0.82 + 0.18 * q
        alpha = q if t < 18.6 else max(0.0, (20.0 - t) / 1.4)
        size = int(230 * scale)
        f = font(size)
        mark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(mark)
        d.text((W // 2, H // 2 - 26), "?", font=f, anchor="mm",
               fill=(255, 255, 255, int(235 * alpha)))
        glow = mark.filter(ImageFilter.GaussianBlur(22))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")
        canvas = Image.alpha_composite(canvas.convert("RGBA"), mark).convert("RGB")

    # ---- 阶段 3：那句话（16–25s） ----
    if t >= 15.4:
        a = min(1.0, (t - 15.4) / 1.2)
        a *= min(1.0, max(0.0, (DUR - t) / 1.0))
        d = ImageDraw.Draw(canvas)
        lines = [("这些数字，和你的账户", 40), ("有什么关系？", 40)]
        # 问号淡出时把整块文案平滑上移居中；否则 20s 后上半屏全空、字压在底部。
        rise = min(1.0, max(0.0, (t - 18.6) / 1.8))
        y0 = H // 2 + 118 - int(170 * rise)
        for i, (ln, sz) in enumerate(lines):
            f = font(sz)
            d.text((W // 2, y0 + i * 60), ln, font=f, anchor="mm",
                   fill=tuple(int(c * a) for c in WHITE))
        # 一条细线，呼应海报的渐变线
        lw = int(120 * a)
        if lw > 2:
            d.line([(W // 2 - lw, y0 + 108), (W // 2 + lw, y0 + 108)],
                   fill=(int(58 * a), int(96 * a), int(150 * a)), width=2)
        f2 = font(19, bold=False)
        d.text((W // 2, y0 + 142), "复盘台 · 市场复盘 × 个人交易画像", font=f2,
               anchor="mm", fill=(int(120 * a), int(140 * a), int(172 * a)))

    return canvas


def main():
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("需要 imageio-ffmpeg：pip install imageio-ffmpeg")

    total = int(DUR * FPS)
    writer = imageio_ffmpeg.write_frames(
        OUT, (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24",
        output_params=["-crf", "19", "-preset", "medium", "-movflags", "+faststart"])
    writer.send(None)
    for i in range(total):
        writer.send(np.array(frame(i / FPS)).tobytes())
        if i % 75 == 0:
            print(f"  {i}/{total}", flush=True)
    writer.close()
    print("写出", os.path.relpath(OUT, ROOT), f"{os.path.getsize(OUT)//1024}KB")


if __name__ == "__main__":
    main()
