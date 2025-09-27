# services/workers/common/decoders/decoder_factory.py
# -*- coding: utf-8 -*-

"""
解码器工厂

根据视频特性和系统资源自动选择最佳解码器
"""

import os
import torch
from multiprocessing import cpu_count
from typing import Dict, Any, Type, Optional, List
from pathlib import Path

from services.common.logger import get_logger
from .base_decoder import BaseDecoder
from .video_info import get_video_info
from .gpu_decoder import GPUDecoder
from .cpu_decoder import CPUDecoder
from .concurrent_decoder import ConcurrentDecoder

logger = get_logger('decoder_factory')


class DecoderFactory:
    """
    解码器工厂类

    根据视频特性和系统资源自动选择最合适的解码器
    """

    _decoders: Dict[str, Type[BaseDecoder]] = {}
    _decoder_configs: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register_decoder(cls, name: str, decoder_class: Type[BaseDecoder],
                        default_config: Dict[str, Any] = None):
        """
        注册解码器类型

        Args:
            name: 解码器名称
            decoder_class: 解码器类
            default_config: 默认配置
        """
        cls._decoders[name] = decoder_class
        cls._decoder_configs[name] = default_config or {}
        logger.info(f"注册解码器: {name} - {decoder_class.__name__}")

    @classmethod
    def create_decoder(cls, decoder_type: str, config: Dict[str, Any] = None) -> BaseDecoder:
        """
        创建指定类型的解码器

        Args:
            decoder_type: 解码器类型
            config: 配置字典

        Returns:
            解码器实例
        """
        if decoder_type not in cls._decoders:
            available_types = list(cls._decoders.keys())
            raise ValueError(f"不支持的解码器类型: {decoder_type}. 可用类型: {available_types}")

        # 合并默认配置和用户配置
        final_config = cls._decoder_configs[decoder_type].copy()
        if config:
            final_config.update(config)

        decoder_class = cls._decoders[decoder_type]
        decoder = decoder_class(final_config)

        logger.info(f"创建解码器: {decoder_type} - {decoder.get_decoder_name()}")
        return decoder

    @classmethod
    def auto_select(cls, video_path: str, config: Dict[str, Any] = None) -> BaseDecoder:
        """
        自动选择最佳解码器

        Args:
            video_path: 视频文件路径
            config: 配置字典

        Returns:
            最合适的解码器实例
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 获取视频信息
        try:
            video_info_dict = get_video_info(video_path)
        except Exception as e:
            logger.warning(f"获取视频信息失败: {e}, 使用默认选择策略")
            video_info_dict = {}

        # 分析视频特性
        video_characteristics = cls._analyze_video_characteristics(video_info_dict)

        # 分析系统资源
        system_resources = cls._analyze_system_resources()

        # 选择最佳解码器
        decoder_type = cls._select_best_decoder(video_characteristics, system_resources)

        logger.info(f"自动选择解码器: {decoder_type} (视频: {Path(video_path).name})")
        return cls.create_decoder(decoder_type, config)

    @classmethod
    def _analyze_video_characteristics(cls, video_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析视频特性

        Args:
            video_info: 视频信息字典

        Returns:
            视频特性字典
        """
        characteristics = {
            'duration': video_info.get('duration', 0),
            'frame_count': video_info.get('frame_count', 0),
            'resolution': video_info.get('width', 0) * video_info.get('height', 0),
            'fps': video_info.get('fps', 0),
            'file_size_mb': video_info.get('file_size_mb', 0),
            'is_large_video': False,
            'is_high_fps': False,
            'is_high_resolution': False
        }

        # 判断视频特性
        characteristics['is_large_video'] = (
            characteristics['duration'] > 300 or  # 5分钟以上
            characteristics['frame_count'] > 10000 or  # 1万帧以上
            characteristics['file_size_mb'] > 100  # 100MB以上
        )

        characteristics['is_high_fps'] = characteristics['fps'] > 30

        characteristics['is_high_resolution'] = characteristics['resolution'] > 1920 * 1080  # 1080p以上

        return characteristics

    @classmethod
    def _analyze_system_resources(cls) -> Dict[str, Any]:
        """
        分析系统资源

        Returns:
            系统资源字典
        """
        resources = {
            'has_gpu': False,
            'gpu_memory_mb': 0,
            'cpu_count': os.cpu_count() or 4,
            'memory_gb': 0
        }

        # 检查GPU
        if torch.cuda.is_available():
            resources['has_gpu'] = True
            resources['gpu_memory_mb'] = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)

        # 检查系统内存
        try:
            import psutil
            resources['memory_gb'] = psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except ImportError:
            resources['memory_gb'] = 8  # 默认假设

        return resources

    @classmethod
    def _select_best_decoder(cls, video_characteristics: Dict[str, Any],
                           system_resources: Dict[str, Any]) -> str:
        """
        选择最佳解码器

        Args:
            video_characteristics: 视频特性
            system_resources: 系统资源

        Returns:
            解码器类型
        """
        # 如果有GPU且视频不是特别大，优先使用GPU解码器
        if (system_resources['has_gpu'] and
            not video_characteristics['is_large_video'] and
            'gpu' in cls._decoders):
            return 'gpu'

        # 如果是大视频且有多核CPU，使用并发解码器
        if (video_characteristics['is_large_video'] and
            system_resources['cpu_count'] >= 4 and
            'concurrent' in cls._decoders):
            return 'concurrent'

        # 如果是高分辨率视频，使用优化的CPU解码器
        if (video_characteristics['is_high_resolution'] and
            'optimized_cpu' in cls._decoders):
            return 'optimized_cpu'

        # 默认使用标准CPU解码器
        if 'cpu' in cls._decoders:
            return 'cpu'

        # 如果以上都不可用，使用第一个可用的解码器
        if cls._decoders:
            return next(iter(cls._decoders.keys()))

        raise RuntimeError("没有可用的解码器")

    @classmethod
    def list_available_decoders(cls) -> List[str]:
        """
        列出可用的解码器类型

        Returns:
            可用解码器类型列表
        """
        return list(cls._decoders.keys())

    @classmethod
    def get_decoder_info(cls, decoder_type: str) -> Dict[str, Any]:
        """
        获取解码器信息

        Args:
            decoder_type: 解码器类型

        Returns:
            解码器信息字典
        """
        if decoder_type not in cls._decoders:
            raise ValueError(f"未知的解码器类型: {decoder_type}")

        decoder_class = cls._decoders[decoder_type]
        return {
            'name': decoder_type,
            'class_name': decoder_class.__name__,
            'config': cls._decoder_configs[decoder_type],
            'docstring': decoder_class.__doc__
        }

    @classmethod
    def benchmark_decoders(cls, video_path: str, decoder_types: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        对不同解码器进行基准测试

        Args:
            video_path: 测试视频路径
            decoder_types: 要测试的解码器类型列表

        Returns:
            基准测试结果
        """
        if decoder_types is None:
            decoder_types = cls.list_available_decoders()

        results = {}

        for decoder_type in decoder_types:
            try:
                logger.info(f"开始基准测试: {decoder_type}")
                decoder = cls.create_decoder(decoder_type)

                # 测试解码性能
                import time
                start_time = time.time()
                frame_count = 0

                for batch, _ in decoder.decode(video_path):
                    frame_count += batch.size(0)
                    if frame_count >= 100:  # 只测试前100帧
                        break

                elapsed_time = time.time() - start_time
                fps = frame_count / elapsed_time if elapsed_time > 0 else 0

                results[decoder_type] = {
                    'fps': fps,
                    'elapsed_time': elapsed_time,
                    'frame_count': frame_count,
                    'success': True
                }

                logger.info(f"基准测试完成: {decoder_type} - {fps:.1f} FPS")

            except Exception as e:
                logger.error(f"基准测试失败: {decoder_type} - {e}")
                results[decoder_type] = {
                    'fps': 0,
                    'elapsed_time': 0,
                    'frame_count': 0,
                    'success': False,
                    'error': str(e)
                }

        return results


# 便捷函数
def create_decoder(decoder_type: str, config: Dict[str, Any] = None) -> BaseDecoder:
    """
    创建解码器的便捷函数

    Args:
        decoder_type: 解码器类型
        config: 配置字典

    Returns:
        解码器实例
    """
    return DecoderFactory.create_decoder(decoder_type, config)


def auto_select_decoder(video_path: str, config: Dict[str, Any] = None) -> BaseDecoder:
    """
    自动选择解码器的便捷函数

    Args:
        video_path: 视频文件路径
        config: 配置字典

    Returns:
        最合适的解码器实例
    """
    return DecoderFactory.auto_select(video_path, config)


# 注册内置解码器
def _register_builtin_decoders():
    """注册内置解码器"""
    # GPU解码器配置
    gpu_config = {
        'batch_size': 32,
        'precision': 'fp16',
        'log_progress': False
    }

    # CPU解码器配置
    cpu_config = {
        'batch_size': 16,
        'use_multiprocessing': False,
        'num_workers': 1
    }

    # 并发解码器配置
    concurrent_config = {
        'num_workers': cpu_count(),
        'use_multiprocessing': True,
        'chunk_size': 1000,
        'max_memory_gb': 4.0
    }

    # 注册解码器
    DecoderFactory.register_decoder('gpu', GPUDecoder, gpu_config)
    DecoderFactory.register_decoder('cpu', CPUDecoder, cpu_config)
    DecoderFactory.register_decoder('concurrent', ConcurrentDecoder, concurrent_config)

    logger.info("内置解码器注册完成")


# 自动注册解码器
_register_builtin_decoders()