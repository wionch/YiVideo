from services.common.subtitle.word_level_aligner import (
    align_words_to_text,
    rebuild_segments_by_words,
)


def test_word_aligner_preserves_timestamps():
    words = [
        {"word": "helllo", "start": 1.0, "end": 1.2},
        {"word": "world", "start": 1.3, "end": 1.6},
    ]
    result = align_words_to_text(words, "hello world")

    assert result[0]["start"] == 1.0
    assert result[0]["end"] == 1.2
    assert result[0]["word"] == "hello"


def test_word_aligner_handles_insert():
    words = [
        {"word": " hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0},
    ]
    result = align_words_to_text(words, "hello brave world")

    assert result[0]["word"] == " hello brave"
    assert result[1]["word"] == " world"
    assert result[1]["start"] == 0.5


def test_word_aligner_handles_delete():
    words = [
        {"word": " hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0},
    ]
    result = align_words_to_text(words, "hello")

    assert result[1]["word"] == ""
    assert result[1]["start"] == 0.5


def test_aligner_inserts_space_after_period():
    words = [
        {"word": " U.", "start": 0.0, "end": 0.2},
        {"word": " S.", "start": 0.2, "end": 0.4},
        {"word": " It's", "start": 0.4, "end": 0.6},
    ]
    result = align_words_to_text(words, "U.S. It's")
    assert "".join(w["word"] for w in result).strip() == "U.S. It's"


def test_rebuild_segments_prefers_punctuation_over_cpl():
    """
    测试当语义边界（逗号）会导致片段超过 CPL 限制时，
    应该回退到字数分割而不是强制在逗号处分割。

    这个测试验证了 CPL=42 是强制约束，优先级高于语义边界。
    """
    segments = [
        {
            "words": [
                {"word": " abcdefghij", "start": 0.0, "end": 1.0},
                {"word": " abcdefghij", "start": 1.0, "end": 2.0},
                {"word": " abcdefghij", "start": 2.0, "end": 3.0},
                {"word": " abcdefghij", "start": 3.0, "end": 4.0},
                {"word": " klmno,", "start": 4.0, "end": 5.0},
                {"word": " tail", "start": 5.0, "end": 6.0},
            ]
        }
    ]
    rebuilt = rebuild_segments_by_words(segments)

    # 总长度 56 字符，如果在逗号处分割会产生 51 字符的左片段（超过 CPL=42）
    # 因此应该使用字数分割，产生至少 2 个片段
    assert len(rebuilt) >= 2

    # 验证所有片段都不超过 CPL 限制
    for segment in rebuilt:
        text = "".join(w.get("word", "") for w in segment.get("words", []))
        assert len(text) <= 42, f"Segment exceeds CPL: {len(text)} chars"


def test_rebuild_segments_avoids_short_tail_when_splitting():
    segments = [
        {
            "words": [
                {"word": " abcdefghij,", "start": 0.0, "end": 1.0},
                {"word": " abcdefghij", "start": 1.0, "end": 2.0},
                {"word": " abcdefghij,", "start": 2.0, "end": 3.0},
                {"word": " abcdefghij", "start": 3.0, "end": 4.0},
                {"word": " abcdefghij,", "start": 4.0, "end": 5.0},
                {"word": " tail", "start": 5.0, "end": 6.0},
            ]
        }
    ]
    rebuilt = rebuild_segments_by_words(segments)

    assert len(rebuilt) == 2
    assert len(rebuilt[0]["words"]) == 3
    assert rebuilt[0]["end"] == 3.0


def test_rebuild_segments_defers_until_punctuation():
    segments = [
        {
            "words": [
                {"word": " abcdefghij", "start": 0.0, "end": 1.0},
                {"word": " abcdefghij", "start": 1.0, "end": 2.0},
                {"word": " abcdefghij", "start": 2.0, "end": 3.0},
                {"word": " abcdefghij", "start": 3.0, "end": 4.0},
                {"word": " abcdefghij", "start": 4.0, "end": 5.0},
                {"word": " abcdefghij.", "start": 5.0, "end": 6.0},
                {"word": " tail", "start": 6.0, "end": 7.0},
                {"word": " tail", "start": 7.0, "end": 8.0},
            ]
        }
    ]
    # 使用较大的 max_cpl 避免字数限制导致的额外分割
    rebuilt = rebuild_segments_by_words(segments, max_cpl=100)

    assert len(rebuilt) == 2
    assert rebuilt[0]["end"] == 6.0
