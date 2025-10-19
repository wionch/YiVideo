# services/common/gpu_memory_manager.py
# -*- coding: utf-8 -*-

"""
GPU显存管理工具模块
专门提供GPU显存监控、清理和管理功能，解决多进程环境下的显存泄漏问题
专注于PyTorch和PaddlePaddle的GPU显存管理
"""

import gc
import logging
import os
import threading
import time
from typing import Dict, Any, Optional, List

from services.common.logger import get_logger

logger = get_logger('gpu_memory_manager')

# 尝试导入GPU相关库
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

try:
    import paddle
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False
    paddle = None

try:
    import nvidia_ml_py3 as nvml
    NVML_AVAILABLE = True
    try:
        nvml.nvmlInit()
    except:
        NVML_AVAILABLE = False
except ImportError:
    NVML_AVAILABLE = False
    nvml = None


class GPUMemoryManager:
    """GPU显存管理器 - 统一管理多进程环境下的GPU显存分配和释放"""

    def __init__(self):
        self.initialized = False
        self.device_count = 0
        self.initial_memory_info = {}
        self.cleanup_lock = threading.Lock()
        self.monitoring_enabled = False
        self._init_gpu_info()

    def _init_gpu_info(self):
        """初始化GPU信息"""
        try:
            # 检测CUDA设备数量
            if TORCH_AVAILABLE and torch.cuda.is_available():
                self.device_count = torch.cuda.device_count()
                logger.info(f"检测到 {self.device_count} 个CUDA设备")

                # 记录初始显存状态
                for i in range(self.device_count):
                    self.initial_memory_info[i] = self.get_memory_info(i)

            elif PADDLE_AVAILABLE and paddle.is_compiled_with_cuda():
                self.device_count = paddle.device.cuda.device_count()
                logger.info(f"检测到 {self.device_count} 个CUDA设备 (PaddlePaddle)")

                # 记录初始显存状态
                for i in range(self.device_count):
                    self.initial_memory_info[i] = self.get_memory_info(i)
            else:
                logger.warning("未检测到可用的CUDA设备")

            self.initialized = True

        except Exception as e:
            logger.error(f"初始化GPU信息失败: {e}")
            self.initialized = False

    def get_memory_info(self, device_id: int = 0) -> Dict[str, Any]:
        """
        获取指定GPU设备的显存信息

        Args:
            device_id: GPU设备ID

        Returns:
            Dict[str, Any]: 包含显存使用信息的字典
        """
        memory_info = {
            'device_id': device_id,
            'total': 0,
            'allocated': 0,
            'cached': 0,
            'free': 0,
            'utilization': 0.0,
            'timestamp': time.time()
        }

        try:
            if NVML_AVAILABLE:
                # 使用NVML获取精确的显存信息
                handle = nvml.nvmlDeviceGetHandleByIndex(device_id)
                mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)

                memory_info.update({
                    'total': mem_info.total,
                    'free': mem_info.free,
                    'used': mem_info.used,
                    'utilization': (mem_info.used / mem_info.total) * 100
                })

            # 同时获取框架级别的显存信息
            if TORCH_AVAILABLE and torch.cuda.is_available() and device_id < torch.cuda.device_count():
                memory_info.update({
                    'torch_allocated': torch.cuda.memory_allocated(device_id),
                    'torch_cached': torch.cuda.memory_reserved(device_id)
                })

            if PADDLE_AVAILABLE and paddle.is_compiled_with_cuda() and device_id < paddle.device.cuda.device_count():
                paddle.set_device(device_id)
                memory_info.update({
                    'paddle_allocated': paddle.device.cuda.memory_allocated()
                })

        except Exception as e:
            logger.debug(f"获取设备 {device_id} 显存信息失败: {e}")

        return memory_info

    def warm_up_gpu(self, device_id: int = 0):
        """
        GPU预热 - 在子进程中进行小规模GPU操作以预热GPU

        Args:
            device_id: GPU设备ID
        """
        if not self.initialized:
            logger.warning("GPU管理器未初始化，跳过GPU预热")
            return

        try:
            logger.debug(f"开始预热GPU设备 {device_id}")

            # 使用PyTorch预热
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.set_device(device_id)

                # 创建小张量进行预热
                x = torch.randn(100, 100, device=f'cuda:{device_id}')
                y = torch.matmul(x, x.T)

                # 同步并清理
                torch.cuda.synchronize(device_id)
                del x, y

            # 使用PaddlePaddle预热
            if PADDLE_AVAILABLE and paddle.is_compiled_with_cuda():
                paddle.set_device(device_id)

                # 创建小张量进行预热
                x = paddle.randn([100, 100], dtype='float32')
                y = paddle.matmul(x, x.T)

                # 同步并清理
                paddle.device.cuda.synchronize()
                del x, y

            logger.debug(f"GPU设备 {device_id} 预热完成")

        except Exception as e:
            logger.warning(f"GPU设备 {device_id} 预热失败: {e}")

    def force_cleanup_memory(self, device_id: int = None, aggressive: bool = False):
        """
        强制清理GPU显存

        Args:
            device_id: GPU设备ID，None表示清理所有设备
            aggressive: 是否使用激进清理模式
        """
        if not self.initialized:
            logger.warning("GPU管理器未初始化，跳过显存清理")
            return

        with self.cleanup_lock:
            try:
                devices_to_clean = [device_id] if device_id is not None else list(range(self.device_count))

                for dev_id in devices_to_clean:
                    logger.debug(f"开始清理GPU设备 {dev_id} 显存")

                    # 清理Python对象
                    gc.collect()

                    # 清理PyTorch显存
                    if TORCH_AVAILABLE and torch.cuda.is_available() and dev_id < torch.cuda.device_count():
                        try:
                            # 清理缓存
                            torch.cuda.empty_cache()

                            # 重置设备
                            torch.cuda.set_device(dev_id)
                            torch.cuda.synchronize(dev_id)

                            # 激进模式下强制重置
                            if aggressive:
                                torch.cuda.reset_peak_memory_stats(dev_id)

                        except Exception as e:
                            logger.debug(f"PyTorch显存清理失败 (设备 {dev_id}): {e}")

                    # 清理PaddlePaddle显存
                    if PADDLE_AVAILABLE and paddle.is_compiled_with_cuda() and dev_id < paddle.device.cuda.device_count():
                        try:
                            paddle.set_device(dev_id)

                            # 清理缓存
                            paddle.device.cuda.empty_cache()

                            # 同步设备
                            paddle.device.cuda.synchronize()

                            # 激进模式下强制重置
                            if aggressive:
                                paddle.device.cuda.memory_reset(dev_id)

                        except Exception as e:
                            logger.debug(f"PaddlePaddle显存清理失败 (设备 {dev_id}): {e}")

                    # 再次垃圾回收
                    gc.collect()

                    logger.debug(f"GPU设备 {dev_id} 显存清理完成")

                # 记录清理后的显存状态
                if logger.level <= logging.DEBUG:
                    for dev_id in devices_to_clean:
                        mem_info = self.get_memory_info(dev_id)
                        logger.debug(f"清理后显存状态 {dev_id}: {mem_info}")

            except Exception as e:
                logger.error(f"强制清理GPU显存失败: {e}")

    def monitor_memory_usage(self, device_id: int = 0, threshold: float = 0.9) -> Dict[str, Any]:
        """
        监控GPU显存使用情况

        Args:
            device_id: GPU设备ID
            threshold: 使用率阈值 (0.0-1.0)

        Returns:
            Dict[str, Any]: 监控结果
        """
        if not self.initialized:
            return {'error': 'GPU管理器未初始化'}

        try:
            current_info = self.get_memory_info(device_id)
            initial_info = self.initial_memory_info.get(device_id, {})

            # 计算使用率
            if current_info.get('total', 0) > 0:
                utilization = current_info.get('used', 0) / current_info['total']
            else:
                utilization = 0.0

            # 判断是否超过阈值
            is_above_threshold = utilization > threshold

            # 计算增长量
            memory_growth = 0
            if initial_info.get('total', 0) > 0:
                initial_used = initial_info.get('used', 0)
                current_used = current_info.get('used', 0)
                memory_growth = current_used - initial_used

            monitoring_result = {
                'device_id': device_id,
                'current_utilization': utilization,
                'is_above_threshold': is_above_threshold,
                'memory_growth_mb': memory_growth / (1024 * 1024),
                'threshold': threshold,
                'timestamp': time.time(),
                'current_info': current_info,
                'initial_info': initial_info
            }

            if is_above_threshold:
                logger.warning(f"GPU设备 {device_id} 显存使用率过高: {utilization:.1%}")

            return monitoring_result

        except Exception as e:
            logger.error(f"监控GPU显存使用失败: {e}")
            return {'error': str(e)}

    def log_memory_state(self, context: str = "", device_id: int = 0):
        """
        记录当前GPU显存状态到日志

        Args:
            context: 上下文描述
            device_id: GPU设备ID
        """
        if not self.initialized:
            return

        try:
            mem_info = self.get_memory_info(device_id)

            if mem_info.get('total', 0) > 0:
                used_mb = mem_info.get('used', 0) / (1024 * 1024)
                total_mb = mem_info.get('total', 0) / (1024 * 1024)
                utilization = mem_info.get('utilization', 0)

                log_msg = f"[显存状态] 设备{device_id}"
                if context:
                    log_msg += f" ({context})"
                log_msg += f" - 使用: {used_mb:.1f}MB / {total_mb:.1f}MB ({utilization:.1f}%)"

                # 添加框架级别信息
                if 'torch_allocated' in mem_info:
                    torch_mb = mem_info['torch_allocated'] / (1024 * 1024)
                    log_msg += f" | PyTorch: {torch_mb:.1f}MB"

                if 'paddle_allocated' in mem_info:
                    paddle_mb = mem_info['paddle_allocated'] / (1024 * 1024)
                    log_msg += f" | Paddle: {paddle_mb:.1f}MB"

                logger.info(log_msg)

        except Exception as e:
            logger.debug(f"记录GPU显存状态失败: {e}")

  
    def cleanup_worker_process(self, device_id: int = 0):
        """
        子进程退出前的完整清理流程

        Args:
            device_id: GPU设备ID
        """
        logger.debug(f"开始清理工作进程 (PID: {os.getpid()}, 设备: {device_id})")

        try:
            # 1. 记录清理前状态
            self.log_memory_state("清理前", device_id)

            # 2. 强制清理GPU显存
            self.force_cleanup_memory(device_id, aggressive=True)

            # 3. 清理Python对象
            gc.collect()

            # 4. 记录清理后状态
            self.log_memory_state("清理后", device_id)

            logger.debug(f"工作进程清理完成 (PID: {os.getpid()})")

        except Exception as e:
            logger.error(f"工作进程清理失败: {e}")


