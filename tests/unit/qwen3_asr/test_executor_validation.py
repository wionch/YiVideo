import pytest
from services.common.context import WorkflowContext
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_missing_audio_path_raises():
    context = WorkflowContext(shared_storage_path="/share/workflows/test")
    executor = Qwen3ASRTranscribeExecutor("qwen3_asr.transcribe_audio", context)
    executor.get_input_data = lambda: {}
    with pytest.raises(ValueError):
        executor.validate_input()
