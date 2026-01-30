# -*- coding: utf-8 -*-

"""
Qwen3-ASR 转录执行器。
"""

from __future__ import annotations


def map_language(language: str | None) -> str | None:
    """将短码映射为 Qwen3-ASR 认可的语言标识。"""
    if language is None:
        return None
    lang = str(language).strip()
    if not lang:
        return None
    low = lang.lower()
    if low in {"auto"}:
        return None
    if low in {"zh", "zh-cn", "cn"}:
        return "Chinese"
    if low in {"en", "en-us"}:
        return "English"
    return lang
