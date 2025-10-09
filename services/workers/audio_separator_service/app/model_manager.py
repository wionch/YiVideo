#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - 模型管理器
功能：线程安全的 UVR-MDX 模型加载和管理
"""

import os
import time
import threading
import logging
from typing import Optional, Dict
from pathlib import Path
from audio_separator.separator import Separator

from .config import get_config, AudioSeparatorConfig

# 配置日志
logger = logging.getLogger(__name__)


class ModelManager:
    """
    UVR-MDX 模型管理器

    功能：
    1. 线程安全的模型单例管理
    2. 模型懒加载和缓存
    3. 模型健康检查
    4. 模型切换支持
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化模型管理器"""
        if self._initialized:
            return

        with self._lock:
            if not self._initialized:
                self.config: AudioSeparatorConfig = get_config()
                self._separators: Dict[str, Separator] = {}
                self._current_model: Optional[str] = None
                self._initialized = True

                logger.info("ModelManager 初始化完成")

    def _create_separator(self, model_name: str) -> Separator:
        """
        创建新的 Separator 实例（带重试机制）

        Args:
            model_name: 模型文件名

        Returns:
            Separator: 音频分离器实例

        Raises:
            RuntimeError: 模型加载失败
            FileNotFoundError: 模型文件不存在
        """
        logger.info(f"创建新的 Separator 实例，模型: {model_name}")

        # 验证模型文件是否存在
        model_path = Path(self.config.models_dir) / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        # 确保参数不为None，防止出现 'NoneType' and 'int' 错误
        segment_size = self.config.mdx_segment_size or 256
        batch_size = self.config.mdx_batch_size or 1
        normalization_threshold = self.config.normalization_threshold or 0.9

        logger.info(f"使用参数: segment_size={segment_size}, batch_size={batch_size}, normalization_threshold={normalization_threshold}")

        max_retries = 3
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                # 创建 Separator 实例
                # 注意：audio-separator 会自动检测 CUDA 并启用 GPU 加速
                separator = Separator(
                    log_level=logging.getLevelName(self.config.log_level),
                    model_file_dir=self.config.models_dir,
                    output_dir=self.config.output_dir,
                    output_format=self.config.output_format,
                    normalization_threshold=normalization_threshold,
                    # 使用完整的参数配置，确保所有参数都有明确的默认值
                    mdx_params={
                        "hop_length": 1024,           # 明确设置 hop_length
                        "segment_size": segment_size,  # 使用配置的 segment_size，避免 None 错误
                        "batch_size": batch_size,      # 使用配置的 batch_size，避免 None 错误
                        "overlap": 0.25,               # 明确设置 overlap，避免 None 错误
                        "enable_denoise": False,       # 明确设置降噪参数
                        "chunk_size": 261120,          # UVR5 标准配置，避免 None 错误
                        "dim_f": 6144,                 # UVR5 标准配置，避免 None 错误
                        "n_fft": 12288,                # UVR5 标准配置，避免 None 错误
                    },
                )

                # 加载模型
                logger.info(f"加载模型: {model_name} (尝试 {attempt + 1}/{max_retries})")
                separator.load_model(model_name)

                logger.info(f"模型 {model_name} 加载成功")
                return separator

            except Exception as e:
                logger.warning(f"模型 {model_name} 加载失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")

                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error(f"模型 {model_name} 加载最终失败")
                    raise RuntimeError(f"无法加载模型 {model_name}: {str(e)}")

    def get_separator(self, model_name: Optional[str] = None) -> Separator:
        """
        获取 Separator 实例（线程安全）

        Args:
            model_name: 模型名称，默认使用配置文件中的默认模型

        Returns:
            Separator: 音频分离器实例
        """
        if model_name is None:
            model_name = self.config.default_model

        with self._lock:
            # 如果模型已缓存，直接返回
            if model_name in self._separators:
                logger.debug(f"使用缓存的模型: {model_name}")
                return self._separators[model_name]

            # 创建新的 Separator 并缓存
            separator = self._create_separator(model_name)
            self._separators[model_name] = separator
            self._current_model = model_name

            return separator

    def separate_audio(
        self,
        audio_path: str,
        model_name: Optional[str] = None,
        output_dir: Optional[str] = None,
        model_type: Optional[str] = None
    ) -> Dict[str, str]:
        """
        分离音频文件（支持MDX和Demucs模型）

        Args:
            audio_path: 输入音频文件路径
            model_name: 使用的模型名称
            output_dir: 输出目录（可选）
            model_type: 模型类型（mdx/demucs）

        Returns:
            Dict[str, str]: 分离结果，包含 vocals 和 instrumental 路径
        """
        # 验证输入文件
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 确定模型类型
        if model_type is None:
            model_type = self.config.model_type
        
        # 根据模型类型选择分离方法
        if model_type.lower() == "demucs":
            return self._separate_audio_demucs(audio_path, model_name, output_dir)
        else:  # 默认使用MDX
            return self._separate_audio_mdx(audio_path, model_name, output_dir)
    
    def _separate_audio_mdx(
        self,
        audio_path: str,
        model_name: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        使用MDX模型分离音频（原有逻辑）
        
        Args:
            audio_path: 输入音频文件路径
            model_name: 使用的模型名称
            output_dir: 输出目录（可选）
            
        Returns:
            Dict[str, str]: 分离结果，包含 vocals 和 instrumental 路径
        """
        # 确定模型名称
        if model_name is None:
            model_name = self.config.default_model

        # 确定输出目录
        if output_dir is None:
            output_dir = self.config.output_dir

        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 为每个任务创建独立的 Separator 实例（避免并发问题）
        logger.info(f"创建新的 Separator 实例用于本次分离任务")
        
        # 确保参数不为None，防止出现 'NoneType' and 'int' 错误
        segment_size = self.config.mdx_segment_size or 256
        batch_size = self.config.mdx_batch_size or 1
        normalization_threshold = self.config.normalization_threshold or 0.9
        
        logger.info(f"使用参数: segment_size={segment_size}, batch_size={batch_size}, normalization_threshold={normalization_threshold}")
        
        separator = Separator(
            log_level=logging.getLevelName(self.config.log_level),
            model_file_dir=self.config.models_dir,
            output_dir=output_dir,  # 直接使用指定的输出目录
            output_format=self.config.output_format,
            normalization_threshold=normalization_threshold,
            # 使用完整的参数配置，确保所有参数都有明确的默认值
            mdx_params={
                "hop_length": 1024,           # 明确设置 hop_length
                "segment_size": segment_size,  # 使用配置的 segment_size，避免 None 错误
                "batch_size": batch_size,      # 使用配置的 batch_size，避免 None 错误
                "overlap": 0.25,               # 明确设置 overlap，避免 None 错误
                "enable_denoise": False,       # 明确设置降噪参数
                "chunk_size": 261120,          # UVR5 标准配置，避免 None 错误
                "dim_f": 6144,                 # UVR5 标准配置，避免 None 错误
                "n_fft": 12288,                # UVR5 标准配置，避免 None 错误
            },
        )

        try:
            logger.info(f"开始分离音频: {audio_path}")
            logger.info(f"使用模型: {model_name}")
            logger.info(f"输出目录: {output_dir}")
            logger.info(f"使用的MDX参数: segment_size={segment_size}, batch_size={batch_size}, overlap=0.25")

            # 加载模型
            logger.info(f"正在加载模型: {model_name}")
            separator.load_model(model_name)
            logger.info(f"模型加载成功: {model_name}")

            # 执行分离
            logger.info(f"开始执行音频分离...")
            output_files = separator.separate(audio_path)
            logger.info(f"音频分离完成，输出文件: {output_files}")

            # 检查输出结果
            if not output_files or len(output_files) == 0:
                raise RuntimeError(
                    f"音频分离失败：未生成任何输出文件。"
                    f"请检查日志以获取详细错误信息。"
                )

            # 解析输出文件（传递 output_dir 用于构建绝对路径）
            result = self._parse_output_files(output_files, output_dir)

            # 验证结果包含必需的文件
            if not result['vocals'] or not result['instrumental']:
                raise RuntimeError(
                    f"音频分离结果不完整：vocals={result['vocals']}, "
                    f"instrumental={result['instrumental']}"
                )

            return result

        except Exception as e:
            logger.error(f"音频分离失败: {str(e)}", exc_info=True)
            raise

    def _parse_output_files(self, output_files: list, output_dir: str = None) -> Dict[str, str]:
        """
        解析输出文件列表，将相对路径转换为绝对路径

        Args:
            output_files: Separator 返回的输出文件列表（可能是相对路径）
            output_dir: 输出目录（用于构建绝对路径）

        Returns:
            Dict[str, str]: 包含 vocals 和 instrumental 的绝对路径字典
        """
        result = {
            'vocals': None,
            'instrumental': None
        }

        for file_path in output_files:
            # 如果是相对路径，转换为绝对路径
            if not Path(file_path).is_absolute() and output_dir:
                file_path = str(Path(output_dir) / file_path)

            file_name = Path(file_path).name.lower()

            if 'vocal' in file_name or 'voice' in file_name:
                result['vocals'] = file_path
            elif 'instrumental' in file_name or 'inst' in file_name or 'no_vocal' in file_name:
                result['instrumental'] = file_path

        # 验证结果
        if result['vocals'] is None or result['instrumental'] is None:
            logger.warning(f"无法识别输出文件类型: {output_files}")
            # 备用逻辑：假设第一个文件是人声，第二个是伴奏
            if len(output_files) >= 2:
                file1 = output_files[0] if Path(output_files[0]).is_absolute() else str(Path(output_dir) / output_files[0])
                file2 = output_files[1] if Path(output_files[1]).is_absolute() else str(Path(output_dir) / output_files[1])
                result['vocals'] = file1
                result['instrumental'] = file2

        return result

    def list_available_models(self) -> list:
        """
        列出所有可用的模型

        Returns:
            list: 可用模型列表
        """
        models_dir = Path(self.config.models_dir)

        if not models_dir.exists():
            logger.warning(f"模型目录不存在: {models_dir}")
            return []

        # 查找所有 .onnx 和 .pth 文件
        model_files = []
        for ext in ['*.onnx', '*.pth', '*.ckpt']:
            model_files.extend(models_dir.glob(ext))

        return [f.name for f in model_files]

    def health_check(self) -> Dict[str, any]:
        """
        全面的健康检查

        Returns:
            Dict: 健康状态信息
        """
        import psutil
        import datetime

        health_status = {
            'status': 'healthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'models_loaded': len(self._separators),
            'current_model': self._current_model,
            'available_models': self.list_available_models(),
            'config': {
                'use_gpu': self.config.use_gpu,
                'gpu_id': self.config.gpu_id,
                'models_dir': self.config.models_dir,
                'output_format': self.config.output_format,
                'mdx_segment_size': self.config.mdx_segment_size,
                'mdx_batch_size': self.config.mdx_batch_size
            },
            'system_info': {},
            'checks': {}
        }

        # 检查模型目录
        models_dir = Path(self.config.models_dir)
        models_dir_check = {
            'exists': models_dir.exists(),
            'readable': False,
            'writable': False,
            'size_mb': 0
        }

        if models_dir.exists():
            models_dir_check['readable'] = os.access(models_dir, os.R_OK)
            models_dir_check['writable'] = os.access(models_dir, os.W_OK)

            # 计算目录大小
            total_size = 0
            for file_path in models_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            models_dir_check['size_mb'] = round(total_size / (1024 * 1024), 2)

        health_status['checks']['models_directory'] = models_dir_check

        # 检查输出目录
        output_dir = Path(self.config.output_dir)
        output_dir_check = {
            'exists': output_dir.exists(),
            'writable': False
        }

        if output_dir.exists():
            output_dir_check['writable'] = os.access(output_dir, os.W_OK)

        health_status['checks']['output_directory'] = output_dir_check

        # 检查系统资源
        try:
            memory = psutil.virtual_memory()
            health_status['system_info'] = {
                'memory_usage_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'cpu_count': psutil.cpu_count()
            }
        except Exception as e:
            health_status['system_info'] = {'error': str(e)}

        # 检查GPU状态（如果启用GPU）
        if self.config.use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_info = {
                        'available': True,
                        'device_count': torch.cuda.device_count(),
                        'current_device': torch.cuda.current_device(),
                        'device_name': torch.cuda.get_device_name(),
                        'memory_allocated_mb': round(torch.cuda.memory_allocated() / (1024**2), 2),
                        'memory_reserved_mb': round(torch.cuda.memory_reserved() / (1024**2), 2)
                    }
                else:
                    gpu_info = {
                        'available': False,
                        'error': 'CUDA not available'
                    }
                health_status['system_info']['gpu'] = gpu_info
            except ImportError:
                health_status['system_info']['gpu'] = {
                    'available': False,
                    'error': 'PyTorch not installed'
                }
            except Exception as e:
                health_status['system_info']['gpu'] = {
                    'available': False,
                    'error': str(e)
                }

        # 检查关键模型文件
        critical_models = [
            self.config.default_model,
            self.config.high_quality_model,
            self.config.vocal_optimization_model
        ]

        model_files_check = {}
        for model_name in critical_models:
            model_path = models_dir / model_name
            model_files_check[model_name] = {
                'exists': model_path.exists(),
                'size_mb': round(model_path.stat().st_size / (1024*1024), 2) if model_path.exists() else 0
            }

        health_status['checks']['critical_models'] = model_files_check

        # 确定整体健康状态
        issues = []

        if not models_dir_check['exists']:
            issues.append('models_directory_not_found')
        elif not models_dir_check['readable']:
            issues.append('models_directory_not_readable')
        elif not models_dir_check['writable']:
            issues.append('models_directory_not_writable')

        if not output_dir_check['exists']:
            issues.append('output_directory_not_found')
        elif not output_dir_check['writable']:
            issues.append('output_directory_not_writable')

        # 检查关键模型
        missing_critical_models = [
            model for model, info in model_files_check.items()
            if not info['exists']
        ]
        if missing_critical_models:
            issues.append('missing_critical_models')
            health_status['missing_models'] = missing_critical_models

        # 检查内存使用
        if memory.percent > 90:
            issues.append('high_memory_usage')

        # 检查GPU状态
        if self.config.use_gpu:
            gpu_info = health_status['system_info'].get('gpu', {})
            if not gpu_info.get('available', False):
                issues.append('gpu_not_available')

        # 更新整体状态
        if issues:
            health_status['status'] = 'unhealthy'
            health_status['issues'] = issues

        return health_status

    def clear_cache(self):
        """清除所有缓存的模型"""
        with self._lock:
            logger.info("清除模型缓存")
            self._separators.clear()
            self._current_model = None
    
    def separate_vocals_optimized(
        self,
        audio_path: str,
        model_name: Optional[str] = None,
        output_dir: Optional[str] = None,
        optimization_level: str = "balanced"
    ) -> Dict[str, str]:
        """
        使用优化参数分离人声
        
        Args:
            audio_path: 输入音频文件路径
            model_name: 使用的模型名称
            output_dir: 输出目录（可选）
            optimization_level: 优化级别 ("fast", "balanced", "quality")
        
        Returns:
            Dict[str, str]: 分离结果，包含 vocals 和 instrumental 路径
        """
        # 验证输入文件
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 确定模型名称
        if model_name is None:
            model_name = self.config.default_model

        # 确定输出目录
        if output_dir is None:
            output_dir = self.config.output_dir

        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 根据优化级别设置参数
        if optimization_level == "fast":
            # 快速模式：使用配置中的快速参数，并确保所有参数都有默认值
            mdx_params = {
                "hop_length": self.config.vocal_fast_params.get("hop_length", 1024),
                "segment_size": self.config.vocal_fast_params.get("segment_size", 256),
                "batch_size": self.config.vocal_fast_params.get("batch_size", 1),
                "overlap": self.config.vocal_fast_params.get("overlap", 0.25),
                "enable_denoise": self.config.vocal_fast_params.get("enable_denoise", False),
                "chunk_size": 261120,          # UVR5 标准配置，避免 None 错误
                "dim_f": 6144,                 # UVR5 标准配置，避免 None 错误
                "n_fft": 12288,                # UVR5 标准配置，避免 None 错误
            }
        elif optimization_level == "quality":
            # 质量模式：使用配置中的质量参数，并确保所有参数都有默认值
            mdx_params = {
                "hop_length": self.config.vocal_quality_params.get("hop_length", 256),
                "segment_size": self.config.vocal_quality_params.get("segment_size", 64),
                "batch_size": self.config.vocal_quality_params.get("batch_size", 1),
                "overlap": self.config.vocal_quality_params.get("overlap", 0.5),
                "enable_denoise": self.config.vocal_quality_params.get("enable_denoise", True),
                "chunk_size": 261120,          # UVR5 标准配置，避免 None 错误
                "dim_f": 6144,                 # UVR5 标准配置，避免 None 错误
                "n_fft": 12288,                # UVR5 标准配置，避免 None 错误
            }
        else:  # balanced
            # 平衡模式：使用配置中的平衡参数，并确保所有参数都有默认值
            mdx_params = {
                "hop_length": self.config.vocal_balanced_params.get("hop_length", 512),
                "segment_size": self.config.vocal_balanced_params.get("segment_size", 128),
                "batch_size": self.config.vocal_balanced_params.get("batch_size", 1),
                "overlap": self.config.vocal_balanced_params.get("overlap", 0.25),
                "enable_denoise": self.config.vocal_balanced_params.get("enable_denoise", True),
                "chunk_size": 261120,          # UVR5 标准配置，避免 None 错误
                "dim_f": 6144,                 # UVR5 标准配置，避免 None 错误
                "n_fft": 12288,                # UVR5 标准配置，避免 None 错误
            }

        # 为每个任务创建独立的 Separator 实例（避免并发问题）
        logger.info(f"创建优化参数的 Separator 实例，优化级别: {optimization_level}")
        
        # 确保参数不为None，防止出现 'NoneType' and 'int' 错误
        normalization_threshold = self.config.normalization_threshold or 0.9
        
        logger.info(f"使用优化参数: {mdx_params}")
        
        separator = Separator(
            log_level=logging.getLevelName(self.config.log_level),
            model_file_dir=self.config.models_dir,
            output_dir=output_dir,  # 直接使用指定的输出目录
            output_format=self.config.output_format,
            normalization_threshold=normalization_threshold,
            mdx_params=mdx_params,
        )

        try:
            logger.info(f"开始优化人声分离: {audio_path}")
            logger.info(f"使用模型: {model_name}")
            logger.info(f"输出目录: {output_dir}")
            logger.info(f"优化级别: {optimization_level}")
            logger.info(f"使用的MDX参数: {mdx_params}")

            # 加载模型
            logger.info(f"正在加载模型: {model_name}")
            separator.load_model(model_name)
            logger.info(f"模型加载成功: {model_name}")

            # 执行分离
            logger.info(f"开始执行优化人声分离...")
            output_files = separator.separate(audio_path)
            logger.info(f"优化人声分离完成，输出文件: {output_files}")

            # 检查输出结果
            if not output_files or len(output_files) == 0:
                raise RuntimeError(
                    f"音频分离失败：未生成任何输出文件。"
                    f"请检查日志以获取详细错误信息。"
                )

            # 解析输出文件（传递 output_dir 用于构建绝对路径）
            result = self._parse_output_files(output_files, output_dir)

            # 验证结果包含必需的文件
            if not result['vocals'] or not result['instrumental']:
                raise RuntimeError(
                    f"音频分离结果不完整：vocals={result['vocals']}, "
                    f"instrumental={result['instrumental']}"
                )

            return result

        except Exception as e:
            logger.error(f"优化人声分离失败: {str(e)}", exc_info=True)
            raise
    
    def _separate_audio_demucs(
        self,
        audio_path: str,
        model_name: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        使用Demucs模型分离音频（使用audio-separator高级API）
        
        Args:
            audio_path: 输入音频文件路径
            model_name: 使用的模型名称
            output_dir: 输出目录（可选）
            
        Returns:
            Dict[str, str]: 分离结果，包含 vocals 和 instrumental 路径
        """
        try:
            # 确定模型名称
            if model_name is None:
                model_name = self.config.demucs_default_model
            
            # 验证模型名称是否是有效的Demucs模型
            # 注意：audio-separator库需要模型文件名带.yaml扩展名
            valid_demucs_models = [
                'htdemucs.yaml', 'htdemucs_ft.yaml', 'htdemucs_6s.yaml',
                'mdx.yaml', 'mdx_q.yaml', 'mdx_extra_q.yaml', 'mdx_extra.yaml'
            ]
            
            # 如果模型名不带.yaml扩展名，添加扩展名
            if not model_name.endswith('.yaml'):
                model_name = f"{model_name}.yaml"
            
            if model_name not in valid_demucs_models:
                logger.warning(f"模型名称 '{model_name}' 可能不是有效的Demucs模型，尝试使用默认模型")
                default_model = self.config.demucs_default_model
                if not default_model.endswith('.yaml'):
                    default_model = f"{default_model}.yaml"
                model_name = default_model
            
            # 确定输出目录
            if output_dir is None:
                output_dir = self.config.output_dir
            
            # 创建输出目录
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始使用Demucs分离音频: {audio_path}")
            logger.info(f"使用模型: {model_name}")
            logger.info(f"输出目录: {output_dir}")
            
            # 处理 segment 参数 - 确保类型正确
            segment = self.config.demucs_segment
            
            # 将字符串 "default" 转换为 None，这样 audio-separator 会使用默认值
            if segment == "default":
                segment = None
                logger.info(f"将字符串 'default' 转换为 None，使用 audio-separator 默认分段大小")
            elif isinstance(segment, str):
                try:
                    # 尝试将字符串转换为浮点数
                    segment = float(segment)
                    logger.info(f"将字符串 '{self.config.demucs_segment}' 转换为数值: {segment}")
                except ValueError:
                    # 如果转换失败，使用 None
                    logger.warning(f"无法解析 segment 参数 '{segment}'，使用默认值")
                    segment = None
            elif segment is not None:
                logger.info(f"使用配置的 segment 值: {segment}")
            else:
                logger.info(f"使用默认 segment 值 (None)")
            
            # 创建 Separator 实例（与独立脚本一致）
            separator = Separator(
                log_level=logging.getLevelName(self.config.log_level),
                model_file_dir=self.config.models_dir,
                output_dir=output_dir,
                output_format=self.config.output_format,
                normalization_threshold=self.config.normalization_threshold or 0.9,
                # 对于Demucs模型，也使用mdx_params参数传递
                mdx_params={
                    "hop_length": 1024,
                    "segment_size": segment if segment is not None else "default",  # audio-separator支持字符串"default"
                    "batch_size": 1,
                    "overlap": 0.25,
                    "enable_denoise": False,
                    "chunk_size": 261120,
                    "dim_f": 6144,
                    "n_fft": 12288,
                },
            )
            
            # 加载模型
            logger.info(f"正在加载Demucs模型: {model_name}")
            separator.load_model(model_name)
            logger.info(f"模型加载成功: {model_name}")
            
            # 执行分离
            logger.info(f"开始执行Demucs音频分离...")
            output_files = separator.separate(audio_path)
            logger.info(f"Demucs音频分离完成，输出文件: {output_files}")
            
            # 检查输出结果
            if not output_files or len(output_files) == 0:
                raise RuntimeError(
                    f"音频分离失败：未生成任何输出文件。"
                    f"请检查日志以获取详细错误信息。"
                )
            
            # 解析输出文件（使用现有的_parse_output_files方法）
            result = self._parse_output_files(output_files, output_dir)
            
            # 验证结果包含必需的文件
            if not result['vocals'] or not result['instrumental']:
                logger.warning(f"标准解析结果不完整，尝试Demucs特殊解析")
                # 对于Demucs模型，尝试特殊解析
                result = self._parse_demucs_output_files(output_files, output_dir)
            
            # 验证结果
            if not result['vocals'] or not result['instrumental']:
                raise RuntimeError(
                    f"音频分离结果不完整：vocals={result['vocals']}, "
                    f"instrumental={result['instrumental']}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Demucs音频分离失败: {str(e)}", exc_info=True)
            raise

    def _parse_demucs_output_files(self, output_files: list, output_dir: str = None) -> Dict[str, str]:
        """
        解析Demucs模型的输出文件列表，处理多轨道输出
        
        Args:
            output_files: Separator 返回的输出文件列表（可能是相对路径）
            output_dir: 输出目录（用于构建绝对路径）
            
        Returns:
            Dict[str, str]: 包含 vocals 和 instrumental 的绝对路径字典
        """
        result = {
            'vocals': None,
            'instrumental': None
        }
        
        # 首先尝试标准解析
        for file_path in output_files:
            # 如果是相对路径，转换为绝对路径
            if not Path(file_path).is_absolute() and output_dir:
                file_path = str(Path(output_dir) / file_path)
            
            file_name = Path(file_path).name.lower()
            
            if 'vocal' in file_name or 'voice' in file_name:
                result['vocals'] = file_path
            elif 'instrumental' in file_name or 'inst' in file_name or 'no_vocal' in file_name:
                result['instrumental'] = file_path
        
        # 如果标准解析失败，尝试Demucs特殊解析
        if not result['vocals'] or not result['instrumental']:
            logger.info(f"尝试Demucs特殊解析，输出文件: {output_files}")
            
            # 收集所有轨道
            tracks = {}
            for file_path in output_files:
                # 如果是相对路径，转换为绝对路径
                if not Path(file_path).is_absolute() and output_dir:
                    file_path = str(Path(output_dir) / file_path)
                
                file_name = Path(file_path).name.lower()
                
                # 识别不同轨道
                if 'drums' in file_name:
                    tracks['drums'] = file_path
                elif 'bass' in file_name:
                    tracks['bass'] = file_path
                elif 'other' in file_name:
                    tracks['other'] = file_path
                elif 'vocals' in file_name or 'vocal' in file_name:
                    tracks['vocals'] = file_path
                elif 'piano' in file_name:
                    tracks['piano'] = file_path
                elif 'guitar' in file_name:
                    tracks['guitar'] = file_path
            
            # 设置人声轨道
            if 'vocals' in tracks:
                result['vocals'] = tracks['vocals']
            
            # 设置伴奏轨道
            if 'instrumental' in tracks:
                result['instrumental'] = tracks['instrumental']
            else:
                # 如果没有明确的伴奏轨道，标记需要合并其他轨道
                instrumental_tracks = []
                for track_name in ['drums', 'bass', 'other', 'piano', 'guitar']:
                    if track_name in tracks:
                        instrumental_tracks.append(tracks[track_name])
                
                if instrumental_tracks:
                    # 如果有多个伴奏音轨，标记需要合并
                    result['instrumental_tracks'] = instrumental_tracks
                    result['instrumental'] = f"[需要合并] {', '.join([Path(t).name for t in instrumental_tracks])}"
                elif len(output_files) >= 2:
                    # 备用逻辑：假设第二个文件是伴奏
                    file2 = output_files[1] if Path(output_files[1]).is_absolute() else str(Path(output_dir) / output_files[1])
                    result['instrumental'] = file2
        
        # 验证结果
        if result['vocals'] is None or result['instrumental'] is None:
            logger.warning(f"无法识别输出文件类型: {output_files}")
            # 备用逻辑：假设第一个文件是人声，第二个是伴奏
            if len(output_files) >= 2:
                file1 = output_files[0] if Path(output_files[0]).is_absolute() else str(Path(output_dir) / output_files[0])
                file2 = output_files[1] if Path(output_files[1]).is_absolute() else str(Path(output_dir) / output_files[1])
                result['vocals'] = file1
                result['instrumental'] = file2
        
        return result


# ========================================
# 全局模型管理器实例
# ========================================
_model_manager = ModelManager()


def get_model_manager() -> ModelManager:
    """
    获取全局模型管理器实例

    Returns:
        ModelManager: 模型管理器
    """
    return _model_manager


if __name__ == "__main__":
    # 测试模型管理器
    logging.basicConfig(level=logging.INFO)

    manager = get_model_manager()
    print("健康检查:", manager.health_check())
