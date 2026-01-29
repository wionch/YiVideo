import pytest
import sys

# 直接导入模块文件，避免包导入的副作用
sys.path.insert(0, "/app/services/common/subtitle")
from segmenter import split_by_weak_punctuation, WEAK_PUNCTUATION


def test_no_split_when_under_max_cpl():
    """当文本长度小于等于 max_cpl 时不分割"""
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world,", "start": 0.5, "end": 1.0},
        {"word": " test", "start": 1.0, "end": 1.5}
    ]
    result = split_by_weak_punctuation(words, max_cpl=50)
    assert len(result) == 1
    assert result[0] == words


def test_split_at_comma():
    """在逗号处分割"""
    words = [
        {"word": " First", "start": 0.0, "end": 0.5},
        {"word": " part,", "start": 0.5, "end": 1.0},
        {"word": " second", "start": 1.0, "end": 1.5},
        {"word": " part", "start": 1.5, "end": 2.0}
    ]
    result = split_by_weak_punctuation(words, max_cpl=10)
    assert len(result) == 2
    assert len(result[0]) == 2  # First part,
    assert len(result[1]) == 2  # second part


def test_split_at_middle_when_multiple_commas():
    """当有多个弱标点时，选择最接近中间位置的分割点，并递归处理左右部分"""
    words = [
        {"word": " First part,", "start": 0.0, "end": 0.5},
        {"word": " middle part,", "start": 0.5, "end": 1.0},
        {"word": " last part", "start": 1.0, "end": 1.5}
    ]
    # 总长度约 35 字符，max_cpl=20 会触发分割
    result = split_by_weak_punctuation(words, max_cpl=20)
    # 中间位置是 1，最接近的弱标点在索引 1 (middle part,)
    # 分割后左部分长度约 25 (>20)，会继续在 " First part," 处分割
    # 最终结果是 3 个片段
    assert len(result) == 3
    assert result[0][0]["word"] == " First part,"
    assert result[1][0]["word"] == " middle part,"
    assert result[2][0]["word"] == " last part"


def test_no_weak_punctuation_returns_original():
    """当没有弱标点时返回原始列表"""
    words = [
        {"word": " No", "start": 0.0, "end": 0.3},
        {"word": " weak", "start": 0.3, "end": 0.6},
        {"word": " punct", "start": 0.6, "end": 0.9}
    ]
    result = split_by_weak_punctuation(words, max_cpl=5)
    assert len(result) == 1
    assert result[0] == words


def test_single_word():
    """单个单词时不分割"""
    words = [
        {"word": " Single", "start": 0.0, "end": 0.5}
    ]
    result = split_by_weak_punctuation(words, max_cpl=5)
    assert len(result) == 1
    assert result[0] == words


def test_recursive_split():
    """递归分割直到每个片段都小于 max_cpl"""
    words = [
        {"word": " A,", "start": 0.0, "end": 0.3},
        {"word": " B,", "start": 0.3, "end": 0.6},
        {"word": " C,", "start": 0.6, "end": 0.9},
        {"word": " D,", "start": 0.9, "end": 1.2},
        {"word": " E", "start": 1.2, "end": 1.5}
    ]
    result = split_by_weak_punctuation(words, max_cpl=3)
    # 应该递归分割成多个片段
    assert len(result) >= 2
