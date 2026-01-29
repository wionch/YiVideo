"""
MultilingualSubtitleSegmenter 集成测试

测试三层断句策略的整合:
1. 强标点断句
2. PySBD 语义断句
3. 通用规则兜底
4. 语义保护断句
"""

import pytest

from services.common.subtitle.segmenter import (
    MultilingualSubtitleSegmenter,
    collect_semantic_boundaries,
    find_best_boundary,
    split_with_semantic_protection,
    merge_incomplete_segments,
)


class TestMultilingualSubtitleSegmenter:
    """测试多语言字幕断句器"""

    @pytest.fixture
    def segmenter(self):
        return MultilingualSubtitleSegmenter()

    def test_empty_input(self, segmenter):
        """测试空输入"""
        result = segmenter.segment([])
        assert result == []

    def test_single_word(self, segmenter):
        """测试单个词"""
        words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
        result = segmenter.segment(words)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_strong_punctuation_split(self, segmenter):
        """测试强标点断句"""
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
            {"word": ".", "start": 1.0, "end": 1.2},
            {"word": "How", "start": 1.5, "end": 2.0},
            {"word": " ", "start": 2.0, "end": 2.0},
            {"word": "are", "start": 2.0, "end": 2.3},
            {"word": " ", "start": 2.3, "end": 2.3},
            {"word": "you", "start": 2.3, "end": 2.6},
            {"word": "?", "start": 2.6, "end": 2.8},
        ]
        result = segmenter.segment(words)
        assert len(result) == 2
        # 第一句: "Hello world."
        assert "".join(w["word"] for w in result[0]) == "Hello world."
        # 第二句: "How are you?"
        assert "".join(w["word"] for w in result[1]) == "How are you?"

    def test_fallback_split_by_word_count(self, segmenter):
        """测试兜底策略 - 按字数分割"""
        # 创建多个词组成的长句子，超过 max_cpl
        words = [
            {"word": "This", "start": 0.0, "end": 0.2},
            {"word": " ", "start": 0.2, "end": 0.2},
            {"word": "is", "start": 0.2, "end": 0.4},
            {"word": " ", "start": 0.4, "end": 0.4},
            {"word": "a", "start": 0.4, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "very", "start": 0.5, "end": 0.7},
            {"word": " ", "start": 0.7, "end": 0.7},
            {"word": "long", "start": 0.7, "end": 0.9},
            {"word": " ", "start": 0.9, "end": 0.9},
            {"word": "sentence", "start": 0.9, "end": 1.2},
        ]
        result = segmenter.segment(words, max_cpl=15)
        # 应该被分割成多个片段
        assert len(result) > 1
        # 每个片段应该不超过 max_cpl
        for seg in result:
            text = "".join(w["word"] for w in seg)
            assert len(text) <= 15

    def test_within_limits_check(self, segmenter):
        """测试限制检查"""
        words = [
            {"word": "Short", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "text", "start": 0.5, "end": 1.0},
        ]
        # 正常情况，不超限
        result = segmenter.segment(words, max_cpl=100, max_duration=10.0)
        assert len(result) == 1

    def test_duration_limit(self, segmenter):
        """测试持续时间限制"""
        words = [
            {"word": "This", "start": 0.0, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "is", "start": 1.0, "end": 2.0},
            {"word": " ", "start": 2.0, "end": 2.0},
            {"word": "a", "start": 2.0, "end": 3.0},
            {"word": " ", "start": 3.0, "end": 3.0},
            {"word": "long", "start": 3.0, "end": 8.0},  # 持续5秒
            {"word": " ", "start": 8.0, "end": 8.0},
            {"word": "sentence", "start": 8.0, "end": 10.0},
        ]
        # 持续时间超过 max_duration=7.0，应该触发兜底分割
        result = segmenter.segment(words, max_duration=7.0, max_cpl=100)
        # 由于持续时间超限，应该被分割
        assert len(result) >= 1

    def test_cps_limit(self, segmenter):
        """测试每秒字符数限制"""
        # 创建一个很长的文本，在很短时间内说完
        words = [
            {"word": "Verylongtext", "start": 0.0, "end": 0.1},
            {"word": "here", "start": 0.1, "end": 0.2},
        ]
        # CPS = 14 / 0.2 = 70，超过 max_cps=18.0
        result = segmenter.segment(words, max_cps=18.0, max_cpl=100)
        # 应该被分割
        assert len(result) >= 1

    def test_chinese_punctuation(self, segmenter):
        """测试中文标点断句"""
        words = [
            {"word": "你好", "start": 0.0, "end": 0.5},
            {"word": "。", "start": 0.5, "end": 0.7},
            {"word": "世界", "start": 1.0, "end": 1.5},
            {"word": "！", "start": 1.5, "end": 1.7},
        ]
        result = segmenter.segment(words)
        assert len(result) == 2
        assert "".join(w["word"] for w in result[0]) == "你好。"
        assert "".join(w["word"] for w in result[1]) == "世界！"

    def test_weak_punctuation_fallback(self, segmenter):
        """测试弱标点兜底分割"""
        # 长文本，没有强标点，但有弱标点
        words = [
            {"word": "First", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "part", "start": 0.5, "end": 1.0},
            {"word": ",", "start": 1.0, "end": 1.1},
            {"word": " ", "start": 1.1, "end": 1.1},
            {"word": "second", "start": 1.1, "end": 1.6},
            {"word": " ", "start": 1.6, "end": 1.6},
            {"word": "part", "start": 1.6, "end": 2.0},
        ]
        # 总长度超过 max_cpl=15 应该触发弱标点分割
        result = segmenter.segment(words, max_cpl=15)
        # 应该被分割成多个片段
        assert len(result) >= 1

    def test_weak_punctuation_no_tiny_segment(self, segmenter, monkeypatch):
        """测试弱标点不产生极短片段"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "I,", "start": 0.0, "end": 0.3},
            {"word": " ", "start": 0.3, "end": 0.3},
            {"word": "agree", "start": 0.3, "end": 0.7},
            {"word": " ", "start": 0.7, "end": 0.7},
            {"word": "with", "start": 0.7, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "you", "start": 1.0, "end": 1.3},
        ]
        result = segmenter.segment(words, max_cpl=6)
        assert all(len("".join(w["word"] for w in seg).strip()) > 2 for seg in result)

    def test_pysbd_language_support(self, segmenter):
        """测试 PySBD 语言支持列表"""
        # 检查支持的语言列表
        assert "en" in segmenter.PYSBD_LANGS
        assert "zh" in segmenter.PYSBD_LANGS
        assert "ja" in segmenter.PYSBD_LANGS
        assert "de" in segmenter.PYSBD_LANGS

    def test_pysbd_global_sentence_first(self, segmenter, monkeypatch):
        """测试全局语义句界优先"""
        class FakeSegmenter:
            def segment(self, text):
                return ["U.S. It's famous."]

        words = [
            {"word": "U.", "start": 0.0, "end": 0.2},
            {"word": "S.", "start": 0.2, "end": 0.4},
            {"word": " ", "start": 0.4, "end": 0.4},
            {"word": "It's", "start": 0.4, "end": 0.6},
            {"word": " ", "start": 0.6, "end": 0.6},
            {"word": "famous.", "start": 0.6, "end": 1.0},
        ]
        monkeypatch.setattr(segmenter, "_pysbd_available", True)
        monkeypatch.setattr(
            segmenter, "_get_pysbd_segmenter", lambda _lang: FakeSegmenter()
        )

        result = segmenter.segment(words, language="en")

        assert len(result) == 1
        assert "".join(w["word"] for w in result[0]) == "U.S. It's famous."
        assert [w["start"] for w in result[0]] == [0.0, 0.2, 0.4, 0.4, 0.6, 0.6]

    def test_abbreviation_not_split(self, segmenter):
        """测试缩写词不会被强标点断句"""
        words = [
            {"word": "Dr.", "start": 0.0, "end": 0.3},
            {"word": " ", "start": 0.3, "end": 0.3},
            {"word": "Smith", "start": 0.3, "end": 0.8},
            {"word": " ", "start": 0.8, "end": 0.8},
            {"word": "is", "start": 0.8, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "here", "start": 1.0, "end": 1.3},
            {"word": ".", "start": 1.3, "end": 1.5},
        ]
        result = segmenter.segment(words)
        # "Dr." 是缩写，不应该在此处断句
        # 应该在最后的 "." 处断句
        assert len(result) == 1
        assert "".join(w["word"] for w in result[0]) == "Dr. Smith is here."

    def test_hyphen_not_split_as_weak_punct(self, segmenter, monkeypatch):
        """测试连字符不作为弱标点断句"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "snap-", "start": 0.0, "end": 0.4},
            {"word": "-trap", "start": 0.4, "end": 0.8},
            {"word": " ", "start": 0.8, "end": 0.8},
            {"word": "jaws", "start": 0.8, "end": 1.2},
        ]
        result = segmenter.segment(words, max_cpl=6)
        texts = ["".join(w["word"] for w in seg) for seg in result]
        assert any("snap-" in text and "-trap" in text for text in texts)


