"""
字幕优化器V2核心数据模型单元测试
"""

import pytest
from services.common.subtitle.optimizer_v2.models import (
    WordTimestamp,
    SubtitleSegment,
    OptimizedLine,
    SegmentTask,
    OptimizationResult,
    OverlapRegion,
    OptimizerConfig,
    OptimizationStatus,
    SegmentType,
)


class TestWordTimestamp:
    """词级时间戳测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        word = WordTimestamp(word="你好", start=1.0, end=1.5, probability=0.95)
        assert word.word == "你好"
        assert word.start == 1.0
        assert word.end == 1.5
        assert word.probability == 0.95

    def test_duration_property(self):
        """测试持续时间属性"""
        word = WordTimestamp(word="test", start=1.0, end=2.5)
        assert word.duration == 1.5

    def test_negative_start_raises_error(self):
        """测试负数开始时间抛出错误"""
        with pytest.raises(ValueError, match="开始时间不能为负数"):
            WordTimestamp(word="test", start=-1.0, end=1.0)

    def test_end_before_start_raises_error(self):
        """测试结束时间小于开始时间抛出错误"""
        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            WordTimestamp(word="test", start=2.0, end=1.0)

    def test_invalid_probability_raises_error(self):
        """测试无效置信度抛出错误"""
        with pytest.raises(ValueError, match="置信度必须在0-1之间"):
            WordTimestamp(word="test", start=1.0, end=2.0, probability=1.5)

        with pytest.raises(ValueError, match="置信度必须在0-1之间"):
            WordTimestamp(word="test", start=1.0, end=2.0, probability=-0.1)

    def test_overlaps_with(self):
        """测试重叠检测"""
        word1 = WordTimestamp(word="a", start=1.0, end=2.0)
        word2 = WordTimestamp(word="b", start=1.5, end=2.5)
        word3 = WordTimestamp(word="c", start=2.5, end=3.0)

        assert word1.overlaps_with(word2) is True
        assert word1.overlaps_with(word3) is False


class TestSubtitleSegment:
    """字幕段测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        segment = SubtitleSegment(
            id=1,
            start=1.0,
            end=5.0,
            text="这是一段测试字幕"
        )
        assert segment.id == 1
        assert segment.start == 1.0
        assert segment.end == 5.0
        assert segment.text == "这是一段测试字幕"

    def test_creation_with_words(self):
        """测试带词级时间戳的创建"""
        words = [
            WordTimestamp(word="这是", start=1.0, end=1.5),
            WordTimestamp(word="一段", start=1.5, end=2.0),
            WordTimestamp(word="测试", start=2.0, end=2.5),
            WordTimestamp(word="字幕", start=2.5, end=3.0),
        ]
        segment = SubtitleSegment(
            id=1,
            start=1.0,
            end=3.0,
            text="这是一段测试字幕",
            words=words
        )
        assert len(segment.words) == 4
        assert segment.words[0].word == "这是"

    def test_duration_property(self):
        """测试持续时间属性"""
        segment = SubtitleSegment(id=1, start=1.0, end=5.0, text="test")
        assert segment.duration == 4.0

    def test_text_length_property(self):
        """测试文本长度属性"""
        segment = SubtitleSegment(id=1, start=1.0, end=5.0, text="你好世界")
        assert segment.text_length == 4

    def test_negative_id_raises_error(self):
        """测试负数ID抛出错误"""
        with pytest.raises(ValueError, match="字幕段ID不能为负数"):
            SubtitleSegment(id=-1, start=1.0, end=5.0, text="test")

    def test_negative_start_raises_error(self):
        """测试负数开始时间抛出错误"""
        with pytest.raises(ValueError, match="开始时间不能为负数"):
            SubtitleSegment(id=1, start=-1.0, end=5.0, text="test")

    def test_end_before_start_raises_error(self):
        """测试结束时间小于开始时间抛出错误"""
        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            SubtitleSegment(id=1, start=5.0, end=1.0, text="test")

    def test_empty_text_raises_error(self):
        """测试空文本抛出错误"""
        with pytest.raises(ValueError, match="字幕文本不能为空"):
            SubtitleSegment(id=1, start=1.0, end=5.0, text="")

    def test_overlaps_with(self):
        """测试重叠检测"""
        seg1 = SubtitleSegment(id=1, start=1.0, end=5.0, text="第一段")
        seg2 = SubtitleSegment(id=2, start=4.0, end=8.0, text="第二段")
        seg3 = SubtitleSegment(id=3, start=6.0, end=10.0, text="第三段")

        assert seg1.overlaps_with(seg2) is True
        assert seg1.overlaps_with(seg3) is False

    def test_get_words_in_range(self):
        """测试获取时间范围内的词"""
        words = [
            WordTimestamp(word="这是", start=1.0, end=1.5),
            WordTimestamp(word="一段", start=1.5, end=2.0),
            WordTimestamp(word="测试", start=2.0, end=2.5),
            WordTimestamp(word="字幕", start=2.5, end=3.0),
        ]
        segment = SubtitleSegment(
            id=1,
            start=1.0,
            end=3.0,
            text="这是一段测试字幕",
            words=words
        )

        result = segment.get_words_in_range(1.5, 2.5)
        assert len(result) == 2
        assert result[0].word == "一段"
        assert result[1].word == "测试"

    def test_get_words_in_range_no_words(self):
        """测试无词级时间戳时返回空列表"""
        segment = SubtitleSegment(id=1, start=1.0, end=3.0, text="测试")
        result = segment.get_words_in_range(1.0, 2.0)
        assert result == []


