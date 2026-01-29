import pytest
import sys

# 直接导入模块文件，避免包导入的副作用
sys.path.insert(0, "/app/services/common/subtitle")
from segmenter import split_by_pause, PAUSE_THRESHOLD


def test_no_split_when_under_max_cpl():
    """当文本长度小于等于 max_cpl 时不分割"""
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 1.0, "end": 1.5},  # 0.5s gap
        {"word": " test", "start": 2.0, "end": 2.5}   # 0.5s gap
    ]
    result = split_by_pause(words, max_cpl=50)
    assert len(result) == 1
    assert result[0] == words


def test_split_at_pause():
    """在停顿超过阈值处分割"""
    words = [
        {"word": " First", "start": 0.0, "end": 0.5},
        {"word": " part", "start": 0.5, "end": 1.0},
        {"word": " second", "start": 2.0, "end": 2.5},  # 1.0s gap > 0.3s
        {"word": " part", "start": 2.5, "end": 3.0}
    ]
    result = split_by_pause(words, max_cpl=10)
    assert len(result) == 2
    assert len(result[0]) == 2  # First part
    assert len(result[1]) == 2  # second part


def test_split_at_middle_when_multiple_pauses():
    """当有多个停顿时，选择最接近中间位置的停顿点"""
    words = [
        {"word": " First part", "start": 0.0, "end": 0.5},
        {"word": " middle part", "start": 1.0, "end": 1.5},  # 0.5s gap
        {"word": " last part", "start": 3.0, "end": 3.5}    # 1.5s gap
    ]
    # 总长度约 33 字符，max_cpl=25 会触发分割
    # 在索引 1 处分割后：左边 23 字符 <= 25，右边 10 字符 <= 25
    result = split_by_pause(words, max_cpl=25)
    # 中间位置是 1，索引 1 的停顿距离中间 0，索引 2 的停顿距离中间 1
    # 所以会选择索引 1 处的停顿进行分割
    assert len(result) == 2
    assert result[0][0]["word"] == " First part"
    assert result[0][1]["word"] == " middle part"
    assert result[1][0]["word"] == " last part"


def test_no_pause_returns_original():
    """当没有停顿时返回原始列表"""
    words = [
        {"word": " No", "start": 0.0, "end": 0.3},
        {"word": " pause", "start": 0.3, "end": 0.6},   # 0 gap
        {"word": " here", "start": 0.6, "end": 0.9}    # 0 gap
    ]
    result = split_by_pause(words, max_cpl=5)
    assert len(result) == 1
    assert result[0] == words


def test_single_word():
    """单个单词时不分割"""
    words = [
        {"word": " Single", "start": 0.0, "end": 0.5}
    ]
    result = split_by_pause(words, max_cpl=5)
    assert len(result) == 1
    assert result[0] == words


def test_recursive_split():
    """递归分割直到每个片段都小于 max_cpl"""
    words = [
        {"word": " A", "start": 0.0, "end": 0.3},
        {"word": " B", "start": 1.0, "end": 1.3},   # 0.7s gap
        {"word": " C", "start": 2.0, "end": 2.3},   # 0.7s gap
        {"word": " D", "start": 3.0, "end": 3.3},   # 0.7s gap
        {"word": " E", "start": 4.0, "end": 4.3}    # 0.7s gap
    ]
    result = split_by_pause(words, max_cpl=3)
    # 应该递归分割成多个片段
    assert len(result) >= 2


def test_pause_threshold_boundary():
    """测试停顿阈值边界情况"""
    # 刚好等于阈值，不分割
    words_at_threshold = [
        {"word": " A", "start": 0.0, "end": 0.3},
        {"word": " B", "start": 0.6, "end": 0.9},  # 0.3s gap = threshold
    ]
    result = split_by_pause(words_at_threshold, max_cpl=2)
    # 0.3s 刚好等于阈值，不大于，所以不分割
    assert len(result) == 1

    # 超过阈值，分割
    words_over_threshold = [
        {"word": " A", "start": 0.0, "end": 0.3},
        {"word": " B", "start": 0.7, "end": 1.0},  # 0.4s gap > threshold
    ]
    result = split_by_pause(words_over_threshold, max_cpl=2)
    assert len(result) == 2


def test_score_pause_distance_penalty():
    """测试停顿评分中的距离惩罚"""
    # 两个停顿点，一个停顿时间长但距离中间远，一个停顿时间短但距离中间近
    words = [
        {"word": " A", "start": 0.0, "end": 0.3},
        {"word": " B", "start": 0.5, "end": 0.8},   # 0.2s gap, idx=0
        {"word": " C", "start": 1.0, "end": 1.3},
        {"word": " D", "start": 1.5, "end": 1.8},   # 0.2s gap, idx=2
        {"word": " E", "start": 3.0, "end": 3.3},   # 1.2s gap, idx=3 (middle)
        {"word": " F", "start": 3.5, "end": 3.8}
    ]
    # 中间位置是 2.5，最接近的是索引 2 (距离 0.5) 或索引 3 (距离 0.5)
    # 但索引 3 的停顿时间更长
    result = split_by_pause(words, max_cpl=5)
    # 应该选择在索引 3 处分割（停顿时间长且距离中间近）
    assert len(result) == 2
