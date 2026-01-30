"""
时间戳重建器

使用两阶段重建策略为优化后的字幕文本重建时间戳：
1. 阶段1: 稳定词锚定 - 使用LCS查找稳定词并保留其时间戳
2. 阶段2: 间隙填充 - 在稳定词之间的间隙中分配时间戳
"""

import logging
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any

from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    OptimizedLine,
    WordTimestamp,
)

logger = logging.getLogger(__name__)


class TimestampReconstructor:
    """
    时间戳重建器

    负责在LLM优化后为字幕文本重建时间戳。使用两阶段策略：
    1. 稳定词锚定：通过LCS找到未变化的词作为锚点
    2. 间隙填充：在锚点之间的间隙中为新词/修改的词分配时间戳

    Attributes:
        min_stable_word_length: 最小稳定词长度，小于此长度的词不参与锚定
        time_epsilon: 时间精度容差（秒）
    """

    def __init__(
        self,
        min_stable_word_length: int = 2,
        time_epsilon: float = 0.001,
    ):
        """
        初始化时间戳重建器

        Args:
            min_stable_word_length: 最小稳定词长度，默认为2
            time_epsilon: 时间精度容差（秒），默认为0.001
        """
        self.min_stable_word_length = min_stable_word_length
        self.time_epsilon = time_epsilon

    def _normalize_word(self, word: str) -> str:
        """
        标准化词语用于比较

        Args:
            word: 原始词语

        Returns:
            标准化后的词语（小写、去除首尾空格）
        """
        return word.strip().lower()

    def _find_stable_words(
        self,
        original_words: List[WordTimestamp],
        optimized_text: str,
    ) -> List[Tuple[int, int, WordTimestamp]]:
        """
        查找稳定词（LCS最长公共子序列）

        使用SequenceMatcher找到原始文本和优化后文本之间的最长公共子序列，
        这些未变化的词被视为"稳定词"，其时间戳将被保留作为锚点。

        Args:
            original_words: 原始词级时间戳列表
            optimized_text: 优化后的文本

        Returns:
            稳定词元组列表，每个元组为 (原始索引, 优化后索引, WordTimestamp)
        """
        if not original_words or not optimized_text:
            return []

        # 提取原始词列表
        original_word_list = [self._normalize_word(w.word) for w in original_words]

        # 分词：将优化后文本拆分为词列表
        optimized_words = self._tokenize(optimized_text)
        optimized_word_list = [self._normalize_word(w) for w in optimized_words]

        # 使用SequenceMatcher找到匹配块
        matcher = SequenceMatcher(None, original_word_list, optimized_word_list, autojunk=False)

        stable_words = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                # 找到匹配的词
                for offset in range(i2 - i1):
                    orig_idx = i1 + offset
                    opt_idx = j1 + offset
                    word_ts = original_words[orig_idx]

                    # 过滤短词
                    if len(original_word_list[orig_idx]) >= self.min_stable_word_length:
                        stable_words.append((orig_idx, opt_idx, word_ts))

        logger.debug(
            f"找到 {len(stable_words)} 个稳定词，"
            f"原始词数: {len(original_words)}, 优化后词数: {len(optimized_words)}"
        )

        return stable_words

    def _tokenize(self, text: str) -> List[str]:
        """
        将文本分词为词列表

        简单的基于空格和标点的分词策略。

        Args:
            text: 输入文本

        Returns:
            词列表
        """
        import re

        # 使用正则表达式分词：匹配单词或标点
        tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        return tokens

    def _distribute_in_gap(
        self,
        gap_words: List[str],
        gap_start: float,
        gap_end: float,
        left_anchor: Optional[WordTimestamp],
        right_anchor: Optional[WordTimestamp],
    ) -> List[WordTimestamp]:
        """
        在间隙中分配时间戳

        当稳定词之间存在间隙（新插入的词或修改的词）时，
        将间隙时间平均分配给间隙中的每个词。

        Args:
            gap_words: 间隙中的词列表
            gap_start: 间隙开始时间
            gap_end: 间隙结束时间
            left_anchor: 左侧锚点词（可能为None）
            right_anchor: 右侧锚点词（可能为None）

        Returns:
            分配了时间戳的词列表

        Raises:
            ValueError: 如果间隙词为空或时间范围无效
        """
        if not gap_words:
            return []

        if gap_end < gap_start:
            raise ValueError(
                f"间隙结束时间必须大于等于开始时间: {gap_end} < {gap_start}"
            )

        gap_duration = gap_end - gap_start
        word_count = len(gap_words)

        if word_count == 0:
            return []

        # 计算每个词的时间
        word_duration = gap_duration / word_count

        result = []
        for i, word in enumerate(gap_words):
            start_time = gap_start + i * word_duration
            end_time = start_time + word_duration

            # 创建新的WordTimestamp
            word_ts = WordTimestamp(
                word=word,
                start=round(start_time, 3),
                end=round(end_time, 3),
                probability=0.8,  # 间隙中的词置信度稍低
            )
            result.append(word_ts)

        logger.debug(
            f"间隙分配: {word_count} 个词, 时间范围 [{gap_start:.3f}, {gap_end:.3f}], "
            f"每词时长 {word_duration:.3f}s"
        )

        return result

    def reconstruct_segment(
        self,
        segment: SubtitleSegment,
        optimized_text: str,
        optimized_start: float,
        optimized_end: float,
    ) -> List[WordTimestamp]:
        """
        重建单个段的时间戳

        使用两阶段策略为优化后的文本重建词级时间戳：
        1. 找到稳定词（LCS）并保留其时间戳
        2. 在稳定词之间的间隙中为新词分配时间戳

        Args:
            segment: 原始字幕段，包含词级时间戳
            optimized_text: 优化后的文本
            optimized_start: 优化后段的开始时间
            optimized_end: 优化后段的结束时间

        Returns:
            重建后的词级时间戳列表

        Raises:
            ValueError: 如果输入参数无效
        """
        if not optimized_text:
            raise ValueError("优化后文本不能为空")

        if optimized_end < optimized_start:
            raise ValueError(
                f"结束时间必须大于开始时间: {optimized_end} < {optimized_start}"
            )

        # 如果没有原始词级时间戳，使用均匀分配
        if not segment.words:
            return self._create_uniform_timestamps(
                optimized_text, optimized_start, optimized_end
            )

        # 阶段1: 查找稳定词
        stable_words = self._find_stable_words(segment.words, optimized_text)

        # 如果没有稳定词，使用均匀分配
        if not stable_words:
            logger.warning("未找到稳定词，使用均匀时间戳分配")
            return self._create_uniform_timestamps(
                optimized_text, optimized_start, optimized_end
            )

        # 阶段2: 间隙填充
        result = self._fill_gaps(
            optimized_text,
            stable_words,
            optimized_start,
            optimized_end,
        )

        return result

    def _fill_gaps(
        self,
        optimized_text: str,
        stable_words: List[Tuple[int, int, WordTimestamp]],
        segment_start: float,
        segment_end: float,
    ) -> List[WordTimestamp]:
        """
        填充稳定词之间的间隙

        Args:
            optimized_text: 优化后的文本
            stable_words: 稳定词列表 (原始索引, 优化后索引, WordTimestamp)
            segment_start: 段开始时间
            segment_end: 段结束时间

        Returns:
            完整的词级时间戳列表
        """
        # 分词
        optimized_words = self._tokenize(optimized_text)

        # 按优化后索引排序稳定词
        sorted_stable = sorted(stable_words, key=lambda x: x[1])

        result = []
        last_opt_idx = -1
        last_end_time = segment_start

        for orig_idx, opt_idx, word_ts in sorted_stable:
            # 处理当前稳定词之前的间隙
            if opt_idx > last_opt_idx + 1:
                # 有间隙需要填充
                gap_words = optimized_words[last_opt_idx + 1 : opt_idx]
                gap_words = self._filter_empty_tokens(gap_words)

                if gap_words:
                    gap_timestamps = self._distribute_in_gap(
                        gap_words,
                        last_end_time,
                        word_ts.start,
                        result[-1] if result else None,
                        word_ts,
                    )
                    result.extend(gap_timestamps)

            # 添加稳定词（调整时间戳以匹配优化后的时间范围）
            adjusted_ts = WordTimestamp(
                word=optimized_words[opt_idx],
                start=max(word_ts.start, segment_start),
                end=min(word_ts.end, segment_end),
                probability=word_ts.probability,
            )
            result.append(adjusted_ts)

            last_opt_idx = opt_idx
            last_end_time = adjusted_ts.end

        # 处理最后一个稳定词之后的间隙
        if last_opt_idx < len(optimized_words) - 1:
            gap_words = optimized_words[last_opt_idx + 1 :]
            gap_words = self._filter_empty_tokens(gap_words)

            if gap_words:
                gap_timestamps = self._distribute_in_gap(
                    gap_words,
                    last_end_time,
                    segment_end,
                    result[-1] if result else None,
                    None,
                )
                result.extend(gap_timestamps)

        return result

    def _filter_empty_tokens(self, tokens: List[str]) -> List[str]:
        """
        过滤空token

        Args:
            tokens: 原始token列表

        Returns:
            过滤后的token列表
        """
        return [t for t in tokens if t and not t.isspace()]

    def _create_uniform_timestamps(
        self,
        text: str,
        start: float,
        end: float,
    ) -> List[WordTimestamp]:
        """
        创建均匀分布的时间戳

        当无法使用稳定词锚定时，将时间均匀分配给每个词。

        Args:
            text: 文本内容
            start: 开始时间
            end: 结束时间

        Returns:
            均匀分布的词级时间戳列表
        """
        words = self._tokenize(text)
        words = self._filter_empty_tokens(words)

        if not words:
            return []

        duration = end - start
        word_duration = duration / len(words)

        result = []
        for i, word in enumerate(words):
            word_start = start + i * word_duration
            word_end = word_start + word_duration

            word_ts = WordTimestamp(
                word=word,
                start=round(word_start, 3),
                end=round(word_end, 3),
                probability=0.5,  # 均匀分配的置信度较低
            )
            result.append(word_ts)

        return result

    def reconstruct_all(
        self,
        segments: List[SubtitleSegment],
        optimized_lines: List[OptimizedLine],
    ) -> List[List[WordTimestamp]]:
        """
        重建所有段的时间戳

        为每个优化后的字幕行重建词级时间戳。

        Args:
            segments: 原始字幕段列表
            optimized_lines: 优化后的字幕行列表

        Returns:
            每个段的词级时间戳列表的列表

        Raises:
            ValueError: 如果输入参数无效或长度不匹配
        """
        if segments is None or optimized_lines is None:
            raise ValueError("输入参数不能为None")

        if len(segments) != len(optimized_lines):
            raise ValueError(
                f"段数与优化行数不匹配: {len(segments)} != {len(optimized_lines)}"
            )

        result = []
        for i, (segment, line) in enumerate(zip(segments, optimized_lines)):
            try:
                word_timestamps = self.reconstruct_segment(
                    segment,
                    line.text,
                    line.start,
                    line.end,
                )
                result.append(word_timestamps)
                logger.debug(f"段 {i} 时间戳重建成功: {len(word_timestamps)} 个词")
            except Exception as e:
                logger.warning(f"段 {i} 时间戳重建失败: {e}，使用均匀分配")
                # 失败时使用均匀分配
                word_timestamps = self._create_uniform_timestamps(
                    line.text, line.start, line.end
                )
                result.append(word_timestamps)

        return result

    def reconstruct_from_dict(
        self,
        original_segments: List[Dict[str, Any]],
        optimized_lines: List[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        """
        从字典数据重建时间戳

        方便与外部系统集成的接口，接受和返回字典格式数据。

        Args:
            original_segments: 原始段字典列表，每个段应包含 'words' 字段
            optimized_lines: 优化后行字典列表，每个行应包含 'text', 'start', 'end' 字段

        Returns:
            每个段的词级时间戳字典列表的列表
        """
        # 转换为模型对象
        segments = []
        for seg_dict in original_segments:
            words = seg_dict.get("words", [])
            word_ts_list = [
                WordTimestamp(
                    word=w.get("word", ""),
                    start=w.get("start", 0.0),
                    end=w.get("end", 0.0),
                    probability=w.get("probability", 1.0),
                )
                for w in words
            ]

            segment = SubtitleSegment(
                id=seg_dict.get("id", 0),
                start=seg_dict.get("start", 0.0),
                end=seg_dict.get("end", 0.0),
                text=seg_dict.get("text", ""),
                words=word_ts_list if word_ts_list else None,
            )
            segments.append(segment)

        opt_lines = [
            OptimizedLine(
                text=line.get("text", ""),
                start=line.get("start", 0.0),
                end=line.get("end", 0.0),
                is_modified=line.get("is_modified", True),
                original_text=line.get("original_text"),
            )
            for line in optimized_lines
        ]

        # 执行重建
        results = self.reconstruct_all(segments, opt_lines)

        # 转换回字典格式
        dict_results = []
        for word_list in results:
            dict_list = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                }
                for w in word_list
            ]
            dict_results.append(dict_list)

        return dict_results
