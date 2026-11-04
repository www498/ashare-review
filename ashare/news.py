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

# 取 80 条：40 条只够覆盖当天几小时，早上跑的时候根本看不到前一晚的消息。
# 用户关心的「昨天晚上的事对今天有什么影响」需要跨夜的时间窗口。
WALLS = ("https://api-one.wallstcn.com/apiv1/content/lives"
         "?channel=global-channel&limit=80")
SINA = ("https://feed.mix.sina.com.cn/api/roll/get"
        "?pageid=153&lid=2516&num=80&page=1")

# 行业 -> 新闻关键词。用于把新闻和自选股挂钩，避免把不相关的宏观条目硬塞进来。
# 覆盖要尽量宽：漏掉一个行业，那个行业的自选股就永远显示「没有相关消息」，
# 用户会以为功能坏了。宁可多匹配几条，也不要整块空着。
IND_KEYS = {
    "贵金属": ["黄金", "白银", "避险", "金价", "央行购金", "美元指数"],
    "有色": ["铜", "铝", "锂", "钴", "镍", "稀土", "有色金属", "矿", "冶炼", "库存",
             "LME", "碳酸锂", "氧化铝", "钼"],
    "化纤": ["化纤", "涤纶", "PTA", "聚酯", "长丝", "粘胶", "氨纶"],
    "电子": ["半导体", "芯片", "算力", "光模块", "AI", "人工智能", "存储", "晶圆",
             "英伟达", "台积电", "封测", "消费电子", "面板"],
    "电气机械": ["光伏", "组件", "硅料", "逆变器", "储能", "装机", "锂电", "电池",
                 "电机", "风电"],
    "设备": ["设备", "光刻", "机床", "招标", "产能", "工程机械"],
    "货币金融": ["银行", "信贷", "贷款", "存款", "净息差", "LPR", "拨备", "降准", "社融"],
    "资本市场": ["券商", "证券", "两融", "IPO", "投行", "经纪", "成交额", "注册制"],
    "保险": ["保险", "保费", "寿险", "财险", "险资"],
    "医药": ["医药", "创新药", "集采", "医保", "药监", "临床", "CXO", "疫苗", "器械"],
    "汽车": ["汽车", "整车", "新能源车", "销量", "车企", "乘用车", "智驾", "零部件"],
    "煤炭": ["煤炭", "动力煤", "焦煤", "秦皇岛", "煤价"],
    "黑色": ["钢铁", "螺纹钢", "铁矿", "钢价", "粗钢"],
    "地产": ["地产", "楼市", "房贷", "土地", "房企", "竣工", "销售面积"],
    "食品": ["白酒", "食品", "调味品", "乳业", "啤酒", "消费复苏"],
    "饮料": ["白酒", "饮料", "啤酒", "乳业"],
    "计算机": ["软件", "信创", "云计算", "数据要素", "网络安全", "大模型"],
    "通信": ["5G", "运营商", "光缆", "卫星", "基站", "6G"],
    "电力": ["电力", "电价", "火电", "水电", "核电", "用电量", "电改"],
    "化工": ["化工", "化肥", "纯碱", "农药", "磷矿", "氟化工"],
    "农业": ["养殖", "生猪", "猪价", "饲料", "种业", "粮食"],
    "农林": ["养殖", "生猪", "猪价", "饲料", "种业", "粮食"],
    "家电": ["家电", "空调", "冰箱", "白电", "以旧换新"],
    "建筑": ["基建", "建筑", "开工", "专项债", "城投"],
}
# 宏观事件 → 受影响的行业。
#
# 为什么不做一个全局宏观模块：那样的结论对每只票都一样，落不到操作上。
# 但也不能把「中期选举」挂给所有股票——军工和白酒受它的影响完全不同。
# 所以这里显式写明「这件事影响哪些行业」，匹配到才挂，匹配不到就不提。
# 只收高确定性的几条，宁可少挂也不要瞎关联。
MACRO_TAGS = [
    (("大选", "中期选举", "选举", "特朗普", "白宫", "国会"),
     ("贵金属", "有色", "军工", "农业"), "风险偏好与美元"),
    (("美联储", "议息", "点阵图", "非农", "CPI", "鲍威尔"),
     ("贵金属", "有色", "地产", "电子"), "利率与美元"),
    (("俄乌", "中东", "地缘", "冲突", "停火", "袭击"),
     ("贵金属", "军工", "化工", "电力"), "避险与供给"),
    (("关税", "制裁", "出口管制", "实体清单", "反倾销"),
     ("电子", "电气机械", "汽车", "机械设备"), "供应链与出口"),
    (("OPEC", "原油", "油价", "减产", "炼化"),
     ("化工", "化纤", "汽车", "电力"), "成本与通胀"),
    (("降准", "降息", "LPR", "社融", "逆回购", "MLF"),
     ("货币金融", "资本市场", "地产", "建筑"), "流动性"),
]