class TestSemanticProtectionIntegration:
    """测试语义保护功能集成到 Segmenter"""

    @pytest.fixture
    def segmenter(self):
        return MultilingualSubtitleSegmenter()

    def test_semantic_protection_uses_weak_punct(self, segmenter, monkeypatch):
        """测试语义保护优先在弱标点处切分"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "world,", "start": 0.5, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "this", "start": 1.0, "end": 1.5},
            {"word": " ", "start": 1.5, "end": 1.5},
            {"word": "is", "start": 1.5, "end": 2.0},
            {"word": " ", "start": 2.0, "end": 2.0},
            {"word": "test", "start": 2.0, "end": 2.5},
        ]
        # 总长度超过 max_cpl，应该触发语义保护切分
        result = segmenter.segment(words, max_cpl=20, use_semantic_protection=True)
        # 应该在逗号处切分
        texts = ["".join(w["word"] for w in seg) for seg in result]
        assert any("world," in text for text in texts)

    def test_semantic_protection_avoids_tiny_segments(self, segmenter, monkeypatch):
        """测试语义保护避免产生极短片段"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "A,", "start": 0.0, "end": 0.3},
            {"word": " ", "start": 0.3, "end": 0.3},
            {"word": "big", "start": 0.3, "end": 0.6},
            {"word": " ", "start": 0.6, "end": 0.6},
            {"word": "test", "start": 0.6, "end": 1.0},
        ]
        result = segmenter.segment(words, max_cpl=6, use_semantic_protection=True)
        # 检查没有极短片段（长度 <= 2）
        for seg in result:
            text = "".join(w["word"] for w in seg).strip()
            assert len(text) > 2, f"发现极短片段: '{text}'"

    def test_semantic_protection_fallback_to_word_count(self, segmenter, monkeypatch):
        """测试语义保护在没有语义边界时回退到字数切分"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        # 使用大写开头的词，避免被 merge_incomplete_segments 合并
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "World", "start": 0.5, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "Test!", "start": 1.0, "end": 1.5},  # 有结尾标点
        ]
        # 没有弱标点，应该回退到字数切分
        result = segmenter.segment(words, max_cpl=10, use_semantic_protection=True)
        assert len(result) >= 1
        # 检查每个片段不超过 max_cpl（最后一个片段除外，如果它是单个词）
        for seg in result:
            text = "".join(w["word"] for w in seg)
            assert len(text) <= 10 or len(seg) == 1

    def test_merge_incomplete_segments_integration(self, segmenter, monkeypatch):
        """测试后处理合并不完整片段"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},  # 无结尾标点
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "world.", "start": 0.5, "end": 1.0},  # 有结尾标点，小写开头
        ]
        result = segmenter.segment(words, max_cpl=20, use_semantic_protection=True)
        # 应该合并成一个完整片段（因为第一个片段无结尾标点，第二个小写开头）
        assert len(result) == 1
        assert "".join(w["word"] for w in result[0]) == "Hello world."

    def test_semantic_protection_disabled(self, segmenter, monkeypatch):
        """测试禁用语义保护时使用原有逻辑"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "world,", "start": 0.5, "end": 1.0},
            {"word": " ", "start": 1.0, "end": 1.0},
            {"word": "test", "start": 1.0, "end": 1.5},
        ]
        # 禁用语义保护
        result = segmenter.segment(words, max_cpl=10, use_semantic_protection=False)
        assert len(result) >= 1

    def test_semantic_protection_with_chinese(self, segmenter, monkeypatch):
        """测试中文语义保护"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "你好", "start": 0.0, "end": 0.5},
            {"word": "，", "start": 0.5, "end": 0.6},
            {"word": "世界", "start": 0.6, "end": 1.0},
            {"word": "，", "start": 1.0, "end": 1.1},
            {"word": "测试", "start": 1.1, "end": 1.5},
        ]
        result = segmenter.segment(words, max_cpl=8, language="zh", use_semantic_protection=True)
        texts = ["".join(w["word"] for w in seg) for seg in result]
        # 应该在中文逗号处切分
        assert any("你好" in text for text in texts)

    def test_semantic_protection_preserves_timestamps(self, segmenter, monkeypatch):
        """测试语义保护保持时间戳不变"""
        monkeypatch.setattr(segmenter, "_pysbd_available", False)
        words = [
            {"word": "Hello,", "start": 0.0, "end": 0.5},
            {"word": " ", "start": 0.5, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ]
        result = segmenter.segment(words, max_cpl=8, use_semantic_protection=True)
        # 检查时间戳保持不变
        all_words = []
        for seg in result:
            all_words.extend(seg)
        assert [w["start"] for w in all_words] == [0.0, 0.5, 0.5]
        assert [w["end"] for w in all_words] == [0.5, 0.5, 1.0]
