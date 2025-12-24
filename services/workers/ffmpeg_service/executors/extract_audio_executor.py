"""
FFmpeg 音频提取执行器。

该模块实现了从视频文件中提取音频的节点执行器。
"""

import os
import subprocess
from typing import Dict, Any, List
from services.common.base_node_executor import BaseNodeExecutor
from services.common.file_service import get_file_service
from services.common.subprocess_utils import run_gpu_command
from services.common.logger import get_logger

logger = get_logger(__name__)


class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    """
    FFmpeg 音频提取执行器。

    功能：从视频文件中提取音频,输出为 WAV 格式(16kHz, 单声道)。

    输入参数：
        - video_path: 视频文件路径(必需)

    输出字段：
        - audio_path: 提取的音频文件本地路径
        - audio_path_minio_url: MinIO URL(如果上传启用)
    """

    def validate_input(self) -> None:
        """验证输入参数"""
        input_data = self.get_input_data()

        # 检查必需参数
        if "video_path" not in input_data:
            raise ValueError("缺少必需参数: video_path")

        # 检查参数有效性
        video_path = input_data["video_path"]
        if not video_path:
            raise ValueError("参数 'video_path' 不能为空")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行核心业务逻辑：从视频中提取音频。

        Returns:
            包含 audio_path 的字典
        """
        input_data = self.get_input_data()
        video_path = input_data["video_path"]

        # 文件下载
        file_service = get_file_service()
        logger.info(f"[{self.stage_name}] 开始下载视频文件: {video_path}")
        video_path = file_service.resolve_and_download(
            video_path, self.context.shared_storage_path
        )
        logger.info(f"[{self.stage_name}] 视频文件下载完成: {video_path}")

        # 验证文件存在
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 在共享存储中创建音频目录
        audio_dir = os.path.join(self.context.shared_storage_path, "audio")
        os.makedirs(audio_dir, exist_ok=True)

        # 生成音频文件名
        video_filename = os.path.basename(video_path)
        audio_filename = os.path.splitext(video_filename)[0] + ".wav"
        audio_path = os.path.join(audio_dir, audio_filename)

        logger.info(f"[{self.stage_name}] 开始从 {video_path} 提取音频...")

        # 使用 ffmpeg 提取音频
        command = [
            "ffmpeg",
            "-i", video_path,
            "-vn",  # 禁用视频
            "-acodec", "pcm_s16le",  # 音频编码
            "-ar", "16000",  # 采样率 16kHz
            "-ac", "1",  # 单声道
            "-y",  # 覆盖输出文件
            audio_path
        ]

        try:
            result = run_gpu_command(
                command,
                stage_name=self.stage_name,
                check=True,
                timeout=1800
            )

            if result.stderr:
                logger.warning(
                    f"[{self.stage_name}] ffmpeg 有 stderr 输出:\n{result.stderr.strip()}"
                )

            # 验证输出文件
            if not os.path.exists(audio_path):
                raise RuntimeError(f"音频提取失败：输出文件不存在 {audio_path}")

            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                raise RuntimeError(f"音频提取失败：输出文件为空 {audio_path}")

            logger.info(
                f"[{self.stage_name}] 音频提取完成：{audio_path} (大小: {file_size} 字节)"
            )

            return {"audio_path": audio_path}

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{self.stage_name}] ffmpeg 音频提取超时({e.timeout}秒)。"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(f"音频提取超时: {e.timeout} 秒") from e

        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{self.stage_name}] ffmpeg 音频提取失败，返回码: {e.returncode}。\n"
                f"Stdout:\n---\n{stdout_output}\n---\n"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(f"音频提取失败: ffmpeg 返回码 {e.returncode}") from e

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段。

        缓存依赖于输入视频文件,相同视频提取的音频相同。
        """
        return ["video_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段(用于缓存验证)。

        音频提取的核心输出是 audio_path。
        """
        return ["audio_path"]
