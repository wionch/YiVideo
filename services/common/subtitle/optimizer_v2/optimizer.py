"""
字幕优化器 V2 - 主优化器入口

提供完整的字幕优化流程，包括加载、分段、LLM优化、合并和时间戳重建。
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import SubtitleOptimizerConfig
from .debug_logger import DebugLogger
from .extractor import SubtitleExtractor
from .llm_optimizer import LLMOptimizer
from .models import OptimizationResult, OptimizedLine, SubtitleSegment
from .segment_manager import SegmentManager
from .timestamp_reconstructor import TimestampReconstructor

logger = logging.getLogger(__name__)


class SubtitleOptimizerV2:
    """
    字幕优化器 V2 主类

    提供完整的字幕优化流程，包括：
    1. 从文件或字典加载字幕数据
    2. 分段处理
    3. 并发LLM优化
    4. 合并结果
    5. 重建时间戳
    6. 输出JSON

    Attributes:
        config: 优化器配置
        extractor: 字幕提取器
        segment_manager: 分段管理器
        llm_optimizer: LLM优化器
        timestamp_reconstructor: 时间戳重建器
        debug_logger: 调试日志记录器
    """

    def __init__(
        self,
        config: Optional[SubtitleOptimizerConfig] = None,
        llm_optimizer: Optional[LLMOptimizer] = None,
    ):
        """
        初始化字幕优化器

        Args:
            config: 优化器配置，如果为None则使用默认配置
            llm_optimizer: LLM优化器实例，如果为None则延迟创建
        """
        self.config = config or SubtitleOptimizerConfig()
        self.extractor = SubtitleExtractor()
        self.segment_manager = SegmentManager(self.config)
        self._llm_optimizer = llm_optimizer  # 可能为None，延迟初始化
        self.timestamp_reconstructor = TimestampReconstructor()
        self.debug_logger = DebugLogger(
            log_dir=self.config.debug.log_dir,
            enabled=self.config.debug.enabled
        )

        # 内部状态
        self._original_segments: List[SubtitleSegment] = []
        self._optimized_lines: List[OptimizedLine] = []
        self._optimization_results: List[OptimizationResult] = []

    @property
    def llm_optimizer(self) -> LLMOptimizer:
        """
        获取LLM优化器实例

        使用延迟初始化，避免在构造函数中创建provider

        Returns:
            LLM优化器实例
        """
        if self._llm_optimizer is None:
            self._llm_optimizer = LLMOptimizer(llm_config=self.config.llm)
        return self._llm_optimizer

    def load_from_file(self, file_path: str) -> "SubtitleOptimizerV2":
        """
        从JSON文件加载字幕数据

        Args:
            file_path: JSON文件路径

        Returns:
            self: 支持链式调用

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON格式无效
        """
        logger.info(f"从文件加载字幕数据: {file_path}")
        self.extractor.load_from_file(file_path)
        self._original_segments = self.extractor.get_all_segments()
        logger.info(f"成功加载 {len(self._original_segments)} 个字幕段")
        return self

    def load_from_dict(self, data: Dict[str, Any]) -> "SubtitleOptimizerV2":
        """
        从字典加载字幕数据

        Args:
            data: 包含字幕数据的字典

        Returns:
            self: 支持链式调用

        Raises:
            ValueError: 数据格式无效
        """
        logger.info("从字典加载字幕数据")
        self.extractor.load_from_dict(data)
        self._original_segments = self.extractor.get_all_segments()
        logger.info(f"成功加载 {len(self._original_segments)} 个字幕段")
        return self

    async def optimize(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        执行主优化流程

        完整的优化流程：
        1. 检查是否已加载数据
        2. 分段处理
        3. 并发LLM优化
        4. 合并结果
        5. 重建时间戳
        6. 输出JSON（可选）

        Args:
            output_path: 可选的输出文件路径，如果提供则将结果保存到文件

        Returns:
            优化结果字典，包含优化后的字幕段和元数据

        Raises:
            ValueError: 未加载数据或优化过程中发生错误
        """
        if not self._original_segments:
            raise ValueError("未加载字幕数据，请先调用 load_from_file 或 load_from_dict")

        total_lines = len(self._original_segments)
        logger.info(f"开始优化流程，共 {total_lines} 行字幕")

        # 步骤1: 提取格式化的字幕行
        formatted_lines = self.extractor.extract_formatted_lines()
        logger.debug(f"提取了 {len(formatted_lines)} 行格式化字幕")

        # 步骤2: 分段
        segment_tasks = self.segment_manager.create_segments(
            formatted_lines, self._original_segments
        )
        logger.info(f"分成 {len(segment_tasks)} 个任务段")

        # 步骤3: 并发LLM优化
        self._optimization_results = await self._optimize_segments(segment_tasks)
        logger.info(f"完成 {len(self._optimization_results)} 个段的优化")

        # 检查是否有失败的任务
        failed_results = [r for r in self._optimization_results if r.error_message]
        if failed_results:
            failed_count = len(failed_results)
            logger.warning(f"有 {failed_count} 个段优化失败")
            # 继续处理成功的段

        # 步骤4: 合并结果
        segment_results = [
            r.optimized_lines for r in self._optimization_results
            if r.optimized_lines
        ]
        if not segment_results:
            raise ValueError("所有段优化都失败了，无法生成结果")

        self._optimized_lines = self.segment_manager.merge_segments(segment_results)
        logger.info(f"合并后共 {len(self._optimized_lines)} 行")

        # 步骤5: 重建时间戳
        word_timestamps_list = self.timestamp_reconstructor.reconstruct_all(
            self._original_segments, self._optimized_lines
        )
        logger.info(f"完成时间戳重建，共 {len(word_timestamps_list)} 段")

        # 步骤6: 构建输出
        result = self._build_output(word_timestamps_list)

        # 步骤7: 保存到文件（如果指定了路径）
        if output_path:
            self._save_to_file(result, output_path)

        logger.info("优化流程完成")
        return result

    async def _optimize_segments(
        self, segment_tasks: List[Any]
    ) -> List[OptimizationResult]:
        """
        并发优化所有分段

        使用 asyncio.Semaphore 控制并发数，避免同时发送过多请求。

        Args:
            segment_tasks: 分段任务列表

        Returns:
            各段的优化结果列表
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def optimize_with_limit(task: Any) -> OptimizationResult:
            async with semaphore:
                # 记录请求日志
                if self.debug_logger.is_enabled():
                    self.debug_logger.log_request(
                        task_id=task.task_id,
                        segment_idx=int(task.task_id.split("_")[-1]),
                        prompt=f"优化 {len(task.segments)} 个字幕段",
                        model=self.config.llm.model,
                    )

                result = await self.llm_optimizer.optimize_segment(task)

                # 记录响应日志
                if self.debug_logger.is_enabled():
                    self.debug_logger.log_response(
                        task_id=task.task_id,
                        segment_idx=int(task.task_id.split("_")[-1]),
                        response=f"生成 {len(result.optimized_lines)} 行",
                    )

                # 记录错误日志
                if result.error_message and self.debug_logger.is_enabled():
                    self.debug_logger.log_error(
                        task_id=task.task_id,
                        segment_idx=int(task.task_id.split("_")[-1]),
                        error=Exception(result.error_message),
                    )

                return result

        # 并发执行所有任务
        tasks = [optimize_with_limit(task) for task in segment_tasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        processed_results: List[OptimizationResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"任务 {segment_tasks[i].task_id} 发生异常: {result}")
                processed_results.append(
                    OptimizationResult(
                        task_id=segment_tasks[i].task_id,
                        status="failed",
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    def _build_output(
        self, word_timestamps_list: List[List[Any]]
    ) -> Dict[str, Any]:
        """
        构建输出结果

        Args:
            word_timestamps_list: 词级时间戳列表的列表

        Returns:
            完整的输出结果字典
        """
        segments = []
        for i, (line, words) in enumerate(zip(self._optimized_lines, word_timestamps_list)):
            segment = {
                "id": i + 1,
                "start": line.start,
                "end": line.end,
                "text": line.text,
                "is_modified": line.is_modified,
                "words": [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    }
                    for w in words
                ],
            }
            if line.original_text:
                segment["original_text"] = line.original_text
            segments.append(segment)

        # 计算统计信息
        modified_count = sum(1 for line in self._optimized_lines if line.is_modified)

        return {
            "metadata": {
                "total_lines": len(segments),
                "modified_lines": modified_count,
                "segment_count": len(self._optimization_results),
                "config": self.config.to_dict(),
            },
            "segments": segments,
        }

    def _save_to_file(self, result: Dict[str, Any], output_path: str) -> None:
        """
        保存结果到JSON文件

        Args:
            result: 结果字典
            output_path: 输出文件路径

        Raises:
            IOError: 文件写入失败
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"结果已保存到: {output_path}")

    def get_optimized_lines(self) -> List[OptimizedLine]:
        """
        获取优化后的字幕行列表

        Returns:
            优化后的字幕行列表
        """
        return self._optimized_lines.copy()

    def get_original_segments(self) -> List[SubtitleSegment]:
        """
        获取原始字幕段列表

        Returns:
            原始字幕段列表
        """
        return self._original_segments.copy()

    def get_optimization_results(self) -> List[OptimizationResult]:
        """
        获取各段的优化结果

        Returns:
            优化结果列表
        """
        return self._optimization_results.copy()

    def get_total_lines(self) -> int:
        """
        获取总行数

        Returns:
            原始字幕段数量
        """
        return len(self._original_segments)
