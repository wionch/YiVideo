from unittest.mock import MagicMock

from services.common.context import WorkflowContext
from services.workers.wservice.executors.rebuild_subtitle_with_words_executor import (
    WServiceRebuildSubtitleWithWordsExecutor,
)


def test_rebuild_executor_outputs_file():
    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_data": [
                    {
                        "words": [
                            {"word": "hello", "start": 1.0, "end": 1.2}
                        ]
                    }
                ],
                "optimized_text": "hello",
            }
        },
        stages={},
    )
    executor = WServiceRebuildSubtitleWithWordsExecutor(
        "wservice.rebuild_subtitle_with_words",
        context,
    )
    executor._save_optimized_segments = MagicMock(return_value="/share/out.json")

    result = executor.execute_core_logic()
    assert "optimized_segments_file" in result


def test_rebuild_executor_splits_by_punctuation_and_limits():
    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_data": [
                    {
                        "words": [
                            {"word": " hello", "start": 0.0, "end": 0.5},
                            {"word": " world.", "start": 0.5, "end": 1.0},
                            {"word": " next", "start": 1.0, "end": 1.5},
                            {"word": " line", "start": 1.5, "end": 2.0},
                        ]
                    }
                ],
                "optimized_text": "hello world. next line",
            }
        },
        stages={},
    )
    executor = WServiceRebuildSubtitleWithWordsExecutor(
        "wservice.rebuild_subtitle_with_words",
        context,
    )
    captured = {}

    def _capture_segments(segments, input_data):
        captured["segments"] = segments
        return "/share/out.json"

    executor._save_optimized_segments = _capture_segments

    result = executor.execute_core_logic()
    segments = captured["segments"]
    assert result["optimized_segments_file"]
    assert len(segments) == 2
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 1.0
    assert segments[1]["start"] == 1.0
    assert segments[1]["end"] == 2.0
