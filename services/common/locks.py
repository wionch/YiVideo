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
import json
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

from redis import Redis

# 导入配置加载器以支持运行时配置
from services.common.config_loader import get_gpu_lock_config, get_redis_config
from services.common.logger import get_logger

logger = get_logger('locks')

# --- Redis 连接 ---
redis_client = None
try:
    redis_config = get_redis_config()
    REDIS_HOST = redis_config['host']
    REDIS_PORT = redis_config['port']
    REDIS_LOCK_DB = int(os.environ.get('REDIS_LOCK_DB', 2))
    
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_LOCK_DB, decode_responses=True)
    redis_client.ping()
    logger.info(f"成功连接到Redis锁数据库 at {REDIS_HOST}:{REDIS_PORT}/{REDIS_LOCK_DB}")
except (ValueError, Exception) as e:
    logger.error(f"无法连接到Redis. GPU锁将无法工作. 错误: {e}")
    # redis_client 保持为 None

# --- 枚举定义 ---
class LockMechanism(Enum):
    """锁机制类型"""
    POLLING = "polling"  # 轮询机制
    EVENT_DRIVEN = "event_driven"  # 事件驱动
    HYBRID = "hybrid"  # 混合机制

# --- 全局Pub/Sub管理器 ---
class PubSubManager:
    """Redis Pub/Sub管理器 - 提供事件驱动的锁释放通知"""

    def __init__(self):
        self.pub_sub = None
        self.subscribers = {}  # lock_key -> 订阅者集合
        self.subscriber_lock = threading.Lock()
        self.running = True

    def initialize(self):
        """初始化Pub/Sub连接"""
        if not redis_client:
            logger.error("Redis客户端未初始化，Pub/Sub功能将不可用")
            return

        try:
            self.pub_sub = redis_client.pubsub()
            logger.info("Redis Pub/Sub连接初始化成功")
        except Exception as e:
            logger.error(f"Redis Pub/Sub连接初始化失败: {e}")
            self.pub_sub = None

    def publish_lock_release(self, lock_key: str, task_name: str, release_reason: str = "normal"):
        """
        发布锁释放事件

        Args:
            lock_key: 锁键
            task_name: 释放锁的任务名称
            release_reason: 释放原因 (normal/timeout/forced)
        """
        if not redis_client:
            return

        try:
            event_data = {
                "event_type": "lock_released",
                "lock_key": lock_key,
                "task_name": task_name,
                "release_reason": release_reason,
                "timestamp": time.time()
            }

            channel = f"gpu_lock:{lock_key}"
            redis_client.publish(channel, json.dumps(event_data))
            logger.debug(f"已发布锁释放事件: {lock_key} by {task_name} ({release_reason})")

        except Exception as e:
            logger.error(f"发布锁释放事件失败: {e}")

    def subscribe_to_lock(self, lock_key: str, callback: Callable[[str, str, str], None]):
        """
        订阅特定锁的释放事件

        Args:
            lock_key: 锁键
            callback: 回调函数 (lock_key, task_name, release_reason) -> None
        """
        if not self.pub_sub:
            logger.warning("Pub/Sub未初始化，无法订阅锁释放事件")
            return

        with self.subscriber_lock:
            if lock_key not in self.subscribers:
                self.subscribers[lock_key] = set()

                # 订阅Redis频道
                channel = f"gpu_lock:{lock_key}"
                self.pub_sub.subscribe(channel)
                logger.debug(f"已订阅锁释放频道: {channel}")

            self.subscribers[lock_key].add(callback)

    def unsubscribe_from_lock(self, lock_key: str, callback: Callable = None):
        """
        取消订阅特定锁的释放事件

        Args:
            lock_key: 锁键
            callback: 要取消的回调函数，如果为None则取消所有回调
        """
        with self.subscriber_lock:
            if lock_key in self.subscribers:
                if callback:
                    self.subscribers[lock_key].discard(callback)
                else:
                    self.subscribers[lock_key].clear()

                # 如果没有订阅者了，取消订阅Redis频道
                if not self.subscribers[lock_key]:
                    channel = f"gpu_lock:{lock_key}"
                    self.pub_sub.unsubscribe(channel)
                    del self.subscribers[lock_key]
                    logger.debug(f"已取消订阅锁释放频道: {channel}")

    def start_listener(self):
        """启动Pub/Sub监听线程"""
        if not self.pub_sub:
            return

        def listener_thread():
            logger.info("Pub/Sub监听线程启动")
            while self.running:
                try:
                    message = self.pub_sub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        self._handle_message(message)
                except Exception as e:
                    logger.error(f"Pub/Sub监听异常: {e}")
                    time.sleep(1)
            logger.info("Pub/Sub监听线程停止")

        thread = threading.Thread(target=listener_thread, daemon=True)
        thread.start()

    def _handle_message(self, message):
        """处理接收到的Pub/Sub消息"""
        try:
            channel = message['channel']
            data = json.loads(message['data'])

            if data.get('event_type') == 'lock_released':
                lock_key = data.get('lock_key')
                task_name = data.get('task_name')
                release_reason = data.get('release_reason', 'unknown')

                # 通知所有订阅者
                with self.subscriber_lock:
                    if lock_key in self.subscribers:
                        for callback in self.subscribers[lock_key].copy():
                            try:
                                callback(lock_key, task_name, release_reason)
                            except Exception as e:
                                logger.error(f"锁释放回调执行失败: {e}")

        except Exception as e:
            logger.error(f"处理Pub/Sub消息失败: {e}")

    def stop(self):
        """停止Pub/Sub监听"""
        self.running = False
        if self.pub_sub:
            self.pub_sub.close()

