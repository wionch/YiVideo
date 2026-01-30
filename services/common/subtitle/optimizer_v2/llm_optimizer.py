"""
LLM优化器模块

提供基于大语言模型的字幕优化功能，支持重试机制和验证。
"""

import re
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    OptimizedLine,
    SegmentTask,
    OptimizationResult,
    OptimizationStatus,
)
from services.common.subtitle.optimizer_v2.llm_providers import LLMProvider, LLMProviderFactory
from services.common.subtitle.optimizer_v2.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMOptimizerConfig:
    """LLM优化器配置"""
    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数退避基数


class LLMOptimizer:
    """LLM优化器

    使用大语言模型优化字幕内容，支持自动重试和结果验证。

    Attributes:
        provider: AI提供商实例
        config: LLM配置
        retry_config: 重试配置
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        llm_config: Optional[LLMConfig] = None,
        retry_config: Optional[LLMOptimizerConfig] = None,
    ):
        """初始化LLM优化器

        Args:
            provider: LLM提供商实例，如果为None则使用默认配置创建
            llm_config: LLM配置
            retry_config: 重试配置
        """
        self.llm_config = llm_config or LLMConfig()
        self.retry_config = retry_config or LLMOptimizerConfig()

        if provider is None:
            provider_config = {
                "model": self.llm_config.model,
                "max_tokens": self.llm_config.max_tokens,
                "temperature": self.llm_config.temperature,
            }
            self.provider = LLMProviderFactory.create_provider("gemini", provider_config)
        else:
            self.provider = provider

    def _build_system_prompt(self) -> str:
        """构建System Prompt

        Returns:
            系统提示词
        """
        return """你是一个专业的字幕优化助手。

你的任务是优化字幕文本，遵循以下规则：
1. 修正错别字和语法错误
2. 优化标点符号使用
3. 保持原意不变
4. 保持行数不变（输入多少行，输出必须多少行）
5. 每行文本对应原始ID必须保持一致

输入格式：
每行格式为 "[ID]文本内容"
例如：
[1]这是一段字幕文本
[2]这是第二段字幕

输出格式要求：
- 必须保持与输入相同的行数
- 每行必须包含ID和优化后的文本
- 格式：[ID]优化后的文本
- 只输出优化后的内容，不要添加解释

