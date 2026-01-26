import json
from unittest.mock import patch

from services.common.context import WorkflowContext
from services.workers.wservice.executors.translate_subtitles_executor import (
    WServiceTranslateSubtitlesExecutor,
)


def test_translate_subtitles_executor_returns_translated_segments_file(tmp_path):
    segments_file = tmp_path / "segments.json"
    segments_file.write_text(
        json.dumps([{"start": 0.0, "end": 1.0, "text": "hello"}]),
        encoding="utf-8",
    )

    context = WorkflowContext(
        workflow_id="test-workflow",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_file": str(segments_file),
                "target_language": "zh",
            }
        },
        stages={},
    )

    translated_segments = [{"start": 0.0, "end": 1.0, "text": "你好"}]
    output_path = tmp_path / "translated.json"

    with patch(
        "services.workers.wservice.executors.translate_subtitles_executor.SubtitleLineTranslator"
    ) as translator_cls, patch(
        "services.workers.wservice.executors.translate_subtitles_executor.build_node_output_path"
    ) as build_path:
        translator = translator_cls.return_value
        translator.translate_lines.return_value = {
            "success": True,
            "translated_segments": translated_segments,
        }
        build_path.return_value = str(output_path)

        executor = WServiceTranslateSubtitlesExecutor("wservice.translate_subtitles", context)
        result_context = executor.execute()

    stage = result_context.stages["wservice.translate_subtitles"]
    assert stage.status == "SUCCESS"
    assert stage.output["translated_segments_file"] == str(output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data[0]["text"] == "你好"
