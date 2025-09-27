# services/workers/common/decoders/video_info.py
# -*- coding: utf-8 -*-

"""
统一视频信息获取工具

合并重复的get_video_info实现，提供统一接口
"""

import json
import os
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from services.common.logger import get_logger

logger = get_logger('video_info')


class VideoInfo:
    """
    统一视频信息获取类

    提供多种视频信息获取方式，自动选择最佳方法
    """

    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}

    def get_video_info(self, video_path: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取视频信息的统一接口

        Args:
            video_path: 视频文件路径
            use_cache: 是否使用缓存

        Returns:
            视频信息字典
        """
        # 验证文件存在性
        if not self._validate_video_file(video_path):
            raise FileNotFoundError(f"视频文件不存在或无效: {video_path}")

        # 检查缓存
        if use_cache and video_path in self.cache:
            logger.debug(f"从缓存获取视频信息: {video_path}")
            return self.cache[video_path]

        # 尝试不同的获取方法
        info = None

        # 方法1: 使用FFprobe（最准确）
        try:
            info = self._get_info_ffmpeg(video_path)
            logger.debug(f"使用FFprobe获取视频信息: {video_path}")
        except Exception as e:
            logger.warning(f"FFprobe获取视频信息失败: {e}")

        # 方法2: 使用mediainfo（备用）
        if info is None:
            try:
                info = self._get_info_mediainfo(video_path)
                logger.debug(f"使用mediainfo获取视频信息: {video_path}")
            except Exception as e:
                logger.warning(f"mediainfo获取视频信息失败: {e}")

        # 方法3: 使用OpenCV（最后备用）
        if info is None:
            try:
                info = self._get_info_opencv(video_path)
                logger.debug(f"使用OpenCV获取视频信息: {video_path}")
            except Exception as e:
                logger.warning(f"OpenCV获取视频信息失败: {e}")

        if info is None:
            raise RuntimeError(f"无法获取视频信息: {video_path}")

        # 添加文件信息
        info.update(self._get_file_info(video_path))

        # 缓存结果
        if use_cache:
            self.cache[video_path] = info

        logger.info(f"成功获取视频信息: {Path(video_path).name} - "
                   f"{info.get('width', 0)}x{info.get('height', 0)}, "
                   f"{info.get('duration', 0):.1f}s, "
                   f"{info.get('frame_count', 0)}帧")

        return info

    def _validate_video_file(self, video_path: str) -> bool:
        """
        验证视频文件

        Args:
            video_path: 视频文件路径

        Returns:
            文件是否有效
        """
        if not os.path.exists(video_path):
            return False

        if not os.path.isfile(video_path):
            return False

        # 检查文件大小
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            return False

        # 检查文件扩展名
        valid_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
        file_ext = Path(video_path).suffix.lower()
        if file_ext not in valid_extensions:
            logger.warning(f"未知视频格式: {file_ext}")

        return True

    def _get_info_ffmpeg(self, video_path: str) -> Dict[str, Any]:
        """
        使用FFprobe获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息字典
        """
        command = [
            'ffprobe', '-v', 'error', '-count_frames',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_read_frames,duration,width,height,avg_frame_rate,r_frame_rate,bit_rate',
            '-show_entries', 'format=size,duration,bit_rate',
            '-of', 'json', video_path
        ]

        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(result.stdout)

        # 解析视频流信息
        stream_info = data.get('streams', [{}])[0]
        format_info = data.get('format', {})

        # 计算FPS
        fps_str = stream_info.get('avg_frame_rate', '0/1')
        try:
            fps = eval(fps_str)
        except:
            fps = 0.0

        return {
            'frame_count': int(stream_info.get('nb_read_frames', 0)),
            'duration': float(stream_info.get('duration', format_info.get('duration', 0))),
            'width': int(stream_info.get('width', 0)),
            'height': int(stream_info.get('height', 0)),
            'fps': fps,
            'bit_rate': int(stream_info.get('bit_rate', format_info.get('bit_rate', 0))),
            'codec': stream_info.get('codec_name', 'unknown'),
            'format': format_info.get('format_name', 'unknown'),
            'source': 'ffprobe'
        }

    def _get_info_mediainfo(self, video_path: str) -> Dict[str, Any]:
        """
        使用mediainfo获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息字典
        """
        info = {}

        # 获取帧数
        try:
            command = ['mediainfo', '--Output=Video;%FrameCount%', video_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
            info['frame_count'] = int(result.stdout.strip())
        except:
            info['frame_count'] = 0

        # 获取宽度
        try:
            command = ['mediainfo', '--Output=Video;%Width%', video_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
            info['width'] = int(result.stdout.strip())
        except:
            info['width'] = 0

        # 获取高度
        try:
            command = ['mediainfo', '--Output=Video;%Height%', video_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
            info['height'] = int(result.stdout.strip())
        except:
            info['height'] = 0

        # 获取时长
        try:
            command = ['mediainfo', '--Output=Video;%Duration%', video_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
            info['duration'] = float(result.stdout.strip()) / 1000.0  # 毫秒转秒
        except:
            info['duration'] = 0.0

        # 获取帧率
        try:
            command = ['mediainfo', '--Output=Video;%FrameRate%', video_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
            info['fps'] = float(result.stdout.strip())
        except:
            info['fps'] = 0.0

        info['source'] = 'mediainfo'

        return info

    def _get_info_opencv(self, video_path: str) -> Dict[str, Any]:
        """
        使用OpenCV获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息字典
        """
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        info = {
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            'duration': cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS),
            'source': 'opencv'
        }

        cap.release()
        return info

    def _get_file_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取文件基本信息

        Args:
            video_path: 视频文件路径

        Returns:
            文件信息字典
        """
        stat = os.stat(video_path)
        return {
            'file_size': stat.st_size,
            'file_size_mb': stat.st_size / (1024 * 1024),
            'file_path': video_path,
            'file_name': Path(video_path).name,
            'modified_time': stat.st_mtime
        }

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logger.info("视频信息缓存已清除")

    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息

        Returns:
            缓存信息字典
        """
        return {
            'cache_size': len(self.cache),
            'cached_files': list(self.cache.keys())
        }


# 全局实例
video_info = VideoInfo()


def get_video_info(video_path: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    获取视频信息的便捷函数

    Args:
        video_path: 视频文件路径
        use_cache: 是否使用缓存

    Returns:
        视频信息字典
    """
    return video_info.get_video_info(video_path, use_cache)