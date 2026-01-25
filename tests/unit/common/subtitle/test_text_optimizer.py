from unittest.mock import MagicMock

from services.common.subtitle.subtitle_text_optimizer import SubtitleTextOptimizer


def test_text_optimizer_calls_ai_provider():
    optimizer = SubtitleTextOptimizer(provider="deepseek")
    optimizer._call_ai = MagicMock(return_value="fixed text")

    result = optimizer.optimize_text(
        segments=[{"id": 1, "text": "helllo"}],
        prompt_file_path=None,
    )

    assert result["success"] is True
    assert result["optimized_text"] == "fixed text"
