# -*- coding: utf-8 -*-

"""
FunASR Service 的 Celery 应用配置。
"""

from celery import Celery
from services.common.celery_config import BROKER_URL, BACKEND_URL

celery_app = Celery(
    "funasr_tasks",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=["services.workers.funasr_service.app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": 3600,
        "max_connections": 10,
    },
)
