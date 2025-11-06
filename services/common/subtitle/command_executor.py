"""
优化指令执行引擎

精确执行AI返回的MOVE、UPDATE、DELETE、PUNCTUATE指令，支持指令冲突检测和解决。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import logging
from typing import List, Dict, Any, Set, Optional
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandExecutionResult:
    """指令执行结果"""
    command_id: int
    command_type: str
    success: bool
    applied: bool
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class CommandExecutor:
    """优化指令执行引擎

    精确执行AI优化指令，支持：
    1. MOVE指令 - 移动文本片段
    2. UPDATE指令 - 修正错别字
    3. DELETE指令 - 删除词汇
    4. PUNCTUATE指令 - 添加标点
    5. 指令冲突检测和解决

    性能优化：
    - 片段ID查找使用O(1)缓存，避免O(n)线性查找
    - 按优先级排序执行指令，减少冲突概率
    - 批量操作优化，减少重复计算
    """

    def __init__(self):
        """初始化指令执行器"""
        self.execution_history: List[CommandExecutionResult] = []

        # 指令冲突检测
        self.segment_modifications: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.moved_texts: Dict[int, str] = {}  # 记录已移动的文本

        # 性能优化：片段ID查找缓存 {subtitles: {segment_id: segment}}
        self._segment_cache: Dict[int, Dict[int, Dict[str, Any]]] = {}

        logger.info("指令执行引擎初始化完成")

    def execute_commands(self,
                        subtitles: List[Dict[str, Any]],
                        commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行所有优化指令

        Args:
            subtitles: 原始字幕列表
            commands: 优化指令列表

        Returns:
            优化后的字幕列表

        Raises:
            ValueError: 指令验证失败
        """
        logger.info(f"开始执行 {len(commands)} 个优化指令")

        if not subtitles:
            logger.warning("字幕列表为空")
            return []

        if not commands:
            logger.info("没有指令需要执行")
            return subtitles.copy()

        # 1. 验证所有指令
        validation_errors = self._validate_all_commands(subtitles, commands)
        if validation_errors:
            error_msg = f"指令验证失败: {validation_errors}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 2. 检测和处理指令冲突
        conflicts = self._detect_conflicts(commands)
        if conflicts:
            logger.warning(f"检测到指令冲突: {conflicts}")
            commands = self._resolve_conflicts(commands, conflicts)

        # 3. 按优先级排序执行
        sorted_commands = self._sort_commands_by_priority(commands)
        logger.info(f"按优先级排序后共 {len(sorted_commands)} 个指令")

        # 4. 创建字幕深拷贝
        processed_subtitles = self._create_deep_copy(subtitles)

        # 5. 构建片段ID查找缓存（性能优化）
        self._build_segment_cache(processed_subtitles)

        # 5. 逐个执行指令
        for i, command in enumerate(sorted_commands):
            try:
                result = self._execute_single_command(
                    processed_subtitles, command, command_index=i
                )
                self.execution_history.append(result)

                if not result.success:
                    logger.warning(f"指令 {i+1} 执行失败: {result.error}")
                elif result.applied:
                    logger.debug(f"指令 {i+1} 执行成功: {command['command']}")

            except Exception as e:
                logger.error(f"指令 {i+1} 执行异常: {e}", exc_info=True)
                self.execution_history.append(CommandExecutionResult(
                    command_id=i+1,
                    command_type=command.get('command', 'UNKNOWN'),
                    success=False,
                    applied=False,
                    error=str(e)
                ))

        # 6. 统计执行结果
        self._log_execution_summary()

        logger.info(f"指令执行完成 - 成功率: {self._get_success_rate():.2%}")
        return processed_subtitles

    def _validate_all_commands(self,
                              subtitles: List[Dict[str, Any]],
                              commands: List[Dict[str, Any]]) -> List[str]:
        """验证所有指令

        Args:
            subtitles: 字幕列表
            commands: 指令列表

        Returns:
            错误信息列表
        """
        errors = []

        # 验证字幕ID存在性
        segment_ids = {sub['id'] for sub in subtitles}
        for i, cmd in enumerate(commands):
            cmd_type = cmd.get('command', '').upper()
            cmd_id = i + 1

            if cmd_type == 'MOVE':
                from_id = cmd.get('from_id')
                to_id = cmd.get('to_id')
                if from_id not in segment_ids:
                    errors.append(f"指令{cmd_id}: from_id {from_id} 不存在")
                if to_id not in segment_ids:
                    errors.append(f"指令{cmd_id}: to_id {to_id} 不存在")

            elif cmd_type == 'UPDATE':
                segment_id = cmd.get('id')
                if segment_id not in segment_ids:
                    errors.append(f"指令{cmd_id}: segment_id {segment_id} 不存在")

            elif cmd_type == 'DELETE':
                segment_id = cmd.get('id')
                if segment_id not in segment_ids:
                    errors.append(f"指令{cmd_id}: segment_id {segment_id} 不存在")

            elif cmd_type == 'PUNCTUATE':
                updates = cmd.get('updates', {})
                for segment_id_str in updates.keys():
                    try:
                        segment_id = int(segment_id_str)
                        if segment_id not in segment_ids:
                            errors.append(f"指令{cmd_id}: segment_id {segment_id} 不存在")
                    except ValueError:
                        errors.append(f"指令{cmd_id}: segment_id '{segment_id_str}' 格式无效")

        return errors

    def _detect_conflicts(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检测指令冲突

        Args:
            commands: 指令列表

        Returns:
            冲突信息列表
        """
        conflicts = []

        # 按片段ID分组指令
        segment_commands = defaultdict(list)
        for i, cmd in enumerate(commands):
            segment_id = self._get_command_segment_id(cmd)
            if segment_id is not None:
                segment_commands[segment_id].append((i, cmd))

        # 检测同一片段的多次修改
        for segment_id, cmds in segment_commands.items():
            if len(cmds) > 1:
                conflict_types = set(cmd[1].get('command') for cmd in cmds)
                if len(conflict_types) > 1 or len(cmds) > 2:
                    conflicts.append({
                        'segment_id': segment_id,
                        'type': 'multiple_modifications',
                        'commands': [cmd[0] for cmd in cmds],
                        'description': f'片段{segment_id}有{len(cmds)}个指令'
                    })

        # 检测MOVE指令冲突
        move_commands = [(i, cmd) for i, cmd in enumerate(commands) if cmd.get('command') == 'MOVE']
        for i, move_cmd in move_commands:
            from_id = move_cmd.get('from_id')
            text = move_cmd.get('text', '')

            # 检查是否有其他指令修改源片段
            for j, other_cmd in enumerate(commands):
                if i == j:
                    continue
                other_id = self._get_command_segment_id(other_cmd)
                if other_id == from_id and other_cmd.get('command') != 'MOVE':
                    conflicts.append({
                        'type': 'move_source_modified',
                        'move_index': i,
                        'conflicting_index': j,
                        'description': f'MOVE指令{i+1}的源片段被指令{j+1}修改'
                    })

        return conflicts

    def _resolve_conflicts(self,
                          commands: List[Dict[str, Any]],
                          conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解决指令冲突

        Args:
            commands: 原始指令列表
            conflicts: 冲突信息列表

        Returns:
            解决冲突后的指令列表
        """
        resolved_commands = commands.copy()

        # 简单的冲突解决策略：保留UPDATE和DELETE，移除冲突的MOVE
        for conflict in conflicts:
            if conflict['type'] == 'move_source_modified':
                move_index = conflict['move_index']
                conflicting_index = conflict['conflicting_index']

                # 移除冲突的MOVE指令
                if move_index < len(resolved_commands):
                    logger.info(f"解决冲突: 移除MOVE指令{move_index+1}")
                    resolved_commands.pop(move_index)

        return resolved_commands

    def _sort_commands_by_priority(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按优先级排序指令

        Args:
            commands: 指令列表

        Returns:
            排序后的指令列表
        """
        # 优先级：DELETE > UPDATE > MOVE > PUNCTUATE
        priority_map = {
            'DELETE': 1,
            'UPDATE': 2,
            'MOVE': 3,
            'PUNCTUATE': 4
        }

        return sorted(commands, key=lambda cmd: priority_map.get(cmd.get('command', ''), 99))

    def _execute_single_command(self,
                              subtitles: List[Dict[str, Any]],
                              command: Dict[str, Any],
                              command_index: int) -> CommandExecutionResult:
        """执行单个指令

        Args:
            subtitles: 字幕列表（原地修改）
            command: 指令
            command_index: 指令索引

        Returns:
            执行结果
        """
        cmd_type = command.get('command', '').upper()
        cmd_id = command_index + 1

        try:
            if cmd_type == 'MOVE':
                return self._execute_move(subtitles, command, cmd_id)
            elif cmd_type == 'UPDATE':
                return self._execute_update(subtitles, command, cmd_id)
            elif cmd_type == 'DELETE':
                return self._execute_delete(subtitles, command, cmd_id)
            elif cmd_type == 'PUNCTUATE':
                return self._execute_punctuate(subtitles, command, cmd_id)
            else:
                return CommandExecutionResult(
                    command_id=cmd_id,
                    command_type=cmd_type,
                    success=False,
                    applied=False,
                    error=f"未知指令类型: {cmd_type}"
                )

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"指令 {cmd_id}[{cmd_type}] 执行异常 [{error_type}]: {error_msg}", exc_info=True)
            return CommandExecutionResult(
                command_id=cmd_id,
                command_type=cmd_type,
                success=False,
                applied=False,
                error=f"[{error_type}] {error_msg}"
            )

    def _execute_move(self,
                     subtitles: List[Dict[str, Any]],
                     command: Dict[str, Any],
                     command_id: int) -> CommandExecutionResult:
        """执行MOVE指令"""
        from_id = command.get('from_id')
        to_id = command.get('to_id')
        text = command.get('text', '')

        from_segment = self._find_segment_by_id(subtitles, from_id)
        to_segment = self._find_segment_by_id(subtitles, to_id)

        if not from_segment or not to_segment:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='MOVE',
                success=False,
                applied=False,
                error="找不到对应片段"
            )

        original_from = from_segment['text']
        original_to = to_segment['text']

        # 执行移动
        if text in original_from:
            new_from = original_from.replace(text, '', 1)
            new_to = original_to + text

            from_segment['text'] = new_from
            to_segment['text'] = new_to

            return CommandExecutionResult(
                command_id=command_id,
                command_type='MOVE',
                success=True,
                applied=True,
                details={
                    'from_id': from_id,
                    'to_id': to_id,
                    'moved_text': text,
                    'from_before': original_from,
                    'from_after': new_from,
                    'to_before': original_to,
                    'to_after': new_to
                }
            )
        else:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='MOVE',
                success=True,
                applied=False,
                error=f"源片段中未找到文本: '{text}'"
            )

    def _execute_update(self,
                       subtitles: List[Dict[str, Any]],
                       command: Dict[str, Any],
                       command_id: int) -> CommandExecutionResult:
        """执行UPDATE指令"""
        segment_id = command.get('id')
        changes = command.get('changes', {})

        segment = self._find_segment_by_id(subtitles, segment_id)
        if not segment:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='UPDATE',
                success=False,
                applied=False,
                error="找不到对应片段"
            )

        original_text = segment['text']
        updated_text = original_text
        applied_changes = {}

        for old_text, new_text in changes.items():
            if old_text in updated_text:
                updated_text = updated_text.replace(old_text, new_text, 1)
                applied_changes[old_text] = new_text

        if applied_changes:
            segment['text'] = updated_text
            return CommandExecutionResult(
                command_id=command_id,
                command_type='UPDATE',
                success=True,
                applied=True,
                details={
                    'segment_id': segment_id,
                    'original': original_text,
                    'updated': updated_text,
                    'changes': applied_changes
                }
            )
        else:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='UPDATE',
                success=True,
                applied=False,
                error="没有应用任何更改"
            )

    def _execute_delete(self,
                       subtitles: List[Dict[str, Any]],
                       command: Dict[str, Any],
                       command_id: int) -> CommandExecutionResult:
        """执行DELETE指令"""
        segment_id = command.get('id')
        words = command.get('words', [])

        segment = self._find_segment_by_id(subtitles, segment_id)
        if not segment:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='DELETE',
                success=False,
                applied=False,
                error="找不到对应片段"
            )

        original_text = segment['text']
        updated_text = original_text
        deleted_words = []

        for word in words:
            if word in updated_text:
                updated_text = updated_text.replace(word, '', 1)
                deleted_words.append(word)

        if deleted_words:
            segment['text'] = updated_text
            return CommandExecutionResult(
                command_id=command_id,
                command_type='DELETE',
                success=True,
                applied=True,
                details={
                    'segment_id': segment_id,
                    'original': original_text,
                    'updated': updated_text,
                    'deleted_words': deleted_words
                }
            )
        else:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='DELETE',
                success=True,
                applied=False,
                error="没有删除任何词"
            )

    def _execute_punctuate(self,
                          subtitles: List[Dict[str, Any]],
                          command: Dict[str, Any],
                          command_id: int) -> CommandExecutionResult:
        """执行PUNCTUATE指令"""
        updates = command.get('updates', {})
        applied_updates = {}

        for segment_id_str, punctuation in updates.items():
            try:
                segment_id = int(segment_id_str)
            except ValueError:
                continue

            segment = self._find_segment_by_id(subtitles, segment_id)
            if segment:
                original_text = segment['text']
                new_text = original_text + punctuation

                segment['text'] = new_text
                applied_updates[segment_id] = {
                    'original': original_text,
                    'updated': new_text,
                    'punctuation': punctuation
                }

        if applied_updates:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='PUNCTUATE',
                success=True,
                applied=True,
                details={'updates': applied_updates}
            )
        else:
            return CommandExecutionResult(
                command_id=command_id,
                command_type='PUNCTUATE',
                success=True,
                applied=False,
                error="没有应用任何标点"
            )

    def _get_command_segment_id(self, command: Dict[str, Any]) -> Optional[int]:
        """获取指令关联的片段ID

        Args:
            command: 指令

        Returns:
            片段ID或None
        """
        cmd_type = command.get('command', '').upper()

        if cmd_type == 'MOVE':
            # MOVE关联两个片段
            return command.get('to_id')  # 优先返回目标片段

        elif cmd_type in ['UPDATE', 'DELETE']:
            return command.get('id')

        elif cmd_type == 'PUNCTUATE':
            # PUNCTUATE可能关联多个片段
            updates = command.get('updates', {})
            if updates:
                return int(list(updates.keys())[0])

        return None

    def _find_segment_by_id(self,
                          subtitles: List[Dict[str, Any]],
                          segment_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查找字幕片段"""
        for subtitle in subtitles:
            if subtitle.get('id') == segment_id:
                return subtitle
        return None

    def _create_deep_copy(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """创建字幕的深拷贝"""
        import copy
        return copy.deepcopy(subtitles)

    def _build_segment_cache(self, subtitles: List[Dict[str, Any]]) -> None:
        """构建片段ID查找缓存

        Args:
            subtitles: 字幕列表
        """
        # 使用字幕列表的ID作为缓存键
        cache_key = id(subtitles)
        self._segment_cache[cache_key] = {
            segment['id']: segment for segment in subtitles
        }
        logger.debug(f"构建片段缓存: {len(self._segment_cache[cache_key])}个片段")

    def _find_segment_by_id(self,
                          subtitles: List[Dict[str, Any]],
                          segment_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查找字幕片段（使用缓存优化）"""
        # 从缓存中查找
        cache_key = id(subtitles)
        cache = self._segment_cache.get(cache_key)
        if cache:
            return cache.get(segment_id)

        # 缓存未命中时的回退（不应该发生）
        for subtitle in subtitles:
            if subtitle.get('id') == segment_id:
                return subtitle
        return None

    def _get_success_rate(self) -> float:
        """获取指令执行成功率"""
        if not self.execution_history:
            return 0.0

        success_count = sum(1 for r in self.execution_history if r.success)
        return success_count / len(self.execution_history)

    def _log_execution_summary(self):
        """记录执行摘要"""
        if not self.execution_history:
            return

        # 按类型统计
        type_stats = defaultdict(lambda: {'total': 0, 'success': 0, 'applied': 0})
        for result in self.execution_history:
            stats = type_stats[result.command_type]
            stats['total'] += 1
            if result.success:
                stats['success'] += 1
            if result.applied:
                stats['applied'] += 1

        # 记录统计
        for cmd_type, stats in type_stats.items():
            logger.info(f"指令类型 {cmd_type} - 总数: {stats['total']}, "
                       f"成功: {stats['success']}, 应用: {stats['applied']}")

    def get_execution_report(self) -> Dict[str, Any]:
        """获取执行报告

        Returns:
            执行报告
        """
        if not self.execution_history:
            return {'total': 0}

        type_stats = defaultdict(lambda: {'total': 0, 'success': 0, 'applied': 0})
        for result in self.execution_history:
            stats = type_stats[result.command_type]
            stats['total'] += 1
            if result.success:
                stats['success'] += 1
            if result.applied:
                stats['applied'] += 1

        return {
            'total_commands': len(self.execution_history),
            'success_rate': self._get_success_rate(),
            'by_type': dict(type_stats),
            'errors': [
                {
                    'command_id': r.command_id,
                    'command_type': r.command_type,
                    'error': r.error
                }
                for r in self.execution_history if not r.success
            ]
        }