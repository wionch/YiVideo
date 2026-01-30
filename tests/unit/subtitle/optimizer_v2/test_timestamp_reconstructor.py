"""
时间戳重建器单元测试

测试时间戳重建器的核心功能：
1. 查找稳定词
2. 间隙时间戳分配
3. 单段重建
4. 多段批量重建
"""

import pytest
from services.common.subtitle.optimizer_v2.timestamp_reconstructor import (
    TimestampReconstructor,
)
from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    OptimizedLine,
    WordTimestamp,
)


class TestFindStableWords:
    """测试查找稳定词功能"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_identical_texts(self, reconstructor):
        """测试完全相同的文本"""
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
            WordTimestamp(word="today", start=1.0, end=1.5),
        ]
        optimized_text = "Hello world today"

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # 应该找到所有词作为稳定词（长度都>=2）
        assert len(stable) == 3
        assert stable[0][0] == 0  # 原始索引
        assert stable[0][1] == 0  # 优化后索引
        assert stable[0][2].word == "Hello"

    def test_partial_modification(self, reconstructor):
        """测试部分修改"""
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
            WordTimestamp(word="today", start=1.0, end=1.5),
        ]
        optimized_text = "Hello everyone today"  # world -> everyone

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # 应该找到 "Hello" 和 "today" 作为稳定词
        assert len(stable) == 2
        assert stable[0][2].word == "Hello"
        assert stable[1][2].word == "today"

    def test_insertion(self, reconstructor):
        """测试插入新词"""
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]
        optimized_text = "Hello beautiful world"  # 插入 beautiful

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # 应该找到 "Hello" 和 "world" 作为稳定词
        assert len(stable) == 2
        assert stable[0][2].word == "Hello"
        assert stable[1][2].word == "world"

    def test_deletion(self, reconstructor):
        """测试删除词"""
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="the", start=0.5, end=0.7),
            WordTimestamp(word="world", start=0.7, end=1.2),
        ]
        optimized_text = "Hello world"  # 删除 "the"

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # 应该找到 "Hello" 和 "world" 作为稳定词
        assert len(stable) == 2
        assert stable[0][2].word == "Hello"
        assert stable[1][2].word == "world"

    def test_empty_input(self, reconstructor):
        """测试空输入"""
        assert reconstructor._find_stable_words([], "text") == []
        assert reconstructor._find_stable_words([], "") == []

    def test_short_words_filtered(self, reconstructor):
        """测试短词被过滤"""
        original_words = [
            WordTimestamp(word="A", start=0.0, end=0.2),
            WordTimestamp(word="big", start=0.2, end=0.5),
            WordTimestamp(word="cat", start=0.5, end=0.8),
        ]
        optimized_text = "A big cat"

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # "A" 应该被过滤（长度为1 < min_stable_word_length=2）
        assert len(stable) == 2
        assert stable[0][2].word == "big"
        assert stable[1][2].word == "cat"

    def test_case_insensitive(self, reconstructor):
        """测试大小写不敏感匹配"""
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="WORLD", start=0.5, end=1.0),
        ]
        optimized_text = "hello World"

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # 大小写应该被视为相同
        assert len(stable) == 2


class TestDistributeInGap:
    """测试间隙时间戳分配"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_single_word_gap(self, reconstructor):
        """测试单词间隙"""
        result = reconstructor._distribute_in_gap(
            gap_words=["beautiful"],
            gap_start=0.5,
            gap_end=1.0,
            left_anchor=None,
            right_anchor=None,
        )

        assert len(result) == 1
        assert result[0].word == "beautiful"
        assert result[0].start == 0.5
        assert result[0].end == 1.0
        assert result[0].probability == 0.8

    def test_multiple_words_gap(self, reconstructor):
        """测试多词间隙"""
        result = reconstructor._distribute_in_gap(
            gap_words=["very", "beautiful"],
            gap_start=0.0,
            gap_end=1.0,
            left_anchor=None,
            right_anchor=None,
        )

        assert len(result) == 2
        # 每个词应该获得0.5秒
        assert result[0].word == "very"
        assert result[0].start == 0.0
        assert result[0].end == 0.5

        assert result[1].word == "beautiful"
        assert result[1].start == 0.5
        assert result[1].end == 1.0

    def test_empty_gap(self, reconstructor):
        """测试空间隙"""
        result = reconstructor._distribute_in_gap(
            gap_words=[],
            gap_start=0.0,
            gap_end=1.0,
            left_anchor=None,
            right_anchor=None,
        )

        assert result == []

    def test_invalid_time_range(self, reconstructor):
        """测试无效时间范围"""
        with pytest.raises(ValueError, match="间隙结束时间必须大于等于开始时间"):
            reconstructor._distribute_in_gap(
                gap_words=["word"],
                gap_start=1.0,
                gap_end=0.5,
                left_anchor=None,
                right_anchor=None,
            )

    def test_with_anchors(self, reconstructor):
        """测试带锚点的间隙分配"""
        left = WordTimestamp(word="Hello", start=0.0, end=0.5, probability=1.0)
        right = WordTimestamp(word="world", start=1.5, end=2.0, probability=1.0)

        result = reconstructor._distribute_in_gap(
            gap_words=["beautiful"],
            gap_start=0.5,
            gap_end=1.5,
            left_anchor=left,
            right_anchor=right,
        )

        assert len(result) == 1
        assert result[0].start == 0.5
        assert result[0].end == 1.5


