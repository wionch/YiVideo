# -*- coding: utf-8 -*-

"""Qwen3-ASR 分段策略测试。"""

from services.workers.qwen3_asr_service.executors import transcribe_executor as te


def test_short_segment_merge():
    """短段应向前合并，避免孤立片段。"""
    time_stamps = [
        {"text": "hello", "start": 0.0, "end": 0.5},
        {"text": "world.", "start": 0.5, "end": 1.0},
        {"text": "ok", "start": 1.1, "end": 1.2},
    ]
    segment_config = {
        "segment_max_duration_s": 30,
        "segment_max_words": 50,
        "segment_gap_threshold_s": 0.8,
        "segment_min_duration_s": 1.0,
        "segment_punctuations": [".", "?", "!"],
    }

    segments = te._build_segments(
        text="",
        time_stamps=time_stamps,
        audio_duration=2.0,
        enable_words=True,
        segment_config=segment_config,
    )

    assert len(segments) == 1
    assert len(segments[0]["words"]) == 3


def test_gap_split_segments():
    """词间隔超过阈值时应切分。"""
    time_stamps = [
        {"text": "a", "start": 0.0, "end": 0.2},
        {"text": "b", "start": 1.2, "end": 1.4},
    ]
    segment_config = {
        "segment_max_duration_s": 30,
        "segment_max_words": 50,
        "segment_gap_threshold_s": 0.8,
        "segment_min_duration_s": 0.0,
        "segment_punctuations": [".", "?", "!"],
    }

    segments = te._build_segments(
        text="",
        time_stamps=time_stamps,
        audio_duration=2.0,
        enable_words=True,
        segment_config=segment_config,
    )

    assert len(segments) == 2


def test_split_by_char_with_punctuation():
    """标点优先拆分后再按长度拼接。"""
    words = ["Hello", "world", "This", "is", "a", "very", "long", "sentence", "that", "should", "split"]
    time_stamps = []
    for idx, word in enumerate(words):
        start = idx * 0.2
        time_stamps.append({
            "text": word,
            "start": start,
            "end": start + 0.2,
        })
    text = "Hello, world. This is a very long sentence that should split."

    segment_config = {
        "segment_max_duration_s": 30,
        "segment_max_words": 50,
        "segment_gap_threshold_s": 0.8,
        "segment_min_duration_s": 0.0,
        "segment_punctuations": [".", "?", "!"],
        "segment_max_chars": 20,
        "segment_min_chars": 0,
        "segment_max_cps": 100.0,
        "segment_char_overflow": 0,
        "segment_break_punctuations": [".", "?", "!", ",", "，"],
    }

    segments = te._build_segments(
        text=text,
        time_stamps=time_stamps,
        audio_duration=5.0,
        enable_words=True,
        segment_config=segment_config,
    )

    assert len(segments) >= 2
    assert segments[0]["text"] == "Hello, world."
    assert segments[1]["text"].startswith("This is")
