# tests/unit/services/common/test_parameter_resolver.py

import pytest
from services.common.parameter_resolver import get_param_with_fallback
from services.common.context import WorkflowContext, StageExecution

def test_priority_resolved_params():
    """测试优先级1: resolved_params"""
    resolved_params = {"video_path": "/resolved/path.mp4"}
    context = {
        "input_params": {
            "input_data": {"video_path": "/input_data/path.mp4"}
        }
    }

    result = get_param_with_fallback("video_path", resolved_params, context)
    assert result == "/resolved/path.mp4"


def test_fallback_input_data():
    """测试优先级2: input_data（静态值）"""
    resolved_params = {}
    context = {
        "input_params": {
            "input_data": {"subtitle_area": [0, 607, 1280, 679]}
        }
    }

    result = get_param_with_fallback("subtitle_area", resolved_params, context)
    assert result == [0, 607, 1280, 679]


def test_fallback_input_data_with_dynamic_reference():
    """测试优先级2: input_data（动态引用）"""
    resolved_params = {}
    context = {
        "input_params": {
            "input_data": {
                "subtitle_area": "${{ stages.paddleocr.detect_subtitle_area.output.subtitle_area }}"
            }
        },
        "stages": {
            "paddleocr.detect_subtitle_area": {
                "output": {"subtitle_area": [0, 918, 1920, 1080]}
            }
        }
    }

    result = get_param_with_fallback("subtitle_area", resolved_params, context)
    assert result == [0, 918, 1920, 1080]


def test_fallback_from_stage():
    """测试优先级3: 上游节点输出"""
    resolved_params = {}
    context = {
        "input_params": {"input_data": {}},
        "stages": {
            "paddleocr.detect_subtitle_area": {
                "output": {"subtitle_area": [0, 918, 1920, 1080]}
            }
        }
    }

    result = get_param_with_fallback(
        "subtitle_area",
        resolved_params,
        context,
        fallback_from_stage="paddleocr.detect_subtitle_area"
    )
    assert result == [0, 918, 1920, 1080]


def test_default_value():
    """测试优先级4: 默认值"""
    resolved_params = {}
    context = {"input_params": {"input_data": {}}, "stages": {}}

    result = get_param_with_fallback(
        "batch_size",
        resolved_params,
        context,
        default=10
    )
    assert result == 10


def test_with_workflow_context_object():
    """测试 WorkflowContext 对象兼容性"""
    resolved_params = {}
    context = WorkflowContext(
        workflow_id="test-123",
        input_params={
            "input_data": {"video_path": "/test/video.mp4"}
        },
        shared_storage_path="/share/test"
    )

    result = get_param_with_fallback("video_path", resolved_params, context)
    assert result == "/test/video.mp4"
