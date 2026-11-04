# -*- coding: utf-8 -*-
"""
当前账号上下文。

为什么需要它：watchlist / positions / statement / report / web 等模块
分散在十几处用 ROOT 拼路径。多用户改造如果逐个加 uid 参数，
改动面大且容易漏，漏掉的那处就会串号——把 A 的持仓写进 B 的账号。

改为集中式上下文：进程启动时设定一次当前账号，所有模块通过
user_paths() 取路径。run_review.py 由 --user 指定，
importer 的每个请求在子进程里以 --user 启动，天然隔离。

默认 uid 为 None，此时全部回退到项目根目录，
保持老用法（直接 python run_review.py）可用，不破坏既有脚本。
"""
import os
import threading

_state = threading.local()
_default_uid = None


def set_user(uid):
    """设定当前进程/线程的账号。None 表示单用户兼容模式。"""
    global _default_uid
    _state.uid = uid
    _default_uid = uid


def current_uid():
    return getattr(_state, "uid", None) or _default_uid


def user_paths():
    from . import auth
    return auth.paths(current_uid())


def watchlist_file():
    return user_paths()["watchlist"]


def positions_file():
    return user_paths()["positions"]


def reports_dir():
    p = user_paths()["reports"]
    os.makedirs(p, exist_ok=True)
    return p


def snapshots_dir():
    p = user_paths()["snapshots"]
    os.makedirs(p, exist_ok=True)
    return p


def user_root():
    return user_paths()["root"]


def label():
    """用于日志与报告页脚的账号标识。"""
    uid = current_uid()
    return uid or "default"
