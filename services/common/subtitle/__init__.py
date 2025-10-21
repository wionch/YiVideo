"""
YiVideo 字幕处理模块

提供字幕校正、解析、AI提供商集成等通用字幕处理功能。
"""

# 字幕校正
from .subtitle_correction import SubtitleCorrector

# 字幕解析
from .subtitle_parser import SubtitleEntry, SRTParser, parse_srt_file, write_srt_file

# AI提供商
from .ai_providers import get_ai_provider, AIProviderFactory

# 字幕校正配置
from .subtitle_correction_config import SubtitleCorrectionConfig

__all__ = [
    # 字幕校正
    'SubtitleCorrector',
    # 字幕解析
    'SubtitleEntry',
    'SRTParser',
    'parse_srt_file',
    'write_srt_file',
    # AI提供商
    'get_ai_provider',
    'AIProviderFactory',
    # 配置
    'SubtitleCorrectionConfig',
]
