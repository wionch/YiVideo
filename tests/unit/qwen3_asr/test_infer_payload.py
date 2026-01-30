import json
from services.workers.qwen3_asr_service.app import qwen3_asr_infer


def test_build_infer_payload_structure():
    payload = qwen3_asr_infer.build_infer_payload(
        text="hello",
        language="English",
        time_stamps=None,
        audio_duration=1.0,
        transcribe_duration=0.5,
    )
    assert "text" in payload
    assert "language" in payload
    assert "time_stamps" in payload
    assert "audio_duration" in payload
    assert "transcribe_duration" in payload
