# services/common/lock_selector.py
# -*- coding: utf-8 -*-

"""
GPU锁选择器 - 统一使用V3智能锁机制
"""

from typing import Dict, Any, Callable

from services.common.config_loader import get_gpu_lock_config
from services.common.locks import gpu_lock as gpu_lock_impl
from services.common.locks import get_gpu_lock_status as get_status_impl
from services.common.locks import release_gpu_lock as release_impl
from services.common.logger import get_logger

logger = get_logger('lock_selector')


def gpu_lock(lock_key: str = "gpu_lock:0",
              timeout: int = None,
              retry_interval: int = None,
              event_driven: bool = None,
              max_wait_time: int = None) -> Callable:
    """
    GPU锁装饰器 - 使用V3智能锁机制（增强版）

    支持事件驱动和智能轮询混合机制，显著提高响应速度

    Args:
        lock_key: 锁键
        timeout: 锁超时时间
        retry_interval: 重试间隔（此参数已废弃，保留用于兼容性）
        event_driven: 是否启用事件驱动（None表示使用配置文件设置）
        max_wait_time: 最大等待时间

    Returns:
        Callable: GPU锁装饰器
    """
    try:
        # 获取GPU锁配置
        config = get_gpu_lock_config()

        if event_driven is None:
            event_driven = config.get('use_event_driven', True)

        if max_wait_time is None:
            max_wait_time = config.get('max_wait_time', 300)

        mechanism = "事件驱动+智能轮询" if event_driven else "智能轮询"
        logger.info(f"使用V3智能锁机制：{mechanism}")

        # 使用V3智能锁
        return gpu_lock_impl(
            lock_key=lock_key,
            timeout=timeout,
            max_wait_time=max_wait_time,
            event_driven=event_driven
        )

    except Exception as e:
        logger.error(f"获取锁配置失败，使用默认配置: {e}")
        return gpu_lock_impl(
            lock_key=lock_key,
            timeout=timeout,
            max_wait_time=max_wait_time,
            event_driven=event_driven
        )


def get_gpu_lock_status(lock_key: str = "gpu_lock:0") -> Dict[str, Any]:
    """
    获取GPU锁状态

    Args:
        lock_key: 锁键

    Returns:
        Dict[str, Any]: 锁状态信息
    """
    try:
        return get_status_impl(lock_key)
    except Exception as e:
        logger.error(f"获取锁状态失败: {e}")
        return {"error": str(e)}


def release_gpu_lock(lock_key: str = "gpu_lock:0", task_name: str = "manual") -> bool:
    """
    释放GPU锁

    Args:
        lock_key: 锁键
        task_name: 任务名称

    Returns:
        bool: 是否成功释放
    """
    try:
        return release_impl(lock_key, task_name)
    except Exception as e:
        logger.error(f"释放锁失败: {e}")
        return False