# -*- coding: utf-8 -*-
"""生成比赛用的封面与海报。

海报必须套比赛模板：模板图当底图，内容只填在中间留白区（y 150~1180），
不能压到顶部标题和底部 logo。所以用绝对定位，而不是流式布局。

输出：
    docs/poster.png   竖版海报 906x1280（2x 渲染）
    docs/cover.png    项目封面 1200x750（2x 渲染）
"""
import base64
import os
import subprocess

TEMPLATE = r"C:\Users\wtr\.workbuddy\clipboard-images\clipboard-2026-11-04T14-38-07-124Z-f8dd12f6.png"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT = os.path.join(ROOT, "shot_dash.png")
OUT = os.path.join(ROOT, "docs")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

TITLE = "不复盘，就只是重复"
SUB = "行情软件只告诉你市场涨跌，不告诉你自己做得怎么样"
REPO = "github.com/www498/ashare-review"

STATS = [("5,577", "沪深京全市场个股"), ("71", "交割单配对交易"),
         ("16", "型交易人格"), ("6s", "全市场取数")]


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def poster_html():
    tpl, shot = b64(TEMPLATE), b64(SHOT)
    stats = "".join(
        f'<div class="st"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l in STATS)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:906px;height:1280px;overflow:hidden;
  font-family:"Microsoft YaHei","PingFang SC",sans-serif;
  background:url(data:image/png;base64,{tpl}) no-repeat center/cover}}
.p{{position:absolute;left:0;right:0;text-align:center}}
.t1{{top:232px;font-size:44px;font-weight:800;color:#fff;letter-spacing:2px;
  text-shadow:0 2px 24px rgba(60,140,255,.55)}}
.t2{{top:306px;font-size:17px;color:#9fbbec;letter-spacing:.6px;line-height:1.7;
  padding:0 100px}}
.line{{top:366px;left:50%;transform:translateX(-50%);width:132px;height:2px;
  background:linear-gradient(90deg,transparent,#4d8fe0,transparent)}}
.stats{{top:398px;display:flex;justify-content:center;gap:0}}
.st{{width:172px;text-align:center}}
.st .v{{font-size:38px;font-weight:800;color:#ffb454;line-height:1.15;
  font-variant-numeric:tabular-nums;text-shadow:0 0 26px rgba(255,150,40,.35)}}
.st .l{{font-size:12.5px;color:#8ba6d4;margin-top:5px;letter-spacing:.4px}}
.shot{{top:520px;left:50%;transform:translateX(-50%);width:706px;
  border-radius:12px;overflow:hidden;
  box-shadow:0 18px 60px rgba(0,0,0,.55),0 0 0 1px rgba(110,160,240,.35)}}
.shot img{{display:block;width:100%}}
.foot{{top:1128px;font-size:13.5px;color:#7f9cc8;letter-spacing:1.2px}}
.foot b{{color:#cfe0ff;font-weight:600}}
</style></head><body>
<div class="p t1">{TITLE}</div>
<div class="p t2">{SUB}</div>
<div class="p line"></div>
<div class="p stats">{stats}</div>
<div class="p shot"><img src="data:image/png;base64,{shot}"></div>
<div class="p foot"><b>{REPO}</b></div>
</body></html>"""


def cover_html():
    shot = b64(SHOT)
    stats = "".join(
        f'<div class="st"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l in STATS[:3])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1200px;height:750px;overflow:hidden;position:relative;
  font-family:"Microsoft YaHei","PingFang SC",sans-serif;
  background:linear-gradient(120deg,#f7f9fd 0%,#eef3fa 52%,#e6edf8 100%)}}
.glow{{position:absolute;width:720px;height:720px;right:-190px;top:-260px;
  border-radius:50%;background:radial-gradient(circle,rgba(64,120,210,.16),transparent 68%)}}
.left{{position:absolute;left:72px;top:158px;width:430px}}
.kicker{{font-size:13px;letter-spacing:3px;color:#3f6aa8;font-weight:700}}
.h1{{font-size:54px;font-weight:800;color:#16233a;line-height:1.16;
  letter-spacing:-.5px;margin-top:14px}}
.h1 em{{font-style:normal;color:#c5221f}}
.sub{{font-size:16px;color:#5b6879;line-height:1.85;margin-top:20px;width:400px}}
.stats{{display:flex;gap:34px;margin-top:34px}}
.st .v{{font-size:30px;font-weight:800;color:#1c3a66;font-variant-numeric:tabular-nums}}
.st .l{{font-size:12px;color:#7d8798;margin-top:3px}}
.tag{{display:inline-block;margin-top:30px;font-size:12.5px;color:#3f6aa8;
  background:#e7eefb;border:1px solid #d3e0f5;border-radius:999px;padding:6px 14px}}
.shot{{position:absolute;right:-96px;top:88px;width:800px;border-radius:10px;
  overflow:hidden;box-shadow:0 24px 70px rgba(24,44,78,.24),0 0 0 1px rgba(180,200,230,.7);
  transform:rotate(-1.6deg)}}
.shot img{{display:block;width:100%}}
.note{{position:absolute;left:72px;bottom:96px;font-size:12.5px;color:#7f8a9b}}
.bar{{position:absolute;left:72px;bottom:54px;font-size:12.5px;color:#8b95a5;letter-spacing:1px}}
</style></head><body>
<div class="glow"></div>
<div class="left">
  <div class="kicker">A 股复盘台</div>
  <div class="h1">市场在哪里，<br>你<em>做得怎么样</em></div>
  <div class="sub">把市场数据和个人交割单放进同一张看板：
    涨跌为什么发生，你自己的每一笔又做对没做对。</div>
  <div class="stats">{stats}</div>
  <div class="tag">知乎黑客松 · 湾区共创季</div>
</div>
<div class="shot"><img src="data:image/png;base64,{shot}"></div>
<div class="note">所有数据在本地计算，交割单不上传任何服务器</div>
<div class="bar">{REPO}</div>
</body></html>"""


def shoot(html, out, w, h, scale=2):
    tmp = os.path.join(ROOT, "_tmp_page.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={w},{h}", f"--force-device-scale-factor={scale}",
                    "--virtual-time-budget=3000", f"--screenshot={out}",
                    "file:///" + tmp.replace("\\", "/")],
                   check=True, capture_output=True)
    os.remove(tmp)
    print("写出", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    shoot(poster_html(), os.path.join(OUT, "poster.png"), 906, 1280)
    shoot(cover_html(), os.path.join(OUT, "cover.png"), 1200, 750)
