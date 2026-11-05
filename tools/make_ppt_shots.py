# -*- coding: utf-8 -*-
"""生成答辩 PPT 用的四张定制截图。

与 make_screens 的区别：这里为特定页面做裁剪与筛选，不追求通用。
- profile：去掉 16 型全谱，只要「形象 + 四维 + 速写」
- journal3：只留赤峰黄金、紫金矿业、西部矿业三手，全列不裁
- sell4：卖后表现前 4 行，放大
- watch：自选股单只展开，纵向拉长
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ashare import web  # noqa: E402

OUT = os.path.join(ROOT, "ppt", "复盘台答辩", "assets")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def shot(name, body, width=1280, height=1600, crop_to=None):
    html = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<style>{web.CSS}</style></head><body>"
            f"<div class='wrap'>{body}</div></body></html>")
    tmp = os.path.join(ROOT, f"_ppt_{name}.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    png = os.path.join(OUT, f"{name}.png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={width},{height}", "--virtual-time-budget=4000",
                    f"--screenshot={png}", "file:///" + tmp.replace("\\", "/")],
                   capture_output=True)
    os.remove(tmp)

    from PIL import Image
    im = Image.open(png).convert("RGB")
    if crop_to:
        im = im.crop((0, 0, im.size[0], min(crop_to, im.size[1])))
    im.save(png, optimize=True)
    print(f"  {name}.png  {im.size[0]}×{im.size[1]}")
    return im


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-11-04"
    session = sys.argv[2] if len(sys.argv) > 2 else "pm"
    uid = sys.argv[3] if len(sys.argv) > 3 else "demo"
    fp = os.path.join(ROOT, "users", uid, "snapshots",
                      day.replace("-", "") + f"_{session}.json")
    with open(fp, encoding="utf-8") as f:
        ctx = json.load(f)

    print("生成定制截图：")

    # 1) 画像：删掉 16 型全谱整块，只留形象、四维、速写
    h = []
    web._sec_profile(h, ctx, compact=True)
    body = "".join(h)
    body = re.sub(r'<details class="fold mb16">.*?</details>', "", body, flags=re.S)
    shot("profile2", body, height=1400, crop_to=760)

    # 2) 逐笔：只留三只票，全列不裁
    keep = {"600988", "601899", "601168"}   # 赤峰黄金 / 紫金矿业 / 西部矿业
    one = dict(ctx)
    j = json.loads(json.dumps(ctx["journal"]))
    j["rows"] = [r for r in j["rows"] if r["code"] in keep]
    j["summary"]["n"] = len(j["rows"])
    one["journal"] = j
    one["sell_review"] = []
    h = []
    web._sec_journal(h, one)
    shot("journal3", "".join(h), height=1200)

    # 3) 自选股：赤峰单只展开，纵向拉到 700
    one2 = dict(ctx)
    one2["anomalies"] = [a for a in (ctx.get("anomalies") or []) if a.get("code") == "600988"]
    h = []
    web._sec_watch(h, one2)
    body = "".join(h).replace('<tr class="det">', '<tr class="det open">')
    shot("watch2", body, height=1400, crop_to=700)


if __name__ == "__main__":
    main()
