# -*- coding: utf-8 -*-
"""
行业分类与板块联动归因。

行业映射来自 baostock（证监会行业分类，79 类），一次性拉取后缓存 30 天。
有了映射，就能回答复盘里最常问的问题：这只票今天是「板块联动」还是「个股独立事件」。

注意区分两套口径：
- 本模块的行业统计，基于我们自己的沪A 全量实时快照，与报告里的宽度指标完全自洽
- stock_sector_fund_flow_rank 是东财的板块资金流，分类更细（申万），但口径独立
"""
import json
import os
import re
import time

import numpy as np

from .data import ROOT

CACHE = os.path.join(ROOT, "data", "industry.json")
TTL = 86400 * 30

# 证监会分类名称太长，展示时截断
SHORT = {
    "J66货币金融服务": "货币金融", "J67资本市场服务": "资本市场", "J68保险业": "保险",
    "C39计算机、通信和其他电子设备制造业": "电子设备", "C35专用设备制造业": "专用设备",
    "C36汽车制造业": "汽车", "C37铁路、船舶、航空航天和其他运输设备制造业": "运输设备",
    "C38电气机械和器材制造业": "电气机械", "C26化学原料和化学制品制造业": "化工",
    "C27医药制造业": "医药", "C30非金属矿物制品业": "非金属矿物", "C31黑色金属冶炼和压延加工业": "钢铁",
    "C32有色金属冶炼和压延加工业": "有色冶炼", "C33金属制品业": "金属制品",
    "B06煤炭开采和洗选业": "煤炭", "B07石油和天然气开采业": "石油开采",
    "B09有色金属矿采选业": "有色金属", "B08黑色金属矿采选业": "黑色金属",
    "D44电力、热力生产和供应业": "电力", "D45燃气生产和供应业": "燃气", "D46水的生产和供应业": "水务",
    "E48土木工程建筑业": "土木工程", "E50建筑装饰和其他建筑业": "建筑装饰",
    "F51批发业": "批发", "F52零售业": "零售", "G53铁路运输业": "铁路运输",
    "G54道路运输业": "道路运输", "G55水上运输业": "水上运输", "G56航空运输业": "航空运输",
    "I65软件和信息技术服务业": "软件信息", "K70房地产业": "房地产",
    "N77生态保护和环境治理业": "环保", "R85新闻和出版业": "出版传媒",
    "C13农副食品加工业": "食品加工", "C15酒、饮料和精制茶制造业": "酒饮料",
    "C17纺织业": "纺织", "C22造纸和纸制品业": "造纸", "C25石油加工、炼焦和核燃料加工业": "石油加工",
    "C28化学纤维制造业": "化纤", "C29橡胶和塑料制品业": "橡塑",
}


# 未精确匹配时的关键词兜底（顺序敏感，先匹配先生效）
KEYMAP = [
    ("广播电视", "传媒影视"), ("新闻出版", "出版传媒"), ("互联网", "互联网"),
    ("软件", "软件信息"), ("电信", "电信"), ("货币金融", "银行"), ("资本市场", "券商"),
    ("保险", "保险"), ("其他金融", "多元金融"),
    ("医药", "医药"), ("化学原料", "化工"), ("化学纤维", "化纤"), ("石油加工", "石化"),
    ("橡胶", "橡塑"), ("非金属矿物", "建材"), ("黑色金属冶炼", "钢铁"), ("有色金属冶炼", "有色冶炼"),
    ("有色金属矿", "有色金属"), ("煤炭", "煤炭"), ("石油和天然气", "石油开采"),
    ("通用设备", "通用设备"), ("仪器仪表", "仪器仪表"), ("汽车", "汽车"),
    ("铁路、船舶", "运输设备"), ("电气机械", "电气机械"), ("金属制品", "金属制品"),
    ("农副食品", "食品加工"), ("食品制造", "食品加工"), ("酒、饮料", "酒饮料"),
    ("纺织服装", "纺织服装"), ("纺织", "纺织"), ("皮革", "皮革制鞋"), ("木材", "木材"),
    ("家具", "家具"), ("造纸", "造纸"), ("印刷", "印刷"), ("文教", "文娱用品"),
    ("废弃资源", "环保资源"), ("生态保护", "环保"), ("电力、热力", "电力"), ("燃气", "燃气"),
    ("开采专业", "采掘服务"), ("开采辅助", "采掘服务"),
    ("水的生产", "水务"), ("土木工程", "土木工程"), ("房屋建筑", "房建"), ("建筑安装", "建筑安装"),
    ("建筑装饰", "建筑装饰"), ("批发", "批发"), ("零售", "零售"), ("铁路运输", "铁路运输"),
    ("道路运输", "道路运输"), ("水上运输", "水上运输"), ("航空运输", "航空运输"),
    ("装卸搬运", "物流"), ("仓储", "仓储"), ("邮政", "邮政"), ("房地产", "房地产"),
    ("研究和试验", "科研服务"), ("专业技术服务", "专业服务"), ("商务服务", "商务服务"),
    ("住宿", "酒店旅游"), ("餐饮", "酒店旅游"), ("教育", "教育"), ("卫生", "医疗"),
    ("文化艺术", "文化"), ("公共设施", "公共设施"), ("水利", "水利"), ("农业", "农林牧渔"),
    ("林业", "农林牧渔"), ("畜牧", "农林牧渔"), ("渔业", "农林牧渔"),
]


