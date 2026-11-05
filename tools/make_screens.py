# -*- coding: utf-8 -*-
"""把看板里的关键区块单独渲染成图片，供 README / Gitee 仓库直接展示。

为什么不用整页截图：整页 1 万多像素高，裁切坐标随样式变动而失效；
单独渲染一个区块，高度自适应，也不会把别的区块裁一半。

跑法：python tools/make_screens.py 2026-11-04 pm demo
输出：docs/screens/01-profile.png / 02-journal.png / 03-watch.png
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ashare import web  # noqa: E402

OUT = os.path.join(ROOT, "docs", "screens")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def shot(name, body_html, width=1280, height=2600):
    html = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<style>{web.CSS}</style></head><body>"
            "<div class='wrap'>" + body_html + "</div></body></html>")
    tmp = os.path.join(ROOT, f"_shot_{name}.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    png = os.path.join(OUT, f"{name}.png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={width},{height}", "--virtual-time-budget=4000",
                    f"--screenshot={png}", "file:///" + tmp.replace("\\", "/")],
                   capture_output=True)
    os.remove(tmp)

    # 裁掉底部空白：页面底色 #f5f6f8
    from PIL import Image
    import numpy as np
    im = Image.open(png).convert("RGB")
    a = np.array(im)
    rows = np.where((np.abs(a.astype(int) - np.array([245, 246, 248])).sum(axis=2) > 12).any(axis=1))[0]
    bottom = int(rows.max()) + 24 if len(rows) else im.size[1]
    im.crop((0, 0, im.size[0], min(bottom, im.size[1]))).save(png, optimize=True)
    print(f"  {name}.png  {im.size[0]}×{min(bottom, im.size[1])}")


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-11-04"
    session = sys.argv[2] if len(sys.argv) > 2 else "pm"
    uid = sys.argv[3] if len(sys.argv) > 3 else "demo"
    os.makedirs(OUT, exist_ok=True)

    fp = os.path.join(ROOT, "users", uid, "snapshots",
                      day.replace("-", "") + f"_{session}.json")
    with open(fp, encoding="utf-8") as f:
        ctx = json.load(f)

    print("渲染截图：")
    h = []
    web._sec_profile(h, ctx, compact=True)
    # 截图时把「16 型全谱」展开：折叠状态下截出来的图看不懂
    body = "".join(h).replace('<details class="fold mb16">',
                              '<details class="fold mb16" open>')
    shot("01-profile", body)

    h = []
    web._sec_journal(h, ctx)
    shot("02-journal", "".join(h))

    h = []
    web._sec_watch(h, ctx)
    shot("03-watch", "".join(h), height=3000)


if __name__ == "__main__":
    main()
