# services/workers/common/decoders/base_decoder.py
# -*- coding: utf-8 -*-

"""
统一解码器基类

为所有解码器提供通用功能和接口定义
"""

import gc
from abc import ABC, abstractmethod
from typing import Dict, Any, Generator, Tuple, Optional, List
import torch
import numpy as np

from services.common.logger import get_logger

logger = get_logger('base_decoder')


class BaseDecoder(ABC):
    """
    统一解码器抽象基类

    提供所有解码器的通用功能：
    - 统一的初始化和配置管理
    - GPU资源管理
    - 内存优化
    - 进度显示
    - 错误处理
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化基础解码器

        Args:
            config: 解码器配置字典
        """
        self.config = config
        self.device = self._get_device()
        self._validate_common_config()

        # 通用配置验证和设置
        self.batch_size = config.get('batch_size', 32)
        self.frame_memory_estimate_mb = config.get('frame_memory_estimate_mb', 0.307)
        self.progress_interval_frames = config.get('progress_interval_frames', 1000)
        self.progress_interval_batches = config.get('progress_interval_batches', 50)

        # 初始化统计信息
        self.stats = {
            'frames_processed': 0,
            'batches_processed': 0,
            'gpu_memory_errors': 0,
            'start_time': None,
            'total_frames': 0,
            'decoding_errors': 0
        }

        logger.info(f"{self.__class__.__name__} 初始化完成 - 设备: {self.device}")

    def _get_device(self) -> str:
        """获取计算设备"""
        return 'cuda' if torch.cuda.is_available() else 'cpu'

    def _validate_common_config(self):
        """验证通用配置参数"""
        # 检查必要的配置项
        required_configs = []
        for config_key in required_configs:
            if config_key not in self.config:
                raise ValueError(f"缺少必要配置项: {config_key}")

    @abstractmethod
    def decode(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        抽象解码方法

        Args:
            video_path: 视频文件路径
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        pass

    @abstractmethod
    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息字典
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, bool]:
        """
        获取解码器能力

        Returns:
            能力字典
        """
        pass

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
                       f"GPU错误={self.stats['gpu_memory_errors']}, "
                       f"解码错误={self.stats['decoding_errors']}")

        # 最终内存优化
        self._optimize_gpu_memory()

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
            'start_time': None,
            'total_frames': 0,
            'decoding_errors': 0
        }

    def get_decoder_name(self) -> str:
        """
        获取解码器名称

        Returns:
            解码器名称
        """
        return self.__class__.__name__

    def validate_video_file(self, video_path: str) -> bool:
        """
        验证视频文件

        Args:
            video_path: 视频文件路径

        Returns:
            文件是否有效
        """
        import os
        if not os.path.exists(video_path):
            logger.error(f"视频文件不存在: {video_path}")
            return False

        if not os.path.isfile(video_path):
            logger.error(f"路径不是文件: {video_path}")
            return False

        # 检查文件大小
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            logger.error(f"视频文件为空: {video_path}")
            return False

        return True

    def process_batch(self, batch_data: Any) -> torch.Tensor:
        """
        处理批次数据（子类可重写此方法）

        Args:
            batch_data: 批次数据

        Returns:
            处理后的张量
        """
        # 默认实现：直接返回数据
        return batch_data

    def __del__(self):
        """析构函数，确保资源释放"""
        try:
            self._optimize_gpu_memory()
        except:
            pass


class DecoderCapability:
    """解码器能力常量"""
    GPU_ACCELERATION = "gpu_acceleration"
    CONCURRENT_PROCESSING = "concurrent_processing"
    BATCH_PROCESSING = "batch_processing"
    MEMORY_OPTIMIZATION = "memory_optimization"
    HARDWARE_DECODING = "hardware_decoding"
    MULTI_FORMAT_SUPPORT = "multi_format_support"
    SEEK_SUPPORT = "seek_support"
    METADATA_EXTRACTION = "metadata_extraction"