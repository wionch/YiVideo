import types

import pytest

from services.api_gateway.app.single_task_executor import SingleTaskExecutor
from services.common.context import StageExecution, WorkflowContext
from services.common import state_manager


def test_check_reuse_completed_uses_latest_callback(monkeypatch):
    executor = SingleTaskExecutor()
    stage_data = {
        "status": "SUCCESS",
        "output": {"audio_path": "/share/demo.wav"},
        "error": None,
        "duration": 1.1,
    }
    existing_state = {
        "workflow_id": "task-demo-001",
        "create_at": "2025-12-17T12:00:00Z",
        "input_params": {"task_name": "ffmpeg.extract_audio", "callback_url": "http://old"},
        "shared_storage_path": "/share/workflows/task-demo-001",
        "stages": {"ffmpeg.extract_audio": stage_data},
    }

    monkeypatch.setattr(executor, "_get_task_state", lambda task_id: existing_state)

    captured = {}

    def fake_update(ctx):
        captured["ctx"] = ctx.model_dump()

    monkeypatch.setattr(
        "services.api_gateway.app.single_task_executor.update_workflow_state", fake_update
    )

    reuse_result = executor._check_reuse(
        "task-demo-001", "ffmpeg.extract_audio", "http://new-cb"
    )

    assert reuse_result["reuse_hit"] is True
    assert reuse_result["state"] == "completed"
    assert reuse_result["reuse_info"]["task_name"] == "ffmpeg.extract_audio"
    assert captured["ctx"]["input_params"]["callback_url"] == "http://new-cb"
    assert captured["ctx"]["reuse_info"]["reuse_hit"] is True


def test_check_reuse_pending_no_callback(monkeypatch):
    executor = SingleTaskExecutor()
    stage_data = {"status": "PENDING", "output": {}, "error": None, "duration": 0}
    existing_state = {
        "workflow_id": "task-demo-002",
        "input_params": {"task_name": "ffmpeg.extract_audio", "callback_url": "http://old"},
        "shared_storage_path": "/share/workflows/task-demo-002",
        "stages": {"ffmpeg.extract_audio": stage_data},
    }

    monkeypatch.setattr(executor, "_get_task_state", lambda task_id: existing_state)

    called = False

    def fake_update(ctx):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "services.api_gateway.app.single_task_executor.update_workflow_state", fake_update
    )

    reuse_result = executor._check_reuse(
        "task-demo-002", "ffmpeg.extract_audio", "http://new-cb"
    )

    assert reuse_result["reuse_hit"] is True
    assert reuse_result["state"] == "pending"
    assert reuse_result["reuse_info"]["state"] == "pending"
    assert called is False


def test_state_manager_callback_selects_task_name_and_reuse_info(monkeypatch):
    sent_payload = {}

    class DummyCallbackManager:
        def send_result(self, task_id, result, minio_files, callback_url):
            sent_payload["task_id"] = task_id
            sent_payload["result"] = result
            sent_payload["callback_url"] = callback_url
            return True

    # 强制 state_manager 使用 dummy callback manager
    monkeypatch.setattr(state_manager, "get_callback_manager", lambda: DummyCallbackManager())

    stage = StageExecution(
        status="SUCCESS",
        input_params={},
        output={"audio_path": "/share/demo.wav"},
        error=None,
        duration=2.0,
    )
    ctx = WorkflowContext(
        workflow_id="task-demo-003",
        create_at="2025-12-17T12:00:00Z",
        input_params={"task_name": "ffmpeg.extract_audio", "callback_url": "http://cb"},
        shared_storage_path="/share/workflows/task-demo-003",
        stages={"ffmpeg.extract_audio": stage},
        error=None,
    )
    # 注入复用信息
    ctx.__dict__["reuse_info"] = {
        "reuse_hit": True,
        "task_name": "ffmpeg.extract_audio",
        "source": "redis",
    }

    state_manager._check_and_trigger_callback(ctx)

    assert sent_payload["task_id"] == "task-demo-003"
    assert sent_payload["callback_url"] == "http://cb"
    assert sent_payload["result"]["reuse_info"]["reuse_hit"] is True
    assert (
        sent_payload["result"]["stages"]["ffmpeg.extract_audio"]["status"]
        == "SUCCESS"
    )
