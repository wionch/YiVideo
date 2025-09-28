# services/api_gateway/app/monitoring/timeout_manager.py
# -*- coding: utf-8 -*-

"""
超时管理器

实现分级超时处理机制，包括警告、软超时和硬超时三个级别。
"""

import os
import time
import logging
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum

from services.common.config_loader import get_gpu_lock_monitor_config
from services.common.locks import lock_manager, get_gpu_lock_status
from services.common.logger import get_logger
from .heartbeat_manager import get_heartbeat_manager

logger = get_logger('timeout_manager')


class TimeoutLevel(Enum):
    """超时级别枚举"""
    WARNING = "warning"        # 警告级别
    SOFT_TIMEOUT = "soft_timeout"  # 软超时
    HARD_TIMEOUT = "hard_timeout"  # 硬超时


class TimeoutAction:
    """超时处理动作"""

    def __init__(self, level: TimeoutLevel, threshold: int, action_func: Callable, name: str):
        self.level = level
        self.threshold = threshold  # 阈值（秒）
        self.action_func = action_func
        self.name = name
        self.last_executed = None

    def should_execute(self, lock_age: float) -> bool:
        """判断是否应该执行该动作"""
        return lock_age >= self.threshold

    def execute(self, lock_status: Dict[str, Any]) -> bool:
        """执行超时处理动作"""
        try:
            self.last_executed = time.time()
            return self.action_func(lock_status)
        except Exception as e:
            logger.error(f"执行超时动作 {self.name} 失败: {e}")
            return False


