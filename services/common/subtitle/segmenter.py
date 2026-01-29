"""
字幕断句模块

三层断句策略:
1. 强标点断句（句点/问号/感叹号，但跳过缩写）
2. PySBD 语义断句（可选依赖）
3. 通用规则兜底（弱标点 → 停顿 → 字数）
"""

import logging
import re
from typing import Any, Dict, List, Set

from services.common.subtitle.abbreviations import is_abbreviation

logger = logging.getLogger(__name__)


# 强标点：句子结束标记
STRONG_PUNCTUATION: Set[str] = {".", "!", "?", "。", "！", "？", "…"}

# 弱标点：潜在断句点
WEAK_PUNCTUATION: Set[str] = {",", "，", "、", ";", ":", "：", "-", "–", "—"}

# 停顿阈值（秒）
PAUSE_THRESHOLD = 0.3

_SINGLE_LETTER_ABBREV = re.compile(r"^[A-Za-z]\.$")


def _is_single_letter_abbrev(word_text: str) -> bool:
    return bool(_SINGLE_LETTER_ABBREV.fullmatch(word_text.strip()))


def _next_is_single_letter_abbrev(words: List[Dict[str, Any]], index: int) -> bool:
    for next_word in words[index + 1:]:
        text = str(next_word.get("word", "")).strip()
        if not text:
            continue
        return _is_single_letter_abbrev(text)
    return False


def _prev_is_single_letter_abbrev(words: List[Dict[str, Any]], index: int) -> bool:
    for prev_word in reversed(words[:index]):
        text = str(prev_word.get("word", "")).strip()
        if not text:
            continue
        return _is_single_letter_abbrev(text)
    return False


def _is_hyphen_boundary(words: List[Dict[str, Any]], index: int) -> bool:
    if index < 0 or index + 1 >= len(words):
        return False
    left = str(words[index].get("word", "")).strip()
    right = str(words[index + 1].get("word", "")).strip()
    hyphens = {"-", "–", "—"}
    return (
        any(left.endswith(h) for h in hyphens)
        or any(right.startswith(h) for h in hyphens)
    )


def _has_strong_punct_split(words: List[Dict[str, Any]]) -> bool:
    for index, word in enumerate(words):
        word_text = str(word.get("word", "")).strip()
        if not word_text:
            continue
        if word_text[-1] in STRONG_PUNCTUATION:
            if is_abbreviation(word_text):
                continue
            if _is_single_letter_abbrev(word_text) and (
                _next_is_single_letter_abbrev(words, index)
                or _prev_is_single_letter_abbrev(words, index)
            ):
                continue
            return True
    return False


