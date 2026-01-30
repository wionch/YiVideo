import pytest
from services.workers.qwen3_asr_service.executors.transcribe_executor import map_language


def test_language_mapping_auto_none():
    assert map_language(None) is None
    assert map_language("") is None
    assert map_language("auto") is None


def test_language_mapping_basic():
    assert map_language("zh") == "Chinese"
    assert map_language("zh-CN") == "Chinese"
    assert map_language("cn") == "Chinese"
    assert map_language("en") == "English"
    assert map_language("en-US") == "English"


def test_language_mapping_passthrough():
    assert map_language("Japanese") == "Japanese"
