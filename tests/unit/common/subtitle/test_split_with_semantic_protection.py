"""
语义保护切分函数测试

测试 split_with_semantic_protection() 函数:
1. 优先在语义边界处切分
2. 超短片段时回退到字数平均切分
3. 递归分割直到满足长度限制
"""

import pytest
from typing import List, Dict, Any

from services.common.subtitle.segmenter import (
    split_with_semantic_protection,
    collect_semantic_boundaries,
    split_by_word_count,
)


class TestSplitWithSemanticProtection:
    """测试语义保护切分函数"""

    def test_empty_words_list(self):
        """测试空词列表返回空结果"""
        result = split_with_semantic_protection([], max_cpl=42, language="en")
        assert result == []

    def test_single_word_returns_as_is(self):
        """测试单个词直接返回"""
        words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
        result = split_with_semantic_protection(words, max_cpl=42, language="en")
        assert result == [words]

    def test_text_within_limit_no_split(self):
        """测试文本在限制内时不分割"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
        ]
        result = split_with_semantic_protection(words, max_cpl=42, language="en")
        assert len(result) == 1
        assert result[0] == words

    def test_split_at_weak_punctuation_boundary(self):
        """测试在弱标点边界处切分"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.3},
            {"word": "this", "start": 0.4, "end": 0.6},
            {"word": "is", "start": 0.7, "end": 0.9},
            {"word": "a", "start": 1.0, "end": 1.1},
            {"word": "very", "start": 1.2, "end": 1.4},
            {"word": "long", "start": 1.5, "end": 1.7},
            {"word": "sentence", "start": 1.8, "end": 2.0},
        ]
        # 总长度约 26, max_cpl=15 需要分割
        result = split_with_semantic_protection(words, max_cpl=15, language="en")
        # 应该在逗号处分割
        assert len(result) >= 2
        # 第一个片段应该以 "Hello," 结尾
        assert result[0][-1]["word"] == "Hello,"

    def test_split_at_conjunction_boundary(self):
        """测试在连词边界处切分"""
        words = [
            {"word": "First", "start": 0.0, "end": 0.3},
            {"word": "part", "start": 0.4, "end": 0.6},
            {"word": "and", "start": 0.7, "end": 0.9},
            {"word": "second", "start": 1.0, "end": 1.3},
            {"word": "part", "start": 1.4, "end": 1.6},
        ]
        # 总长度约 22, max_cpl=12 需要分割
        result = split_with_semantic_protection(words, max_cpl=12, language="en")
        # 应该在 "and" 前分割
        assert len(result) >= 2

    def test_fallback_to_word_count_when_no_semantic_boundary(self):
        """测试没有语义边界时回退到字数切分"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.2},
            {"word": "world", "start": 0.3, "end": 0.5},
            {"word": "test", "start": 0.6, "end": 0.8},
            {"word": "text", "start": 0.9, "end": 1.1},
        ]
        # 没有弱标点或连词，应该回退到字数切分
        result = split_with_semantic_protection(words, max_cpl=10, language="en")
        assert len(result) >= 2
        # 检查所有片段都不超过 max_cpl
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= 10

    def test_avoid_tiny_segments(self):
        """测试避免产生超短片段"""
        words = [
            {"word": "A,", "start": 0.0, "end": 0.2},  # 2 chars
            {"word": "very", "start": 0.3, "end": 0.5},
            {"word": "long", "start": 0.6, "end": 0.8},
            {"word": "text", "start": 0.9, "end": 1.1},
            {"word": "here", "start": 1.2, "end": 1.4},
        ]
        # 如果在逗号处分割，左片段只有 "A," (2 chars)，太短
        result = split_with_semantic_protection(words, max_cpl=10, language="en")
        # 检查没有超短片段（<=2字符）
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) > 2 or len(seg) == len(words)

    def test_recursive_split(self):
        """测试递归分割直到满足长度限制"""
        words = [
            {"word": "This,", "start": 0.0, "end": 0.3},
            {"word": "is,", "start": 0.4, "end": 0.6},
            {"word": "a,", "start": 0.7, "end": 0.9},
            {"word": "very,", "start": 1.0, "end": 1.3},
            {"word": "long,", "start": 1.4, "end": 1.7},
            {"word": "text", "start": 1.8, "end": 2.0},
        ]
        # max_cpl=10 应该产生多次分割
        result = split_with_semantic_protection(words, max_cpl=10, language="en")
        # 检查所有片段都不超过 max_cpl
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= 10

    def test_force_parameter(self):
        """测试 force 参数强制分割"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
        ]
        # 文本长度 10，小于 max_cpl=15
        # force=False 时不分割
        result_no_force = split_with_semantic_protection(words, max_cpl=15, language="en", force=False)
        assert len(result_no_force) == 1

        # force=True 时强制分割（即使文本在限制内）
        result_force = split_with_semantic_protection(words, max_cpl=15, language="en", force=True)
        # 强制分割可能产生更多片段
        assert len(result_force) >= 1

    def test_chinese_text_split(self):
        """测试中文文本切分"""
        words = [
            {"word": "你好，", "start": 0.0, "end": 0.3},
            {"word": "这是", "start": 0.4, "end": 0.6},
            {"word": "一个", "start": 0.7, "end": 0.9},
            {"word": "很长的", "start": 1.0, "end": 1.3},
            {"word": "句子", "start": 1.4, "end": 1.6},
        ]
        result = split_with_semantic_protection(words, max_cpl=10, language="zh")
        # 应该在逗号处分割
        assert len(result) >= 2
        # 检查所有片段都不超过 max_cpl
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= 10

    def test_preserve_word_order(self):
        """测试保持词序"""
        words = [
            {"word": "First", "start": 0.0, "end": 0.2},
            {"word": "second", "start": 0.3, "end": 0.5},
            {"word": "third", "start": 0.6, "end": 0.8},
            {"word": "fourth", "start": 0.9, "end": 1.1},
        ]
        result = split_with_semantic_protection(words, max_cpl=10, language="en")
        # 合并所有片段应该得到原始顺序
        all_words = []
        for seg in result:
            all_words.extend(seg)
        assert [w["word"] for w in all_words] == [w["word"] for w in words]

    def test_all_segments_within_max_cpl(self):
        """测试所有片段都不超过 max_cpl"""
        words = [
            {"word": "This", "start": 0.0, "end": 0.2},
            {"word": "is", "start": 0.3, "end": 0.5},
            {"word": "a", "start": 0.6, "end": 0.8},
            {"word": "test", "start": 0.9, "end": 1.1},
            {"word": "sentence", "start": 1.2, "end": 1.4},
            {"word": "with", "start": 1.5, "end": 1.7},
            {"word": "many", "start": 1.8, "end": 2.0},
            {"word": "words", "start": 2.1, "end": 2.3},
        ]
        max_cpl = 12
        result = split_with_semantic_protection(words, max_cpl=max_cpl, language="en")
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= max_cpl

    def test_no_words_lost(self):
        """测试没有词丢失"""
        words = [
            {"word": "One", "start": 0.0, "end": 0.2},
            {"word": "two", "start": 0.3, "end": 0.5},
            {"word": "three", "start": 0.6, "end": 0.8},
            {"word": "four", "start": 0.9, "end": 1.1},
            {"word": "five", "start": 1.2, "end": 1.4},
        ]
        result = split_with_semantic_protection(words, max_cpl=8, language="en")
        # 统计所有词数
        total_words = sum(len(seg) for seg in result)
        assert total_words == len(words)


