# services/workers/pyannote_audio_service/app/celery_app.py
# -*- coding: utf-8 -*-

"""
Pyannote Audio Service 的 Celery 应用配置。
"""

from celery import Celery
from services.common.celery_config import BROKER_URL, BACKEND_URL

# --- Celery App Configuration ---

celery_app = Celery(
    'pyannote_audio_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['services.workers.pyannote_audio_service.app.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)