#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - Celery 任务定义
功能：基于 UVR-MDX 模型的人声/背景音分离任务
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from celery import Task

from services.common.locks import gpu_lock
from services.common.logger import get_logger
from services.common.context import WorkflowContext, StageExecution
from services.common import state_manager
from .celery_app import celery_app
from .model_manager import get_model_manager
# 导入新的通用配置加载器
from services.common.config_loader import CONFIG
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service

# 配置日志
logger = get_logger('audio_separator.tasks')


class AudioSeparatorTask(Task):
    """音频分离任务基类"""

    def __init__(self):
        super().__init__()
        self.model_manager = get_model_manager()
        self._config_cache = None
        self._config_timestamp = 0

    def get_config(self):
        """获取实时配置，支持热重载和简单缓存"""
        import time
        current_time = time.time()

        # 缓存5秒，避免频繁读取文件，但保持实时性
        if (self._config_cache is None or
            current_time - self._config_timestamp > 5):
            self._config_cache = CONFIG.get('audio_separator_service', {})
            self._config_timestamp = current_time
            logger.debug("配置缓存已更新")

        return self._config_cache

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时的回调"""
        logger.error(f"任务 {task_id} 失败: {exc}", exc_info=True)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功时的回调"""
        logger.info(f"任务 {task_id} 成功完成")
        super().on_success(retval, task_id, args, kwargs)


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.separate_vocals',
    max_retries=3,
    default_retry_delay=60
)
@gpu_lock()  # 🔒 集成 GPU 锁
def separate_vocals(self, context: dict) -> dict:
    """
    [工作流任务] 分离音频中的人声和背景音。

    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.audio_separator_service.executors import AudioSeparatorSeparateVocalsExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = AudioSeparatorSeparateVocalsExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.health_check'
)
def health_check(self) -> Dict[str, Any]:
    """健康检查任务"""
    try:
        health_status = self.model_manager.health_check()
        health_status['service_status'] = 'healthy'
        health_status['timestamp'] = time.time()
        return health_status
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}", exc_info=True)
        return {
            'service_status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Audio Separator Tasks 模块加载成功")
