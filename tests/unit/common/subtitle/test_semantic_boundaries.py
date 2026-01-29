"""
语义边界收集函数测试

测试 collect_semantic_boundaries() 函数:
1. 弱标点边界检测
2. 连词边界检测
3. 停顿边界检测
4. 边界分数计算
5. 多语言支持
"""

import pytest
from typing import List, Dict, Any

from services.common.subtitle.segmenter import collect_semantic_boundaries
from services.common.subtitle.segmentation_config import SegmentationConfig


class TestCollectSemanticBoundaries:
    """测试语义边界收集函数"""

    @pytest.fixture
    def config(self):
        return SegmentationConfig()

    def test_empty_words_list(self):
        """测试空词列表返回空结果"""
        result = collect_semantic_boundaries([], "en")
        assert result == []

    def test_single_word_no_boundaries(self):
        """测试单个词没有边界"""
        words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
        result = collect_semantic_boundaries(words, "en")
        assert result == []

    def test_weak_punctuation_boundary_comma(self):
        """测试逗号弱标点边界"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "en")
        assert len(result) == 1
        assert result[0]["index"] == 0  # 边界在第一个词后
        assert result[0]["type"] == "weak_punct"
        assert result[0]["char"] == ","
        assert "score" in result[0]
        assert 0 <= result[0]["score"] <= 1

    def test_weak_punctuation_boundary_semicolon(self):
        """测试分号弱标点边界"""
        words = [
            {"word": "First;", "start": 0.0, "end": 0.5},
            {"word": "second", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "en")
        assert len(result) == 1
        assert result[0]["type"] == "weak_punct"
        assert result[0]["char"] == ";"

    def test_conjunction_boundary(self):
        """测试连词边界"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "and", "start": 0.6, "end": 0.8},
            {"word": "world", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "en")
        # 应该检测到 "and" 前的边界
        conj_boundaries = [b for b in result if b["type"] == "conjunction"]
        assert len(conj_boundaries) >= 1
        assert conj_boundaries[0]["word"] == "and"

    def test_pause_boundary(self):
        """测试停顿边界"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 1.5, "end": 2.0}  # 1秒停顿
        ]
        result = collect_semantic_boundaries(words, "en")
        pause_boundaries = [b for b in result if b["type"] == "pause"]
        assert len(pause_boundaries) == 1
        assert pause_boundaries[0]["index"] == 0
        assert pause_boundaries[0]["gap"] == 1.0

    def test_multiple_boundaries(self):
        """测试多个边界检测"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "and", "start": 0.6, "end": 0.8},
            {"word": "world", "start": 1.5, "end": 2.0}  # 停顿
        ]
        result = collect_semantic_boundaries(words, "en")
        # 应该检测到逗号、连词和停顿
        assert len(result) >= 2

    def test_boundary_score_range(self):
        """测试边界分数在有效范围内"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "and", "start": 0.6, "end": 0.8},
            {"word": "world", "start": 1.5, "end": 2.0}
        ]
        result = collect_semantic_boundaries(words, "en")
        for boundary in result:
            assert 0 <= boundary["score"] <= 1

    def test_boundary_result_structure(self):
        """测试边界结果结构"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "en")
        assert len(result) == 1
        boundary = result[0]
        assert "index" in boundary
        assert "type" in boundary
        assert "score" in boundary
        assert isinstance(boundary["index"], int)
        assert isinstance(boundary["type"], str)
        assert isinstance(boundary["score"], float)

    def test_chinese_weak_punctuation(self):
        """测试中文弱标点"""
        words = [
            {"word": "你好，", "start": 0.0, "end": 0.5},
            {"word": "世界", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "zh")
        assert len(result) == 1
        assert result[0]["type"] == "weak_punct"
        assert result[0]["char"] == "，"

    def test_chinese_conjunction(self):
        """测试中文连词"""
        words = [
            {"word": "我", "start": 0.0, "end": 0.3},
            {"word": "和", "start": 0.4, "end": 0.6},
            {"word": "你", "start": 0.7, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "zh")
        conj_boundaries = [b for b in result if b["type"] == "conjunction"]
        assert len(conj_boundaries) >= 1
        assert conj_boundaries[0]["word"] == "和"

    def test_sentence_starter_boundary(self):
        """测试句首词边界"""
        # 注意：不使用逗号，避免被弱标点抢占边界位置
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "the", "start": 1.0, "end": 1.2},  # 句首词，前面有停顿
            {"word": "world", "start": 1.3, "end": 1.5}
        ]
        result = collect_semantic_boundaries(words, "en")
        starter_boundaries = [b for b in result if b["type"] == "sentence_starter"]
        assert len(starter_boundaries) >= 1
        assert starter_boundaries[0]["word"] == "the"

    def test_no_duplicate_boundaries(self):
        """测试同一位置不会有重复边界"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},  # 逗号
            {"word": "and", "start": 1.0, "end": 1.2}  # 连词 + 停顿
        ]
        result = collect_semantic_boundaries(words, "en")
        indices = [b["index"] for b in result]
        # 检查没有重复的index
        assert len(indices) == len(set(indices))

    def test_english_language(self):
        """测试英语语言支持"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "en")
        assert len(result) == 1

    def test_german_language(self):
        """测试德语语言支持"""
        words = [
            {"word": "Hallo,", "start": 0.0, "end": 0.5},
            {"word": "und", "start": 0.6, "end": 0.8},
            {"word": "Welt", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "de")
        assert len(result) >= 1

    def test_french_language(self):
        """测试法语语言支持"""
        words = [
            {"word": "Bonjour,", "start": 0.0, "end": 0.5},
            {"word": "et", "start": 0.6, "end": 0.8},
            {"word": "monde", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "fr")
        assert len(result) >= 1

    def test_spanish_language(self):
        """测试西班牙语语言支持"""
        words = [
            {"word": "Hola,", "start": 0.0, "end": 0.5},
            {"word": "y", "start": 0.6, "end": 0.8},
            {"word": "mundo", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "es")
        assert len(result) >= 1

    def test_japanese_language(self):
        """测试日语语言支持"""
        words = [
            {"word": "こんにちは、", "start": 0.0, "end": 0.5},
            {"word": "と", "start": 0.6, "end": 0.8},
            {"word": "世界", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "ja")
        assert len(result) >= 1

    def test_korean_language(self):
        """测试韩语语言支持"""
        words = [
            {"word": "안녕,", "start": 0.0, "end": 0.5},
            {"word": "그리고", "start": 0.6, "end": 0.8},
            {"word": "세계", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "ko")
        assert len(result) >= 1

    def test_unknown_language_fallback(self):
        """测试未知语言回退到英语"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0}
        ]
        result = collect_semantic_boundaries(words, "unknown")
        assert len(result) == 1

    def test_hyphen_not_boundary(self):
        """测试连字符不是边界"""
        words = [
            {"word": "well-", "start": 0.0, "end": 0.3},
            {"word": "known", "start": 0.4, "end": 0.7}
        ]
        result = collect_semantic_boundaries(words, "en")
        # 连字符不应该被视为弱标点边界
        weak_puncts = [b for b in result if b["type"] == "weak_punct"]
        assert len(weak_puncts) == 0

    def test_short_pause_not_boundary(self):
        """测试短停顿不是边界"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.55, "end": 1.0}  # 0.05秒停顿，太短
        ]
        result = collect_semantic_boundaries(words, "en")
        pause_boundaries = [b for b in result if b["type"] == "pause"]
        assert len(pause_boundaries) == 0

    def test_conjunction_case_insensitive(self):
        """测试连词大小写不敏感"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "AND", "start": 0.6, "end": 0.8},
            {"word": "world", "start": 0.9, "end": 1.2}
        ]
        result = collect_semantic_boundaries(words, "en")
        conj_boundaries = [b for b in result if b["type"] == "conjunction"]
        assert len(conj_boundaries) >= 1

    def test_boundary_priority_weak_punct_higher_than_conjunction(self):
        """测试弱标点边界优先级高于连词"""
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},  # 弱标点
            {"word": "and", "start": 0.6, "end": 0.8}  # 连词
        ]
        result = collect_semantic_boundaries(words, "en")
        if len(result) == 1:
            # 如果只有一个边界，应该是弱标点
            assert result[0]["type"] == "weak_punct"


class TestSemanticBoundariesIntegration:
    """语义边界收集集成测试"""

    def test_real_world_sentence(self):
        """测试真实句子场景"""
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
            {"word": "study", "start": 3.5, "end": 3.8}
        ]
        result = collect_semantic_boundaries(words, "en")
        # 应该检测到多个边界
        assert len(result) >= 2
        # 检查边界类型
        types = [b["type"] for b in result]
        assert "weak_punct" in types

    def test_complex_sentence_with_all_boundary_types(self):
        """测试包含所有边界类型的复杂句子"""
        words = [
            {"word": "First,", "start": 0.0, "end": 0.3},  # 弱标点
            {"word": "we", "start": 0.4, "end": 0.5},
            {"word": "need", "start": 0.6, "end": 0.8},
            {"word": "to", "start": 0.9, "end": 1.0},
            {"word": "study,", "start": 1.1, "end": 1.4},  # 弱标点
            {"word": "and", "start": 1.5, "end": 1.7},  # 连词
            {"word": "then", "start": 2.5, "end": 2.7},  # 停顿 + 句首词
            {"word": "we", "start": 2.8, "end": 2.9},
            {"word": "can", "start": 3.0, "end": 3.2},
            {"word": "start.", "start": 3.3, "end": 3.6}
        ]
        result = collect_semantic_boundaries(words, "en")
        types = set(b["type"] for b in result)
        # 应该包含多种边界类型
        assert len(types) >= 2
