# -*- coding: utf-8 -*-

"""Qwen3-ASR Celery 任务入口。"""

from services.workers.qwen3_asr_service.app.celery_app import celery_app
from services.workers.qwen3_asr_service.executors.transcribe_executor import Qwen3ASRTranscribeExecutor
from services.common.context import WorkflowContext
from services.common import state_manager


@celery_app.task(bind=True, name='qwen3_asr.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    """Qwen3-ASR 语音转录任务入口。"""
    workflow_context = WorkflowContext(**context)
    executor = Qwen3ASRTranscribeExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
