"""
字幕优化器V2核心数据模型

定义字幕优化流程中使用的所有数据结构，包括词级时间戳、字幕段、
优化结果等核心概念。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class OptimizationStatus(str, Enum):
    """优化状态枚举"""
    PENDING = "pending"           # 待处理
    PROCESSING = "processing"     # 处理中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    SKIPPED = "skipped"           # 已跳过


class SegmentType(str, Enum):
    """分段类型枚举"""
    NORMAL = "normal"             # 普通段落
    OVERLAP_START = "overlap_start"  # 重叠开始
    OVERLAP_END = "overlap_end"      # 重叠结束
    OVERLAP_MIDDLE = "overlap_middle"  # 重叠中间


@dataclass
class WordTimestamp:
    """
    词级时间戳

    表示单个词语的时间位置和识别置信度。

    Attributes:
        word: 词语内容
        start: 开始时间（秒）
        end: 结束时间（秒）
        probability: 识别置信度（0-1）
    """
    word: str
    start: float
    end: float
    probability: float = 1.0

    def __post_init__(self):
        """验证时间戳有效性"""
        if self.start < 0:
            raise ValueError(f"开始时间不能为负数: {self.start}")
        if self.end < self.start:
            raise ValueError(f"结束时间必须大于开始时间: end={self.end}, start={self.start}")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"置信度必须在0-1之间: {self.probability}")

    @property
    def duration(self) -> float:
        """词语持续时间"""
        return self.end - self.start

    def overlaps_with(self, other: 'WordTimestamp') -> bool:
        """检查是否与另一个词时间戳重叠"""
        return not (self.end <= other.start or self.start >= other.end)


@dataclass
class SubtitleSegment:
    """
    字幕段

    表示一个完整的字幕段落，包含时间范围、文本内容和词级时间戳。

    Attributes:
        id: 字幕段唯一标识
        start: 开始时间（秒）
        end: 结束时间（秒）
        text: 字幕文本
        words: 词级时间戳列表（可选）
    """
    id: int
    start: float
    end: float
    text: str
    words: Optional[List[WordTimestamp]] = None

    def __post_init__(self):
        """验证字幕段有效性"""
        if self.id < 0:
            raise ValueError(f"字幕段ID不能为负数: {self.id}")
        if self.start < 0:
            raise ValueError(f"开始时间不能为负数: {self.start}")
        if self.end < self.start:
            raise ValueError(f"结束时间必须大于开始时间: end={self.end}, start={self.start}")
        if not self.text:
            raise ValueError("字幕文本不能为空")

    @property
    def duration(self) -> float:
        """字幕段持续时间"""
        return self.end - self.start

    @property
    def text_length(self) -> int:
        """文本长度（字符数）"""
        return len(self.text)

    def overlaps_with(self, other: 'SubtitleSegment') -> bool:
        """检查是否与另一个字幕段重叠"""
        return not (self.end <= other.start or self.start >= other.end)

    def get_words_in_range(self, start_time: float, end_time: float) -> List[WordTimestamp]:
        """
        获取指定时间范围内的词

        Args:
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）

        Returns:
            在指定时间范围内的词列表
        """
        if self.words is None:
            return []
        return [
            word for word in self.words
            if word.start >= start_time and word.end <= end_time
        ]


@dataclass
class OptimizedLine:
    """
    优化后的字幕行

    表示经过LLM优化后的单行字幕内容。

    Attributes:
        text: 优化后的文本内容
        start: 开始时间（秒）
        end: 结束时间（秒）
        is_modified: 是否被修改过
        original_text: 原始文本（用于对比）
    """
    text: str
    start: float
    end: float
    is_modified: bool = True
    original_text: Optional[str] = None

    def __post_init__(self):
        """验证时间戳有效性"""
        if self.start < 0:
            raise ValueError(f"开始时间不能为负数: {self.start}")
        if self.end < self.start:
            raise ValueError(f"结束时间必须大于开始时间: end={self.end}, start={self.start}")

    @property
    def duration(self) -> float:
        """行持续时间"""
        return self.end - self.start

    @property
    def text_length(self) -> int:
        """文本长度（字符数）"""
        return len(self.text)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "is_modified": self.is_modified,
            "original_text": self.original_text,
        }


@dataclass
class SegmentTask:
    """
    分段处理任务

    表示需要提交给LLM处理的字幕分段任务。

    Attributes:
        task_id: 任务唯一标识
        segments: 包含的字幕段列表
        context_before: 前文内容（用于上下文理解）
        context_after: 后文内容（用于上下文理解）
        segment_type: 分段类型
        overlap_regions: 重叠区域列表
    """
    task_id: str
    segments: List[SubtitleSegment]
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    segment_type: SegmentType = SegmentType.NORMAL
    overlap_regions: List['OverlapRegion'] = field(default_factory=list)

    def __post_init__(self):
        """验证任务有效性"""
        if not self.task_id:
            raise ValueError("任务ID不能为空")
        if not self.segments:
            raise ValueError("任务必须包含至少一个字幕段")

    @property
    def start_time(self) -> float:
        """任务开始时间（第一个段落的开始时间）"""
        return min(seg.start for seg in self.segments)

    @property
    def end_time(self) -> float:
        """任务结束时间（最后一个段落的结束时间）"""
        return max(seg.end for seg in self.segments)

    @property
    def total_text(self) -> str:
        """所有段落的合并文本"""
        return " ".join(seg.text for seg in self.segments)

    @property
    def total_duration(self) -> float:
        """任务总持续时间"""
        return self.end_time - self.start_time


@dataclass
class OptimizationResult:
    """
    优化结果

    表示字幕优化任务的完整结果。

    Attributes:
        task_id: 任务唯一标识
        status: 优化状态
        optimized_lines: 优化后的字幕行列表
        error_message: 错误信息（如果失败）
        metadata: 元数据信息
    """
    task_id: str
    status: OptimizationStatus
    optimized_lines: List[OptimizedLine] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证结果有效性"""
        if not self.task_id:
            raise ValueError("任务ID不能为空")
        if self.status == OptimizationStatus.FAILED and not self.error_message:
            raise ValueError("失败状态必须提供错误信息")

    @property
    def is_success(self) -> bool:
        """是否成功完成"""
        return self.status == OptimizationStatus.COMPLETED

    @property
    def total_lines(self) -> int:
        """优化后的总行数"""
        return len(self.optimized_lines)

    @property
    def total_duration(self) -> float:
        """优化后内容的总持续时间"""
        if not self.optimized_lines:
            return 0.0
        return self.optimized_lines[-1].end - self.optimized_lines[0].start

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "optimized_lines": [line.to_dict() for line in self.optimized_lines],
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class OverlapRegion:
    """
    重叠区域

    表示两个相邻分段之间的重叠区域，用于确保分段边界的平滑过渡。

    Attributes:
        start: 重叠开始时间（秒）
        end: 重叠结束时间（秒）
        previous_segments: 前一分段的字幕段列表
        next_segments: 后一分段的字幕段列表
    """
    start: float
    end: float
    previous_segments: List[SubtitleSegment] = field(default_factory=list)
    next_segments: List[SubtitleSegment] = field(default_factory=list)

    def __post_init__(self):
        """验证重叠区域有效性"""
        if self.start < 0:
            raise ValueError(f"开始时间不能为负数: {self.start}")
        if self.end <= self.start:
            raise ValueError(f"结束时间必须大于开始时间: end={self.end}, start={self.start}")

    @property
    def duration(self) -> float:
        """重叠区域持续时间"""
        return self.end - self.start

    def contains_time(self, time: float) -> bool:
        """检查指定时间是否在重叠区域内"""
        return self.start <= time <= self.end


