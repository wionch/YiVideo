from unittest.mock import patch

import pytest

from services.common.context import WorkflowContext
from services.common.validators.node_response_validator import NodeResponseValidator


@pytest.fixture()
def validator():
    return NodeResponseValidator(strict_mode=True)


@pytest.fixture()
def base_context():
    return {
        "workflow_id": "test-workflow",
        "shared_storage_path": "/share",
        "input_params": {},
        "stages": {},
    }


class TestNodeResponseFormat:
    def test_wservice_ai_optimize_text_response_format(self, validator, base_context):
        from services.workers.wservice.executors import WServiceAIOptimizeTextExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "segments_file": "/share/transcribe.json"
        }

        with patch.object(
            WServiceAIOptimizeTextExecutor,
            "execute_core_logic",
            return_value={
                "optimized_text_file": "/share/optimized_text.txt",
            },
        ):
            executor = WServiceAIOptimizeTextExecutor("wservice.ai_optimize_text", context)
            result_context = executor.execute()

        stage = result_context.stages["wservice.ai_optimize_text"]
        assert stage.status == "SUCCESS"
        assert "optimized_text_file" in stage.output

    def test_wservice_rebuild_subtitle_with_words_response_format(self, validator, base_context):
        from services.workers.wservice.executors import WServiceRebuildSubtitleWithWordsExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "segments_file": "/share/transcribe.json",
            "optimized_text": "hello world",
        }

        with patch.object(
            WServiceRebuildSubtitleWithWordsExecutor,
            "execute_core_logic",
            return_value={
                "optimized_segments_file": "/share/optimized_segments.json",
            },
        ):
            executor = WServiceRebuildSubtitleWithWordsExecutor(
                "wservice.rebuild_subtitle_with_words",
                context,
            )
            result_context = executor.execute()

        stage = result_context.stages["wservice.rebuild_subtitle_with_words"]
        assert stage.status == "SUCCESS"
        assert "optimized_segments_file" in stage.output

    def test_wservice_translate_subtitles_response_format(self, validator, base_context):
        from services.workers.wservice.executors import WServiceTranslateSubtitlesExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "segments_file": "/share/transcribe.json",
            "target_language": "zh",
        }

        with patch.object(
            WServiceTranslateSubtitlesExecutor,
            "execute_core_logic",
            return_value={
                "translated_segments_file": "/share/translated_segments.json",
            },
        ):
            executor = WServiceTranslateSubtitlesExecutor(
                "wservice.translate_subtitles",
                context,
            )
            result_context = executor.execute()

        stage = result_context.stages["wservice.translate_subtitles"]
        assert stage.status == "SUCCESS"
        assert "translated_segments_file" in stage.output
