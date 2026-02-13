# -*- coding: utf-8 -*-

"""Qwen3-ASR 参数透传测试。"""

from services.common.context import WorkflowContext
from services.workers.qwen3_asr_service.executors import transcribe_executor as te


def test_backend_ignore_vllm_params(monkeypatch, tmp_path):
    """非 vLLM 后端忽略 vLLM 参数。"""
    context = WorkflowContext(shared_storage_path=str(tmp_path), workflow_id="wf-params")
    executor = te.Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    executor.stage_name = "qwen3_asr.transcribe_audio"
    executor.get_input_data = lambda: {
        "audio_path": "/tmp/demo.wav",
        "backend": "transformers",
        "device": "cpu",
        "max_model_len": 60000,
        "gpu_memory_utilization": 0.5,
    }

    class _FileService:
        def resolve_and_download(self, *_args, **_kwargs):
            return str(tmp_path / "demo.wav")

    monkeypatch.setattr(te, "get_file_service", lambda: _FileService())
    monkeypatch.setattr(te.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(te.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(te.os, "remove", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(te, "build_node_output_path", lambda *_args, **_kwargs: str(tmp_path / "out.json"))
    monkeypatch.setattr(te, "ensure_directory", lambda *_args, **_kwargs: None)

    captured = {}

    def _fake_build_infer_command(
        audio_path,
        output_file,
        model_name,
        backend,
        language,
        enable_word_timestamps,
        forced_aligner_model,
        max_model_len,
        gpu_memory_utilization,
    ):
        captured["max_model_len"] = max_model_len
        captured["gpu_memory_utilization"] = gpu_memory_utilization
        return ["echo"]

    monkeypatch.setattr(te, "build_infer_command", _fake_build_infer_command)
    monkeypatch.setattr(
        te,
        "_run_infer",
        lambda *_args, **_kwargs: {
            "text": "hello",
            "language": "English",
            "time_stamps": [{"text": "hello", "start": 0.0, "end": 0.5}],
            "audio_duration": 1.0,
            "transcribe_duration": 0.1,
        },
    )

    executor.execute_core_logic()

    assert captured["max_model_len"] is None
    assert captured["gpu_memory_utilization"] is None
