#!/usr/bin/env python3
"""
基于 Pydantic 的 faster-whisper 配置验证系统
提供严格的配置验证和类型检查
"""

from typing import Optional, Union, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator
from pydantic.types import confloat, conint
import logging

from services.common.logger import get_logger

logger = get_logger('config_validation')

class DeviceType(str, Enum):
    """支持的设备类型"""
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"

class ComputeType(str, Enum):
    """支持的计算类型"""
    FLOAT32 = "float32"
    FLOAT16 = "float16"
    INT8 = "int8"
    INT16 = "int16"

class ModelName(str, Enum):
    """支持的模型名称"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"

class LanguageCode(str, Enum):
    """支持的语言代码"""
    ZH = "zh"
    EN = "en"
    JA = "ja"
    KO = "ko"
    FR = "fr"
    DE = "de"
    ES = "es"
    IT = "it"
    PT = "pt"
    RU = "ru"
    AUTO = "auto"

class WhisperxServiceConfig(BaseModel):
    """faster-whisper 服务配置验证模型"""

    # 基础配置
    model_name: ModelName = Field(
        default=ModelName.LARGE_V2,
        description="faster-whisper 模型名称"
    )
    language: LanguageCode = Field(
        default=LanguageCode.ZH,
        description="音频语言代码"
    )
    device: DeviceType = Field(
        default=DeviceType.CUDA,
        description="计算设备类型"
    )
    compute_type: ComputeType = Field(
        default=ComputeType.FLOAT16,
        description="计算精度类型"
    )
    batch_size: conint(gt=0, le=64) = Field(
        default=4,
        description="批处理大小"
    )

    # Faster-Whisper 配置
    use_faster_whisper: bool = Field(
        default=True,
        description="是否使用 Faster-Whisper 后端"
    )
    faster_whisper_threads: conint(gt=0, le=32) = Field(
        default=4,
        description="Faster-Whisper 线程数"
    )
    model_quantization: ComputeType = Field(
        default=ComputeType.FLOAT16,
        description="模型量化类型"
    )

    # 高级配置
    enable_word_timestamps: bool = Field(
        default=True,
        description="是否启用词级时间戳"
    )
    enable_diarization: bool = Field(
        default=False,
        description="是否启用说话人分离"
    )
    audio_sample_rate: conint(gt=0, le=48000) = Field(
        default=16000,
        description="音频采样率"
    )
    audio_channels: conint(gt=0, le=8) = Field(
        default=1,
        description="音频声道数"
    )

    # 性能优化配置
    chunk_size: conint(gt=0, le=1000) = Field(
        default=30,
        description="音频分块大小(秒)"
    )
    stride_size: conint(gt=0, le=1000) = Field(
        default=10,
        description="音频分块重叠大小(秒)"
    )
    temperature: confloat(ge=0.0, le=1.0) = Field(
        default=0.0,
        description="生成温度参数"
    )
    best_of: conint(gt=0, le=10) = Field(
        default=5,
        description="最佳候选数量"
    )
    beam_size: conint(gt=0, le=10) = Field(
        default=5,
        description="束搜索大小"
    )

    # 内存管理配置
    memory_threshold_mb: confloat(ge=100.0, le=50000.0) = Field(
        default=4000.0,
        description="内存阈值(MB)"
    )
    enable_memory_optimization: bool = Field(
        default=True,
        description="是否启用内存优化"
    )

    # 配置验证器
    @validator('batch_size')
    def validate_batch_size(cls, v, values):
        """验证批处理大小"""
        device = values.get('device')
        compute_type = values.get('compute_type')

        if device == DeviceType.CPU:
            if v > 8:
                raise ValueError("CPU设备批处理大小不应超过8")
        elif device == DeviceType.CUDA:
            if compute_type == ComputeType.FLOAT32 and v > 16:
                raise ValueError("FLOAT32精度下批处理大小不应超过16")
            elif compute_type == ComputeType.FLOAT16 and v > 32:
                raise ValueError("FLOAT16精度下批处理大小不应超过32")

        return v

    @validator('faster_whisper_threads')
    def validate_faster_whisper_threads(cls, v, values):
        """验证 Faster-Whisper 线程数"""
        device = values.get('device')

        if device == DeviceType.CPU:
            if v > 8:
                raise ValueError("CPU设备Faster-Whisper线程数不应超过8")
        elif device == DeviceType.CUDA:
            if v > 16:
                raise ValueError("CUDA设备Faster-Whisper线程数不应超过16")

        return v

    @validator('chunk_size')
    def validate_chunk_size(cls, v, values):
        """验证音频分块大小"""
        stride_size = values.get('stride_size')

        if stride_size and v <= stride_size:
            raise ValueError("分块大小必须大于重叠大小")

        return v

    @validator('stride_size')
    def validate_stride_size(cls, v, values):
        """验证重叠大小"""
        chunk_size = values.get('chunk_size')

        if chunk_size and v >= chunk_size:
            raise ValueError("重叠大小必须小于分块大小")

        return v

    @root_validator(skip_on_failure=True)
    def validate_configuration_consistency(cls, values):
        """验证配置一致性"""
        device = values.get('device')
        compute_type = values.get('compute_type')
        use_faster_whisper = values.get('use_faster_whisper')

        # 检查设备与计算类型的兼容性
        if device == DeviceType.CPU and compute_type == ComputeType.FLOAT16:
            logger.warning("CPU设备使用FLOAT16精度可能导致性能下降")

        # 检查 Faster-Whisper 与设备的兼容性
        if use_faster_whisper and device == DeviceType.MPS:
            logger.warning("Faster-Whisper 在 MPS 设备上的支持有限")

        # 检查模型大小与内存的兼容性
        model_name = values.get('model_name')
        memory_threshold = values.get('memory_threshold_mb')

        if model_name in [ModelName.LARGE, ModelName.LARGE_V2, ModelName.LARGE_V3]:
            if memory_threshold < 2000:
                raise ValueError("大型模型需要至少2000MB内存阈值")

        return values

    class Config:
        """Pydantic 配置"""
        use_enum_values = True
        validate_assignment = True
        extra = 'forbid'  # 禁止额外字段
        allow_mutation = True

class WhisperxConfigManager:
    """faster-whisper 配置管理器"""

    def __init__(self):
        self._config: Optional[WhisperxServiceConfig] = None
        self._lock = None
        try:
            import threading
            self._lock = threading.RLock()
        except ImportError:
            pass

    def load_config(self, config_dict: Dict[str, Any]) -> WhisperxServiceConfig:
        """加载并验证配置"""
        try:
            if self._lock:
                with self._lock:
                    config = WhisperxServiceConfig(**config_dict)
                    self._config = config
            else:
                config = WhisperxServiceConfig(**config_dict)
                self._config = config

            logger.info("配置验证成功")
            logger.info(f"模型: {config.model_name}")
            logger.info(f"设备: {config.device}")
            logger.info(f"计算类型: {config.compute_type}")
            logger.info(f"批处理大小: {config.batch_size}")
            logger.info(f"Faster-Whisper: {config.use_faster_whisper}")

            return config

        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            raise ValueError(f"无效的配置: {e}")

    def get_config(self) -> WhisperxServiceConfig:
        """获取当前配置"""
        if self._config is None:
            raise ValueError("配置未加载")
        return self._config

    def update_config(self, updates: Dict[str, Any]) -> WhisperxServiceConfig:
        """更新配置"""
        if self._config is None:
            raise ValueError("配置未加载")

        try:
            if self._lock:
                with self._lock:
                    current_dict = self._config.dict()
                    current_dict.update(updates)
                    self._config = WhisperxServiceConfig(**current_dict)
            else:
                current_dict = self._config.dict()
                current_dict.update(updates)
                self._config = WhisperxServiceConfig(**current_dict)

            logger.info("配置更新成功")
            return self._config

        except Exception as e:
            logger.error(f"配置更新失败: {e}")
            raise ValueError(f"配置更新失败: {e}")

    def validate_config_dict(self, config_dict: Dict[str, Any]) -> bool:
        """验证配置字典是否有效"""
        try:
            WhisperxServiceConfig(**config_dict)
            return True
        except Exception:
            return False

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式"""
        return WhisperxServiceConfig.schema()

    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return WhisperxServiceConfig().dict()

    def get_config_diff(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """获取配置差异"""
        if self._config is None:
            return new_config

        current_dict = self._config.dict()
        diff = {}

        for key, value in new_config.items():
            if key not in current_dict or current_dict[key] != value:
                diff[key] = {
                    'old': current_dict.get(key),
                    'new': value
                }

        return diff

# 全局配置管理器实例
config_manager = WhisperxConfigManager()

def get_config_manager() -> WhisperxConfigManager:
    """获取配置管理器实例"""
    return config_manager

def load_and_validate_config(config_dict: Dict[str, Any]) -> WhisperxServiceConfig:
    """加载并验证配置的便利函数"""
    return config_manager.load_config(config_dict)

def get_current_config() -> WhisperxServiceConfig:
    """获取当前配置的便利函数"""
    return config_manager.get_config()

# 配置验证装饰器
def validate_config(func):
    """配置验证装饰器"""
    def wrapper(*args, **kwargs):
        try:
            config = get_current_config()
            return func(config, *args, **kwargs)
        except ValueError as e:
            logger.error(f"配置验证失败: {e}")
            raise
    return wrapper

if __name__ == "__main__":
    # 测试配置验证
    test_config = {
        "model_name": "large-v2",
        "language": "zh",
        "device": "cuda",
        "compute_type": "float16",
        "batch_size": 4,
        "use_faster_whisper": True,
        "faster_whisper_threads": 4,
        "enable_word_timestamps": True,
        "enable_diarization": False
    }

    try:
        config = load_and_validate_config(test_config)
        print("配置验证成功!")
        print(f"模型: {config.model_name}")
        print(f"设备: {config.device}")
        print(f"批处理大小: {config.batch_size}")
    except Exception as e:
        print(f"配置验证失败: {e}")