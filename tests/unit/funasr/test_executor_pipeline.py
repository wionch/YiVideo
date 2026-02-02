from types import SimpleNamespace
from unittest import mock

import services.workers.funasr_service.executors.transcribe_executor as transcribe_executor
from services.workers.funasr_service.executors.transcribe_executor import (
    FunASRTranscribeExecutor,
)


def test_executor_pipeline(monkeypatch, tmp_path):
    context = SimpleNamespace(
        workflow_id="wf-1",
        shared_storage_path="/share/workflows/wf-1",
        stages={},
        error=None,
    )
    executor = FunASRTranscribeExecutor("funasr.transcribe_audio", context)
    executor.get_input_data = lambda: {"audio_path": "/tmp/demo.wav"}

    fake_file_service = mock.Mock()
    fake_file_service.resolve_and_download.return_value = "/tmp/demo.wav"
    monkeypatch.setattr(transcribe_executor, "get_file_service", lambda: fake_file_service)
    monkeypatch.setattr(transcribe_executor.os.path, "exists", lambda _: True)
    monkeypatch.setattr(
        transcribe_executor,
        "build_node_output_path",
        lambda *args, **kwargs: str(tmp_path / "out.json"),
    )
    monkeypatch.setattr(transcribe_executor.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(transcribe_executor, "ensure_directory", lambda *_: None)
    fake_payload = {
        "text": "hi",
        "language": "en",
        "audio_duration": 1.0,
        "time_stamps": [],
        "speaker": None,
        "transcribe_duration": 0.2,
    }
    monkeypatch.setattr(transcribe_executor, "_run_infer", lambda *args, **kwargs: fake_payload)
    result = executor.execute()
    assert "segments_file" in result.stages["funasr.transcribe_audio"].output
