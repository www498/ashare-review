# 阿里云 ECS 部署演示页

## 结论

在 ECS 上跑一个静态服务，用 `http://公网IP:8080/` 访问。不需要域名、不需要备案、不用装 nginx。

**为什么用 8080**：阿里云大陆地域对未备案的 80/443 会有拦截，非标准端口一般可以直接访问。
答辩演示用 IP 加端口就够了。

---

## 一、安全组放行（先做，否则打不开）

阿里云控制台 → **云服务器 ECS → 实例** → 点进你的实例 → **安全组** → 配置规则 →
**入方向 → 手动添加**：

| 字段 | 填 |
|---|---|
| 端口范围 | `8080/8080` |
| 授权对象 | `0.0.0.0/0` |
| 协议类型 | 自定义 TCP |

保存后立即生效。

---

## 二、把代码放到服务器上

用阿里云控制台的「远程连接」（Workbench）或本地终端 SSH 登录服务器，执行：

```bash
cd /opt
git clone https://gitee.com/www498/ashare-review.git ashare-demo
```

服务器在国内，拉 Gitee 很快，约十几秒。

---

## 三、一键启动

```bash
sudo bash /opt/ashare-demo/tools/serve_demo.sh 8080
```

脚本做四件事：

1. 用 `python3 -m http.server` 起静态服务，根目录指向 `docs/`；
2. 写 systemd 服务 `ashare-demo.service`，开机自启、崩溃自动重启；
3. 放行本机防火墙端口（firewalld / ufw 都兼容）；
4. 从阿里云元数据服务取公网 IP，打印访问地址。

看到下面这两行就成功了：

```
http://<公网IP>:8080/          （入口页，自动跳到演示）
http://<公网IP>:8080/demo.html （演示页）
```

---

## 四、验证

```bash
curl -I http://127.0.0.1:8080/demo.html     # 应返回 200
```

浏览器打开 `http://<公网IP>:8080/`，应该先看到演示入口页，1 秒后跳到看板。
重点确认三块：交易画像（含 16 张形象）、今日 11 手逐笔、卖出回看。

---

## 五、更新与停止

```bash
cd /opt/ashare-demo && git pull          # 拉最新代码
sudo systemctl restart ashare-demo       # 重启（静态文件其实不用重启也能生效）
sudo systemctl stop ashare-demo          # 停
sudo systemctl disable ashare-demo       # 取消开机自启
journalctl -u ashare-demo -n 50          # 看日志
```

---

## 六、常见问题

**打开是 404 / 连接被拒**

1. 安全组没放行 → 回第一步；
2. 端口被占：`ss -lntp | grep 8080`，换一个端口重跑脚本；
3. 服务没起：`systemctl status ashare-demo`。

**页面能开但图片不显示**

`docs/assets/persona/` 没拉全。执行 `git status` 确认工作区干净，或重新 `git clone`。

**想用 80 端口**

需要域名完成 ICP 备案后，用 nginx 反向代理到 8080。答辩前不建议折腾备案（1–2 周）。

**能不能换成 OSS**

可以，把 `docs/` 整个目录上传到 OSS 静态网站托管，绑定域名仍需备案；用 OSS 默认域名访问
会强制下载 HTML 而不是渲染，所以**不如直接开 ECS**。

---

## 七、答辩当天的双保险

| 方案 | 依赖 | 用途 |
|---|---|---|
| PPT | 无 | 主演示，不切窗口 |
| `http://IP:8080/` | 现场网络 + 服务器 | 评委自己点开看 |
| `docs/demo-offline.zip` | 无 | 前两个都挂了时的兜底 |

上台前 10 分钟做一次：

- [ ] 手机流量（不用会场 Wi-Fi）打开 `http://IP:8080/`，确认能开
- [ ] 如果需要重启：`sudo systemctl restart ashare-demo`
- [ ] 记住端口号，别到时候说错
