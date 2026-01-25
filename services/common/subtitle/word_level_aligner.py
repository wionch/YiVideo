"""
词级对齐工具

将优化后的文本对齐回原始词级时间戳结构。
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_WORD_PATTERN = re.compile(r"^\w+$", re.UNICODE)
_PREFIX_PATTERN = re.compile(r"^\s*[^\w]*", re.UNICODE)


def align_words_to_text(
    words: List[Dict[str, Any]],
    optimized_text: str,
    min_ratio: float = 0.5,
    return_error: bool = False
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Optional[str]]]:
    if not words:
        if return_error:
            return [], None
        return []

    original_tokens = [str(word.get("word", "")).strip() for word in words]
    optimized_tokens = _merge_punctuation(_tokenize(optimized_text))

    normalized_original = [_normalize_token(token) for token in original_tokens]
    normalized_target = [_normalize_token(token) for token in optimized_tokens]

    matcher = SequenceMatcher(None, normalized_original, normalized_target, autojunk=False)
    confidence = matcher.ratio()
    if confidence < min_ratio:
        error = f"对齐置信度过低: {confidence:.2f}"
        logger.warning(error)
        if return_error:
            return words, error
        return words

    mapped_tokens: List[Optional[str]] = [None] * len(words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "replace"):
            length = min(i2 - i1, j2 - j1)
            for offset in range(length):
                mapped_tokens[i1 + offset] = optimized_tokens[j1 + offset]

    aligned_words: List[Dict[str, Any]] = []
    for index, word in enumerate(words):
        new_token = mapped_tokens[index]
        if not new_token:
            aligned_words.append(word.copy())
            continue

        prefix = _extract_prefix(str(word.get("word", "")))
        updated = word.copy()
        updated["word"] = f"{prefix}{new_token}"
        aligned_words.append(updated)

    if return_error:
        return aligned_words, None
    return aligned_words


def _tokenize(text: str) -> List[str]:
    return _TOKEN_PATTERN.findall(text)


def _merge_punctuation(tokens: List[str]) -> List[str]:
    merged: List[str] = []
    for token in tokens:
        if _WORD_PATTERN.match(token):
            merged.append(token)
        else:
            if merged:
                merged[-1] = f"{merged[-1]}{token}"
            else:
                merged.append(token)
    return merged


def _normalize_token(token: str) -> str:
    return token.strip().lower()


def _extract_prefix(word: str) -> str:
    match = _PREFIX_PATTERN.match(word)
    return match.group(0) if match else ""
