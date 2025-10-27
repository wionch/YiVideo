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
    from services.common.logger import get_logger
    from services.common.locks import gpu_lock, SmartGpuLockManager
except ImportError as e:
    print(f"导入共享模块失败: {e}")
    sys.exit(1)

# 设置日志
logger = get_logger(__name__)

# 加载配置
config = get_config()

# 从 app.py 导入 celery_app
from .app import celery_app, gpu_lock_manager

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
            self.gpu_lock_manager.force_release_lock()

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
    IndexTTS语音生成任务

    Args:
        context: 任务上下文，包含：
            - text: 要转换的文本
            - output_path: 输出音频文件路径
            - voice_preset: 语音预设 (可选)
            - speed: 语速控制 (可选)
            - workflow_id: 工作流ID (可选)
            - stage_name: 阶段名称 (可选)

    Returns:
        Dict[str, Any]: 任务执行结果
    """
    start_time = time.time()
    task_id = self.request.id

    # 提取参数（兼容多种参数名称）
    text = context.get('text', '')
    output_path = context.get('output_path', '')

    # 音色参考音频 - 支持多种参数名
    reference_audio = (
        context.get('spk_audio_prompt') or  # 优先使用IndexTTS2官方参数名
        context.get('reference_audio') or   # 兼容旧参数名
        context.get('speaker_audio') or     # 兼容其他可能参数名
        None
    )

    # 情感参考音频
    emotion_reference = (
        context.get('emo_audio_prompt') or  # 优先使用IndexTTS2官方参数名
        context.get('emotion_reference') or # 兼容旧参数名
        None
    )

    # 情感相关参数
    emotion_alpha = float(context.get('emotion_alpha', 1.0))  # 修正默认值为1.0
    emotion_vector = context.get('emotion_vector')
    emotion_text = context.get('emotion_text')
    use_emo_text = bool(context.get('use_emo_text', False))
    use_random = bool(context.get('use_random', False))

    # 技术参数
    max_text_tokens_per_segment = int(context.get('max_text_tokens_per_segment', 120))
    verbose = bool(context.get('verbose', False))

    workflow_id = context.get('workflow_id', 'unknown')
    stage_name = context.get('stage_name', 'indextts.generate_speech')

    logger.info(f"开始执行IndexTTS2任务 {task_id}")
    logger.info(f"工作流ID: {workflow_id}")
    logger.info(f"文本长度: {len(text)} 字符")
    if reference_audio:
        logger.info(f"音色参考: {reference_audio}")
    if emotion_reference:
        logger.info(f"情感参考: {emotion_reference}")

    # 参数验证
    if not text:
        error_msg = "输入文本不能为空"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg,
            'task_id': task_id,
            'workflow_id': workflow_id
        }

    if not output_path:
        error_msg = "输出路径不能为空"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg,
            'task_id': task_id,
            'workflow_id': workflow_id
        }

    # IndexTTS2需要参考音频参数（必需参数）
    if not reference_audio:
        error_msg = "缺少必需参数: spk_audio_prompt (说话人参考音频)"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg,
            'task_id': task_id,
            'workflow_id': workflow_id,
            'hint': 'IndexTTS2是基于参考音频的语音合成系统，必须提供说话人参考音频'
        }

    # 验证参考音频文件是否存在
    if not os.path.exists(reference_audio):
        error_msg = f"参考音频文件不存在: {reference_audio}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg,
            'task_id': task_id,
            'workflow_id': workflow_id
        }

    # 验证输出目录是否存在，不存在则创建
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"创建输出目录: {output_dir}")
        except Exception as e:
            error_msg = f"无法创建输出目录 {output_dir}: {str(e)}"
            logger.error(error_msg)
            return {
                'status': 'error',
                'error': error_msg,
                'task_id': task_id,
                'workflow_id': workflow_id
            }

    try:
        # 获取 TTS 引擎（懒加载 + 子进程隔离）
        engine = get_tts_engine()

        # 生成语音（在子进程中执行）
        result = engine.generate_speech(
            text=text,
            output_path=output_path,
            reference_audio=reference_audio,
            emotion_reference=emotion_reference,
            emotion_alpha=emotion_alpha,
            emotion_vector=emotion_vector,
            emotion_text=emotion_text,
            use_random=use_random,
            max_text_tokens_per_segment=max_text_tokens_per_segment
        )

        # 添加任务信息
        result.update({
            'task_id': task_id,
            'workflow_id': workflow_id,
            'stage_name': stage_name,
            'input_params': {
                'text_length': len(text),
                'reference_audio': reference_audio,
                'emotion_reference': emotion_reference,
                'emotion_alpha': emotion_alpha,
                'emotion_vector': emotion_vector,
                'emotion_text': emotion_text,
                'use_random': use_random,
                'max_text_tokens_per_segment': max_text_tokens_per_segment
            }
        })

        total_time = time.time() - start_time
        logger.info(f"IndexTTS2任务 {task_id} 完成，总耗时: {total_time:.2f}秒")

        return result

    except Exception as e:
        error_msg = f"IndexTTS任务执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)

        return {
            'status': 'error',
            'error': error_msg,
            'task_id': task_id,
            'workflow_id': workflow_id,
            'stage_name': stage_name,
            'processing_time': time.time() - start_time
        }


@celery_app.task(bind=True, name='indextts.list_voice_presets')
def list_voice_presets(self) -> Dict[str, Any]:
    """
    列出可用的语音预设

    Returns:
        Dict[str, Any]: 可用的语音预设列表
    """
    try:
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