class TestReconstructSegment:
    """测试单段重建"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_no_change(self, reconstructor):
        """测试无变化时重建"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.5,
            text="Hello world today",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5),
                WordTimestamp(word="world", start=0.5, end=1.0),
                WordTimestamp(word="today", start=1.0, end=1.5),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello world today",
            optimized_start=0.0,
            optimized_end=1.5,
        )

        # 应该保留原始时间戳
        assert len(result) == 3
        assert result[0].word == "Hello"
        assert result[0].start == 0.0
        assert result[0].end == 0.5
        assert result[1].word == "world"
        assert result[1].start == 0.5
        assert result[1].end == 1.0
        assert result[2].word == "today"
        assert result[2].start == 1.0
        assert result[2].end == 1.5

    def test_insertion_reconstruction(self, reconstructor):
        """测试插入新词时重建"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.0,
            text="Hello world",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5),
                WordTimestamp(word="world", start=0.5, end=1.0),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello beautiful world",  # 插入 beautiful
            optimized_start=0.0,
            optimized_end=1.0,
        )

        # 应该有3个词
        assert len(result) == 3
        assert result[0].word == "Hello"
        assert result[0].start == 0.0  # 稳定词保留原时间

        assert result[1].word == "beautiful"
        # beautiful 应该在 Hello 和 world 之间分配时间
        assert result[1].start >= 0.5
        assert result[1].end <= 0.5

        assert result[2].word == "world"
        assert result[2].start == 0.5  # 稳定词保留原时间

    def test_deletion_reconstruction(self, reconstructor):
        """测试删除词时重建"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.5,
            text="Hello the world",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5),
                WordTimestamp(word="the", start=0.5, end=0.7),
                WordTimestamp(word="world", start=0.7, end=1.5),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello world",  # 删除 "the"
            optimized_start=0.0,
            optimized_end=1.5,
        )

        # 应该有2个词
        assert len(result) == 2
        assert result[0].word == "Hello"
        assert result[1].word == "world"

    def test_no_original_words(self, reconstructor):
        """测试没有原始词级时间戳"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.0,
            text="Hello world",
            words=None,
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello world",
            optimized_start=0.0,
            optimized_end=1.0,
        )

        # 应该使用均匀分配
        assert len(result) == 2
        assert result[0].start == 0.0
        assert result[0].end == 0.5
        assert result[1].start == 0.5
        assert result[1].end == 1.0

    def test_empty_optimized_text_raises(self, reconstructor):
        """测试空优化文本抛出错误"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.0,
            text="Hello",
            words=[WordTimestamp(word="Hello", start=0.0, end=1.0)],
        )

        with pytest.raises(ValueError, match="优化后文本不能为空"):
            reconstructor.reconstruct_segment(
                segment=segment,
                optimized_text="",
                optimized_start=0.0,
                optimized_end=1.0,
            )

    def test_invalid_time_range_raises(self, reconstructor):
        """测试无效时间范围抛出错误"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.0,
            text="Hello",
            words=[WordTimestamp(word="Hello", start=0.0, end=1.0)],
        )

        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            reconstructor.reconstruct_segment(
                segment=segment,
                optimized_text="Hello",
                optimized_start=1.0,
                optimized_end=0.0,
            )

    def test_modification_with_punctuation(self, reconstructor):
        """测试带标点的修改"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=2.0,
            text="Hello world today",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5),
                WordTimestamp(word="world", start=0.5, end=1.0),
                WordTimestamp(word="today", start=1.0, end=2.0),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello, world! Today?",  # 添加标点
            optimized_start=0.0,
            optimized_end=2.0,
        )

        # 应该包含标点和词
        assert len(result) == 6  # Hello , world ! Today ?


