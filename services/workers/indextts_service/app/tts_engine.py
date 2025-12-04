#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS Engine with Process Isolation
参考 PaddleOCR 的懒加载模式实现的子进程隔离 TTS 引擎
"""

import os
import sys
import atexit
import multiprocessing
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

from services.common.logger import get_logger

logger = get_logger('indextts_engine')

# --- 全局变量（仅在工作进程中初始化） ---
tts_model_process_global = None


class MultiProcessTTSEngine:
    """
    多进程 IndexTTS 引擎，实现懒加载和进程隔离
    参考 PaddleOCR 的实现模式
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 TTS 引擎配置

        Args:
            config: 配置字典，包含：
                - model_dir: 模型目录路径
                - use_fp16: 是否使用 FP16
                - use_deepspeed: 是否使用 DeepSpeed
                - use_cuda_kernel: 是否使用 CUDA kernel
                - num_workers: 工作进程数（默认1）
        """
        self.config = config
        self.model_dir = config.get('model_dir', '/models/indextts')
        self.num_workers = config.get('num_workers', 1)

        logger.info(f"TTS Engine 初始化 (懒加载模式)")
        logger.info(f"模型目录: {self.model_dir}, 工作进程数: {self.num_workers}")

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
        生成语音（通过子进程）

        Args:
            text: 要转换的文本
            output_path: 输出音频文件路径
            reference_audio: 参考音频文件路径 (音色)
            emotion_reference: 情感参考音频路径
            emotion_alpha: 情感强度 (0.0-1.0)
            emotion_vector: 情感向量
            emotion_text: 情感描述文本
            use_random: 是否使用随机采样
            max_text_tokens_per_segment: 每段最大token数

        Returns:
            生成结果字典
        """
        task = {
            'text': text,
            'output_path': output_path,
            'reference_audio': reference_audio,
            'emotion_reference': emotion_reference,
            'emotion_alpha': emotion_alpha,
            'emotion_vector': emotion_vector,
            'emotion_text': emotion_text,
            'use_random': use_random,
            'max_text_tokens_per_segment': max_text_tokens_per_segment
        }

        logger.info(f"开始TTS任务: 文本长度={len(text)}, 输出={output_path}")

        # 使用子进程执行 TTS 任务
        result = self._execute_tts_in_subprocess(task)

        return result

    def _execute_tts_in_subprocess(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        在子进程中执行 TTS 任务
        参考 PaddleOCR 的 _multiprocess_ocr_batch 实现
        """
        ctx = multiprocessing.get_context('spawn')

        try:
            logger.info("启动 TTS 工作进程...")

            with ProcessPoolExecutor(
                max_workers=self.num_workers,
                initializer=_tts_worker_initializer,
                initargs=(self.config,),
                mp_context=ctx
            ) as executor:
                # 提交任务
                future = executor.submit(_tts_worker_task, task)

                # 等待结果（超时30分钟）
                result = future.result(timeout=1800)

                # 确保子进程正确终止
                try:
                    logger.debug("清理 ProcessPoolExecutor...")
                    executor.shutdown(wait=True)
                    logger.debug("ProcessPoolExecutor 已清理")
                except Exception as shutdown_e:
                    logger.warning(f"ProcessPoolExecutor 清理警告: {shutdown_e}")

            # 主进程 GPU 显存清理
            try:
                from services.common.gpu_memory_manager import log_gpu_memory_state, force_cleanup_gpu_memory
                log_gpu_memory_state("TTS 任务完成")
                force_cleanup_gpu_memory(aggressive=True)
                logger.info("主进程 GPU 显存已清理")
            except Exception as cleanup_e:
                logger.warning(f"主进程 GPU 显存清理失败: {cleanup_e}")
                # 降级清理
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("主进程 GPU 缓存已清理（降级模式）")

            return result

        except Exception as e:
            logger.error(f"TTS 任务执行失败: {e}", exc_info=True)

            # 出错时也要清理
            try:
                from services.common.gpu_memory_manager import force_cleanup_gpu_memory
                force_cleanup_gpu_memory(aggressive=True)
            except:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            return {
                'status': 'error',
                'error': str(e),
                'output_path': task.get('output_path', '')
            }


# --- 工作进程初始化器 ---
def _tts_worker_initializer(config: Dict[str, Any]):
    """
    工作进程初始化函数 - 加载 IndexTTS 模型
    参考 PaddleOCR 的 _full_ocr_worker_initializer
    """
    global tts_model_process_global
    pid = os.getpid()

    logger.info(f"[PID: {pid}] 开始初始化 IndexTTS 模型...")

    # 初始化 GPU 内存管理
    try:
        from services.common.gpu_memory_manager import initialize_worker_gpu_memory
        initialize_worker_gpu_memory()
        logger.info(f"[PID: {pid}] GPU 内存管理初始化完成")
    except Exception as e:
        logger.warning(f"[PID: {pid}] GPU 内存管理初始化失败: {e}")

    # 注册子进程退出清理函数
    try:
        atexit.register(_cleanup_worker_process)
        logger.debug(f"[PID: {pid}] 已注册子进程清理函数")
    except Exception as e:
        logger.warning(f"[PID: {pid}] 注册清理函数失败: {e}")

    try:
        # 从配置中获取参数
        model_dir = config.get('model_dir', '/models/indextts')
        use_fp16 = config.get('use_fp16', True)
        use_deepspeed = config.get('use_deepspeed', False)
        use_cuda_kernel = config.get('use_cuda_kernel', False)

        # 检查模型目录
        checkpoints_dir = os.path.join(model_dir, 'checkpoints')
        if not os.path.exists(checkpoints_dir):
            raise FileNotFoundError(f"模型检查点目录不存在: {checkpoints_dir}")

        config_path = os.path.join(checkpoints_dir, 'config.yaml')
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"IndexTTS 配置文件不存在: {config_path}")

        # 添加 IndexTTS 路径 - 使用配置的模型目录
        indextts_path = model_dir  # 使用配置中的模型目录
        if os.path.exists(indextts_path):
            sys.path.insert(0, indextts_path)

        # 导入并初始化 IndexTTS2
        from indextts.infer_v2 import IndexTTS2

        logger.info(f"[PID: {pid}] 加载 IndexTTS2 模型: {checkpoints_dir}")
        logger.info(f"[PID: {pid}] FP16={use_fp16}, DeepSpeed={use_deepspeed}, CUDA Kernel={use_cuda_kernel}")

        # 初始化模型
        tts_model_process_global = IndexTTS2(
            cfg_path=config_path,
            model_dir=checkpoints_dir,
            use_fp16=use_fp16,
            use_deepspeed=use_deepspeed,
            use_cuda_kernel=use_cuda_kernel
        )

        logger.info(f"[PID: {pid}] IndexTTS2 模型初始化成功")

    except Exception as e:
        logger.error(f"[PID: {pid}] IndexTTS2 模型初始化失败: {e}", exc_info=True)
        tts_model_process_global = None


# --- 工作进程任务函数 ---
def _tts_worker_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    工作进程中执行的 TTS 任务
    参考 PaddleOCR 的 _full_ocr_worker_task
    """
    global tts_model_process_global

    if tts_model_process_global is None:
        return {
            'status': 'error',
            'error': 'IndexTTS 模型未初始化',
            'output_path': task.get('output_path', '')
        }

    try:
        import time
        import torch
        start_time = time.time()

        # 提取参数
        text = task['text']
        output_path = task['output_path']
        reference_audio = task.get('reference_audio')
        emotion_reference = task.get('emotion_reference')
        emotion_alpha = task.get('emotion_alpha', 0.65)
        emotion_vector = task.get('emotion_vector')
        emotion_text = task.get('emotion_text')
        use_random = task.get('use_random', False)
        max_text_tokens_per_segment = task.get('max_text_tokens_per_segment', 120)

        # 创建输出目录
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 执行 TTS 推理
        tts_model_process_global.infer(
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

        # 清理中间变量
        del audio_data

        # 定期清理 GPU 显存
        try:
            from services.common.gpu_memory_manager import force_cleanup_gpu_memory
            force_cleanup_gpu_memory(aggressive=False)
        except:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return {
            'status': 'success',
            'output_path': str(output_path),
            'duration': duration,
            'sample_rate': sample_rate,
            'text_length': len(text),
            'processing_time': processing_time,
            'model_info': {
                'model_type': 'IndexTTS2',
                'device': 'cuda' if torch.cuda.is_available() else 'cpu',
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
        logger.error(f"TTS 任务执行失败: {e}", exc_info=True)

        # 出错时也要清理显存
        try:
            from services.common.gpu_memory_manager import force_cleanup_gpu_memory
            force_cleanup_gpu_memory(aggressive=True)
        except:
            pass

        return {
            'status': 'error',
            'error': str(e),
            'output_path': task.get('output_path', '')
        }


# --- 清理函数 ---
def _cleanup_worker_process():
    """
    子进程退出前的完整清理流程
    参考 PaddleOCR 的 _cleanup_worker_process
    """
    global tts_model_process_global
    pid = os.getpid()

    try:
        logger.debug(f"[PID: {pid}] 开始清理子进程资源")

        # 1. 清理 IndexTTS 模型
        if tts_model_process_global is not None:
            try:
                del tts_model_process_global
                tts_model_process_global = None
                logger.debug(f"[PID: {pid}] IndexTTS 模型已清理")
            except Exception as e:
                logger.warning(f"[PID: {pid}] IndexTTS 模型清理失败: {e}")

        # 2. 强制清理 GPU 显存
        try:
            from services.common.gpu_memory_manager import force_cleanup_gpu_memory
            force_cleanup_gpu_memory(aggressive=True)
            logger.debug(f"[PID: {pid}] GPU 显存已强制清理")
        except Exception as e:
            logger.debug(f"[PID: {pid}] GPU 显存清理失败: {e}")
            # 降级清理
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.debug(f"[PID: {pid}] GPU 缓存已清理（降级模式）")
            except:
                pass

        # 3. Python 垃圾回收
        import gc
        gc.collect()

        logger.debug(f"[PID: {pid}] 子进程资源清理完成")

    except Exception as e:
        logger.error(f"[PID: {pid}] 子进程清理过程中发生错误: {e}")
