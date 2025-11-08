"""
滑窗重叠分段器

实现滑窗重叠分段策略，支持大体积字幕的并发处理。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SubtitleBatch:
    """字幕批次

    表示一个分段的字幕数据块。
    """
    batch_id: int
    start_index: int  # 主区域开始索引
    end_index: int    # 主区域结束索引
    overlap_start: int  # 重叠区域开始索引
    overlap_end: int    # 重叠区域结束索引
    subtitles: List[Dict[str, Any]]  # 包含重叠的完整字幕列表
    is_main: bool  # 是否为主区域（True）还是重叠区域（False）


class SlidingWindowSplitter:
    """滑窗重叠分段器

    将大量字幕分成多个批次，每批次包含重叠区域以保证上下文完整性。
    """

    def __init__(self, batch_size: int = 50, overlap_size: int = 10):
        """初始化分段器

        Args:
            batch_size: 主区域大小（每段处理的字幕条数）
            overlap_size: 重叠区域大小（从前一段保留的字幕数）
        """
        self.batch_size = batch_size
        self.overlap_size = overlap_size

        logger.info(f"滑窗分段器初始化 - batch_size: {batch_size}, overlap_size: {overlap_size}")

    def split_subtitles(self, subtitles: List[Dict[str, Any]]) -> List[SubtitleBatch]:
        """将字幕列表分割成批次

        Args:
            subtitles: 完整的字幕列表

        Returns:
            分段后的字幕批次列表
        """
        total_count = len(subtitles)
        logger.info(f"开始分段处理: {total_count}条字幕")

        if total_count == 0:
            logger.warning("字幕列表为空")
            return []

        batches = []
        batch_id = 1
        start_index = 0

        while start_index < total_count:
            # 计算主区域结束索引
            end_index = min(start_index + self.batch_size, total_count)

            # 计算重叠区域（前一batch的最后overlap_size条）
            overlap_start = max(0, start_index - self.overlap_size)
            overlap_end = start_index

            # 获取包含重叠的完整字幕列表
            batch_subtitles = subtitles[overlap_start:end_index]

            # 创建批次
            batch = SubtitleBatch(
                batch_id=batch_id,
                start_index=start_index,
                end_index=end_index,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                subtitles=batch_subtitles,
                is_main=True  # 所有批次都作为主区域处理
            )

            batches.append(batch)
            logger.debug(f"创建批次 {batch_id}: 主区域[{start_index}-{end_index}), 重叠[{overlap_start}-{overlap_end})")

            # 移动到下一个主区域开始位置
            start_index = end_index
            batch_id += 1

        logger.info(f"分段完成: {len(batches)}个批次")
        return batches

    def merge_results(self, results: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """合并多个批次的处理结果

        Args:
            results: 各批次的优化后字幕列表

        Returns:
            合并后的完整字幕列表
        """
        logger.info(f"开始合并结果: {len(results)}个批次")

        if not results:
            return []

        # 只保留主区域的字幕，丢弃重叠区域
        merged_subtitles = []
        for i, batch_result in enumerate(results):
            if i == 0:
                # 第一个批次：保留所有字幕
                merged_subtitles.extend(batch_result)
            else:
                # 后续批次：只保留主区域的字幕
                start = min(self.overlap_size, len(batch_result))
                merged_subtitles.extend(batch_result[start:])

        logger.info(f"合并完成: {len(merged_subtitles)}条字幕")
        return merged_subtitles

    def validate_batch_count(self, total_count: int, threshold: int = 100) -> Tuple[bool, str]:
        """验证是否需要分段处理

        Args:
            total_count: 字幕总数
            threshold: 分段阈值

        Returns:
            (是否需要分段, 原因)
        """
        if total_count > threshold:
            reason = f"字幕数量 {total_count} 超过阈值 {threshold}"
            logger.info(f"需要分段处理 - {reason}")
            return True, reason
        else:
            reason = f"字幕数量 {total_count} 未超过阈值 {threshold}"
            logger.debug(f"无需分段处理 - {reason}")
            return False, reason

    def get_batch_info(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, int]]:
        """获取分批信息

        Args:
            subtitles: 字幕列表

        Returns:
            每个批次的统计信息
        """
        batches = self.split_subtitles(subtitles)
        return [
            {
                "batch_id": batch.batch_id,
                "main_count": batch.end_index - batch.start_index,
                "overlap_count": batch.start_index - batch.overlap_start,
                "total_count": len(batch.subtitles)
            }
            for batch in batches
        ]