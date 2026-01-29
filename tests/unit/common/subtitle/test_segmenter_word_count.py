import pytest

from services.common.subtitle.segmenter import split_by_word_count


def test_no_split_when_under_max_cpl():
    """当文本长度小于等于 max_cpl 时不分割"""
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0},
        {"word": " test", "start": 1.0, "end": 1.5}
    ]
    result = split_by_word_count(words, max_cpl=50)
    assert len(result) == 1
    assert result[0] == words


def test_no_split_single_word():
    """单个单词时不分割"""
    words = [
        {"word": " Single", "start": 0.0, "end": 0.5}
    ]
    result = split_by_word_count(words, max_cpl=5)
    assert len(result) == 1
    assert result[0] == words


def test_split_by_word_count_basic():
    """基本字数分割测试"""
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0},
        {"word": " this", "start": 1.0, "end": 1.5},
        {"word": " is", "start": 1.5, "end": 2.0},
        {"word": " a", "start": 2.0, "end": 2.5},
        {"word": " test", "start": 2.5, "end": 3.0}
    ]
    # 总长度约 32 字符，max_cpl=10，应该分成约 4 段
    max_cpl = 10
    result = split_by_word_count(words, max_cpl=max_cpl)
    assert len(result) >= 2
    # 检查每个片段长度不超过 max_cpl
    for segment in result:
        text = "".join(w.get("word", "") for w in segment)
        assert len(text) <= max_cpl or len(segment) == 1


def test_split_maintains_word_integrity():
    """分割保持单词完整性，不在单词中间切断"""
    words = [
        {"word": " HelloWorld", "start": 0.0, "end": 0.5},
        {"word": " TestCase", "start": 0.5, "end": 1.0},
        {"word": " Example", "start": 1.0, "end": 1.5}
    ]
    result = split_by_word_count(words, max_cpl=10)
    # 检查每个单词都是完整的
    for segment in result:
        for word in segment:
            assert word["word"] in [" HelloWorld", " TestCase", " Example"]


def test_recursive_split():
    """递归分割直到每个片段都小于 max_cpl"""
    words = [
        {"word": " A", "start": 0.0, "end": 0.3},
        {"word": " B", "start": 0.3, "end": 0.6},
        {"word": " C", "start": 0.6, "end": 0.9},
        {"word": " D", "start": 0.9, "end": 1.2},
        {"word": " E", "start": 1.2, "end": 1.5},
        {"word": " F", "start": 1.5, "end": 1.8},
        {"word": " G", "start": 1.8, "end": 2.1},
        {"word": " H", "start": 2.1, "end": 2.4}
    ]
    result = split_by_word_count(words, max_cpl=5)
    # 应该分割成多个片段
    assert len(result) >= 2
    # 每个片段应该相对平均
    segment_lengths = [len("".join(w.get("word", "") for w in segment)) for segment in result]
    # 最长和最短的差距不应该太大（允许一定误差）
    assert max(segment_lengths) - min(segment_lengths) <= 10


def test_empty_words():
    """空列表处理"""
    result = split_by_word_count([], max_cpl=10)
    # 空文本长度 0 <= max_cpl，应该返回包含空列表的列表
    assert result == [[]]


def test_even_distribution():
    """测试字数平均分配"""
    words = [
        {"word": " One", "start": 0.0, "end": 0.3},
        {"word": " Two", "start": 0.3, "end": 0.6},
        {"word": " Three", "start": 0.6, "end": 0.9},
        {"word": " Four", "start": 0.9, "end": 1.2},
        {"word": " Five", "start": 1.2, "end": 1.5}
    ]
    # 总长度约 23 字符，max_cpl=10，应该分成 2-3 段
    result = split_by_word_count(words, max_cpl=10)
    assert len(result) >= 2
    # 检查所有单词都被包含
    all_words = []
    for segment in result:
        all_words.extend(segment)
    assert len(all_words) == len(words)
