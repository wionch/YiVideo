# services/api_gateway/app/monitoring/heartbeat_manager.py
# -*- coding: utf-8 -*-

"""
任务心跳管理器

管理任务的心跳检测，用于监控任务状态和检测任务崩溃。
"""

import os
import time
import threading
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta

from redis import Redis
from services.common.config_loader import get_gpu_lock_monitor_config
from services.common.logger import get_logger

logger = get_logger('heartbeat_manager')


class TaskHeartbeat:
    """单个任务的心跳管理"""

    def __init__(self, task_id: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.config = config
        self.redis_client = self._init_redis_client()
        self.heartbeat_key = f"task_heartbeat:{task_id}"
        self.running = False
        self.heartbeat_thread = None
        self.last_heartbeat_time = None

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
            return client
        except ValueError as e:
            logger.error(f"Redis配置错误: {e}")
            return None
        except Exception as e:
            logger.error(f"任务 {self.task_id} 无法连接到Redis: {e}")
            return None

    def start_heartbeat(self):
        """启动心跳线程"""
        if not self.redis_client:
            logger.error(f"任务 {self.task_id} Redis客户端未初始化，无法启动心跳")
            return

        if self.running:
            logger.warning(f"任务 {self.task_id} 心跳已在运行中")
            return

        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logger.info(f"任务 {self.task_id} 心跳已启动")

    def stop_heartbeat(self):
        """停止心跳线程"""
        if not self.running:
            return

        self.running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)

        # 清理心跳记录
        self._cleanup_heartbeat()
        logger.info(f"任务 {self.task_id} 心跳已停止")

    def _heartbeat_loop(self):
        """心跳循环"""
        logger.info(f"任务 {self.task_id} 心跳循环开始")

        heartbeat_interval = self.config.get('heartbeat', {}).get('interval', 60)
        heartbeat_timeout = self.config.get('heartbeat', {}).get('timeout', 300)

        while self.running:
            try:
                # 更新心跳
                current_time = time.time()
                self._update_heartbeat(current_time)
                self.last_heartbeat_time = current_time

                # 等待下一次心跳
                time.sleep(heartbeat_interval)

            except Exception as e:
                logger.error(f"任务 {self.task_id} 心跳更新失败: {e}")
                time.sleep(30)  # 异常情况下等待更长时间

        logger.info(f"任务 {self.task_id} 心跳循环结束")

    def _update_heartbeat(self, timestamp: float):
        """更新心跳记录"""
        if not self.redis_client:
            return

        try:
            heartbeat_timeout = self.config.get('heartbeat', {}).get('timeout', 300)
            heartbeat_data = {
                'task_id': self.task_id,
                'timestamp': timestamp,
                'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                'status': 'running'
            }

            # 设置心跳记录，带过期时间
            self.redis_client.setex(
                self.heartbeat_key,
                heartbeat_timeout,
                str(heartbeat_data)
            )

        except Exception as e:
            logger.error(f"任务 {self.task_id} 更新心跳失败: {e}")

    def _cleanup_heartbeat(self):
        """清理心跳记录"""
        if not self.redis_client:
            return

        try:
            self.redis_client.delete(self.heartbeat_key)
        except Exception as e:
            logger.error(f"任务 {self.task_id} 清理心跳失败: {e}")

    def is_alive(self) -> bool:
        """检查心跳是否活跃"""
        if not self.redis_client:
            return False

        try:
            heartbeat_exists = self.redis_client.exists(self.heartbeat_key)
            return heartbeat_exists > 0
        except Exception as e:
            logger.error(f"任务 {self.task_id} 检查心跳状态失败: {e}")
            return False

    def get_heartbeat_info(self) -> Dict[str, Any]:
        """获取心跳信息"""
        if not self.redis_client:
            return {'error': 'Redis客户端未初始化'}

        try:
            heartbeat_data = self.redis_client.get(self.heartbeat_key)
            if heartbeat_data:
                return {
                    'task_id': self.task_id,
                    'heartbeat_exists': True,
                    'heartbeat_data': eval(heartbeat_data),  # 注意：实际应该用JSON解析
                    'last_update': self.last_heartbeat_time,
                    'is_running': self.running
                }
            else:
                return {
                    'task_id': self.task_id,
                    'heartbeat_exists': False,
                    'is_running': self.running
                }
        except Exception as e:
            logger.error(f"任务 {self.task_id} 获取心跳信息失败: {e}")
            return {'error': str(e)}


