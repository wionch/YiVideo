"""
主要字幕优化器类

整合所有字幕优化组件，实现完整的AI字幕优化工作流。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from .subtitle_extractor import SubtitleExtractor
from .ai_request_builder import AIRequestBuilder
from .ai_command_parser import AICommandParser
from .prompt_loader import PromptLoader
from .sliding_window_splitter import SlidingWindowSplitter, SubtitleBatch
from .subtitle_segment_processor import SubtitleSegmentProcessor
from .optimized_file_generator import OptimizedFileGenerator
from .ai_providers import AIProviderFactory

logger = logging.getLogger(__name__)


class SubtitleOptimizer:
    """主要字幕优化器

    整合字幕优化工作流的完整流程：
    1. 提取字幕数据
    2. 加载系统提示词
    3. 构建AI请求
    4. 调用AI API
    5. 解析优化指令
    6. 应用优化指令
    7. 生成优化文件
    """

    def __init__(self,
                 batch_size: int = 50,
                 overlap_size: int = 10,
                 provider: str = "deepseek",
                 max_retries: int = 3,
                 timeout: int = 300,
                 max_concurrent: int = 5,
                 batch_threshold: int = 100):
        """初始化字幕优化器

        Args:
            batch_size: 批处理大小
            overlap_size: 重叠区域大小
            provider: AI提供商
            max_retries: 最大重试次数
            timeout: API调用超时时间（秒）
            max_concurrent: 最大并发数
            batch_threshold: 启用批处理的字幕数量阈值
        """
        self.batch_size = batch_size
        self.overlap_size = overlap_size
        self.provider = provider
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.batch_threshold = batch_threshold

        # 初始化各个组件
        self.extractor = SubtitleExtractor()
        self.request_builder = AIRequestBuilder()
        self.command_parser = AICommandParser()
        self.prompt_loader = PromptLoader()
        self.segment_processor = SubtitleSegmentProcessor()
        self.file_generator = OptimizedFileGenerator()
        self.ai_factory = AIProviderFactory()

        # 滑窗分段器（仅在大体积字幕时使用）
        self.splitter = SlidingWindowSplitter(
            batch_size=batch_size,
            overlap_size=overlap_size
        )

        # 导入并发处理器
        from .concurrent_batch_processor import ConcurrentBatchProcessor, BatchResultMerger
        self.concurrent_processor = ConcurrentBatchProcessor(
            max_retries=max_retries,
            timeout=timeout,
            max_concurrent=max_concurrent
        )
        self.result_merger = BatchResultMerger(overlap_size=overlap_size)

        logger.info(f"字幕优化器初始化完成 - 提供商: {provider}, "
                   f"批次大小: {batch_size}, 重叠大小: {overlap_size}, "
                   f"并发数: {max_concurrent}, 重试: {max_retries}")

    def optimize_subtitles(self,
                          transcribe_file_path: str,
                          output_file_path: Optional[str] = None,
                          prompt_file_path: Optional[str] = None) -> Dict[str, Any]:
        """优化字幕文件

        Args:
            transcribe_file_path: 原始转录文件路径
            output_file_path: 输出文件路径，如果为None则自动生成
            prompt_file_path: 系统提示词文件路径

        Returns:
            优化结果字典，包含统计信息和文件路径

        Raises:
            FileNotFoundError: 文件不存在
            Exception: 优化过程中出现错误
        """
        start_time = time.time()
        logger.info(f"开始优化字幕文件: {transcribe_file_path}")

        try:
            # 1. 提取字幕数据
            subtitles = self.extractor.extract_subtitles(transcribe_file_path)

            if not subtitles:
                logger.warning("字幕列表为空，无法优化")
                return self._create_error_result("字幕列表为空")

            # 2. 加载系统提示词
            system_prompt = self.prompt_loader.load_prompt(prompt_file_path)

            # 3. 检查是否需要分段处理
            need_batch, reason = self.splitter.validate_batch_count(
                len(subtitles), threshold=self.batch_threshold
            )

            if need_batch:
                logger.info(f"启用批量处理 - {reason}")
                result = self._process_with_batching(
                    subtitles, system_prompt, output_file_path, start_time
                )
            else:
                logger.info("启用单批处理")
                result = self._process_single_batch(
                    subtitles, system_prompt, transcribe_file_path,
                    output_file_path, start_time
                )

            # 记录成功信息
            processing_time = time.time() - start_time
            logger.info(f"字幕优化完成 - 耗时: {processing_time:.2f}秒")

            return {
                'success': True,
                'file_path': result['file_path'],
                'processing_time': processing_time,
                'subtitles_count': len(subtitles),
                'commands_applied': result.get('commands_count', 0),
                'provider': self.provider,
                'batch_mode': need_batch,
                'batches_count': result.get('batches_count', 1)
            }

        except Exception as e:
            logger.error(f"字幕优化失败: {e}", exc_info=True)
            return self._create_error_result(str(e))

    def _process_single_batch(self,
                            subtitles: List[Dict[str, Any]],
                            system_prompt: str,
                            transcribe_file_path: str,
                            output_file_path: Optional[str],
                            start_time: float) -> Dict[str, Any]:
        """单批处理（无需分段）

        Args:
            subtitles: 字幕列表
            system_prompt: 系统提示词
            transcribe_file_path: 原始文件路径
            output_file_path: 输出文件路径
            start_time: 开始时间

        Returns:
            处理结果
        """
        # 构建AI请求
        request = self.request_builder.build_request(
            subtitles, system_prompt, self.provider
        )

        # 调用AI API
        ai_response = self._call_ai_api(request)

        # 解析指令
        commands = self.command_parser.parse_response(ai_response)

        # 应用指令
        optimized_subtitles = self.segment_processor.process_subtitles(
            subtitles, commands
        )

        # 生成输出路径
        if output_file_path is None:
            output_file_path = self.file_generator.generate_output_path(
                "default", transcribe_file_path, "optimized"
            )

        # 生成优化文件
        optimization_info = {
            'provider': self.provider,
            'commands_count': len(commands),
            'processing_time': time.time() - start_time
        }

        self.file_generator.generate_optimized_file(
            transcribe_file_path,
            optimized_subtitles,
            output_file_path,
            optimization_info
        )

        return {
            'file_path': output_file_path,
            'commands_count': len(commands),
            'batches_count': 1
        }

    def _process_with_batching(self,
                             subtitles: List[Dict[str, Any]],
                             system_prompt: str,
                             output_file_path: Optional[str],
                             start_time: float) -> Dict[str, Any]:
        """批量处理（分段并发）

        Args:
            subtitles: 字幕列表
            system_prompt: 系统提示词
            output_file_path: 输出文件路径
            start_time: 开始时间

        Returns:
            处理结果
        """
        import asyncio

        # 分段
        batches = self.splitter.split_subtitles(subtitles)
        logger.info(f"[批处理] 分割为 {len(batches)} 个批次 - "
                   f"批次大小: {self.batch_size}, 重叠: {self.overlap_size}")

        # 使用asyncio.run执行异步并发处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 准备AI提供商
            ai_provider = self.ai_factory.create_provider(self.provider)

            # 并发处理各批次
            batch_results = loop.run_until_complete(
                self.concurrent_processor.process_batches(
                    batches=batches,
                    request_builder=self.request_builder,
                    ai_provider=ai_provider,
                    command_parser=self.command_parser,
                    segment_processor=self.segment_processor
                )
            )

            # 获取统计信息
            stats = self.concurrent_processor.get_statistics(batch_results)
            logger.info(f"[批处理] 处理统计: {stats}")

            # 检查是否有失败的任务
            if stats['failed_batches'] > 0:
                error_msg = f"有 {stats['failed_batches']} 个批次处理失败"
                logger.error(f"[批处理] {error_msg}")
                raise RuntimeError(error_msg)

            # 合并结果
            merged_subtitles = self.result_merger.merge_results(batch_results)

            # 验证合并结果
            merge_validation = self.result_merger.validate_merge(
                original_count=len(subtitles),
                merged_count=len(merged_subtitles),
                batches_count=len(batches)
            )

            if not merge_validation['valid']:
                logger.warning(f"[批处理] 合并结果异常: {merge_validation}")

            total_commands = stats['total_commands']

            # 生成输出路径
            if output_file_path is None:
                output_file_path = self.file_generator.generate_output_path(
                    "default", "default.json", "optimized"
                )

            # 生成优化文件
            optimization_info = {
                'provider': self.provider,
                'commands_count': total_commands,
                'processing_time': time.time() - start_time
            }

        self.file_generator.generate_optimized_file(
            "dummy.json",  # 原始路径不重要，重要的是输出数据
            merged_subtitles,
            output_file_path,
            optimization_info
        )

        return {
            'file_path': output_file_path,
            'commands_count': total_commands,
            'batches_count': len(batches)
        }

    def _call_ai_api(self, request: Dict[str, Any]) -> str:
        """调用AI API

        Args:
            request: AI请求字典

        Returns:
            AI响应内容

        Raises:
            Exception: API调用失败
        """
        try:
            # 使用AI提供商工厂
            provider = self.ai_factory.create_provider(self.provider)
            response = provider.generate_text(request)

            logger.info(f"AI API调用成功，提供商: {self.provider}")
            return response

        except Exception as e:
            logger.error(f"AI API调用失败: {e}")
            raise

    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """创建错误结果

        Args:
            error_message: 错误信息

        Returns:
            错误结果字典
        """
        return {
            'success': False,
            'error': error_message,
            'file_path': None,
            'commands_applied': 0
        }

    def get_statistics(self) -> Dict[str, Any]:
        """获取优化器统计信息

        Returns:
            统计信息
        """
        return {
            'provider': self.provider,
            'batch_size': self.batch_size,
            'overlap_size': self.overlap_size,
            'has_splitter': self.splitter is not None
        }