class TestOptimizedLine:
    """优化后字幕行测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        line = OptimizedLine(
            text="优化后的字幕",
            start=1.0,
            end=5.0
        )
        assert line.text == "优化后的字幕"
        assert line.start == 1.0
        assert line.end == 5.0
        assert line.is_modified is True
        assert line.original_text is None

    def test_creation_with_original(self):
        """测试带原始文本的创建"""
        line = OptimizedLine(
            text="优化后的字幕",
            start=1.0,
            end=5.0,
            is_modified=True,
            original_text="原始字幕"
        )
        assert line.original_text == "原始字幕"
        assert line.is_modified is True

    def test_duration_property(self):
        """测试持续时间属性"""
        line = OptimizedLine(text="test", start=1.0, end=4.0)
        assert line.duration == 3.0

    def test_text_length_property(self):
        """测试文本长度属性"""
        line = OptimizedLine(text="你好世界", start=1.0, end=4.0)
        assert line.text_length == 4

    def test_negative_start_raises_error(self):
        """测试负数开始时间抛出错误"""
        with pytest.raises(ValueError, match="开始时间不能为负数"):
            OptimizedLine(text="test", start=-1.0, end=5.0)

    def test_end_before_start_raises_error(self):
        """测试结束时间小于开始时间抛出错误"""
        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            OptimizedLine(text="test", start=5.0, end=1.0)

    def test_to_dict(self):
        """测试转换为字典"""
        line = OptimizedLine(
            text="优化后的字幕",
            start=1.0,
            end=5.0,
            is_modified=True,
            original_text="原始字幕"
        )
        result = line.to_dict()
        assert result["text"] == "优化后的字幕"
        assert result["start"] == 1.0
        assert result["end"] == 5.0
        assert result["is_modified"] is True
        assert result["original_text"] == "原始字幕"


class TestSegmentTask:
    """分段处理任务测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        segments = [
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
            SubtitleSegment(id=2, start=3.0, end=5.0, text="第二段"),
        ]
        task = SegmentTask(task_id="task-001", segments=segments)
        assert task.task_id == "task-001"
        assert len(task.segments) == 2
        assert task.segment_type == SegmentType.NORMAL

    def test_creation_with_context(self):
        """测试带上下文的创建"""
        segments = [SubtitleSegment(id=1, start=1.0, end=3.0, text="测试")]
        task = SegmentTask(
            task_id="task-001",
            segments=segments,
            context_before="前文内容",
            context_after="后文内容",
            segment_type=SegmentType.OVERLAP_START
        )
        assert task.context_before == "前文内容"
        assert task.context_after == "后文内容"
        assert task.segment_type == SegmentType.OVERLAP_START

    def test_empty_task_id_raises_error(self):
        """测试空任务ID抛出错误"""
        with pytest.raises(ValueError, match="任务ID不能为空"):
            SegmentTask(task_id="", segments=[])

    def test_empty_segments_raises_error(self):
        """测试空段落列表抛出错误"""
        with pytest.raises(ValueError, match="任务必须包含至少一个字幕段"):
            SegmentTask(task_id="task-001", segments=[])

    def test_start_time_property(self):
        """测试开始时间属性"""
        segments = [
            SubtitleSegment(id=2, start=3.0, end=5.0, text="第二段"),
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
        ]
        task = SegmentTask(task_id="task-001", segments=segments)
        assert task.start_time == 1.0

    def test_end_time_property(self):
        """测试结束时间属性"""
        segments = [
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
            SubtitleSegment(id=2, start=3.0, end=6.0, text="第二段"),
        ]
        task = SegmentTask(task_id="task-001", segments=segments)
        assert task.end_time == 6.0

    def test_total_text_property(self):
        """测试总文本属性"""
        segments = [
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
            SubtitleSegment(id=2, start=3.0, end=5.0, text="第二段"),
        ]
        task = SegmentTask(task_id="task-001", segments=segments)
        assert task.total_text == "第一段 第二段"

    def test_total_duration_property(self):
        """测试总持续时间属性"""
        segments = [
            SubtitleSegment(id=1, start=1.0, end=3.0, text="第一段"),
            SubtitleSegment(id=2, start=3.0, end=6.0, text="第二段"),
        ]
        task = SegmentTask(task_id="task-001", segments=segments)
        assert task.total_duration == 5.0


