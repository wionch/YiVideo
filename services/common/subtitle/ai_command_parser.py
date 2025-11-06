"""
AI优化指令解析器

解析AI模型返回的JSON指令，支持MOVE、UPDATE、DELETE、PUNCTUATE四种简单指令。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import json
import logging
from typing import List, Dict, Any, Union
from enum import Enum

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """指令类型枚举"""
    MOVE = "MOVE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PUNCTUATE = "PUNCTUATE"


class AICommandParser:
    """AI优化指令解析器

    解析AI返回的JSON指令，确保指令格式正确且参数完整。
    """

    def __init__(self):
        """初始化解析器"""
        pass

    def parse_response(self, response: str) -> List[Dict[str, Any]]:
        """解析AI响应

        Args:
            response: AI模型返回的JSON字符串

        Returns:
            解析后的指令列表

        Raises:
            json.JSONDecodeError: JSON格式错误
            ValueError: 指令格式无效
        """
        logger.info("开始解析AI响应")

        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            raise

        # 检查是否包含commands字段
        if 'commands' not in data:
            logger.warning("AI响应缺少commands字段")
            return []

        commands = data['commands']

        if not isinstance(commands, list):
            logger.warning("commands字段不是数组格式")
            return []

        # 解析和验证每个指令
        valid_commands = []
        for i, command in enumerate(commands):
            try:
                validated_command = self._validate_command(command, i + 1)
                if validated_command:
                    valid_commands.append(validated_command)
            except (ValueError, KeyError) as e:
                logger.warning(f"指令 {i + 1} 格式无效，跳过: {e}")
                continue

        logger.info(f"解析完成: {len(valid_commands)}个有效指令")
        return valid_commands

    def _validate_command(self, command: Dict[str, Any], index: int) -> Dict[str, Any]:
        """验证单个指令

        Args:
            command: 指令字典
            index: 指令索引

        Returns:
            验证后的指令

        Raises:
            ValueError: 指令格式无效
        """
        if not isinstance(command, dict):
            raise ValueError(f"指令 {index} 不是对象格式")

        # 检查指令类型
        if 'command' not in command:
            raise ValueError(f"指令 {index} 缺少command字段")

        cmd_type = command['command'].upper()

        # 验证指令类型
        if cmd_type not in [e.value for e in CommandType]:
            raise ValueError(f"指令 {index} 类型无效: {cmd_type}")

        # 根据类型验证参数
        if cmd_type == CommandType.MOVE.value:
            return self._validate_move_command(command, index)
        elif cmd_type == CommandType.UPDATE.value:
            return self._validate_update_command(command, index)
        elif cmd_type == CommandType.DELETE.value:
            return self._validate_delete_command(command, index)
        elif cmd_type == CommandType.PUNCTUATE.value:
            return self._validate_punctuate_command(command, index)
        else:
            raise ValueError(f"指令 {index} 不支持的类型: {cmd_type}")

    def _validate_move_command(self, command: Dict[str, Any], index: int) -> Dict[str, Any]:
        """验证MOVE指令

        Args:
            command: 指令字典
            index: 指令索引

        Returns:
            验证后的MOVE指令

        Raises:
            ValueError: 参数无效
        """
        required_fields = ['from_id', 'to_id', 'text']
        for field in required_fields:
            if field not in command:
                raise ValueError(f"MOVE指令 {index} 缺少字段: {field}")

        # 验证ID
        if not isinstance(command['from_id'], int) or command['from_id'] < 1:
            raise ValueError(f"MOVE指令 {index} from_id无效")
        if not isinstance(command['to_id'], int) or command['to_id'] < 1:
            raise ValueError(f"MOVE指令 {index} to_id无效")

        # 验证文本
        if not isinstance(command['text'], str):
            raise ValueError(f"MOVE指令 {index} text无效")

        return {
            'command': 'MOVE',
            'from_id': command['from_id'],
            'to_id': command['to_id'],
            'text': command['text']
        }

    def _validate_update_command(self, command: Dict[str, Any], index: int) -> Dict[str, Any]:
        """验证UPDATE指令

        Args:
            command: 指令字典
            index: 指令索引

        Returns:
            验证后的UPDATE指令

        Raises:
            ValueError: 参数无效
        """
        if 'id' not in command:
            raise ValueError(f"UPDATE指令 {index} 缺少字段: id")
        if 'changes' not in command:
            raise ValueError(f"UPDATE指令 {index} 缺少字段: changes")

        # 验证ID
        if not isinstance(command['id'], int) or command['id'] < 1:
            raise ValueError(f"UPDATE指令 {index} id无效")

        # 验证changes
        if not isinstance(command['changes'], dict):
            raise ValueError(f"UPDATE指令 {index} changes无效")
        if not command['changes']:
            raise ValueError(f"UPDATE指令 {index} changes不能为空")

        return {
            'command': 'UPDATE',
            'id': command['id'],
            'changes': command['changes']
        }

    def _validate_delete_command(self, command: Dict[str, Any], index: int) -> Dict[str, Any]:
        """验证DELETE指令

        Args:
            command: 指令字典
            index: 指令索引

        Returns:
            验证后的DELETE指令

        Raises:
            ValueError: 参数无效
        """
        if 'id' not in command:
            raise ValueError(f"DELETE指令 {index} 缺少字段: id")
        if 'words' not in command:
            raise ValueError(f"DELETE指令 {index} 缺少字段: words")

        # 验证ID
        if not isinstance(command['id'], int) or command['id'] < 1:
            raise ValueError(f"DELETE指令 {index} id无效")

        # 验证words
        if not isinstance(command['words'], list):
            raise ValueError(f"DELETE指令 {index} words无效")
        if not command['words']:
            raise ValueError(f"DELETE指令 {index} words不能为空")

        return {
            'command': 'DELETE',
            'id': command['id'],
            'words': command['words']
        }

    def _validate_punctuate_command(self, command: Dict[str, Any], index: int) -> Dict[str, Any]:
        """验证PUNCTUATE指令

        Args:
            command: 指令字典
            index: 指令索引

        Returns:
            验证后的PUNCTUATE指令

        Raises:
            ValueError: 参数无效
        """
        if 'updates' not in command:
            raise ValueError(f"PUNCTUATE指令 {index} 缺少字段: updates")

        # 验证updates
        if not isinstance(command['updates'], dict):
            raise ValueError(f"PUNCTUATE指令 {index} updates无效")
        if not command['updates']:
            raise ValueError(f"PUNCTUATE指令 {index} updates不能为空")

        return {
            'command': 'PUNCTUATE',
            'updates': command['updates']
        }

    def validate_commands_count(self, commands: List[Dict[str, Any]], max_commands: int = 100) -> bool:
        """验证指令数量

        Args:
            commands: 指令列表
            max_commands: 最大指令数

        Returns:
            是否在允许范围内
        """
        if len(commands) > max_commands:
            logger.warning(f"指令数量 {len(commands)} 超过限制 {max_commands}")
            return False

        return True