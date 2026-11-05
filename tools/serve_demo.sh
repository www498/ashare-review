#!/usr/bin/env bash
# 在阿里云 ECS 上把演示页跑成一个可访问的站点。
#
# 为什么用 8080 而不是 80
# ----------------------
# 阿里云大陆地域对未备案的 80/443 有拦截，换一个非标准端口通常可以直接访问。
# 答辩演示用 IP:8080 就够了，不需要域名、不需要备案。
#
# 用法（在服务器上，仓库根目录执行）：
#   sudo bash tools/serve_demo.sh            # 默认 8080 端口
#   sudo bash tools/serve_demo.sh 9000       # 换端口
#
# 停止：systemctl stop ashare-demo
# 日志：journalctl -u ashare-demo -n 50
set -e

PORT="${1:-8080}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${2:-$ROOT/docs}"

if [ ! -f "$DIR/demo.html" ]; then
  echo "找不到 $DIR/demo.html，先确认仓库完整"
  exit 1
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "缺 python3。CentOS: yum install -y python3　Ubuntu: apt install -y python3"
  exit 1
fi

echo "站点目录：$DIR"
echo "监听端口：$PORT"

cat >/etc/systemd/system/ashare-demo.service <<EOF
[Unit]
Description=Ashare review demo (static)
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$PY -m http.server $PORT --bind 0.0.0.0 --directory $DIR
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ashare-demo >/dev/null 2>&1
systemctl restart ashare-demo

# 本机防火墙放行（阿里云安全组还要单独放行，脚本改不了）
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --add-port="$PORT"/tcp --permanent >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
fi
if command -v ufw >/dev/null 2>&1; then
  ufw allow "$PORT"/tcp >/dev/null 2>&1 || true
fi

sleep 1
IP="$(curl -s --max-time 3 http://100.100.100.200/latest/meta-data/eipv4 || true)"
if [ -z "$IP" ]; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

if systemctl is-active --quiet ashare-demo; then
  echo
  echo "已启动。访问地址："
  echo "  http://$IP:$PORT/          （入口页，自动跳到演示）"
  echo "  http://$IP:$PORT/demo.html （演示页）"
  echo
  echo "如果打不开：到阿里云控制台 → 实例 → 安全组 → 入方向，放行 TCP $PORT。"
else
  echo "启动失败，看日志：journalctl -u ashare-demo -n 50 --no-pager"
  exit 1
fi
