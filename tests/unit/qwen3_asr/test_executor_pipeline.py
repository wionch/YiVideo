import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_executor_parses_subprocess_output(monkeypatch, tmp_path):
    context = SimpleNamespace(shared_storage_path=str(tmp_path), workflow_id="workflow-123")
    executor = Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    executor.stage_name = "qwen3_asr.transcribe_audio"
    executor.get_input_data = lambda: {"audio_path": "/tmp/demo.wav"}

    class _FileService:
        def resolve_and_download(self, *_args, **_kwargs):
            return "/tmp/demo.wav"

    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.get_file_service",
        lambda: _FileService(),
    )
    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.os.path.exists",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.build_node_output_path",
        lambda *_args, **_kwargs: str(tmp_path / "out.json"),
    )
    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.ensure_directory",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.os.makedirs",
        lambda *_args, **_kwargs: None,
    )

    fake_output = tmp_path / "infer.json"
    fake_output.write_text(
        json.dumps(
            {
                "text": "hello",
                "language": "English",
                "time_stamps": [
                    {"text": "hello", "start": 0.0, "end": 0.5},
                ],
                "audio_duration": 1.0,
                "transcribe_duration": 0.5,
            }
        ),
        encoding="utf-8",
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor.run_gpu_command",
        lambda *_args, **_kwargs: _Result(),
    )
    monkeypatch.setattr(
        "services.workers.qwen3_asr_service.executors.transcribe_executor._read_infer_output",
        lambda *_args, **_kwargs: json.loads(fake_output.read_text()),
    )

    result = executor.execute_core_logic()
    assert "segments_file" in result
    assert result["segments_count"] >= 1
