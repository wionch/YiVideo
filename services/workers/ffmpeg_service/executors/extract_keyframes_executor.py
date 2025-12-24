"""
FFmpeg 关键帧提取执行器。

该模块实现了从视频文件中提取关键帧的节点执行器。
"""

import os
from typing import Dict, Any, List
from services.common.base_node_executor import BaseNodeExecutor
from services.common.file_service import get_file_service
from services.common.logger import get_logger
from services.workers.ffmpeg_service.app.modules.video_decoder import extract_random_frames

logger = get_logger(__name__)


class FFmpegExtractKeyframesExecutor(BaseNodeExecutor):
    """
    FFmpeg 关键帧提取执行器。

    功能：从视频文件中随机抽取指定数量的关键帧图片。

    输入参数：
        - video_path: 视频文件路径(必需)
        - keyframe_sample_count: 抽取帧数(可选,默认100)

    输出字段：
        - keyframe_dir: 关键帧目录本地路径
        - keyframe_dir_minio_url: MinIO URL(如果上传启用)
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

        # 检查可选参数的有效性
        if "keyframe_sample_count" in input_data:
            count = input_data["keyframe_sample_count"]
            if not isinstance(count, int) or count <= 0:
                raise ValueError("参数 'keyframe_sample_count' 必须是正整数")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行核心业务逻辑：从视频中提取关键帧。

        Returns:
            包含 keyframe_dir 的字典
        """
        input_data = self.get_input_data()
        video_path = input_data["video_path"]
        num_frames = input_data.get("keyframe_sample_count", 100)

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

        # 创建关键帧目录
        keyframes_dir = os.path.join(self.context.shared_storage_path, "keyframes")
        os.makedirs(keyframes_dir, exist_ok=True)

        logger.info(f"[{self.stage_name}] 开始从 {video_path} 抽取 {num_frames} 帧...")

        # 调用核心函数提取关键帧
        frame_paths = extract_random_frames(video_path, num_frames, keyframes_dir)

        if not frame_paths:
            raise RuntimeError("核心函数 extract_random_frames 未能成功抽取任何帧")

        logger.info(
            f"[{self.stage_name}] 关键帧提取完成：{len(frame_paths)} 帧，"
            f"目录: {keyframes_dir}"
        )

        return {"keyframe_dir": keyframes_dir}

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段。

        缓存依赖于输入视频和抽取帧数,相同参数提取的关键帧相同。
        """
        return ["video_path", "keyframe_sample_count"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段(用于缓存验证)。

        关键帧提取的核心输出是 keyframe_dir。
        """
        return ["keyframe_dir"]
