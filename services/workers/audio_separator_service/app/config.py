#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - 配置管理模块
功能：加载和验证音频分离服务的配置参数
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator


class AudioSeparatorConfig(BaseModel):
    """音频分离服务配置模型"""

    # ========================================
    # 模型类型选择
    # ========================================
    model_type: str = Field(
        default="mdx",
        description="模型类型 (mdx/demucs)"
    )

    # ========================================
    # MDX 模型配置
    # ========================================
    default_model: str = Field(
        default="UVR-MDX-NET-Inst_HQ_5.onnx",
        description="默认使用的 UVR-MDX 模型"
    )

    high_quality_model: str = Field(
        default="UVR-MDX-NET-Voc_FT.onnx",
        description="高质量模型（人声专用优化）"
    )

    fast_model: str = Field(
        default="UVR-MDX-NET-Inst_3.onnx",
        description="快速模型（质量稍低）"
    )

    vocal_optimization_model: str = Field(
        default="UVR-MDX-NET-Voc_FT.onnx",
        description="人声专用优化模型（推荐用于人声分离）"
    )

    models_dir: str = Field(
        default="/models/uvr_mdx",
        description="模型文件存储目录 - 映射到宿主机避免重复下载"
    )
    
    # ========================================
    # Demucs 模型配置
    # ========================================
    demucs_default_model: str = Field(
        default="htdemucs",
        description="默认使用的 Demucs 模型"
    )

    demucs_fast_model: str = Field(
        default="mdx_extra_q",
        description="快速 Demucs 模型"
    )

    demucs_balanced_model: str = Field(
        default="htdemucs",
        description="平衡 Demucs 模型"
    )

    demucs_high_quality_model: str = Field(
        default="htdemucs_6s",
        description="高质量 Demucs 模型 (6-stem)"
    )

    demucs_models_dir: str = Field(
        default="/models/demucs",
        description="Demucs模型文件存储目录"
    )

    # ========================================
    # GPU 配置
    # ========================================
    use_gpu: bool = Field(
        default=True,
        description="是否使用 GPU 加速"
    )

    gpu_id: int = Field(
        default=0,
        description="使用的 GPU 设备 ID"
    )

    enable_gpu_lock: bool = Field(
        default=True,
        description="是否启用 GPU 锁机制"
    )

    # ========================================
    # 输出配置
    # ========================================
    output_format: str = Field(
        default="flac",
        description="输出音频格式（flac/wav/mp3）"
    )

    output_dir: str = Field(
        default="/share/workflows/audio_separated",
        description="分离后音频文件存储目录（工作流中间数据）"
    )

    normalization_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="音频归一化阈值"
    )

    # ========================================
    # 性能配置
    # ========================================
    mdx_segment_size: int = Field(
        default=256,  # 改回更安全的默认值
        description="MDX 模型分段大小（留空让模型使用默认值）"
    )

    mdx_batch_size: int = Field(
        default=1,
        description="MDX 模型批处理大小"
    )

    enable_tta: bool = Field(
        default=False,
        description="是否启用 Test-Time Augmentation（提高质量但降低速度）"
    )
    
    # ========================================
    # Demucs 模型参数
    # ========================================
    demucs_segment: str = Field(
        default="default",
        description="Demucs模型分段大小"
    )

    demucs_shifts: int = Field(
        default=2,
        description="Demucs模型shifts参数"
    )

    demucs_workers: int = Field(
        default=1,
        description="Demucs模型工作进程数"
    )

    demucs_gpu_id: int = Field(
        default=0,
        description="Demucs模型GPU设备ID"
    )

    # ========================================
    # 人声分离优化配置
    # ========================================
    vocal_optimization_level: str = Field(
        default="balanced",
        description="人声分离优化级别 (fast/balanced/quality)"
    )

    vocal_optimization_model: str = Field(
        default="UVR-MDX-NET-Inst_HQ_5.onnx",
        description="专门用于人声分离优化的模型"
    )

    # 人声分离优化参数
    vocal_fast_params: Dict[str, Any] = Field(
        default={
            "hop_length": 1024,
            "enable_denoise": False,
            "segment_size": 256,
            "overlap": 0.25,
        },
        description="快速模式人声分离参数"
    )

    vocal_balanced_params: Dict[str, Any] = Field(
        default={
            "hop_length": 512,
            "enable_denoise": True,
            "segment_size": 128,
            "overlap": 0.25,
        },
        description="平衡模式人声分离参数"
    )

    vocal_quality_params: Dict[str, Any] = Field(
        default={
            "hop_length": 256,
            "enable_denoise": True,
            "segment_size": 64,
            "overlap": 0.5,
            "batch_size": 1,
        },
        description="质量模式人声分离参数"
    )

    # ========================================
    # 文件管理配置
    # ========================================
    cleanup_temp_files: bool = Field(
        default=True,
        description="是否自动清理临时文件"
    )

    preserve_background: bool = Field(
        default=True,
        description="是否保留背景音文件（用于后续视频合成）"
    )

    file_retention_days: int = Field(
        default=7,
        description="分离文件保留天数"
    )

    # ========================================
    # 监控配置
    # ========================================
    enable_monitoring: bool = Field(
        default=True,
        description="是否启用性能监控"
    )

    log_level: str = Field(
        default="INFO",
        description="日志级别"
    )

    @validator('output_format')
    def validate_output_format(cls, v):
        """验证输出格式"""
        allowed_formats = ['flac', 'wav', 'mp3', 'ogg']
        if v.lower() not in allowed_formats:
            raise ValueError(f"output_format 必须是以下之一: {allowed_formats}")
        return v.lower()

    @validator('models_dir', 'output_dir')
    def validate_directory(cls, v):
        """验证目录路径并自动创建"""
        path = Path(v)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @validator('gpu_id')
    def validate_gpu_id(cls, v):
        """验证GPU ID"""
        if v < 0:
            raise ValueError('GPU ID 不能为负数')
        return v

    @validator('mdx_segment_size')
    def validate_segment_size(cls, v):
        """验证分段大小"""
        if v <= 0 or v > 1024:
            raise ValueError('MDX 分段大小必须在 1-1024 之间')
        return v

    @validator('mdx_batch_size')
    def validate_batch_size(cls, v):
        """验证批处理大小"""
        if v <= 0 or v > 16:
            raise ValueError('MDX 批处理大小必须在 1-16 之间')
        return v

    @validator('default_model', 'high_quality_model', 'fast_model', 'vocal_optimization_model')
    def validate_model_name(cls, v):
        """验证模型文件名"""
        if not v or not v.strip():
            raise ValueError('模型名称不能为空')
        if not v.endswith(('.onnx', '.pth', '.ckpt')):
            raise ValueError('模型文件必须以 .onnx, .pth 或 .ckpt 结尾')
        return v.strip()


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径，默认为项目根目录的 config.yml
        """
        if config_path is None:
            # 默认配置文件路径
            config_path = os.path.join(
                os.path.dirname(__file__),
                "../../../../config.yml"
            )

        self.config_path = Path(config_path).resolve()
        self._config_data: Optional[Dict[str, Any]] = None
        self._audio_separator_config: Optional[AudioSeparatorConfig] = None

    def load(self) -> AudioSeparatorConfig:
        """
        加载配置文件

        Returns:
            AudioSeparatorConfig: 验证后的配置对象
        """
        if self._audio_separator_config is not None:
            return self._audio_separator_config

        # 读取 YAML 配置文件
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_data = yaml.safe_load(f)
        else:
            print(f"警告: 配置文件 {self.config_path} 不存在，使用默认配置")
            self._config_data = {}

        # 提取 audio_separator_service 配置
        service_config = self._config_data.get('audio_separator_service', {})

        # 使用 Pydantic 验证配置
        self._audio_separator_config = AudioSeparatorConfig(**service_config)

        return self._audio_separator_config

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        if self._audio_separator_config is None:
            self.load()

        return getattr(self._audio_separator_config, key, default)


# ========================================
# 全局配置实例
# ========================================
_config_loader = ConfigLoader()


def get_config() -> AudioSeparatorConfig:
    """
    获取音频分离服务配置

    Returns:
        AudioSeparatorConfig: 配置对象
    """
    return _config_loader.load()


def reload_config() -> AudioSeparatorConfig:
    """
    重新加载配置（用于配置热更新）

    Returns:
        AudioSeparatorConfig: 新的配置对象
    """
    global _config_loader
    _config_loader = ConfigLoader()
    return _config_loader.load()


if __name__ == "__main__":
    # 测试配置加载
    config = get_config()
    print("音频分离服务配置:")
    print(config.model_dump_json(indent=2))
