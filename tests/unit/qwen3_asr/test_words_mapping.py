from services.workers.qwen3_asr_service.executors.transcribe_executor import map_words


def test_map_words_disabled():
    assert map_words(None, enable=False) == ([], 0)


def test_map_words_enabled():
    time_stamps = [
        {"text": "你好", "start": 0.0, "end": 0.5},
        {"text": "世界", "start": 0.5, "end": 1.0},
    ]
    words, total = map_words(time_stamps, enable=True)
    assert total == 2
    assert words[0]["word"] == "你好"
    assert words[0]["start"] == 0.0
    assert words[0]["end"] == 0.5
    assert words[0]["probability"] is None
