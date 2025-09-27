# services/common/locks.py
# -*- coding: utf-8 -*-

"""
提供基于Redis的分布式锁，用于控制对共享资源（如GPU）的访问。
"""

import os

from services.common.logger import get_logger

logger = get_logger('locks')
import functools
import logging

from celery import Task
from redis import Redis

# 配置日志
# 日志已统一管理，使用 services.common.logger

# --- Redis 连接 ---
# 使用环境变量或默认值初始化Redis连接
# 注意：这里创建了一个全局连接实例。在生产环境中，更健壮的做法是使用连接池
# 并根据需要获取和释放连接，或者在应用启动时进行初始化。
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
# 使用一个专门的DB来存储锁，避免与Celery Broker或Backend冲突
REDIS_LOCK_DB = int(os.environ.get('REDIS_LOCK_DB', 2)) 

try:
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_LOCK_DB, decode_responses=True)
    redis_client.ping()
    logger.info(f"成功连接到Redis锁数据库 at {REDIS_HOST}:{REDIS_PORT}/{REDIS_LOCK_DB}")
except Exception as e:
    logger.error(f"无法连接到Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_LOCK_DB}. 分布式锁将无法工作. 错误: {e}")
    redis_client = None

# --- 分布式锁装饰器 ---

def gpu_lock(lock_key: str = "gpu_lock", timeout: int = 600, retry_interval: int = 10):
    """
    一个分布式GPU锁装饰器，确保被装饰的Celery任务在同一时间内只有一个实例在运行。

    Args:
        lock_key (str): 在Redis中用于锁的键。
        timeout (int): 锁的超时时间（秒），防止任务崩溃导致死锁。
        retry_interval (int): 当获取锁失败时，任务重试前的等待时间（秒）。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self: Task, *args, **kwargs):
            if not redis_client:
                logger.error("Redis客户端未初始化，无法获取锁。将直接执行任务，可能导致资源冲突。")
                return func(self, *args, **kwargs)

            try:
                # 尝试获取锁 (SETNX)
                # set(key, value, nx=True, ex=timeout)
                # nx=True: 只在键不存在时设置
                # ex=timeout: 设置键的过期时间
                if redis_client.set(lock_key, "locked", nx=True, ex=timeout):
                    logger.info(f"任务 {self.name} 成功获取锁 '{lock_key}'。")
                    try:
                        # 成功获取锁，执行任务
                        result = func(self, *args, **kwargs)
                        return result
                    finally:
                        # 任务执行完毕，释放锁
                        logger.info(f"任务 {self.name} 执行完毕，释放锁 '{lock_key}'。")
                        redis_client.delete(lock_key)
                else:
                    # 未能获取锁，说明有其他任务正在执行
                    logger.warning(f"任务 {self.name} 获取锁 '{lock_key}' 失败，将在 {retry_interval} 秒后重试。")
                    # 使用Celery的重试机制
                    raise self.retry(countdown=retry_interval, exc=Exception("Could not acquire lock."))
            
            except Exception as e:
                # 捕获包括重试异常在内的所有异常
                logger.error(f"任务 {self.name} 在处理锁时发生异常: {e}")
                # 如果不是Celery的重试异常，则需要决定是否要重试
                if not isinstance(e, self.MaxRetriesExceededError):
                     raise self.retry(countdown=retry_interval, exc=e)
                else:
                     raise e

        return wrapper
    return decorator