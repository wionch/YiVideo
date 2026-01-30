# -*- coding: utf-8 -*-

"""
Qwen3-ASR 转录执行器。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from services.common.base_node_executor import BaseNodeExecutor


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


def map_words(time_stamps: List[Dict[str, Any]] | None, enable: bool) -> Tuple[list, int]:
    """将时间戳列表映射为 words 结构。"""
    if not enable:
        return [], 0
    if not time_stamps:
        return [], 0
    words = []
    for item in time_stamps:
        words.append({
            "word": item.get("text", ""),
            "start": item.get("start", 0.0),
            "end": item.get("end", 0.0),
            "probability": None,
        })
    return words, len(words)


class Qwen3ASRTranscribeExecutor(BaseNodeExecutor):
    """Qwen3-ASR 语音转录执行器。"""

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        if not input_data.get("audio_path"):
            raise ValueError("缺少必需参数: audio_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        raise NotImplementedError("尚未实现核心转录逻辑")

    def get_cache_key_fields(self) -> List[str]:
        return []
