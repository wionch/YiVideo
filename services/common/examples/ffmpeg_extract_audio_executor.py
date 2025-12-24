# services/common/examples/ffmpeg_extract_audio_executor.py
# -*- coding: utf-8 -*-

"""
FFmpeg 音频提取节点执行器示例。

本示例展示如何使用 BaseNodeExecutor 实现一个符合统一规范的节点。

使用方法：
    from services.common.examples.ffmpeg_extract_audio_executor import FFmpegExtractAudioExecutor
    from services.common.context import WorkflowContext

    context = WorkflowContext(
        workflow_id="task-001",
        shared_storage_path="/share/workflows/task-001",
        input_params={
            "input_data": {
                "video_path": "http://localhost:9000/yivideo/task-001/demo.mp4"
            },
            "core": {
                "auto_upload_to_minio": True
            }
        }
    )

    executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
    result_context = executor.execute()

    # 验证响应格式
    from services.common.validators import NodeResponseValidator
    validator = NodeResponseValidator(strict_mode=True)
    validator.validate(result_context, "ffmpeg.extract_audio")
"""

from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor


class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    """
    FFmpeg 音频提取节点执行器。

    功能：从视频文件中提取音频轨道。

    输入参数：
        - video_path: 视频文件路径（必需）

    输出字段：
        - audio_path: 提取的音频文件路径
        - audio_path_minio_url: MinIO URL（如果上传启用）
    """

    def validate_input(self) -> None:
        """验证输入参数"""
        input_data = self.get_input_data()

        if "video_path" not in input_data:
            raise ValueError("Missing required parameter: video_path")

        video_path = input_data["video_path"]
        if not video_path:
            raise ValueError("Parameter 'video_path' cannot be empty")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行音频提取逻辑。

        Note:
            这是一个示例实现，实际应该调用 FFmpeg 服务。
        """
        input_data = self.get_input_data()
        video_path = input_data["video_path"]

        # 示例：构造输出路径
        # 实际实现应该调用 FFmpeg 服务进行音频提取
        audio_filename = video_path.split("/")[-1].replace(".mp4", ".wav")
        audio_path = f"{self.context.shared_storage_path}/audio/{audio_filename}"

        return {
            "audio_path": audio_path
        }

    def get_cache_key_fields(self) -> List[str]:
        """
        音频提取的缓存键仅依赖输入视频路径。

        相同的视频路径会复用之前的提取结果。
        """
        return ["video_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        音频提取必须产生 audio_path 字段。

        如果该字段不存在或为空，缓存无效。
        """
        return ["audio_path"]


# 使用示例
if __name__ == "__main__":
    from services.common.context import WorkflowContext
    from services.common.validators import NodeResponseValidator

    # 创建工作流上下文
    context = WorkflowContext(
        workflow_id="task-demo-001",
        shared_storage_path="/share/workflows/task-demo-001",
        input_params={
            "input_data": {
                "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
            },
            "core": {
                "auto_upload_to_minio": True
            }
        }
    )

    # 执行节点
    executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
    result_context = executor.execute()

    # 打印结果
    print("=" * 60)
    print("执行结果:")
    print("=" * 60)
    print(f"状态: {result_context.stages['ffmpeg.extract_audio'].status}")
    print(f"输出: {result_context.stages['ffmpeg.extract_audio'].output}")
    print(f"时长: {result_context.stages['ffmpeg.extract_audio'].duration}秒")

    # 验证响应格式
    print("\n" + "=" * 60)
    print("格式验证:")
    print("=" * 60)
    validator = NodeResponseValidator(strict_mode=False)
    is_valid = validator.validate(result_context, "ffmpeg.extract_audio")
    print(validator.get_validation_report())
