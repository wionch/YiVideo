# services/workers/whisperx_service/app/speaker_word_matcher.py
# -*- coding: utf-8 -*-

"""
基于词级时间戳的说话人精准匹配算法
通过词级时间戳实现精确的说话人标注，避免长片段跨越多个说话人区域的问题
"""

import logging
from typing import List, Dict, Tuple, Any, Optional
from collections import defaultdict

from services.common.logger import get_logger

logger = get_logger('speaker_word_matcher')


def convert_annotation_to_segments(annotation) -> List[Dict]:
    """
    将pyannote的DiarizeOutput或Annotation对象转换为说话人片段列表

    Args:
        annotation: pyannote的DiarizeOutput或Annotation对象

    Returns:
        List[Dict]: 说话人片段列表，每个片段包含start, end, speaker信息
    """
    segments = []

    try:
        logger.debug(f"convert_annotation_to_segments: 输入类型 {type(annotation)}")

        # 检查是否是DiarizeOutput类型
        if hasattr(annotation, 'speaker_diarization'):
            # DiarizeOutput对象，使用speaker_diarization属性
            speaker_annotation = annotation.speaker_diarization
            logger.debug("检测到DiarizeOutput对象，使用speaker_diarization属性")
        else:
            # 直接是Annotation对象
            speaker_annotation = annotation
            logger.debug("检测到Annotation对象，直接使用")

        # 遍历说话人分离结果
        segment_count = 0
        for turn, speaker in speaker_annotation:
            segments.append({
                'start': float(turn.start),
                'end': float(turn.end),
                'duration': float(turn.end - turn.start),
                'speaker': str(speaker)
            })
            segment_count += 1

            # 调试信息（只显示前5个）
            if segment_count <= 5:
                logger.debug(f"说话人片段 {segment_count}: {turn.start:.2f}s-{turn.end:.2f}s, 说话人: {speaker}")

        # 按开始时间排序
        segments.sort(key=lambda x: x['start'])
        logger.info(f"成功提取到 {len(segments)} 个说话人片段")

        # 显示说话人统计
        speakers = set(seg['speaker'] for seg in segments)
        logger.info(f"识别到的说话人: {sorted(speakers)}")

        return segments

    except Exception as e:
        logger.error(f"转换annotation到字典列表失败: {e}")
        import traceback
        traceback.print_exc()

        # 返回默认的模拟数据
        logger.warning("返回默认说话人片段")
        return [{
            'start': 0.0,
            'end': 300.0,
            'duration': 300.0,
            'speaker': 'SPEAKER_00'
        }]


# 从公共模块导入 WordLevelMerger
from services.common.subtitle.subtitle_merger import WordLevelMerger, create_word_level_merger


def create_speaker_word_matcher(speaker_segments: List[Dict], config: Optional[Dict] = None) -> WordLevelMerger:
    """
    创建说话人词级匹配器的工厂函数 (重构后)
    现在这个函数是一个包装器，调用公共模块的工厂函数。

    Args:
        speaker_segments: 说话人分离结果
        config: 配置参数，包含字幕片段时长限制等

    Returns:
        WordLevelMerger: 公共模块中的合并器实例
    """
    # 直接调用公共模块的工厂函数
    return create_word_level_merger(speaker_segments, config)
