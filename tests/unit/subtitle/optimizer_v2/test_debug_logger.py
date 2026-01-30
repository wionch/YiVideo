"""调试日志记录器测试"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from services.common.subtitle.optimizer_v2.debug_logger import DebugLogger


class TestDebugLogger:
    """DebugLogger测试类"""

    def test_init_creates_directory_when_enabled(self, tmp_path):
        """测试初始化时创建日志目录(启用状态)"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        assert log_dir.exists()
        assert logger.enabled is True

    def test_init_does_not_create_directory_when_disabled(self, tmp_path):
        """测试初始化时不创建日志目录(禁用状态)"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=False)

        assert not log_dir.exists()
        assert logger.enabled is False

    def test_log_request_creates_file(self, tmp_path):
        """测试记录请求时创建文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_request(
            task_id="task-001",
            segment_idx=0,
            prompt="测试提示词",
            model="gpt-4",
        )

        expected_file = log_dir / "task-001_seg0_request.txt"
        assert expected_file.exists()

        content = expected_file.read_text(encoding="utf-8")
        assert "LLM 请求" in content
        assert "测试提示词" in content
        assert "gpt-4" in content

    def test_log_request_with_extra(self, tmp_path):
        """测试记录请求时包含额外信息"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_request(
            task_id="task-002",
            segment_idx=1,
            prompt="测试提示词",
            extra={"temperature": 0.7, "max_tokens": 1000},
        )

        expected_file = log_dir / "task-002_seg1_request.txt"
        content = expected_file.read_text(encoding="utf-8")
        assert "temperature" in content
        assert "0.7" in content
        assert "max_tokens" in content

    def test_log_request_disabled_does_not_write(self, tmp_path):
        """测试禁用时记录请求不写入文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=False)

        logger.log_request(
            task_id="task-003",
            segment_idx=0,
            prompt="测试提示词",
        )

        # 目录不应被创建
        assert not log_dir.exists()

    def test_log_response_creates_file(self, tmp_path):
        """测试记录响应时创建文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_response(
            task_id="task-004",
            segment_idx=2,
            response="优化后的字幕内容",
            latency_ms=1500.5,
        )

        expected_file = log_dir / "task-004_seg2_response.txt"
        assert expected_file.exists()

        content = expected_file.read_text(encoding="utf-8")
        assert "LLM 响应" in content
        assert "优化后的字幕内容" in content
        assert "1500.5" in content

    def test_log_response_without_latency(self, tmp_path):
        """测试记录响应时不包含延迟信息"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_response(
            task_id="task-005",
            segment_idx=0,
            response="响应内容",
        )

        expected_file = log_dir / "task-005_seg0_response.txt"
        content = expected_file.read_text(encoding="utf-8")
        assert "响应内容" in content
        assert "latency_ms" not in content

    def test_log_response_disabled_does_not_write(self, tmp_path):
        """测试禁用时记录响应不写入文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=False)

        logger.log_response(
            task_id="task-006",
            segment_idx=0,
            response="响应内容",
        )

        assert not log_dir.exists()

    def test_log_error_creates_file(self, tmp_path):
        """测试记录错误时创建文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        error = ValueError("测试错误信息")
        logger.log_error(
            task_id="task-007",
            segment_idx=3,
            error=error,
            context={"segment_text": "原始字幕文本"},
        )

        expected_file = log_dir / "task-007_seg3_error.txt"
        assert expected_file.exists()

        content = expected_file.read_text(encoding="utf-8")
        assert "错误日志" in content
        assert "ValueError" in content
        assert "测试错误信息" in content
        assert "原始字幕文本" in content

    def test_log_error_without_context(self, tmp_path):
        """测试记录错误时不包含上下文"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        error = RuntimeError("运行时错误")
        logger.log_error(
            task_id="task-008",
            segment_idx=0,
            error=error,
        )

        expected_file = log_dir / "task-008_seg0_error.txt"
        content = expected_file.read_text(encoding="utf-8")
        assert "RuntimeError" in content
        assert "运行时错误" in content

    def test_log_error_disabled_does_not_write(self, tmp_path):
        """测试禁用时记录错误不写入文件"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=False)

        error = Exception("错误")
        logger.log_error(
            task_id="task-009",
            segment_idx=0,
            error=error,
        )

        assert not log_dir.exists()

    def test_is_enabled(self):
        """测试is_enabled方法"""
        logger_enabled = DebugLogger(enabled=True)
        logger_disabled = DebugLogger(enabled=False)

        assert logger_enabled.is_enabled() is True
        assert logger_disabled.is_enabled() is False

    def test_file_naming_format(self, tmp_path):
        """测试文件命名格式"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_request(task_id="my-task", segment_idx=5, prompt="test")
        logger.log_response(task_id="my-task", segment_idx=5, response="test")
        logger.log_error(task_id="my-task", segment_idx=5, error=Exception("test"))

        assert (log_dir / "my-task_seg5_request.txt").exists()
        assert (log_dir / "my-task_seg5_response.txt").exists()
        assert (log_dir / "my-task_seg5_error.txt").exists()

    def test_format_content_structure(self, tmp_path):
        """测试内容格式结构"""
        log_dir = tmp_path / "test_logs"
        logger = DebugLogger(log_dir=str(log_dir), enabled=True)

        logger.log_request(
            task_id="task-010",
            segment_idx=0,
            prompt="测试",
        )

        content = (log_dir / "task-010_seg0_request.txt").read_text(encoding="utf-8")
        # 检查分隔线
        assert "=" * 60 in content
        # 检查时间戳格式
        assert "时间:" in content
        # 检查标题
        assert "LLM 请求" in content
