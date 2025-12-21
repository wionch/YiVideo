import json
import tempfile
import time
from datetime import datetime
from copy import deepcopy
from typing import Dict, Any

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
    def __init__(self):
        self.last_payload = None
        self.last_callback_url = None

    def validate_callback_url(self, url: str) -> bool:
        return True

    def send_result(self, task_id, payload, minio_files, callback_url):
        self.last_payload = payload
        self.last_callback_url = callback_url
        return True

@pytest.fixture(autouse=True)
def patch_state_manager(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)
    return fake

@pytest.fixture
def patched_executor(monkeypatch):
    callback_mgr = FakeCallbackManager()
    monkeypatch.setattr(ste, "get_minio_service", lambda: None)
    monkeypatch.setattr(ste, "get_callback_manager", lambda: callback_mgr)
    executor = ste.SingleTaskExecutor()
    executor.callback_manager = callback_mgr  # Explicitly assign for access in tests

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

def _make_multi_stage_state(task_id):
    """Creates a state with multiple completed stages"""
    return WorkflowContext(
        workflow_id=task_id,
        create_at=datetime.now().isoformat(),
        input_params={"task_name": "faster_whisper.transcribe_audio", "input_data": {}, "callback_url": None},
        shared_storage_path="/tmp",
        stages={
            "ffmpeg.extract_audio": {
                "status": "SUCCESS",
                "output": {"result": "A"},
                "duration": 1.0,
            },
            "faster_whisper.transcribe_audio": {
                "status": "SUCCESS",
                "output": {"result": "B"},
                "duration": 1.0,
            },
            "audio_separator.separate_vocals": {
                "status": "PENDING",
                "output": {},
            }
        },
        status="completed",
        error=None,
    )

def test_cache_hit_response_filtering(monkeypatch, patched_executor):
    task_id = "task-demo-filter"
    
    # 1. Preset state with multiple stages
    existing_state = _make_multi_stage_state(task_id)
    state_manager.create_workflow_state(existing_state)

    # 2. Reuse Task A (ffmpeg.extract_audio)
    # Mock signature to ensure we don't actually schedule
    def forbidden_signature(*args, **kwargs):
        raise AssertionError("should not schedule when reusing")
    monkeypatch.setattr(patched_executor.celery_app, "signature", forbidden_signature)

    result_a = patched_executor.execute_task(
        task_name="ffmpeg.extract_audio",
        task_id=task_id,
        input_data={},
        callback_url="http://cb.com/a"
    )

    assert result_a["mode"] == "reuse_completed"
    ctx_a = result_a["context"]
    # Check filtering
    assert list(ctx_a["stages"].keys()) == ["ffmpeg.extract_audio"]
    assert ctx_a["stages"]["ffmpeg.extract_audio"]["status"] == "SUCCESS"
    # Check global fields retained
    assert ctx_a["workflow_id"] == task_id
    assert ctx_a["status"] == "completed"

    # 3. Reuse Task B (faster_whisper.transcribe_audio)
    result_b = patched_executor.execute_task(
        task_name="faster_whisper.transcribe_audio",
        task_id=task_id,
        input_data={},
        callback_url="http://cb.com/b"
    )
    
    assert result_b["mode"] == "reuse_completed"
    ctx_b = result_b["context"]
    assert list(ctx_b["stages"].keys()) == ["faster_whisper.transcribe_audio"]
    
    # 4. Reuse Task C (audio_separator.separate_vocals) - Pending
    result_c = patched_executor.execute_task(
        task_name="audio_separator.separate_vocals",
        task_id=task_id,
        input_data={},
        callback_url="http://cb.com/c"
    )
    
    assert result_c["mode"] == "reuse_pending"
    ctx_c = result_c["context"]
    assert list(ctx_c["stages"].keys()) == ["audio_separator.separate_vocals"]
    assert ctx_c["stages"]["audio_separator.separate_vocals"]["status"] == "PENDING"

def test_callback_payload_filtering(monkeypatch, patched_executor):
    task_id = "task-demo-callback"
    callback_url = "http://cb.com/callback"
    
    # 1. Test Reuse Callback Filtering (T006)
    existing_state = _make_multi_stage_state(task_id)
    existing_state.input_params["callback_url"] = callback_url
    state_manager.create_workflow_state(existing_state)

    def forbidden_signature(*args, **kwargs):
        raise AssertionError("should not schedule")
    monkeypatch.setattr(patched_executor.celery_app, "signature", forbidden_signature)

    # Reuse Task A
    patched_executor.execute_task(
        task_name="ffmpeg.extract_audio",
        task_id=task_id,
        input_data={},
        callback_url=callback_url
    )

    # Wait for async thread
    time.sleep(0.1)

    callback_mgr = patched_executor.callback_manager
    assert callback_mgr.last_payload is not None
    ctx_reuse = callback_mgr.last_payload
    # Verify reuse callback payload is filtered
    assert list(ctx_reuse["stages"].keys()) == ["ffmpeg.extract_audio"]
    
    # 2. Test Normal Completion Callback Filtering (T007)
    # Reset
    callback_mgr.last_payload = None
    
    # Simulate normal completion
    full_result = existing_state.model_dump()
    
    patched_executor._send_callback_if_needed(task_id, full_result, [])
    
    assert callback_mgr.last_payload is not None
    ctx_normal = callback_mgr.last_payload
    # Verify normal callback payload is filtered (matches faster_whisper.transcribe_audio from existing_state input_params)
    assert list(ctx_normal["stages"].keys()) == ["faster_whisper.transcribe_audio"]
