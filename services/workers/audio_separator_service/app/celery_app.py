#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - Celery 应用配置
"""

from celery import Celery
from services.common.celery_config import BROKER_URL, BACKEND_URL

# ========================================
# Celery 配置
# ========================================

celery_app = Celery(
    'audio_separator_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['services.workers.audio_separator_service.app.tasks']
)

# ========================================
# Celery 配置更新
# ========================================
celery_app.conf.update(
    # 序列化配置
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # 时区配置
    timezone='Asia/Shanghai',
    enable_utc=True,

    # 任务执行配置
    task_acks_late=True,  # 任务完成后再确认
    task_reject_on_worker_lost=True,  # Worker 丢失时拒绝任务
    task_track_started=True,  # 跟踪任务开始状态

    # 结果过期时间（1天）
    result_expires=86400,

    # 任务超时配置
    task_soft_time_limit=600,  # 软超时：10分钟
    task_time_limit=900,  # 硬超时：15分钟

    # Worker 配置
    worker_prefetch_multiplier=1,  # 每次只预取 1 个任务（重要：避免 GPU 锁竞争）
    worker_max_tasks_per_child=50,  # Worker 进程处理 50 个任务后重启（防止内存泄漏）

    # 日志配置
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
)

if __name__ == '__main__':
    celery_app.start()
