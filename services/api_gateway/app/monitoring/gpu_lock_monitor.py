# services/api_gateway/app/monitoring/gpu_lock_monitor.py
# -*- coding: utf-8 -*-

"""
GPU锁监控器

提供主动监控GPU锁状态、检测死锁、自动恢复等功能。
"""

import os
import time
import threading
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from redis import Redis
from services.common.config_loader import get_gpu_lock_monitor_config
from services.common.locks import lock_manager, get_gpu_lock_status, get_gpu_lock_health_summary
from services.common.logger import get_logger

logger = get_logger('gpu_lock_monitor')


class GPULockMonitor:
    """GPU锁监控器 - 主动监控和自动恢复"""

    def __init__(self):
        self.running = False
        self.monitor_thread = None
        self.config = get_gpu_lock_monitor_config()
        self.redis_client = self._init_redis_client()

        # 监控统计
        self.monitor_stats = {
            'total_checks': 0,
            'warning_count': 0,
            'soft_timeout_count': 0,
            'hard_timeout_count': 0,
            'successful_recoveries': 0,
            'start_time': time.time(),
            'last_check_time': None
        }

        # 监控状态
        self.monitor_status = {
            'status': 'stopped',
            'last_error': None,
            'last_recovery_time': None,
            'healthy_checks': 0,
            'unhealthy_checks': 0
        }

    def _init_redis_client(self) -> Optional[Redis]:
        """初始化Redis客户端"""
        try:
            from services.common.config_loader import get_redis_config
            
            redis_config = get_redis_config()
            redis_host = redis_config['host']
            redis_port = redis_config['port']
            redis_db = int(os.environ.get('REDIS_LOCK_DB', 2))

            client = Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
            client.ping()
            logger.info(f"GPU锁监控器成功连接到Redis at {redis_host}:{redis_port}/{redis_db}")
            return client
        except ValueError as e:
            logger.error(f"Redis配置错误: {e}")
            return None
        except Exception as e:
            logger.error(f"GPU锁监控器无法连接到Redis: {e}")
            return None

    def start_monitoring(self):
        """启动监控线程"""
        if not self.config.get('enabled', True):
            logger.info("GPU锁监控功能已禁用")
            return

        if self.running:
            logger.warning("GPU锁监控器已在运行中")
            return

        if not self.redis_client:
            logger.error("Redis客户端未初始化，无法启动监控")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("GPU锁监控器已启动")

    def stop_monitoring(self):
        """停止监控线程"""
        if not self.running:
            return

        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        self.monitor_status['status'] = 'stopped'
        logger.info("GPU锁监控器已停止")

    def _monitor_loop(self):
        """监控主循环"""
        logger.info("GPU锁监控循环开始")

        while self.running:
            try:
                # 更新监控状态
                self.monitor_status['status'] = 'running'

                # 执行监控检查
                self._perform_monitoring_check()

                # 更新统计信息
                self.monitor_stats['total_checks'] += 1
                self.monitor_stats['last_check_time'] = time.time()

                # 等待下一次检查
                monitor_interval = self.config.get('monitor_interval', 30)
                time.sleep(monitor_interval)

            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                self.monitor_status['last_error'] = str(e)
                self.monitor_status['status'] = 'error'
                time.sleep(60)  # 异常情况下等待更长时间

        logger.info("GPU锁监控循环结束")

    def _perform_monitoring_check(self):
        """执行一次完整的监控检查"""
        try:
            # 获取GPU锁状态
            lock_status = get_gpu_lock_status()

            if 'error' in lock_status:
                logger.error(f"获取锁状态失败: {lock_status['error']}")
                return

            # 检查锁的健康状态
            health_info = lock_status.get('health', {})
            if health_info.get('status') == 'healthy':
                self.monitor_status['healthy_checks'] += 1
                return

            self.monitor_status['unhealthy_checks'] += 1

            # 处理不健康的锁状态
            self._handle_unhealthy_lock(lock_status, health_info)

        except Exception as e:
            logger.error(f"监控检查失败: {e}")

    def _handle_unhealthy_lock(self, lock_status: Dict[str, Any], health_info: Dict[str, Any]):
        """处理不健康的锁状态"""
        issues = health_info.get('issues', [])
        lock_age = health_info.get('lock_age')

        if not issues:
            return

        logger.warning(f"检测到GPU锁健康问题: {issues}")

        # 根据锁年龄和问题类型进行分级处理
        if lock_age and lock_age > 0:
            timeout_levels = self.config.get('timeout_levels', {})
            warning_threshold = timeout_levels.get('warning', 1800)
            soft_timeout_threshold = timeout_levels.get('soft_timeout', 3600)
            hard_timeout_threshold = timeout_levels.get('hard_timeout', 7200)

            if lock_age >= hard_timeout_threshold:
                self._handle_hard_timeout(lock_status)
            elif lock_age >= soft_timeout_threshold:
                self._handle_soft_timeout(lock_status)
            elif lock_age >= warning_threshold:
                self._handle_warning(lock_status)

    def _handle_warning(self, lock_status: Dict[str, Any]):
        """处理警告级别的锁问题"""
        self.monitor_stats['warning_count'] += 1
        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_age = lock_status.get('lock_age', 0)

        logger.warning(f"GPU锁警告: 锁持有者 {lock_holder} 持有锁时间过长 ({lock_age:.0f}秒)")

        # 这里可以添加通知逻辑，如发送告警邮件或消息

    def _handle_soft_timeout(self, lock_status: Dict[str, Any]):
        """处理软超时"""
        self.monitor_stats['soft_timeout_count'] += 1
        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')
        lock_age = lock_status.get('lock_age', 0)

        logger.warning(f"GPU锁软超时: 锁持有者 {lock_holder} 持有锁时间过长 ({lock_age:.0f}秒)")

        # 尝试优雅终止任务
        if self.config.get('auto_recovery', True):
            success = self._attempt_graceful_termination(lock_key, lock_holder)
            if success:
                self.monitor_stats['successful_recoveries'] += 1
                self.monitor_status['last_recovery_time'] = time.time()

    def _handle_hard_timeout(self, lock_status: Dict[str, Any]):
        """处理硬超时"""
        self.monitor_stats['hard_timeout_count'] += 1
        lock_holder = lock_status.get('lock_holder', 'unknown')
        lock_key = lock_status.get('lock_key', 'gpu_lock:0')
        lock_age = lock_status.get('lock_age', 0)

        logger.error(f"GPU锁硬超时: 锁持有者 {lock_holder} 持有锁时间过长 ({lock_age:.0f}秒)，准备强制释放")

        # 强制释放锁
        if self.config.get('auto_recovery', True):
            success = self._force_release_lock(lock_key)
            if success:
                self.monitor_stats['successful_recoveries'] += 1
                self.monitor_status['last_recovery_time'] = time.time()
                logger.info(f"成功强制释放GPU锁 {lock_key}")

    def _attempt_graceful_termination(self, lock_key: str, lock_holder: str) -> bool:
        """尝试优雅终止任务"""
        try:
            # 检查任务是否还有心跳
            heartbeat_key = f"task_heartbeat:{lock_holder}"
            if self.redis_client:
                heartbeat_exists = self.redis_client.exists(heartbeat_key)
                if heartbeat_exists:
                    logger.info(f"任务 {lock_holder} 仍有心跳，尝试发送终止信号")
                    # 这里可以添加向任务发送终止信号的逻辑
                    # 例如通过消息队列或信号机制
                    return False
                else:
                    logger.info(f"任务 {lock_holder} 无心跳，准备释放锁")
                    return self._force_release_lock(lock_key)

            return False

        except Exception as e:
            logger.error(f"优雅终止失败: {e}")
            return False

    def _force_release_lock(self, lock_key: str) -> bool:
        """强制释放锁"""
        try:
            if not self.redis_client:
                return False

            # 获取当前锁信息
            lock_value = self.redis_client.get(lock_key)
            if lock_value:
                # 记录释放前的状态
                logger.info(f"强制释放锁 {lock_key} (持有者: {lock_value})")

                # 删除锁
                result = self.redis_client.delete(lock_key)
                if result:
                    logger.info(f"成功释放锁 {lock_key}")
                    return True
                else:
                    logger.error(f"释放锁 {lock_key} 失败")
                    return False
            else:
                logger.info(f"锁 {lock_key} 已不存在")
                return True

        except Exception as e:
            logger.error(f"强制释放锁异常: {e}")
            return False

    def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控器状态"""
        return {
            'monitor_status': self.monitor_status,
            'monitor_stats': self.monitor_stats,
            'config': self.config,
            'is_running': self.running,
            'uptime': time.time() - self.monitor_stats['start_time'] if self.running else 0
        }

    def get_monitor_health(self) -> Dict[str, Any]:
        """获取监控器健康状态"""
        stats = self.monitor_stats

        # 计算健康指标
        total_checks = stats['total_checks']
        if total_checks > 0:
            healthy_rate = self.monitor_status['healthy_checks'] / total_checks
            recovery_rate = stats['successful_recoveries'] / (stats['soft_timeout_count'] + stats['hard_timeout_count'] + 1)
        else:
            healthy_rate = 0.0
            recovery_rate = 0.0

        # 判断健康状态
        health_status = 'healthy'
        issues = []

        if not self.running:
            health_status = 'stopped'
            issues.append('监控器已停止')
        elif self.monitor_status['status'] == 'error':
            health_status = 'error'
            issues.append(f'监控器错误: {self.monitor_status.get("last_error", "未知错误")}')
        elif healthy_rate < 0.9:
            health_status = 'warning'
            issues.append(f'健康检查成功率低: {healthy_rate:.2%}')

        return {
            'status': health_status,
            'issues': issues,
            'metrics': {
                'total_checks': total_checks,
                'healthy_rate': healthy_rate,
                'recovery_rate': recovery_rate,
                'warning_count': stats['warning_count'],
                'timeout_count': stats['soft_timeout_count'] + stats['hard_timeout_count'],
                'successful_recoveries': stats['successful_recoveries']
            },
            'timestamp': time.time()
        }


# 全局监控器实例
gpu_monitor = None


def get_gpu_monitor() -> GPULockMonitor:
    """获取全局GPU锁监控器实例"""
    global gpu_monitor
    if gpu_monitor is None:
        gpu_monitor = GPULockMonitor()
    return gpu_monitor


def start_gpu_monitoring():
    """启动GPU锁监控"""
    monitor = get_gpu_monitor()
    monitor.start_monitoring()


def stop_gpu_monitoring():
    """停止GPU锁监控"""
    monitor = get_gpu_monitor()
    monitor.stop_monitoring()