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
