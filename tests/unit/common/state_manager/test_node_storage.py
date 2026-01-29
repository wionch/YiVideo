# -*- coding: utf-8 -*-

import pytest

import services.common.state_manager as state_manager
from services.common.context import WorkflowContext


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl = {}

    def setex(self, key, ttl_seconds, value):
        self.storage[key] = value
        self.ttl[key] = ttl_seconds
        return True

    def set(self, key, value, keepttl=False):
        self.storage[key] = value
        if not keepttl:
            self.ttl.pop(key, None)
        return True

    def get(self, key):
        return self.storage.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.storage:
                removed += 1
                self.storage.pop(key, None)
                self.ttl.pop(key, None)
        return removed

    def scan_iter(self, match=None, count=10):
        if not match:
            for key in list(self.storage.keys()):
                yield key
            return
        prefix = match.split("*", 1)[0]
        for key in list(self.storage.keys()):
            if key.startswith(prefix):
                yield key


def _build_context(task_id="task-1", task_name="ffmpeg.extract_audio"):
    return WorkflowContext(
        workflow_id=task_id,
        create_at="2026-01-29T00:00:00",
        input_params={
            "task_name": task_name,
            "input_data": {"video_path": "demo.mp4"},
            "callback_url": None,
        },
        shared_storage_path=f"/share/workflows/{task_id}",
        stages={
            task_name: {
                "status": "SUCCESS",
                "output": {"audio_path": "/share/workflows/demo.wav"},
                "error": None,
                "duration": 1.0,
            }
        },
        error=None,
    )


def test_create_workflow_state_writes_node_key(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    context = _build_context()
    state_manager.create_workflow_state(context)

    key = f"{context.workflow_id}:ffmpeg:extract_audio"
    assert key in fake.storage
    assert fake.ttl[key] == 24 * 60 * 60


def test_get_workflow_state_aggregates_nodes(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    ctx_a = _build_context(task_name="ffmpeg.extract_audio")
    ctx_b = _build_context(task_name="faster_whisper.transcribe")

    state_manager.create_workflow_state(ctx_a)
    state_manager.create_workflow_state(ctx_b)

    merged = state_manager.get_workflow_state(ctx_a.workflow_id)
    assert merged["workflow_id"] == ctx_a.workflow_id
    assert "stages" in merged
    assert "ffmpeg.extract_audio" in merged["stages"]
    assert "faster_whisper.transcribe" in merged["stages"]


def test_create_workflow_state_requires_task_name(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    context = WorkflowContext(
        workflow_id="task-2",
        create_at="2026-01-29T00:00:00",
        input_params={
            "input_data": {"video_path": "demo.mp4"},
            "callback_url": None,
        },
        shared_storage_path="/share/workflows/task-2",
        stages={
            "ffmpeg.extract_audio": {
                "status": "SUCCESS",
                "output": {"audio_path": "/share/workflows/demo.wav"},
                "error": None,
                "duration": 1.0,
            },
            "faster_whisper.transcribe": {
                "status": "SUCCESS",
                "output": {"text": "demo"},
                "error": None,
                "duration": 2.0,
            },
        },
        error=None,
    )

    with pytest.raises(ValueError):
        state_manager.create_workflow_state(context)


def test_create_workflow_state_requires_valid_task_name(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    context = WorkflowContext(
        workflow_id="task-3",
        create_at="2026-01-29T00:00:00",
        input_params={
            "task_name": "invalid_task_name",
            "input_data": {"video_path": "demo.mp4"},
            "callback_url": None,
        },
        shared_storage_path="/share/workflows/task-3",
        stages={
            "invalid_task_name": {
                "status": "SUCCESS",
                "output": {"audio_path": "/share/workflows/demo.wav"},
                "error": None,
                "duration": 1.0,
            }
        },
        error=None,
    )

    with pytest.raises(ValueError):
        state_manager.create_workflow_state(context)
