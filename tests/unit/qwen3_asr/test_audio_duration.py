# -*- coding: utf-8 -*-

"""Qwen3-ASR 时长兜底测试。"""

from services.workers.qwen3_asr_service.executors import transcribe_executor as te


def test_audio_duration_from_timestamps():
    """时长为空时应回退到最后一个词的 end。"""
    time_stamps = [
        {"text": "a", "start": 0.0, "end": 1.2},
        {"text": "b", "start": 1.2, "end": 2.4},
    ]
    assert te._resolve_audio_duration(0, time_stamps) == 2.4


def test_audio_duration_empty():
    """无时间戳时返回 0。"""
    assert te._resolve_audio_duration(0, None) == 0.0