class TestReconstructAll:
    """测试批量重建"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_multiple_segments_no_change(self, reconstructor):
        """测试多段无变化重建"""
        segments = [
            SubtitleSegment(
                id=1,
                start=0.0,
                end=1.0,
                text="First segment",
                words=[
                    WordTimestamp(word="First", start=0.0, end=0.5),
                    WordTimestamp(word="segment", start=0.5, end=1.0),
                ],
            ),
            SubtitleSegment(
                id=2,
                start=1.0,
                end=2.0,
                text="Second segment",
                words=[
                    WordTimestamp(word="Second", start=1.0, end=1.5),
                    WordTimestamp(word="segment", start=1.5, end=2.0),
                ],
            ),
        ]

        optimized_lines = [
            OptimizedLine(text="First segment", start=0.0, end=1.0, is_modified=False),
            OptimizedLine(text="Second segment", start=1.0, end=2.0, is_modified=False),
        ]

        result = reconstructor.reconstruct_all(segments, optimized_lines)

        assert len(result) == 2
        assert len(result[0]) == 2
        assert len(result[1]) == 2

    def test_multiple_segments_with_insertion(self, reconstructor):
        """测试多段插入重建"""
        segments = [
            SubtitleSegment(
                id=1,
                start=0.0,
                end=1.0,
                text="Hello world",
                words=[
                    WordTimestamp(word="Hello", start=0.0, end=0.5),
                    WordTimestamp(word="world", start=0.5, end=1.0),
                ],
            ),
            SubtitleSegment(
                id=2,
                start=1.0,
                end=2.0,
                text="Good morning",
                words=[
                    WordTimestamp(word="Good", start=1.0, end=1.5),
                    WordTimestamp(word="morning", start=1.5, end=2.0),
                ],
            ),
        ]

        optimized_lines = [
            OptimizedLine(
                text="Hello beautiful world", start=0.0, end=1.0, is_modified=True
            ),
            OptimizedLine(text="Good morning", start=1.0, end=2.0, is_modified=False),
        ]

        result = reconstructor.reconstruct_all(segments, optimized_lines)

        assert len(result) == 2
        # 第一段有3个词（插入了beautiful）
        assert len(result[0]) == 3
        # 第二段保持2个词
        assert len(result[1]) == 2

    def test_mismatched_length_raises(self, reconstructor):
        """测试长度不匹配抛出错误"""
        segments = [
            SubtitleSegment(id=1, start=0.0, end=1.0, text="First"),
        ]
        optimized_lines = [
            OptimizedLine(text="First", start=0.0, end=1.0),
            OptimizedLine(text="Second", start=1.0, end=2.0),
        ]

        with pytest.raises(ValueError, match="段数与优化行数不匹配"):
            reconstructor.reconstruct_all(segments, optimized_lines)

    def test_none_input_raises(self, reconstructor):
        """测试None输入抛出错误"""
        with pytest.raises(ValueError, match="输入参数不能为None"):
            reconstructor.reconstruct_all(None, [])

        with pytest.raises(ValueError, match="输入参数不能为None"):
            reconstructor.reconstruct_all([], None)


class TestReconstructFromDict:
    """测试字典接口"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_basic_dict_reconstruction(self, reconstructor):
        """测试基本字典重建"""
        original_segments = [
            {
                "id": 1,
                "start": 0.0,
                "end": 1.0,
                "text": "Hello world",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 1.0},
                    {"word": "world", "start": 0.5, "end": 1.0, "probability": 1.0},
                ],
            }
        ]

        optimized_lines = [
            {"text": "Hello world", "start": 0.0, "end": 1.0, "is_modified": False}
        ]

        result = reconstructor.reconstruct_from_dict(
            original_segments, optimized_lines
        )

        assert len(result) == 1
        assert len(result[0]) == 2
        assert result[0][0]["word"] == "Hello"
        assert result[0][0]["start"] == 0.0
        assert result[0][0]["end"] == 0.5

    def test_dict_with_modification(self, reconstructor):
        """测试带修改的字典重建"""
        original_segments = [
            {
                "id": 1,
                "start": 0.0,
                "end": 1.0,
                "text": "Hello world",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 1.0},
                    {"word": "world", "start": 0.5, "end": 1.0, "probability": 1.0},
                ],
            }
        ]

        optimized_lines = [
            {"text": "Hello beautiful world", "start": 0.0, "end": 1.0, "is_modified": True}
        ]

        result = reconstructor.reconstruct_from_dict(
            original_segments, optimized_lines
        )

        assert len(result) == 1
        assert len(result[0]) == 3  # 插入了 beautiful


