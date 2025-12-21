import json
import tempfile
from datetime import datetime

import pytest

from services.common import state_manager
from services.common.context import WorkflowContext
from services.api_gateway.app import single_task_executor as ste


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def set(self, key, value, keepttl=False):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def expire(self, key, seconds):
        return True


class FakeCallbackManager:
    def validate_callback_url(self, url: str) -> bool:
        return True

    def send_result(self, task_id, payload, minio_files, callback_url):
        return True


class FakeSig:
    def __init__(self, captured):
        self.captured = captured
        self.id = "fake-id"

    def apply_async(self):
        self.captured["apply_async_called"] = True
        return self


@pytest.fixture(autouse=True)
def patch_state_manager(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)
    return fake


@pytest.fixture
def patched_executor(monkeypatch):
    # 避免依赖真实 MinIO/Callback
    monkeypatch.setattr(ste, "get_minio_service", lambda: None)
    monkeypatch.setattr(ste, "get_callback_manager", lambda: FakeCallbackManager())
    executor = ste.SingleTaskExecutor()

    # 使用可控的 shared_storage_path
    def fake_create_task_context(task_id, task_name, input_data, callback_url=None):
        temp_dir = tempfile.mkdtemp()
        return {
            "workflow_id": task_id,
            "create_at": datetime.now().isoformat(),
            "input_params": {
                "task_name": task_name,
                "input_data": input_data,
                "callback_url": callback_url,
            },
            "shared_storage_path": temp_dir,
            "stages": {
                task_name: {
                    "status": "pending",
                    "output": {},
                    "start_time": None,
                    "end_time": None,
                }
            },
            "error": None,
        }

    monkeypatch.setattr(executor, "_create_task_context", fake_create_task_context)
    return executor


def _make_state(task_id, stage_name, status, output):
    return WorkflowContext(
        workflow_id=task_id,
        create_at=datetime.now().isoformat(),
        input_params={"task_name": stage_name, "input_data": {}, "callback_url": None},
        shared_storage_path="/tmp",
        stages={
            stage_name: {
                "status": status,
                "input_params": {},
                "output": output,
                "error": None,
                "duration": 1.0,
            }
        },
        status="completed" if status.lower() == "success" else status,
        error=None,
    )


def test_reuse_keep_existing_stages(monkeypatch, patched_executor):
    task_id = "task-demo-keep-stages"

    # 预置已有阶段（ffmpeg.extract_audio）
    existing = _make_state(
        task_id, "ffmpeg.extract_audio", "SUCCESS", {"audio_path": "/tmp/a.wav"}
    )
    state_manager.create_workflow_state(existing)

    captured = {}

    def fake_signature(task_name, kwargs=None, options=None, immutable=None):
        captured["context"] = kwargs["context"]
        return FakeSig(captured)

    monkeypatch.setattr(patched_executor.celery_app, "signature", fake_signature)

    result = patched_executor.execute_task(
        task_name="audio_separator.separate_vocals",
        task_id=task_id,
        input_data={"audio_path": "/tmp/a.wav"},
        callback_url=None,
    )

    assert result["mode"] == "scheduled"
    # Celery 负载应包含旧阶段 + 新阶段
    ctx = captured["context"]
    assert "ffmpeg.extract_audio" in ctx.get("stages", {})
    assert "audio_separator.separate_vocals" in ctx.get("stages", {})

    # Redis 中同样保留旧阶段
    redis_state = state_manager.get_workflow_state(task_id)
    assert "ffmpeg.extract_audio" in redis_state.get("stages", {})
    assert "audio_separator.separate_vocals" in redis_state.get("stages", {})


def test_pending_reuse_no_reschedule(monkeypatch, patched_executor):
    task_id = "task-demo-pending"

    pending_state = _make_state(
        task_id,
        "ffmpeg.extract_audio",
        "PENDING",
        {"audio_path": "/tmp/a.wav"},
    )
    state_manager.create_workflow_state(pending_state)

    # 如果进入复用等待态，不应调用 Celery 签名
    def forbidden_signature(*args, **kwargs):
        raise AssertionError("should not schedule when pending")

    monkeypatch.setattr(patched_executor.celery_app, "signature", forbidden_signature)

    result = patched_executor.execute_task(
        task_name="ffmpeg.extract_audio",
        task_id=task_id,
        input_data={"audio_path": "/tmp/a.wav"},
        callback_url=None,
    )

    assert result["mode"] == "reuse_pending"
    assert result["reuse_info"]["state"] in ("pending", "running")

    # 确认未增加新阶段
    redis_state = state_manager.get_workflow_state(task_id)
    assert list(redis_state.get("stages", {}).keys()) == ["ffmpeg.extract_audio"]
