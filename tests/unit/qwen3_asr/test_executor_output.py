from services.workers.qwen3_asr_service.executors.transcribe_executor import build_transcribe_json


def test_build_transcribe_json_structure(tmp_path):
    segments = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "你好", "words": []}
    ]
    payload = build_transcribe_json(
        stage_name="qwen3_asr.transcribe_audio",
        workflow_id="workflow-123",
        audio_file_name="demo.wav",
        segments=segments,
        audio_duration=1.0,
        language="zh",
        model_name="Qwen/Qwen3-ASR-0.6B",
        device="cuda",
        enable_word_timestamps=False,
        transcribe_duration=0.5,
    )
    assert "metadata" in payload
    assert "segments" in payload
    assert "statistics" in payload
