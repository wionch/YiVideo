"""
词级对齐工具

将优化后的文本对齐回原始词级时间戳结构。
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple, Union

from services.common.subtitle.segmenter import MultilingualSubtitleSegmenter

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
    appended_tokens: List[List[str]] = [[] for _ in range(len(words))]
    deleted_indices = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapped_tokens[i1 + offset] = optimized_tokens[j1 + offset]
        elif tag == "replace":
            length = min(i2 - i1, j2 - j1)
            for offset in range(length):
                mapped_tokens[i1 + offset] = optimized_tokens[j1 + offset]
            for idx in range(i1 + length, i2):
                deleted_indices.add(idx)
            if j2 - j1 > length:
                insert_target = i1 + length - 1 if (i1 + length - 1) >= 0 else i1
                if 0 <= insert_target < len(words):
                    appended_tokens[insert_target].extend(
                        optimized_tokens[j1 + length:j2]
                    )
        elif tag == "insert":
            insert_target = i1 - 1 if i1 > 0 else i1
            if 0 <= insert_target < len(words):
                appended_tokens[insert_target].extend(optimized_tokens[j1:j2])
        elif tag == "delete":
            for idx in range(i1, i2):
                deleted_indices.add(idx)

    aligned_words: List[Dict[str, Any]] = []
    for index, word in enumerate(words):
        if index in deleted_indices:
            base_token = ""
        else:
            base_token = mapped_tokens[index]
            if base_token is None:
                base_token = original_tokens[index]

        combined = base_token or ""
        for token in appended_tokens[index]:
            combined = _append_token(combined, token)

        if not combined:
            updated = word.copy()
            updated["word"] = ""
            aligned_words.append(updated)
            continue

        prefix = _extract_prefix(str(word.get("word", "")))
        updated = word.copy()
        updated["word"] = f"{prefix}{combined}"
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


def _append_token(base: str, token: str) -> str:
    if not base:
        return token
    if not token:
        return base
    if _should_join_without_space(base, token):
        return f"{base}{token}"
    return f"{base} {token}"


def _should_join_without_space(base: str, token: str) -> bool:
    if not base or not token:
        return False
    if base[-1] in ("'", "’", "-", "–", "—", "/"):
        return True
    if token[0] in ("'", "’", "-", "–", "—"):
        return True
    return not _WORD_PATTERN.match(token)


def rebuild_segments_by_words(
    segments: List[Dict[str, Any]],
    max_cpl: int = 42,
    max_cps: float = 18.0,
    min_duration: float = 1.0,
    max_duration: float = 7.0,
    language: str = "en"
) -> List[Dict[str, Any]]:
    """
    基于词级时间戳重建字幕片段

    使用三层断句策略：
    1. 强标点断句（跳过缩写）
    2. PySBD 语义断句（可选）
    3. 通用规则兜底
    """
    words = _flatten_segment_words(segments)
    if not words:
        return []

    # 使用新的 segmenter
    segmenter = MultilingualSubtitleSegmenter()
    word_segments = segmenter.segment(
        words,
        language=language,
        max_cpl=max_cpl,
        max_cps=max_cps,
        min_duration=min_duration,
        max_duration=max_duration
    )

    # 转换为片段格式
    rebuilt_segments = []
    for idx, word_seg in enumerate(word_segments):
        segment = _create_segment_from_words(word_seg)
        segment["id"] = idx + 1
        rebuilt_segments.append(segment)

    return rebuilt_segments


def _create_segment_from_words(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从词列表创建片段"""
    text = "".join(w.get("word", "") for w in words).strip()
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)

    segment: Dict[str, Any] = {
        "start": start,
        "end": end,
        "duration": max(end - start, 0.0),
        "text": text,
        "words": words
    }

    # 保留说话人信息
    speakers = {w.get("speaker") for w in words if w.get("speaker")}
    if len(speakers) == 1:
        segment["speaker"] = speakers.pop()

    return segment


def _flatten_segment_words(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat_words: List[Dict[str, Any]] = []
    for segment in segments:
        speaker = segment.get("speaker")
        for word in segment.get("words") or []:
            word_data = word.copy()
            if speaker and "speaker" not in word_data:
                word_data["speaker"] = speaker
            flat_words.append(word_data)
    flat_words.sort(key=lambda item: item.get("start", 0.0))
    return flat_words
