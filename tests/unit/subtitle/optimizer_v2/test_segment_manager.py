"""
字幕优化器V2分段管理器单元测试
"""

import pytest
from services.common.subtitle.optimizer_v2.segment_manager import (
    SegmentManager,
    SegmentInfo,
)
from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    OptimizedLine,
    SegmentTask,
    OverlapRegion,
    SegmentType,
)
from services.common.subtitle.optimizer_v2.config import SubtitleOptimizerConfig


class TestSegmentInfo:
    """分段信息测试"""

    def test_basic_properties(self):
        """测试基本属性"""
        segments = [
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
            SubtitleSegment(id=2, start=3.0, end=5.0, text="第二段"),
        ]
        info = SegmentInfo(
            index=0,
            start_line=0,
            end_line=2,
            segments=segments,
            is_overlap=False
        )

        assert info.index == 0
        assert info.start_line == 0
        assert info.end_line == 2
        assert info.line_count == 2
        assert info.is_overlap is False
        assert info.start_time == 1.0
        assert info.end_time == 5.0

    def test_empty_segments(self):
        """测试空段列表"""
        info = SegmentInfo(index=0, start_line=0, end_line=0)
        assert info.line_count == 0
        assert info.start_time == 0.0
        assert info.end_time == 0.0


class TestSegmentManagerCreation:
    """分段管理器创建测试"""

    def test_default_config(self):
        """测试默认配置"""
        manager = SegmentManager()
        assert manager.config.segment_size == 100
        assert manager.config.overlap_lines == 20

    def test_custom_config(self):
        """测试自定义配置"""
        config = SubtitleOptimizerConfig(segment_size=50, overlap_lines=10)
        manager = SegmentManager(config)
        assert manager.config.segment_size == 50
        assert manager.config.overlap_lines == 10


class TestCreateSegments:
    """创建分段任务测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        return SegmentManager()

    @pytest.fixture
    def small_manager(self):
        """提供小分段配置的管理器"""
        config = SubtitleOptimizerConfig(segment_size=5, overlap_lines=2)
        return SegmentManager(config)

    def test_empty_lines(self, manager):
        """测试空行列表"""
        result = manager.create_segments([])
        assert result == []

    def test_none_lines_raises_error(self, manager):
        """测试None输入抛出错误"""
        with pytest.raises(ValueError, match="lines不能为None"):
            manager.create_segments(None)

    def test_small_input_no_segmentation(self, manager):
        """测试小输入不分段"""
        lines = [f"[{i}]第{i}行字幕" for i in range(10)]
        result = manager.create_segments(lines)

        assert len(result) == 1
        assert result[0].task_id == "segment_0"
        assert len(result[0].segments) == 10

    def test_basic_segmentation(self, small_manager):
        """测试基本分段"""
        lines = [f"[{i}]第{i}行字幕" for i in range(15)]
        result = small_manager.create_segments(lines)

        # 15行，分段大小5，重叠2
        # segment_0: 0-5 (5行)
        # segment_1: 3-8 (5行，重叠2行)
        # segment_2: 6-11 (5行，重叠2行)
        # segment_3: 9-15 (6行，最后一段)
        assert len(result) == 4

    def test_segment_task_properties(self, small_manager):
        """测试分段任务属性"""
        lines = [f"[{i}]第{i}行字幕" for i in range(15)]
        result = small_manager.create_segments(lines)

        # 验证第一个任务
        assert result[0].task_id == "segment_0"
        assert len(result[0].segments) == 5  # 0-4
        assert result[0].segment_type == SegmentType.OVERLAP_START

        # 验证中间任务
        assert result[1].task_id == "segment_1"
        assert len(result[1].segments) == 5  # 3-7
        assert result[1].segment_type == SegmentType.OVERLAP_MIDDLE

        # 验证最后一个任务
        assert result[-1].task_id == "segment_3"
        assert result[-1].segment_type == SegmentType.OVERLAP_END

    def test_with_subtitle_segments(self, small_manager):
        """测试带字幕段的分段"""
        lines = [f"[{i}]第{i}行字幕" for i in range(10)]
        segments = [
            SubtitleSegment(id=i, start=float(i), end=float(i) + 2.0, text=f"第{i}行字幕")
            for i in range(10)
        ]

        result = small_manager.create_segments(lines, segments)

        # 10行，分段大小5，重叠2
        # segment_0: 0-5 (5行)
        # segment_1: 3-10 (7行，包含重叠，最后一段扩展到结尾)
        assert len(result) == 2
        # 验证第一段包含正确的字幕段
        assert result[0].segments[0].id == 0
        assert result[0].segments[0].start == 0.0

    def test_segment_with_context_lines(self, small_manager):
        """测试带上下文的分段"""
        lines = [f"[{i}]第{i}行字幕" for i in range(12)]
        result = small_manager.create_segments(lines)

        # 验证分段包含重叠区域
        # segment_0: 0-5
        # segment_1: 3-8 (包含3,4作为重叠)
        assert len(result[1].segments) == 5


class TestCalculateSegmentRanges:
    """计算分段范围测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        config = SubtitleOptimizerConfig(segment_size=10, overlap_lines=3)
        return SegmentManager(config)

    def test_empty_lines(self, manager):
        """测试空行"""
        result = manager.calculate_segment_ranges(0)
        assert result == []

    def test_negative_lines_raises_error(self, manager):
        """测试负数行数抛出错误"""
        with pytest.raises(ValueError, match="总行数不能为负数"):
            manager.calculate_segment_ranges(-1)

    def test_no_segmentation_needed(self, manager):
        """测试不需要分段的情况"""
        result = manager.calculate_segment_ranges(5)
        assert result == [(0, 5)]

    def test_basic_ranges(self, manager):
        """测试基本范围计算"""
        # 25行，分段大小10，重叠3
        # segment_0: 0-10
        # segment_1: 7-17 (10-3=7)
        # segment_2: 14-25 (17-3=14, 到结尾)
        result = manager.calculate_segment_ranges(25)

        assert len(result) == 3
        assert result[0] == (0, 10)
        assert result[1] == (7, 17)
        assert result[2] == (14, 25)

    def test_exact_fit(self, manager):
        """测试正好对齐的情况"""
        # 17行，分段大小10，重叠3
        # segment_0: 0-10
        # segment_1: 7-17
        result = manager.calculate_segment_ranges(17)

        assert len(result) == 2
        assert result[0] == (0, 10)
        assert result[1] == (7, 17)


