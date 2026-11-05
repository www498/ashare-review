# 国内托管与演示兜底

## 先说结论

**答辩当天的演示不依赖网络。** 现场用本地的 `docs/demo.html`（或解压 `docs/demo-offline.zip`）
直接双击打开；国内 Git 承担两件事：代码备份、评委事后查看。

原因很直接：Pages 类服务都可能遇到现场网络、域名解析、平台审核问题；
而单文件 HTML 双击就能开，是最稳的路径。国内 Git 是第二层保险，不是第一层。

---

## 一、上传到国内 Git

### 方式 A：网页导入（最省事，不用命令行）

1. 登录 [Gitee](https://gitee.com) → 新建仓库 → 选择「导入已有仓库」；
2. 填入 GitHub 地址（若导入失败，说明 Gitee 拉不到 GitHub，改用方式 B）；
3. 导入完成后，把仓库设为公开。

> Gitee 的「导入 GitHub 仓库」依赖 Gitee 服务器能访问 GitHub，偶尔会超时。
> 导入失败不是你的问题，直接走方式 B。

### 方式 B：脚本推送（推荐）

1. 在 Gitee 生成私人令牌：**设置 → 私人令牌 → 生成新令牌**，勾选 `projects`；
2. 在仓库目录执行：

```bash
python tools/cn_push.py "https://<你的用户名>:<令牌>@gitee.com/<你的用户名>/ashare-review.git"
```

脚本会推送全部分支与标签，推完自动把令牌从 `.git/config` 里抹掉。
GitCode 用法相同，把域名换成 `gitcode.com`。

### 方式 C：压缩包上传（无令牌、无命令行）

`dist/ashare-review-src.zip` 是当前提交的完整源码（约 27MB）。
在 Gitee 网页「上传文件」可以传，但网页上传不适合大量文件；
更推荐用方式 B。

### 带历史的完整备份

`dist/ashare-review.bundle` 是包含全部提交历史的 git 包（约 32MB）。
在任意机器上执行 `git clone ashare-review.bundle ashare-review` 即可还原完整仓库，
再按方式 B 推到 Gitee。

---

## 二、演示页放哪里

**先说结论：Gitee 没有可用的在线演示能力。**

Gitee Pages 已于 **2024 年 5 月下线**，官方回复是「由于不可抗原因，服务已下线，暂无恢复计划」。
现在仓库「服务」菜单里只剩腾讯云托管、阿里云 SAE、CodeCheck 这些，没有 Pages。
另外实测：仓库里 `.html` 的 raw 直链返回 **451**，浏览器只会显示源码，不会渲染页面。
所以下面这条路是断的，不要再按旧教程操作。

| 方式 | 可用性 | 说明 |
|---|---|---|
| **离线包（推荐）** | 可用 | 仓库里 `docs/demo-offline.zip`，下载解压双击 `demo.html` |
| 仓库内直接打开 | 可用 | 克隆仓库后双击 `docs/demo.html` |
| README 截图 | 可用 | 仓库首页已放画像与逐笔两张真实界面图 |
| Gitee Pages | **已下线** | 2024 年 5 月停止服务 |
| GitHub Pages | 可用但不稳 | 国内访问看线路，不能作为现场唯一方案 |

如果评审明确要求「点链接就能看」，只有两条路，都要额外成本：

1. **自有域名 + ICP 备案 + 国内静态托管**（腾讯云 EdgeOne Pages、阿里云 OSS、腾讯云 CloudBase）。
   备案通常 1–2 周，免费二级域名拿不到大陆节点，手机打开仍然可能失败。
2. **AtomGit Pages**：国内平台，流程与当年的 Gitee Pages 类似，免费，但长期可用性需自己评估。

答辩在即，不建议现在去开新平台。现场用离线包，仓库给评委看代码和截图，足够了。

---

## 三、答辩当天检查清单

- [ ] U 盘里放一份 `demo-offline.zip`，并在答辩电脑桌面解压一份
- [ ] 浏览器提前打开 `demo.html`，确认画像、图鉴、逐笔复盘三块都能显示
- [ ] 断网状态下再打开一次，确认图片（16 型形象）仍能显示
- [ ] 记下三个跳转锚点：`#sec-profile`（画像）、`#sec-journal`（逐笔）、`#sec-watch`（自选股）
- [ ] PPT 与 HTML 放在同一个文件夹，避免现场找文件

---

## 四、改了内容之后怎么更新

```bash
# 1. 重新生成演示页（会同步画像、重注入图鉴）
python tools/build_demo_page.py 2026-11-04 pm demo

# 2. 重新打包离线演示包
python -c "import zipfile,os; z=zipfile.ZipFile('docs/demo-offline.zip','w',zipfile.ZIP_DEFLATED); z.write('docs/demo.html','demo.html'); [z.write(os.path.join('docs/assets/persona',f),'assets/persona/'+f) for f in sorted(os.listdir('docs/assets/persona')) if f.endswith('.png')]; z.close()"

# 3. 提交并推送国内仓库
git add -A && git commit -m "更新演示页"
python tools/cn_push.py "https://<用户名>:<令牌>@gitee.com/<用户名>/ashare-review.git"
```

---

## 五、为什么不用 GitHub Pages 做现场演示

GitHub Pages 在国内的访问稳定性不可控：DNS 污染、CDN 节点、运营商差异都会导致
打开缓慢或失败。代码留在 GitHub 没问题（评委可访问性由平台保证），
但**现场演示必须有一个不依赖网络的版本**。这就是 `docs/demo-offline.zip` 存在的理由。
