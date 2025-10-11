#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS Service Tasks
IndexTTS2 文本转语音服务的具体任务实现
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
import torchaudio
import soundfile as sf
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


class IndexTTSModel:
    """IndexTTS2模型管理器"""

    def __init__(self, model_path: str = "/models/indextts"):
        """
        初始化IndexTTS模型

        Args:
            model_path: 模型存储路径
        """
        self.model_path = Path(model_path)
        self.checkpoints_path = self.model_path / "checkpoints"
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger = logger
        self.model_version = "unknown"

        self._setup_model()

    def _setup_model(self):
        """设置和加载模型"""
        try:
            self.logger.info(f"正在初始化IndexTTS2模型...")
            self.logger.info(f"使用设备: {self.device}")

            # 检查模型文件
            if not self.checkpoints_path.exists():
                raise FileNotFoundError(f"模型检查点目录不存在: {self.checkpoints_path}")

            config_path = self.checkpoints_path / "config.yaml"
            if not config_path.exists():
                raise FileNotFoundError(f"IndexTTS2配置文件不存在: {config_path}")

            # 从环境变量获取性能配置
            use_fp16 = os.getenv('INDEX_TTS_USE_FP16', 'true').lower() == 'true'
            use_deepspeed = os.getenv('INDEX_TTS_USE_DEEPSPEED', 'false').lower() == 'true'
            use_cuda_kernel = os.getenv('INDEX_TTS_USE_CUDA_KERNEL', 'false').lower() == 'true'

            # 导入并初始化IndexTTS2
            try:
                # 添加IndexTTS2路径
                sys.path.insert(0, "/tmp/index-tts")
                from indextts.infer_v2 import IndexTTS2

                self.logger.info(f"加载IndexTTS2模型: {self.checkpoints_path}")
                self.logger.info(f"FP16: {use_fp16}, DeepSpeed: {use_deepspeed}, CUDA Kernel: {use_cuda_kernel}")

                # 初始化模型
                self.model = IndexTTS2(
                    cfg_path=str(config_path),
                    model_dir=str(self.checkpoints_path),
                    use_fp16=use_fp16,
                    use_deepspeed=use_deepspeed,
                    use_cuda_kernel=use_cuda_kernel
                )

                self.model_version = getattr(self.model, 'model_version', '2.0')
                self.logger.info(f"IndexTTS2模型初始化成功! 版本: {self.model_version}")

            except ImportError as e:
                self.logger.error(f"无法导入IndexTTS2: {e}")
                raise RuntimeError(f"IndexTTS2模块导入失败: {e}")

        except Exception as e:
            self.logger.error(f"IndexTTS2模型初始化失败: {e}")
            raise RuntimeError(f"IndexTTS2模型初始化失败: {e}")

    def generate_speech(
        self,
        text: str,
        output_path: str,
        reference_audio: Optional[str] = None,
        emotion_reference: Optional[str] = None,
        emotion_alpha: float = 0.65,
        emotion_vector: Optional[List[float]] = None,
        emotion_text: Optional[str] = None,
        use_random: bool = False,
        max_text_tokens_per_segment: int = 120,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用IndexTTS2生成语音

        Args:
            text: 要转换的文本
            output_path: 输出音频文件路径
            reference_audio: 参考音频文件路径 (音色)
            emotion_reference: 情感参考音频路径
            emotion_alpha: 情感强度 (0.0-1.0)
            emotion_vector: 情感向量 [喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]
            emotion_text: 情感描述文本
            use_random: 是否使用随机采样
            max_text_tokens_per_segment: 每段最大token数
            **kwargs: 其他参数

        Returns:
            Dict[str, Any]: 生成结果
        """
        start_time = time.time()

        try:
            self.logger.info(f"开始生成语音...")
            self.logger.info(f"文本: {text[:100]}...")
            self.logger.info(f"输出路径: {output_path}")

            # 创建输出目录
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # 使用真实的IndexTTS2模型
            return self._generate_with_real_model(
                text=text,
                output_path=output_path,
                reference_audio=reference_audio,
                emotion_reference=emotion_reference,
                emotion_alpha=emotion_alpha,
                emotion_vector=emotion_vector,
                emotion_text=emotion_text,
                use_random=use_random,
                max_text_tokens_per_segment=max_text_tokens_per_segment,
                **kwargs
            )

        except Exception as e:
            error_msg = f"语音生成失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                'status': 'error',
                'error': error_msg,
                'output_path': output_path,
                'processing_time': time.time() - start_time
            }

    def _generate_with_real_model(self, **kwargs) -> Dict[str, Any]:
        """使用真实IndexTTS2模型生成语音"""
        try:
            start_time = time.time()

            # 准备参数
            text = kwargs['text']
            output_path = kwargs['output_path']
            reference_audio = kwargs.get('reference_audio')
            emotion_reference = kwargs.get('emotion_reference')
            emotion_alpha = kwargs.get('emotion_alpha', 0.65)
            emotion_vector = kwargs.get('emotion_vector')
            emotion_text = kwargs.get('emotion_text')
            use_random = kwargs.get('use_random', False)
            max_text_tokens_per_segment = kwargs.get('max_text_tokens_per_segment', 120)

            # IndexTTS2推理
            self.model.infer(
                spk_audio_prompt=reference_audio,
                text=text,
                output_path=output_path,
                emo_audio_prompt=emotion_reference,
                emo_alpha=emotion_alpha,
                emo_vector=emotion_vector,
                use_emo_text=bool(emotion_text),
                emo_text=emotion_text,
                use_random=use_random,
                max_text_tokens_per_segment=max_text_tokens_per_segment,
                verbose=True
            )

            # 获取生成的音频信息
            import librosa
            audio_data, sample_rate = librosa.load(output_path)
            duration = len(audio_data) / sample_rate

            processing_time = time.time() - start_time
            self.logger.info(f"IndexTTS2语音生成完成，耗时: {processing_time:.2f}秒")

            return {
                'status': 'success',
                'output_path': str(output_path),
                'duration': duration,
                'sample_rate': sample_rate,
                'text_length': len(text),
                'processing_time': processing_time,
                'model_info': {
                    'model_type': 'IndexTTS2',
                    'model_version': self.model_version,
                    'device': self.device,
                    },
                'parameters': {
                    'reference_audio': reference_audio,
                    'emotion_reference': emotion_reference,
                    'emotion_alpha': emotion_alpha,
                    'emotion_vector': emotion_vector,
                    'emotion_text': emotion_text,
                    'use_random': use_random,
                    'max_text_tokens_per_segment': max_text_tokens_per_segment
                }
            }

        except Exception as e:
            raise Exception(f"IndexTTS2推理失败: {str(e)}")


# 全局模型实例
_model_instance = None

def get_model_instance() -> IndexTTSModel:
    """获取模型单例"""
    global _model_instance
    if _model_instance is None:
        model_path = os.environ.get('INDEX_TTS_MODEL_PATH', '/models/indextts')
        _model_instance = IndexTTSModel(model_path)
    return _model_instance


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

    # 提取参数
    text = context.get('text', '')
    output_path = context.get('output_path', '')
    reference_audio = context.get('reference_audio')  # 音色参考音频
    emotion_reference = context.get('emotion_reference')  # 情感参考音频
    emotion_alpha = float(context.get('emotion_alpha', 0.65))  # 情感强度
    emotion_vector = context.get('emotion_vector')  # 情感向量
    emotion_text = context.get('emotion_text')  # 情感描述文本
    use_random = bool(context.get('use_random', False))  # 随机采样
    max_text_tokens_per_segment = int(context.get('max_text_tokens_per_segment', 120))

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

    try:
        # 获取模型实例
        model = get_model_instance()

        # 生成语音
        result = model.generate_speech(
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
        model = get_model_instance()

        info = {
            'model_type': 'IndexTTS2',
            'model_version': model.model_version,
            'device': model.device,
            'model_path': str(model.model_path),
            'status': 'ready',
            'capabilities': {
                'text_to_speech': True,
                'voice_cloning': True,  # 支持音色克隆
                'emotion_control': True,  # 支持情感控制
                'multi_language': True,   # 支持中英文
                'real_time': False
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