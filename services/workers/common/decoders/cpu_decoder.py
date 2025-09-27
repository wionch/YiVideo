# services/workers/common/decoders/cpu_decoder.py
# -*- coding: utf-8 -*-

"""
CPU解码器

基于OpenCV的高效CPU视频解码器
"""

import time
from typing import Generator, Tuple, Dict, Any

import cv2
import numpy as np
import torch

from services.common.logger import get_logger
from .base_decoder import BaseDecoder, DecoderCapability

logger = get_logger('cpu_decoder')


class CPUDecoder(BaseDecoder):
    """
    CPU解码器

    使用OpenCV实现的高效CPU视频解码器
    适合没有GPU或小视频文件的场景
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化CPU解码器

        Args:
            config: 解码器配置
        """
        super().__init__(config)

        # CPU解码器特有配置
        self.use_multiprocessing = config.get('use_multiprocessing', False)
        self.num_workers = config.get('num_workers', 1)
        self.buffer_size = config.get('buffer_size', 100)

        logger.info(f"CPU解码器已加载 - 批大小: {self.batch_size}, 多进程: {self.use_multiprocessing}")

    def decode(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        解码视频

        Args:
            video_path: 视频文件路径
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        self._start_processing()
        try:
            # 验证视频文件
            if not self.validate_video_file(video_path):
                raise ValueError(f"无效的视频文件: {video_path}")

            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"无法打开视频文件: {video_path}")

            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            self.stats['total_frames'] = frame_count

            logger.info(f"开始解码视频: {video_path}, 分辨率: {width}x{height}, 帧数: {frame_count}")

            current_frame = 0
            batch_frames = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # 转换颜色空间 BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 转换为torch张量
                frame_tensor = torch.from_numpy(frame_rgb).float()

                # 转换维度为 THWC -> CTWH
                frame_tensor = frame_tensor.permute(2, 0, 1)

                batch_frames.append(frame_tensor)

                # 批量处理
                if len(batch_frames) >= self.batch_size:
                    batch_tensor = torch.stack(batch_frames)
                    metadata = {
                        'frame_count': len(batch_frames),
                        'fps': fps,
                        'width': width,
                        'height': height,
                        'frame_indices': list(range(current_frame - len(batch_frames) + 1, current_frame + 1))
                    }

                    yield batch_tensor, metadata

                    current_frame += len(batch_frames)
                    self.stats['frames_processed'] += len(batch_frames)
                    self.stats['batches_processed'] += 1

                    # 记录进度
                    self._log_progress(current_frame, frame_count, "解码")

                    # 清空批次
                    batch_frames = []

            # 处理剩余的帧
            if batch_frames:
                batch_tensor = torch.stack(batch_frames)
                metadata = {
                    'frame_count': len(batch_frames),
                    'fps': fps,
                    'width': width,
                    'height': height,
                    'frame_indices': list(range(current_frame - len(batch_frames) + 1, current_frame + 1))
                }

                yield batch_tensor, metadata

                current_frame += len(batch_frames)
                self.stats['frames_processed'] += len(batch_frames)
                self.stats['batches_processed'] += 1

            cap.release()
            logger.info(f"视频解码完成: {video_path}, 处理帧数: {current_frame}")

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
        if not self.validate_video_file(video_path):
            raise ValueError(f"无效的视频文件: {video_path}")

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"无法打开视频文件: {video_path}")

            info = {
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'duration': cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS),
                'fourcc': int(cap.get(cv2.CAP_PROP_FOURCC)),
                'codec': self._fourcc_to_string(int(cap.get(cv2.CAP_PROP_FOURCC))),
                'source': 'opencv'
            }

            cap.release()
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
            DecoderCapability.GPU_ACCELERATION: False,
            DecoderCapability.CONCURRENT_PROCESSING: self.use_multiprocessing,
            DecoderCapability.BATCH_PROCESSING: True,
            DecoderCapability.MEMORY_OPTIMIZATION: True,
            DecoderCapability.HARDWARE_DECODING: False,
            DecoderCapability.MULTI_FORMAT_SUPPORT: True,
            DecoderCapability.SEEK_SUPPORT: True,
            DecoderCapability.METADATA_EXTRACTION: True
        }

        return capabilities

    def _fourcc_to_string(self, fourcc: int) -> str:
        """
        将FourCC代码转换为字符串

        Args:
            fourcc: FourCC代码

        Returns:
            编码器名称字符串
        """
        return "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])

    def extract_frames_at_timestamps(self, video_path: str, timestamps: list,
                                    **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        在指定时间戳提取帧

        Args:
            video_path: 视频文件路径
            timestamps: 时间戳列表（秒）
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        if not self.validate_video_file(video_path):
            raise ValueError(f"无效的视频文件: {video_path}")

        # 获取视频信息
        video_info = self.get_video_info(video_path)
        fps = video_info['fps']

        if fps == 0:
            logger.warning(f"无法获取视频FPS: {video_path}")
            return

        # 将时间戳转换为帧索引
        frame_indices = [int(timestamp * fps) for timestamp in timestamps]

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        try:
            for i, target_frame in enumerate(frame_indices):
                # 跳转到目标帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"无法读取帧 {target_frame}")
                    continue

                # 转换颜色空间
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 转换为torch张量
                frame_tensor = torch.from_numpy(frame_rgb).float()
                frame_tensor = frame_tensor.permute(2, 0, 1)

                metadata = {
                    'frame_count': 1,
                    'fps': fps,
                    'width': frame.shape[1],
                    'height': frame.shape[0],
                    'timestamp': timestamps[i],
                    'frame_index': target_frame,
                    'extracted_index': i
                }

                yield frame_tensor, metadata
                self.stats['frames_processed'] += 1

        finally:
            cap.release()

    def __str__(self):
        return f"CPUDecoder(batch_size={self.batch_size}, multiprocessing={self.use_multiprocessing})"

    def __repr__(self):
        return self.__str__()