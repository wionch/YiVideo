# services/workers/common/decoders/concurrent_decoder.py
# -*- coding: utf-8 -*-

"""
并发解码器

使用多进程和线程池实现的高并发视频解码器
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Generator, Tuple, Dict, Any, List
from multiprocessing import Manager, cpu_count

import cv2
import numpy as np
import torch

from services.common.logger import get_logger
from .base_decoder import BaseDecoder, DecoderCapability

logger = get_logger('concurrent_decoder')


class ConcurrentDecoder(BaseDecoder):
    """
    并发解码器

    使用多进程和线程池实现的高并发视频解码器
    适合大文件和高并发场景
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化并发解码器

        Args:
            config: 解码器配置
        """
        super().__init__(config)

        # 并发解码器特有配置
        self.num_workers = config.get('num_workers', cpu_count())
        self.use_multiprocessing = config.get('use_multiprocessing', True)
        self.chunk_size = config.get('chunk_size', 1000)  # 每个任务处理的帧数
        self.max_memory_gb = config.get('max_memory_gb', 4.0)

        # 验证配置
        cpu_cores = cpu_count()
        if self.num_workers > cpu_cores:
            logger.warning(f"工作进程数({self.num_workers})超过CPU核心数({cpu_cores})")

        logger.info(f"并发解码器已加载 - 工作进程: {self.num_workers}, "
                   f"多进程: {self.use_multiprocessing}, 块大小: {self.chunk_size}")

    def decode(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        并发解码视频

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

            # 获取视频信息
            video_info = self.get_video_info(video_path)
            total_frames = video_info['frame_count']

            if total_frames == 0:
                logger.warning(f"无法获取视频帧数: {video_path}")
                return

            self.stats['total_frames'] = total_frames

            # 分块处理
            chunks = self._create_chunks(total_frames, self.chunk_size)

            logger.info(f"开始并发解码: {video_path}, 总帧数: {total_frames}, 块数: {len(chunks)}")

            # 根据配置选择执行器
            if self.use_multiprocessing and total_frames > 5000:  # 大视频使用多进程
                results = self._decode_multiprocess(video_path, chunks)
            else:
                results = self._decode_threadpool(video_path, chunks)

            # 合并结果
            for chunk_frames, metadata in results:
                if chunk_frames is not None:
                    yield chunk_frames, metadata

            logger.info(f"并发解码完成: {video_path}")

        except Exception as e:
            logger.error(f"并发解码失败: {e}")
            self.stats['decoding_errors'] += 1
            raise
        finally:
            self._finish_processing()

    def _create_chunks(self, total_frames: int, chunk_size: int) -> List[Tuple[int, int]]:
        """
        创建帧块

        Args:
            total_frames: 总帧数
            chunk_size: 块大小

        Returns:
            帧块列表 [(start_frame, end_frame), ...]
        """
        chunks = []
        for start in range(0, total_frames, chunk_size):
            end = min(start + chunk_size, total_frames)
            chunks.append((start, end))
        return chunks

    def _decode_multiprocess(self, video_path: str, chunks: List[Tuple[int, int]]) -> List[Tuple[torch.Tensor, Dict]]:
        """
        多进程解码

        Args:
            video_path: 视频文件路径
            chunks: 帧块列表

        Returns:
            解码结果列表
        """
        results = []

        try:
            with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
                # 提交任务
                future_to_chunk = {
                    executor.submit(self._decode_chunk, video_path, chunk): chunk
                    for chunk in chunks
                }

                # 收集结果
                for future in as_completed(future_to_chunk):
                    chunk = future_to_chunk[future]
                    try:
                        chunk_result = future.result(timeout=300)  # 5分钟超时
                        if chunk_result:
                            results.append(chunk_result)
                    except Exception as e:
                        logger.error(f"块 {chunk} 解码失败: {e}")
                        self.stats['decoding_errors'] += 1

        except Exception as e:
            logger.error(f"多进程解码失败: {e}")
            # 回退到线程池
            logger.info("回退到线程池解码...")
            return self._decode_threadpool(video_path, chunks)

        return results

    def _decode_threadpool(self, video_path: str, chunks: List[Tuple[int, int]]) -> List[Tuple[torch.Tensor, Dict]]:
        """
        线程池解码

        Args:
            video_path: 视频文件路径
            chunks: 帧块列表

        Returns:
            解码结果列表
        """
        results = []

        try:
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                # 提交任务
                future_to_chunk = {
                    executor.submit(self._decode_chunk, video_path, chunk): chunk
                    for chunk in chunks
                }

                # 收集结果
                for future in as_completed(future_to_chunk):
                    chunk = future_to_chunk[future]
                    try:
                        chunk_result = future.result(timeout=120)  # 2分钟超时
                        if chunk_result:
                            results.append(chunk_result)
                    except Exception as e:
                        logger.error(f"块 {chunk} 解码失败: {e}")
                        self.stats['decoding_errors'] += 1

        except Exception as e:
            logger.error(f"线程池解码失败: {e}")
            # 单线程处理
            logger.info("回退到单线程解码...")
            return self._decode_sequential(video_path, chunks)

        return results

    def _decode_sequential(self, video_path: str, chunks: List[Tuple[int, int]]) -> List[Tuple[torch.Tensor, Dict]]:
        """
        顺序解码（回退方案）

        Args:
            video_path: 视频文件路径
            chunks: 帧块列表

        Returns:
            解码结果列表
        """
        results = []

        for chunk in chunks:
            try:
                chunk_result = self._decode_chunk(video_path, chunk)
                if chunk_result:
                    results.append(chunk_result)
            except Exception as e:
                logger.error(f"块 {chunk} 顺序解码失败: {e}")
                self.stats['decoding_errors'] += 1

        return results

    def _decode_chunk(self, video_path: str, chunk: Tuple[int, int]) -> Tuple[torch.Tensor, Dict]:
        """
        解码单个帧块

        Args:
            video_path: 视频文件路径
            chunk: 帧块 (start_frame, end_frame)

        Returns:
            (帧张量块, 元数据) 的元组
        """
        start_frame, end_frame = chunk
        frames = []

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"无法打开视频文件: {video_path}")

            # 跳转到起始帧
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            current_frame = start_frame
            while current_frame < end_frame:
                ret, frame = cap.read()
                if not ret:
                    break

                # 转换颜色空间
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 转换为torch张量
                frame_tensor = torch.from_numpy(frame_rgb).float()
                frame_tensor = frame_tensor.permute(2, 0, 1)

                frames.append(frame_tensor)
                current_frame += 1

            cap.release()

            if frames:
                # 组合成批次
                batch_tensor = torch.stack(frames)
                metadata = {
                    'frame_count': len(frames),
                    'start_frame': start_frame,
                    'end_frame': current_frame,
                    'chunk_size': end_frame - start_frame,
                    'chunk_index': start_frame // self.chunk_size
                }

                return batch_tensor, metadata
            else:
                return None, None

        except Exception as e:
            logger.error(f"解码块 {chunk} 失败: {e}")
            raise

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
                'concurrent_workers': self.num_workers,
                'chunk_size': self.chunk_size,
                'source': 'concurrent_decoder'
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
            DecoderCapability.CONCURRENT_PROCESSING: True,
            DecoderCapability.BATCH_PROCESSING: True,
            DecoderCapability.MEMORY_OPTIMIZATION: True,
            DecoderCapability.HARDWARE_DECODING: False,
            DecoderCapability.MULTI_FORMAT_SUPPORT: True,
            DecoderCapability.SEEK_SUPPORT: True,
            DecoderCapability.METADATA_EXTRACTION: True
        }

        return capabilities

    def decode_video_concurrently(self, video_path: str, **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        并发解码的便捷方法（向后兼容）

        Args:
            video_path: 视频文件路径
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        return self.decode(video_path, **kwargs)

    def extract_random_frames(self, video_path: str, num_frames: int = 10,
                             **kwargs) -> Generator[Tuple[torch.Tensor, Dict], None, None]:
        """
        随机提取帧

        Args:
            video_path: 视频文件路径
            num_frames: 提取帧数
            **kwargs: 其他参数

        Yields:
            (帧张量, 元数据字典) 的元组
        """
        if not self.validate_video_file(video_path):
            raise ValueError(f"无效的视频文件: {video_path}")

        # 获取视频信息
        video_info = self.get_video_info(video_path)
        total_frames = video_info['frame_count']

        if total_frames == 0:
            logger.warning(f"无法获取视频帧数: {video_path}")
            return

        # 生成随机帧索引
        import random
        random_indices = sorted(random.sample(range(total_frames), min(num_frames, total_frames)))

        # 创建小任务
        chunks = [(idx, idx + 1) for idx in random_indices]

        # 并发处理
        results = self._decode_threadpool(video_path, chunks)

        # 按原始顺序返回结果
        for i, (frame_tensor, metadata) in enumerate(results):
            if frame_tensor is not None:
                metadata.update({
                    'random_index': i,
                    'original_index': random_indices[i]
                })
                yield frame_tensor, metadata
                self.stats['frames_processed'] += 1

    def __str__(self):
        return f"ConcurrentDecoder(workers={self.num_workers}, multiprocessing={self.use_multiprocessing})"

    def __repr__(self):
        return self.__str__()