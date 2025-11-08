"""
指令执行统计和验证模块

提供指令执行统计、验证和质量保证功能。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


@dataclass
class CommandValidationResult:
    """指令验证结果"""
    is_valid: bool
    command_index: int
    command_type: str
    errors: List[str]
    warnings: List[str]
    details: Optional[Dict[str, Any]] = None


@dataclass
class CommandExecutionStatistics:
    """指令执行统计"""
    total_commands: int
    successful_commands: int
    failed_commands: int
    applied_commands: int
    skipped_commands: int
    by_type: Dict[str, Dict[str, int]]
    execution_time: float
    error_details: List[Dict[str, Any]]


class CommandValidator:
    """指令验证器

    验证AI指令的格式、参数和逻辑正确性。
    """

    def __init__(self):
        """初始化指令验证器"""
        pass

    def validate_command_list(self,
                            commands: List[Dict[str, Any]],
                            subtitles: List[Dict[str, Any]]) -> List[CommandValidationResult]:
        """验证指令列表

        Args:
            commands: 指令列表
            subtitles: 字幕列表

        Returns:
            验证结果列表
        """
        results = []

        # 验证必要字段
        for i, command in enumerate(commands):
            result = self._validate_single_command(command, i, subtitles)
            results.append(result)

        # 验证跨指令逻辑
        logic_errors = self._validate_cross_command_logic(commands, subtitles)
        for error in logic_errors:
            if error['index'] < len(results):
                results[error['index']].errors.append(error['message'])

        return results

    def _validate_single_command(self,
                                command: Dict[str, Any],
                                index: int,
                                subtitles: List[Dict[str, Any]]) -> CommandValidationResult:
        """验证单个指令

        Args:
            command: 指令
            index: 指令索引
            subtitles: 字幕列表

        Returns:
            验证结果
        """
        errors = []
        warnings = []
        command_type = command.get('command', '').upper()

        # 检查必要字段
        if 'command' not in command:
            return CommandValidationResult(
                is_valid=False,
                command_index=index,
                command_type='UNKNOWN',
                errors=['缺少command字段'],
                warnings=[]
            )

        # 验证各类型指令
        if command_type == 'MOVE':
            errors.extend(self._validate_move_command(command, subtitles))
        elif command_type == 'UPDATE':
            errors.extend(self._validate_update_command(command, subtitles))
        elif command_type == 'DELETE':
            errors.extend(self._validate_delete_command(command, subtitles))
        elif command_type == 'PUNCTUATE':
            errors.extend(self._validate_punctuate_command(command, subtitles))
        else:
            errors.append(f"未知指令类型: {command_type}")

        return CommandValidationResult(
            is_valid=len(errors) == 0,
            command_index=index,
            command_type=command_type,
            errors=errors,
            warnings=warnings
        )

    def _validate_move_command(self, command: Dict[str, Any], subtitles: List[Dict[str, Any]]) -> List[str]:
        """验证MOVE指令"""
        errors = []

        if 'from_id' not in command:
            errors.append("MOVE指令缺少from_id字段")
        if 'to_id' not in command:
            errors.append("MOVE指令缺少to_id字段")
        if 'text' not in command:
            errors.append("MOVE指令缺少text字段")

        if errors:
            return errors

        # 验证片段存在性
        segment_ids = {sub['id'] for sub in subtitles}
        from_id = command['from_id']
        to_id = command['to_id']

        if from_id not in segment_ids:
            errors.append(f"源片段ID {from_id} 不存在")
        if to_id not in segment_ids:
            errors.append(f"目标片段ID {to_id} 不存在")

        # 验证文本内容
        text = command.get('text', '')
        if not text.strip():
            errors.append("MOVE指令的text不能为空")

        # 验证源片段是否包含要移动的文本
        from_segment = next((s for s in subtitles if s['id'] == from_id), None)
        if from_segment and text not in from_segment.get('text', ''):
            errors.append(f"源片段{from_id}中未找到文本: '{text}'")

        return errors

    def _validate_update_command(self, command: Dict[str, Any], subtitles: List[Dict[str, Any]]) -> List[str]:
        """验证UPDATE指令"""
        errors = []

        if 'id' not in command:
            errors.append("UPDATE指令缺少id字段")
        if 'changes' not in command:
            errors.append("UPDATE指令缺少changes字段")

        if errors:
            return errors

        # 验证片段存在性
        segment_ids = {sub['id'] for sub in subtitles}
        segment_id = command['id']

        if segment_id not in segment_ids:
            errors.append(f"片段ID {segment_id} 不存在")

        # 验证changes
        changes = command.get('changes', {})
        if not isinstance(changes, dict):
            errors.append("changes字段必须是字典")
        elif not changes:
            errors.append("changes不能为空")
        else:
            # 验证替换内容不为空
            for old, new in changes.items():
                if not old.strip():
                    errors.append("替换的旧文本不能为空")

        return errors

    def _validate_delete_command(self, command: Dict[str, Any], subtitles: List[Dict[str, Any]]) -> List[str]:
        """验证DELETE指令"""
        errors = []

        if 'id' not in command:
            errors.append("DELETE指令缺少id字段")
        if 'words' not in command:
            errors.append("DELETE指令缺少words字段")

        if errors:
            return errors

        # 验证片段存在性
        segment_ids = {sub['id'] for sub in subtitles}
        segment_id = command['id']

        if segment_id not in segment_ids:
            errors.append(f"片段ID {segment_id} 不存在")

        # 验证words
        words = command.get('words', [])
        if not isinstance(words, list):
            errors.append("words字段必须是列表")
        elif not words:
            errors.append("words不能为空")
        else:
            # 验证词汇不为空
            for word in words:
                if not word.strip():
                    errors.append("要删除的词不能为空")

        return errors

    def _validate_punctuate_command(self, command: Dict[str, Any], subtitles: List[Dict[str, Any]]) -> List[str]:
        """验证PUNCTUATE指令"""
        errors = []

        if 'updates' not in command:
            errors.append("PUNCTUATE指令缺少updates字段")
            return errors

        # 验证updates
        updates = command.get('updates', {})
        if not isinstance(updates, dict):
            errors.append("updates字段必须是字典")
        elif not updates:
            errors.append("updates不能为空")
        else:
            # 验证片段ID和标点
            segment_ids = {sub['id'] for sub in subtitles}
            for segment_id_str, punctuation in updates.items():
                try:
                    segment_id = int(segment_id_str)
                except ValueError:
                    errors.append(f"片段ID '{segment_id_str}' 格式无效")
                    continue

                if segment_id not in segment_ids:
                    errors.append(f"片段ID {segment_id} 不存在")

                if not punctuation.strip():
                    errors.append(f"片段{segment_id}的标点不能为空")

        return errors

    def _validate_cross_command_logic(self, commands: List[Dict[str, Any]], subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证跨指令逻辑

        Args:
            commands: 指令列表
            subtitles: 字幕列表

        Returns:
            逻辑错误列表
        """
        logic_errors = []

        # 检查同一片段的多次修改
        segment_commands = defaultdict(list)
        for i, cmd in enumerate(commands):
            segment_id = self._get_command_segment_id(cmd)
            if segment_id is not None:
                segment_commands[segment_id].append((i, cmd))

        for segment_id, cmds in segment_commands.items():
            if len(cmds) > 2:
                logic_errors.append({
                    'index': cmds[1][0],  # 第二个指令
                    'message': f'片段{segment_id}有{len(cmds)}个指令，可能导致冲突'
                })

        return logic_errors

    def _get_command_segment_id(self, command: Dict[str, Any]) -> Optional[int]:
        """获取指令关联的片段ID"""
        cmd_type = command.get('command', '').upper()

        if cmd_type == 'MOVE':
            return command.get('to_id')
        elif cmd_type in ['UPDATE', 'DELETE']:
            return command.get('id')
        elif cmd_type == 'PUNCTUATE':
            updates = command.get('updates', {})
            if updates:
                try:
                    return int(list(updates.keys())[0])
                except (ValueError, IndexError):
                    return None

        return None


