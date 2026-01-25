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
    max_duration: float = 7.0
) -> List[Dict[str, Any]]:
    words = _flatten_segment_words(segments)
    if not words:
        return []

    rebuilt_segments = _split_words_by_punctuation_and_limits(
        words,
        max_cpl=max_cpl,
        max_cps=max_cps,
        min_duration=min_duration,
        max_duration=max_duration
    )
    for idx, segment in enumerate(rebuilt_segments):
        segment["id"] = idx + 1
    return rebuilt_segments


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


def _split_words_by_punctuation_and_limits(
    words: List[Dict[str, Any]],
    max_cpl: int,
    max_cps: float,
    min_duration: float,
    max_duration: float
) -> List[Dict[str, Any]]:
    if not words:
        return []

    strong_punctuation = set("。！？.!?")
    weak_punctuation = set("，、；,;:")

    segments: List[Dict[str, Any]] = []
    current_words: List[Dict[str, Any]] = []

    for index, word in enumerate(words):
        current_words.append(word)
        word_text = str(word.get("word", "")).strip()
        is_last_word = index == len(words) - 1

        current_duration = _segment_duration(current_words)
        if word_text and word_text[-1] in strong_punctuation:
            if current_duration >= min_duration or is_last_word:
                _flush_segment(segments, current_words)
                current_words = []
                continue

        while current_words:
            over_cpl, over_cps, over_duration, duration = _check_limits(
                current_words,
                max_cpl=max_cpl,
                max_cps=max_cps,
                min_duration=min_duration,
                max_duration=max_duration
            )
            if not (over_cpl or over_cps or over_duration):
                break

            candidates = _collect_break_indices(
                current_words,
                strong_punctuation,
                weak_punctuation
            )
            if not candidates:
                if not over_duration and not is_last_word:
                    break
                split_idx = len(current_words) - 1
                is_balanced = True
            else:
                split_idx, is_balanced = _select_break_index(
                    current_words,
                    candidates,
                    max_cpl=max_cpl,
                    max_cps=max_cps,
                    min_duration=min_duration,
                    max_duration=max_duration
                )
                if not is_balanced and not over_duration and not is_last_word:
                    break

            _flush_segment(segments, current_words[:split_idx + 1])
            current_words = current_words[split_idx + 1:]

        if is_last_word and current_words:
            _flush_segment(segments, current_words)
            current_words = []

    return segments


def _find_last_break_index(
    words: List[Dict[str, Any]],
    strong_punctuation: set,
    weak_punctuation: set
) -> Optional[int]:
    for idx in range(len(words) - 1, -1, -1):
        word_text = str(words[idx].get("word", "")).strip()
        if word_text and word_text[-1] in strong_punctuation.union(weak_punctuation):
            return idx
    return None


def _check_limits(
    words: List[Dict[str, Any]],
    max_cpl: int,
    max_cps: float,
    min_duration: float,
    max_duration: float
) -> tuple[bool, bool, bool, float]:
    text = _build_segment_text(words)
    text_length = len(text)
    duration = _segment_duration(words)

    over_cpl = text_length > max_cpl
    over_duration = duration > max_duration
    over_cps = duration >= min_duration and duration > 0 and (text_length / duration) > max_cps
    return over_cpl, over_cps, over_duration, duration


def _collect_break_indices(
    words: List[Dict[str, Any]],
    strong_punctuation: set,
    weak_punctuation: set
) -> List[int]:
    indices: List[int] = []
    for idx, word in enumerate(words):
        word_text = str(word.get("word", "")).strip()
        if word_text and word_text[-1] in strong_punctuation.union(weak_punctuation):
            indices.append(idx)
    return indices


def _segment_text_length(words: List[Dict[str, Any]]) -> int:
    return len(_build_segment_text(words))


def _within_limits(
    words: List[Dict[str, Any]],
    max_cpl: int,
    max_cps: float,
    min_duration: float,
    max_duration: float
) -> bool:
    over_cpl, over_cps, over_duration, _ = _check_limits(
        words,
        max_cpl=max_cpl,
        max_cps=max_cps,
        min_duration=min_duration,
        max_duration=max_duration
    )
    return not (over_cpl or over_cps or over_duration)


def _select_break_index(
    words: List[Dict[str, Any]],
    candidates: List[int],
    max_cpl: int,
    max_cps: float,
    min_duration: float,
    max_duration: float,
    min_balance_ratio: float = 0.5
) -> tuple[int, bool]:
    total_length = _segment_text_length(words)
    if not candidates:
        return len(words) - 1, True

    preferred = [
        idx for idx in candidates
        if _within_limits(words[:idx + 1], max_cpl, max_cps, min_duration, max_duration)
    ]
    if not preferred:
        preferred = candidates

    best_balanced_idx = None
    best_balanced_diff = None
    best_ratio = -1.0
    best_ratio_idx = preferred[0]

    for idx in preferred:
        left_words = words[:idx + 1]
        left_len = _segment_text_length(left_words)
        right_len = max(total_length - left_len, 0)

        if right_len == 0 or left_len == 0:
            ratio = 0.0
        else:
            ratio = min(left_len, right_len) / max(left_len, right_len)

        diff = abs(left_len - right_len)
        if ratio >= min_balance_ratio:
            if best_balanced_idx is None or diff < best_balanced_diff:
                best_balanced_idx = idx
                best_balanced_diff = diff

        if ratio > best_ratio:
            best_ratio = ratio
            best_ratio_idx = idx

    if best_balanced_idx is not None:
        return best_balanced_idx, True
    return best_ratio_idx, False


def _segment_duration(words: List[Dict[str, Any]]) -> float:
    if not words:
        return 0.0
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)
    return max(end - start, 0.0)


def _build_segment_text(words: List[Dict[str, Any]]) -> str:
    parts = [str(word.get("word", "")) for word in words if word.get("word")]
    return "".join(parts).strip()


def _flush_segment(
    segments: List[Dict[str, Any]],
    words: List[Dict[str, Any]]
) -> None:
    if not words:
        return
    text = _build_segment_text(words)
    if not text:
        return
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)
    segment: Dict[str, Any] = {
        "start": start,
        "end": end,
        "duration": max(end - start, 0.0),
        "text": text,
        "words": words
    }
    speakers = {word.get("speaker") for word in words if word.get("speaker")}
    if len(speakers) == 1:
        segment["speaker"] = speakers.pop()
    segments.append(segment)
