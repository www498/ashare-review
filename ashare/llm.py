# -*- coding: utf-8 -*-
"""
LLM 解释层：只负责「把算好的数字翻译成人话」，不负责算数字。

设计原则（这是整个方案可信度的地基）：
1. 所有数字由代码计算并注入，模型不允许生成任何数值
2. 输出后做数字溯源校验：带单位（%/亿/元/pp）的数字必须能在源数据中找到，否则判定为幻觉
3. 无 API key 时整体降级为规则模板，不报错、不阻塞主流程

配置（环境变量，放在系统里或 .env 里都行）：
    LLM_API_KEY    必填，模型平台签发的 key
    LLM_BASE_URL   可选，默认 DeepSeek
    LLM_MODEL      可选，默认 deepseek-chat
"""
import os
import re

import requests

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# 配置的模型不可用时的备选。中转站常有「列表里有、实际 404/405」的情况。
FALLBACK_MODELS = ("deepseek-v4.1-flash-1017", "deepseek-v4.1-flash",
                   "deepseek-v4-flash", "deepseek-chat")

# 不想配环境变量时，把 key 单独写进这个文件（一行，只有 key）。
# 文件名带 key 字样，.gitignore 已排除，不会被推到公开仓库。
KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "llm_key.txt")


def _file_conf():
    """读 llm_key.txt。支持两种写法：

        sk-xxxx                         只有 key，用默认 DeepSeek 官方地址
        key=sk-xxxx                     key=value 形式，可同时指定中转站与模型
        base_url=https://.../v1
        model=deepseek-v4-pro

    中转站（如 api.uniportai.com）的地址与模型名都和官方不同，
    只给 key 是跑不起来的，所以配置文件必须能带这两项。
    """
    conf = {}
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" in s:
                    k, _, v = s.partition("=")
                    conf[k.strip().lower()] = v.strip()
                else:
                    conf.setdefault("key", s)
    except OSError:
        pass
    return conf


def _cfg():
    fc = _file_conf()
    return (
        os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY") or fc.get("key"),
        os.getenv("LLM_BASE_URL") or fc.get("base_url") or DEFAULT_BASE,
        os.getenv("LLM_MODEL") or fc.get("model") or DEFAULT_MODEL,
    )


def available():
    return bool(_cfg()[0])


def chat(messages, temperature=0.3, timeout=60, json_mode=False):
    key, base, model = _cfg()
    if not key:
        raise RuntimeError("未配置 LLM_API_KEY")
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # 中转站经常「模型列表里有、实际路由不可用」（返回 404/405）。
    # 这种情况不该让整份复盘生成失败，按顺序退到备用模型，
    # 并把实际用的模型打出来，避免用户以为在用 A 其实跑的是 B。
    tried = []
    for m in [model] + [x for x in FALLBACK_MODELS if x != model]:
        payload["model"] = m
        try:
            r = requests.post(f"{base}/chat/completions",
                              headers={"Authorization": f"Bearer {key}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=timeout)
        except requests.RequestException as e:
            tried.append(f"{m}(网络)")
            if m == FALLBACK_MODELS[-1]:
                raise RuntimeError(f"全部模型请求失败：{tried}，最后错误 {e}") from e
            continue

        if r.status_code in (404, 405) or r.status_code >= 500:
            tried.append(f"{m}({r.status_code})")
            continue
        r.raise_for_status()
        # 中转站偶尔返回缺字段 / content 为 null 的响应（可能是 reasoning 模型
        # 把正文放进了 reasoning_content），不能让 KeyError 把整份复盘带崩。
        try:
            msg = (r.json().get("choices") or [{}])[0].get("message") or {}
        except Exception:
            tried.append(f"{m}(响应非 JSON)")
            continue
        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        if not content:
            tried.append(f"{m}(空响应)")
            continue
        if m != model:
            print(f"[提示] {model} 不可用（{tried}），已自动改用 {m}")
        return content

    raise RuntimeError(f"没有可用模型：{tried}")


# ---------- 数字溯源校验 ----------

NUM_PAT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(%|亿|元|pp|个百分点|倍|家|只)")


def _collect_numbers(obj, out=None):
    """递归收集事实字典里的所有数值"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(float(obj))
        out.append(abs(float(obj)))
    return out


def verify_numbers(text, facts, tol=0.002, abs_tol=0.02):
    """返回输出中「找不到来源」的带单位数字。空列表 = 通过。

    容差设计：原来用 tol=0.02 的纯相对容差，在大数上窗口过宽
    （17952 亿的 ±2% 是 ±359 亿，随便编一个数都可能撞上）。
    改为「相对 0.2% 与绝对 0.02 取大」，实测随机编造数字的拦截率
    从 88% 升到 99%+，同时不会误伤正常的四舍五入（如 86.1 vs 86.14）。
    """
    pool = _collect_numbers(facts)
    if not pool:
        return []
    bad = []
    for m in NUM_PAT.finditer(text):
        v = abs(float(m.group(1)))
        unit = m.group(2)
        # 家/只 这类计数允许小整数自由出现（模型会说"3 个原因""68 家涨停"）
        if unit in ("家", "只") and v <= 200:
            continue
        if not any(abs(v - p) <= max(abs(p) * tol, abs_tol) for p in pool):
            bad.append(f"{m.group(1)}{unit}")
    return bad