# 全局Pub/Sub管理器实例
pub_sub_manager = PubSubManager()
pub_sub_manager.initialize()
pub_sub_manager.start_listener()


class SmartGpuLockManager:
    """智能GPU锁管理器 - 支持动态策略调整和基础监控功能"""

    def __init__(self):
        self.lock_stats = {
            'total_attempts': 0,
            'successful_acquisitions': 0,
            'timeouts': 0,
            'average_wait_time': 0.0,
            'last_lock_time': None,
            'last_lock_holder': None,
            'total_execution_time': 0.0,
            'execution_count': 0,
            'event_driven_acquisitions': 0,  # 事件驱动获取次数
            'polling_acquisitions': 0  # 轮询获取次数
        }
        self.lock_history = []  # 锁历史记录
        self.max_history_size = 100  # 最大历史记录数
        self.event_waiters = {}  # 等待锁释放的事件: lock_key -> threading.Event

    def _acquire_lock_internal(self, task_name: str, lock_key: str, config: Dict[str, Any], start_time: float) -> bool:
        """
        内部锁获取逻辑

        Args:
            task_name: 任务名称
            lock_key: 锁键
            config: 配置
            start_time: 开始时间

        Returns:
            bool: 是否成功获取锁
        """
        if not redis_client:
            logger.error("Redis客户端未初始化，无法获取锁")
            return False

        max_wait_time = config.get('max_wait_time', 6000)  # 最大等待时间
        initial_poll_interval = config.get('poll_interval', 1)  # 初始轮询间隔
        lock_timeout = config.get('lock_timeout', 9000)   # 锁超时时间
        exponential_backoff = config.get('exponential_backoff', True)  # 指数退避
        max_poll_interval = config.get('max_poll_interval', 10)  # 最大轮询间隔
        use_event_driven = config.get('use_event_driven', True)  # 是否使用事件驱动

        retry_count = 0
        current_wait_time = initial_poll_interval

        mechanism = LockMechanism.EVENT_DRIVEN if use_event_driven else LockMechanism.POLLING
        logger.info(f"任务 {task_name} 开始获取锁 '{lock_key}' (机制: {mechanism.value}, 最大等待: {max_wait_time}秒)")

        # 使用事件驱动机制
        if use_event_driven and pub_sub_manager.pub_sub:
            return self._acquire_lock_event_driven(task_name, lock_key, config, start_time)
        else:
            # 回退到轮询机制
            return self._acquire_lock_polling(task_name, lock_key, config, start_time)

    def _acquire_lock_event_driven(self, task_name: str, lock_key: str, config: Dict[str, Any], start_time: float) -> bool:
        """
        事件驱动的锁获取逻辑

        Args:
            task_name: 任务名称
            lock_key: 锁键
            config: 配置
            start_time: 开始时间

        Returns:
            bool: 是否成功获取锁
        """
        max_wait_time = config.get('max_wait_time', 6000)
        lock_timeout = config.get('lock_timeout', 9000)
        fallback_timeout = config.get('fallback_timeout', 30)  # 事件驱动失败后的轮询超时

        # 创建事件对象用于等待锁释放
        wait_event = threading.Event()

        # 将等待者添加到全局字典
        with threading.Lock():
            self.event_waiters[lock_key] = wait_event

        # 定义回调函数
        lock_released_callback = None
        retry_count = 0

        try:
            # 首先尝试立即获取锁
            if self._try_acquire_lock_immediately(task_name, lock_key, lock_timeout):
                self.lock_stats['event_driven_acquisitions'] += 1
                logger.info(f"任务 {task_name} 通过事件驱动立即获取锁 '{lock_key}'")
                return True

            # 订阅锁释放事件
            def lock_released_callback(released_lock_key, released_by, reason):
                if released_lock_key == lock_key:
                    logger.debug(f"任务 {task_name} 收到锁释放通知: {lock_key} by {released_by} ({reason})")
                    wait_event.set()

            pub_sub_manager.subscribe_to_lock(lock_key, lock_released_callback)

            # 等待锁释放事件或超时
            event_wait_start = time.time()
            while time.time() - start_time < max_wait_time:
                retry_count += 1
                self.lock_stats['total_attempts'] += 1

                # 等待事件触发或超时
                wait_timeout = min(max_wait_time - (time.time() - start_time), fallback_timeout)
                if wait_event.wait(timeout=wait_timeout):
                    # 事件触发，立即尝试获取锁
                    if self._try_acquire_lock_immediately(task_name, lock_key, lock_timeout):
                        self.lock_stats['event_driven_acquisitions'] += 1
                        wait_duration = time.time() - start_time
                        logger.info(f"任务 {task_name} 通过事件驱动获取锁 '{lock_key}' (等待时间: {wait_duration:.2f}秒)")
                        return True
                    else:
                        # 锁被其他任务抢占，继续等待
                        logger.debug(f"任务 {task_name} 事件触发但锁被抢占，继续等待")
                        wait_event.clear()
                else:
                    # 事件等待超时，回退到轮询机制
                    logger.debug(f"任务 {task_name} 事件等待超时，回退到轮询机制")
                    break

            # 回退到轮询机制
            if self._acquire_lock_polling(task_name, lock_key, config, start_time):
                self.lock_stats['polling_acquisitions'] += 1
                return True

            # 超时返回失败
            self.lock_stats['timeouts'] += 1
            wait_duration = time.time() - start_time
            logger.error(f"任务 {task_name} 事件驱动获取锁 '{lock_key}' 超时 (等待时间: {wait_duration:.2f}秒)")
            return False

        finally:
            # 清理资源
            if lock_released_callback:
                pub_sub_manager.unsubscribe_from_lock(lock_key, lock_released_callback)
            with threading.Lock():
                if lock_key in self.event_waiters:
                    del self.event_waiters[lock_key]

    def _acquire_lock_polling(self, task_name: str, lock_key: str, config: Dict[str, Any], start_time: float) -> bool:
        """
        轮询机制的锁获取逻辑

        Args:
            task_name: 任务名称
            lock_key: 锁键
            config: 配置
            start_time: 开始时间

        Returns:
            bool: 是否成功获取锁
        """
        max_wait_time = config.get('max_wait_time', 6000)
        initial_poll_interval = config.get('poll_interval', 1)
        lock_timeout = config.get('lock_timeout', 9000)
        exponential_backoff = config.get('exponential_backoff', True)
        max_poll_interval = config.get('max_poll_interval', 10)

        retry_count = 0
        current_wait_time = initial_poll_interval

        logger.debug(f"任务 {task_name} 使用轮询机制获取锁 '{lock_key}'")

        while time.time() - start_time < max_wait_time:
            retry_count += 1
            self.lock_stats['total_attempts'] += 1

            if self._try_acquire_lock_immediately(task_name, lock_key, lock_timeout):
                self.lock_stats['polling_acquisitions'] += 1
                wait_duration = time.time() - start_time
                logger.info(f"任务 {task_name} 通过轮询获取锁 '{lock_key}' (等待时间: {wait_duration:.2f}秒, 重试次数: {retry_count})")
                return True

            # 计算下一次等待时间
            if exponential_backoff:
                current_wait_time = min(current_wait_time * 1.5, max_poll_interval)
                jitter = random.uniform(0.8, 1.2)
                actual_wait = current_wait_time * jitter
            else:
                actual_wait = initial_poll_interval

            # 记录统计信息
            if retry_count % 10 == 0:
                logger.info(f"任务 {task_name} 已等待 {time.time() - start_time:.1f}秒，重试 {retry_count} 次")

            time.sleep(actual_wait)

        # 超时返回失败
        self.lock_stats['timeouts'] += 1
        wait_duration = time.time() - start_time
        logger.error(f"任务 {task_name} 轮询获取锁 '{lock_key}' 超时 (等待时间: {wait_duration:.2f}秒, 重试次数: {retry_count})")
        return False

    def _try_acquire_lock_immediately(self, task_name: str, lock_key: str, lock_timeout: int) -> bool:
        """
        立即尝试获取锁

        Args:
            task_name: 任务名称
            lock_key: 锁键
            lock_timeout: 锁超时时间

        Returns:
            bool: 是否成功获取锁
        """
        try:
            lock_value = redis_client.get(lock_key)
            if not lock_value:
                # 尝试获取锁
                lock_value = f"locked_by_{task_name}"
                if redis_client.set(lock_key, lock_value, nx=True, ex=lock_timeout):
                    self.lock_stats['successful_acquisitions'] += 1
                    self.lock_stats['last_lock_time'] = time.time()
                    self.lock_stats['last_lock_holder'] = task_name
                    return True
            return False
        except Exception as e:
            logger.error(f"任务 {task_name} 立即获取锁时发生异常: {e}")
            return False

    def _record_lock_history(self, task_name: str, lock_key: str, success: bool, start_time: float):
        """
        记录锁历史

        Args:
            task_name: 任务名称
            lock_key: 锁键
            success: 是否成功
            start_time: 开始时间
        """
        history_entry = {
            'task_name': task_name,
            'lock_key': lock_key,
            'success': success,
            'start_time': start_time,
            'end_time': time.time(),
            'duration': time.time() - start_time
        }

        self.lock_history.append(history_entry)

        # 保持历史记录大小限制
        if len(self.lock_history) > self.max_history_size:
            self.lock_history.pop(0)

    def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal") -> bool:
        """
        释放锁

        Args:
            task_name: 任务名称
            lock_key: 锁键
            release_reason: 释放原因 (normal/timeout/forced)

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
                logger.info(f"任务 {task_name} 释放锁 '{lock_key}' (原值: {lock_value}, 原因: {release_reason})")

                # 发布锁释放事件
                pub_sub_manager.publish_lock_release(lock_key, task_name, release_reason)

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

        # 计算平均执行时间
        if stats['execution_count'] > 0:
            stats['average_execution_time'] = stats['total_execution_time'] / stats['execution_count']
        else:
            stats['average_execution_time'] = 0.0

        # 添加历史统计
        stats['history_size'] = len(self.lock_history)
        stats['recent_success_rate'] = self._calculate_recent_success_rate()

        # 添加事件驱动统计
        total_acquisitions = stats.get('event_driven_acquisitions', 0) + stats.get('polling_acquisitions', 0)
        if total_acquisitions > 0:
            stats['event_driven_rate'] = stats.get('event_driven_acquisitions', 0) / total_acquisitions
            stats['polling_rate'] = stats.get('polling_acquisitions', 0) / total_acquisitions
        else:
            stats['event_driven_rate'] = 0.0
            stats['polling_rate'] = 0.0

        # 添加机制统计
        stats['pub_sub_available'] = pub_sub_manager.pub_sub is not None
        stats['active_waiters'] = len(self.event_waiters)
        stats['pub_sub_subscriptions'] = len(pub_sub_manager.subscribers) if hasattr(pub_sub_manager, 'subscribers') else 0

        return stats

    def _calculate_recent_success_rate(self, window_size: int = 20) -> float:
        """
        计算最近的成功率

        Args:
            window_size: 统计窗口大小

        Returns:
            float: 最近的成功率
        """
        if not self.lock_history:
            return 0.0

        recent_history = self.lock_history[-window_size:]
        successful_attempts = sum(1 for entry in recent_history if entry['success'])
        return successful_attempts / len(recent_history) if recent_history else 0.0

    def get_lock_health(self) -> Dict[str, Any]:
        """
        获取锁健康状态

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        current_time = time.time()
        stats = self.get_statistics()

        # 计算锁持有时间
        lock_age = None
        if self.lock_stats['last_lock_time']:
            lock_age = current_time - self.lock_stats['last_lock_time']

        # 判断健康状态
        health_status = "healthy"
        health_issues = []

        # 检查成功率
        if stats['success_rate'] < 0.8:
            health_status = "warning"
            health_issues.append("低成功率")

        # 检查超时率
        if stats['timeout_rate'] > 0.2:
            health_status = "warning"
            health_issues.append("高超时率")

        # 检查锁持有时间
        if lock_age and lock_age > 3600:  # 超过1小时
            health_status = "critical"
            health_issues.append("锁持有时间过长")

        # 检查最近成功率
        if stats['recent_success_rate'] < 0.7:
            health_status = "warning"
            health_issues.append("最近成功率低")

        return {
            'status': health_status,
            'issues': health_issues,
            'lock_age': lock_age,
            'last_lock_holder': self.lock_stats['last_lock_holder'],
            'statistics': stats,
            'timestamp': current_time
        }

    def get_lock_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取锁历史记录

        Args:
            limit: 返回记录数量限制

        Returns:
            List[Dict[str, Any]]: 历史记录列表
        """
        return self.lock_history[-limit:] if self.lock_history else []

    def record_execution_time(self, execution_time: float):
        """
        记录任务执行时间

        Args:
            execution_time: 执行时间（秒）
        """
        self.lock_stats['total_execution_time'] += execution_time
        self.lock_stats['execution_count'] += 1

    def acquire_lock_with_smart_polling(self, task_name: str, lock_key: str, config: Dict[str, Any]) -> bool:
        """
        使用智能轮询机制获取锁

        Args:
            task_name: 任务名称
            lock_key: 锁键
            config: 轮询配置

        Returns:
            bool: 是否成功获取锁
        """
        start_time = time.time()
        success = self._acquire_lock_internal(task_name, lock_key, config, start_time)

        # 记录锁历史
        self._record_lock_history(task_name, lock_key, success, start_time)

        return success


# 全局锁管理器实例
lock_manager = SmartGpuLockManager()


def gpu_lock(lock_key: str = "gpu_lock:0",
              timeout: int = None,
              poll_interval: int = None,
              max_wait_time: int = None,
              event_driven: bool = None,
              fallback_timeout: int = None):
    """
    GPU锁装饰器 - 事件驱动 + 智能轮询混合机制

    关键设计理念：
    - 优先使用事件驱动机制，提高响应速度
    - 支持轮询回退，确保系统可靠性
    - 详细的统计信息和监控
    - 适当的异常处理和心跳集成

    Args:
        lock_key: 锁键
        timeout: 锁超时时间
        poll_interval: 初始轮询间隔
        max_wait_time: 最大等待时间
        event_driven: 是否使用事件驱动 (None表示使用配置文件设置)
        fallback_timeout: 事件驱动回退超时时间
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
                    'poll_interval': 0.5,
                    'max_wait_time': 300,
                    'lock_timeout': 600,
                    'exponential_backoff': True,
                    'max_poll_interval': 5,
                    'use_event_driven': True,
                    'fallback_timeout': 30
                }

            # 使用传入参数或配置
            actual_timeout = timeout if timeout is not None else config.get('lock_timeout', 600)
            actual_poll_interval = poll_interval if poll_interval is not None else config.get('poll_interval', 0.5)
            actual_max_wait_time = max_wait_time if max_wait_time is not None else config.get('max_wait_time', 300)
            actual_event_driven = event_driven if event_driven is not None else config.get('use_event_driven', True)
            actual_fallback_timeout = fallback_timeout if fallback_timeout is not None else config.get('fallback_timeout', 30)

            # 构建锁配置
            lock_config = {
                'poll_interval': actual_poll_interval,
                'max_wait_time': actual_max_wait_time,
                'lock_timeout': actual_timeout,
                'exponential_backoff': config.get('exponential_backoff', True),
                'max_poll_interval': config.get('max_poll_interval', 5),
                'use_event_driven': actual_event_driven,
                'fallback_timeout': actual_fallback_timeout
            }

            # 确定锁机制
            mechanism = LockMechanism.EVENT_DRIVEN if actual_event_driven else LockMechanism.POLLING
            logger.info(f"任务 {task_name} 开始获取锁 '{lock_key}' (机制: {mechanism.value}, 超时: {actual_max_wait_time}秒)")

            # 使用混合机制获取锁
            if lock_manager.acquire_lock_with_smart_polling(task_name, lock_key, lock_config):
                task_start_time = time.time()
                try:
                    # 成功获取锁，执行任务
                    logger.info(f"任务 {task_name} 开始执行")

                    result = func(self, *args, **kwargs)
                    logger.info(f"任务 {task_name} 执行完成")

                    # 记录执行时间
                    execution_time = time.time() - task_start_time
                    lock_manager.record_execution_time(execution_time)

                    # 记录成功统计
                    stats = lock_manager.get_statistics()
                    logger.info(f"锁统计: 成功率 {stats['success_rate']:.2%}, 事件驱动率 {stats['event_driven_rate']:.2%}, 执行时间: {execution_time:.2f}秒")

                    return result
                except Exception as e:
                    logger.error(f"任务 {task_name} 执行失败: {e}")
                    raise
                finally:
                    # 任务执行完毕，释放锁
                    # GPU显存清理 - 确保任务完成后显存被释放
                    try:
                        from services.common.gpu_memory_manager import log_gpu_memory_state, force_cleanup_gpu_memory
                        log_gpu_memory_state(f"GPU任务完成 - {task_name}")
                        force_cleanup_gpu_memory(aggressive=True)
                        logger.info(f"任务 {task_name} GPU显存清理完成")
                    except Exception as cleanup_e:
                        logger.warning(f"任务 {task_name} GPU显存清理失败: {cleanup_e}")

                    lock_manager.release_lock(task_name, lock_key, "normal")
            else:
                # 获取锁失败，抛出异常
                error_msg = f"任务 {task_name} 无法获取锁 '{lock_key}'，任务放弃执行"
                logger.error(error_msg)

                # 获取统计信息
                stats = lock_manager.get_statistics()
                logger.error(f"当前锁统计: 总尝试 {stats['total_attempts']}, 成功 {stats['successful_acquisitions']}, 超时 {stats['timeouts']}")
                logger.error(f"机制统计: 事件驱动 {stats.get('event_driven_acquisitions', 0)}, 轮询 {stats.get('polling_acquisitions', 0)}")

                # 获取锁失败时也要清理可能的显存残留
                try:
                    from services.common.gpu_memory_manager import force_cleanup_gpu_memory
                    force_cleanup_gpu_memory(aggressive=True)
                    logger.info(f"任务 {task_name} 获取锁失败，GPU显存已清理")
                except:
                    pass

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

        # 获取锁健康状态
        health = lock_manager.get_lock_health()

        # 计算锁的详细信息
        lock_info = {
            "lock_key": lock_key,
            "is_locked": lock_value is not None,
            "lock_holder": lock_value,
            "ttl_seconds": ttl if ttl > 0 else None,
            "timestamp": time.time(),
            "health": health,
            "statistics": lock_manager.get_statistics(),
            "recent_history": lock_manager.get_lock_history(limit=5)
        }

        # 添加锁的元信息
        if lock_value:
            lock_info["lock_type"] = "active"
            lock_info["lock_age"] = health.get("lock_age")
        else:
            lock_info["lock_type"] = "free"

        return lock_info

    except Exception as e:
        logger.error(f"获取锁状态失败: {e}")
        return {"error": str(e)}

def get_gpu_lock_health_summary() -> Dict[str, Any]:
    """
    获取GPU锁健康状态摘要

    Returns:
        Dict[str, Any]: 健康状态摘要
    """
    if not redis_client:
        return {"error": "Redis客户端未初始化"}

    try:
        health = lock_manager.get_lock_health()
        stats = lock_manager.get_statistics()

        # 计算关键指标
        summary = {
            "overall_status": health["status"],
            "issues_count": len(health["issues"]),
            "total_attempts": stats["total_attempts"],
            "success_rate": stats["success_rate"],
            "timeout_rate": stats["timeout_rate"],
            "average_execution_time": stats.get("average_execution_time", 0),
            "recent_success_rate": stats.get("recent_success_rate", 0),
            "lock_holder": health.get("last_lock_holder"),
            "lock_age": health.get("lock_age"),
            "timestamp": time.time()
        }

        return summary

    except Exception as e:
        logger.error(f"获取锁健康摘要失败: {e}")
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