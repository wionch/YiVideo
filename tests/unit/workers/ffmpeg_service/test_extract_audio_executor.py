"""
FFmpeg 音频提取执行器单元测试。
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.common.context import WorkflowContext
from services.workers.ffmpeg_service.executors import FFmpegExtractAudioExecutor


class TestFFmpegExtractAudioExecutor:
    """FFmpegExtractAudioExecutor 单元测试"""

    def test_successful_execution(self):
        """测试成功执行"""
        context = WorkflowContext(
            workflow_id="task-001",
            shared_storage_path="/share/workflows/task-001",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

        # Mock 文件服务和 ffmpeg 命令
        with patch('services.workers.ffmpeg_service.executors.extract_audio_executor.get_file_service') as mock_file_service, \
             patch('services.workers.ffmpeg_service.executors.extract_audio_executor.run_gpu_command') as mock_run_cmd, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024000), \
             patch('os.makedirs'):

            # 配置 mock
            mock_file_service.return_value.resolve_and_download.return_value = "/share/video.mp4"
            mock_run_cmd.return_value = Mock(stderr="")

            # 执行
            result_context = executor.execute()

            # 验证
            assert "ffmpeg.extract_audio" in result_context.stages
            stage = result_context.stages["ffmpeg.extract_audio"]
            assert stage.status == "SUCCESS"
            assert "audio_path" in stage.output
            assert stage.output["audio_path"].endswith(".wav")
            assert stage.duration > 0

    def test_missing_video_path(self):
        """测试缺少 video_path 参数"""
        context = WorkflowContext(
            workflow_id="task-002",
            shared_storage_path="/share/workflows/task-002",
            input_params={"input_data": {}}
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        result_context = executor.execute()

        stage = result_context.stages["ffmpeg.extract_audio"]
        assert stage.status == "FAILED"
        assert "缺少必需参数" in stage.error

    def test_empty_video_path(self):
        """测试空 video_path 参数"""
        context = WorkflowContext(
            workflow_id="task-003",
            shared_storage_path="/share/workflows/task-003",
            input_params={"input_data": {"video_path": ""}}
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        result_context = executor.execute()

        stage = result_context.stages["ffmpeg.extract_audio"]
        assert stage.status == "FAILED"
        assert "不能为空" in stage.error

    def test_video_file_not_found(self):
        """测试视频文件不存在"""
        context = WorkflowContext(
            workflow_id="task-004",
            shared_storage_path="/share/workflows/task-004",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

        with patch('services.workers.ffmpeg_service.executors.extract_audio_executor.get_file_service') as mock_file_service, \
             patch('os.path.exists', return_value=False):

            mock_file_service.return_value.resolve_and_download.return_value = "/share/video.mp4"

            result_context = executor.execute()

            stage = result_context.stages["ffmpeg.extract_audio"]
            assert stage.status == "FAILED"
            assert "不存在" in stage.error

    def test_ffmpeg_command_failure(self):
        """测试 ffmpeg 命令执行失败"""
        import subprocess

        context = WorkflowContext(
            workflow_id="task-005",
            shared_storage_path="/share/workflows/task-005",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

        with patch('services.workers.ffmpeg_service.executors.extract_audio_executor.get_file_service') as mock_file_service, \
             patch('services.workers.ffmpeg_service.executors.extract_audio_executor.run_gpu_command') as mock_run_cmd, \
             patch('os.path.exists', return_value=True), \
             patch('os.makedirs'):

            mock_file_service.return_value.resolve_and_download.return_value = "/share/video.mp4"

            # 模拟 ffmpeg 失败
            mock_run_cmd.side_effect = subprocess.CalledProcessError(
                1, "ffmpeg", stderr="Invalid video format"
            )

            result_context = executor.execute()

            stage = result_context.stages["ffmpeg.extract_audio"]
            assert stage.status == "FAILED"
            assert "音频提取失败" in stage.error

    def test_minio_url_generation(self):
        """测试 MinIO URL 生成"""
        context = WorkflowContext(
            workflow_id="task-006",
            shared_storage_path="/share/workflows/task-006",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": True}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

        with patch('services.workers.ffmpeg_service.executors.extract_audio_executor.get_file_service') as mock_file_service, \
             patch('services.workers.ffmpeg_service.executors.extract_audio_executor.run_gpu_command') as mock_run_cmd, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024000), \
             patch('os.makedirs'):

            mock_file_service.return_value.resolve_and_download.return_value = "/share/video.mp4"
            mock_run_cmd.return_value = Mock(stderr="")

            result_context = executor.execute()

            stage = result_context.stages["ffmpeg.extract_audio"]
            assert stage.status == "SUCCESS"
            assert "audio_path" in stage.output
            assert "audio_path_minio_url" in stage.output

    def test_cache_key_fields(self):
        """测试缓存键字段"""
        context = WorkflowContext(
            workflow_id="task-007",
            shared_storage_path="/share/workflows/task-007",
            input_params={"input_data": {"video_path": "/share/video.mp4"}}
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        cache_fields = executor.get_cache_key_fields()

        assert cache_fields == ["video_path"]

    def test_required_output_fields(self):
        """测试必需输出字段"""
        context = WorkflowContext(
            workflow_id="task-008",
            shared_storage_path="/share/workflows/task-008",
            input_params={"input_data": {"video_path": "/share/video.mp4"}}
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        required_fields = executor.get_required_output_fields()

        assert required_fields == ["audio_path"]


if __name__ == "__main__":
    # 功能验证测试
    print("开始 FFmpegExtractAudioExecutor 功能验证测试...")

    test_instance = TestFFmpegExtractAudioExecutor()

    tests = [
        ("成功执行测试", test_instance.test_successful_execution),
        ("缺少 video_path 测试", test_instance.test_missing_video_path),
        ("空 video_path 测试", test_instance.test_empty_video_path),
        ("视频文件不存在测试", test_instance.test_video_file_not_found),
        ("ffmpeg 失败测试", test_instance.test_ffmpeg_command_failure),
        ("MinIO URL 生成测试", test_instance.test_minio_url_generation),
        ("缓存键字段测试", test_instance.test_cache_key_fields),
        ("必需输出字段测试", test_instance.test_required_output_fields),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            print(f"✅ {test_name} - 通过")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} - 失败: {e}")
            failed += 1

    print(f"\n测试完成: {passed} 通过, {failed} 失败")

    if failed == 0:
        print("✅ 所有测试通过!")
    else:
        print(f"❌ {failed} 个测试失败")
