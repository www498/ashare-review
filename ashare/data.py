# -*- coding: utf-8 -*-
"""
数据层：全部走腾讯 qt.gtimg.cn（批量、无限流），避开东财 push2 的 IP 限流。
沪A 全量约 2318 只，60 只/请求，6 并发，约 1~2 秒。
"""
import json, os, time
import requests
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data")
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
QT_URL = "https://qt.gtimg.cn/q="
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq"


def _f(x):
    """腾讯字段里的空值/'-' 统一转 nan"""
    try:
        v = float(x)
        return v
    except Exception:
        return float("nan")


def _parse(chunk):
    out = []
    for line in chunk.split(";"):
        if "~" not in line:
            continue
        p = line.split("~")
        if len(p) < 50:
            continue
        try:
            out.append({
                "code": p[2].strip(),
                "name": p[1].strip(),
                "price": _f(p[3]),
                "prev_close": _f(p[4]),
                "open": _f(p[5]),
                "vol": _f(p[6]),          # 手
                "chg": _f(p[31]),
                "pct": _f(p[32]),         # 涨跌幅 %
                "high": _f(p[33]),
                "low": _f(p[34]),
                "amount": _f(p[37]),      # 万元
                "turnover": _f(p[38]),    # 换手率 %
                "pe": _f(p[39]),
                "amp": _f(p[43]),         # 振幅 %
                "float_mv": _f(p[44]),    # 流通市值 亿
                "total_mv": _f(p[45]),    # 总市值 亿
                "pb": _f(p[46]),
                "limit_up": _f(p[47]),
                "limit_down": _f(p[48]),
                "vol_ratio": _f(p[49]),   # 量比
                "ts": p[30].strip(),
            })
        except Exception:
            continue
    return out


def _fetch_chunk(codes_with_prefix):
    q = ",".join(codes_with_prefix)
    for attempt in range(3):
        try:
            r = requests.get(QT_URL + q, headers=HEADERS, timeout=10)
            r.encoding = "gbk"
            return _parse(r.text)
        except Exception:
            time.sleep(0.4 * (attempt + 1))
    return []


def fetch_symbols(symbols, batch=60, workers=6):
    """批量拉实时行情。symbols 为带前缀的完整代码，如 sh000001 / sh600519。"""
    if not symbols:
        return []
    reqs = [symbols[i:i + batch] for i in range(0, len(symbols), batch)]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for part in ex.map(_fetch_chunk, reqs):
            rows.extend(part)
    return rows


def fetch_quotes(codes, batch=60, workers=6):
    """批量拉实时行情。codes 为 6 位代码，自动加 sh 前缀。"""
    if not codes:
        return {}
    reqs = [[sym(c) for c in codes[i:i + batch]] for i in range(0, len(codes), batch)]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for part in ex.map(_fetch_chunk, reqs):
            rows.extend(part)
    return {r["code"]: r for r in rows}


# ---------------- 代码与前缀 ----------------

def sym(code):
    """6 位代码 -> 带交易所前缀的完整代码。腾讯接口需要这个形式。
    北交所代码有两代：老的 43/83/87 开头，2024 年后统一为 92 开头。"""
    c = str(code).zfill(6)
    if c.startswith(("92", "43", "83", "87")):
        return "bj" + c
    if c[0] == "6":
        return "sh" + c
    if c[0] in "03":
        return "sz" + c
    return "sh" + c


def market_of(code):
    return sym(code)[:2]


def is_a_share(code):
    """是否 A 股个股。排除基金(5xx/15x/16x)、可转债(11x/12x)、B股(900/200)。"""
    c = str(code).zfill(6)
    if len(c) != 6 or not c.isdigit():
        return False
    if c[0] == "6":                       # 沪主板 / 科创板
        return True
    if c[:2] in ("00", "30"):             # 深主板 / 创业板
        return True
    if c[:2] in ("92", "43", "83", "87"): # 北交所
        return True
    return False


def limit_pct(code):
    """涨跌停幅度（%）。主板 10、创业板/科创板 20、北交所 30。"""
    c = str(code).zfill(6)
    if c.startswith(("92", "43", "83", "87")):
        return 30.0
    if c.startswith(("300", "301", "688", "689")):
        return 20.0
    return 10.0


