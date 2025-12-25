# services/common/subtitle/word_timestamp_utils.py
# -*- coding: utf-8 -*-

"""
词级时间戳工具模块

功能：
1. 扁平化转录片段中的词级时间戳
2. 计算词级时间戳与说话人片段的重叠比例
"""

from typing import List, Dict


def flatten_word_timestamps(transcript_segments: List[Dict]) -> List[Dict]:
    """
    将转录片段的嵌套结构扁平化为单一词列表

    Args:
        transcript_segments: 转录片段列表，每个片段包含 words 数组
            格式: [{
                'start': float,
                'end': float,
                'text': str,
                'speaker': str (可选),
                'words': [{
                    'word': str,
                    'start': float,
                    'end': float,
                    'probability': float (可选)
                }]
            }]

    Returns:
        扁平化的词列表，按 start 时间排序
            格式: [{
                'word': str,
                'start': float,
                'end': float,
                'probability': float,
                'speaker': str (继承自 segment)
            }]
    """
    all_words = []

    for segment in transcript_segments:
        words = segment.get('words', [])
        segment_speaker = segment.get('speaker')

        for word in words:
            word_data = {
                'word': word['word'],
                'start': word['start'],
                'end': word['end'],
                'probability': word.get('probability', 1.0)
            }

            # 继承 segment 的 speaker（如果有）
            if segment_speaker:
                word_data['speaker'] = segment_speaker

            all_words.append(word_data)

    # 按 start 时间排序
    all_words.sort(key=lambda w: w['start'])

    return all_words


def calculate_overlap_ratio(
    word_start: float,
    word_end: float,
    segment_start: float,
    segment_end: float
) -> float:
    """
    计算词级时间戳与 segment 的重叠比例

    Args:
        word_start: 词的开始时间
        word_end: 词的结束时间
        segment_start: segment 的开始时间
        segment_end: segment 的结束时间

    Returns:
        重叠比例 (0.0 ~ 1.0)
        - 0.0: 无重叠
        - 1.0: 完全包含
        - 0.0 ~ 1.0: 部分重叠

    Examples:
        >>> # 完全包含
        >>> calculate_overlap_ratio(12.0, 13.0, 11.0, 14.0)
        1.0

        >>> # 部分重叠
        >>> calculate_overlap_ratio(12.0, 14.0, 13.0, 15.0)
        0.5

        >>> # 无重叠
        >>> calculate_overlap_ratio(10.0, 11.0, 12.0, 13.0)
        0.0
    """
    # 计算重叠区间
    overlap_start = max(word_start, segment_start)
    overlap_end = min(word_end, segment_end)

    # 无重叠
    if overlap_start >= overlap_end:
        return 0.0

    # 计算重叠时长
    overlap_duration = overlap_end - overlap_start

    # 计算词的总时长
    word_duration = word_end - word_start

    # 避免除零
    if word_duration <= 0:
        return 0.0

    # 计算重叠比例
    ratio = overlap_duration / word_duration

    # 确保在 [0.0, 1.0] 范围内
    return min(max(ratio, 0.0), 1.0)
