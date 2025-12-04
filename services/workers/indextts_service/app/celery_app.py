#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS Service Celery Application
IndexTTS2 文本转语音服务的 Celery 工作节点配置
"""

import os
import sys
from pathlib import Path

# 添加必要的路径
current_dir = Path(__file__).parent
services_dir = current_dir.parent.parent
sys.path.insert(0, str(services_dir))

# 添加IndexTTS2路径 - 使用配置的模型目录
from services.common.config_loader import get_config
config = get_config()
indextts_model_dir = config.get('indextts_service', {}).get('model_dir', '/models/indextts')
indextts_path = Path(indextts_model_dir)
if indextts_path.exists():
    sys.path.insert(0, str(indextts_path))

# 导入共享模块
try:
    from services.common.config_loader import get_config
    from services.common.logger import get_logger
    from services.common.locks import SmartGpuLockManager
except ImportError as e:
    # 这是一个严重错误，服务无法在没有其通用模块的情况下运行。
    # 记录错误并立即退出。
    import logging
    logging.basicConfig(level=logging.ERROR)
    logger = logging.getLogger(__name__)
    logger.critical(f"无法导入共享模块 (例如, config_loader, logger): {e}", exc_info=True)
    logger.critical("这是一个致命错误，服务将退出。请检查 PYTHONPATH 和模块依赖项。")
    sys.exit("错误：关键共享模块缺失，服务无法启动。")
else:
    # 设置日志
    logger = get_logger(__name__)

    # 加载配置
    config = get_config()

    # 初始化GPU锁管理器
    try:
        gpu_lock_manager = SmartGpuLockManager()
        logger.info("GPU锁管理器初始化成功")
    except Exception as e:
        logger.error(f"GPU锁管理器初始化失败: {e}")
        gpu_lock_manager = None

# 导入 Celery
from celery import Celery

# ========================================
# IndexTTS2 模型管理 (已移除，改用子进程隔离模式)
# ========================================
# 模型加载逻辑已迁移到 tts_engine.py，使用懒加载 + 子进程隔离模式

# ========================================
# Celery 应用配置
# ========================================

# 创建 Celery 应用
celery_app = Celery('indextts_service')

# 从环境变量中读取 Redis 连接信息
from services.common.celery_config import BROKER_URL, BACKEND_URL

# Celery 配置
celery_app.conf.update(
    # Broker 配置
    broker_url=BROKER_URL,
    result_backend=BACKEND_URL,

    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # 队列配置
    task_routes={
        'indextts.generate_speech': {'queue': 'indextts_queue'},
    },

    # Worker 配置
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,

    # 任务超时配置
    task_soft_time_limit=1800,  # 30分钟软超时
    task_time_limit=2100,       # 35分钟硬超时

    # 结果保留时间
    result_expires=3600,        # 1小时后清理结果

    # 错误重试配置
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
)

# ========================================
# Worker 启动时初始化
# ========================================

from celery.signals import worker_ready

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Worker准备就绪时的回调 - 不再预加载模型，改为懒加载"""
    logger.info("IndexTTS Worker 准备就绪 (懒加载模式，模型将在首次任务时加载)")

# ========================================
# 导入任务模块
# ========================================

try:
    from .tasks import *
    logger.info("IndexTTS任务模块加载成功")
except ImportError as e:
    logger.error(f"IndexTTS任务模块加载失败: {e}")

# ========================================
# 应用启动检查
# ========================================

@celery_app.task(bind=True)
def health_check(self):
    """
    健康检查任务
    """
    try:
        # 检查GPU状态
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_count = torch.cuda.device_count() if gpu_available else 0
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else "N/A"

        # 检查IndexTTS模型可用性
        model_status = "unknown"
        try:
            # 这里可以添加IndexTTS模型检查逻辑
            model_status = "ready"
        except Exception as e:
            model_status = f"error: {str(e)}"

        # 检查GPU锁状态
        lock_status = "unknown"
        if gpu_lock_manager:
            try:
                lock_info = gpu_lock_manager.get_lock_info()
                lock_status = "available" if lock_info is None else "locked"
            except Exception as e:
                lock_status = f"error: {str(e)}"

        return {
            'status': 'healthy',
            'service': 'indextts_service',
            'gpu': {
                'available': gpu_available,
                'count': gpu_count,
                'name': gpu_name
            },
            'model': model_status,
            'gpu_lock': lock_status
        }

    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            'status': 'unhealthy',
            'service': 'indextts_service',
            'error': str(e)
        }

if __name__ == '__main__':
    # 启动 Celery Worker
    celery_app.start()