from unittest.mock import MagicMock, patch

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


def test_rebuild_executor_generates_report(tmp_path):
    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_data": [
                    {
                        "words": [
                            {"word": "hello", "start": 0.0, "end": 0.5},
                            {"word": "world", "start": 0.5, "end": 1.0},
                        ]
                    }
                ],
                "optimized_text": "hello brave world",
                "report": True,
            }
        },
        stages={},
    )
    executor = WServiceRebuildSubtitleWithWordsExecutor(
        "wservice.rebuild_subtitle_with_words",
        context,
    )
    executor._save_optimized_segments = MagicMock(return_value="/share/out.json")
    report_path = tmp_path / "report.txt"

    with patch(
        "services.workers.wservice.executors.rebuild_subtitle_with_words_executor."
        "build_node_output_path",
        return_value=str(report_path),
    ):
        result = executor.execute_core_logic()

    assert result["report_file"] == str(report_path)
    content = report_path.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    detail_index = lines.index("变化明细:")
    assert "原字幕文本" in content
    assert "优化后的字幕文本" in content
    assert "变化明细" in content
    assert "字幕ID: 1" in content
    assert "新增" in content
    assert "brave" in content
    assert lines[detail_index + 1].startswith("字幕ID: ")


def test_rebuild_executor_report_uses_segment_id_range(tmp_path):
    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_data": [
                    {
                        "id": 3,
                        "words": [
                            {"word": "hello", "start": 0.0, "end": 0.5},
                            {"word": "there", "start": 0.5, "end": 1.0},
                        ]
                    },
                    {
                        "id": 4,
                        "words": [
                            {"word": "world", "start": 1.0, "end": 1.5},
                            {"word": "again", "start": 1.5, "end": 2.0},
                        ]
                    },
                ],
                "optimized_text": "hello earth planet again",
                "report": True,
            }
        },
        stages={},
    )
    executor = WServiceRebuildSubtitleWithWordsExecutor(
        "wservice.rebuild_subtitle_with_words",
        context,
    )
    executor._save_optimized_segments = MagicMock(return_value="/share/out.json")
    report_path = tmp_path / "report.txt"

    with patch(
        "services.workers.wservice.executors.rebuild_subtitle_with_words_executor."
        "build_node_output_path",
        return_value=str(report_path),
    ):
        result = executor.execute_core_logic()

    assert result["report_file"] == str(report_path)
    content = report_path.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    detail_index = lines.index("变化明细:")
    assert "字幕ID: 3-4" in content
    assert "替换" in content
    assert lines[detail_index + 1].startswith("字幕ID: ")
