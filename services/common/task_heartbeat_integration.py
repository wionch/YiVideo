# services/common/task_heartbeat_integration.py
# -*- coding: utf-8 -*-

"""
任务心跳集成模块

为PaddleOCR和FFmpeg等服务提供心跳集成功能，与GPU锁监控系统配合使用。
"""

import time
import threading
from typing import Optional, Dict, Any
from services.common.logger import get_logger

logger = get_logger('task_heartbeat_integration')

# 全局心跳管理器实例
_heartbeat_manager = None


def get_heartbeat_manager():
    """获取心跳管理器实例"""
    global _heartbeat_manager
    if _heartbeat_manager is None:
        try:
            from services.api_gateway.app.monitoring.heartbeat_manager import TaskHeartbeatManager
            _heartbeat_manager = TaskHeartbeatManager()
            logger.info("心跳管理器初始化成功")
        except ImportError:
            logger.warning("无法导入心跳管理器，心跳功能将被禁用")
            _heartbeat_manager = None
    return _heartbeat_manager


class TaskHeartbeatIntegration:
    """任务心跳集成类"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.heartbeat_manager = get_heartbeat_manager()
        self._heartbeat_thread = None
        self._should_stop = False
        self._heartbeat_interval = 30  # 30秒心跳间隔

    def start_heartbeat(self):
        """启动心跳线程"""
        if self.heartbeat_manager is None:
            logger.warning(f"任务 {self.task_id}: 心跳管理器不可用，跳过心跳启动")
            return

        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            logger.warning(f"任务 {self.task_id}: 心跳线程已在运行")
            return

        self._should_stop = False
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker,
            name=f"Heartbeat-{self.task_id}",
            daemon=True
        )
        self._heartbeat_thread.start()
        logger.info(f"任务 {self.task_id}: 心跳线程已启动")

    def stop_heartbeat(self):
        """停止心跳线程"""
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._should_stop = True
            self._heartbeat_thread.join(timeout=5)
            logger.info(f"任务 {self.task_id}: 心跳线程已停止")

    def _heartbeat_worker(self):
        """心跳工作线程"""
        logger.info(f"任务 {self.task_id}: 心跳工作线程开始运行")

        while not self._should_stop:
            try:
                # 更新心跳
                if self.heartbeat_manager:
                    heartbeat_key = f"task_heartbeat:{self.task_id}"
                    if hasattr(self.heartbeat_manager, 'redis_client') and self.heartbeat_manager.redis_client:
                        # 直接使用Redis更新心跳
                        self.heartbeat_manager.redis_client.setex(
                            heartbeat_key,
                            120,  # 2分钟TTL
                            f"active_{int(time.time())}"
                        )
                    else:
                        logger.warning(f"任务 {self.task_id}: Redis客户端不可用")

                # 等待下一次心跳
                for _ in range(self._heartbeat_interval):
                    if self._should_stop:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"任务 {self.task_id}: 心跳更新失败: {e}")
                time.sleep(5)  # 错误情况下等待5秒后重试

        logger.info(f"任务 {self.task_id}: 心跳工作线程停止")

    def update_task_status(self, status: str, progress: float = None, message: str = None):
        """更新任务状态信息"""
        if self.heartbeat_manager is None:
            return

        try:
            status_data = {
                "status": status,
                "timestamp": time.time(),
                "progress": progress,
                "message": message
            }

            status_key = f"task_status:{self.task_id}"
            if hasattr(self.heartbeat_manager, 'redis_client') and self.heartbeat_manager.redis_client:
                self.heartbeat_manager.redis_client.setex(
                    status_key,
                    300,  # 5分钟TTL
                    str(status_data)
                )

        except Exception as e:
            logger.error(f"任务 {self.task_id}: 状态更新失败: {e}")


def start_task_heartbeat(task_id: str) -> TaskHeartbeatIntegration:
    """
    启动任务心跳

    Args:
        task_id: 任务ID

    Returns:
        TaskHeartbeatIntegration: 心跳集成实例
    """
    integration = TaskHeartbeatIntegration(task_id)
    integration.start_heartbeat()
    return integration


def update_task_heartbeat(task_id: str, status: str = None, progress: float = None, message: str = None):
    """
    更新任务心跳和状态

    Args:
        task_id: 任务ID
        status: 任务状态
        progress: 进度百分比
        message: 状态消息
    """
    try:
        heartbeat_manager = get_heartbeat_manager()
        if heartbeat_manager:
            # 更新心跳
            heartbeat_key = f"task_heartbeat:{task_id}"
            if hasattr(heartbeat_manager, 'redis_client') and heartbeat_manager.redis_client:
                heartbeat_manager.redis_client.setex(heartbeat_key, 120, f"active_{int(time.time())}")

            # 更新状态
            if status:
                status_data = {
                    "status": status,
                    "timestamp": time.time(),
                    "progress": progress,
                    "message": message
                }
                status_key = f"task_status:{task_id}"
                heartbeat_manager.redis_client.setex(status_key, 300, str(status_data))

    except Exception as e:
        logger.error(f"更新任务 {task_id} 心跳失败: {e}")


def stop_task_heartbeat(task_id: str):
    """
    停止任务心跳

    Args:
        task_id: 任务ID
    """
    try:
        # 清理Redis中的心跳和状态数据
        heartbeat_manager = get_heartbeat_manager()
        if heartbeat_manager and hasattr(heartbeat_manager, 'redis_client') and heartbeat_manager.redis_client:
            heartbeat_manager.redis_client.delete(f"task_heartbeat:{task_id}")
            heartbeat_manager.redis_client.delete(f"task_status:{task_id}")
            logger.info(f"任务 {task_id}: 心跳数据已清理")
    except Exception as e:
        logger.error(f"停止任务 {task_id} 心跳失败: {e}")


# 装饰器版本：自动为任务添加心跳支持
def with_task_heartbeat():
    """
    任务心跳装饰器

    使用示例：
    @with_task_heartbeat()
    def my_task(self, context):
        # 任务逻辑
        pass
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            task_id = getattr(self, 'request', None) or getattr(self, 'id', None) or func.__name__

            # 启动心跳
            integration = start_task_heartbeat(task_id)

            try:
                # 更新任务状态为运行中
                integration.update_task_status("running", 0, "任务开始执行")

                # 执行原函数
                result = func(self, *args, **kwargs)

                # 更新任务状态为完成
                integration.update_task_status("completed", 100, "任务执行完成")

                return result

            except Exception as e:
                # 更新任务状态为失败
                integration.update_task_status("failed", None, f"任务执行失败: {e}")
                raise

            finally:
                # 停止心跳
                integration.stop_heartbeat()

        return wrapper
    return decorator