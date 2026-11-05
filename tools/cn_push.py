# -*- coding: utf-8 -*-
"""把当前仓库推送到国内代码托管平台（Gitee / GitCode / CNB 均可）。

为什么单独一个脚本
------------------
GitHub 在本机要走代理，推送经常 502；国内平台直连更快。
但凭据不能写进仓库，所以由命令行传入，推完立刻从 remote 里抹掉。

用法：
    python tools/cn_push.py "https://<用户名>:<私人令牌>@gitee.com/<用户名>/ashare-review.git"

    # GitCode 同理：
    python tools/cn_push.py "https://<用户名>:<私人令牌>@gitcode.com/<用户名>/ashare-review.git"

令牌在平台网页生成：
    Gitee  设置 → 私人令牌 → 生成（勾选 projects）
    GitCode 设置 → 访问令牌 → 生成（勾选 write_repository）

推完 remote 会重置为不含令牌的地址，避免凭据留在 .git/config。
"""

import re
import subprocess
import sys


def run(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True, errors="replace")
    if check and r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        sys.exit(f"命令失败：{' '.join(args)}")
    return r


def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python tools/cn_push.py \"https://用户名:令牌@gitee.com/用户名/仓库.git\"")
    url = sys.argv[1].strip()
    if not re.match(r"^https://[^/]+@", url):
        sys.exit("URL 里没带用户名和令牌。格式：https://用户名:令牌@域名/路径.git")

    # 先确认这是不是一个 git 仓库
    r = run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
    if "true" not in (r.stdout or ""):
        sys.exit("当前目录不是 git 仓库")

    branch = (run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout or "main").strip()
    print(f"当前分支：{branch}")

    run(["git", "remote", "remove", "cn"], check=False)
    run(["git", "remote", "add", "cn", url])

    print("推送全部分支与标签……")
    r = run(["git", "push", "cn", "--all", "--force-with-lease"], check=False)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        # 空仓库首次推送时 --force-with-lease 会失败，退回普通 push
        r = run(["git", "push", "cn", "--all"], check=False)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            print(out)
            run(["git", "remote", "set-url", "cn", re.sub(r"//[^@]+@", "//", url)], check=False)
            sys.exit("推送失败：检查仓库是否已创建、令牌是否有写权限")

    run(["git", "push", "cn", "--tags"], check=False)
    print(out.strip()[-800:])

    # 抹掉 remote 里的凭据
    safe = re.sub(r"//[^@]+@", "//", url)
    run(["git", "remote", "set-url", "cn", safe], check=False)
    print(f"\n完成。remote cn = {safe}")
    print("建议再到平台网页确认：默认分支是否为 " + branch + "，以及仓库是否设为公开。")


if __name__ == "__main__":
    main()
