"""
字幕优化器V2分段管理器

负责将字幕数据分段处理、管理重叠区域、合并分段结果。
支持大文件分段处理以提高并发性能和降低LLM调用延迟。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import difflib

from .models import SubtitleSegment, OptimizedLine, SegmentTask, OverlapRegion
from .config import SubtitleOptimizerConfig


@dataclass
class SegmentInfo:
    """
    分段信息

    表示一个字幕分段的基本信息，用于内部分段管理。

    Attributes:
        index: 分段索引
        start_line: 起始行号（包含）
        end_line: 结束行号（不包含）
        segments: 包含的字幕段列表
        is_overlap: 是否为重叠区域
    """
    index: int
    start_line: int
    end_line: int
    segments: List[SubtitleSegment] = field(default_factory=list)
    is_overlap: bool = False

    @property
    def line_count(self) -> int:
        """行数"""
        return self.end_line - self.start_line

    @property
    def start_time(self) -> float:
        """开始时间"""
        if not self.segments:
            return 0.0
        return min(seg.start for seg in self.segments)

    @property
    def end_time(self) -> float:
        """结束时间"""
        if not self.segments:
            return 0.0
        return max(seg.end for seg in self.segments)


class SegmentManager:
    """
    分段管理器

    负责将字幕数据分段处理，管理重叠区域，合并分段结果。

    Attributes:
        config: 字幕优化器配置
        _segments: 原始字幕段列表
        _segment_infos: 分段信息列表
    """

    def __init__(self, config: Optional[SubtitleOptimizerConfig] = None):
        """
        初始化分段管理器

        Args:
            config: 字幕优化器配置，如果为None则使用默认配置
        """
        self.config = config or SubtitleOptimizerConfig()
        self._segments: List[SubtitleSegment] = []
        self._segment_infos: List[SegmentInfo] = []

    def create_segments(
        self,
        lines: List[str],
        segments: Optional[List[SubtitleSegment]] = None
    ) -> List[SegmentTask]:
        """
        创建分段任务

        将字幕行列表分割成多个SegmentTask，每个任务包含指定数量的行。
        相邻分段之间会有重叠区域以确保上下文连续性。

        Args:
            lines: 字幕行列表，格式为 "[ID]文本内容"
            segments: 可选的字幕段列表，用于提供时间戳信息

        Returns:
            分段任务列表

        Raises:
            ValueError: 输入参数无效
        """
        if lines is None:
            raise ValueError("lines不能为None")

        if not lines:
            return []

        # 解析行获取ID映射
        id_to_segment: Dict[int, SubtitleSegment] = {}
        if segments:
            for seg in segments:
                id_to_segment[seg.id] = seg

        # 解析行获取ID列表
        line_ids = self._parse_line_ids(lines)
        if not line_ids:
            return []

        total_lines = len(line_ids)
        segment_size = self.config.segment_size
        overlap_lines = self.config.overlap_lines

        # 如果总行数小于等于分段大小，不需要分段
        if total_lines <= segment_size:
            task_segments = self._build_task_segments(line_ids, id_to_segment, lines)
            task = SegmentTask(
                task_id="segment_0",
                segments=task_segments,
                segment_type=self._get_segment_type(0, 1)
            )
            return [task]

        # 计算分段范围
        ranges = self.calculate_segment_ranges(total_lines)
        total_segments = len(ranges)

        # 创建任务
        tasks = []
        for segment_index, (start_idx, end_idx) in enumerate(ranges):
            # 获取当前分段的行ID
            current_ids = line_ids[start_idx:end_idx]
            task_segments = self._build_task_segments(
                current_ids, id_to_segment, lines
            )

            # 确定分段类型
            segment_type = self._get_segment_type(segment_index, total_segments)

            # 创建任务
            task = SegmentTask(
                task_id=f"segment_{segment_index}",
                segments=task_segments,
                segment_type=segment_type
            )
            tasks.append(task)

            # 更新分段信息
            segment_info = SegmentInfo(
                index=segment_index,
                start_line=start_idx,
                end_line=end_idx,
                segments=task_segments,
                is_overlap=(segment_index > 0 and end_idx < total_lines)
            )
            self._segment_infos.append(segment_info)

        return tasks

    def _parse_line_ids(self, lines: List[str]) -> List[int]:
        """
        解析行ID

        从格式化的行中提取ID列表。

        Args:
            lines: 格式化的字幕行列表

        Returns:
            ID列表
        """
        ids = []
        for line in lines:
            if line.startswith("[") and "]" in line:
                try:
                    id_str = line[1:line.index("]")]
                    ids.append(int(id_str))
                except (ValueError, IndexError):
                    continue
        return ids

    def _build_task_segments(
        self,
        line_ids: List[int],
        id_to_segment: Dict[int, SubtitleSegment],
        lines: List[str]
    ) -> List[SubtitleSegment]:
        """
        构建任务段列表

        Args:
            line_ids: 行ID列表
            id_to_segment: ID到段的映射
            lines: 原始行列表

        Returns:
            字幕段列表
        """
        task_segments = []
        for line_id in line_ids:
            if line_id in id_to_segment:
                task_segments.append(id_to_segment[line_id])
            else:
                # 从行文本创建临时段
                for line in lines:
                    if line.startswith(f"[{line_id}]"):
                        text = line[line.index("]") + 1:]
                        task_segments.append(
                            SubtitleSegment(
                                id=line_id,
                                start=0.0,
                                end=0.0,
                                text=text
                            )
                        )
                        break
        return task_segments

    def _get_segment_type(self, index: int, total: int) -> Any:
        """
        获取分段类型

        Args:
            index: 分段索引
            total: 总分段数

        Returns:
            分段类型枚举值
        """
        from .models import SegmentType

        if total <= 1:
            return SegmentType.NORMAL
        if index == 0:
            return SegmentType.OVERLAP_START
        if index == total - 1:
            return SegmentType.OVERLAP_END
        return SegmentType.OVERLAP_MIDDLE

    def _estimate_segment_count(self, total_lines: int) -> int:
        """
        估计分段数量

        Args:
            total_lines: 总行数

        Returns:
            估计的分段数量
        """
        segment_size = self.config.segment_size
        overlap_lines = self.config.overlap_lines

        if total_lines <= segment_size:
            return 1

        # 计算分段数：每段实际新增行数 = segment_size - overlap_lines
        effective_size = segment_size - overlap_lines
        count = 1 + (total_lines - segment_size + effective_size - 1) // effective_size
        return max(1, count)

    def extract_overlap_region(
        self,
        previous_lines: List[OptimizedLine],
        current_lines: List[OptimizedLine],
        overlap_count: Optional[int] = None
    ) -> OverlapRegion:
        """
        提取重叠区域

        从两个相邻分段的结果中提取重叠区域的内容。

        Args:
            previous_lines: 前一分段的优化结果
            current_lines: 当前分段的优化结果
            overlap_count: 重叠行数，如果为None则使用配置值

        Returns:
            重叠区域对象

        Raises:
            ValueError: 输入参数无效
        """
        if previous_lines is None or current_lines is None:
            raise ValueError("输入行列表不能为None")

        overlap_count = overlap_count or self.config.overlap_lines

        # 获取前一分段的最后overlap_count行
        prev_overlap = previous_lines[-overlap_count:] if len(previous_lines) >= overlap_count else previous_lines

        # 获取当前分段的前overlap_count行
        curr_overlap = current_lines[:overlap_count] if len(current_lines) >= overlap_count else current_lines

        # 计算时间范围
        start_time = min(
            line.start for line in prev_overlap
        ) if prev_overlap else 0.0

        end_time = max(
            line.end for line in curr_overlap
        ) if curr_overlap else 0.0

        # 转换为SubtitleSegment用于OverlapRegion
        prev_segments = [
            SubtitleSegment(
                id=i,
                start=line.start,
                end=line.end,
                text=line.text
            )
            for i, line in enumerate(prev_overlap)
        ]

        next_segments = [
            SubtitleSegment(
                id=i,
                start=line.start,
                end=line.end,
                text=line.text
            )
            for i, line in enumerate(curr_overlap)
        ]

        return OverlapRegion(
            start=start_time,
            end=end_time,
            previous_segments=prev_segments,
            next_segments=next_segments
        )

    def calculate_diff_score(
        self,
        original_text: str,
        optimized_text: str
    ) -> float:
        """
        计算差异度

        计算原始文本和优化后文本之间的差异程度，用于检测修改。
        使用SequenceMatcher计算相似度，返回差异比例。

        Args:
            original_text: 原始文本
            optimized_text: 优化后文本

        Returns:
            差异度（0-1之间），0表示完全相同，1表示完全不同

        Raises:
            ValueError: 输入参数无效
        """
        if original_text is None or optimized_text is None:
            raise ValueError("文本不能为None")

        # 标准化文本（去除多余空格）
        original = " ".join(original_text.split())
        optimized = " ".join(optimized_text.split())

        if not original and not optimized:
            return 0.0

        if not original or not optimized:
            return 1.0

        # 使用SequenceMatcher计算相似度
        matcher = difflib.SequenceMatcher(None, original, optimized)
        similarity = matcher.ratio()

        # 返回差异度 = 1 - 相似度
        return 1.0 - similarity

    def merge_segments(
        self,
        segment_results: List[List[OptimizedLine]],
        overlap_regions: Optional[List[OverlapRegion]] = None
    ) -> List[OptimizedLine]:
        """
        合并段结果

        将多个分段的优化结果合并成一个完整的字幕列表。
        处理重叠区域的去重和边界平滑，使用基于diff_threshold的智能去重策略。

        Args:
            segment_results: 各分段的优化结果列表
            overlap_regions: 重叠区域列表（可选）

        Returns:
            合并后的优化字幕列表

        Raises:
            ValueError: 输入参数无效
        """
        if segment_results is None:
            raise ValueError("segment_results不能为None")

        if not segment_results:
            return []

        if len(segment_results) == 1:
            return segment_results[0]

        overlap_lines = self.config.overlap_lines
        diff_threshold = self.config.diff_threshold
        merged = []

        # 处理第一个分段
        first_segment = segment_results[0]
        if len(first_segment) > overlap_lines:
            # 保留第一个分段的大部分，只去掉最后overlap_lines行（将在重叠区域处理）
            merged.extend(first_segment[:-overlap_lines])
        else:
            # 如果分段太短，全部保留
            merged.extend(first_segment)

        # 处理中间分段
        for i in range(1, len(segment_results) - 1):
            current_segment = segment_results[i]
            previous_segment = segment_results[i - 1]

            # 获取重叠区域
            prev_overlap = previous_segment[-overlap_lines:] if len(previous_segment) >= overlap_lines else previous_segment
            curr_overlap = current_segment[:overlap_lines] if len(current_segment) >= overlap_lines else current_segment

            # 智能选择重叠区域内容
            selected_overlap = self._resolve_overlap_conflict(
                prev_overlap, curr_overlap, diff_threshold
            )

            # 添加当前分段的非重叠部分
            if len(current_segment) > overlap_lines:
                # 去掉前overlap_lines行，保留剩余部分
                merged.extend(current_segment[overlap_lines:])
            else:
                # 分段太短，全部保留
                merged.extend(current_segment)

        # 处理最后一个分段
        last_segment = segment_results[-1]
        if len(last_segment) > overlap_lines:
            # 去掉前overlap_lines行（已在重叠区域处理）
            merged.extend(last_segment[overlap_lines:])
        else:
            # 如果分段太短，全部保留
            merged.extend(last_segment)

        # 重新分配ID和时间戳
        return self._normalize_merged_lines(merged)

    def _resolve_overlap_conflict(
        self,
        prev_overlap: List[OptimizedLine],
        curr_overlap: List[OptimizedLine],
        diff_threshold: float
    ) -> List[OptimizedLine]:
        """
        解决重叠区域冲突

        基于diff_threshold智能选择去重策略：
        - 如果两段优化结果差异小（< threshold），保留后一段（通常质量更好）
        - 如果差异大（>= threshold），保留修改幅度更大的一段（可能优化更彻底）

        Args:
            prev_overlap: 前一段的重叠区域
            curr_overlap: 当前段的重叠区域
            diff_threshold: 差异阈值

        Returns:
            选择后的重叠区域行列表
        """
        if not prev_overlap or not curr_overlap:
            return curr_overlap if curr_overlap else prev_overlap

        # 确保两段长度一致（取最小长度）
        min_len = min(len(prev_overlap), len(curr_overlap))
        prev_lines = prev_overlap[-min_len:]
        curr_lines = curr_overlap[:min_len]

        selected_lines = []

        for prev_line, curr_line in zip(prev_lines, curr_lines):
            # 计算两段之间的差异
            text_diff = self.calculate_diff_score(prev_line.text, curr_line.text)

            # 计算各自的修改幅度（与原始文本比较）
            prev_modification = self.calculate_diff_score(
                prev_line.original_text or "", prev_line.text
            ) if prev_line.original_text else 0.0

            curr_modification = self.calculate_diff_score(
                curr_line.original_text or "", curr_line.text
            ) if curr_line.original_text else 0.0

            if text_diff < diff_threshold:
                # 差异小，保留后一段（通常有更好上下文）
                selected_lines.append(curr_line)
            else:
                # 差异大，保留修改幅度更大的一段
                if curr_modification >= prev_modification:
                    selected_lines.append(curr_line)
                else:
                    selected_lines.append(prev_line)

        return selected_lines

    def _normalize_merged_lines(self, lines: List[OptimizedLine]) -> List[OptimizedLine]:
        """
        规范化合并后的行

        重新分配ID并确保时间戳连续性。

        Args:
            lines: 合并后的行列表

        Returns:
            规范化后的行列表
        """
        normalized = []
        for i, line in enumerate(lines):
            normalized.append(OptimizedLine(
                text=line.text,
                start=line.start,
                end=line.end,
                is_modified=line.is_modified,
                original_text=line.original_text
            ))
        return normalized

    def get_overlap_lines_for_retry(
        self,
        segment_index: int,
        all_results: List[List[OptimizedLine]],
        expand_count: Optional[int] = None
    ) -> List[OptimizedLine]:
        """
        获取扩展重叠区

        当检测到重叠区域存在冲突时，获取扩展的重叠行用于重试。

        Args:
            segment_index: 当前分段索引
            all_results: 所有分段的结果列表
            expand_count: 扩展行数，如果为None则使用配置值

        Returns:
            扩展后的重叠区行列表

        Raises:
            ValueError: 输入参数无效
            IndexError: 分段索引无效
        """
        if all_results is None:
            raise ValueError("all_results不能为None")

        if segment_index < 0 or segment_index >= len(all_results):
            raise IndexError(f"无效的分段索引: {segment_index}")

        expand_count = expand_count or self.config.max_overlap_expand
        current_result = all_results[segment_index]

        overlap_lines = []

        # 获取前一分段的尾部
        if segment_index > 0:
            prev_result = all_results[segment_index - 1]
            prev_count = min(expand_count, len(prev_result))
            if prev_count > 0:
                overlap_lines.extend(prev_result[-prev_count:])

        # 添加当前分段
        overlap_lines.extend(current_result)

        # 获取后一分段的头部
        if segment_index < len(all_results) - 1:
            next_result = all_results[segment_index + 1]
            next_count = min(expand_count, len(next_result))
            if next_count > 0:
                overlap_lines.extend(next_result[:next_count])

        return overlap_lines

    def calculate_segment_ranges(self, total_lines: int) -> List[Tuple[int, int]]:
        """
        计算分段范围

        计算每个分段的起始和结束行号（不包含结束行）。
        每个分段包含segment_size行内容，后续段包含前一段的最后overlap_lines行作为重叠。

        Args:
            total_lines: 总行数

        Returns:
            分段范围列表，每个元素为(start, end)元组

        Raises:
            ValueError: 总行数无效
        """
        if total_lines < 0:
            raise ValueError("总行数不能为负数")

        if total_lines == 0:
            return []

        segment_size = self.config.segment_size
        overlap_lines = self.config.overlap_lines

        # 如果总行数小于等于分段大小，不需要分段
        if total_lines <= segment_size:
            return [(0, total_lines)]

        ranges = []
        start_idx = 0

        while start_idx < total_lines:
            # 计算当前分段的结束位置
            end_idx = min(start_idx + segment_size, total_lines)

            # 检查是否已经有分段覆盖到了这个位置
            if ranges and start_idx < ranges[-1][1]:
                # 如果当前起始位置已经被前一段覆盖，且剩余行数不多，合并到最后一段
                remaining = total_lines - ranges[-1][1]
                if remaining <= overlap_lines:
                    # 扩展最后一段到结尾
                    last_start = ranges[-1][0]
                    ranges[-1] = (last_start, total_lines)
                    break

            ranges.append((start_idx, end_idx))

            # 如果已经到达末尾，结束循环
            if end_idx >= total_lines:
                break

            # 下一段的起始位置（包含重叠）
            next_start = end_idx - overlap_lines

            # 避免无限循环：确保下一段的起始位置大于当前起始位置
            if next_start <= start_idx:
                next_start = end_idx

            # 确保下一段的起始位置不超过总行数
            if next_start >= total_lines:
                break

            start_idx = next_start

        return ranges

    def should_segment(self, total_lines: int) -> bool:
        """
        判断是否需要分段

        Args:
            total_lines: 总行数

        Returns:
            是否需要分段
        """
        return total_lines > self.config.segment_size