def _short(name):
    if not name:
        return "未分类"
    if name in SHORT:
        return SHORT[name]
    s = re.sub(r"^[A-Z]\d+", "", name)          # 去掉 C39 / J66 这类前缀
    s = re.sub(r"[、，,（）()\s]", "", s)
    for k, v in KEYMAP:
        if k in s:
            return v
    return s[:5]


def fetch(force=False):
    """返回 {code6: 行业短名}。缓存里存原始分类名，短名在读取时生成，
    这样调整显示规则不用重新拉数据。"""
    if not force and os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                obj = json.load(f)
            if time.time() - obj.get("ts", 0) < TTL:
                return {k: _short(v) for k, v in obj["map"].items()}
        except Exception:
            pass

    import baostock as bs
    bs.login()
    rs = bs.query_stock_industry()
    raw = {}
    while rs.error_code == "0" and rs.next():
        row = rs.get_row_data()
        code, ind = row[1], row[3]
        if code.startswith("sh.") and ind:
            raw[code[3:]] = ind
    bs.logout()

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "map": raw}, f, ensure_ascii=False)
    return {k: _short(v) for k, v in raw.items()}


def industry_stats(quotes, mapping, min_n=5):
    """按行业聚合沪A 个股表现。只用有效报价的个股。"""
    groups = {}
    for code, q in quotes.items():
        if not q or q.get("price", 0) <= 0:
            continue
        p = q.get("pct")
        if p is None or np.isnan(p):
            continue
        ind = mapping.get(code, "未分类")
        if ind == "未分类":
            continue
        g = groups.setdefault(ind, {"pcts": [], "amt": 0.0, "up": 0, "down": 0, "names": []})
        g["pcts"].append(p)
        g["amt"] += q.get("amount", 0) / 1e4
        if p > 0.05:
            g["up"] += 1
        elif p < -0.05:
            g["down"] += 1
        g["names"].append(q.get("name", code))

    out = []
    for ind, g in groups.items():
        if len(g["pcts"]) < min_n:
            continue
        out.append({
            "industry": ind, "n": len(g["pcts"]),
            "median": float(np.median(g["pcts"])),
            "mean": float(np.mean(g["pcts"])),
            "up": g["up"], "down": g["down"],
            "up_ratio": g["up"] / len(g["pcts"]),
            "amount": g["amt"],
        })
    return sorted(out, key=lambda x: -x["median"])


def attribute_one(quote, mapping, stats_by_ind, mapping_code=None):
    """判断个股异动是板块联动还是独立事件。
    规则：个股涨跌幅与所属行业中位数同向、且差距 < 行业离散度，判为板块联动。"""
    code = quote.get("code") or mapping_code
    ind = mapping.get(code, "未分类")
    p = quote.get("pct")
    if ind == "未分类" or p is None or np.isnan(p):
        return None
    st = stats_by_ind.get(ind)
    if not st:
        return None
    gap = p - st["median"]
    if abs(gap) < 1.0:
        verdict = "跟随板块"
    elif gap > 0:
        verdict = "强于板块"
    else:
        verdict = "弱于板块"
    return {"industry": ind, "ind_median": st["median"], "gap": gap,
            "verdict": verdict, "ind_n": st["n"], "ind_up_ratio": st["up_ratio"]}


def attribute_watchlist(anomalies, mapping, stats):
    """给自选股逐只贴归因，返回带 attr 字段的新列表"""
    by_ind = {s["industry"]: s for s in stats}
    out = []
    for a in anomalies:
        out.append({**a, "attr": attribute_one(a, mapping, by_ind)})
    return out