class TestOptimizationResult:
    """优化结果测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED
        )
        assert result.task_id == "task-001"
        assert result.status == OptimizationStatus.COMPLETED
        assert result.optimized_lines == []
        assert result.error_message is None

    def test_creation_with_lines(self):
        """测试带优化行的创建"""
        lines = [
            OptimizedLine(text="第一行", start=1.0, end=3.0),
            OptimizedLine(text="第二行", start=3.0, end=5.0),
        ]
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=lines,
            metadata={"total_chars": 100}
        )
        assert len(result.optimized_lines) == 2
        assert result.metadata["total_chars"] == 100

    def test_failed_status_requires_error_message(self):
        """测试失败状态需要错误信息"""
        with pytest.raises(ValueError, match="失败状态必须提供错误信息"):
            OptimizationResult(
                task_id="task-001",
                status=OptimizationStatus.FAILED
            )

    def test_failed_status_with_error_message(self):
        """测试失败状态带错误信息"""
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.FAILED,
            error_message="网络连接失败"
        )
        assert result.error_message == "网络连接失败"

    def test_empty_task_id_raises_error(self):
        """测试空任务ID抛出错误"""
        with pytest.raises(ValueError, match="任务ID不能为空"):
            OptimizationResult(task_id="", status=OptimizationStatus.PENDING)

    def test_is_success_property(self):
        """测试成功状态属性"""
        success_result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED
        )
        failed_result = OptimizationResult(
            task_id="task-002",
            status=OptimizationStatus.FAILED,
            error_message="错误"
        )
        assert success_result.is_success is True
        assert failed_result.is_success is False

    def test_total_lines_property(self):
        """测试总行数属性"""
        lines = [
            OptimizedLine(text="第一行", start=1.0, end=3.0),
            OptimizedLine(text="第二行", start=3.0, end=5.0),
        ]
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=lines
        )
        assert result.total_lines == 2

    def test_total_duration_property(self):
        """测试总持续时间属性"""
        lines = [
            OptimizedLine(text="第一行", start=1.0, end=3.0),
            OptimizedLine(text="第二行", start=3.0, end=6.0),
        ]
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=lines
        )
        assert result.total_duration == 5.0

    def test_total_duration_empty_lines(self):
        """测试空行列表时总持续时间为0"""
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=[]
        )
        assert result.total_duration == 0.0

    def test_to_dict(self):
        """测试转换为字典"""
        lines = [OptimizedLine(text="测试", start=1.0, end=3.0)]
        result = OptimizationResult(
            task_id="task-001",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=lines,
            metadata={"key": "value"}
        )
        result_dict = result.to_dict()
        assert result_dict["task_id"] == "task-001"
        assert result_dict["status"] == "completed"
        assert len(result_dict["optimized_lines"]) == 1
        assert result_dict["metadata"]["key"] == "value"


class TestOverlapRegion:
    """重叠区域测试"""

    def test_valid_creation(self):
        """测试有效创建"""
        region = OverlapRegion(start=1.0, end=3.0)
        assert region.start == 1.0
        assert region.end == 3.0
        assert region.previous_segments == []
        assert region.next_segments == []

    def test_creation_with_segments(self):
        """测试带字幕段的创建"""
        prev_segments = [SubtitleSegment(id=1, start=0.5, end=2.0, text="前一段")]
        next_segments = [SubtitleSegment(id=2, start=2.5, end=4.0, text="后一段")]
        region = OverlapRegion(
            start=1.0,
            end=3.0,
            previous_segments=prev_segments,
            next_segments=next_segments
        )
        assert len(region.previous_segments) == 1
        assert len(region.next_segments) == 1

    def test_duration_property(self):
        """测试持续时间属性"""
        region = OverlapRegion(start=1.0, end=4.0)
        assert region.duration == 3.0

    def test_negative_start_raises_error(self):
        """测试负数开始时间抛出错误"""
        with pytest.raises(ValueError, match="开始时间不能为负数"):
            OverlapRegion(start=-1.0, end=3.0)

    def test_end_before_start_raises_error(self):
        """测试结束时间小于等于开始时间抛出错误"""
        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            OverlapRegion(start=3.0, end=1.0)

        with pytest.raises(ValueError, match="结束时间必须大于开始时间"):
            OverlapRegion(start=3.0, end=3.0)

    def test_contains_time(self):
        """测试时间包含检测"""
        region = OverlapRegion(start=1.0, end=3.0)
        assert region.contains_time(1.0) is True
        assert region.contains_time(2.0) is True
        assert region.contains_time(3.0) is True
        assert region.contains_time(0.5) is False
        assert region.contains_time(3.5) is False


class TestOptimizerConfig:
    """优化器配置测试"""

    def test_default_values(self):
        """测试默认值"""
        config = OptimizerConfig()
        assert config.max_chars_per_line == 40
        assert config.max_lines_per_segment == 2
        assert config.min_duration == 1.0
        assert config.max_duration == 7.0
        assert config.preserve_punctuation is True
        assert config.enable_overlap is True
        assert config.overlap_duration == 2.0
        assert config.llm_timeout == 60
        assert config.max_retry_attempts == 3

    def test_custom_values(self):
        """测试自定义值"""
        config = OptimizerConfig(
            max_chars_per_line=50,
            max_lines_per_segment=3,
            min_duration=0.5,
            max_duration=10.0,
            preserve_punctuation=False,
            enable_overlap=False,
            overlap_duration=1.0,
            llm_timeout=120,
            max_retry_attempts=5
        )
        assert config.max_chars_per_line == 50
        assert config.max_lines_per_segment == 3
        assert config.min_duration == 0.5
        assert config.max_duration == 10.0
        assert config.preserve_punctuation is False
        assert config.enable_overlap is False
        assert config.overlap_duration == 1.0
        assert config.llm_timeout == 120
        assert config.max_retry_attempts == 5

    def test_invalid_max_chars_per_line(self):
        """测试无效每行最大字符数"""
        with pytest.raises(ValueError, match="每行最大字符数必须大于0"):
            OptimizerConfig(max_chars_per_line=0)

        with pytest.raises(ValueError, match="每行最大字符数必须大于0"):
            OptimizerConfig(max_chars_per_line=-1)

    def test_invalid_max_lines_per_segment(self):
        """测试无效每段最大行数"""
        with pytest.raises(ValueError, match="每个段落最大行数必须大于0"):
            OptimizerConfig(max_lines_per_segment=0)

    def test_invalid_min_duration(self):
        """测试无效最小持续时间"""
        with pytest.raises(ValueError, match="最小持续时间必须大于0"):
            OptimizerConfig(min_duration=0)

    def test_invalid_max_duration(self):
        """测试无效最大持续时间"""
        with pytest.raises(ValueError, match="最大持续时间必须大于最小持续时间"):
            OptimizerConfig(min_duration=5.0, max_duration=3.0)

        with pytest.raises(ValueError, match="最大持续时间必须大于最小持续时间"):
            OptimizerConfig(min_duration=5.0, max_duration=5.0)

    def test_invalid_overlap_duration(self):
        """测试无效重叠持续时间"""
        with pytest.raises(ValueError, match="重叠持续时间必须大于0"):
            OptimizerConfig(enable_overlap=True, overlap_duration=0)

    def test_invalid_llm_timeout(self):
        """测试无效LLM超时时间"""
        with pytest.raises(ValueError, match="LLM超时时间必须大于0"):
            OptimizerConfig(llm_timeout=0)

    def test_invalid_max_retry_attempts(self):
        """测试无效最大重试次数"""
        with pytest.raises(ValueError, match="最大重试次数不能为负数"):
            OptimizerConfig(max_retry_attempts=-1)

    def test_to_dict(self):
        """测试转换为字典"""
        config = OptimizerConfig(max_chars_per_line=50)
        result = config.to_dict()
        assert result["max_chars_per_line"] == 50
        assert result["max_lines_per_segment"] == 2
        assert result["min_duration"] == 1.0

    def test_from_dict(self):
        """测试从字典创建"""
        config_dict = {
            "max_chars_per_line": 50,
            "max_lines_per_segment": 3,
            "min_duration": 0.5,
            "max_duration": 10.0,
        }
        config = OptimizerConfig.from_dict(config_dict)
        assert config.max_chars_per_line == 50
        assert config.max_lines_per_segment == 3
        assert config.min_duration == 0.5
        assert config.max_duration == 10.0
        # 未指定的使用默认值
        assert config.preserve_punctuation is True
        assert config.llm_timeout == 60

    def test_from_dict_empty(self):
        """测试从空字典创建使用默认值"""
        config = OptimizerConfig.from_dict({})
        assert config.max_chars_per_line == 40
        assert config.max_lines_per_segment == 2