class TimeoutManager:
    """超时管理器 - 分级超时处理"""

    def __init__(self):
        self.config = get_gpu_lock_monitor_config()
        self.timeout_actions: List[TimeoutAction] = []
        self.timeout_stats = {
            'warning_actions': 0,
            'soft_timeout_actions': 0,
            'hard_timeout_actions': 0,
            'successful_actions': 0,
            'failed_actions': 0,
            'start_time': time.time()
        }
        self.action_history = []
        self.max_history_size = 100

        self._initialize_timeout_actions()

    def _initialize_timeout_actions(self):
        """初始化超时处理动作"""
        timeout_levels = self.config.get('timeout_levels', {})

        # 警告级别动作
        warning_threshold = timeout_levels.get('warning', 1800)
        self.timeout_actions.append(TimeoutAction(
            level=TimeoutLevel.WARNING,
            threshold=warning_threshold,
            action_func=self._handle_warning_timeout,
            name="warning_action"
        ))

        # 软超时级别动作
        soft_timeout_threshold = timeout_levels.get('soft_timeout', 3600)
        self.timeout_actions.append(TimeoutAction(
            level=TimeoutLevel.SOFT_TIMEOUT,
            threshold=soft_timeout_threshold,
            action_func=self._handle_soft_timeout,
            name="soft_timeout_action"
        ))

        # 硬超时级别动作
        hard_timeout_threshold = timeout_levels.get('hard_timeout', 7200)
        self.timeout_actions.append(TimeoutAction(
            level=TimeoutLevel.HARD_TIMEOUT,
            threshold=hard_timeout_threshold,
            action_func=self._handle_hard_timeout,
            name="hard_timeout_action"
        ))

        logger.info(f"初始化超时处理动作: 警告({warning_threshold}s), 软超时({soft_timeout_threshold}s), 硬超时({hard_timeout_threshold}s)")

    def check_and_handle_timeouts(self, lock_key: str = "gpu_lock:0") -> Dict[str, Any]:
        """检查并处理超时"""
        try:
            # 获取锁状态
            lock_status = get_gpu_lock_status(lock_key)
            if 'error' in lock_status:
                logger.error(f"获取锁状态失败: {lock_status['error']}")
                return {'error': lock_status['error']}

            # 检查锁是否被持有
            if not lock_status.get('is_locked', False):
                return {'status': 'no_lock', 'message': '锁未被持有'}

            # 获取锁年龄
            health_info = lock_status.get('health', {})
            lock_age = health_info.get('lock_age')
            if lock_age is None:
                return {'error': '无法获取锁年龄'}

            # 处理超时
            return self._process_timeout_actions(lock_status, lock_age)

        except Exception as e:
            logger.error(f"检查超时失败: {e}")
            return {'error': str(e)}

    def _process_timeout_actions(self, lock_status: Dict[str, Any], lock_age: float) -> Dict[str, Any]:
        """处理超时动作"""
        results = {
            'lock_key': lock_status.get('lock_key'),
            'lock_age': lock_age,
            'actions_executed': [],
            'successful_actions': 0,
            'failed_actions': 0
        }

        # 按阈值从小到大处理
        sorted_actions = sorted(self.timeout_actions, key=lambda x: x.threshold)

        for action in sorted_actions:
            if action.should_execute(lock_age):
                logger.info(f"执行超时动作: {action.name} (锁年龄: {lock_age:.0f}s, 阈值: {action.threshold}s)")

                # 执行动作
                success = action.execute(lock_status)

                # 记录结果
                action_result = {
                    'action_name': action.name,
                    'level': action.level.value,
                    'threshold': action.threshold,
                    'success': success,
                    'timestamp': time.time()
                }
                results['actions_executed'].append(action_result)

                # 更新统计
                self._update_action_stats(action.level, success)

                # 记录历史
                self._record_action_history(action_result)

                if success:
                    results['successful_actions'] += 1
                else:
                    results['failed_actions'] += 1

                # 如果是硬超时且成功，可能需要特殊处理
                if action.level == TimeoutLevel.HARD_TIMEOUT and success:
                    results['lock_released'] = True

        return results

    def _handle_warning_timeout(self, lock_status: Dict[str, Any]) -> bool:
        """处理警告级别超时"""
        self.timeout_stats['warning_actions'] += 1

        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_age = lock_status.get('lock_age', 0)
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')

        logger.warning(f"GPU锁警告: 锁 {lock_key} 被 {lock_holder} 持有时间过长 ({lock_age:.0f}s)")

        # 发送警告通知
        self._send_warning_notification(lock_status)

        return True

    def _handle_soft_timeout(self, lock_status: Dict[str, Any]) -> bool:
        """处理软超时"""
        self.timeout_stats['soft_timeout_actions'] += 1

        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_age = lock_status.get('lock_age', 0)
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')

        logger.warning(f"GPU锁软超时: 锁 {lock_key} 被 {lock_holder} 持有时间过长 ({lock_age:.0f}s)")

        # 尝试优雅终止
        success = self._attempt_graceful_termination(lock_status)

        if success:
            logger.info(f"成功优雅终止任务 {lock_holder}")
        else:
            logger.warning(f"优雅终止任务 {lock_holder} 失败")

        return success

    def _handle_hard_timeout(self, lock_status: Dict[str, Any]) -> bool:
        """处理硬超时"""
        self.timeout_stats['hard_timeout_actions'] += 1

        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_age = lock_status.get('lock_age', 0)
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')

        logger.error(f"GPU锁硬超时: 锁 {lock_key} 被 {lock_holder} 持有时间过长 ({lock_age:.0f}s)，准备强制释放")

        # 强制释放锁
        success = self._force_release_lock(lock_key)

        if success:
            logger.info(f"成功强制释放锁 {lock_key}")
        else:
            logger.error(f"强制释放锁 {lock_key} 失败")

        return success

    def _attempt_graceful_termination(self, lock_status: Dict[str, Any]) -> bool:
        """尝试优雅终止任务"""
        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')

        # 检查任务心跳
        heartbeat_manager = get_heartbeat_manager()
        heartbeat_info = heartbeat_manager.check_task_heartbeat(lock_holder)

        if 'error' in heartbeat_info:
            logger.error(f"检查任务心跳失败: {heartbeat_info['error']}")
            return False

        if heartbeat_info.get('heartbeat_exists', False):
            logger.info(f"任务 {lock_holder} 仍有心跳，尝试发送终止信号")

            # 这里可以实现具体的终止逻辑
            # 例如：通过消息队列发送终止信号
            # 或者通过系统信号终止进程
            return self._send_termination_signal(lock_holder)
        else:
            logger.info(f"任务 {lock_holder} 无心跳，直接释放锁")
            return self._force_release_lock(lock_key)

    def _send_termination_signal(self, task_id: str) -> bool:
        """发送终止信号"""
        # 这里可以实现具体的终止逻辑
        # 例如：
        # 1. 通过Celery发送任务终止信号
        # 2. 通过系统信号终止进程
        # 3. 通过消息队列通知任务停止

        logger.info(f"向任务 {task_id} 发送终止信号")

        # 暂时返回True，实际实现需要根据具体任务执行机制
        # 这里只是一个框架
        return True

    def _force_release_lock(self, lock_key: str) -> bool:
        """强制释放锁"""
        try:
            # 使用锁管理器的强制释放功能
            return lock_manager.release_lock("timeout_manager", lock_key)
        except Exception as e:
            logger.error(f"强制释放锁失败: {e}")
            return False

    def _send_warning_notification(self, lock_status: Dict[str, Any]):
        """发送警告通知"""
        # 这里可以实现具体的警告通知逻辑
        # 例如：发送邮件、短信、Webhook等

        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_age = lock_status.get('lock_age', 0)
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')

        message = f"GPU锁警告: 锁 {lock_key} 被 {lock_holder} 持有时间过长 ({lock_age:.0f}s)"
        logger.warning(message)

        # 可以集成到现有的告警系统中
        # self._send_alert_email(message)
        # self._send_alert_webhook(message)

    def _update_action_stats(self, level: TimeoutLevel, success: bool):
        """更新动作统计"""
        if success:
            self.timeout_stats['successful_actions'] += 1
        else:
            self.timeout_stats['failed_actions'] += 1

    def _record_action_history(self, action_result: Dict[str, Any]):
        """记录动作历史"""
        self.action_history.append(action_result)

        # 保持历史记录大小限制
        if len(self.action_history) > self.max_history_size:
            self.action_history.pop(0)

    def get_timeout_status(self) -> Dict[str, Any]:
        """获取超时状态"""
        return {
            'timeout_stats': self.timeout_stats,
            'action_history': self.action_history[-10:],  # 最近10条记录
            'configured_actions': [
                {
                    'name': action.name,
                    'level': action.level.value,
                    'threshold': action.threshold,
                    'last_executed': action.last_executed
                }
                for action in self.timeout_actions
            ],
            'timestamp': time.time()
        }

    def get_timeout_config(self) -> Dict[str, Any]:
        """获取超时配置"""
        return self.config.get('timeout_levels', {})

    def update_config(self):
        """更新配置"""
        self.config = get_gpu_lock_monitor_config()
        self._initialize_timeout_actions()
        logger.info("超时管理器配置已更新")


# 全局超时管理器实例
timeout_manager = None


def get_timeout_manager() -> TimeoutManager:
    """获取全局超时管理器实例"""
    global timeout_manager
    if timeout_manager is None:
        timeout_manager = TimeoutManager()
    return timeout_manager


def check_lock_timeouts(lock_key: str = "gpu_lock:0") -> Dict[str, Any]:
    """检查锁超时"""
    manager = get_timeout_manager()
    return manager.check_and_handle_timeouts(lock_key)