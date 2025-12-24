"""
WService merge_speaker_segments 执行器单元测试。
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from services.workers.wservice.executors.merge_speaker_segments_executor import (
    WServiceMergeSpeakerSegmentsExecutor
)
from services.common.context import WorkflowContext, StageExecution


@pytest.fixture
def mock_context():
    """创建模拟的工作流上下文"""
    context = WorkflowContext(
        workflow_id="test_workflow_123",
        shared_storage_path="/tmp/test_storage",
        input_params={
            "node_params": {
                "wservice.merge_speaker_segments": {}
            }
        },
        stages={}
    )
    return context


@pytest.fixture
def mock_transcript_segments():
    """创建模拟的转录片段数据"""
    return [
        {
            "id": 1,
            "start": 0.0,
            "end": 5.0,
            "text": "这是第一段文本",
            "words": [
                {"word": "这是", "start": 0.0, "end": 1.0},
                {"word": "第一段", "start": 1.0, "end": 3.0},
                {"word": "文本", "start": 3.0, "end": 5.0}
            ]
        },
        {
            "id": 2,
            "start": 5.0,
            "end": 10.0,
            "text": "这是第二段文本",
            "words": [
                {"word": "这是", "start": 5.0, "end": 6.0},
                {"word": "第二段", "start": 6.0, "end": 8.0},
                {"word": "文本", "start": 8.0, "end": 10.0}
            ]
        }
    ]


@pytest.fixture
def mock_speaker_segments():
    """创建模拟的说话人片段数据"""
    return [
        {
            "start": 0.0,
            "end": 5.0,
            "speaker": "SPEAKER_00"
        },
        {
            "start": 5.0,
            "end": 10.0,
            "speaker": "SPEAKER_01"
        }
    ]


class TestWServiceMergeSpeakerSegmentsExecutor:
    """WServiceMergeSpeakerSegmentsExecutor 测试类"""

    def test_init(self, mock_context):
        """测试执行器初始化"""
        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )
        assert executor.stage_name == "wservice.merge_speaker_segments"
        assert executor.context == mock_context
        assert executor.file_service is not None

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_validate_input_with_direct_data(self, mock_get_param, mock_context):
        """测试输入验证 - 直接提供数据"""
        # 模拟参数返回
        def param_side_effect(key, *args):
            if key == "segments_data":
                return [{"start": 0, "end": 1, "text": "test"}]
            elif key == "speaker_segments_data":
                return [{"start": 0, "end": 1, "speaker": "SPEAKER_00"}]
            return None

        mock_get_param.side_effect = param_side_effect

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        # 应该不抛出异常
        executor.validate_input()

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_validate_input_with_upstream_nodes(self, mock_get_param, mock_context):
        """测试输入验证 - 从上游节点获取"""
        # 模拟没有直接参数
        mock_get_param.return_value = None

        # 添加上游节点
        mock_context.stages['faster_whisper.transcribe_audio'] = StageExecution(
            status="SUCCESS",
            output={"segments": [{"start": 0, "end": 1, "text": "test"}]}
        )
        mock_context.stages['pyannote_audio.diarize_speakers'] = StageExecution(
            status="SUCCESS",
            output={"speaker_enhanced_segments": [{"start": 0, "end": 1, "speaker": "SPEAKER_00"}]}
        )

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        # 应该不抛出异常
        executor.validate_input()

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_validate_input_missing_transcript(self, mock_get_param, mock_context):
        """测试输入验证 - 缺少转录数据"""
        mock_get_param.return_value = None

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        with pytest.raises(ValueError, match="请提供 segments_data/segments_file"):
            executor.validate_input()

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.create_subtitle_merger')
    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.validate_speaker_segments')
    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_execute_core_logic_with_direct_data(
        self,
        mock_get_param,
        mock_validate,
        mock_create_merger,
        mock_context,
        mock_transcript_segments,
        mock_speaker_segments
    ):
        """测试核心逻辑执行 - 直接数据"""
        # 模拟参数返回
        def param_side_effect(key, *args):
            if key == "segments_data":
                return mock_transcript_segments
            elif key == "speaker_segments_data":
                return mock_speaker_segments
            return None

        mock_get_param.side_effect = param_side_effect
        mock_validate.return_value = True

        # 模拟合并器
        mock_merger = MagicMock()
        merged_result = [
            {
                "id": 1,
                "start": 0.0,
                "end": 5.0,
                "text": "这是第一段文本",
                "speaker": "SPEAKER_00"
            },
            {
                "id": 2,
                "start": 5.0,
                "end": 10.0,
                "text": "这是第二段文本",
                "speaker": "SPEAKER_01"
            }
        ]
        mock_merger.merge.return_value = merged_result
        mock_create_merger.return_value = mock_merger

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        result = executor.execute_core_logic()

        # 验证结果
        assert "merged_segments" in result
        assert len(result["merged_segments"]) == 2
        assert result["merged_segments"][0]["speaker"] == "SPEAKER_00"
        assert result["merged_segments"][1]["speaker"] == "SPEAKER_01"

        assert "input_summary" in result
        assert result["input_summary"]["transcript_segments_count"] == 2
        assert result["input_summary"]["speaker_segments_count"] == 2
        assert result["input_summary"]["merged_segments_count"] == 2

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_get_transcript_segments_from_direct_data(
        self,
        mock_get_param,
        mock_context,
        mock_transcript_segments
    ):
        """测试获取转录片段 - 直接数据"""
        mock_get_param.return_value = mock_transcript_segments

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        result = executor._get_transcript_segments({})
        assert result == mock_transcript_segments

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_param_with_fallback')
    def test_get_speaker_segments_from_direct_data(
        self,
        mock_get_param,
        mock_context,
        mock_speaker_segments
    ):
        """测试获取说话人片段 - 直接数据"""
        mock_get_param.return_value = mock_speaker_segments

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        result = executor._get_speaker_segments({})
        assert result == mock_speaker_segments

    def test_normalize_path_with_url(self, mock_context):
        """测试路径规范化 - URL"""
        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        url = "http://example.com/file.json"
        result = executor._normalize_path(url)
        assert result == url

    def test_normalize_path_with_minio_url(self, mock_context):
        """测试路径规范化 - MinIO URL"""
        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        url = "minio://bucket/file.json"
        result = executor._normalize_path(url)
        assert result == url

    @patch('os.path.exists')
    def test_download_if_needed_with_local_file(self, mock_exists, mock_context):
        """测试文件下载 - 本地文件"""
        mock_exists.return_value = True

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        local_path = "/tmp/local_file.json"
        result = executor._download_if_needed(local_path)
        assert result == local_path

    @patch('services.workers.wservice.executors.merge_speaker_segments_executor.get_file_service')
    def test_download_if_needed_with_url(self, mock_get_file_service, mock_context):
        """测试文件下载 - URL"""
        mock_file_service = MagicMock()
        mock_file_service.resolve_and_download.return_value = "/tmp/downloaded_file.json"
        mock_get_file_service.return_value = mock_file_service

        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        url = "http://example.com/file.json"
        result = executor._download_if_needed(url)
        assert result == "/tmp/downloaded_file.json"

    def test_get_cache_key_fields(self, mock_context):
        """测试缓存键字段"""
        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        fields = executor.get_cache_key_fields()
        assert "segments_file" in fields
        assert "diarization_file" in fields

    def test_get_required_output_fields(self, mock_context):
        """测试必需输出字段"""
        executor = WServiceMergeSpeakerSegmentsExecutor(
            "wservice.merge_speaker_segments",
            mock_context
        )

        fields = executor.get_required_output_fields()
        assert "merged_segments" in fields
