# services/workers/common/decoders/gpu_decoder.py
# -*- coding: utf-8 -*-

"""
GPU加速解码器

基于PyAV和PyTorch的GPU加速视频解码器
"""

import time
from typing import Generator, Tuple, Dict, Any

import av
import numpy as np
import torch

from services.common.logger import get_logger
from .base_decoder import BaseDecoder, DecoderCapability

logger = get_logger('gpu_decoder')


class GPUDecoder(BaseDecoder):
    """
    GPU加速解码器

    使用PyAV和PyTorch实现的高效视频解码器
    支持批量处理和GPU加速
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化GPU解码器

        Args:
            config: 解码器配置
        """
        super().__init__(config)

        # GPU解码器特有配置
        self.fps = config.get('fps', None)
        self.log_progress = config.get('log_progress', False)
        self.precision = config.get('precision', 'fp16')  # fp16 或 fp32

        # 验证设备支持
        if self.device == 'cpu':
            logger.warning("GPU解码器在CPU模式下运行，性能将受限")

        logger.info(f"GPU解码器已加载 - 设备: {self.device}, 批大小: {self.batch_size}, 精度: {self.precision}")

    def decode(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        解码视频

        Args:
            video_path: 视频文件路径
            **kwargs: 其他参数（fps, log_progress等）

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        self._start_processing()
        try:
            # 覆盖配置参数
            fps = kwargs.get('fps', self.fps)
            log_progress = kwargs.get('log_progress', self.log_progress)

            # 验证视频文件
            if not self.validate_video_file(video_path):
                raise ValueError(f"无效的视频文件: {video_path}")

            # 打开视频文件
            container = av.open(video_path)
            video_stream = container.streams.video[0]

            # 设置帧率
            if fps:
                video_stream.thread_type = 'AUTO'
                video_stream.codec_context.thread_type = 'AUTO'

            # 创建进度条
            if log_progress:
                from ..utils.progress_logger import create_progress_bar
                total_frames = video_stream.frames
                progress_bar = create_progress_bar(total_frames, "解码视频")

            frame_count = 0
            batch_frames = []

            for frame in container.decode(video_stream):
                # 转换为numpy数组
                img_array = frame.to_ndarray(format='rgb24')

                # 转换为torch张量
                frame_tensor = torch.from_numpy(img_array).float()
                if self.precision == 'fp16':
                    frame_tensor = frame_tensor.half()

                # 转换维度为 THWC -> CTWH
                frame_tensor = frame_tensor.permute(2, 0, 1)

                # 移动到GPU
                if self.device == 'cuda':
                    frame_tensor = frame_tensor.cuda()

                batch_frames.append(frame_tensor)

                # 批量处理
                if len(batch_frames) >= self.batch_size:
                    batch_tensor = torch.stack(batch_frames)
                    metadata = {
                        'frame_count': len(batch_frames),
                        'fps': video_stream.average_rate,
                        'width': frame.width,
                        'height': frame.height,
                        'timestamp': frame.time,
                        'keyframe': frame.key_frame,
                        'pict_type': frame.pict_type
                    }

                    yield batch_tensor, metadata

                    frame_count += len(batch_frames)
                    self.stats['frames_processed'] += len(batch_frames)
                    self.stats['batches_processed'] += 1

                    # 更新进度
                    if log_progress:
                        progress_bar.update(len(batch_frames))

                    # 记录进度
                    self._log_progress(frame_count, total_frames or 1000, "解码")

                    # 清空批次
                    batch_frames = []

            # 处理剩余的帧
            if batch_frames:
                batch_tensor = torch.stack(batch_frames)
                metadata = {
                    'frame_count': len(batch_frames),
                    'fps': video_stream.average_rate,
                    'width': frame.width,
                    'height': frame.height,
                    'timestamp': frame.time,
                    'keyframe': frame.key_frame,
                    'pict_type': frame.pict_type
                }

                yield batch_tensor, metadata

                frame_count += len(batch_frames)
                self.stats['frames_processed'] += len(batch_frames)
                self.stats['batches_processed'] += 1

            if log_progress:
                progress_bar.close()

            logger.info(f"视频解码完成: {video_path}, 总帧数: {frame_count}")

        except Exception as e:
            logger.error(f"视频解码失败: {e}")
            self.stats['decoding_errors'] += 1
            raise
        finally:
            self._finish_processing()

    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息字典
        """
        from .video_info import get_video_info

        try:
            # 使用统一视频信息获取
            info = get_video_info(video_path, use_cache=True)

            # 添加GPU解码器特有信息
            info.update({
                'gpu_decoder_supported': self.device == 'cuda',
                'recommended_batch_size': self._calculate_optimal_batch_size(info),
                'precision_mode': self.precision
            })

            return info

        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise

    def get_capabilities(self) -> Dict[str, bool]:
        """
        获取解码器能力

        Returns:
            能力字典
        """
        capabilities = {
            DecoderCapability.GPU_ACCELERATION: self.device == 'cuda',
            DecoderCapability.BATCH_PROCESSING: True,
            DecoderCapability.MEMORY_OPTIMIZATION: True,
            DecoderCapability.MULTI_FORMAT_SUPPORT: True,
            DecoderCapability.SEEK_SUPPORT: True,
            DecoderCapability.METADATA_EXTRACTION: True,
            DecoderCapability.CONCURRENT_PROCESSING: False,  # GPU解码器通常不适合并发
            DecoderCapability.HARDWARE_DECODING: True
        }

        return capabilities

    def _calculate_optimal_batch_size(self, video_info: Dict[str, Any]) -> int:
        """
        计算最优批大小

        Args:
            video_info: 视频信息

        Returns:
            最优批大小
        """
        if self.device != 'cuda':
            return min(self.batch_size, 16)  # CPU模式使用较小批大小

        # 获取GPU内存
        if torch.cuda.is_available():
            gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)

            # 根据GPU内存和视频分辨率调整批大小
            resolution = video_info.get('width', 0) * video_info.get('height', 0)
            memory_per_frame_mb = resolution * 3 * 2 / (1024 * 1024)  # RGB * 2 bytes (fp16)

            # 计算理论最大批大小
            max_batch = int((gpu_memory_gb * 1024 * 0.3) / memory_per_frame_mb)  # 使用30% GPU内存

            return min(max_batch, self.batch_size, 128)  # 不超过配置的批大小和最大值

        return self.batch_size

    def decode_gpu(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        GPU解码的便捷方法（向后兼容）

        Args:
            video_path: 视频文件路径
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        return self.decode(video_path, **kwargs)

    def sample_frames_precise_gpu(self, video_path: str, sample_count: int = 100,
                                subtitle_area: Tuple[int, int, int, int] = None,
                                **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        精确采样帧（GPU版本）

        Args:
            video_path: 视频文件路径
            sample_count: 采样帧数
            subtitle_area: 字幕区域 (x1, y1, x2, y2)
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        if not self.validate_video_file(video_path):
            raise ValueError(f"无效的视频文件: {video_path}")

        # 获取视频信息
        video_info = self.get_video_info(video_path)
        total_frames = video_info.get('frame_count', 0)

        if total_frames == 0:
            logger.warning(f"无法获取视频帧数: {video_path}")
            return

        # 计算采样间隔
        if sample_count >= total_frames:
            sample_indices = list(range(total_frames))
        else:
            sample_indices = [int(i * total_frames / sample_count) for i in range(sample_count)]

        # 打开视频
        container = av.open(video_path)
        video_stream = container.streams.video[0]

        sampled_count = 0

        for target_frame in sample_indices:
            try:
                # 跳转到目标帧
                video_stream.seek(target_frame, backward=True)

                # 解码帧
                for frame in container.decode(video_stream):
                    frame_index = frame.pts

                    if frame_index >= target_frame:
                        # 转换为张量
                        img_array = frame.to_ndarray(format='rgb24')
                        frame_tensor = torch.from_numpy(img_array).float()

                        # 裁剪字幕区域（如果指定）
                        if subtitle_area:
                            x1, y1, x2, y2 = subtitle_area
                            frame_tensor = frame_tensor[y1:y2, x1:x2]

                        # 转换维度和精度
                        frame_tensor = frame_tensor.permute(2, 0, 1)
                        if self.precision == 'fp16':
                            frame_tensor = frame_tensor.half()

                        if self.device == 'cuda':
                            frame_tensor = frame_tensor.cuda()

                        metadata = {
                            'frame_count': 1,
                            'fps': video_stream.average_rate,
                            'width': frame_tensor.shape[2],
                            'height': frame_tensor.shape[1],
                            'timestamp': frame.time,
                            'frame_index': frame_index,
                            'sample_index': sampled_count
                        }

                        yield frame_tensor, metadata
                        sampled_count += 1
                        self.stats['frames_processed'] += 1
                        break

            except Exception as e:
                logger.warning(f"采样帧 {target_frame} 失败: {e}")
                self.stats['decoding_errors'] += 1
                continue

        logger.info(f"精确采样完成: {video_path}, 采样 {sampled_count}/{len(sample_indices)} 帧")

    def __str__(self):
        return f"GPUDecoder(device={self.device}, batch_size={self.batch_size}, precision={self.precision})"

    def __repr__(self):
        return self.__str__()