class TestEdgeCases:
    """测试边界情况"""

    @pytest.fixture
    def reconstructor(self):
        """提供默认重建器"""
        return TimestampReconstructor()

    def test_single_word_segment(self, reconstructor):
        """测试单字段"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=0.5,
            text="Hello",
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello",
            optimized_start=0.0,
            optimized_end=0.5,
        )

        assert len(result) == 1
        assert result[0].word == "Hello"

    def test_all_words_replaced(self, reconstructor):
        """测试所有词都被替换"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=1.0,
            text="Old text here",
            words=[
                WordTimestamp(word="Old", start=0.0, end=0.3),
                WordTimestamp(word="text", start=0.3, end=0.6),
                WordTimestamp(word="here", start=0.6, end=1.0),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Completely different words",  # 完全不同的文本
            optimized_start=0.0,
            optimized_end=1.0,
        )

        # 应该使用均匀分配
        assert len(result) == 3
        # 验证时间均匀分布
        assert result[0].start == 0.0
        assert result[0].end == pytest.approx(0.333, rel=0.01)

    def test_very_long_gap(self, reconstructor):
        """测试非常长的间隙"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=10.0,
            text="Start end",
            words=[
                WordTimestamp(word="Start", start=0.0, end=1.0),
                WordTimestamp(word="end", start=9.0, end=10.0),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Start word1 word2 word3 word4 word5 end",  # 长间隙
            optimized_start=0.0,
            optimized_end=10.0,
        )

        assert len(result) == 7
        # 验证中间词均匀分配8秒间隙
        assert result[1].start == 1.0
        assert result[1].end == pytest.approx(2.6, rel=0.1)

    def test_punctuation_handling(self, reconstructor):
        """测试标点处理"""
        segment = SubtitleSegment(
            id=1,
            start=0.0,
            end=2.0,
            text="Hello world",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=1.0),
                WordTimestamp(word="world", start=1.0, end=2.0),
            ],
        )

        result = reconstructor.reconstruct_segment(
            segment=segment,
            optimized_text="Hello, world!",  # 添加标点
            optimized_start=0.0,
            optimized_end=2.0,
        )

        # 应该包含标点和词
        assert len(result) == 4  # Hello , world !