@dataclass
class OptimizerConfig:
    """
    优化器配置

    字幕优化器的配置参数。

    Attributes:
        max_chars_per_line: 每行最大字符数
        max_lines_per_segment: 每个段落最大行数
        min_duration: 最小持续时间（秒）
        max_duration: 最大持续时间（秒）
        preserve_punctuation: 是否保留标点符号
        enable_overlap: 是否启用分段重叠
        overlap_duration: 重叠持续时间（秒）
        llm_timeout: LLM请求超时时间（秒）
        max_retry_attempts: 最大重试次数
    """
    max_chars_per_line: int = 40
    max_lines_per_segment: int = 2
    min_duration: float = 1.0
    max_duration: float = 7.0
    preserve_punctuation: bool = True
    enable_overlap: bool = True
    overlap_duration: float = 2.0
    llm_timeout: int = 60
    max_retry_attempts: int = 3

    def __post_init__(self):
        """验证配置有效性"""
        if self.max_chars_per_line <= 0:
            raise ValueError(f"每行最大字符数必须大于0: {self.max_chars_per_line}")
        if self.max_lines_per_segment <= 0:
            raise ValueError(f"每个段落最大行数必须大于0: {self.max_lines_per_segment}")
        if self.min_duration <= 0:
            raise ValueError(f"最小持续时间必须大于0: {self.min_duration}")
        if self.max_duration <= self.min_duration:
            raise ValueError(f"最大持续时间必须大于最小持续时间: max={self.max_duration}, min={self.min_duration}")
        if self.enable_overlap and self.overlap_duration <= 0:
            raise ValueError(f"重叠持续时间必须大于0: {self.overlap_duration}")
        if self.llm_timeout <= 0:
            raise ValueError(f"LLM超时时间必须大于0: {self.llm_timeout}")
        if self.max_retry_attempts < 0:
            raise ValueError(f"最大重试次数不能为负数: {self.max_retry_attempts}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "max_chars_per_line": self.max_chars_per_line,
            "max_lines_per_segment": self.max_lines_per_segment,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "preserve_punctuation": self.preserve_punctuation,
            "enable_overlap": self.enable_overlap,
            "overlap_duration": self.overlap_duration,
            "llm_timeout": self.llm_timeout,
            "max_retry_attempts": self.max_retry_attempts,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'OptimizerConfig':
        """从字典创建配置"""
        return cls(
            max_chars_per_line=config_dict.get("max_chars_per_line", 40),
            max_lines_per_segment=config_dict.get("max_lines_per_segment", 2),
            min_duration=config_dict.get("min_duration", 1.0),
            max_duration=config_dict.get("max_duration", 7.0),
            preserve_punctuation=config_dict.get("preserve_punctuation", True),
            enable_overlap=config_dict.get("enable_overlap", True),
            overlap_duration=config_dict.get("overlap_duration", 2.0),
            llm_timeout=config_dict.get("llm_timeout", 60),
            max_retry_attempts=config_dict.get("max_retry_attempts", 3),
        )
