# -*- coding: utf-8 -*-
"""
交易日历。

为什么需要：原来全项目只用 weekday() < 5 判断，于是
1. 国庆/春节照样触发定时任务，拉到的是上一交易日的陈旧盘口，
   再被 upsert_today() 当成新的一天写进历史表，污染温度趋势；
2. 连板的「上一交易日」按自然日算，长假后必然错位。

实现取舍：不引入新依赖、不额外请求网络。
优先用本地历史表 breadth_history.csv 里**已经确认存在行情**的日期，
这是最可信的交易日证据；表里没有的日期（如未来、或表更新前）
退回「工作日 + 内置节假日表」判断。
节假日表需要每年更新一次，缺失时会退化为仅排除周末，
因此 is_trading_day 对未知年份返回的结果标记为不确定。
"""
import datetime as dt
import os

from .data import ROOT

HIST_CSV = os.path.join(ROOT, "data", "breadth_history.csv")

# 中国大陆证券市场休市日（节假日，不含周末）。每年需更新。
HOLIDAYS = {
    # 2025
    "2025-01-01",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04",
    "2025-04-04", "2025-05-01", "2025-05-02", "2025-05-05",
    "2025-06-02", "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07",
    "2025-10-08",
    # 2026（注意：10-08 经本地历史表证实有行情，不是休市日）
    "2026-01-01", "2026-01-02",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-23", "2026-02-24",
    "2026-04-06", "2026-05-01", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-09-25",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}

_KNOWN_YEARS = {2025, 2026}
_cache = {"mtime": None, "days": frozenset()}


def _known_days():
    """历史表里出现过的日期 = 确认有行情的交易日。"""
    try:
        mtime = os.path.getmtime(HIST_CSV)
    except OSError:
        return frozenset()
    if _cache["mtime"] == mtime:
        return _cache["days"]
    days = set()
    try:
        with open(HIST_CSV, encoding="utf-8-sig") as f:
            header = f.readline().strip().split(",")
            try:
                di = header.index("date")
            except ValueError:
                di = 0
            for line in f:
                parts = line.strip().split(",")
                if len(parts) > di and parts[di]:
                    days.add(parts[di])
    except Exception:
        return frozenset()
    _cache["mtime"], _cache["days"] = mtime, frozenset(days)
    return _cache["days"]


def _to_date(d):
    return dt.date.fromisoformat(d) if isinstance(d, str) else d


def is_trading_day(d=None):
    """d 是否为交易日。历史表已收录 -> 确定为真；否则按工作日 + 节假日表推断。"""
    d = _to_date(d or dt.date.today())
    if d.isoformat() in _known_days():
        return True
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in HOLIDAYS


def calendar_is_certain(d=None):
    """节假日表是否覆盖该年份。False 表示 is_trading_day 的结果仅为「非周末」推断。"""
    d = _to_date(d or dt.date.today())
    return d.year in _KNOWN_YEARS


def prev_trading_day(d=None):
    """d 之前最近的一个交易日。"""
    d = _to_date(d or dt.date.today())
    cur = d - dt.timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cur):
            return cur
        cur -= dt.timedelta(days=1)
    return cur


def trading_days_between(a, b):
    """(a, b] 区间内的交易日个数。a == b 时为 0。"""
    a, b = _to_date(a), _to_date(b)
    if b <= a:
        return 0
    n, cur = 0, a + dt.timedelta(days=1)
    while cur <= b:
        if is_trading_day(cur):
            n += 1
        cur += dt.timedelta(days=1)
    return n