# 全局GPU内存管理器实例
gpu_memory_manager = GPUMemoryManager()


def get_gpu_memory_manager() -> GPUMemoryManager:
    """获取全局GPU内存管理器实例"""
    return gpu_memory_manager


def initialize_worker_gpu_memory(device_id: int = 0):
    """
    初始化工作进程的GPU内存管理

    Args:
        device_id: GPU设备ID
    """
    try:
        # 预热GPU
        gpu_memory_manager.warm_up_gpu(device_id)

        # 记录初始化状态
        gpu_memory_manager.log_memory_state(f"工作进程初始化 (PID: {os.getpid()})", device_id)

        logger.info(f"工作进程GPU内存初始化完成 (PID: {os.getpid()}, 设备: {device_id})")

    except Exception as e:
        logger.error(f"工作进程GPU内存初始化失败: {e}")


def cleanup_worker_gpu_memory(device_id: int = 0):
    """
    清理工作进程的GPU内存

    Args:
        device_id: GPU设备ID
    """
    gpu_memory_manager.cleanup_worker_process(device_id)


def log_gpu_memory_state(context: str = "", device_id: int = 0):
    """
    记录GPU内存状态的便捷函数

    Args:
        context: 上下文描述
        device_id: GPU设备ID
    """
    gpu_memory_manager.log_memory_state(context, device_id)


def force_cleanup_gpu_memory(device_id: int = None, aggressive: bool = False):
    """
    强制清理GPU内存的便捷函数

    Args:
        device_id: GPU设备ID
        aggressive: 是否使用激进清理
    """
    gpu_memory_manager.force_cleanup_memory(device_id, aggressive)




def monitor_gpu_memory(device_id: int = 0, threshold: float = 0.9) -> Dict[str, Any]:
    """
    监控GPU内存使用情况的便捷函数

    Args:
        device_id: GPU设备ID
        threshold: 使用率阈值

    Returns:
        Dict[str, Any]: 监控结果
    """
    return gpu_memory_manager.monitor_memory_usage(device_id, threshold)