"""
字幕校正模块

提供基于AI的字幕校正功能，支持多个AI服务提供商。
用于对faster-whisper转录的字幕进行智能校正、修复和优化。
"""

import os
import asyncio
import aiohttp
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .subtitle_parser import SRTParser, SubtitleEntry
from .ai_providers import AIProviderFactory
from .subtitle_correction_config import SubtitleCorrectionConfig
from .token_utils import should_batch_subtitle, token_estimator
from services.common.config_loader import CONFIG
from services.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CorrectionResult:
    """字幕校正结果"""
    success: bool
    corrected_subtitle_path: Optional[str] = None
    original_subtitle_path: Optional[str] = None
    provider_used: Optional[str] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None
    statistics: Optional[Dict[str, Any]] = None


class SubtitleCorrector:
    """
    字幕校正器主类

    支持多个AI服务提供商进行字幕校正：
    - DeepSeek (deepseek-chat)
    - Gemini (gemini-pro)
    - 智谱AI (glm-4)
    - 火山引擎 (doubao-pro)
    """

    def __init__(self, provider: Optional[str] = None, config: Optional[Dict] = None):
        """
        初始化字幕校正器

        Args:
            provider: AI服务提供商，如果为None则使用配置中的默认提供商
            config: 自定义配置，如果为None则使用全局配置
        """
        self.config = SubtitleCorrectionConfig(config or CONFIG.get('subtitle_correction', {}))
        self.provider_name = provider or self.config.default_provider
        self.parser = SRTParser()

        # 初始化AI提供商
        try:
            self.ai_provider = AIProviderFactory.create_provider(
                self.provider_name,
                self.config.get_provider_config(self.provider_name)
            )
            logger.info(f"字幕校正器初始化成功，使用AI提供商: {self.provider_name}")
        except Exception as e:
            logger.error(f"初始化AI提供商失败: {e}")
            raise

    async def correct_subtitle_file(
        self,
        subtitle_path: str,
        output_path: Optional[str] = None,
        system_prompt_path: Optional[str] = None
    ) -> CorrectionResult:
        """
        校正字幕文件

        Args:
            subtitle_path: 原始字幕文件路径
            output_path: 输出文件路径，如果为None则自动生成
            system_prompt_path: 系统提示词文件路径，如果为None则使用配置中的路径

        Returns:
            CorrectionResult: 校正结果
        """
        start_time = time.time()

        try:
            # 验证输入文件
            if not os.path.exists(subtitle_path):
                raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")

            # 解析字幕文件
            logger.info(f"开始解析字幕文件: {subtitle_path}")
            subtitle_entries = self.parser.parse_file(subtitle_path)

            if not subtitle_entries:
                raise ValueError("字幕文件为空或格式无效")

            logger.info(f"成功解析 {len(subtitle_entries)} 条字幕")

            # 执行本地短字幕合并预处理
            if self.config.enable_local_merge:
                subtitle_entries = self._apply_local_merge(subtitle_entries)
                logger.info(f"本地合并后剩余 {len(subtitle_entries)} 条字幕")

            # 生成输出路径
            if not output_path:
                subtitle_dir = os.path.dirname(subtitle_path)
                subtitle_name = os.path.basename(subtitle_path)
                name_without_ext = os.path.splitext(subtitle_name)[0]
                output_path = os.path.join(subtitle_dir, f"{name_without_ext}_corrected.srt")

            # 读取系统提示词
            system_prompt = self._load_system_prompt(system_prompt_path)

            # 准备AI请求
            subtitle_text = self.parser.entries_to_text(subtitle_entries)

            # 使用智能token估算判断是否需要分批处理
            should_batch, recommended_batch_size, batch_info = should_batch_subtitle(
                subtitle_text, self.config.max_subtitle_length
            )

            if should_batch:
                logger.info(f"启用智能分批处理: 原因={', '.join(batch_info['reasons'])}, "
                           f"文本长度={batch_info['text_length']}字符, "
                           f"估算tokens={batch_info['token_estimate']['total_input_tokens']}, "
                           f"推荐批次大小={recommended_batch_size}字符")
                # 使用基于字幕条目的分批处理
                corrected_entries = await self._batch_correct_entries(subtitle_entries, system_prompt, recommended_batch_size)
                corrected_text = self.parser.entries_to_text(corrected_entries)
            else:
                logger.info(f"启用单批处理: 文本长度={batch_info['text_length']}字符, "
                           f"估算tokens={batch_info['token_estimate']['total_input_tokens']}")
                corrected_text = await self._single_correct(subtitle_text, system_prompt)
                corrected_entries = self.parser.parse_text(corrected_text)

            # 验证校正结果
            if len(corrected_entries) == 0:
                raise ValueError("AI校正结果为空")

            # 保持原始时间戳
            corrected_entries = self._preserve_timestamps(subtitle_entries, corrected_entries)

            # 写入校正后的字幕文件
            self.parser.write_file(corrected_entries, output_path)

            processing_time = time.time() - start_time

            # 生成统计信息
            statistics = {
                'original_entries': len(subtitle_entries),
                'corrected_entries': len(corrected_entries),
                'original_characters': len(subtitle_text),
                'corrected_characters': len(corrected_text),
                'processing_time': processing_time,
                'provider': self.provider_name
            }

            logger.info(f"字幕校正完成，耗时: {processing_time:.2f}秒")
            logger.info(f"原始字幕: {statistics['original_entries']} 条，校正后: {statistics['corrected_entries']} 条")

            return CorrectionResult(
                success=True,
                corrected_subtitle_path=output_path,
                original_subtitle_path=subtitle_path,
                provider_used=self.provider_name,
                processing_time=processing_time,
                statistics=statistics
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"字幕校正失败: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return CorrectionResult(
                success=False,
                original_subtitle_path=subtitle_path,
                provider_used=self.provider_name,
                processing_time=processing_time,
                error_message=error_msg
            )

    def _apply_local_merge(self, subtitle_entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        应用本地短字幕合并预处理

        Args:
            subtitle_entries: 原始字幕条目列表

        Returns:
            List[SubtitleEntry]: 本地合并后的字幕条目列表
        """
        logger.info("开始应用本地短字幕合并预处理")

        # 使用配置中的参数
        max_chars = self.config.local_merge_max_chars
        max_line_length = self.config.local_merge_max_line_length

        # 执行本地合并
        merged_entries = self.parser.merge_short_subtitles_locally(
            subtitle_entries,
            max_chars=max_chars,
            max_line_length=max_line_length
        )

        logger.info(f"本地短字幕合并预处理完成，从 {len(subtitle_entries)} 条减少到 {len(merged_entries)} 条")
        return merged_entries

    def _load_system_prompt(self, system_prompt_path: Optional[str] = None) -> str:
        """加载系统提示词"""
        prompt_path = system_prompt_path or self.config.system_prompt_path

        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"系统提示词文件不存在: {prompt_path}")

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read().strip()

            logger.debug(f"成功加载系统提示词: {prompt_path}")
            return system_prompt

        except Exception as e:
            logger.error(f"读取系统提示词文件失败: {e}")
            raise

  
    async def _single_correct_with_retry(self, subtitle_text: str, system_prompt: str, max_retries: int = 2) -> str:
        """带重试机制的单次校正处理"""
        logger.debug("执行带重试的单次字幕校正")

        for attempt in range(max_retries + 1):
            try:
                response = await self.ai_provider.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": subtitle_text}
                    ],
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )

                corrected_text = response.strip()
                logger.debug(f"单次校正完成，尝试次数: {attempt + 1}")
                return corrected_text

            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"单次校正最终失败，已重试 {max_retries} 次: {e}")
                    raise

                # 如果是400错误，尝试分批处理
                if "400" in str(e) or "Bad Request" in str(e):
                    logger.warning(f"检测到400错误，尝试分批处理 (尝试 {attempt + 1}/{max_retries + 1})")
                    try:
                        # 计算更小的批次大小
                        should_batch, smaller_batch_size, _ = should_batch_subtitle(subtitle_text, 1000)
                        if should_batch:
                            logger.info(f"自动切换到分批处理，批次大小: {smaller_batch_size}")
                            return await self._batch_correct(subtitle_text, system_prompt, smaller_batch_size)
                    except Exception as retry_e:
                        logger.warning(f"重试分批处理也失败: {retry_e}")

                # 其他类型的错误，直接重试
                logger.warning(f"单次校正失败，准备重试 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                await asyncio.sleep(1)  # 短暂等待后重试

    async def _single_correct(self, subtitle_text: str, system_prompt: str) -> str:
        """单次校正处理（保持向后兼容）"""
        return await self._single_correct_with_retry(subtitle_text, system_prompt)

    async def _batch_correct_entries(self, subtitle_entries: List[SubtitleEntry], system_prompt: str, recommended_batch_size: int = None) -> List[SubtitleEntry]:
        """
        基于字幕条目的分批校正处理入口方法

        Args:
            subtitle_entries: 字幕条目列表
            system_prompt: 系统提示词
            recommended_batch_size: 推荐的批次大小

        Returns:
            List[SubtitleEntry]: 校正后的字幕条目列表
        """
        logger.debug(f"开始基于字幕条目的分批校正，共 {len(subtitle_entries)} 条字幕")

        # 调用内部分批处理方法
        corrected_text = await self._batch_correct(subtitle_entries, system_prompt, recommended_batch_size)

        # 解析校正结果
        corrected_entries = self.parser.parse_text(corrected_text)

        logger.debug(f"基于字幕条目的分批校正完成，结果 {len(corrected_entries)} 条字幕")
        return corrected_entries

    async def _batch_correct(self, subtitle_entries: List[SubtitleEntry], system_prompt: str, recommended_batch_size: int = None) -> str:
        """基于字幕条目的分批校正处理"""
        logger.debug("执行基于字幕条目的分批字幕校正")

        # 使用推荐的批次大小，如果没有则使用默认策略
        if recommended_batch_size:
            max_batch_size = recommended_batch_size
            logger.debug(f"使用推荐的批次大小: {max_batch_size} 字符")
        else:
            max_batch_size = self.config.max_subtitle_length // 2  # 为AI响应留出空间
            logger.debug(f"使用默认批次大小: {max_batch_size} 字符")

        # 智能分批：基于字幕条目而非文本
        entry_batches = self._split_entries_batch(subtitle_entries, max_batch_size)
        logger.info(f"智能分批处理: 总共 {len(entry_batches)} 个批次")

        corrected_batches = []

        for i, batch_entries in enumerate(entry_batches):
            try:
                logger.debug(f"正在处理第 {i+1}/{len(entry_batches)} 批，包含 {len(batch_entries)} 条字幕")

                # 验证批次完整性
                self._validate_batch_integrity(batch_entries, i+1)

                # 将字幕条目转换为文本
                batch_text = self.parser.entries_to_text(batch_entries)
                logger.debug(f"批次 {i+1} 文本长度: {len(batch_text)} 字符")

                response = await self.ai_provider.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": batch_text}
                    ],
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )

                # 解析校正结果
                corrected_batch_text = response.strip()
                corrected_batch_entries = self.parser.parse_text(corrected_batch_text)

                # 验证校正结果的完整性
                if len(corrected_batch_entries) == 0:
                    logger.warning(f"第 {i+1} 批校正结果为空，使用原始字幕")
                    corrected_batch_entries = batch_entries
                else:
                    # 验证校正后字幕的完整性
                    if self._validate_corrected_batch(batch_entries, corrected_batch_entries, i+1):
                        logger.debug(f"第 {i+1} 批校正结果验证通过")
                    else:
                        logger.warning(f"第 {i+1} 批校正结果验证失败，使用原始字幕")
                        corrected_batch_entries = batch_entries

                corrected_batches.append(corrected_batch_entries)

                # 添加延迟避免API频率限制
                if i < len(entry_batches) - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"第 {i+1} 批校正失败: {e}")
                # 如果某批失败，使用原始字幕条目
                corrected_batches.append(batch_entries)

        # 合并所有批次的校正结果
        all_corrected_entries = []
        for batch_entries in corrected_batches:
            all_corrected_entries.extend(batch_entries)

        # 转换为文本格式
        corrected_text = self.parser.entries_to_text(all_corrected_entries)
        logger.debug(f"分批校正完成，总共处理 {len(all_corrected_entries)} 条字幕")
        return corrected_text

    def _split_entries_batch(self, entries: List[SubtitleEntry], max_size: int) -> List[List[SubtitleEntry]]:
        """
        基于字幕条目的智能分批算法

        确保每个批次包含完整的字幕条目，不会破坏SRT格式的完整性。

        Args:
            entries: 字幕条目列表
            max_size: 每批次的最大字符数

        Returns:
            List[List[SubtitleEntry]]: 分批后的字幕条目列表
        """
        if not entries:
            return []

        # 如果总字符数小于最大限制，直接返回单个批次
        total_text = self.parser.entries_to_text(entries)
        if len(total_text) <= max_size:
            return [entries]

        logger.debug(f"开始智能分批，总字幕条目: {len(entries)}，最大批次大小: {max_size} 字符")

        batches = []
        current_batch = []
        current_batch_size = 0

        # 预估每个字幕条目的字符数（包括格式）
        for entry in entries:
            # 计算单个字幕条目的字符数（包括序号、时间戳、文本和分隔符）
            entry_text = str(entry)
            entry_size = len(entry_text) + 2  # +2 for the double newline between entries

            # 如果当前批次为空，直接添加
            if not current_batch:
                current_batch.append(entry)
                current_batch_size = entry_size
                logger.debug(f"开始新批次，添加字幕条目 {entry.index}，大小: {entry_size} 字符")
                continue

            # 检查添加当前条目是否会超过最大限制
            if current_batch_size + entry_size <= max_size:
                current_batch.append(entry)
                current_batch_size += entry_size
                logger.debug(f"批次中添加字幕条目 {entry.index}，当前批次大小: {current_batch_size} 字符")
            else:
                # 保存当前批次，开始新批次
                batches.append(current_batch)
                logger.debug(f"完成批次，包含 {len(current_batch)} 条字幕，总大小: {current_batch_size} 字符")

                current_batch = [entry]
                current_batch_size = entry_size
                logger.debug(f"开始新批次，添加字幕条目 {entry.index}，大小: {entry_size} 字符")

        # 添加最后一个批次
        if current_batch:
            batches.append(current_batch)
            logger.debug(f"完成最后批次，包含 {len(current_batch)} 条字幕，总大小: {current_batch_size} 字符")

        # 验证分批结果
        total_entries = sum(len(batch) for batch in batches)
        if total_entries != len(entries):
            logger.error(f"分批验证失败：原始条目数 {len(entries)} != 分批后条目数 {total_entries}")
            raise ValueError("分批处理导致字幕条目丢失")

        logger.info(f"智能分批完成: {len(batches)} 个批次")
        for i, batch in enumerate(batches):
            batch_text_size = len(self.parser.entries_to_text(batch))
            logger.info(f"批次 {i+1}: {len(batch)} 条字幕，约 {batch_text_size} 字符")

        return batches

    def _split_text_blocks(self, text: str, max_size: int) -> List[str]:
        """将文本分割为适合处理的块（保留用于向后兼容）"""
        if len(text) <= max_size:
            return [text]

        blocks = []
        current_block = ""

        lines = text.split('\n')
        for line in lines:
            # 如果添加这一行会超过最大大小，且当前块不为空，则保存当前块
            if len(current_block) + len(line) + 1 > max_size and current_block:
                blocks.append(current_block)
                current_block = line
            else:
                if current_block:
                    current_block += '\n' + line
                else:
                    current_block = line

        # 添加最后一个块
        if current_block:
            blocks.append(current_block)

        return blocks

    def _validate_batch_integrity(self, batch_entries: List[SubtitleEntry], batch_num: int) -> bool:
        """
        验证批次中字幕条目的完整性

        Args:
            batch_entries: 批次中的字幕条目
            batch_num: 批次编号

        Returns:
            bool: 验证是否通过
        """
        if not batch_entries:
            logger.error(f"批次 {batch_num} 为空")
            return False

        # 检查序号连续性
        indices = [entry.index for entry in batch_entries]
        if indices != sorted(indices):
            logger.error(f"批次 {batch_num} 中序号不连续: {indices}")
            return False

        # 检查时间戳连续性
        for i in range(len(batch_entries) - 1):
            current_entry = batch_entries[i]
            next_entry = batch_entries[i + 1]

            # 检查时间戳是否合理
            if current_entry.start_time >= current_entry.end_time:
                logger.error(f"批次 {batch_num} 中条目 {current_entry.index} 时间戳无效")
                return False

            # 检查时间重叠
            if current_entry.end_time > next_entry.start_time:
                logger.warning(f"批次 {batch_num} 中条目 {current_entry.index} 与 {next_entry.index} 时间重叠")

        logger.debug(f"批次 {batch_num} 完整性验证通过: {len(batch_entries)} 条字幕")
        return True

    def _validate_corrected_batch(self, original_entries: List[SubtitleEntry],
                                corrected_entries: List[SubtitleEntry],
                                batch_num: int) -> bool:
        """
        验证校正后批次的完整性

        Args:
            original_entries: 原始字幕条目
            corrected_entries: 校正后字幕条目
            batch_num: 批次编号

        Returns:
            bool: 验证是否通过
        """
        # 基本检查
        if not corrected_entries:
            logger.error(f"批次 {batch_num} 校正结果为空")
            return False

        # 检查条目数量的合理性（AI可能会合并或拆分字幕条目）
        original_count = len(original_entries)
        corrected_count = len(corrected_entries)

        # 允许AI合并条目，但不允许条目数量差异过大
        if corrected_count < original_count * 0.3 or corrected_count > original_count * 3:
            logger.warning(f"批次 {batch_num} 条目数量变化异常: {original_count} -> {corrected_count}")
            return False

        # 检查时间戳范围的合理性
        original_start_time = original_entries[0].start_time
        original_end_time = original_entries[-1].end_time
        corrected_start_time = corrected_entries[0].start_time
        corrected_end_time = corrected_entries[-1].end_time

        # 时间偏移不应超过5秒
        if abs(corrected_start_time - original_start_time) > 5.0 or abs(corrected_end_time - original_end_time) > 5.0:
            logger.warning(f"批次 {batch_num} 时间偏移过大: 原始[{original_start_time:.1f}, {original_end_time:.1f}] -> 校正[{corrected_start_time:.1f}, {corrected_end_time:.1f}]")
            return False

        logger.debug(f"批次 {batch_num} 校正结果验证通过: {original_count} -> {corrected_count} 条字幕")
        return True

    def _preserve_timestamps(self, original_entries: List[SubtitleEntry],
                           corrected_entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        保持原始时间戳

        将校正后的文本与原始时间戳进行匹配，保持时间轴的准确性。
        """
        if len(corrected_entries) != len(original_entries):
            logger.warning(f"校正前后字幕条目数量不匹配: {len(original_entries)} -> {len(corrected_entries)}")

            # 如果数量不匹配，尝试智能对齐
            return self._align_timestamps(original_entries, corrected_entries)

        # 数量匹配，直接对应
        for i, corrected_entry in enumerate(corrected_entries):
            if i < len(original_entries):
                corrected_entry.start_time = original_entries[i].start_time
                corrected_entry.end_time = original_entries[i].end_time

        return corrected_entries

    def _align_timestamps(self, original_entries: List[SubtitleEntry],
                         corrected_entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        智能对齐时间戳

        当校正前后字幕条目数量不匹配时，尝试智能分配时间戳。
        优先保留AI合并后的时间戳格式，只在必要时进行调整。
        """
        logger.info("执行智能时间戳对齐")

        if len(corrected_entries) == 0:
            return original_entries

        # 检查校正后的字幕是否已经包含有效的时间戳
        has_valid_timestamps = all(
            entry.start_time >= 0 and entry.end_time > entry.start_time
            for entry in corrected_entries
        )

        if has_valid_timestamps:
            total_corrected_duration = corrected_entries[-1].end_time - corrected_entries[0].start_time
            total_original_duration = original_entries[-1].end_time - original_entries[0].start_time

            # 如果时间范围合理，保持AI的时间戳
            if abs(total_corrected_duration - total_original_duration) < 60:  # 允许1分钟误差
                logger.info("AI生成的时间戳合理，保持不变")
                return self._reindex_entries(corrected_entries)
            else:
                logger.info(f"时间戳范围差异较大 (校正: {total_corrected_duration:.1f}s, 原始: {total_original_duration:.1f}s)，进行调整")

        # 智能时间戳分配策略
        return self._smart_timestamp_allocation(original_entries, corrected_entries)

    def _smart_timestamp_allocation(self, original_entries: List[SubtitleEntry],
                                   corrected_entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        智能分配时间戳，考虑文本长度和原始节奏
        """
        if not original_entries or not corrected_entries:
            return corrected_entries

        total_original_duration = original_entries[-1].end_time - original_entries[0].start_time
        if total_original_duration <= 0:
            return corrected_entries

        # 计算原始字幕的平均文本长度节奏
        original_char_per_second = sum(len(entry.text) for entry in original_entries) / total_original_duration

        # 计算每个校正条目的目标时长（基于文本长度）
        for i, entry in enumerate(corrected_entries):
            text_length = len(entry.text)
            target_duration = text_length / max(original_char_per_second, 1)

            # 限制最小和最大时长
            min_duration = 1.0  # 最小1秒
            max_duration = 10.0  # 最大10秒
            target_duration = max(min_duration, min(target_duration, max_duration))

            if i == 0:
                entry.start_time = original_entries[0].start_time
            else:
                entry.start_time = corrected_entries[i-1].end_time

            entry.end_time = entry.start_time + target_duration

        # 调整最后一条，确保总时长接近原始时长
        if len(corrected_entries) > 0:
            current_total_duration = corrected_entries[-1].end_time - corrected_entries[0].start_time
            if current_total_duration > total_original_duration * 1.2:  # 如果超过20%
                scale_factor = total_original_duration / current_total_duration
                for entry in corrected_entries:
                    entry.start_time *= scale_factor
                    entry.end_time *= scale_factor

        return self._reindex_entries(corrected_entries)

    def _reindex_entries(self, entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        重新编号字幕条目
        """
        for i, entry in enumerate(entries):
            entry.index = i + 1
        return entries

    def get_supported_providers(self) -> List[str]:
        """获取支持的AI服务提供商列表"""
        return AIProviderFactory.get_supported_providers()

    def get_provider_info(self, provider: str) -> Dict[str, Any]:
        """获取指定AI服务提供商的信息"""
        return AIProviderFactory.get_provider_info(provider)


# 便捷函数
async def correct_subtitle(
    subtitle_path: str,
    provider: Optional[str] = None,
    output_path: Optional[str] = None,
    system_prompt_path: Optional[str] = None
) -> CorrectionResult:
    """
    便捷的字幕校正函数

    Args:
        subtitle_path: 字幕文件路径
        provider: AI服务提供商
        output_path: 输出路径
        system_prompt_path: 系统提示词路径

    Returns:
        CorrectionResult: 校正结果
    """
    corrector = SubtitleCorrector(provider=provider)
    return await corrector.correct_subtitle_file(
        subtitle_path=subtitle_path,
        output_path=output_path,
        system_prompt_path=system_prompt_path
    )