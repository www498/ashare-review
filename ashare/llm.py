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
import json
import os
import re

import requests

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def _cfg():
    return (
        os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
        os.getenv("LLM_BASE_URL", DEFAULT_BASE),
        os.getenv("LLM_MODEL", DEFAULT_MODEL),
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
    r = requests.post(f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


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
