from unittest.mock import patch

from services.common.context import WorkflowContext
from services.workers.wservice.executors.ai_optimize_text_executor import (
    WServiceAIOptimizeTextExecutor,
)


def test_ai_optimize_text_output_without_optimized_text(tmp_path):
    segments_file = tmp_path / "segments.json"
    segments_file.write_text("[]", encoding="utf-8")
    output_path = tmp_path / "optimized.txt"

    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={"input_data": {"segments_file": str(segments_file)}},
        stages={},
    )

    with patch(
        "services.workers.wservice.executors.ai_optimize_text_executor."
        "SubtitleTextOptimizer.optimize_text",
        return_value={
            "success": True,
            "optimized_text": "hello world",
            "stats": {"provider": "test"},
        },
    ), patch(
        "services.workers.wservice.executors.ai_optimize_text_executor."
        "build_node_output_path",
        return_value=str(output_path),
    ):
        executor = WServiceAIOptimizeTextExecutor("wservice.ai_optimize_text", context)
        result = executor.execute_core_logic()

    assert "optimized_text" not in result
    assert result["optimized_text_file"] == str(output_path)
    assert output_path.read_text(encoding="utf-8") == "hello world"
