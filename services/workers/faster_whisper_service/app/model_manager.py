#!/usr/bin/env python3
"""
线程安全的 faster-whisper 模型管理器
解决全局变量的并发访问问题，提供安全的模型加载和管理机制
"""

import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager

from faster_whisper import WhisperModel

from services.common.config_loader import CONFIG
from services.common.logger import get_logger

logger = get_logger('model_manager')

@dataclass
class ModelConfig:
    """模型配置数据类"""
    model_name: str
    language: str
    device: str
    compute_type: str
    batch_size: int
    faster_whisper_threads: int
    model_quantization: str
    enable_word_timestamps: bool
    audio_sample_rate: int
    audio_channels: int

class ThreadSafeModelManager:
    """线程安全的模型管理器"""

    def __init__(self):
        self._lock = threading.RLock()
        self._asr_model = None
        self._model_config = None
        self._last_load_time = 0
        self._load_in_progress = False
        self._load_failed = False
        self._load_error = None

    def _load_config(self) -> ModelConfig:
        """从配置文件加载模型配置"""
        cfg = CONFIG.get('faster_whisper_service', {})

        return ModelConfig(
            model_name=cfg.get('model_name', 'large-v2'),
            language=cfg.get('language', 'zh'),
            device=cfg.get('device', 'cuda'),
            compute_type=cfg.get('compute_type', 'float16'),
            batch_size=cfg.get('batch_size', 4),
            faster_whisper_threads=cfg.get('faster_whisper_threads', 4),
            model_quantization=cfg.get('model_quantization', 'float16'),
            enable_word_timestamps=cfg.get('enable_word_timestamps', True),
            audio_sample_rate=cfg.get('audio_sample_rate', 16000),
            audio_channels=cfg.get('audio_channels', 1)
        )

    def _load_asr_model(self, config: ModelConfig) -> Any:
        """加载 ASR 模型"""
        logger.info(f"Loading faster-whisper ASR model '{config.model_name}' with configuration:")
        logger.info(f"  - Device: {config.device}")
        logger.info(f"  - Compute type: {config.compute_type}")
        logger.info(f"  - CPU Threads: {config.faster_whisper_threads}")
        logger.info(f"  - Quantization: {config.model_quantization}")

        # 构建模型加载参数
        model_kwargs = {
            'device': config.device,
            'compute_type': config.compute_type,
            'cpu_threads': config.faster_whisper_threads,
            'num_workers': 4,
        }

        try:
            # 加载 ASR 模型
            model = WhisperModel(config.model_name, **model_kwargs)
            logger.info("✓ ASR model loaded successfully")
            return model

        except Exception as e:
            logger.error(f"Failed to load ASR model: {e}")
            raise

    def _load_models_internal(self) -> bool:
        """内部模型加载方法（已加锁）"""
        if self._load_in_progress:
            # 等待其他线程完成加载
            max_wait = 300  # 5分钟
            start_time = time.time()

            while self._load_in_progress:
                if time.time() - start_time > max_wait:
                    raise RuntimeError("Timeout waiting for model loading")
                time.sleep(0.1)

            if self._load_failed:
                raise RuntimeError(f"Model loading failed: {self._load_error}")
            return True

        self._load_in_progress = True
        self._load_failed = False
        self._load_error = None

        try:
            # 加载配置
            self._model_config = self._load_config()

            # 加载 ASR 模型
            self._asr_model = self._load_asr_model(self._model_config)

            self._last_load_time = time.time()
            logger.info("faster-whisper models loading process completed")
            return True

        except Exception as e:
            self._load_failed = True
            self._load_error = str(e)
            logger.error(f"Failed to load models: {e}")
            raise

        finally:
            self._load_in_progress = False

    def ensure_models_loaded(self) -> bool:
        """确保模型已加载"""
        with self._lock:
            # 检查是否需要重新加载
            current_config = self._load_config()

            if (self._asr_model is None or
                self._model_config is None or
                not self._configs_equal(current_config, self._model_config)):

                logger.info("Models need to be reloaded due to configuration change")
                return self._load_models_internal()

            return True

    def _configs_equal(self, config1: ModelConfig, config2: ModelConfig) -> bool:
        """比较两个配置是否相等"""
        return (config1.model_name == config2.model_name and
                config1.language == config2.language and
                config1.device == config2.device and
                config1.compute_type == config2.compute_type and
                config1.batch_size == config2.batch_size and
                config1.faster_whisper_threads == config2.faster_whisper_threads and
                config1.model_quantization == config2.model_quantization and
                config1.enable_word_timestamps == config2.enable_word_timestamps)

    @contextmanager
    def get_models(self):
        """获取模型实例的上下文管理器"""
        self.ensure_models_loaded()

        try:
            with self._lock:
                yield self._asr_model, self._model_config
        except Exception as e:
            logger.error(f"Error while using models: {e}")
            raise

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        with self._lock:
            return {
                'asr_model_loaded': self._asr_model is not None,
                'model_config': self._model_config.__dict__ if self._model_config else None,
                'last_load_time': self._last_load_time,
                'load_in_progress': self._load_in_progress,
                'load_failed': self._load_failed,
                'load_error': self._load_error
            }

    def unload_models(self):
        """卸载模型"""
        with self._lock:
            logger.info("Unloading faster-whisper models...")
            self._asr_model = None
            self._model_config = None
            self._last_load_time = 0
            self._load_failed = False
            self._load_error = None
            logger.info("Models unloaded successfully")

    def health_check(self) -> Dict[str, Any]:
        """模型健康检查"""
        with self._lock:
            status = {
                'status': 'healthy',
                'asr_model_available': self._asr_model is not None,
                'last_load_time': self._last_load_time,
                'configuration_valid': self._model_config is not None
            }

            if self._load_failed:
                status['status'] = 'unhealthy'
                status['error'] = self._load_error

            # 检查配置是否发生变化
            if self._model_config:
                current_config = self._load_config()
                if not self._configs_equal(current_config, self._model_config):
                    status['status'] = 'configuration_changed'
                    status['message'] = 'Model configuration has changed, reload required'

            return status

# 全局模型管理器实例
model_manager = ThreadSafeModelManager()

def get_model_manager() -> ThreadSafeModelManager:
    """获取模型管理器实例"""
    return model_manager

def _format_segments_to_srt(segments: list) -> str:
    """将分段转换为SRT格式"""
    srt_content = ""
    for i, segment in enumerate(segments):
        start_time = segment['start']
        end_time = segment['end']
        text = segment['text']

        start_srt = f"{int(start_time // 3600):02}:{int((start_time % 3600) // 60):02}:{int(start_time % 60):02},{int((start_time * 1000) % 1000):03}"
        end_srt = f"{int(end_time // 3600):02}:{int((end_time % 3600) // 60):02}:{int(end_time % 60):02},{int((end_time * 1000) % 1000):03}"

        srt_content += f"{i + 1}\n"
        srt_content += f"{start_srt} --> {end_srt}\n"
        srt_content += f"{text.strip()}\n\n"
    return srt_content


