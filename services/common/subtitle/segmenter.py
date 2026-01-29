"""
字幕断句模块

三层断句策略:
1. 强标点断句（句点/问号/感叹号，但跳过缩写）
2. PySBD 语义断句（可选依赖）
3. 通用规则兜底（弱标点 → 停顿 → 字数）
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# 延迟加载 abbreviations 模块，避免触发 __init__.py 的副作用
_is_abbreviation = None


def _get_is_abbreviation():
    """获取 is_abbreviation 函数，首次调用时动态加载"""
    global _is_abbreviation
    if _is_abbreviation is None:
        # 直接加载 abbreviations.py 文件，避免通过包导入触发 __init__.py
        subtitle_dir = Path(__file__).parent
        abbreviations_path = subtitle_dir / "abbreviations.py"

        spec = importlib.util.spec_from_file_location("abbreviations", abbreviations_path)
        abbreviations_module = importlib.util.module_from_spec(spec)
        sys.modules["segmenter_abbreviations"] = abbreviations_module
        spec.loader.exec_module(abbreviations_module)

        _is_abbreviation = abbreviations_module.is_abbreviation
    return _is_abbreviation


# 强标点：句子结束标记
STRONG_PUNCTUATION: Set[str] = {".", "!", "?", "。", "！", "？", "…"}

# 弱标点：潜在断句点
WEAK_PUNCTUATION: Set[str] = {",", "，", "、", ";", ":", "：", "-", "–", "—"}

# 停顿阈值（秒）
PAUSE_THRESHOLD = 0.3


def split_by_strong_punctuation(words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """在强标点处断句，但跳过缩写词"""
    if not words:
        return []

    segments: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    for word in words:
        current.append(word)
        word_text = word.get("word", "").strip()

        if word_text and word_text[-1] in STRONG_PUNCTUATION:
            if not _get_is_abbreviation()(word_text):
                segments.append(current)
                current = []

    if current:
        segments.append(current)

    return segments
