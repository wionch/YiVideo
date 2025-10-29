# services/workers/faster_whisper_service/app/celery_app.py
# -*- coding: utf-8 -*-

"""
Faster Whisper Service 的 Celery 应用配置。
"""

from celery import Celery
from services.common.celery_config import BROKER_URL, BACKEND_URL

# --- Celery App Configuration ---

celery_app = Celery(
    'faster_whisper_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['services.workers.faster_whisper_service.app.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour
        'max_connections': 10,
    }
)