示例输出：
[1]这是一段优化后的字幕文本
[2]这是第二段优化后的字幕"""

    def _build_user_prompt(
        self,
        task: SegmentTask,
        context_before: Optional[str] = None,
        context_after: Optional[str] = None,
    ) -> str:
        """构建User Prompt

        Args:
            task: 分段任务
            context_before: 前文内容（用于上下文理解）
            context_after: 后文内容（用于上下文理解）

        Returns:
            用户提示词
        """
        lines = []

        # 添加上下文前文
        if context_before:
            lines.append("【前文】")
            lines.append(context_before)
            lines.append("")

        # 添加需要优化的内容
        lines.append("【需要优化的字幕】")
        for segment in task.segments:
            line = f"[{segment.id}]{segment.text}"
            lines.append(line)

        # 添加上下文后文
        if context_after:
            lines.append("")
            lines.append("【后文】")
            lines.append(context_after)

        lines.append("")
        lines.append("请优化上述字幕，保持行数和ID一致，只输出优化后的内容。")

        return "\n".join(lines)

    def _parse_response(self, response: str, task: SegmentTask) -> List[OptimizedLine]:
        """解析LLM响应

        Args:
            response: LLM响应文本
            task: 原始任务

        Returns:
            优化后的字幕行列表

        Raises:
            ValueError: 解析失败或格式错误
        """
        if not response or not response.strip():
            raise ValueError("LLM响应为空")

        lines = response.strip().split("\n")
        optimized_lines = []
        expected_ids = {seg.id for seg in task.segments}
        found_ids = set()

        # 构建ID到原始段的映射
        id_to_segment = {seg.id: seg for seg in task.segments}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 解析格式: [ID]文本内容
            match = re.match(r"^\[(\d+)\](.+)$", line)
            if not match:
                # 尝试更宽松的格式
                match = re.match(r"^\[(\d+)\]\s*(.+)$", line)

            if not match:
                logger.warning(f"无法解析行: {line}")
                continue

            try:
                seg_id = int(match.group(1))
                text = match.group(2).strip()

                # 验证ID是否在预期范围内
                if seg_id not in expected_ids:
                    logger.warning(f"ID {seg_id} 不在预期范围内: {expected_ids}")
                    continue

                if seg_id in found_ids:
                    logger.warning(f"ID {seg_id} 重复出现")
                    continue

                found_ids.add(seg_id)

                # 获取原始段的时间戳和文本
                original_seg = id_to_segment.get(seg_id)
                if original_seg:
                    start = original_seg.start
                    end = original_seg.end
                    original_text = original_seg.text
                else:
                    # 不应该发生，因为已经验证了ID
                    start = 0.0
                    end = 0.0
                    original_text = None

                optimized_lines.append(
                    OptimizedLine(
                        text=text,
                        start=start,
                        end=end,
                        is_modified=text != original_text,
                        original_text=original_text,
                    )
                )

            except (ValueError, IndexError) as e:
                logger.warning(f"解析行失败: {line}, 错误: {e}")
                continue

        if not optimized_lines:
            raise ValueError("未能从响应中解析出任何有效字幕行")

        # 按开始时间排序
        optimized_lines.sort(key=lambda x: x.start)

        return optimized_lines

    def _validate_id_range(
        self,
        optimized_lines: List[OptimizedLine],
        task: SegmentTask,
    ) -> Tuple[bool, Optional[str]]:
        """校验ID范围

        验证优化后的字幕行ID是否与本段范围一致。

        Args:
            optimized_lines: 优化后的字幕行列表
            task: 原始任务

        Returns:
            (是否有效, 错误信息)
        """
        # 首先检查行数是否一致
        if len(optimized_lines) != len(task.segments):
            return (
                False,
                f"行数不一致: 预期{len(task.segments)}行，实际{len(optimized_lines)}行"
            )

        expected_ids = {seg.id for seg in task.segments}
        actual_ids = set()

        # 提取ID（从start时间反查ID）
        id_to_time_map = {seg.id: (seg.start, seg.end) for seg in task.segments}

        for line in optimized_lines:
            # 根据时间范围查找对应的ID
            found_id = None
            for seg_id, (start, end) in id_to_time_map.items():
                if abs(line.start - start) < 0.1 and abs(line.end - end) < 0.1:
                    found_id = seg_id
                    break

            if found_id is not None:
                actual_ids.add(found_id)

        # 检查ID集合是否一致
        if actual_ids != expected_ids:
            missing = expected_ids - actual_ids
            extra = actual_ids - expected_ids
            errors = []
            if missing:
                errors.append(f"缺少ID: {sorted(missing)}")
            if extra:
                errors.append(f"多余ID: {sorted(extra)}")
            return False, "; ".join(errors)

        return True, None

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """计算指数退避延迟

        Args:
            attempt: 当前尝试次数（从0开始）

        Returns:
            延迟时间（秒）
        """
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** attempt
        )
        return min(delay, self.retry_config.max_delay)

    async def optimize_segment(
        self,
        task: SegmentTask,
        context_before: Optional[str] = None,
        context_after: Optional[str] = None,
    ) -> OptimizationResult:
        """优化单个段

        带自动重试机制的段优化。

        Args:
            task: 分段任务
            context_before: 前文内容
            context_after: 后文内容

        Returns:
            优化结果
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(task, context_before, context_after)

        last_error = None

        for attempt in range(self.retry_config.max_retries):
            try:
                logger.info(
                    f"开始优化任务 {task.task_id}, "
                    f"尝试 {attempt + 1}/{self.retry_config.max_retries}"
                )

                # 调用LLM
                response = await self.provider.call(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=self.llm_config.max_tokens,
                    temperature=self.llm_config.temperature,
                )

                # 解析响应
                optimized_lines = self._parse_response(response, task)

                # 验证ID范围
                is_valid, error_msg = self._validate_id_range(optimized_lines, task)
                if not is_valid:
                    raise ValueError(f"验证失败: {error_msg}")

                logger.info(
                    f"任务 {task.task_id} 优化成功，"
                    f"生成 {len(optimized_lines)} 行"
                )

                return OptimizationResult(
                    task_id=task.task_id,
                    status=OptimizationStatus.COMPLETED,
                    optimized_lines=optimized_lines,
                    metadata={
                        "attempts": attempt + 1,
                        "original_segments": len(task.segments),
                        "optimized_lines": len(optimized_lines),
                    },
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    f"任务 {task.task_id} 尝试 {attempt + 1} 失败: {e}"
                )

                # 如果不是最后一次尝试，则等待后重试
                if attempt < self.retry_config.max_retries - 1:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.info(f"等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)

        # 所有重试都失败了
        error_message = f"优化失败，已重试{self.retry_config.max_retries}次: {last_error}"
        logger.error(error_message)

        return OptimizationResult(
            task_id=task.task_id,
            status=OptimizationStatus.FAILED,
            error_message=error_message,
            metadata={
                "attempts": self.retry_config.max_retries,
                "last_error": str(last_error),
            },
        )
