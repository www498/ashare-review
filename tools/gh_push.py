# -*- coding: utf-8 -*-
"""用 GitHub Git Data API 同步当前代码到一个新提交。

为什么不用 git push
-------------------
本机到 github.com:443 的 CONNECT 隧道返回 502，但 api.github.com 正常。
所以走 REST：上传 blob → 拼树 → 建 commit → 移动 ref。

为什么按内容比对而不是按 git diff
--------------------------------
之前几次通过 API 推送，GitHub 生成的 commit sha 与本地不同（作者时间戳不同），
本地和远程历史就此分叉，git diff 找不到共同祖先。所以这里不比历史，
直接比每个文件的 blob sha：一致的跳过，不一致或新增的上传，
远程有而本地没有的删除。
"""
import base64
import json
import subprocess
import sys
import urllib.request

REPO = "www498/ashare-review"
API = f"https://api.github.com/repos/{REPO}"

# git 协议走代理会 502，但 api.github.com 直连是通的。
# 显式清空代理，避免 urllib 读到环境变量里的 http_proxy。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def token():
    out = subprocess.run(["git", "credential", "fill"],
                         input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("没有找到 GitHub 凭据")


TOKEN = token()


def call(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    with _OPENER.open(req, timeout=90) as r:
        return json.loads(r.read().decode())


def git(*args, text=False):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args],
                          capture_output=True, check=True).stdout


def local_files():
    """当前提交里的所有文件 → {path: blob sha}。"""
    out = git("ls-tree", "-r", "HEAD", "-z").decode("utf-8", "replace")
    files = {}
    for rec in out.split("\0"):
        if not rec:
            continue
        head, path = rec.split("\t", 1)
        _mode, _type, sha = head.split()
        files[path] = sha
    return files


def remote_files(tree_sha):
    res = call("GET", f"{API}/git/trees/{tree_sha}?recursive=1")
    if res.get("truncated"):
        sys.exit("远程树太大，API 返回被截断，需要换分页方案")
    return {n["path"]: n["sha"] for n in res["tree"] if n["type"] == "blob"}


def main():
    ref = call("GET", f"{API}/git/ref/heads/main")
    base = ref["object"]["sha"]
    base_tree = call("GET", f"{API}/git/commits/{base}")["tree"]["sha"]
    loc, rem = local_files(), remote_files(base_tree)
    print(f"远程 HEAD {base[:8]}  本地 {len(loc)} 个文件 / 远程 {len(rem)} 个")

    entries, added, changed = [], 0, 0
    for path, sha in loc.items():
        if rem.get(path) == sha:
            continue
        content = git("show", f"HEAD:{path}")
        blob = call("POST", f"{API}/git/blobs", {
            "content": base64.b64encode(content).decode(), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        flag = "改" if path in rem else "增"
        if path in rem:
            changed += 1
        else:
            added += 1
        print(f"  {flag} {path}  {len(content) // 1024}KB")

    gone = [p for p in rem if p not in loc]
    for p in gone:
        entries.append({"path": p, "mode": "100644", "type": "blob", "sha": None})
        print(f"  删 {p}")

    if not entries:
        print("没有差异，无需提交")
        return

    tree = call("POST", f"{API}/git/trees", {"base_tree": base_tree, "tree": entries})
    msg = git("log", "-1", "--pretty=%B", "HEAD").decode("utf-8").strip()
    commit = call("POST", f"{API}/git/commits",
                  {"message": msg, "tree": tree["sha"], "parents": [base]})
    call("PATCH", f"{API}/git/refs/heads/main", {"sha": commit["sha"]})
    print(f"\n已推送 {commit['sha'][:8]}  新增 {added} 修改 {changed} 删除 {len(gone)}")


if __name__ == "__main__":
    main()
