# -*- coding: utf-8 -*-
"""当天财经新闻，用于给自选股的涨跌补充「消息面」。

为什么需要
----------
归因能算出「板块涨了 3 个点」，但说不清板块为什么涨。财经快讯里往往
就写着原因（央行操作、某个政策、海外商品价格）。把它接进来，
「为什么涨」这条链才完整。

数据来源（都是公开接口，无需 key）
--------------------------------
华尔街见闻实时快讯  宏观、政策、海外
新浪财经滚动        国内财经、个股

设计原则
--------
1. **只取标题**，不抓正文。标题通常已含关键事实，正文会引入版权与体积问题。
2. 按当天缓存到 data/news_YYYY-MM-DD.json，一天只抓一次，断网时用缓存。
3. 抓不到就返回空列表，页面上整块不渲染 —— 消息面是补充，不是主链路。
4. 新闻只是「线索」：页面上必须标明来自公开快讯、未做事实核验，
   让大模型引用时也只能复述标题，不能扩写。
"""
import datetime as dt
import json
import os
import re

import requests

from .data import ROOT

CACHE_DIR = os.path.join(ROOT, "data")
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

WALLS = ("https://api-one.wallstcn.com/apiv1/content/lives"
         "?channel=global-channel&limit=40")
SINA = ("https://feed.mix.sina.com.cn/api/roll/get"
        "?pageid=153&lid=2516&num=40&page=1")

# 行业 -> 新闻关键词。用于把新闻和自选股挂钩，避免把不相关的宏观条目硬塞进来
IND_KEYS = {
    "贵金属": ["黄金", "白银", "避险", "美联储", "降息", "加息", "金价", "央行购金"],
    "有色金属": ["铜", "铝", "锂", "钴", "镍", "稀土", "有色金属", "矿", "冶炼", "库存"],
    "电子设备": ["半导体", "芯片", "算力", "光模块", "AI", "人工智能", "存储", "晶圆", "英伟达"],
    "专用设备": ["设备", "光刻", "光伏", "锂电", "产能", "招标"],
}
GENERAL_KEYS = ["央行", "降准", "降息", "财政", "政策", "证监会", "汇率", "人民币",
                "美联储", "关税", "PMI", "CPI", "政治局", "国常会", "外资"]


def _today():
    return dt.date.today().isoformat()


def _cache_path(day=None):
    return os.path.join(CACHE_DIR, f"news_{day or _today()}.json")


def _clean(t):
    t = re.sub(r"<[^>]+>", "", str(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def _from_wallst(rets):
    try:
        r = requests.get(WALLS, headers=HDRS, timeout=12)
        items = (r.json().get("data") or {}).get("items") or []
    except Exception:
        return
    for it in items:
        txt = _clean(it.get("content_text") or it.get("title"))
        if not txt or len(txt) < 8:
            continue
        ts = it.get("display_time")
        when = (dt.datetime.fromtimestamp(int(ts)).strftime("%H:%M")
                if ts else "")
        rets.append({"time": when, "title": txt[:120], "source": "华尔街见闻"})


def _from_sina(rets):
    try:
        r = requests.get(SINA, headers=HDRS, timeout=12)
        items = (r.json().get("result") or {}).get("data") or []
    except Exception:
        return
    for it in items:
        title = _clean(it.get("title"))
        if not title:
            continue
        ts = it.get("ctime")
        when = (dt.datetime.fromtimestamp(int(ts)).strftime("%H:%M")
                if ts else "")
        rets.append({"time": when, "title": title, "source": "新浪财经"})


def fetch(force=False):
    """返回当天的新闻列表（已按时间倒序）。失败返回空列表，不抛异常。"""
    day = _today()
    fp = _cache_path(day)
    if not force and os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    out = []
    _from_wallst(out)
    _from_sina(out)
    # 去重（两个源偶有重复标题）
    seen, uniq = set(), []
    for x in out:
        k = x["title"][:24]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)

    if uniq:
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(uniq, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    return uniq


def match(items, codes=None, names=None, industries=None, limit=8):
    """挑出与自选股相关的新闻：命中股票名优先，其次行业关键词，最后宏观政策。"""
    codes, names = codes or [], names or []
    industries = industries or []
    keys = []
    for n in names:
        if n and len(n) >= 2:
            keys.append(("个股", n))
    for ind in industries:
        for k in IND_KEYS.get(ind, []):
            keys.append((ind, k))
    for k in GENERAL_KEYS:
        keys.append(("宏观", k))

    hit, used = [], set()
    for level in ("个股", "宏观"):
        for it in items:
            if it["title"] in used:
                continue
            for tag, k in keys:
                if tag == level and k in it["title"]:
                    hit.append({**it, "tag": tag, "key": k})
                    used.add(it["title"])
                    break
    # 行业级别的命中放在中间层
    ind_hits = []
    for it in items:
        if it["title"] in used:
            continue
        for tag, k in keys:
            if tag not in ("个股", "宏观") and k in it["title"]:
                ind_hits.append({**it, "tag": tag, "key": k})
                used.add(it["title"])
                break
    merged = ([h for h in hit if h["tag"] == "个股"] + ind_hits
              + [h for h in hit if h["tag"] == "宏观"])
    return merged[:limit]