class TaskHeartbeatManager:
    """任务心跳管理器 - 管理所有任务的心跳"""

    def __init__(self):
        self.config = get_gpu_lock_monitor_config()
        self.redis_client = self._init_redis_client()
        self.active_heartbeats: Dict[str, TaskHeartbeat] = {}
        self.heartbeat_stats = {
            'total_tasks': 0,
            'active_tasks': 0,
            'dead_tasks': 0,
            'heartbeat_failures': 0,
            'start_time': time.time()
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
            logger.info("任务心跳管理器成功连接到Redis")
            return client
        except ValueError as e:
            logger.error(f"Redis配置错误: {e}")
            return None
        except Exception as e:
            logger.error(f"任务心跳管理器无法连接到Redis: {e}")
            return None

    def register_task(self, task_id: str) -> Optional[TaskHeartbeat]:
        """注册任务并启动心跳"""
        if task_id in self.active_heartbeats:
            logger.warning(f"任务 {task_id} 已注册")
            return self.active_heartbeats[task_id]

        try:
            heartbeat = TaskHeartbeat(task_id, self.config)
            heartbeat.start_heartbeat()
            self.active_heartbeats[task_id] = heartbeat
            self.heartbeat_stats['total_tasks'] += 1
            self.heartbeat_stats['active_tasks'] += 1

            logger.info(f"任务 {task_id} 已注册并启动心跳")
            return heartbeat

        except Exception as e:
            logger.error(f"注册任务 {task_id} 失败: {e}")
            self.heartbeat_stats['heartbeat_failures'] += 1
            return None

    def unregister_task(self, task_id: str):
        """注销任务并停止心跳"""
        if task_id not in self.active_heartbeats:
            logger.warning(f"任务 {task_id} 未注册")
            return

        try:
            heartbeat = self.active_heartbeats[task_id]
            heartbeat.stop_heartbeat()
            del self.active_heartbeats[task_id]
            self.heartbeat_stats['active_tasks'] = max(0, self.heartbeat_stats['active_tasks'] - 1)

            logger.info(f"任务 {task_id} 已注销并停止心跳")

        except Exception as e:
            logger.error(f"注销任务 {task_id} 失败: {e}")

    def check_task_heartbeat(self, task_id: str) -> Dict[str, Any]:
        """检查单个任务的心跳状态"""
        if task_id in self.active_heartbeats:
            return self.active_heartbeats[task_id].get_heartbeat_info()
        else:
            # 检查是否有遗留的心跳记录
            if self.redis_client:
                heartbeat_key = f"task_heartbeat:{task_id}"
                heartbeat_exists = self.redis_client.exists(heartbeat_key)
                if heartbeat_exists:
                    return {
                        'task_id': task_id,
                        'heartbeat_exists': True,
                        'is_registered': False,
                        'status': 'orphaned'
                    }

            return {
                'task_id': task_id,
                'heartbeat_exists': False,
                'is_registered': False,
                'status': 'not_found'
            }

    def check_all_heartbeats(self) -> Dict[str, Any]:
        """检查所有任务的心跳状态"""
        results = {
            'active_tasks': {},
            'dead_tasks': [],
            'orphaned_tasks': [],
            'statistics': self.heartbeat_stats.copy(),
            'timestamp': time.time()
        }

        # 检查活跃任务
        dead_tasks = []
        for task_id, heartbeat in self.active_heartbeats.items():
            heartbeat_info = heartbeat.get_heartbeat_info()
            results['active_tasks'][task_id] = heartbeat_info

            if not heartbeat.is_alive():
                dead_tasks.append(task_id)

        results['dead_tasks'] = dead_tasks

        # 检查孤立的心跳记录
        if self.redis_client:
            try:
                # 获取所有心跳键
                heartbeat_keys = self.redis_client.keys("task_heartbeat:*")
                for key in heartbeat_keys:
                    task_id = key.replace("task_heartbeat:", "")
                    if task_id not in self.active_heartbeats:
                        results['orphaned_tasks'].append(task_id)
            except Exception as e:
                logger.error(f"检查孤立心跳记录失败: {e}")

        return results

    def cleanup_dead_tasks(self):
        """清理死任务"""
        dead_tasks = []
        for task_id, heartbeat in self.active_heartbeats.items():
            if not heartbeat.is_alive():
                dead_tasks.append(task_id)

        for task_id in dead_tasks:
            logger.warning(f"清理死任务: {task_id}")
            self.unregister_task(task_id)
            self.heartbeat_stats['dead_tasks'] += 1

    def cleanup_orphaned_heartbeats(self):
        """清理孤立的心跳记录"""
        if not self.redis_client:
            return

        try:
            # 获取所有心跳键
            heartbeat_keys = self.redis_client.keys("task_heartbeat:*")
            cleaned_count = 0

            for key in heartbeat_keys:
                task_id = key.replace("task_heartbeat:", "")
                if task_id not in self.active_heartbeats:
                    self.redis_client.delete(key)
                    cleaned_count += 1
                    logger.info(f"清理孤立心跳记录: {key}")

            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个孤立心跳记录")

        except Exception as e:
            logger.error(f"清理孤立心跳记录失败: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取心跳统计信息"""
        stats = self.heartbeat_stats.copy()
        stats['current_active_tasks'] = len(self.active_heartbeats)
        stats['uptime'] = time.time() - stats['start_time']

        # 计算故障率
        if stats['total_tasks'] > 0:
            stats['failure_rate'] = stats['dead_tasks'] / stats['total_tasks']
        else:
            stats['failure_rate'] = 0.0

        return stats

    def shutdown(self):
        """关闭心跳管理器"""
        logger.info("关闭任务心跳管理器")

        # 停止所有心跳
        for task_id, heartbeat in list(self.active_heartbeats.items()):
            try:
                heartbeat.stop_heartbeat()
            except Exception as e:
                logger.error(f"停止任务 {task_id} 心跳失败: {e}")

        self.active_heartbeats.clear()
        logger.info("任务心跳管理器已关闭")


# 全局心跳管理器实例
heartbeat_manager = None


def get_heartbeat_manager() -> TaskHeartbeatManager:
    """获取全局心跳管理器实例"""
    global heartbeat_manager
    if heartbeat_manager is None:
        heartbeat_manager = TaskHeartbeatManager()
    return heartbeat_manager


def start_task_heartbeat(task_id: str) -> Optional[TaskHeartbeat]:
    """启动任务心跳"""
    manager = get_heartbeat_manager()
    return manager.register_task(task_id)


def stop_task_heartbeat(task_id: str):
    """停止任务心跳"""
    manager = get_heartbeat_manager()
    manager.unregister_task(task_id)