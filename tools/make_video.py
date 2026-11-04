# -*- coding: utf-8 -*-
"""把真实界面截图合成一段演示片。

为什么不用录屏
--------------
完整跑一次复盘要 3 分钟，录进去没人看；而这些界面本身是静态的，
用「截图 + 缓慢推近 + 字幕」表达得更清楚，也方便改词重出。

输出：docs/demo_body.mp4（1280x720，30fps，约 73 秒，无声）——成片的正片部分。
片头由 tools/make_intro.py 生成，最后用 tools/make_final_video.py 无损拼接成
docs/demo.mp4（25s 片头 + 73s 正片 = 98s）。拆成三段是为了改文案时只重渲染一段。

旁白另外配，或直接用字幕——无声版在 B 站也能看。

跑法：python tools/make_video.py → python tools/make_intro.py → python tools/make_final_video.py
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "demo_body.mp4")

W, H, FPS = 1280, 720, 30
NAVY = (8, 20, 56)
DEEP = (4, 12, 38)

FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"


def font(size, bold=True):
    path = FONT_B if bold else FONT_R
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


SCENES = [
    dict(kind="title", dur=5,
         t1="不复盘，就只是重复", t2="A 股市场复盘 × 个人交易画像"),
    dict(kind="shot", img="vid_home.png", box=(200, 0, 1720, 855), dur=11,
         cap="主页：交易行为画像常驻，下面是每天的复盘"),
    dict(kind="shot", img="vid_dash.png", box=(200, 30, 1720, 885), dur=11,
         cap="单日看板：市场温度、持仓、今天做的每一笔"),
    dict(kind="shot", img="vid_cf.png", box=(0, 88, 1280, 808), dur=13,
         cap="今天为什么涨：大盘 + 板块 + 个股，三段可直接相加"),
    dict(kind="shot", img="vid_ly.png", box=(0, 88, 1280, 808), dur=12,
         cap="涨了 3.6% 却跑输 6.1% 的板块，量还放大了 —— 借势出货"),
    # 收尾落在「每一笔操作」上，而不是堆技术指标：这是产品真正的差异点。
    # 同一张真实看板截图取两个窗口，像镜头往下移：先逐笔判断，再卖出后回看。
    dict(kind="shot", img="vid_journal.png", box=(0, 0, 1280, 720), dur=12,
         cap="今天 11 手逐笔复盘：该不该买/卖，只用成交当时的数据判断"),
    dict(kind="shot", img="vid_journal.png", box=(0, 470, 1280, 1190), dur=9,
         cap="卖出后 3/5 日回看：卖飞还是躲过，结果和决策质量分开算"),
]


def ken_burns(img, t, dur, z0=1.0, z1=1.05):
    """从中心缓慢推近。动态比静止画面更容易让人看下去。"""
    z = z0 + (z1 - z0) * (t / max(dur, 1e-6))
    w, h = img.size
    nw, nh = int(w / z), int(h / z)
    left, top = (w - nw) // 2, (h - nh) // 2
    return img.crop((left, top, left + nw, top + nh)).resize((W, H), Image.LANCZOS)


def caption_bar(canvas, text):
    """底部字幕条：半透明深底 + 白字，保证在任何截图上都读得清。"""
    if not text:
        return canvas
    d = ImageDraw.Draw(canvas, "RGBA")
    f = font(30)
    tw = d.textlength(text, font=f)
    # 压扁并贴到底边：逐笔复盘那两帧的表格一直排到画面下方，
    # 原来 58px 高、离底 44px 的字幕条会盖掉最后一行和说明文字。
    pad_x, pad_y = 26, 10
    bw, bh = int(tw) + pad_x * 2, 30 + pad_y * 2
    x0, y0 = (W - bw) // 2, H - bh - 20
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=10, fill=(8, 16, 34, 205))
    d.text((x0 + pad_x, y0 + pad_y - 2), text, font=f, fill=(240, 245, 252))
    return canvas


def title_card(t1, t2, t, dur):
    canvas = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(canvas)
    # 顶部一条细光带，和海报的渐变线呼应
    for i in range(H):
        c = tuple(int(NAVY[j] + (DEEP[j] - NAVY[j]) * i / H) for j in range(3))
        d.line([(0, i), (W, i)], fill=c)
    # 淡入
    a = min(1.0, t / 0.8) * min(1.0, max(0.0, (dur - t) / 0.8))
    f1, f2 = font(66), font(28, bold=False)
    d.text((W // 2, H // 2 - 34), t1, font=f1, anchor="mm",
           fill=(int(255 * a), int(255 * a), int(255 * a)))
    d.text((W // 2, H // 2 + 48), t2, font=f2, anchor="mm",
           fill=(int(150 * a), int(175 * a), int(220 * a)))
    d.line([(W // 2 - 60, H // 2 + 4), (W // 2 + 60, H // 2 + 4)],
           fill=(int(70 * a), int(120 * a), int(200 * a)), width=2)
    return canvas


def build_frames():
    cache = {}
    for sc in SCENES:
        if sc["kind"] != "shot":
            continue
        p = os.path.join(ROOT, sc["img"])
        if not os.path.exists(p):
            sys.exit(f"缺少素材 {sc['img']}，先跑截图步骤")
        im = Image.open(p).convert("RGB")
        l, t, r, b = sc["box"]
        cache[sc["img"] + str(sc["box"])] = im.crop((l, t, r, b)).resize((W, H), Image.LANCZOS)

    for sc in SCENES:
        n = int(sc["dur"] * FPS)
        for i in range(n):
            t = i / FPS
            if sc["kind"] == "title":
                yield np.array(title_card(sc["t1"], sc["t2"], t, sc["dur"]))
            else:
                base = ken_burns(cache[sc["img"] + str(sc["box"])], t, sc["dur"])
                yield np.array(caption_bar(base, sc.get("cap")))


def main():
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("需要 imageio-ffmpeg：pip install imageio-ffmpeg")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    total = int(sum(s["dur"] for s in SCENES) * FPS)
    writer = imageio_ffmpeg.write_frames(
        OUT, (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24",
        output_params=["-crf", "20", "-preset", "medium", "-movflags", "+faststart"])
    writer.send(None)
    for i, frame in enumerate(build_frames()):
        writer.send(frame.tobytes())
        if i % 90 == 0:
            print(f"  渲染 {i}/{total} 帧", flush=True)
    writer.close()
    print("写出", os.path.relpath(OUT, ROOT),
          f"{os.path.getsize(OUT) // 1024}KB  {total / FPS:.0f}s")


if __name__ == "__main__":
    main()
