#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS Service Tasks
IndexTTS2 文本转语音服务的具体任务实现（使用子进程隔离模式）
"""

import os
import sys
import time
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import torch
from celery import Task

# 导入共享模块
try:
    from services.common.config_loader import get_config
    from services.common.context import WorkflowContext, StageExecution
    from services.common.logger import get_logger
    from services.common.locks import gpu_lock, SmartGpuLockManager
    from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
    from services.common.file_service import get_file_service
except ImportError as e:
    print(f"导入共享模块失败: {e}")
    sys.exit(1)

# 设置日志
logger = get_logger(__name__)

# 加载配置
config = get_config()

# 从 app.py 导入 celery_app
from .celery_app import celery_app, gpu_lock_manager

# 导入新的子进程隔离 TTS 引擎
from .tts_engine import MultiProcessTTSEngine


class IndexTTSTask(Task):
    """IndexTTS任务基类，集成GPU锁和错误处理"""

    def __init__(self):
        super().__init__()
        self.gpu_lock_manager = gpu_lock_manager

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时的回调"""
        logger.error(f"任务 {task_id} 失败: {exc}")

        # 清理GPU锁
        if self.gpu_lock_manager:
            try:
                # 获取 GPU ID 和构造锁键
                gpu_id = kwargs.get('gpu_id', 0)
                lock_key = f"gpu_lock:{gpu_id}"
                # 使用任务 ID 作为任务名
                task_name = task_id
                # 调用正确的方法
                self.gpu_lock_manager.release_lock(task_name, lock_key, "task_failure")
                logger.info(f"任务 {task_id} 失败后成功释放锁 {lock_key}")
            except Exception as e:
                logger.error(f"释放锁失败: {e}", exc_info=True)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功时的回调"""
        logger.info(f"任务 {task_id} 成功完成")


# 全局 TTS 引擎实例（懒加载 + 子进程隔离模式）
_tts_engine = None


def get_tts_engine() -> MultiProcessTTSEngine:
    """
    获取 TTS 引擎单例（懒加载）

    引擎在首次调用时才会创建，模型在子进程中加载
    """
    global _tts_engine
    if _tts_engine is None:
        # 优先从config.yml获取配置，回退到环境变量
        indextts_config = config.get('indextts_service', {})

        # 模型配置
        model_dir = indextts_config.get('model_dir',
                    os.getenv('INDEX_TTS_MODEL_DIR', '/models/indextts'))

        # 性能配置
        use_fp16 = indextts_config.get('use_fp16',
                     os.getenv('INDEX_TTS_USE_FP16', 'true').lower() == 'true')
        use_deepspeed = indextts_config.get('use_deepspeed',
                         os.getenv('INDEX_TTS_USE_DEEPSPEED', 'false').lower() == 'true')
        use_cuda_kernel = indextts_config.get('use_cuda_kernel',
                           os.getenv('INDEX_TTS_USE_CUDA_KERNEL', 'false').lower() == 'true')
        num_workers = indextts_config.get('num_workers',
                         int(os.getenv('INDEX_TTS_NUM_WORKERS', '1')))

        logger.info("创建 IndexTTS 引擎实例（懒加载模式）")
        logger.info(f"配置来源: config.yml indextts_service 配置")
        logger.info(f"模型目录: {model_dir}")
        logger.info(f"FP16: {use_fp16}, DeepSpeed: {use_deepspeed}, CUDA Kernel: {use_cuda_kernel}")

        _tts_engine = MultiProcessTTSEngine({
            'model_dir': model_dir,
            'use_fp16': use_fp16,
            'use_deepspeed': use_deepspeed,
            'use_cuda_kernel': use_cuda_kernel,
            'num_workers': num_workers
        })
    return _tts_engine


@celery_app.task(bind=True, base=IndexTTSTask, name='indextts.generate_speech')
@gpu_lock()
def generate_speech(
    self,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    IndexTTS语音生成任务。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.indextts_service.executors import IndexTTSGenerateSpeechExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = IndexTTSGenerateSpeechExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(bind=True, name='indextts.list_voice_presets')
def list_voice_presets(self) -> Dict[str, Any]:
    """
    列出可用的语音预设

    Returns:
        Dict[str, Any]: 可用的语音预设列表
    """
    try:
        # --- Parameter Resolution ---
        workflow_context = WorkflowContext(**self.request.kwargs.get('context', {}))
        stage_name = self.name
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
                
                # 保存到当前 stage 的 input_params
                if stage_name not in workflow_context.stages:
                     workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
                workflow_context.stages[stage_name].input_params = resolved_params
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e

        # 这里将实现获取IndexTTS可用语音预设的逻辑
        # 目前返回一些示例预设
        presets = {
            'default': {
                'name': 'Default Voice',
                'description': '默认语音',
                'language': 'zh-CN',
                'gender': 'female'
            },
            'male_01': {
                'name': 'Male Voice 01',
                'description': '男声01',
                'language': 'zh-CN',
                'gender': 'male'
            },
            'female_01': {
                'name': 'Female Voice 01',
                'description': '女声01',
                'language': 'zh-CN',
                'gender': 'female'
            }
        }

        return {
            'status': 'success',
            'presets': presets,
            'total_count': len(presets)
        }

    except Exception as e:
        error_msg = f"获取语音预设失败: {str(e)}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg
        }


@celery_app.task(bind=True, name='indextts.get_model_info')
def get_model_info(self) -> Dict[str, Any]:
    """
    获取模型信息

    Returns:
        Dict[str, Any]: 模型信息
    """
    try:
        # --- Parameter Resolution ---
        workflow_context = WorkflowContext(**self.request.kwargs.get('context', {}))
        stage_name = self.name
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
                
                # 保存到当前 stage 的 input_params
                if stage_name not in workflow_context.stages:
                     workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
                workflow_context.stages[stage_name].input_params = resolved_params
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e

        # 返回配置信息（不需要加载模型）
        model_dir = os.getenv('INDEX_TTS_MODEL_DIR', '/models/indextts')
        use_fp16 = os.getenv('INDEX_TTS_USE_FP16', 'true').lower() == 'true'
        use_deepspeed = os.getenv('INDEX_TTS_USE_DEEPSPEED', 'false').lower() == 'true'
        use_cuda_kernel = os.getenv('INDEX_TTS_USE_CUDA_KERNEL', 'false').lower() == 'true'

        info = {
            'model_type': 'IndexTTS2',
            'model_version': '2.0',
            'device': 'cuda' if torch.cuda.is_available() else 'cpu',
            'model_path': model_dir,
            'status': 'ready (lazy-loading)',
            'capabilities': {
                'text_to_speech': True,
                'voice_cloning': True,
                'emotion_control': True,
                'multi_language': True,
                'real_time': False
            },
            'config': {
                'use_fp16': use_fp16,
                'use_deepspeed': use_deepspeed,
                'use_cuda_kernel': use_cuda_kernel
            }
        }

        return {
            'status': 'success',
            'model_info': info
        }

    except Exception as e:
        error_msg = f"获取模型信息失败: {str(e)}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg
        }