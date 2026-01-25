from services.common.subtitle.word_level_aligner import align_words_to_text


def test_word_aligner_preserves_timestamps():
    words = [
        {"word": "helllo", "start": 1.0, "end": 1.2},
        {"word": "world", "start": 1.3, "end": 1.6},
    ]
    result = align_words_to_text(words, "hello world")

    assert result[0]["start"] == 1.0
    assert result[0]["end"] == 1.2
    assert result[0]["word"] == "hello"
