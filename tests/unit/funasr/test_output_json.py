from services.workers.funasr_service.executors.transcribe_executor import (
    build_transcribe_json,
)


def test_build_transcribe_json_has_core_fields():
    data = build_transcribe_json(
        stage_name="funasr.transcribe_audio",
        workflow_id="wf-1",
        audio_file_name="demo.wav",
        segments=[{"id": 0, "start": 0.0, "end": 1.0, "text": "hi"}],
        audio_duration=1.0,
        language="zh",
        model_name="FunAudioLLM/Fun-ASR-Nano-2512",
        device="cuda",
        enable_word_timestamps=False,
        transcribe_duration=0.5,
        funasr_metadata={"vad_model": "fsmn-vad"},
    )
    assert data["metadata"]["task_name"] == "funasr.transcribe_audio"
    assert data["statistics"]["total_segments"] == 1
