"""
单元测试: 验证wservice中的迁移任务

此测试验证从faster_whisper_service迁移的4个非GPU任务在wservice中正确实现。
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestMigratedTasks:
    """测试从faster_whisper_service迁移到wservice的任务"""

    def test_generate_subtitle_files_exists(self):
        """验证generate_subtitle_files任务存在于wservice"""
        from services.workers.wservice.app.tasks import generate_subtitle_files

        assert generate_subtitle_files is not None
        assert callable(generate_subtitle_files)

    def test_merge_speaker_segments_exists(self):
        """验证merge_speaker_segments任务存在于wservice"""
        from services.workers.wservice.app.tasks import merge_speaker_segments

        assert merge_speaker_segments is not None
        assert callable(merge_speaker_segments)

    def test_merge_with_word_timestamps_exists(self):
        """验证merge_with_word_timestamps任务存在于wservice"""
        from services.workers.wservice.app.tasks import merge_with_word_timestamps

        assert merge_with_word_timestamps is not None
        assert callable(merge_with_word_timestamps)

    def test_correct_subtitles_exists(self):
        """验证correct_subtitles任务存在于wservice"""
        from services.workers.wservice.app.tasks import correct_subtitles

        assert correct_subtitles is not None
        assert callable(correct_subtitles)

    def test_all_migrated_tasks_use_celery_decorator(self):
        """验证所有迁移的任务都使用正确的Celery装饰器"""
        from services.workers.wservice.app.tasks import (
            generate_subtitle_files,
            merge_speaker_segments,
            merge_with_word_timestamps,
            correct_subtitles
        )

        tasks = [
            ('generate_subtitle_files', generate_subtitle_files),
            ('merge_speaker_segments', merge_speaker_segments),
            ('merge_with_word_timestamps', merge_with_word_timestamps),
            ('correct_subtitles', correct_subtitles)
        ]

        for name, task in tasks:
            # 验证任务有正确的名称
            assert hasattr(task, 'name'), f"Task {name} should have 'name' attribute"
            assert task.name.startswith('wservice.'), f"Task {name} should have wservice prefix"

    def test_helper_functions_exist_in_wservice(self):
        """验证辅助函数在wservice中存在"""
        import inspect
        from services.workers.wservice.app import tasks

        # 获取所有函数
        all_functions = [
            name for name, obj in inspect.getmembers(tasks)
            if inspect.isfunction(obj) and hasattr(obj, '__name__')
        ]

        # 这些辅助函数应该存在于wservice（作为标准实现）
        required_helpers = [
            'load_segments_from_file',
            'load_speaker_data_from_file',
            'get_segments_data',
            'segments_to_word_timestamp_json',
            'get_speaker_data'
        ]

        for helper in required_helpers:
            assert helper in all_functions, f"Helper function {helper} should exist in wservice"

    @patch('services.workers.wservice.app.tasks.WorkflowContext')
    @patch('services.workers.wservice.app.tasks.state_manager')
    def test_generate_subtitle_files_signature(self, mock_state_manager, mock_context):
        """验证generate_subtitle_files函数签名正确"""
        from services.workers.wservice.app.tasks import generate_subtitle_files
        import inspect

        sig = inspect.signature(generate_subtitle_files)
        params = list(sig.parameters.keys())

        # 验证参数：self, context
        assert 'self' in params
        assert 'context' in params
        assert len(params) == 2

    @patch('services.workers.wservice.app.tasks.WorkflowContext')
    @patch('services.workers.wservice.app.tasks.state_manager')
    def test_merge_speaker_segments_signature(self, mock_state_manager, mock_context):
        """验证merge_speaker_segments函数签名正确"""
        from services.workers.wservice.app.tasks import merge_speaker_segments
        import inspect

        sig = inspect.signature(merge_speaker_segments)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert 'context' in params
        assert len(params) == 2

    @patch('services.workers.wservice.app.tasks.WorkflowContext')
    @patch('services.workers.wservice.app.tasks.state_manager')
    def test_merge_with_word_timestamps_signature(self, mock_state_manager, mock_context):
        """验证merge_with_word_timestamps函数签名正确"""
        from services.workers.wservice.app.tasks import merge_with_word_timestamps
        import inspect

        sig = inspect.signature(merge_with_word_timestamps)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert 'context' in params
        assert len(params) == 2

    @patch('services.workers.wservice.app.tasks.WorkflowContext')
    @patch('services.workers.wservice.app.tasks.state_manager')
    def test_correct_subtitles_signature(self, mock_state_manager, mock_context):
        """验证correct_subtitles函数签名正确"""
        from services.workers.wservice.app.tasks import correct_subtitles
        import inspect

        sig = inspect.signature(correct_subtitles)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert 'context' in params
        assert len(params) == 2


if __name__ == '__main__':
    pytest.main([__file__])
