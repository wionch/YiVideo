from services.common.subtitle.subtitle_line_translator import SubtitleLineTranslator


def test_translate_lines_fails_on_line_count_mismatch():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.0, "end": 2.0, "text": "World"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "你好"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is False
    assert "行数不一致" in result["error"]


def test_translate_lines_fails_on_budget_exceeded():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hi"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "这是一个非常非常非常长的句子超过预算了"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=10,
        max_retries=1,
    )

    assert result["success"] is False
    assert "超出字符预算" in result["error"]


def test_translate_lines_forces_single_line_budget():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hi"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "12345678901"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=10,
        max_lines=2,
        max_retries=1,
    )

    assert result["success"] is False
    assert "超出字符预算" in result["error"]


def test_translate_lines_allows_empty_when_budget_zero():
    segments = [
        {"start": 0.0, "end": 0.0, "text": "Hi"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return ""

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is True
    assert result["translated_lines"] == [""]
    assert result["translated_segments"][0]["text"] == ""


def test_translate_lines_handles_mixed_zero_budget_lines():
    segments = [
        {"start": 0.0, "end": 0.0, "text": "Hi"},
        {"start": 0.0, "end": 1.0, "text": "Hello"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "\n你好"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is True
    assert result["translated_lines"] == ["", "你好"]
    assert result["translated_segments"][0]["text"] == ""
    assert result["translated_segments"][1]["text"] == "你好"


def test_translate_lines_appends_empty_for_trailing_zero_budget():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.0, "end": 1.0, "text": "Hi"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "你好"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is True
    assert result["translated_lines"] == ["你好", ""]
    assert result["translated_segments"][0]["text"] == "你好"
    assert result["translated_segments"][1]["text"] == ""


def test_translate_lines_success_returns_segments():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.0, "end": 2.0, "text": "World"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "你好\n世界"

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is True
    assert result["translated_lines"] == ["你好", "世界"]
    assert result["translated_segments"][0]["text"] == "你好"
    assert result["translated_segments"][1]["text"] == "世界"
