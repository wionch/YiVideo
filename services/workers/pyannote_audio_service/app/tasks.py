# services/workers/pyannote_audio_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
Pyannote Audio Service Tasks
基于 pyannote.audio 的说话人分离任务实现
"""

import os
import tempfile
import subprocess
import sys
import time
from pathlib import Path
from tokenize import TokenInfo
from typing import Dict, Any, Optional
import logging

import torch
import librosa
import numpy as np
from pyannote.audio import Pipeline
from pyannote.core import Annotation, Segment

# 导入Celery应用和工作流模型
from services.workers.pyannote_audio_service.app.celery_app import celery_app

# 导入共享模块
from services.common.config_loader import get_config
from services.common.logger import get_logger
from services.common.locks import gpu_lock
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service

config = get_config()
logger = get_logger(__name__)

class PyannoteAudioTask:
    """Pyannote音频任务基类 - 简化版本，与测试脚本保持一致"""

    def __init__(self):
        logger.info("初始化PyannoteAudioTask...")

    def load_pipeline(self):
        """加载说话人分离管道 - 与测试脚本保持一致的简化实现"""
        try:
            logger.info("开始加载说话人分离管道...")

            # 直接使用测试脚本的简单方式
            hf_token = os.environ.get('HF_TOKEN', config.get('pyannote_audio_service', {}).get('hf_token', ''))
            model_name = "pyannote/speaker-diarization-community-1"

            logger.info(f"选择模型: {model_name}")
            logger.info(f"HF Token存在: {bool(hf_token)}")

            # 与测试脚本完全一致的加载方式
            logger.info("开始从HuggingFace加载pipeline...")
            pipeline = Pipeline.from_pretrained(model_name, token=hf_token)
            logger.info("Pipeline加载完成")

            # 移动到CUDA设备（与测试脚本一致）
            logger.info("将pipeline移动到CUDA设备...")
            pipeline.to(torch.device("cuda"))
            logger.info("Pipeline已移动到CUDA设备")

            return pipeline

        except Exception as e:
            logger.error(f"加载说话人分离管道失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            raise

@celery_app.task(bind=True, name='pyannote_audio.diarize_speakers')
@gpu_lock(timeout=1800, poll_interval=0.5)
def diarize_speakers(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    [工作流任务] 说话人分离 - 使用 subprocess 调用独立推理脚本。
    该任务已迁移到统一的 BaseNodeExecutor 框架。

    Args:
        context: 工作流上下文

    Returns:
        dict: 包含说话人分离结果的字典
    """
    from services.workers.pyannote_audio_service.executors import PyannoteAudioDiarizeSpeakersExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PyannoteAudioDiarizeSpeakersExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()

@celery_app.task(bind=True, name='pyannote_audio.get_speaker_segments')
def get_speaker_segments(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    [工作流任务] 获取指定说话人的片段。
    该任务已迁移到统一的 BaseNodeExecutor 框架。

    支持单任务模式调用，通过 input_data 传入参数：
    - diarization_file: 说话人分离结果文件路径
    - speaker: 目标说话人标签（可选，不指定则返回所有说话人统计）

    Args:
        context: 工作流上下文

    Returns:
        dict: 包含指定说话人片段的字典
    """
    from services.workers.pyannote_audio_service.executors import PyannoteAudioGetSpeakerSegmentsExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PyannoteAudioGetSpeakerSegmentsExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()

@celery_app.task(bind=True, name='pyannote_audio.validate_diarization')
def validate_diarization(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    [工作流任务] 验证说话人分离结果的质量。
    该任务已迁移到统一的 BaseNodeExecutor 框架。

    支持单任务模式调用，通过 input_data 传入参数：
    - diarization_file: 说话人分离结果文件路径

    Args:
        context: 工作流上下文

    Returns:
        dict: 包含质量验证结果的字典
    """
    from services.workers.pyannote_audio_service.executors import PyannoteAudioValidateDiarizationExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PyannoteAudioValidateDiarizationExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
