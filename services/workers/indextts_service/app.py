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

# 添加IndexTTS2路径
indextts_path = Path("/tmp/index-tts")
if indextts_path.exists():
    sys.path.insert(0, str(indextts_path))

# 导入共享模块
try:
    from services.common.config_loader import get_config
    from services.common.logger import get_logger
    from services.common.locks import SmartGpuLockManager
except ImportError as e:
    print(f"导入共享模块失败: {e}")
    print("尝试直接使用基础配置...")
    # 提供备用配置
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    class DummyConfig:
        def get(self, key, default=None):
            return {
                'redis': {
                    'port': 6379,
                    'broker_db': 0,
                    'backend_db': 1
                }
            }.get(key, default)

    config = DummyConfig()
    gpu_lock_manager = None
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
# IndexTTS2 模型管理
# ========================================

# 全局IndexTTS2模型实例
tts_model = None

def initialize_indextts():
    """初始化IndexTTS2模型"""
    global tts_model
    try:
        logger.info("正在初始化IndexTTS2模型...")

        # 从环境变量获取配置
        model_dir = os.getenv('INDEX_TTS_MODEL_DIR', '/models/indextts')
        use_fp16 = os.getenv('INDEX_TTS_USE_FP16', 'true').lower() == 'true'
        use_deepspeed = os.getenv('INDEX_TTS_USE_DEEPSPEED', 'false').lower() == 'true'
        use_cuda_kernel = os.getenv('INDEX_TTS_USE_CUDA_KERNEL', 'false').lower() == 'true'

        # 检查模型目录
        checkpoints_dir = os.path.join(model_dir, 'checkpoints')
        if not os.path.exists(checkpoints_dir):
            logger.warning(f"模型检查点目录不存在: {checkpoints_dir}")
            return False

        # 配置文件路径
        config_path = os.path.join(checkpoints_dir, 'config.yaml')
        if not os.path.exists(config_path):
            logger.error(f"IndexTTS2配置文件不存在: {config_path}")
            return False

        # 导入IndexTTS2
        try:
            from indextts.infer_v2 import IndexTTS2

            logger.info(f"加载IndexTTS2模型: {checkpoints_dir}")
            logger.info(f"FP16: {use_fp16}, DeepSpeed: {use_deepspeed}, CUDA Kernel: {use_cuda_kernel}")

            # 初始化模型
            tts_model = IndexTTS2(
                cfg_path=config_path,
                model_dir=checkpoints_dir,
                use_fp16=use_fp16,
                use_deepspeed=use_deepspeed,
                use_cuda_kernel=use_cuda_kernel
            )

            logger.info("IndexTTS2模型初始化成功!")
            logger.info(f"模型版本: {getattr(tts_model, 'model_version', 'Unknown')}")
            return True

        except ImportError as e:
            logger.error(f"无法导入IndexTTS2: {e}")
            return False

    except Exception as e:
        logger.error(f"IndexTTS2模型初始化失败: {e}")
        return False

def get_tts_model():
    """获取IndexTTS2模型实例，如果未初始化则尝试初始化"""
    global tts_model
    if tts_model is None:
        if not initialize_indextts():
            raise RuntimeError("IndexTTS2模型未初始化")
    return tts_model

# ========================================
# Celery 应用配置
# ========================================

# 创建 Celery 应用
celery_app = Celery('indextts_service')

# 从配置文件中读取 Redis 连接信息
redis_config = config.get('redis', {})
broker_url = f"redis://redis:{redis_config.get('port', 6379)}/{redis_config.get('broker_db', 0)}"
backend_url = f"redis://redis:{redis_config.get('port', 6379)}/{redis_config.get('backend_db', 1)}"

# Celery 配置
celery_app.conf.update(
    # Broker 配置
    broker_url=broker_url,
    result_backend=backend_url,

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
    """Worker准备就绪时初始化IndexTTS2模型"""
    logger.info("IndexTTS Worker 准备就绪，开始初始化模型...")
    if initialize_indextts():
        logger.info("IndexTTS2模型初始化完成，Worker已准备就绪")
    else:
        logger.warning("IndexTTS2模型初始化失败，但Worker将继续运行")

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