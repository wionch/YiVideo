# services/common/locks.py
# -*- coding: utf-8 -*-

"""
GPU锁架构V3：智能锁机制
结合V1和V2的优点，支持动态调整策略和指数退避轮询
"""

import os
import functools
import logging
import time
import threading
import random
from typing import Dict, Any, Optional

from redis import Redis

# 导入配置加载器以支持运行时配置
from services.common.config_loader import get_gpu_lock_config
from services.common.logger import get_logger

logger = get_logger('locks')

# --- Redis 连接 ---
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_LOCK_DB = int(os.environ.get('REDIS_LOCK_DB', 2))

try:
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_LOCK_DB, decode_responses=True)
    redis_client.ping()
    logger.info(f"成功连接到Redis锁数据库 at {REDIS_HOST}:{REDIS_PORT}/{REDIS_LOCK_DB}")
except Exception as e:
    logger.error(f"无法连接到Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_LOCK_DB}. GPU锁将无法工作. 错误: {e}")
    redis_client = None


class SmartGpuLockManager:
    """智能GPU锁管理器 - 支持动态策略调整"""

    def __init__(self):
        self.lock_stats = {
            'total_attempts': 0,
            'successful_acquisitions': 0,
            'timeouts': 0,
            'average_wait_time': 0.0
        }

    def acquire_lock_with_smart_polling(self, task_name: str, lock_key: str, config: Dict[str, Any]) -> bool:
        """
        使用智能轮询机制获取锁

        Args:
            task_name: 任务名称
            lock_key: 锁键
            config: 配置

        Returns:
            bool: 是否成功获取锁
        """
        if not redis_client:
            logger.error("Redis客户端未初始化，无法获取锁")
            return False

        max_wait_time = config.get('max_wait_time', 6000)  # 最大等待时间100分钟
        initial_poll_interval = config.get('poll_interval', 1)  # 初始轮询间隔
        lock_timeout = config.get('lock_timeout', 9000)   # 锁超时时间150分钟
        exponential_backoff = config.get('exponential_backoff', True)  # 指数退避
        max_poll_interval = config.get('max_poll_interval', 10)  # 最大轮询间隔

        start_time = time.time()
        retry_count = 0
        current_wait_time = initial_poll_interval

        logger.info(f"任务 {task_name} 开始智能获取锁 '{lock_key}' (最大等待: {max_wait_time}秒)")

        while time.time() - start_time < max_wait_time:
            retry_count += 1
            self.lock_stats['total_attempts'] += 1

            try:
                # 检查锁状态
                lock_value = redis_client.get(lock_key)
                if lock_value:
                    lock_ttl = redis_client.ttl(lock_key)
                    logger.info(f"任务 {task_name} 等待锁 '{lock_key}' (持有者: {lock_value}, 剩余TTL: {lock_ttl}秒)")
                else:
                    # 尝试获取锁 - 使用统一的锁值格式
                    lock_value = f"locked_by_{task_name}"
                    if redis_client.set(lock_key, lock_value, nx=True, ex=lock_timeout):
                        self.lock_stats['successful_acquisitions'] += 1
                        wait_duration = time.time() - start_time
                        logger.info(f"任务 {task_name} 成功获取锁 '{lock_key}' (等待时间: {wait_duration:.2f}秒, 重试次数: {retry_count})")
                        return True

                # 计算下一次等待时间
                if exponential_backoff:
                    # 指数退避 + 随机抖动
                    current_wait_time = min(current_wait_time * 1.5, max_poll_interval)
                    # 添加随机抖动避免多个任务同步
                    jitter = random.uniform(0.8, 1.2)
                    actual_wait = current_wait_time * jitter
                else:
                    actual_wait = initial_poll_interval

                # 记录统计信息
                if retry_count % 10 == 0:  # 每10次记录一次
                    logger.info(f"任务 {task_name} 已等待 {time.time() - start_time:.1f}秒，重试 {retry_count} 次")

                # 等待
                time.sleep(actual_wait)

            except Exception as e:
                logger.error(f"任务 {task_name} 获取锁时发生异常: {e}")
                time.sleep(initial_poll_interval)

        # 超时返回失败
        self.lock_stats['timeouts'] += 1
        wait_duration = time.time() - start_time
        logger.error(f"任务 {task_name} 获取锁 '{lock_key}' 超时 (等待时间: {wait_duration:.1f}秒, 重试次数: {retry_count})")
        return False

    def release_lock(self, task_name: str, lock_key: str) -> bool:
        """
        释放锁

        Args:
            task_name: 任务名称
            lock_key: 锁键

        Returns:
            bool: 是否成功释放
        """
        if not redis_client:
            return False

        try:
            lock_value = redis_client.get(lock_key)
            # 兼容多种锁值格式：
            # 1. 新格式：locked_by_{task_name}
            # 2. 旧格式：locked
            # 3. 其他格式：只要包含任务名称或就是locked
            if lock_value and (
                f"locked_by_{task_name}" in lock_value or
                lock_value == "locked" or
                task_name in lock_value
            ):
                redis_client.delete(lock_key)
                logger.info(f"任务 {task_name} 释放锁 '{lock_key}' (原值: {lock_value})")
                return True
            else:
                logger.warning(f"任务 {task_name} 尝试释放不持有的锁 '{lock_key}' (当前值: {lock_value})")
                return False
        except Exception as e:
            logger.error(f"任务 {task_name} 释放锁时发生异常: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取锁统计信息"""
        stats = self.lock_stats.copy()
        if stats['total_attempts'] > 0:
            stats['success_rate'] = stats['successful_acquisitions'] / stats['total_attempts']
            stats['timeout_rate'] = stats['timeouts'] / stats['total_attempts']
        else:
            stats['success_rate'] = 0.0
            stats['timeout_rate'] = 0.0
        return stats


# 全局锁管理器实例
lock_manager = SmartGpuLockManager()


def gpu_lock(lock_key: str = "gpu_lock:0", timeout: int = None, poll_interval: int = None, max_wait_time: int = None):
    """
    GPU锁装饰器 - 智能轮询机制

    关键设计理念：
    - 支持指数退避和随机抖动
    - 详细的统计信息
    - 适当的异常处理

    Args:
        lock_key: 锁键
        timeout: 锁超时时间
        poll_interval: 初始轮询间隔
        max_wait_time: 最大等待时间
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 获取任务名称
            task_name = getattr(self, 'name', func.__name__)

            if not redis_client:
                logger.error(f"任务 {task_name} Redis客户端未初始化，将直接执行任务")
                return func(self, *args, **kwargs)

            # 获取配置
            try:
                config = get_gpu_lock_config()
            except Exception as e:
                logger.error(f"获取GPU锁配置失败: {e}，使用默认配置")
                config = {
                    'poll_interval': 1,
                    'max_wait_time': 6000,
                    'lock_timeout': 9000,
                    'exponential_backoff': True,
                    'max_poll_interval': 10
                }

            # 使用传入参数或配置
            actual_timeout = timeout if timeout is not None else config.get('lock_timeout', 9000)
            actual_poll_interval = poll_interval if poll_interval is not None else config.get('poll_interval', 1)
            actual_max_wait_time = max_wait_time if max_wait_time is not None else config.get('max_wait_time', 6000)

            # 构建智能轮询配置
            poll_config = {
                'poll_interval': actual_poll_interval,
                'max_wait_time': actual_max_wait_time,
                'lock_timeout': actual_timeout,
                'exponential_backoff': config.get('exponential_backoff', True),
                'max_poll_interval': config.get('max_poll_interval', 10)
            }

            logger.info(f"任务 {task_name} 开始获取锁 '{lock_key}' (智能轮询, 超时: {actual_max_wait_time}秒)")

            # 使用智能轮询机制获取锁
            if lock_manager.acquire_lock_with_smart_polling(task_name, lock_key, poll_config):
                try:
                    # 成功获取锁，执行任务
                    logger.info(f"任务 {task_name} 开始执行")
                    result = func(self, *args, **kwargs)
                    logger.info(f"任务 {task_name} 执行完成")

                    # 记录成功统计
                    stats = lock_manager.get_statistics()
                    logger.info(f"锁统计: 成功率 {stats['success_rate']:.2%}, 超时率 {stats['timeout_rate']:.2%}")

                    return result
                finally:
                    # 任务执行完毕，释放锁
                    lock_manager.release_lock(task_name, lock_key)
            else:
                # 获取锁失败，抛出异常
                error_msg = f"任务 {task_name} 无法获取锁 '{lock_key}'，任务放弃执行"
                logger.error(error_msg)

                # 获取统计信息
                stats = lock_manager.get_statistics()
                logger.error(f"当前锁统计: 总尝试 {stats['total_attempts']}, 成功 {stats['successful_acquisitions']}, 超时 {stats['timeouts']}")

                # 抛出异常，让Celery和工作流引擎知道任务失败
                raise Exception(f"GPU_LOCK_TIMEOUT: {error_msg}")

        return wrapper
    return decorator


def get_gpu_lock_status(lock_key: str = "gpu_lock:0") -> Dict[str, Any]:
    """
    获取GPU锁状态信息

    Args:
        lock_key: 锁键

    Returns:
        dict: 锁状态信息
    """
    if not redis_client:
        return {"error": "Redis客户端未初始化"}

    try:
        lock_value = redis_client.get(lock_key)
        ttl = redis_client.ttl(lock_key)

        status = {
            "lock_key": lock_key,
            "is_locked": lock_value is not None,
            "lock_holder": lock_value,
            "ttl_seconds": ttl if ttl > 0 else None,
            "timestamp": time.time(),
            "statistics": lock_manager.get_statistics()
        }

        return status

    except Exception as e:
        logger.error(f"获取锁状态失败: {e}")
        return {"error": str(e)}


def release_gpu_lock(lock_key: str = "gpu_lock:0", task_name: str = "manual") -> bool:
    """
    手动释放GPU锁

    Args:
        lock_key: 锁键
        task_name: 任务名称

    Returns:
        bool: 是否成功释放
    """
    return lock_manager.release_lock(task_name, lock_key)