# -*- coding: utf-8 -*-
"""
轻量调度器：替代 Windows 计划任务（本机 schtasks 被安全策略禁用）。

常驻运行，工作日 11:35 触发午盘总结、15:05 触发收盘总结。
用法：
    python scheduler.py          # 常驻，Ctrl+C 退出
    python scheduler.py --test   # 立即各跑一次，验证链路
开机自启：把 scheduler.vbs 的快捷方式放进 shell:startup 目录即可。
"""
import datetime as dt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
USER_FILE = os.path.join(HERE, "launch_user.txt")


def default_user():
    """读取本地账号配置。没有配置文件时返回 None（单用户模式，写项目根目录）。"""
    try:
        with open(USER_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None
TASKS = [(11, 35, "am"), (15, 5, "pm")]
FIRED = set()


def run(session, user=None):
    cmd = [sys.executable, os.path.join(HERE, "run_review.py"), "--session", session]
    if session == "pm":
        cmd.append("--forecast")
    if user:
        cmd += ["--user", user]
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] 触发 {session} 复盘 ...", flush=True)
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    ok = "OK" if r.returncode == 0 else f"失败({r.returncode})"
    print(f"[{ts}] {session} 完成：{ok}", flush=True)
    if r.returncode != 0 and r.stderr:
        print(r.stderr[-500:], flush=True)


def main():
    global FIRED
    # 账号：命令行 --user 优先，其次 launch_user.txt，都没有则为单用户模式
    user = None
    if "--user" in sys.argv:
        i = sys.argv.index("--user")
        user = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    user = user or default_user()
    tag = f"账号 {user}" if user else "单用户模式（写项目根目录）"

    if "--test" in sys.argv:
        for _, _, s in TASKS:
            run(s, user)
        return

    print(f"调度器已启动：交易日 11:35 午盘、15:05 收盘。Ctrl+C 退出。", flush=True)
    print(f"[账号] {tag}", flush=True)
    try:
        from ashare.tcal import is_trading_day, calendar_is_certain
    except Exception:
        is_trading_day = lambda d=None: (d or dt.date.today()).weekday() < 5
        calendar_is_certain = lambda d=None: False
    if not calendar_is_certain():
        print(f"[提示] 节假日表未覆盖 {dt.date.today().year} 年，"
              f"非交易日仅能按周末排除，请更新 ashare/tcal.py 的 HOLIDAYS。", flush=True)

    announced = None
    while True:
        now = dt.datetime.now()
        today = now.date()
        trading = is_trading_day(today)
        if not trading and announced != today:
            print(f"[{now:%H:%M:%S}] {today} 非交易日，今日不触发。", flush=True)
            announced = today
        if trading:
            for h, m, s in TASKS:
                key = (today, s)
                if now.hour == h and now.minute == m and key not in FIRED:
                    run(s, user)
                    FIRED.add(key)
        # 每天清一次，避免集合无限增长
        FIRED = {k for k in FIRED if k[0] == today}
        time.sleep(20)


if __name__ == "__main__":
    main()
