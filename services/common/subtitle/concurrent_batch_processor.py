"""
并发批次处理器

实现大体积字幕的并发处理，使用asyncio进行AI API调用。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class BatchProcessingResult:
    """批次处理结果

    表示一个批次的处理结果。
    """
    batch_id: int
    success: bool
    optimized_subtitles: List[Dict[str, Any]]
    commands_count: int
    duration: float
    error: Optional[str] = None


class ConcurrentBatchProcessor:
    """并发批次处理器

    使用asyncio实现并发AI API调用，处理大体积字幕。
    """

    def __init__(self,
                 max_retries: int = 3,
                 timeout: int = 300,
                 max_concurrent: int = 5):
        """初始化并发处理器

        Args:
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
            max_concurrent: 最大并发数
        """
        self.max_retries = max_retries
        self.timeout = timeout  # 简单的超时时间（秒）
        self.max_concurrent = max_concurrent

        # 限制并发数的信号量
        self.semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(f"并发批次处理器初始化 - 重试: {max_retries}, "
                   f"超时: {timeout}秒, 并发数: {max_concurrent}")

    async def process_batches(self,
                            batches: List,
                            request_builder: Any,
                            ai_provider: Any,
                            command_parser: Any,
                            segment_processor: Any) -> List[BatchProcessingResult]:
        """并发处理多个批次

        Args:
            batches: 字幕批次列表
            request_builder: AI请求构建器
            ai_provider: AI提供商
            command_parser: 指令解析器
            segment_processor: 片段处理器

        Returns:
            批次处理结果列表
        """
        logger.info(f"开始并发处理 {len(batches)} 个批次")

        # 创建任务列表
        tasks = []
        for batch in batches:
            task = self._process_single_batch(
                batch=batch,
                request_builder=request_builder,
                ai_provider=ai_provider,
                command_parser=command_parser,
                segment_processor=segment_processor
            )
            tasks.append(task)

        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_type = type(result).__name__
                error_msg = str(result)
                logger.error(f"批次 {i+1} 处理失败 [{error_type}]: {error_msg}")
                processed_results.append(BatchProcessingResult(
                    batch_id=i+1,
                    success=False,
                    optimized_subtitles=[],
                    commands_count=0,
                    duration=0.0,
                    error=f"[{error_type}] {error_msg}"
                ))
            else:
                processed_results.append(result)

        # 统计成功和失败
        success_count = sum(1 for r in processed_results if r.success)
        logger.info(f"并发处理完成 - 成功: {success_count}/{len(batches)}")

        return processed_results

    async def _process_single_batch(self,
                                  batch: Any,
                                  request_builder: Any,
                                  ai_provider: Any,
                                  command_parser: Any,
                                  segment_processor: Any) -> BatchProcessingResult:
        """处理单个批次

        Args:
            batch: 字幕批次
            request_builder: AI请求构建器
            ai_provider: AI提供商
            command_parser: 指令解析器
            segment_processor: 片段处理器

        Returns:
            批次处理结果
        """
        start_time = time.time()
        batch_id = batch.batch_id

        try:
            # 使用信号量限制并发
            async with self.semaphore:
                # 构建AI请求
                request = request_builder.build_request(
                    subtitles=batch.subtitles,
                    system_prompt="",  # 将由调用者传入
                    provider=ai_provider.provider_name
                )

                # 调用AI API（带重试）
                ai_response = await self._call_ai_api_with_retry(
                    ai_provider, request
                )

                # 解析指令
                commands = command_parser.parse_response(ai_response)

                # 应用指令
                optimized_subtitles = segment_processor.process_subtitles(
                    batch.subtitles, commands
                )

                duration = time.time() - start_time

                logger.debug(f"批次 {batch_id} 处理成功 - "
                           f"字幕: {len(optimized_subtitles)}, 指令: {len(commands)}, "
                           f"耗时: {duration:.2f}秒")

                return BatchProcessingResult(
                    batch_id=batch_id,
                    success=True,
                    optimized_subtitles=optimized_subtitles,
                    commands_count=len(commands),
                    duration=duration
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"批次 {batch_id} 处理失败: {e}")

            return BatchProcessingResult(
                batch_id=batch_id,
                success=False,
                optimized_subtitles=[],
                commands_count=0,
                duration=duration,
                error=str(e)
            )

    async def _call_ai_api_with_retry(self, ai_provider, request) -> str:
        """带重试的AI API调用

        Args:
            ai_provider: AI提供商
            request: AI请求（包含messages字段）

        Returns:
            AI响应内容

        Raises:
            Exception: 重试后仍然失败
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                # 提取消息并调用AI提供商的异步方法
                messages = request.get('messages', [])
                response = await ai_provider.chat_completion(messages)
                return response

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.warning(f"AI API调用失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}, "
                                 f"{wait_time}秒后重试")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"AI API调用失败，已重试 {self.max_retries} 次: {e}")

        # 所有重试都失败
        raise last_error

    def get_statistics(self, results: List[BatchProcessingResult]) -> Dict[str, Any]:
        """获取处理统计

        Args:
            results: 批次处理结果列表

        Returns:
            统计信息
        """
        if not results:
            return {}

        total_duration = sum(r.duration for r in results)
        success_count = sum(1 for r in results if r.success)
        total_commands = sum(r.commands_count for r in results if r.success)

        return {
            'total_batches': len(results),
            'success_batches': success_count,
            'failed_batches': len(results) - success_count,
            'success_rate': success_count / len(results) * 100,
            'total_duration': total_duration,
            'avg_duration': total_duration / len(results),
            'total_commands': total_commands,
            'errors': [r.error for r in results if not r.success and r.error]
        }