# ---------------- 成分股 ----------------

def _bj_from_sina(pages=8, num=100):
    """新浪 hs_bjs 节点枚举北交所，返回 6 位代码。"""
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "Market_Center.getHQNodeData?page={p}&num={n}&sort=symbol&asc=1&node=hs_bjs")
    out = []
    for p in range(1, pages + 1):
        try:
            r = requests.get(url.format(p=p, n=num),
                             headers={**HEADERS, "Referer": "https://finance.sina.com.cn"},
                             timeout=10)
            js = r.json()
        except Exception:
            break
        if not js:
            break
        for x in js:
            s = x.get("symbol", "")
            if s.startswith("bj"):
                out.append(s[2:])
    return out


def _fetch_universe(markets):
    """按市场拉取在市 A 股代码。markets 为 ('sh',) / ('sh','sz') 等。"""
    codes = []
    try:
        import akshare as ak
    except Exception:
        return []
    if "sh" in markets:
        for s in ("主板A股", "科创板"):
            try:
                df = ak.stock_info_sh_name_code(symbol=s)
                codes += [str(c).zfill(6) for c in df["证券代码"].tolist()]
            except Exception:
                pass
    if "sz" in markets:
        try:
            df = ak.stock_info_sz_name_code(symbol="A股列表")
            col = "A股代码" if "A股代码" in df.columns else "证券代码"
            codes += [str(c).zfill(6) for c in df[col].tolist()]
        except Exception:
            pass
    if "bj" in markets:
        # akshare 的北交所接口走 bse.cn，常被代理拦；改用新浪的 hs_bjs 节点分页枚举
        try:
            codes += _bj_from_sina()
        except Exception:
            pass
    keep = []
    for c in codes:
        m = market_of(c)
        if m in markets:
            keep.append(c)
    return sorted(set(keep))


def sh_universe(force=False):
    """兼容旧调用：只取沪A。"""
    return universe(("sh",), force=force)


def universe(markets=None, force=False):
    """按配置的市场范围返回全量代码。首次拉取后本地缓存 7 天。"""
    from . import config as _C
    markets = markets or getattr(_C, "MARKETS", ("sh",))
    key = "-".join(markets)
    path = os.path.join(CACHE_DIR, f"universe_{key}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        if time.time() - obj.get("ts", 0) < 86400 * 7:
            return obj["codes"]
    codes = _fetch_universe(markets)
    if codes:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "codes": codes}, f)
    return codes


# ---------------- 指数历史 ----------------

def index_daily(sym, n=6):
    """腾讯日K，返回 [date, open, close, high, low, volume] 列表（由旧到新）"""
    try:
        r = requests.get(KLINE_URL.format(sym=sym, n=n), headers=HEADERS, timeout=10)
        d = r.json()["data"][sym]
        k = d.get("day") or d.get("qfqday") or []
        return k
    except Exception:
        return []


# ---------------- 市场宽度参考（乐咕，全市场口径）----------------

def market_activity():
    try:
        import akshare as ak
        df = ak.stock_market_activity_legu()
        return {str(r["item"]): r["value"] for _, r in df.iterrows()}
    except Exception:
        return {}


# ---------------- 快照缓存 ----------------

def save_snapshot(name, obj):
    from .context import snapshots_dir
    path = snapshots_dir()
    os.makedirs(path, exist_ok=True)
    fp = os.path.join(path, name + ".json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    return fp


def load_snapshot(name):
    from .context import snapshots_dir
    fp = os.path.join(snapshots_dir(), name + ".json")
    if not os.path.exists(fp):
        return None
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def list_snapshots(session=None):
    """已有快照名（形如 20261102_pm），按日期从新到旧。
    session 传 'am'/'pm' 时只返回该时段的。"""
    from .context import snapshots_dir
    path = snapshots_dir()
    if not os.path.isdir(path):
        return []
    names = [f[:-5] for f in os.listdir(path) if f.endswith(".json")]
    if session:
        names = [n for n in names if n.endswith("_" + session)]
    return sorted(names, reverse=True)


def latest_snapshot(session=None):
    """最近一份可用快照名，没有则 None。离线演示兜底用。"""
    names = list_snapshots(session)
    return names[0] if names else None
