# services/common/cache_key_strategy.py
# -*- coding: utf-8 -*-

"""
缓存键策略模块。

本模块提供统一的缓存键生成策略，确保复用判定逻辑透明且一致。

核心概念：
- 显式声明：每个节点明确声明缓存键字段
- 稳定生成：相同输入总是生成相同的缓存键
- 多字段组合：支持多个字段组合生成缓存键
"""

import hashlib
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class CacheKeyStrategy(ABC):
    """缓存键生成策略接口"""

    @abstractmethod
    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        子类必须实现此方法以声明缓存键字段。

        Returns:
            字段名称列表

        Examples:
            >>> return ["audio_path", "model_name"]
        """
        pass

    def generate_cache_key(self, task_name: str, input_params: Dict[str, Any]) -> str:
        """
        生成缓存键。

        Args:
            task_name: 任务名称（如 "ffmpeg.extract_audio"）
            input_params: 输入参数字典

        Returns:
            缓存键字符串（格式：task_name:hash）

        Examples:
            >>> strategy.generate_cache_key("ffmpeg.extract_audio", {"video_path": "/share/video.mp4"})
            'ffmpeg.extract_audio:5f4dcc3b5aa765d61d8327deb882cf99'
        """
        key_fields = self.get_cache_key_fields()
        key_values = {}

        for field in key_fields:
            if field in input_params:
                key_values[field] = input_params[field]

        # 生成稳定的哈希（使用排序后的 JSON）
        key_str = json.dumps(key_values, sort_keys=True)
        hash_value = hashlib.md5(key_str.encode()).hexdigest()

        return f"{task_name}:{hash_value}"


def can_reuse_cache(
    stage_output: Dict[str, Any],
    stage_status: str,
    required_fields: List[str]
) -> bool:
    """
    判断是否可以复用缓存。

    Args:
        stage_output: 阶段输出字典
        stage_status: 阶段状态
        required_fields: 必需的输出字段列表

    Returns:
        True 如果可以复用，False 否则

    Examples:
        >>> can_reuse_cache(
        ...     {"audio_path": "/share/audio.wav"},
        ...     "SUCCESS",
        ...     ["audio_path"]
        ... )
        True
    """
    # 检查状态
    if stage_status != "SUCCESS":
        return False

    # 检查输出是否为空
    if not stage_output:
        return False

    # 检查必需字段
    for field in required_fields:
        if field not in stage_output:
            return False
        # 只有 None 和空字符串被视为无效值
        # 数字 0 和布尔值 False 是有效值
        value = stage_output[field]
        if value is None or value == '':
            return False

    return True


def is_pending_state(stage_status: str) -> bool:
    """
    判断是否为等待态。

    Args:
        stage_status: 阶段状态

    Returns:
        True 如果是等待态，False 否则
    """
    return stage_status in ["PENDING", "RUNNING"]
