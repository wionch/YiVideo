# tests/unit/common/test_state_manager_upload_dedup.py
# -*- coding: utf-8 -*-

"""
MinIO 文件上传去重逻辑单元测试

测试 state_manager.py::_upload_files_to_minio() 的去重功能
"""

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

from services.common.context import WorkflowContext, StageExecution
from services.common.state_manager import _upload_files_to_minio


@pytest.fixture
def mock_file_service():
    """Mock FileService"""
    with patch('services.common.file_service.get_file_service') as mock_get:
        mock_service = MagicMock()
        mock_service.upload_to_minio.return_value = "http://minio:9000/yivideo/test/file.wav"
        mock_get.return_value = mock_service
        yield mock_service


@pytest.fixture
def temp_file():
    """创建临时文件用于测试"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
        f.write(b"test audio data")
        temp_path = f.name

    yield temp_path

    # 清理
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def workflow_context():
    """创建测试用的工作流上下文"""
    return WorkflowContext(
        workflow_id="test_workflow",
        input_params={},
        shared_storage_path="/share/workflows/test_workflow",
        stages={}
    )


class TestSingleFileDeduplication:
    """测试单个文件字段的去重逻辑"""

    def test_first_upload_succeeds(self, workflow_context, temp_file, mock_file_service):
        """测试首次上传成功"""
        # Given: 工作流上下文包含文件路径,但没有 MinIO URL
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 文件被上传
        mock_file_service.upload_to_minio.assert_called_once()
        assert "audio_path_minio_url" in workflow_context.stages["test_stage"].output

    def test_skip_already_uploaded_file(self, workflow_context, temp_file, mock_file_service):
        """测试跳过已上传的单个文件"""
        # Given: 工作流上下文包含文件路径和 MinIO URL
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": "http://minio:9000/yivideo/test/existing.wav"
            }
        )

        # When: 调用上传函数
        with patch('services.common.state_manager.logger') as mock_logger:
            _upload_files_to_minio(workflow_context)

            # Then: 文件未被上传,记录了跳过日志
            mock_file_service.upload_to_minio.assert_not_called()
            # 验证日志包含关键信息（不检查完整URL）
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("跳过已上传的文件: audio_path" in call for call in info_calls)

    def test_upload_when_minio_url_missing(self, workflow_context, temp_file, mock_file_service):
        """测试 MinIO URL 缺失时正常上传"""
        # Given: 工作流上下文包含文件路径,但 MinIO URL 字段不存在
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 文件被上传
        mock_file_service.upload_to_minio.assert_called_once()
        assert "audio_path_minio_url" in workflow_context.stages["test_stage"].output

    def test_skip_http_url_path(self, workflow_context, mock_file_service):
        """测试跳过 HTTP URL 路径"""
        # Given: 工作流上下文包含 HTTP URL
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": "http://example.com/audio.wav"
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 文件未被上传
        mock_file_service.upload_to_minio.assert_not_called()


class TestArrayFileDeduplication:
    """测试数组文件字段的去重逻辑"""

    def test_skip_already_uploaded_array(self, workflow_context, temp_file, mock_file_service):
        """测试跳过已上传的文件数组"""
        # Given: 工作流上下文包含文件数组和 MinIO URL 数组
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "all_audio_files": [temp_file],
                "all_audio_files_minio_urls": ["http://minio:9000/yivideo/test/file1.wav"]
            }
        )

        # When: 调用上传函数
        with patch('services.common.state_manager.logger') as mock_logger:
            _upload_files_to_minio(workflow_context)

            # Then: 文件未被上传,记录了跳过日志
            mock_file_service.upload_to_minio.assert_not_called()
            mock_logger.info.assert_any_call(
                "跳过已上传的文件数组: all_audio_files (已有 all_audio_files_minio_urls)"
            )

    def test_upload_array_when_minio_urls_missing(self, workflow_context, temp_file, mock_file_service):
        """测试 MinIO URL 数组缺失时正常上传"""
        # Given: 工作流上下文包含文件数组,但 MinIO URL 数组不存在
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "all_audio_files": [temp_file]
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 文件被上传
        mock_file_service.upload_to_minio.assert_called_once()
        assert "all_audio_files_minio_urls" in workflow_context.stages["test_stage"].output

    def test_skip_empty_minio_urls_array(self, workflow_context, temp_file, mock_file_service):
        """测试空的 MinIO URL 数组时正常上传"""
        # Given: 工作流上下文包含文件数组,但 MinIO URL 数组为空
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "all_audio_files": [temp_file],
                "all_audio_files_minio_urls": []
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 文件被上传 (因为数组为空,不满足去重条件)
        mock_file_service.upload_to_minio.assert_called_once()


class TestLogObservability:
    """测试日志可观测性"""

    def test_log_message_on_skip_single_file(self, workflow_context, temp_file):
        """测试跳过单个文件时记录正确日志"""
        # Given: 已上传的文件
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": "http://minio:9000/yivideo/test/existing.wav"
            }
        )

        # When: 调用上传函数
        with patch('services.common.state_manager.logger') as mock_logger:
            _upload_files_to_minio(workflow_context)

            # Then: 记录了正确的日志
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("跳过已上传的文件: audio_path" in call for call in info_calls)

    def test_log_message_on_skip_array(self, workflow_context, temp_file):
        """测试跳过文件数组时记录正确日志"""
        # Given: 已上传的文件数组
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "all_audio_files": [temp_file],
                "all_audio_files_minio_urls": ["http://minio:9000/yivideo/test/file1.wav"]
            }
        )

        # When: 调用上传函数
        with patch('services.common.state_manager.logger') as mock_logger:
            _upload_files_to_minio(workflow_context)

            # Then: 记录了正确的日志
            mock_logger.info.assert_any_call(
                "跳过已上传的文件数组: all_audio_files (已有 all_audio_files_minio_urls)"
            )


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_data_structure_unchanged(self, workflow_context, temp_file, mock_file_service):
        """测试数据结构保持不变"""
        # Given: 工作流上下文包含文件路径
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 数据结构包含原始路径和 MinIO URL
        output = workflow_context.stages["test_stage"].output
        assert "audio_path" in output  # 原始路径保留
        assert output["audio_path"] == temp_file
        assert "audio_path_minio_url" in output  # MinIO URL 新增
        assert "audio_path_uploaded" not in output  # 没有额外的标记字段

    def test_no_additional_fields(self, workflow_context, temp_file, mock_file_service):
        """测试不会新增额外字段"""
        # Given: 工作流上下文
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file
            }
        )

        original_keys = set(workflow_context.stages["test_stage"].output.keys())

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 只新增了 _minio_url 字段
        new_keys = set(workflow_context.stages["test_stage"].output.keys())
        added_keys = new_keys - original_keys
        assert added_keys == {"audio_path_minio_url"}


class TestMultipleStages:
    """测试多阶段场景"""

    def test_dedup_across_stages(self, workflow_context, temp_file, mock_file_service):
        """测试跨阶段去重"""
        # Given: 多个阶段包含相同的文件路径
        workflow_context.stages["stage1"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": "http://minio:9000/yivideo/test/file.wav"
            }
        )
        workflow_context.stages["stage2"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": "http://minio:9000/yivideo/test/file.wav"
            }
        )

        # When: 调用上传函数
        _upload_files_to_minio(workflow_context)

        # Then: 两个阶段的文件都不会被上传
        mock_file_service.upload_to_minio.assert_not_called()


class TestEmptyUrlHandling:
    """测试空URL和无效URL的处理"""

    def test_empty_string_minio_url_triggers_upload(self, workflow_context, temp_file, mock_file_service):
        """测试空字符串MinIO URL会触发重新上传"""
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": ""  # 空字符串，应该触发上传
            }
        )

        _upload_files_to_minio(workflow_context)

        # 验证上传被调用（因为URL为空）
        mock_file_service.upload_to_minio.assert_called_once()

        # 验证MinIO URL被更新
        assert workflow_context.stages["test_stage"].output["audio_path_minio_url"] != ""
        assert workflow_context.stages["test_stage"].output["audio_path_minio_url"].startswith("http://")

    def test_empty_array_minio_urls_triggers_upload(self, workflow_context, temp_file, mock_file_service):
        """测试空数组MinIO URLs会触发重新上传"""
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "all_audio_files": [temp_file],
                "all_audio_files_minio_urls": []  # 空数组，应该触发上传
            }
        )

        _upload_files_to_minio(workflow_context)

        # 验证上传被调用
        mock_file_service.upload_to_minio.assert_called_once()
        
        # 验证MinIO URLs被填充
        assert len(workflow_context.stages["test_stage"].output["all_audio_files_minio_urls"]) == 1
        assert workflow_context.stages["test_stage"].output["all_audio_files_minio_urls"][0].startswith("http://")

    def test_invalid_url_format_triggers_reupload(self, workflow_context, temp_file, mock_file_service):
        """测试无效URL格式（不以http开头）会触发重新上传"""
        workflow_context.stages["test_stage"] = StageExecution(
            status="SUCCESS",
            output={
                "audio_path": temp_file,
                "audio_path_minio_url": "invalid-url-format"  # 无效格式
            }
        )

        with patch('services.common.state_manager.logger') as mock_logger:
            _upload_files_to_minio(workflow_context)

            # 验证上传被调用
            mock_file_service.upload_to_minio.assert_called_once()
            
            # 验证日志警告
            warning_calls = [call for call in mock_logger.warning.call_args_list 
                            if "无效的MinIO URL" in str(call)]
            assert len(warning_calls) > 0

            # 验证URL被修正
            assert workflow_context.stages["test_stage"].output["audio_path_minio_url"].startswith("http://")