GENERAL_KEYS = ["央行", "降准", "降息", "财政", "政策", "证监会", "汇率", "人民币",
                "美联储", "关税", "PMI", "CPI", "政治局", "国常会", "外资"]


def _today():
    return dt.date.today().isoformat()


def _cache_path(day=None):
    return os.path.join(CACHE_DIR, f"news_{day or _today()}.json")


def _clean(t):
    t = re.sub(r"<[^>]+>", "", str(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def _headline(t, n=58):
    """取一条快讯的「标题」，不要整段正文。

    华尔街见闻的 content_text 常常是几百字的通稿全文（外事会见尤其长），
    整段塞进页面会把一张卡片撑成一屏，而且真正的信息在第一句。
    """
    t = _clean(t)
    for sep in ("。", "！", "？", "；", "|"):
        i = t.find(sep)
        if 8 <= i <= n:
            return t[:i]
    return t[:n] + ("…" if len(t) > n else "")


def _stamp(ts):
    """时间戳 → (HH:MM, YYYY-MM-DD)。带日期是为了区分昨晚和今早的消息。"""
    if not ts:
        return "", ""
    try:
        t = dt.datetime.fromtimestamp(int(ts))
        return t.strftime("%H:%M"), t.strftime("%Y-%m-%d")
    except Exception:
        return "", ""


def _from_wallst(rets):
    try:
        r = requests.get(WALLS, headers=HDRS, timeout=12)
        items = (r.json().get("data") or {}).get("items") or []
    except Exception:
        return
    for it in items:
        txt = _headline(it.get("title") or it.get("content_text"))
        if not txt or len(txt) < 8:
            continue
        when, day = _stamp(it.get("display_time"))
        rets.append({"time": when, "date": day, "title": txt, "source": "华尔街见闻"})


def _from_sina(rets):
    try:
        r = requests.get(SINA, headers=HDRS, timeout=12)
        items = (r.json().get("result") or {}).get("data") or []
    except Exception:
        return
    for it in items:
        title = _headline(it.get("title"))
        if not title:
            continue
        when, day = _stamp(it.get("ctime"))
        rets.append({"time": when, "date": day, "title": title, "source": "新浪财经"})


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


def _ind_keys(ind):
    """行业名 → 关键词。

    行业名来自 baostock，是「货币金融」「电气机械」这种短分类，
    和口语里的「银行」「光伏」对不上。所以不能精确查表，要双向包含匹配：
    「资本市场」能命中「资本市场服务」，「电气机械」能带出光伏和电池关键词。
    没覆盖的行业退化为行业名本身，至少还能靠名字直接匹配标题。
    """
    if not ind:
        return []
    keys = []
    for k, v in IND_KEYS.items():
        if k in ind or ind in k:
            keys.extend(v)
    for suf in ("设备", "行业", "制造", "服务", "开采", "加工", "机械"):
        if ind.endswith(suf) and len(ind) > len(suf):
            keys.append(ind[:-len(suf)])
    keys.append(ind)
    return list(dict.fromkeys(keys))


# 个股公告常带「证监会」「央行」字样（比如立案告知书），但那不是宏观事件。
# 判断宏观时必须先把这类排掉，否则解释「大盘为什么动」时引用的会是某家公司的雷。
_NOT_MACRO = ("立案", "收到", "公告", "公司", "股份", "股东", "答复", "回复",
              "减持", "质押", "问询", "停牌")


def macro_headlines(items, n=5):
    """全市场层面的标题，用来解释「大盘 / 板块为什么动」。"""
    out = []
    for it in items:
        t = it.get("title") or ""
        if not t or any(w in t for w in _NOT_MACRO):
            continue
        if any(k in t for k in GENERAL_KEYS):
            out.append(t)
    return out[:n]


def _macro_keys(ind):
    """该行业的宏观驱动词。中期选举只影响贵金属/有色/军工，不该挂给白酒。"""
    if not ind:
        return []
    keys = []
    for words, inds, _why in MACRO_TAGS:
        if any(i in ind or ind in i for i in inds):
            keys.extend(words)
    return list(dict.fromkeys(keys))


def attach(items, targets, limit=3, spread=3):
    """把快讯挂到每一只自选股上，而不是单独列成一个模块。

    只认两级别：标题里直接提到这只票（个股），或命中它所属行业的关键词（行业）。
    **不做宏观兜底**——试过一版，结果是「王毅会见越南外长」被挂到每一只票下面，
    因为标题里有「政治局」。那种匹配对操作零价值，只会让人不再相信这块内容。
    没有相关消息就留空，页面会明确写出「今天没有直接相关的消息」。

    spread：同一条新闻最多挂给几只股票。一条行业新闻挂满整个自选股列表，
    等于没有个性化。

    targets: {code: {"name": 名称, "industry": 行业}}
    返回 {code: [{title, time, source, level, key}]}
    """
    out = {}
    taken = {}          # 标题 -> 已被几只票占用
    for code, t in (targets or {}).items():
        name = (t.get("name") or "").strip()
        ind = (t.get("industry") or "").strip()
        hits, used = [], set()

        if len(name) >= 2:
            for it in items:
                if name in it["title"] and taken.get(it["title"], 0) < spread:
                    hits.append({**it, "level": "个股", "key": name})
                    used.add(it["title"])
                    taken[it["title"]] = taken.get(it["title"], 0) + 1
                    break

        if len(hits) < limit:
            for k in _ind_keys(ind):
                if len(k) < 2:
                    continue
                for it in items:
                    if (it["title"] in used or k not in it["title"]
                            or taken.get(it["title"], 0) >= spread):
                        continue
                    hits.append({**it, "level": "行业", "key": k})
                    used.add(it["title"])
                    taken[it["title"]] = taken.get(it["title"], 0) + 1
                    break

        # 宏观事件排在最后：它解释的是「这个行业今天为什么动」，
        # 优先级低于点名这只票的消息，但比没有强。
        # 最多两条，且优先挑真正提到市场影响的——
        # 「伊朗回应中期选举」和「民主党拿下国会、股市上涨」说的是一件事，
        # 但后者才有解释力。
        if len(hits) < limit:
            cand = []
            for k in _macro_keys(ind):
                for it in items:
                    if it["title"] in used or taken.get(it["title"], 0) >= spread:
                        continue
                    if k in it["title"]:
                        cand.append((it, k))
                        break
            mkt = ("股市", "市场", "风险", "利好", "利空", "资金", "涨", "跌")
            cand.sort(key=lambda x: 0 if any(w in x[0]["title"] for w in mkt) else 1)
            for it, k in cand[:2]:
                if it["title"] in used:
                    continue
                hits.append({**it, "level": "宏观", "key": k})
                used.add(it["title"])
                taken[it["title"]] = taken.get(it["title"], 0) + 1

        if hits:
            out[code] = hits[:limit]
    return out


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
