# -*- coding: utf-8 -*-

"""Qwen3-ASR Celery 应用。"""

from celery import Celery

celery_app = Celery(
    'qwen3_asr_tasks',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['services.workers.qwen3_asr_service.app.tasks'],
)
