# -*- coding: utf-8 -*-

"""Qwen3-ASR Celery 任务入口。"""

from services.workers.qwen3_asr_service.app.celery_app import celery_app
from services.workers.qwen3_asr_service.executors.transcribe_executor import Qwen3ASRTranscribeExecutor


@celery_app.task(bind=True, name='qwen3_asr.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    executor = Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    return executor.execute(self, context)
