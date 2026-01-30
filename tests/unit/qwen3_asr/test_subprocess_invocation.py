import json
from pathlib import Path
from services.workers.qwen3_asr_service.executors.transcribe_executor import build_infer_command


def test_build_infer_command(tmp_path):
    out = tmp_path / "out.json"
    cmd = build_infer_command(
        audio_path="/tmp/a.wav",
        output_file=str(out),
        model_name="Qwen/Qwen3-ASR-0.6B",
        backend="vllm",
        language="Chinese",
        enable_word_timestamps=True,
        forced_aligner_model="Qwen/Qwen3-ForcedAligner-0.6B",
    )
    cmd_str = " ".join(cmd)
    assert "--audio_path" in cmd_str
    assert "--backend" in cmd_str
    assert "vllm" in cmd_str
    assert "--language" in cmd_str
