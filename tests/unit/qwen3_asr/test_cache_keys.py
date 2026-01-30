from services.common.context import WorkflowContext
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_cache_key_fields():
    context = WorkflowContext(shared_storage_path="/share/workflows/test")
    executor = Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    fields = executor.get_cache_key_fields()
    assert fields == [
        "audio_path",
        "backend",
        "model_size",
        "language",
        "enable_word_timestamps",
    ]


def test_required_output_fields():
    context = WorkflowContext(shared_storage_path="/share/workflows/test")
    executor = Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    assert executor.get_required_output_fields() == ["segments_file"]
