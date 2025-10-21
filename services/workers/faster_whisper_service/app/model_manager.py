#!/usr/bin/env python3
"""
线程安全的 WhisperX 模型管理器
解决全局变量的并发访问问题，提供安全的模型加载和管理机制
"""

import threading
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager

import whisperx

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
    use_faster_whisper: bool
    faster_whisper_threads: int
    model_quantization: str
    enable_word_timestamps: bool
    enable_diarization: bool
    audio_sample_rate: int
    audio_channels: int

class ThreadSafeModelManager:
    """线程安全的模型管理器"""

    def __init__(self):
        self._lock = threading.RLock()
        self._asr_model = None
        self._align_model = None
        self._align_metadata = None
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
            use_faster_whisper=cfg.get('use_faster_whisper', True),
            faster_whisper_threads=cfg.get('faster_whisper_threads', 4),
            model_quantization=cfg.get('model_quantization', 'float16'),
            enable_word_timestamps=cfg.get('enable_word_timestamps', True),
            enable_diarization=cfg.get('enable_diarization', False),
            audio_sample_rate=cfg.get('audio_sample_rate', 16000),
            audio_channels=cfg.get('audio_channels', 1)
        )

    def _load_asr_model(self, config: ModelConfig) -> Any:
        """加载 ASR 模型"""
        logger.info(f"Loading WhisperX ASR model '{config.model_name}' with configuration:")
        logger.info(f"  - Device: {config.device}")
        logger.info(f"  - Compute type: {config.compute_type}")
        logger.info(f"  - Batch size: {config.batch_size}")
        logger.info(f"  - Language: {config.language}")
        logger.info(f"  - Faster-Whisper: {config.use_faster_whisper}")

        if config.use_faster_whisper:
            logger.info(f"  - Threads: {config.faster_whisper_threads}")
            logger.info(f"  - Quantization: {config.model_quantization}")

        # 构建模型加载参数
        model_kwargs = {
            'device': config.device,
            'compute_type': config.compute_type,
            'language': config.language
        }

        # 启用 Faster-Whisper 后端
        if config.use_faster_whisper:
            model_kwargs['threads'] = config.faster_whisper_threads

        try:
            # 加载 ASR 模型
            model = whisperx.load_model(config.model_name, **model_kwargs)
            logger.info("✓ ASR model loaded successfully")
            return model

        except Exception as e:
            logger.error(f"Failed to load ASR model: {e}")
            # 降级策略：尝试使用原生后端
            if config.use_faster_whisper:
                logger.warning("Attempting fallback to native backend...")
                model_kwargs.pop('threads', None)
                model = whisperx.load_model(config.model_name, **model_kwargs)
                logger.info("✓ Fallback to native backend successful")
                return model
            raise

    def _load_alignment_model(self, config: ModelConfig) -> tuple[Optional[Any], Optional[Dict]]:
        """加载对齐模型"""
        if not config.language or not config.enable_diarization:
            logger.info("Alignment model skipped (diarization disabled or no language specified)")
            return None, None

        try:
            logger.info(f"Loading WhisperX Alignment model for language '{config.language}'...")
            align_model, align_metadata = whisperx.load_align_model(
                language_code=config.language,
                device=config.device
            )
            logger.info("✓ Alignment model loaded successfully")
            return align_model, align_metadata

        except Exception as e:
            logger.warning(f"Failed to load alignment model: {e}")
            return None, None

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

            # 加载对齐模型
            self._align_model, self._align_metadata = self._load_alignment_model(self._model_config)

            self._last_load_time = time.time()
            logger.info("WhisperX models loading process completed")
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
                config1.use_faster_whisper == config2.use_faster_whisper and
                config1.faster_whisper_threads == config2.faster_whisper_threads and
                config1.model_quantization == config2.model_quantization and
                config1.enable_word_timestamps == config2.enable_word_timestamps and
                config1.enable_diarization == config2.enable_diarization)

    @contextmanager
    def get_models(self):
        """获取模型实例的上下文管理器"""
        self.ensure_models_loaded()

        try:
            with self._lock:
                yield self._asr_model, self._align_model, self._align_metadata, self._model_config
        except Exception as e:
            logger.error(f"Error while using models: {e}")
            raise

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        with self._lock:
            return {
                'asr_model_loaded': self._asr_model is not None,
                'align_model_loaded': self._align_model is not None,
                'model_config': self._model_config.__dict__ if self._model_config else None,
                'last_load_time': self._last_load_time,
                'load_in_progress': self._load_in_progress,
                'load_failed': self._load_failed,
                'load_error': self._load_error
            }

    def unload_models(self):
        """卸载模型"""
        with self._lock:
            logger.info("Unloading WhisperX models...")
            self._asr_model = None
            self._align_model = None
            self._align_metadata = None
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
                'align_model_available': self._align_model is not None,
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

# 向后兼容的全局函数
def get_whisperx_models():
    """向后兼容的模型加载函数"""
    return model_manager.ensure_models_loaded()

def segments_to_srt(segments: list) -> str:
    """Converts whisperx segments to SRT format."""
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


def segments_to_word_timestamp_json(segments: list, include_segment_info: bool = True) -> str:
    """
    将WhisperX的segments转换为包含词级时间戳的JSON格式

    Args:
        segments: WhisperX转录结果的segments列表
        include_segment_info: 是否包含句子级别信息

    Returns:
        JSON格式的字符串，包含详细的词级时间戳信息
    """
    import json

    result = {
        "format": "word_timestamps",
        "total_segments": len(segments),
        "segments": []
    }

    for i, segment in enumerate(segments):
        segment_data = {
            "id": i + 1,
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        }

        # 如果包含句子级别信息，添加SRT格式时间
        if include_segment_info:
            segment_data["srt_time"] = f"{int(segment['start'] // 3600):02}:{int((segment['start'] % 3600) // 60):02}:{int(segment['start'] % 60):02},{int((segment['start'] * 1000) % 1000):03} --> {int(segment['end'] // 3600):02}:{int((segment['end'] % 3600) // 60):02}:{int(segment['end'] % 60):02},{int((segment['end'] * 1000) % 1000):03}"

        # 检查是否有词级时间戳数据
        if "words" in segment and segment["words"]:
            segment_data["words"] = []
            for word_info in segment["words"]:
                word_data = {
                    "word": word_info["word"],
                    "start": word_info["start"],
                    "end": word_info["end"],
                    "confidence": word_info.get("confidence", 0.0)
                }
                segment_data["words"].append(word_data)
        else:
            # 如果没有词级时间戳，将整个segment作为一个词处理
            segment_data["words"] = [{
                "word": segment["text"].strip(),
                "start": segment["start"],
                "end": segment["end"],
                "confidence": 1.0
            }]

        result["segments"].append(segment_data)

    return json.dumps(result, indent=2, ensure_ascii=False)