"""测试 transcr ibe_executor 的嵌套列表兼容性修复."""

import pytest
from services.workers.funasr_service.executors.transcribe_executor import (
    map_words,
    build_segments_from_payload,
)


class TestMapWordsCompatibility:
    """测试 map_words 函数对嵌套列表的处理兼容性."""

    def test_normal_time_stamps(self):
        """正常格式的时间戳应该正常工作."""
        time_stamps = [
            {"text": "hello", "start": 0.0, "end": 0.5},
            {"text": "world", "start": 0.6, "end": 1.0},
        ]
        words, count = map_words(time_stamps, enable=True)
        assert count == 2
        assert words[0]["word"] == "hello"
        assert words[1]["word"] == "world"

    def test_nested_time_stamps_single_level(self):
        """单层嵌套 [[{...}]] 应该被正确处理."""
        time_stamps = [[
            {"text": "hello", "start": 0.0, "end": 0.5},
            {"text": "world", "start": 0.6, "end": 1.0},
        ]]
        words, count = map_words(time_stamps, enable=True)
        assert count == 2
        assert words[0]["word"] == "hello"

    def test_nested_time_stamps_deep(self):
        """多层嵌套 [[[{...}]]] 应该被正确处理."""
        time_stamps = [[[
            {"text": "deep", "start": 0.0, "end": 0.5},
        ]]]
        words, count = map_words(time_stamps, enable=True)
        assert count == 1
        assert words[0]["word"] == "deep"

    def test_empty_time_stamps(self):
        """空列表应该返回空结果."""
        words, count = map_words([], enable=True)
        assert count == 0
        assert words == []

    def test_none_time_stamps(self):
        """None 应该返回空结果."""
        words, count = map_words(None, enable=True)
        assert count == 0
        assert words == []

    def test_disabled_map_words(self):
        """enable=False 应该返回空结果."""
        time_stamps = [{"text": "hello", "start": 0.0, "end": 0.5}]
        words, count = map_words(time_stamps, enable=False)
        assert count == 0
        assert words == []


class TestBuildSegmentsFromPayloadCompatibility:
    """测试 build_segments_from_payload 函数兼容性."""

    def test_normal_segments(self):
        """正常格式的 segments 应该正常工作."""
        payload = {
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "hello"},
                {"start": 1.0, "end": 2.0, "text": "world"},
            ]
        }
        segments = build_segments_from_payload(payload, audio_duration=2.0, enable_word_timestamps=False)
        assert len(segments) == 2
        assert segments[0]["text"] == "hello"
        assert segments[1]["text"] == "world"

    def test_nested_segments_single_level(self):
        """单层嵌套 segments [[{...}]] 应该被正确处理."""
        payload = {
            "segments": [[
                {"start": 0.0, "end": 1.0, "text": "nested"},
            ]]
        }
        segments = build_segments_from_payload(payload, audio_duration=1.0, enable_word_timestamps=False)
        assert len(segments) == 1
        assert segments[0]["text"] == "nested"

    def test_no_segments_uses_time_stamps(self):
        """没有 segments 时应该使用 time_stamps 构建."""
        payload = {
            "text": "hello world",
            "time_stamps": [
                {"text": "hello", "start": 0.0, "end": 0.5},
                {"text": "world", "start": 0.6, "end": 1.0},
            ]
        }
        segments = build_segments_from_payload(payload, audio_duration=1.0, enable_word_timestamps=True)
        assert len(segments) == 1
        assert segments[0]["text"] == "hello world"
        assert "words" in segments[0]

    def test_empty_payload(self):
        """空 payload 应该返回默认 segment."""
        payload = {}
        segments = build_segments_from_payload(payload, audio_duration=5.0, enable_word_timestamps=False)
        assert len(segments) == 1
        assert segments[0]["start"] == 0.0
        assert segments[0]["end"] == 5.0
        assert segments[0]["text"] == ""


class TestEdgeCases:
    """测试边界情况."""

    def test_mixed_nested_items_in_time_stamps(self):
        """time_stamps 中混合格式和嵌套应该都能处理."""
        # 虽然实际不太可能出现，但测试鲁棒性
        time_stamps = [
            {"text": "normal", "start": 0.0, "end": 0.5},
            [{"text": "nested", "start": 0.6, "end": 1.0}],  # 嵌套的单个元素
        ]
        words, count = map_words(time_stamps, enable=True)
        assert count == 2
        assert words[0]["word"] == "normal"
        assert words[1]["word"] == "nested"

    def test_segments_with_nested_items(self):
        """segments 中混合格式应该都能处理."""
        payload = {
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "normal"},
                [{"start": 1.0, "end": 2.0, "text": "nested"}],  # 嵌套
            ]
        }
        segments = build_segments_from_payload(payload, audio_duration=2.0, enable_word_timestamps=False)
        assert len(segments) == 2
        assert segments[0]["text"] == "normal"
        assert segments[1]["text"] == "nested"
