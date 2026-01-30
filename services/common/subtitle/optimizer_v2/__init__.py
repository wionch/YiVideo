"""
字幕优化器 V2

提供完整的字幕优化流程，包括加载、分段、LLM优化、合并和时间戳重建。
"""

from .config import (
    DebugConfig,
    LLMConfig,
    OptimizerConfigLoader,
    SubtitleOptimizerConfig,
)
from .debug_logger import DebugLogger
from .extractor import SubtitleExtractor
from .llm_optimizer import LLMOptimizer
from .models import (
    OptimizationResult,
    OptimizationStatus,
    OptimizedLine,
    OptimizerConfig,
    OverlapRegion,
    SegmentTask,
    SegmentType,
    SubtitleSegment,
    WordTimestamp,
)
from .optimizer import SubtitleOptimizerV2
from .segment_manager import SegmentManager
from .timestamp_reconstructor import TimestampReconstructor

__all__ = [
    # 主优化器
    "SubtitleOptimizerV2",
    # 配置类
    "SubtitleOptimizerConfig",
    "DebugConfig",
    "LLMConfig",
    "OptimizerConfig",
    "OptimizerConfigLoader",
    # 核心组件
    "SubtitleExtractor",
    "SegmentManager",
    "LLMOptimizer",
    "TimestampReconstructor",
    "DebugLogger",
    # 数据模型
    "OptimizationResult",
    "OptimizationStatus",
    "OptimizedLine",
    "OverlapRegion",
    "SegmentTask",
    "SegmentType",
    "SubtitleSegment",
    "WordTimestamp",
]

__version__ = "2.0.0"
