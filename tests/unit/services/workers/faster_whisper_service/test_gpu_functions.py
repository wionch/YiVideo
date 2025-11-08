"""
单元测试: 验证faster_whisper_service的GPU功能（迁移后应保留）

此测试验证GPU相关功能在迁移后是否完整保留。
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestGPUFunctions:
    """测试faster_whisper_service中保留的GPU功能"""

    def test_transcribe_audio_exists(self):
        """验证transcribe_audio任务存在"""
        from services.workers.faster_whisper_service.app.tasks import transcribe_audio

        assert transcribe_audio is not None
        assert callable(transcribe_audio)

    @patch('services.workers.faster_whisper_service.app.tasks.gpu_lock')
    @patch('services.workers.faster_whisper_service.app.tasks.workflow_context')
    def test_transcribe_audio_has_gpu_lock(self, mock_context, mock_gpu_lock):
        """验证transcribe_audio使用GPU锁装饰器"""
        from services.workers.faster_whisper_service.app.tasks import transcribe_audio

        # 检查函数是否被gpu_lock装饰器包装
        assert hasattr(transcribe_audio, '__wrapped__')

    def test_non_gpu_tasks_removed(self):
        """验证非GPU任务已从faster_whisper_service中移除"""
        import inspect
        from services.workers.faster_whisper_service.app import tasks

        # 获取所有任务函数
        task_functions = [
            name for name, obj in inspect.getmembers(tasks)
            if inspect.isfunction(obj) and hasattr(obj, '__name__')
        ]

        # 验证非GPU任务不存在
        non_gpu_tasks = [
            'generate_subtitle_files',
            'merge_speaker_segments',
            'merge_with_word_timestamps',
            'correct_subtitles',
            'merge_for_tts'
        ]

        for task in non_gpu_tasks:
            assert task not in task_functions, f"Non-GPU task {task} should be removed from faster_whisper_service"

    def test_helper_functions_removed(self):
        """验证重复的辅助函数已从faster_whisper_service中移除"""
        import inspect
        from services.workers.faster_whisper_service.app import tasks

        # 获取所有函数
        all_functions = [
            name for name, obj in inspect.getmembers(tasks)
            if inspect.isfunction(obj) and hasattr(obj, '__name__')
        ]

        # 这些辅助函数应该不存在于faster_whisper_service
        duplicate_helpers = [
            'load_segments_from_file',
            'load_speaker_data_from_file',
            'get_segments_data',
            'segments_to_word_timestamp_json',
            'get_speaker_data'
        ]

        for helper in duplicate_helpers:
            assert helper not in all_functions, f"Helper function {helper} should be removed from faster_whisper_service"


if __name__ == '__main__':
    pytest.main([__file__])
