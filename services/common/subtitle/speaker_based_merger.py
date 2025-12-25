# services/common/subtitle/speaker_based_merger.py
# -*- coding: utf-8 -*-

"""
基于说话人时间区间的字幕合并模块

功能：
1. 将词级时间戳匹配到说话人 segments
2. 计算匹配质量指标
3. 生成基于说话人时间基准的合并结果
"""

from typing import List, Dict, Any
from services.common.subtitle.word_timestamp_utils import (
    flatten_word_timestamps,
    calculate_overlap_ratio
)
from services.common.logger import get_logger

logger = get_logger('speaker_based_merger')


def calculate_match_quality(
    matched_words: List[Dict],
    segment_start: float,
    segment_end: float
) -> Dict[str, Any]:
    """
    计算匹配质量指标

    Args:
        matched_words: 匹配到的词列表
        segment_start: segment 的开始时间
        segment_end: segment 的结束时间

    Returns:
        匹配质量指标字典:
        {
            "matched_words": int,          # 匹配到的词数量
            "total_words_in_range": int,   # 时间范围内的总词数
            "coverage_ratio": float,       # 时间覆盖率
            "partial_overlaps": int,       # 部分重叠的词数量
            "full_matches": int            # 完全包含的词数量
        }
    """
    matched_count = len(matched_words)

    if matched_count == 0:
        return {
            "matched_words": 0,
            "total_words_in_range": 0,
            "coverage_ratio": 0.0,
            "partial_overlaps": 0,
            "full_matches": 0
        }

    # 计算完全匹配和部分重叠的数量
    full_matches = 0
    partial_overlaps = 0

    for word in matched_words:
        word_start = word['start']
        word_end = word['end']

        # 判断是否完全包含
        if word_start >= segment_start and word_end <= segment_end:
            full_matches += 1
        else:
            partial_overlaps += 1

    # 计算时间覆盖率
    # 收集所有匹配词的时间区间
    if matched_words:
        # 计算匹配词覆盖的总时长
        covered_intervals = []
        for word in matched_words:
            # 只计算在 segment 范围内的部分
            word_start = max(word['start'], segment_start)
            word_end = min(word['end'], segment_end)
            if word_start < word_end:
                covered_intervals.append((word_start, word_end))

        # 合并重叠区间
        if covered_intervals:
            covered_intervals.sort()
            merged_intervals = [covered_intervals[0]]

            for start, end in covered_intervals[1:]:
                if start <= merged_intervals[-1][1]:
                    # 合并重叠区间
                    merged_intervals[-1] = (
                        merged_intervals[-1][0],
                        max(merged_intervals[-1][1], end)
                    )
                else:
                    merged_intervals.append((start, end))

            # 计算总覆盖时长
            total_covered = sum(end - start for start, end in merged_intervals)
            segment_duration = segment_end - segment_start

            coverage_ratio = total_covered / segment_duration if segment_duration > 0 else 0.0
        else:
            coverage_ratio = 0.0
    else:
        coverage_ratio = 0.0

    return {
        "matched_words": matched_count,
        "total_words_in_range": matched_count,
        "coverage_ratio": round(coverage_ratio, 4),
        "partial_overlaps": partial_overlaps,
        "full_matches": full_matches
    }


def match_words_to_speaker_segments(
    all_words: List[Dict],
    diarization_segments: List[Dict],
    overlap_threshold: float = 0.5
) -> List[Dict]:
    """
    将词级时间戳匹配到说话人 segments

    Args:
        all_words: 扁平化的词列表（已排序）
        diarization_segments: 说话人 segments 列表
        overlap_threshold: 重叠阈值（默认 0.5）

    Returns:
        合并后的 segments 列表，每个 segment 包含:
        {
            "id": int,
            "start": float,
            "end": float,
            "duration": float,
            "speaker": str,
            "text": str,
            "word_count": int,
            "words": List[Dict],
            "speaker_confidence": float,
            "match_quality": Dict
        }
    """
    merged_segments = []
    word_index = 0  # 当前搜索起始位置
    total_words = len(all_words)

    logger.info(
        f"开始匹配: {len(diarization_segments)} 个说话人片段, "
        f"{total_words} 个词, 重叠阈值={overlap_threshold}"
    )

    for seg_idx, diar_seg in enumerate(diarization_segments):
        diar_start = diar_seg['start']
        diar_end = diar_seg['end']
        speaker = diar_seg.get('speaker', 'SPEAKER_UNKNOWN')
        speaker_confidence = diar_seg.get('speaker_confidence', 1.0)

        matched_words = []

        # 从当前位置开始查找可能重叠的词
        # 优化：跳过已经完全在 segment 之前的词
        while word_index < total_words and all_words[word_index]['end'] < diar_start:
            word_index += 1

        # 从当前位置开始收集重叠的词
        temp_index = word_index
        while temp_index < total_words:
            word = all_words[temp_index]
            word_start = word['start']
            word_end = word['end']

            # 如果词完全在 segment 之后，停止搜索
            if word_start > diar_end:
                break

            # 计算重叠比例
            overlap_ratio = calculate_overlap_ratio(
                word_start, word_end,
                diar_start, diar_end
            )

            # 如果重叠比例 >= 阈值，匹配该词
            if overlap_ratio >= overlap_threshold:
                matched_words.append(word)

            temp_index += 1

        # 拼接文本
        text = ''.join(w['word'] for w in matched_words)

        # 计算匹配质量
        match_quality = calculate_match_quality(
            matched_words,
            diar_start,
            diar_end
        )

        # 构建输出 segment
        merged_seg = {
            'id': seg_idx + 1,
            'start': diar_start,
            'end': diar_end,
            'duration': diar_end - diar_start,
            'speaker': speaker,
            'text': text,
            'word_count': len(matched_words),
            'words': matched_words,
            'speaker_confidence': speaker_confidence,
            'match_quality': match_quality
        }

        merged_segments.append(merged_seg)

    logger.info(
        f"匹配完成: 生成 {len(merged_segments)} 个合并片段, "
        f"平均每片段 {sum(s['word_count'] for s in merged_segments) / len(merged_segments):.1f} 个词"
    )

    return merged_segments


def merge_speaker_based_subtitles(
    transcript_segments: List[Dict],
    diarization_segments: List[Dict],
    overlap_threshold: float = 0.5
) -> List[Dict]:
    """
    基于说话人时间区间合并字幕（主入口函数）

    Args:
        transcript_segments: 转录片段列表（包含词级时间戳）
        diarization_segments: 说话人片段列表
        overlap_threshold: 重叠阈值（默认 0.5）

    Returns:
        合并后的 segments 列表

    Raises:
        ValueError: 如果输入数据无效
    """
    # 验证输入
    if not transcript_segments:
        raise ValueError("转录片段列表不能为空")

    if not diarization_segments:
        raise ValueError("说话人片段列表不能为空")

    # 验证词级时间戳存在性
    has_words = any(seg.get('words') for seg in transcript_segments)
    if not has_words:
        raise ValueError("转录结果不包含词级时间戳，无法执行基于说话人的合并")

    # 扁平化词级时间戳
    logger.info(f"扁平化 {len(transcript_segments)} 个转录片段的词级时间戳")
    all_words = flatten_word_timestamps(transcript_segments)
    logger.info(f"提取到 {len(all_words)} 个词")

    # 执行匹配
    merged_segments = match_words_to_speaker_segments(
        all_words,
        diarization_segments,
        overlap_threshold
    )

    return merged_segments
