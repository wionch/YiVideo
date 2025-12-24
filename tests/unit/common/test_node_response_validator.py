# tests/unit/common/test_node_response_validator.py
# -*- coding: utf-8 -*-

"""NodeResponseValidator 单元测试"""

import pytest
from services.common.validators import NodeResponseValidator, ValidationError
from services.common.context import WorkflowContext, StageExecution


class TestNodeResponseValidator:
    """NodeResponseValidator 测试"""

    def test_valid_response(self):
        """测试有效响应验证通过"""
        context = WorkflowContext(
            workflow_id="task-001",
            shared_storage_path="/share/workflows/task-001",
            input_params={"input_data": {}}
        )

        # 添加有效的阶段执行结果
        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={"video_path": "/share/video.mp4"},
            output={"audio_path": "/share/audio.wav"},
            error=None,
            duration=1.5
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert is_valid
        assert len(validator.errors) == 0

    def test_missing_stage(self):
        """测试缺失阶段"""
        context = WorkflowContext(
            workflow_id="task-002",
            shared_storage_path="/share/workflows/task-002",
            input_params={}
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "nonexistent.node")

        assert not is_valid
        assert len(validator.errors) == 1
        assert "not found" in validator.errors[0]

    def test_missing_stage_strict_mode(self):
        """测试严格模式下缺失阶段抛出异常"""
        context = WorkflowContext(
            workflow_id="task-003",
            shared_storage_path="/share/workflows/task-003",
            input_params={}
        )

        validator = NodeResponseValidator(strict_mode=True)

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(context, "nonexistent.node")

        assert "not found" in str(exc_info.value)

    def test_invalid_status(self):
        """测试无效状态值"""
        context = WorkflowContext(
            workflow_id="task-004",
            shared_storage_path="/share/workflows/task-004",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="success",  # 小写,无效
            input_params={},
            output={},
            error=None,
            duration=0.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert not is_valid
        assert any("Invalid status" in error for error in validator.errors)

    def test_incorrect_minio_url_naming(self):
        """测试错误的 MinIO URL 命名"""
        context = WorkflowContext(
            workflow_id="task-005",
            shared_storage_path="/share/workflows/task-005",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={
                "keyframe_dir": "/share/keyframes",
                "keyframe_minio_url": "http://..."  # 错误:缺少 _dir
            },
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert not is_valid
        # 错误消息可能是 "corresponding local field" 或 "naming convention"
        assert any("corresponding local field" in error or "naming convention" in error for error in validator.errors)

    def test_non_standard_duration_field(self):
        """测试非标准时长字段"""
        context = WorkflowContext(
            workflow_id="task-006",
            shared_storage_path="/share/workflows/task-006",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={
                "audio_path": "/share/audio.wav",
                "processing_time": 2.5  # 非标准字段
            },
            error=None,
            duration=2.5
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert not is_valid
        assert any("Non-standard duration field" in error for error in validator.errors)

    def test_provenance_field_validation(self):
        """测试数据溯源字段验证"""
        context = WorkflowContext(
            workflow_id="task-007",
            shared_storage_path="/share/workflows/task-007",
            input_params={}
        )

        # 完整的溯源信息
        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={
                "audio_path": "/share/audio.wav",
                "provenance": {
                    "source_stage": "previous.node",
                    "source_field": "output_path"
                }
            },
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert is_valid

    def test_incomplete_provenance_field(self):
        """测试不完整的溯源字段"""
        context = WorkflowContext(
            workflow_id="task-008",
            shared_storage_path="/share/workflows/task-008",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={
                "audio_path": "/share/audio.wav",
                "provenance": {
                    "source_stage": "previous.node"
                    # 缺少 source_field
                }
            },
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert not is_valid
        assert any("Provenance field missing" in error for error in validator.errors)

    def test_validation_report_success(self):
        """测试成功验证的报告"""
        context = WorkflowContext(
            workflow_id="task-009",
            shared_storage_path="/share/workflows/task-009",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={"audio_path": "/share/audio.wav"},
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        validator.validate(context, "test.node")
        report = validator.get_validation_report()

        assert "✅" in report
        assert "passed" in report

    def test_validation_report_with_errors(self):
        """测试包含错误的验证报告"""
        context = WorkflowContext(
            workflow_id="task-010",
            shared_storage_path="/share/workflows/task-010",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="success",  # 无效状态
            input_params={},
            output={"processing_time": 1.0},  # 非标准字段
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        validator.validate(context, "test.node")
        report = validator.get_validation_report()

        assert "❌" in report
        assert "error(s)" in report
        assert "Invalid status" in report
        assert "Non-standard duration field" in report

    def test_multiple_validation_errors(self):
        """测试多个验证错误"""
        context = WorkflowContext(
            workflow_id="task-011",
            shared_storage_path="/share/workflows/task-011",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="pending",  # 小写,无效
            input_params={},
            output={
                "keyframe_dir": "/share/keyframes",
                "keyframe_url": "http://...",  # 错误命名
                "transcribe_duration": 5.0  # 非标准字段
            },
            error=None,
            duration=5.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert not is_valid
        assert len(validator.errors) >= 2  # 至少2个错误（状态和非标准字段）

    def test_strict_mode_raises_exception(self):
        """测试严格模式抛出异常"""
        context = WorkflowContext(
            workflow_id="task-012",
            shared_storage_path="/share/workflows/task-012",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="success",  # 无效
            input_params={},
            output={},
            error=None,
            duration=0.0
        )

        validator = NodeResponseValidator(strict_mode=True)

        with pytest.raises(ValidationError):
            validator.validate(context, "test.node")

    def test_correct_minio_url_naming(self):
        """测试正确的 MinIO URL 命名"""
        context = WorkflowContext(
            workflow_id="task-013",
            shared_storage_path="/share/workflows/task-013",
            input_params={}
        )

        context.stages["test.node"] = StageExecution(
            status="SUCCESS",
            input_params={},
            output={
                "audio_path": "/share/audio.wav",
                "audio_path_minio_url": "http://minio:9000/yivideo/audio.wav",
                "keyframe_dir": "/share/keyframes",
                "keyframe_dir_minio_url": "http://minio:9000/yivideo/keyframes/"
            },
            error=None,
            duration=1.0
        )

        validator = NodeResponseValidator(strict_mode=False)
        is_valid = validator.validate(context, "test.node")

        assert is_valid
        assert len(validator.errors) == 0
