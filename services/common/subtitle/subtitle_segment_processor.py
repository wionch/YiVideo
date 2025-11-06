"""
字幕片段处理器

应用AI优化指令到字幕片段，支持MOVE、UPDATE、DELETE、PUNCTUATE四种指令。

作者: Claude Code
日期: 2025-11-06
版本: v2.0.0
"""

import logging
from typing import List, Dict, Any, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)


class SubtitleSegmentProcessor:
    """字幕片段处理器

    应用AI优化指令到字幕内容，生成优化后的字幕列表。
    支持增强的指令执行引擎，包含验证、统计和冲突解决功能。
    """

    def __init__(self, use_enhanced_executor: bool = True):
        """初始化处理器

        Args:
            use_enhanced_executor: 是否使用增强的指令执行器
        """
        self.use_enhanced_executor = use_enhanced_executor

        if use_enhanced_executor:
            from .command_executor import CommandExecutor
            from .command_statistics import CommandStatisticsCollector, CommandValidator
            self.command_executor = CommandExecutor()
            self.statistics_collector = CommandStatisticsCollector()
            self.validator = CommandValidator()
            logger.info("使用增强的指令执行引擎")
        else:
            self.command_executor = None
            self.statistics_collector = None
            self.validator = None
            logger.info("使用基础指令执行器")

    def process_subtitles(self,
                         subtitles: List[Dict[str, Any]],
                         commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理字幕应用优化指令

        Args:
            subtitles: 原始字幕列表
            commands: 优化指令列表

        Returns:
            优化后的字幕列表

        Raises:
            ValueError: 指令验证失败
        """
        logger.info(f"开始处理字幕: {len(subtitles)}条字幕，{len(commands)}个指令")

        if not subtitles:
            logger.warning("字幕列表为空")
            return []

        if not commands:
            logger.info("没有指令需要执行")
            return subtitles.copy()

        # 如果使用增强执行器
        if self.command_executor:
            return self._process_with_enhanced_executor(subtitles, commands)
        else:
            return self._process_with_basic_executor(subtitles, commands)

    def _process_with_enhanced_executor(self,
                                       subtitles: List[Dict[str, Any]],
                                       commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用增强执行器处理

        Args:
            subtitles: 原始字幕列表
            commands: 优化指令列表

        Returns:
            优化后的字幕列表
        """
        import time

        # 1. 验证指令
        logger.info("[US3] 开始指令验证")
        self.statistics_collector.start_tracking()

        validation_results = self.validator.validate_command_list(commands, subtitles)
        invalid_count = sum(1 for r in validation_results if not r.is_valid)

        if invalid_count > 0:
            error_messages = []
            for result in validation_results:
                if not result.is_valid:
                    error_messages.append(f"指令{result.command_index+1}: {', '.join(result.errors)}")

            error_msg = f"有 {invalid_count} 个指令验证失败"
            logger.error(f"[US3] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[US3] 指令验证通过 - {len(validation_results)}个指令")

        # 2. 执行指令
        start_time = time.time()
        try:
            processed_subtitles = self.command_executor.execute_commands(subtitles, commands)
            execution_time = time.time() - start_time

            # 3. 记录统计
            self.statistics_collector.stop_tracking()
            stats = self.statistics_collector.get_statistics()

            # 记录到日志
            self.statistics_collector.log_summary()

            logger.info(f"[US3] 指令执行完成 - 成功率: {self.statistics_collector.get_success_rate():.2%}, "
                       f"应用率: {self.statistics_collector.get_application_rate():.2%}")

            return processed_subtitles

        except Exception as e:
            self.statistics_collector.stop_tracking()
            logger.error(f"[US3] 指令执行失败: {e}", exc_info=True)
            raise

    def _process_with_basic_executor(self,
                                    subtitles: List[Dict[str, Any]],
                                    commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用基础执行器处理（向后兼容）

        Args:
            subtitles: 原始字幕列表
            commands: 优化指令列表

        Returns:
            优化后的字幕列表
        """
        # 创建字幕的深拷贝，避免修改原始数据
        processed_subtitles = deepcopy(subtitles)

        # 按指令类型分组应用
        self._apply_move_commands(processed_subtitles, commands)
        self._apply_update_commands(processed_subtitles, commands)
        self._apply_delete_commands(processed_subtitles, commands)
        self._apply_punctuate_commands(processed_subtitles, commands)

        # 统计应用结果
        stats = self._get_command_stats(commands)
        logger.info(f"[US3-基础] 指令应用完成: {stats}")

        return processed_subtitles

    def _apply_move_commands(self,
                           subtitles: List[Dict[str, Any]],
                           commands: List[Dict[str, Any]]) -> None:
        """应用MOVE指令

        Args:
            subtitles: 字幕列表（原地修改）
            commands: 指令列表
        """
        move_commands = [cmd for cmd in commands if cmd.get('command') == 'MOVE']

        for cmd in move_commands:
            from_id = cmd.get('from_id')
            to_id = cmd.get('to_id')
            text = cmd.get('text', '')

            if not text:
                logger.warning(f"MOVE指令缺少text字段: {cmd}")
                continue

            # 查找源和目标片段
            from_segment = self._find_segment_by_id(subtitles, from_id)
            to_segment = self._find_segment_by_id(subtitles, to_id)

            if not from_segment or not to_segment:
                logger.warning(f"MOVE指令无法找到对应片段: {cmd}")
                continue

            # 从源片段移除文本
            original_text = from_segment.get('text', '')
            if text in original_text:
                new_from_text = original_text.replace(text, '', 1)
                from_segment['text'] = new_from_text
                logger.debug(f"从片段{from_id}移除文本: '{text}'")

            # 将文本添加到目标片段末尾
            original_to_text = to_segment.get('text', '')
            to_segment['text'] = original_to_text + text
            logger.debug(f"向片段{to_id}添加文本: '{text}'")

    def _apply_update_commands(self,
                             subtitles: List[Dict[str, Any]],
                             commands: List[Dict[str, Any]]) -> None:
        """应用UPDATE指令

        Args:
            subtitles: 字幕列表（原地修改）
            commands: 指令列表
        """
        update_commands = [cmd for cmd in commands if cmd.get('command') == 'UPDATE']

        for cmd in update_commands:
            segment_id = cmd.get('id')
            changes = cmd.get('changes', {})

            if not changes:
                logger.warning(f"UPDATE指令缺少changes字段: {cmd}")
                continue

            # 查找目标片段
            segment = self._find_segment_by_id(subtitles, segment_id)
            if not segment:
                logger.warning(f"UPDATE指令无法找到对应片段: {cmd}")
                continue

            # 应用文本替换
            original_text = segment.get('text', '')
            updated_text = original_text

            for old_text, new_text in changes.items():
                if old_text in updated_text:
                    updated_text = updated_text.replace(old_text, new_text, 1)
                    logger.debug(f"片段{segment_id}: '{old_text}' -> '{new_text}'")

            if updated_text != original_text:
                segment['text'] = updated_text

    def _apply_delete_commands(self,
                             subtitles: List[Dict[str, Any]],
                             commands: List[Dict[str, Any]]) -> None:
        """应用DELETE指令

        Args:
            subtitles: 字幕列表（原地修改）
            commands: 指令列表
        """
        delete_commands = [cmd for cmd in commands if cmd.get('command') == 'DELETE']

        for cmd in delete_commands:
            segment_id = cmd.get('id')
            words = cmd.get('words', [])

            if not words:
                logger.warning(f"DELETE指令缺少words字段: {cmd}")
                continue

            # 查找目标片段
            segment = self._find_segment_by_id(subtitles, segment_id)
            if not segment:
                logger.warning(f"DELETE指令无法找到对应片段: {cmd}")
                continue

            # 删除指定词汇
            original_text = segment.get('text', '')
            updated_text = original_text

            for word in words:
                if word in updated_text:
                    updated_text = updated_text.replace(word, '', 1)
                    logger.debug(f"从片段{segment_id}删除词: '{word}'")

            if updated_text != original_text:
                segment['text'] = updated_text

    def _apply_punctuate_commands(self,
                                subtitles: List[Dict[str, Any]],
                                commands: List[Dict[str, Any]]) -> None:
        """应用PUNCTUATE指令

        Args:
            subtitles: 字幕列表（原地修改）
            commands: 指令列表
        """
        punctuate_commands = [cmd for cmd in commands if cmd.get('command') == 'PUNCTUATE']

        for cmd in punctuate_commands:
            updates = cmd.get('updates', {})

            if not updates:
                logger.warning(f"PUNCTUATE指令缺少updates字段: {cmd}")
                continue

            # 应用标点更新
            for segment_id_str, punctuation in updates.items():
                try:
                    segment_id = int(segment_id_str)
                except ValueError:
                    logger.warning(f"PUNCTUATE指令ID格式无效: {segment_id_str}")
                    continue

                segment = self._find_segment_by_id(subtitles, segment_id)
                if not segment:
                    logger.warning(f"PUNCTUATE指令无法找到对应片段: {segment_id}")
                    continue

                # 添加标点到片段末尾
                original_text = segment.get('text', '')
                segment['text'] = original_text + punctuation
                logger.debug(f"向片段{segment_id}添加标点: '{punctuation}'")

    def _find_segment_by_id(self,
                          subtitles: List[Dict[str, Any]],
                          segment_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查找字幕片段

        Args:
            subtitles: 字幕列表
            segment_id: 片段ID

        Returns:
            找到的片段或None
        """
        for subtitle in subtitles:
            if subtitle.get('id') == segment_id:
                return subtitle
        return None

    def _get_command_stats(self, commands: List[Dict[str, Any]]) -> Dict[str, int]:
        """获取指令应用统计

        Args:
            commands: 指令列表

        Returns:
            统计信息
        """
        stats = {
            'total': len(commands),
            'move': 0,
            'update': 0,
            'delete': 0,
            'punctuate': 0
        }

        for cmd in commands:
            cmd_type = cmd.get('command', '').lower()
            if cmd_type in stats:
                stats[cmd_type] += 1

        return stats

    def get_execution_report(self) -> Optional[Dict[str, Any]]:
        """获取执行报告

        Returns:
            执行报告或None
        """
        if self.statistics_collector:
            return self.statistics_collector.export_report()
        return None