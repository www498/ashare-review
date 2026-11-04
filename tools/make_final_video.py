# -*- coding: utf-8 -*-
"""把 25 秒片头 + 100 秒正片拼成最终演示片 docs/demo.mp4（共 125 秒）。

为什么用 concat + copy
----------------------
两段都是 libx264 / yuv420p / 1280x720 / 30fps，编码参数兼容，
直接流拷贝即可：1 秒完成，且不会二次压缩损失画质。
如果哪天改了分辨率或帧率，再换成 filter_complex 重编码。

前置：python tools/make_intro.py（片头）、python tools/make_video.py（正片）
跑法：python tools/make_final_video.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
PARTS = [os.path.join(DOCS, "intro.mp4"), os.path.join(DOCS, "demo_body.mp4")]
OUT = os.path.join(DOCS, "demo.mp4")


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("需要 imageio-ffmpeg：pip install imageio-ffmpeg")


def duration(ff, path):
    """imageio-ffmpeg 只带 ffmpeg 不带 ffprobe，从 -i 的 stderr 读时长。"""
    r = subprocess.run([ff, "-hide_banner", "-i", path],
                       capture_output=True, text=True, errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def main():
    for p in PARTS:
        if not os.path.exists(p):
            sys.exit(f"缺少 {os.path.relpath(p, ROOT)}，先跑对应的生成脚本")

    ff = ffmpeg_exe()
    before = [duration(ff, p) for p in PARTS]

    # concat demuxer 要求 list 文件里的路径是绝对路径、正斜杠；-safe 0 放开盘符路径。
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        for p in PARTS:
            f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
        lst = f.name
    try:
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", lst, "-c", "copy",
                        "-movflags", "+faststart", OUT], check=True)
    finally:
        os.unlink(lst)

    after = duration(ff, OUT)
    for p, d in zip(PARTS, before):
        print(f"  {os.path.basename(p):<17} {d:6.2f}s" if d else f"  {p} 时长未知")
    print(f"  {os.path.basename(OUT):<17} {after:6.2f}s  "
          f"{os.path.getsize(OUT) // 1024}KB" if after else "写出 " + OUT)
    if after and all(before):
        drift = after - sum(before)
        print(f"  拼接误差 {drift:+.2f}s（流拷贝下应为 0）")
        if abs(drift) > 0.2:
            sys.exit("时长不守恒，检查两段编码参数是否一致")


if __name__ == "__main__":
    main()