class TestShouldSegment:
    """判断是否需要分段测试"""

    def test_should_not_segment(self):
        """测试不需要分段"""
        config = SubtitleOptimizerConfig(segment_size=100)
        manager = SegmentManager(config)

        assert manager.should_segment(50) is False
        assert manager.should_segment(100) is False

    def test_should_segment(self):
        """测试需要分段"""
        config = SubtitleOptimizerConfig(segment_size=100)
        manager = SegmentManager(config)

        assert manager.should_segment(101) is True
        assert manager.should_segment(200) is True


class TestExtractOverlapRegion:
    """提取重叠区域测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        config = SubtitleOptimizerConfig(overlap_lines=3)
        return SegmentManager(config)

    def test_basic_extraction(self, manager):
        """测试基本提取"""
        prev_lines = [
            OptimizedLine(text="第一行", start=0.0, end=2.0),
            OptimizedLine(text="第二行", start=2.0, end=4.0),
            OptimizedLine(text="第三行", start=4.0, end=6.0),
            OptimizedLine(text="第四行", start=6.0, end=8.0),
            OptimizedLine(text="第五行", start=8.0, end=10.0),
        ]
        curr_lines = [
            OptimizedLine(text="第四行改", start=6.0, end=8.0),
            OptimizedLine(text="第五行改", start=8.0, end=10.0),
            OptimizedLine(text="第六行", start=10.0, end=12.0),
            OptimizedLine(text="第七行", start=12.0, end=14.0),
        ]

        region = manager.extract_overlap_region(prev_lines, curr_lines)

        assert region.start == 4.0  # 前一段倒数第三行的开始时间
        assert region.end == 12.0  # 当前段前三行中最后一行的结束时间（第六行）
        assert len(region.previous_segments) == 3
        assert len(region.next_segments) == 3

    def test_short_lines(self, manager):
        """测试短行列表"""
        prev_lines = [
            OptimizedLine(text="第一行", start=0.0, end=2.0),
            OptimizedLine(text="第二行", start=2.0, end=4.0),
        ]
        curr_lines = [
            OptimizedLine(text="第二行改", start=2.0, end=4.0),
            OptimizedLine(text="第三行", start=4.0, end=6.0),
        ]

        region = manager.extract_overlap_region(prev_lines, curr_lines)

        assert len(region.previous_segments) == 2
        assert len(region.next_segments) == 2

    def test_none_input_raises_error(self, manager):
        """测试None输入抛出错误"""
        lines = [OptimizedLine(text="测试", start=0.0, end=2.0)]

        with pytest.raises(ValueError, match="输入行列表不能为None"):
            manager.extract_overlap_region(None, lines)

        with pytest.raises(ValueError, match="输入行列表不能为None"):
            manager.extract_overlap_region(lines, None)

    def test_custom_overlap_count(self, manager):
        """测试自定义重叠行数"""
        prev_lines = [
            OptimizedLine(text=f"第{i}行", start=float(i) * 2, end=float(i) * 2 + 2)
            for i in range(10)
        ]
        curr_lines = [
            OptimizedLine(text=f"第{i}行改", start=float(i) * 2, end=float(i) * 2 + 2)
            for i in range(8, 18)
        ]

        region = manager.extract_overlap_region(prev_lines, curr_lines, overlap_count=5)

        assert len(region.previous_segments) == 5
        assert len(region.next_segments) == 5


class TestCalculateDiffScore:
    """计算差异度测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        return SegmentManager()

    def test_identical_text(self, manager):
        """测试相同文本"""
        score = manager.calculate_diff_score("这是一段测试文本", "这是一段测试文本")
        assert score == 0.0

    def test_completely_different(self, manager):
        """测试完全不同的文本"""
        score = manager.calculate_diff_score("abcdef", "ghijkl")
        assert score > 0.8  # 应该接近1.0

    def test_partial_difference(self, manager):
        """测试部分差异"""
        score = manager.calculate_diff_score("这是一段测试文本", "这是一段修改文本")
        assert 0.0 < score < 1.0

    def test_whitespace_normalization(self, manager):
        """测试空格规范化"""
        score = manager.calculate_diff_score("这是  一段   测试", "这是一段测试")
        # 空格差异应该被规范化
        assert score < 0.5

    def test_empty_texts(self, manager):
        """测试空文本"""
        assert manager.calculate_diff_score("", "") == 0.0
        assert manager.calculate_diff_score("", "有内容") == 1.0
        assert manager.calculate_diff_score("有内容", "") == 1.0

    def test_none_input_raises_error(self, manager):
        """测试None输入抛出错误"""
        with pytest.raises(ValueError, match="文本不能为None"):
            manager.calculate_diff_score(None, "测试")

        with pytest.raises(ValueError, match="文本不能为None"):
            manager.calculate_diff_score("测试", None)


