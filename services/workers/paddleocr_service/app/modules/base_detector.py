# services/workers/paddleocr_service/app/modules/base_detector.py
# -*- coding: utf-8 -*-

"""
基础检测器类

为所有检测器提供通用功能和接口，减少代码重复，提高可维护性。

根据 DETECTOR_ARCHITECTURE_ANALYSIS_REPORT.md 的重构建议实现
"""

import gc
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import torch

from services.common.logger import get_logger

logger = get_logger('base_detector')


class BaseDetector(ABC):
    """
    基础检测器抽象类

    提供所有检测器的通用功能：
    - 统一的初始化和配置管理
    - GPU资源管理
    - 内存优化
    - 进度显示
    - 错误处理
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化基础检测器

        Args:
            config: 检测器配置字典
        """
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        # 通用配置验证和设置
        self._validate_common_config()

        # GPU内存管理配置
        self.frame_memory_estimate_mb = config.get('frame_memory_estimate_mb', 0.307)
        self.progress_interval_frames = config.get('progress_interval_frames', 1000)
        self.progress_interval_batches = config.get('progress_interval_batches', 50)

        # 初始化统计信息
        self.stats = {
            'frames_processed': 0,
            'batches_processed': 0,
            'gpu_memory_errors': 0,
            'start_time': None
        }

        logger.info(f"{self.__class__.__name__} 初始化完成 - 设备: {self.device}")

    def _validate_common_config(self):
        """验证通用配置参数"""
        # 检查必要的配置项
        required_configs = []
        for config_key in required_configs:
            if config_key not in self.config:
                raise ValueError(f"缺少必要配置项: {config_key}")

    def _log_progress(self, current: int, total: int, stage: str = "处理"):
        """
        记录进度信息

        Args:
            current: 当前进度
            total: 总数
            stage: 处理阶段描述
        """
        if current % self.progress_interval_frames == 0:
            progress = (current / total) * 100
            logger.info(f"📊 {stage}进度: {current}/{total} ({progress:.1f}%)")

    def _log_batch_progress(self, batch_count: int, frame_count: int, additional_info: str = ""):
        """
        记录批次处理进度

        Args:
            batch_count: 批次数量
            frame_count: 帧数量
            additional_info: 附加信息
        """
        if batch_count % self.progress_interval_batches == 0:
            info = f"批次: {batch_count}, 帧: {frame_count}"
            if additional_info:
                info += f", {additional_info}"
            logger.info(f"  📊 已处理 {info}")

    def _optimize_gpu_memory(self):
        """优化GPU内存使用"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # 强制垃圾回收
        gc.collect()

    def _safe_gpu_operation(self, operation_func, *args, **kwargs):
        """
        安全执行GPU操作，处理内存不足异常

        Args:
            operation_func: 要执行的操作函数
            *args, **kwargs: 操作函数的参数

        Returns:
            操作结果或None（如果失败）
        """
        try:
            return operation_func(*args, **kwargs)
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                self.stats['gpu_memory_errors'] += 1
                logger.warning(f"⚠️ GPU内存不足，跳过操作: {e}")
                self._optimize_gpu_memory()
                return None
            else:
                raise e

    def _estimate_memory_usage(self, frame_count: int) -> float:
        """
        估算内存使用量

        Args:
            frame_count: 帧数量

        Returns:
            估算的内存使用量(MB)
        """
        return frame_count * self.frame_memory_estimate_mb

    def _start_processing(self):
        """开始处理前的准备工作"""
        import time
        self.stats['start_time'] = time.time()
        logger.info(f"🚀 开始 {self.__class__.__name__} 处理")

    def _finish_processing(self):
        """完成处理后的清理工作"""
        import time
        if self.stats['start_time']:
            duration = time.time() - self.stats['start_time']
            logger.info(f"✅ {self.__class__.__name__} 处理完成")
            logger.info(f"⏱️  处理时间: {duration:.2f}秒")
            logger.info(f"📊 处理统计: 帧={self.stats['frames_processed']}, "
                       f"批次={self.stats['batches_processed']}, "
                       f"GPU错误={self.stats['gpu_memory_errors']}")

        # 最终内存优化
        self._optimize_gpu_memory()

    @abstractmethod
    def detect(self, video_path: str, *args, **kwargs) -> Any:
        """
        抽象检测方法

        所有子类必须实现此方法

        Args:
            video_path: 视频文件路径
            *args, **kwargs: 其他参数

        Returns:
            检测结果
        """
        pass

    @abstractmethod
    def get_detector_name(self) -> str:
        """
        获取检测器名称

        Returns:
            检测器名称
        """
        pass

    def get_stats(self) -> Dict[str, Any]:
        """
        获取处理统计信息

        Returns:
            统计信息字典
        """
        return self.stats.copy()

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'frames_processed': 0,
            'batches_processed': 0,
            'gpu_memory_errors': 0,
            'start_time': None
        }


class GPUDecorator:
    """
    GPU操作装饰器，为检测器提供GPU内存保护
    """

    def __init__(self, detector_instance):
        self.detector = detector_instance

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            return self.detector._safe_gpu_operation(func, *args, **kwargs)
        return wrapper


class ConfigManager:
    """
    配置管理器，提供统一的配置验证和管理功能
    """

    @staticmethod
    def validate_config(config: Dict[str, Any], required_keys: List[str],
                       optional_keys: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        验证和规范化配置

        Args:
            config: 原始配置
            required_keys: 必需的配置键
            optional_keys: 可选配置键及其默认值

        Returns:
            验证后的配置
        """
        validated_config = config.copy()

        # 检查必需键
        for key in required_keys:
            if key not in validated_config:
                raise ValueError(f"缺少必需配置项: {key}")

        # 设置可选键的默认值
        if optional_keys:
            for key, default_value in optional_keys.items():
                validated_config.setdefault(key, default_value)

        return validated_config

    @staticmethod
    def validate_range(value: Any, min_val: Any, max_val: Any, name: str) -> Any:
        """
        验证数值范围

        Args:
            value: 要验证的值
            min_val: 最小值
            max_val: 最大值
            name: 参数名称

        Returns:
            验证后的值
        """
        if not (min_val <= value <= max_val):
            raise ValueError(f"{name}必须在{min_val}和{max_val}之间，当前值: {value}")
        return value


class ProgressTracker:
    """
    进度跟踪器，提供统一的进度显示功能
    """

    def __init__(self, total_items: int, name: str = "处理"):
        self.total_items = total_items
        self.name = name
        self.processed_items = 0
        self.start_time = None

    def start(self):
        """开始跟踪"""
        import time
        self.start_time = time.time()
        logger.info(f"🚀 开始 {self.name}")

    def update(self, increment: int = 1, additional_info: str = ""):
        """
        更新进度

        Args:
            increment: 增量
            additional_info: 附加信息
        """
        self.processed_items += increment

        if self.processed_items % 1000 == 0:  # 每1000项显示一次
            progress = (self.processed_items / self.total_items) * 100
            info = f"进度: {self.processed_items}/{self.total_items} ({progress:.1f}%)"
            if additional_info:
                info += f" - {additional_info}"
            logger.info(f"📊 {self.name} {info}")

    def finish(self):
        """完成跟踪"""
        import time
        if self.start_time:
            duration = time.time() - self.start_time
            logger.info(f"✅ {self.name} 完成 - 耗时: {duration:.2f}秒")