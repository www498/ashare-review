# -*- coding: utf-8 -*-
"""把已生成的人格图背景打成透明。

为什么要连通性判断而不是简单色差阈值
------------------------------------
这些形象里有大量白色元素：衬衫、鱼线、海鸥、账本。
单纯「离背景色近就透明」会把人物身上的白一起挖掉。
改成从画布四边向内做洪水填充，只清除「与边缘连通」的浅色区域——
人物内部的白色被深色描边包住，不与边缘连通，因此安全。
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "assets", "persona")

TOL = 9           # 与背景色的最大色差。取小值很关键：白鞋、白衬衫离背景只有 10 左右，
                  # 放宽到 20 以上就会把它们当成背景一起挖掉
FEATHER = 1.0     # 边缘羽化半径（像素）
OUT = 360         # 输出边长
FILL = 0.92       # 人物包围盒占画布的比例。统一这个值，16 个形象看起来才一样大


def _tighten(im):
    """按不透明区域重新裁切，让人物在画布里居中且大小一致。

    生成时人物占比是随机的（有的贴着边，有的只占一半），
    直接用原图会让 16 个形象大小参差。这里统一按包围盒归一化。
    """
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.where(a > 12)
    if not len(ys):
        return im
    cy, cx = (ys.min() + ys.max()) / 2.0, (xs.min() + xs.max()) / 2.0
    side = max(ys.max() - ys.min(), xs.max() - xs.min())
    if side < 8:
        return im

    scale = OUT * FILL / side
    new = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                    Image.LANCZOS)
    canvas = Image.new("RGBA", (OUT, OUT), (0, 0, 0, 0))
    canvas.paste(new, (int(OUT / 2 - cx * scale), int(OUT / 2 - cy * scale)), new)
    return canvas


def cut(path, tol=TOL):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    bg = a[2, 2]
    d = np.sqrt(((a - bg) ** 2).sum(axis=2))

    near = d < tol
    # 只保留从画布边缘能连到的浅色区域，作为「背景」
    seed = np.zeros_like(near)
    seed[0, :] = near[0, :]
    seed[-1, :] = near[-1, :]
    seed[:, 0] = near[:, 0]
    seed[:, -1] = near[:, -1]
    bgmask = ndimage.binary_propagation(seed, mask=near)

    solid = ~bgmask
    # 收紧阈值后，人物内部的浅色块可能被啃出小洞，补回来
    solid = ndimage.binary_fill_holes(solid)

    alpha = np.where(solid, 255.0, 0.0)
    # 羽化：把硬边磨成 1px 过渡，贴到任何底色上都不会有锯齿
    alpha = ndimage.gaussian_filter(alpha, FEATHER)
    alpha[alpha < 6] = 0

    rgba = np.dstack([a, alpha]).astype(np.uint8)
    out = _tighten(Image.fromarray(rgba, mode="RGBA"))
    out.save(path, optimize=True)
    return int((alpha > 0).sum()), alpha.size


if __name__ == "__main__":
    for code in sorted(os.listdir(D)):
        if not code.endswith(".png"):
            continue
        p = os.path.join(D, code)
        probe = Image.open(p)
        if probe.mode == "RGBA" and (np.asarray(probe)[:, :, 3] < 250).mean() > 0.02:
            print(f"{code:12s} 已处理，跳过")
            continue
        kept, total = cut(p)
        print(f"{code:12s} 保留 {kept / total:.0%}  {os.path.getsize(p) // 1024}KB")