class TestMergeSegments:
    """合并段结果测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        config = SubtitleOptimizerConfig(overlap_lines=2)
        return SegmentManager(config)

    def test_single_segment(self, manager):
        """测试单分段"""
        lines = [
            OptimizedLine(text="第一行", start=0.0, end=2.0),
            OptimizedLine(text="第二行", start=2.0, end=4.0),
        ]
        result = manager.merge_segments([lines])

        assert len(result) == 2
        assert result[0].text == "第一行"
        assert result[1].text == "第二行"

    def test_empty_result(self, manager):
        """测试空结果"""
        result = manager.merge_segments([])
        assert result == []

    def test_none_input_raises_error(self, manager):
        """测试None输入抛出错误"""
        with pytest.raises(ValueError, match="segment_results不能为None"):
            manager.merge_segments(None)

    def test_two_segments(self, manager):
        """测试两个分段合并"""
        # 分段1: 0-4行，重叠2行
        segment1 = [
            OptimizedLine(text="第0行", start=0.0, end=2.0),
            OptimizedLine(text="第1行", start=2.0, end=4.0),
            OptimizedLine(text="第2行", start=4.0, end=6.0),
            OptimizedLine(text="第3行", start=6.0, end=8.0),
        ]
        # 分段2: 2-6行，重叠2行
        segment2 = [
            OptimizedLine(text="第2行改", start=4.0, end=6.0),
            OptimizedLine(text="第3行改", start=6.0, end=8.0),
            OptimizedLine(text="第4行", start=8.0, end=10.0),
            OptimizedLine(text="第5行", start=10.0, end=12.0),
        ]

        result = manager.merge_segments([segment1, segment2])

        # 应该去掉segment1的最后2行和segment2的前2行（重叠区）
        # 保留: segment1[0:2] + segment2[2:]
        assert len(result) == 4
        assert result[0].text == "第0行"
        assert result[1].text == "第1行"
        assert result[2].text == "第4行"
        assert result[3].text == "第5行"

    def test_three_segments(self, manager):
        """测试三个分段合并"""
        # 分段1: 0-4
        segment1 = [
            OptimizedLine(text=f"第{i}行", start=float(i) * 2, end=float(i) * 2 + 2)
            for i in range(4)
        ]
        # 分段2: 2-6 (重叠2行)
        segment2 = [
            OptimizedLine(text=f"第{i}行", start=float(i) * 2, end=float(i) * 2 + 2)
            for i in range(2, 6)
        ]
        # 分段3: 4-8 (重叠2行)
        segment3 = [
            OptimizedLine(text=f"第{i}行", start=float(i) * 2, end=float(i) * 2 + 2)
            for i in range(4, 8)
        ]

        result = manager.merge_segments([segment1, segment2, segment3])

        # segment1[0:2] + segment2[2:4] + segment3[2:]
        # = [0,1] + [4,5] + [6,7] = 6行
        assert len(result) == 6

    def test_short_segments(self, manager):
        """测试短分段"""
        # 分段很短，小于2*overlap_lines
        segment1 = [
            OptimizedLine(text="第0行", start=0.0, end=2.0),
            OptimizedLine(text="第1行", start=2.0, end=4.0),
        ]
        segment2 = [
            OptimizedLine(text="第2行", start=4.0, end=6.0),
            OptimizedLine(text="第3行", start=6.0, end=8.0),
        ]

        result = manager.merge_segments([segment1, segment2])

        # 短分段应该全部保留
        assert len(result) >= 2


class TestGetOverlapLinesForRetry:
    """获取扩展重叠区测试"""

    @pytest.fixture
    def manager(self):
        """提供默认管理器"""
        config = SubtitleOptimizerConfig(max_overlap_expand=5)
        return SegmentManager(config)

    @pytest.fixture
    def sample_results(self):
        """提供示例结果"""
        return [
            [OptimizedLine(text=f"seg0_{i}", start=float(i), end=float(i) + 1) for i in range(10)],
            [OptimizedLine(text=f"seg1_{i}", start=float(i) + 10, end=float(i) + 11) for i in range(10)],
            [OptimizedLine(text=f"seg2_{i}", start=float(i) + 20, end=float(i) + 21) for i in range(10)],
        ]

    def test_middle_segment(self, manager, sample_results):
        """测试中间分段"""
        result = manager.get_overlap_lines_for_retry(1, sample_results)

        # 应该包含前一分段的尾部、当前分段、后一分段的头部
        # 默认max_overlap_expand=5
        assert len(result) == 20  # 5 + 10 + 5

    def test_first_segment(self, manager, sample_results):
        """测试第一个分段"""
        result = manager.get_overlap_lines_for_retry(0, sample_results)

        # 第一个分段没有前驱
        assert len(result) == 15  # 10 + 5 (后一分段头部)

    def test_last_segment(self, manager, sample_results):
        """测试最后一个分段"""
        result = manager.get_overlap_lines_for_retry(2, sample_results)

        # 最后一个分段没有后继
        assert len(result) == 15  # 5 (前一分段尾部) + 10

    def test_invalid_index_raises_error(self, manager, sample_results):
        """测试无效索引抛出错误"""
        with pytest.raises(IndexError, match="无效的分段索引"):
            manager.get_overlap_lines_for_retry(-1, sample_results)

        with pytest.raises(IndexError, match="无效的分段索引"):
            manager.get_overlap_lines_for_retry(3, sample_results)

    def test_none_input_raises_error(self, manager):
        """测试None输入抛出错误"""
        with pytest.raises(ValueError, match="all_results不能为None"):
            manager.get_overlap_lines_for_retry(0, None)

    def test_custom_expand_count(self, manager, sample_results):
        """测试自定义扩展行数"""
        result = manager.get_overlap_lines_for_retry(1, sample_results, expand_count=3)

        # 3 + 10 + 3 = 16
        assert len(result) == 16

    def test_short_neighbor_segments(self, manager):
        """测试短邻居分段"""
        short_results = [
            [OptimizedLine(text=f"seg0_{i}", start=float(i), end=float(i) + 1) for i in range(3)],
            [OptimizedLine(text=f"seg1_{i}", start=float(i) + 10, end=float(i) + 11) for i in range(3)],
            [OptimizedLine(text=f"seg2_{i}", start=float(i) + 20, end=float(i) + 21) for i in range(3)],
        ]

        result = manager.get_overlap_lines_for_retry(1, short_results)

        # 邻居分段只有3行，应该全部包含
        assert len(result) == 9  # 3 + 3 + 3