class CommandStatisticsCollector:
    """指令统计收集器

    收集和分析指令执行统计数据。
    """

    def __init__(self):
        """初始化统计收集器"""
        self.execution_history: List[Dict[str, Any]] = []
        self.type_statistics: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            'total': 0, 'success': 0, 'failure': 0, 'applied': 0, 'skipped': 0
        })
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start_tracking(self):
        """开始跟踪"""
        self.start_time = datetime.now().timestamp()
        logger.debug("开始指令执行统计跟踪")

    def record_execution(self,
                        command_index: int,
                        command_type: str,
                        success: bool,
                        applied: bool,
                        execution_time: float,
                        error_message: Optional[str] = None):
        """记录单次执行

        Args:
            command_index: 指令索引
            command_type: 指令类型
            success: 是否成功
            applied: 是否应用
            execution_time: 执行时间
            error_message: 错误信息
        """
        execution_record = {
            'index': command_index,
            'type': command_type,
            'success': success,
            'applied': applied,
            'execution_time': execution_time,
            'timestamp': datetime.now().timestamp(),
            'error': error_message
        }

        self.execution_history.append(execution_record)

        # 更新类型统计
        stats = self.type_statistics[command_type]
        stats['total'] += 1
        if success:
            stats['success'] += 1
        else:
            stats['failure'] += 1

        if applied:
            stats['applied'] += 1
        else:
            stats['skipped'] += 1

        logger.debug(f"记录指令执行 - {command_type}[{command_index}]: "
                    f"成功={success}, 应用={applied}, 耗时={execution_time:.3f}秒")

    def stop_tracking(self):
        """停止跟踪"""
        self.end_time = datetime.now().timestamp()
        logger.debug(f"停止指令执行统计跟踪 - 总耗时: {self.get_total_duration():.3f}秒")

    def get_statistics(self) -> CommandExecutionStatistics:
        """获取完整统计

        Returns:
            执行统计
        """
        total = len(self.execution_history)
        successful = sum(1 for e in self.execution_history if e['success'])
        failed = total - successful
        applied = sum(1 for e in self.execution_history if e['applied'])
        skipped = total - applied

        # 转换为普通字典
        by_type = {
            cmd_type: dict(stats)
            for cmd_type, stats in self.type_statistics.items()
        }

        return CommandExecutionStatistics(
            total_commands=total,
            successful_commands=successful,
            failed_commands=failed,
            applied_commands=applied,
            skipped_commands=skipped,
            by_type=by_type,
            execution_time=self.get_total_duration(),
            error_details=[
                {
                    'index': e['index'],
                    'type': e['type'],
                    'error': e['error']
                }
                for e in self.execution_history if not e['success']
            ]
        )

    def get_total_duration(self) -> float:
        """获取总执行时间

        Returns:
            总时间（秒）
        """
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def get_success_rate(self) -> float:
        """获取成功率

        Returns:
            成功率 (0-1)
        """
        if not self.execution_history:
            return 0.0
        return sum(1 for e in self.execution_history if e['success']) / len(self.execution_history)

    def get_application_rate(self) -> float:
        """获取应用率

        Returns:
            应用率 (0-1)
        """
        if not self.execution_history:
            return 0.0
        return sum(1 for e in self.execution_history if e['applied']) / len(self.execution_history)

    def get_performance_metrics(self) -> Dict[str, float]:
        """获取性能指标

        Returns:
            性能指标
        """
        if not self.execution_history:
            return {}

        execution_times = [e['execution_time'] for e in self.execution_history]

        return {
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'min_execution_time': min(execution_times),
            'max_execution_time': max(execution_times),
            'total_execution_time': sum(execution_times)
        }

    def get_type_distribution(self) -> Dict[str, int]:
        """获取指令类型分布

        Returns:
            类型分布
        """
        return dict(Counter(e['type'] for e in self.execution_history))

    def log_summary(self):
        """记录统计摘要"""
        stats = self.get_statistics()
        performance = self.get_performance_metrics()
        distribution = self.get_type_distribution()

        logger.info("指令执行统计摘要:")
        logger.info(f"  总指令数: {stats.total_commands}")
        logger.info(f"  成功率: {stats.successful_commands}/{stats.total_commands} ({self.get_success_rate():.2%})")
        logger.info(f"  应用率: {stats.applied_commands}/{stats.total_commands} ({self.get_application_rate():.2%})")
        logger.info(f"  执行时间: {stats.execution_time:.3f}秒")
        logger.info(f"  类型分布: {distribution}")

        if stats.failed_commands > 0:
            logger.warning(f"  失败指令: {stats.failed_commands}")
            for error in stats.error_details:
                logger.warning(f"    - {error['type']}[{error['index']}]: {error['error']}")

    def export_report(self) -> Dict[str, Any]:
        """导出完整报告

        Returns:
            完整报告
        """
        return {
            'statistics': self.get_statistics().__dict__,
            'performance_metrics': self.get_performance_metrics(),
            'type_distribution': self.get_type_distribution(),
            'execution_history': self.execution_history,
            'generated_at': datetime.now().isoformat()
        }