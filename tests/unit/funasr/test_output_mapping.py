from services.workers.funasr_service.executors.transcribe_executor import (
    build_segments,
    build_segments_from_payload,
    map_words,
    normalize_speaker,
)


def test_map_words_with_timestamps():
    words, count = map_words(
        [
            {"text": "hello", "start": 0.1, "end": 0.5},
            {"text": "world", "start": 0.6, "end": 1.0},
        ],
        enable=True,
    )
    assert count == 2
    assert words[0]["word"] == "hello"
    assert words[1]["start"] == 0.6


def test_build_segments_fallback_when_no_words():
    segments = build_segments(text="hello", words=[], audio_duration=2.0, speaker=None)
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 2.0


def test_normalize_speaker_optional():
    assert normalize_speaker(None) is None
    assert normalize_speaker("spk1") == "spk1"


def test_build_segments_from_payload_uses_segments():
    payload = {"segments": [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "spk1"}]}
    segments = build_segments_from_payload(
        payload, audio_duration=1.0, enable_word_timestamps=False
    )
    assert segments[0]["speaker"] == "spk1"


def test_build_segments_from_payload_uses_timestamps():
    payload = {"text": "hi", "time_stamps": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    segments = build_segments_from_payload(
        payload, audio_duration=1.0, enable_word_timestamps=True
    )
    assert "words" in segments[0]