def split_by_strong_punctuation(words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """在强标点处断句，但跳过缩写词"""
    if not words:
        return []

    segments: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    for index, word in enumerate(words):
        current.append(word)
        word_text = word.get("word", "").strip()

        if word_text and word_text[-1] in STRONG_PUNCTUATION:
            if _is_single_letter_abbrev(word_text) and (
                _next_is_single_letter_abbrev(words, index)
                or _prev_is_single_letter_abbrev(words, index)
            ):
                continue
            if not is_abbreviation(word_text):
                segments.append(current)
                current = []

    if current:
        segments.append(current)

    return segments


def split_by_weak_punctuation(
    words: List[Dict[str, Any]], max_cpl: int, force: bool = False
) -> List[List[Dict[str, Any]]]:
    """在弱标点处断句，保持片段长度不超过 max_cpl"""
    text = "".join(w.get("word", "") for w in words)
    if not force and len(text) <= max_cpl:
        return [words]
    if len(words) <= 1:
        return [words]
    candidates = []
    for i, word in enumerate(words[:-1]):
        word_text = word.get("word", "").strip()
        if word_text and word_text[-1] in WEAK_PUNCTUATION:
            if word_text[-1] in {"-", "–", "—"} and len(word_text) > 1:
                continue
            candidates.append(i)
    if not candidates:
        return [words]
    mid = len(words) // 2
    best_split = min(candidates, key=lambda x: abs(x - mid))
    left = words[:best_split + 1]
    right = words[best_split + 1:]
    return split_by_weak_punctuation(left, max_cpl) + split_by_weak_punctuation(right, max_cpl)


def split_by_pause(
    words: List[Dict[str, Any]], max_cpl: int, force: bool = False
) -> List[List[Dict[str, Any]]]:
    """基于词间停顿时间进行断句，停顿超过 PAUSE_THRESHOLD (0.3s) 视为潜在断句点"""
    text = "".join(w.get("word", "") for w in words)
    if not force and len(text) <= max_cpl:
        return [words]
    if len(words) <= 1:
        return [words]
    candidates = []
    for i in range(len(words) - 1):
        current_word_end = words[i].get("end", 0)
        next_word_start = words[i + 1].get("start", current_word_end)
        gap = next_word_start - current_word_end
        if gap > PAUSE_THRESHOLD:
            candidates.append((i, gap))
    if not candidates:
        return [words]
    mid = len(words) // 2
    def score_pause(item):
        idx, gap = item
        distance_penalty = abs(idx - mid) * 0.1
        return gap - distance_penalty
    best_split, _ = max(candidates, key=score_pause)
    left = words[:best_split + 1]
    right = words[best_split + 1:]
    return split_by_pause(left, max_cpl) + split_by_pause(right, max_cpl)


def split_by_word_count(
    words: List[Dict[str, Any]], max_cpl: int, force: bool = False
) -> List[List[Dict[str, Any]]]:
    """基于字数进行断句，确保每个片段不超过 max_cpl 字符"""
    text = "".join(w.get("word", "") for w in words)
    if not force and len(text) <= max_cpl:
        return [words]
    if len(words) <= 1:
        return [words]
    if not text:
        return [words]

    max_word_len = max(len(w.get("word", "")) for w in words)
    if max_word_len > max_cpl and len(words) == 1:
        return [words]

    if max_cpl <= 0:
        return [words]

    num_segments = max(2, (len(text) + max_cpl - 1) // max_cpl)
    target_len = len(text) / num_segments

    best_split = None
    best_diff = None
    current_len = 0
    for i, word in enumerate(words[:-1]):
        if _is_hyphen_boundary(words, i):
            continue
        current_len += len(word.get("word", ""))
        diff = abs(current_len - target_len)
        if best_diff is None or diff < best_diff:
            best_split = i
            best_diff = diff

    if best_split is None:
        return [words]

    left = words[:best_split + 1]
    right = words[best_split + 1:]
    if not left or not right:
        return [words]

    return split_by_word_count(left, max_cpl) + split_by_word_count(right, max_cpl)


class MultilingualSubtitleSegmenter:
    """多语言字幕断句器。三层策略: 1.强标点 2.PySBD语义 3.通用规则兜底"""

    PYSBD_LANGS = {
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
        "ru",
        "nl",
        "da",
        "fi",
        "zh",
        "ja",
        "ko",
        "ar",
        "hi",
        "pl",
        "cs",
        "sk",
        "tr",
        "el",
        "he",
        "fa",
    }

    def __init__(self):
        self._pysbd_available = False
        self._try_import_pysbd()

    def _try_import_pysbd(self):
        try:
            from pysbd import Segmenter

            self._pysbd_available = True
            self._pysbd_segmenters = {}
        except ImportError:
            logger.info("PySBD not available, using fallback segmentation")

    def _get_pysbd_segmenter(self, language: str):
        """获取或创建指定语言的 PySBD 分句器"""
        from pysbd import Segmenter

        if language not in self._pysbd_segmenters:
            self._pysbd_segmenters[language] = Segmenter(language=language, clean=False)
        return self._pysbd_segmenters[language]

    def _build_text_and_offsets(
        self, words: List[Dict[str, Any]]
    ) -> tuple:
        text_parts = []
        offsets = []
        cursor = 0
        for word in words:
            token = str(word.get("word", ""))
            start = cursor
            cursor += len(token)
            end = cursor
            text_parts.append(token)
            offsets.append((start, end))
        return "".join(text_parts), offsets

    def _apply_pysbd_global_split(
        self, words: List[Dict[str, Any]], language: str
    ) -> List[List[Dict[str, Any]]]:
        text, offsets = self._build_text_and_offsets(words)
        if not text:
            return []

        segmenter = self._get_pysbd_segmenter(language)
        sentences = segmenter.segment(text)
        if not sentences:
            return []
        if len(sentences) <= 1 and _has_strong_punct_split(words):
            return []

        total_len = sum(len(sentence) for sentence in sentences)
        if total_len != len(text):
            logger.warning("PySBD 句界长度不匹配，回退强标点断句")
            return []

        result: List[List[Dict[str, Any]]] = []
        cursor = 0
        word_idx = 0
        for sent in sentences:
            sent_len = len(sent)
            if sent_len == 0:
                continue
            sent_end = cursor + sent_len
            current_seg = []

            while word_idx < len(words) and offsets[word_idx][1] <= sent_end:
                current_seg.append(words[word_idx])
                word_idx += 1

            if not current_seg and word_idx < len(words):
                current_seg.append(words[word_idx])
                word_idx += 1

            if current_seg:
                result.append(current_seg)

            cursor = sent_end

        if word_idx < len(words):
            if result:
                result[-1].extend(words[word_idx:])
            else:
                result.append(words[word_idx:])

        return result

    def _apply_pysbd_split(
        self, segments: List[List[Dict[str, Any]]], language: str, max_cpl: int
    ) -> List[List[Dict[str, Any]]]:
        """对过长的片段应用 PySBD 语义断句"""
        result = []
        for seg in segments:
            text = "".join(w.get("word", "") for w in seg)
            if len(text) <= max_cpl:
                result.append(seg)
                continue

            segmenter = self._get_pysbd_segmenter(language)
            sentences = segmenter.segment(text)

            if len(sentences) <= 1:
                result.append(seg)
                continue

            total_len = sum(len(sentence) for sentence in sentences)
            if total_len != len(text):
                logger.warning("PySBD 句界长度不匹配，跳过语义断句")
                result.append(seg)
                continue

            word_offsets = []
            cursor = 0
            for word in seg:
                word_text = word.get("word", "")
                start = cursor
                end = cursor + len(word_text)
                word_offsets.append((start, end))
                cursor = end

            cursor = 0
            word_idx = 0
            for sent in sentences:
                sent_len = len(sent)
                if sent_len == 0:
                    continue
                sent_end = cursor + sent_len
                current_seg = []

                while word_idx < len(seg) and word_offsets[word_idx][1] <= sent_end:
                    current_seg.append(seg[word_idx])
                    word_idx += 1

                if not current_seg and word_idx < len(seg):
                    current_seg.append(seg[word_idx])
                    word_idx += 1

                if current_seg:
                    result.append(current_seg)

                cursor = sent_end

            if word_idx < len(seg):
                if result:
                    result[-1].extend(seg[word_idx:])
                else:
                    result.append(seg[word_idx:])

        return result

    def segment(
        self,
        words: List[Dict[str, Any]],
        language: str = "en",
        max_cpl: int = 42,
        max_cps: float = 18.0,
        min_duration: float = 1.0,
        max_duration: float = 7.0,
    ) -> List[List[Dict[str, Any]]]:
        """
        执行三层断句策略

        Args:
            words: 词级时间戳列表，每个词包含 word/start/end
            language: 语言代码
            max_cpl: 每行最大字符数
            max_cps: 每秒最大字符数
            min_duration: 最小持续时间（秒）
            max_duration: 最大持续时间（秒）

        Returns:
            分割后的片段列表
        """
        if not words:
            return []

        # 第一层：全局 PySBD 语义断句（可用且支持语言时优先）
        segments: List[List[Dict[str, Any]]]
        if self._pysbd_available and language in self.PYSBD_LANGS:
            segments = self._apply_pysbd_global_split(words, language)
            if not segments:
                segments = split_by_strong_punctuation(words)
        else:
            segments = split_by_strong_punctuation(words)

        # 第三层：通用规则兜底
        final_result: List[List[Dict[str, Any]]] = []
        for seg in segments:
            final_result.extend(
                self._split_with_fallback(
                    seg,
                    max_cpl=max_cpl,
                    max_cps=max_cps,
                    min_duration=min_duration,
                    max_duration=max_duration
                )
            )

        return final_result

    def _fallback_split(
        self, words: List[Dict[str, Any]], max_cpl: int, force: bool = False
    ) -> List[List[Dict[str, Any]]]:
        """兜底分割策略：弱标点 -> 停顿 -> 字数"""
        segments = split_by_weak_punctuation(words, max_cpl, force=force)
        if len(segments) > 1:
            if self._has_tiny_segment(segments):
                return self._split_by_word_count_no_tiny(words, max_cpl)
            return segments

        segments = split_by_pause(words, max_cpl, force=force)
        if len(segments) > 1:
            return segments

        return split_by_word_count(words, max_cpl, force=force)

    def _has_tiny_segment(self, segments: List[List[Dict[str, Any]]]) -> bool:
        for seg in segments:
            text = "".join(w.get("word", "") for w in seg).strip()
            if len(text) <= 2:
                return True
        return False

    def _split_by_word_count_no_tiny(
        self, words: List[Dict[str, Any]], max_cpl: int
    ) -> List[List[Dict[str, Any]]]:
        text = "".join(w.get("word", "") for w in words)
        if len(text) <= max_cpl:
            return [words]
        if len(words) <= 1:
            return [words]
        if not text:
            return [words]
        if max_cpl <= 0:
            return [words]

        num_segments = max(2, (len(text) + max_cpl - 1) // max_cpl)
        target_len = len(text) / num_segments

        best_split = None
        best_diff = None
        current_len = 0
        for i, word in enumerate(words[:-1]):
            if _is_hyphen_boundary(words, i):
                continue
            current_len += len(word.get("word", ""))
            left_len = len("".join(w.get("word", "") for w in words[: i + 1]).strip())
            right_len = len("".join(w.get("word", "") for w in words[i + 1 :]).strip())
            if left_len <= 2 or right_len <= 2:
                continue
            diff = abs(current_len - target_len)
            if best_diff is None or diff < best_diff:
                best_split = i
                best_diff = diff

        if best_split is None:
            return [words]

        left = words[: best_split + 1]
        right = words[best_split + 1 :]
        if not left or not right:
            return [words]

        return (
            self._split_by_word_count_no_tiny(left, max_cpl)
            + self._split_by_word_count_no_tiny(right, max_cpl)
        )

    def _split_with_fallback(
        self,
        words: List[Dict[str, Any]],
        max_cpl: int,
        max_cps: float,
        min_duration: float,
        max_duration: float,
    ) -> List[List[Dict[str, Any]]]:
        if not self._should_split(words, max_cpl, max_cps, min_duration, max_duration):
            return [words]

        segments = self._fallback_split(words, max_cpl, force=True)
        if len(segments) <= 1:
            return [words]
        result: List[List[Dict[str, Any]]] = []
        for seg in segments:
            if not self._should_split(seg, max_cpl, max_cps, min_duration, max_duration):
                result.append(seg)
                continue
            if len(seg) <= 1:
                result.append(seg)
                continue
            if seg == words:
                result.append(seg)
                continue
            result.extend(
                self._split_with_fallback(
                    seg,
                    max_cpl=max_cpl,
                    max_cps=max_cps,
                    min_duration=min_duration,
                    max_duration=max_duration
                )
            )
        return result

    def _should_split(
        self,
        words: List[Dict[str, Any]],
        max_cpl: int,
        max_cps: float,
        min_duration: float,
        max_duration: float,
    ) -> bool:
        text = "".join(w.get("word", "") for w in words)
        if len(text) > max_cpl:
            return True
        if len(words) < 2:
            return False
        duration = words[-1]["end"] - words[0]["start"]
        if duration > max_duration:
            return True
        if duration > 0 and len(text) / duration > max_cps:
            return True
        if duration < min_duration:
            return False
        return False

    def _within_limits(
        self,
        words: List[Dict[str, Any]],
        max_cpl: int,
        max_cps: float,
        min_duration: float,
        max_duration: float,
    ) -> bool:
        """检查片段是否在限制范围内"""
        text = "".join(w.get("word", "") for w in words)
        if len(text) > max_cpl:
            return False

        if len(words) >= 2:
            duration = words[-1]["end"] - words[0]["start"]
            if duration < min_duration:
                return False
            if duration > max_duration:
                return False
            if duration > 0 and len(text) / duration > max_cps:
                return False

        return True


def merge_incomplete_segments(
    segments: List[List[Dict[str, Any]]],
    min_length: int = 3,
) -> List[List[Dict[str, Any]]]:
    """
    后处理合并：合并不完整片段和极短片段

    合并规则：
    1. 不完整片段：无结尾标点 + 小写开头（表示句子未结束）
    2. 极短片段：文本长度 < min_length

    合并策略：
    - 开头的极短/不完整片段：合并到后一个片段
    - 中间的极短/不完整片段：合并到前一个片段
    - 连续的多个不完整片段：依次向前合并

    Args:
        segments: 片段列表，每个片段是词级时间戳列表
        min_length: 最小片段长度（字符数），默认3

    Returns:
        合并后的片段列表
    """
    if not segments:
        return []

    if len(segments) <= 1:
        return segments

    def get_text(words: List[Dict[str, Any]]) -> str:
        """获取片段的完整文本"""
        return "".join(w.get("word", "") for w in words)

    def has_ending_punctuation(words: List[Dict[str, Any]]) -> bool:
        """检查片段是否有结尾标点"""
        if not words:
            return False
        # 从后向前查找第一个非空白字符
        for word in reversed(words):
            text = word.get("word", "").strip()
            if text:
                return text[-1] in STRONG_PUNCTUATION
        return False

    def is_lowercase_start(words: List[Dict[str, Any]]) -> bool:
        """检查片段是否以小写字母开头"""
        if not words:
            return False
        # 找到第一个非空白字符
        for word in words:
            text = word.get("word", "").strip()
            if text:
                first_char = text[0]
                return first_char.islower()
        return False

    def get_text_length(words: List[Dict[str, Any]]) -> int:
        """获取片段的非空白文本长度"""
        text = get_text(words)
        return len(text.strip())

    def is_incomplete(words: List[Dict[str, Any]]) -> bool:
        """
        判断片段是否不完整

        不完整条件：
        1. 无结尾标点 + 小写开头（句子未结束）
        2. 极短片段（长度 < min_length）
        """
        text_len = get_text_length(words)
        if text_len < min_length:
            return True
        if not has_ending_punctuation(words) and is_lowercase_start(words):
            return True
        return False

    result: List[List[Dict[str, Any]]] = []

    for i, seg in enumerate(segments):
        if not seg:
            continue

        if not is_incomplete(seg):
            # 完整片段，直接添加
            result.append(seg)
        else:
            # 不完整片段，需要合并
            if not result:
                # 是第一个片段且不完整，需要看后一个片段
                # 暂时保存，等处理到下一个完整片段时再合并
                # 实际上应该向前合并到已有的结果中
                # 如果没有前一个，则保留到后面再处理
                # 这里简化处理：开头的极短片段暂时保留，等后面再决定
                result.append(seg)
            else:
                # 有前一个片段，合并到前一个
                result[-1].extend(seg)

    # 处理特殊情况：如果结果中有多个片段，检查第一个是否极短
    # 如果是，合并到第二个
    if len(result) >= 2:
        first_len = get_text_length(result[0])
        if first_len < min_length and not has_ending_punctuation(result[0]):
            # 第一个片段极短且无标点，合并到第二个
            merged = result[0] + result[1]
            result = [merged] + result[2:]

    return result
