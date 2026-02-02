# -*- coding: utf-8 -*-

"""FunASR Celery 任务入口。"""

from services.common import state_manager
from services.common.context import WorkflowContext
from services.workers.funasr_service.app.celery_app import celery_app
from services.workers.funasr_service.executors.transcribe_executor import (
    FunASRTranscribeExecutor,
)


@celery_app.task(bind=True, name="funasr.transcribe_audio")
def transcribe_audio(self, context: dict) -> dict:
    """FunASR 语音转录任务入口。"""
    workflow_context = WorkflowContext(**context)
    executor = FunASRTranscribeExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
