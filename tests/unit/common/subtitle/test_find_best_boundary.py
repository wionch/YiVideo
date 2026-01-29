"""
测试 find_best_boundary 函数

该函数从候选边界中选择最佳切分点，考虑：
1. 避免产生超短片段
2. 中间位置偏好
3. 长度均衡
"""

import pytest

from services.common.subtitle.segmenter import find_best_boundary, collect_semantic_boundaries


class TestFindBestBoundary:
    """测试 find_best_boundary 函数"""

    def test_no_boundaries_returns_none(self):
        """当没有候选边界时返回 None"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ]
        boundaries = []
        result = find_best_boundary(words, boundaries, min_length=3)
        assert result is None

    def test_single_boundary_returns_it(self):
        """只有一个候选边界时直接返回"""
        words = [
            {"word": "First part,", "start": 0.0, "end": 0.5},
            {"word": "second", "start": 0.5, "end": 1.0},
            {"word": "part", "start": 1.0, "end": 1.5},
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9}
        ]
        result = find_best_boundary(words, boundaries, min_length=3)
        assert result == 0

    def test_avoid_tiny_left_segment(self):
        """避免产生超短的左片段"""
        words = [
            {"word": "A,", "start": 0.0, "end": 0.2},  # 2 chars
            {"word": "long", "start": 0.2, "end": 0.5},
            {"word": "text", "start": 0.5, "end": 0.8},
            {"word": "here", "start": 0.8, "end": 1.0},
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9},
            {"index": 2, "type": "conjunction", "word": "and", "score": 0.7},
        ]
        # min_length=3, 在 index 0 分割会产生左片段 "A," (2 chars)，太短
        result = find_best_boundary(words, boundaries, min_length=3)
        assert result == 2  # 应该选择 index 2

    def test_avoid_tiny_right_segment(self):
        """避免产生超短的右片段"""
        words = [
            {"word": "Long", "start": 0.0, "end": 0.3},
            {"word": "text", "start": 0.3, "end": 0.6},
            {"word": "here,", "start": 0.6, "end": 0.9},
            {"word": "B", "start": 0.9, "end": 1.0},  # 1 char
        ]
        boundaries = [
            {"index": 0, "type": "conjunction", "word": "and", "score": 0.7},
            {"index": 2, "type": "weak_punct", "char": ",", "score": 0.9},
        ]
        # min_length=3, 在 index 2 分割会产生右片段 "B" (1 char)，太短
        result = find_best_boundary(words, boundaries, min_length=3)
        assert result == 0  # 应该选择 index 0

    def test_prefer_middle_position(self):
        """当有多个可选边界时，优先选择中间位置"""
        words = [
            {"word": "A,", "start": 0.0, "end": 0.2},
            {"word": "B,", "start": 0.2, "end": 0.4},
            {"word": "C,", "start": 0.4, "end": 0.6},
            {"word": "D,", "start": 0.6, "end": 0.8},
            {"word": "E", "start": 0.8, "end": 1.0},
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9},
            {"index": 3, "type": "weak_punct", "char": ",", "score": 0.9},
        ]
        # 中间位置是 2，index 0 距离 2，index 3 距离 1
        # 应该选择更接近中间的 index 3
        result = find_best_boundary(words, boundaries, min_length=1)
        assert result == 3

    def test_consider_score_and_position(self):
        """综合考虑分数和位置"""
        words = [
            {"word": "First,", "start": 0.0, "end": 0.2},
            {"word": "middle,", "start": 0.2, "end": 0.4},
            {"word": "last", "start": 0.4, "end": 0.6},
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9},  # 高分但偏左
            {"index": 1, "type": "conjunction", "word": "and", "score": 0.6},  # 低分但在中间
        ]
        # 中间位置是 1，index 1 正好在中间
        result = find_best_boundary(words, boundaries, min_length=3)
        # 应该根据综合评分选择
        assert result in [0, 1]  # 具体取决于算法实现

    def test_all_boundaries_cause_tiny_segments(self):
        """当所有边界都会产生超短片段时，选择相对最好的"""
        words = [
            {"word": "A,", "start": 0.0, "end": 0.2},  # 2 chars
            {"word": "B", "start": 0.2, "end": 0.4},   # 1 char
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9},
        ]
        # 无论怎么分割都会产生超短片段，应该返回 None 或选择该边界
        result = find_best_boundary(words, boundaries, min_length=3)
        # 如果无法避免超短片段，应该返回 None
        assert result is None

    def test_prefer_higher_score_when_equidistant(self):
        """当距离中间位置相同时，优先选择高分边界"""
        words = [
            {"word": "A,", "start": 0.0, "end": 0.2},
            {"word": "B,", "start": 0.2, "end": 0.4},
            {"word": "C,", "start": 0.4, "end": 0.6},
            {"word": "D,", "start": 0.6, "end": 0.8},
            {"word": "E", "start": 0.8, "end": 1.0},
        ]
        boundaries = [
            {"index": 1, "type": "conjunction", "word": "and", "score": 0.6},
            {"index": 3, "type": "weak_punct", "char": ",", "score": 0.9},
        ]
        # 中间位置是 2，index 1 距离 1，index 3 距离 1
        # 距离相同，应该选择分数更高的 index 3
        result = find_best_boundary(words, boundaries, min_length=1)
        assert result == 3

    def test_integration_with_collect_semantic_boundaries(self):
        """与 collect_semantic_boundaries 集成测试"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.3},
            {"word": "world,", "start": 0.3, "end": 0.6},
            {"word": "and", "start": 0.6, "end": 0.9},
            {"word": "welcome", "start": 0.9, "end": 1.2},
        ]
        boundaries = collect_semantic_boundaries(words, language="en")
        result = find_best_boundary(words, boundaries, min_length=3)
        # 应该返回一个有效的边界索引
        assert result is not None
        assert 0 <= result < len(words) - 1

    def test_empty_words_returns_none(self):
        """空词列表返回 None"""
        words = []
        boundaries = [{"index": 0, "type": "weak_punct", "score": 0.9}]
        result = find_best_boundary(words, boundaries, min_length=3)
        assert result is None

    def test_boundary_index_out_of_range(self):
        """边界索引超出范围时忽略该边界"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ]
        boundaries = [
            {"index": 5, "type": "weak_punct", "char": ",", "score": 0.9},  # 超出范围
            {"index": 0, "type": "conjunction", "word": "and", "score": 0.7},
        ]
        result = find_best_boundary(words, boundaries, min_length=1)
        assert result == 0  # 应该选择有效的 index 0

    def test_length_balance_preference(self):
        """测试长度均衡偏好"""
        words = [
            {"word": "This is a very long first part,", "start": 0.0, "end": 0.5},
            {"word": "short", "start": 0.5, "end": 0.7},
        ]
        boundaries = [
            {"index": 0, "type": "weak_punct", "char": ",", "score": 0.9},
        ]
        # 分割后左片段很长，右片段很短
        result = find_best_boundary(words, boundaries, min_length=3)
        # 如果右片段太短，应该返回 None 或警告
        # 这里右片段 "short" 有 5 chars，满足 min_length=3
        assert result == 0