class BatchResultMerger:
    """批次结果合并器

    正确处理重叠区域，合并多个批次的处理结果。
    """

    def __init__(self, overlap_size: int = 10):
        """初始化结果合并器

        Args:
            overlap_size: 重叠区域大小
        """
        self.overlap_size = overlap_size

        logger.info(f"批次结果合并器初始化 - 重叠大小: {overlap_size}")

    def merge_results(self, results: List[BatchProcessingResult]) -> List[Dict[str, Any]]:
        """合并批次结果

        Args:
            results: 批次处理结果列表（按batch_id排序）

        Returns:
            合并后的字幕列表

        Raises:
            ValueError: 如果有批次处理失败
        """
        # 检查是否有失败的任务
        failed_results = [r for r in results if not r.success]
        if failed_results:
            error_messages = [f"批次{r.batch_id}: {r.error}" for r in failed_results]
            raise ValueError(f"有 {len(failed_results)} 个批次处理失败: {error_messages}")

        # 按batch_id排序
        sorted_results = sorted(results, key=lambda r: r.batch_id)

        logger.info(f"开始合并 {len(sorted_results)} 个批次的处理结果")

        if not sorted_results:
            return []

        merged_subtitles = []
        total_commands = 0

        for i, result in enumerate(sorted_results):
            optimized_subtitles = result.optimized_subtitles
            total_commands += result.commands_count

            if i == 0:
                # 第一个批次：保留所有字幕
                merged_subtitles.extend(optimized_subtitles)
                logger.debug(f"合并批次 {result.batch_id} - 保留全部 {len(optimized_subtitles)} 条")
            else:
                # 后续批次：只保留主区域的字幕
                start_index = min(self.overlap_size, len(optimized_subtitles))
                main_subtitles = optimized_subtitles[start_index:]
                merged_subtitles.extend(main_subtitles)
                logger.debug(f"合并批次 {result.batch_id} - 丢弃前 {start_index} 条重叠，"
                           f"保留 {len(main_subtitles)} 条")

        logger.info(f"合并完成 - 总字幕: {len(merged_subtitles)}, "
                   f"总指令: {total_commands}")

        return merged_subtitles

    def validate_merge(self,
                      original_count: int,
                      merged_count: int,
                      batches_count: int) -> Dict[str, Any]:
        """验证合并结果

        Args:
            original_count: 原始字幕数量
            merged_count: 合并后字幕数量
            batches_count: 批次数量

        Returns:
            验证结果
        """
        # 计算期望的合并后数量
        # 假设每个批次大小为B，重叠为O
        # 合并后数量 = B * batches_count - O * (batches_count - 1)
        # 但实际可能因为指令执行而变化

        # 这里简化验证：如果合并后数量在合理范围内（> 原始数量 * 0.8）
        # 则认为合并成功
        min_expected = int(original_count * 0.8)
        max_expected = int(original_count * 1.2)  # 允许一定增长

        is_valid = min_expected <= merged_count <= max_expected

        return {
            'valid': is_valid,
            'original_count': original_count,
            'merged_count': merged_count,
            'batches_count': batches_count,
            'min_expected': min_expected,
            'max_expected': max_expected,
            'change_rate': (merged_count - original_count) / original_count * 100
        }