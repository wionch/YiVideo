# services/workers/wservice/app/celery_app.py
# -*- coding: utf-8 -*-

"""
wservice - Celery Application
"""

from celery import Celery
from services.common.celery_config import BROKER_URL, BACKEND_URL

# ========================================
# Celery 配置
# ========================================

celery_app = Celery(
    'wservice_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['services.workers.wservice.app.tasks']
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
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,

    # 结果过期时间（1天）
    result_expires=86400,

    # Worker 配置
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

if __name__ == '__main__':
    celery_app.start()
