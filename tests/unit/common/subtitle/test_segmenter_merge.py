"""
测试 merge_incomplete_segments() 函数

该函数用于后处理合并：
1. 合并不完整片段（无标点+小写开头）
2. 合并极短片段
"""

import pytest

from services.common.subtitle.segmenter import merge_incomplete_segments


class TestMergeIncompleteSegments:
    """测试后处理合并函数"""

    def test_empty_input(self):
        """测试空输入"""
        result = merge_incomplete_segments([])
        assert result == []

    def test_single_segment(self):
        """测试单个片段"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ]
        ]
        result = merge_incomplete_segments(segments)
        assert len(result) == 1
        assert result[0] == segments[0]

    def test_incomplete_segment_lowercase_start(self):
        """测试小写开头且无标点的片段应被合并到前一个"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": " ", "start": 0.5, "end": 0.5},
                {"word": "world", "start": 0.5, "end": 1.0},
                {"word": ".", "start": 1.0, "end": 1.2},
            ],
            [
                {"word": " ", "start": 1.2, "end": 1.2},
                {"word": "this", "start": 1.5, "end": 1.8},
                {"word": " ", "start": 1.8, "end": 1.8},
                {"word": "is", "start": 1.8, "end": 2.0},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 第二个片段小写开头且无结尾标点，应该合并到第一个
        assert len(result) == 1
        assert len(result[0]) == 8  # 两个片段合并

    def test_incomplete_segment_with_punctuation_not_merged(self):
        """测试有标点的片段即使小写开头也不应合并"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "this", "start": 1.0, "end": 1.3},
                {"word": ".", "start": 1.3, "end": 1.5},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 第二个片段有标点，不应该合并
        assert len(result) == 2

    def test_incomplete_segment_uppercase_start_not_merged(self):
        """测试大写开头的片段即使无标点也不应合并"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "This", "start": 1.0, "end": 1.3},
                {"word": " ", "start": 1.3, "end": 1.3},
                {"word": "is", "start": 1.3, "end": 1.5},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 第二个片段大写开头，不应该合并
        assert len(result) == 2

    def test_tiny_segment_merge(self):
        """测试极短片段应被合并"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": " ", "start": 0.5, "end": 0.5},
                {"word": "world", "start": 0.5, "end": 1.0},
                {"word": ".", "start": 1.0, "end": 1.2},
            ],
            [
                {"word": "Hi", "start": 1.5, "end": 1.7},
            ],
        ]
        result = merge_incomplete_segments(segments, min_length=3)
        # 第二个片段极短（长度2），应该合并到第一个
        assert len(result) == 1

    def test_multiple_incomplete_segments(self):
        """测试多个不完整片段连续合并"""
        segments = [
            [
                {"word": "First", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "second", "start": 1.0, "end": 1.3},
            ],
            [
                {"word": "third", "start": 1.5, "end": 1.8},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 第二、三个都是小写开头且无标点，都应该合并到第一个
        assert len(result) == 1

    def test_incomplete_at_beginning(self):
        """测试开头的极短片段应合并到后一个"""
        segments = [
            [
                {"word": "Hi", "start": 0.0, "end": 0.2},
            ],
            [
                {"word": "Hello", "start": 0.5, "end": 1.0},
                {"word": " ", "start": 1.0, "end": 1.0},
                {"word": "world", "start": 1.0, "end": 1.5},
                {"word": ".", "start": 1.5, "end": 1.7},
            ],
        ]
        result = merge_incomplete_segments(segments, min_length=3)
        # 第一个片段极短，应该合并到第二个
        assert len(result) == 1

    def test_complete_segments_no_merge(self):
        """测试完整片段不应被合并"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "World", "start": 1.0, "end": 1.5},
                {"word": "!", "start": 1.5, "end": 1.7},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 两个片段都有完整标点，不应该合并
        assert len(result) == 2

    def test_chinese_incomplete_segment(self):
        """测试中文字符的不完整片段合并"""
        segments = [
            [
                {"word": "你好", "start": 0.0, "end": 0.5},
                {"word": "。", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "世界", "start": 1.0, "end": 1.5},
            ],
        ]
        result = merge_incomplete_segments(segments, min_length=3)
        # 第二个片段无标点且长度较短，应该合并
        assert len(result) == 1

    def test_mixed_complete_and_incomplete(self):
        """测试混合完整和不完整片段"""
        segments = [
            [
                {"word": "First", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "Second", "start": 1.0, "end": 1.3},
                {"word": ".", "start": 1.3, "end": 1.5},
            ],
            [
                {"word": "third", "start": 1.8, "end": 2.0},
            ],
        ]
        result = merge_incomplete_segments(segments)
        # 前两个完整，第三个不完整应该合并到第二个
        assert len(result) == 2
        # 验证第三个合并到了第二个
        assert len(result[1]) == 3  # Second. (2) + third (1) = 3

    def test_only_whitespace_words(self):
        """测试只有空白字符的片段应被视为不完整"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": " ", "start": 0.7, "end": 0.7},
                {"word": "  ", "start": 0.7, "end": 0.7},
            ],
        ]
        result = merge_incomplete_segments(segments, min_length=3)
        # 第二个片段只有空白，长度视为0，应该合并
        assert len(result) == 1

    def test_custom_min_length(self):
        """测试自定义最小长度"""
        segments = [
            [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": ".", "start": 0.5, "end": 0.7},
            ],
            [
                {"word": "Hi", "start": 1.0, "end": 1.2},
            ],
        ]
        # min_length=2 时，"Hi" 长度2不小于2，不应该合并
        result = merge_incomplete_segments(segments, min_length=2)
        assert len(result) == 2

        # min_length=3 时，"Hi" 长度2小于3，应该合并
        result = merge_incomplete_segments(segments, min_length=3)
        assert len(result) == 1