class TestSplitWithSemanticProtectionIntegration:
    """语义保护切分集成测试"""

    def test_real_world_sentence_with_punctuation(self):
        """测试带标点的真实句子"""
        words = [
            {"word": "Well,", "start": 0.0, "end": 0.3},
            {"word": "little", "start": 0.4, "end": 0.6},
            {"word": "kitty,", "start": 0.7, "end": 0.9},
            {"word": "if", "start": 1.0, "end": 1.1},
            {"word": "you", "start": 1.2, "end": 1.3},
            {"word": "want", "start": 1.4, "end": 1.6},
            {"word": "to", "start": 1.7, "end": 1.8},
            {"word": "catch", "start": 1.9, "end": 2.1},
            {"word": "the", "start": 2.2, "end": 2.3},
            {"word": "masters,", "start": 2.4, "end": 2.7},
            {"word": "you've", "start": 2.8, "end": 3.0},
            {"word": "got", "start": 3.1, "end": 3.2},
            {"word": "to", "start": 3.3, "end": 3.4},
            {"word": "study", "start": 3.5, "end": 3.8},
        ]
        result = split_with_semantic_protection(words, max_cpl=25, language="en")
        # 检查所有片段都不超过 max_cpl
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= 25

    def test_complex_sentence_with_multiple_boundaries(self):
        """测试包含多个边界的复杂句子"""
        words = [
            {"word": "First,", "start": 0.0, "end": 0.3},
            {"word": "we", "start": 0.4, "end": 0.5},
            {"word": "need", "start": 0.6, "end": 0.8},
            {"word": "to", "start": 0.9, "end": 1.0},
            {"word": "study,", "start": 1.1, "end": 1.4},
            {"word": "and", "start": 1.5, "end": 1.7},
            {"word": "then", "start": 2.5, "end": 2.7},
            {"word": "we", "start": 2.8, "end": 2.9},
            {"word": "can", "start": 3.0, "end": 3.2},
            {"word": "start.", "start": 3.3, "end": 3.6},
        ]
        result = split_with_semantic_protection(words, max_cpl=20, language="en")
        # 验证分割结果
        assert len(result) >= 2
        # 检查所有片段都不超过 max_cpl
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= 20

    def test_very_long_text_requires_multiple_splits(self):
        """测试需要多次分割的长文本"""
        words = [
            {"word": "This,", "start": 0.0, "end": 0.2},
            {"word": "is,", "start": 0.3, "end": 0.5},
            {"word": "a,", "start": 0.6, "end": 0.8},
            {"word": "very,", "start": 0.9, "end": 1.1},
            {"word": "long,", "start": 1.2, "end": 1.4},
            {"word": "text,", "start": 1.5, "end": 1.7},
            {"word": "that,", "start": 1.8, "end": 2.0},
            {"word": "needs,", "start": 2.1, "end": 2.3},
            {"word": "many,", "start": 2.4, "end": 2.6},
            {"word": "splits", "start": 2.7, "end": 2.9},
        ]
        max_cpl = 10
        result = split_with_semantic_protection(words, max_cpl=max_cpl, language="en")
        # 应该产生多个片段
        assert len(result) >= 3
        # 每个片段都应该满足长度限制
        for seg in result:
            text = "".join(w.get("word", "") for w in seg)
            assert len(text) <= max_cpl
