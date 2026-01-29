import pytest

from services.common.subtitle.segmenter import split_by_strong_punctuation, STRONG_PUNCTUATION, WEAK_PUNCTUATION


def test_split_by_period():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world.", "start": 0.5, "end": 1.0},
        {"word": " Next", "start": 1.5, "end": 2.0},
        {"word": " sentence.", "start": 2.0, "end": 2.5}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 2


def test_not_split_abbreviation():
    words = [
        {"word": " Dr.", "start": 0.0, "end": 0.3},
        {"word": " Smith", "start": 0.3, "end": 0.8},
        {"word": " lives", "start": 0.8, "end": 1.2},
        {"word": " in", "start": 1.2, "end": 1.5},
        {"word": " U.S.", "start": 1.5, "end": 2.0}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 1


def test_split_by_question_mark():
    words = [
        {"word": " What", "start": 0.0, "end": 0.3},
        {"word": " time?", "start": 0.3, "end": 0.8},
        {"word": " Now.", "start": 1.0, "end": 1.5}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 2


def test_empty_input():
    result = split_by_strong_punctuation([])
    assert result == []


def test_no_punctuation():
    words = [
        {"word": " No", "start": 0.0, "end": 0.3},
        {"word": " punctuation", "start": 0.3, "end": 0.8}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 1
