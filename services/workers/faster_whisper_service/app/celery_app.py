# services/workers/faster_whisper_service/app/celery_app.py
# -*- coding: utf-8 -*-

"""
Faster Whisper Service 的 Celery 应用配置。
"""

import os
from celery import Celery

# --- Celery App Configuration ---
BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
BACKEND_URL = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

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
)