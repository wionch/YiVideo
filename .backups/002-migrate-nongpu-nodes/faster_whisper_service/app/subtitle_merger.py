# services/workers/faster_whisper_service/app/subtitle_merger.py
# -*- coding: utf-8 -*-

"""
字幕合并模块
将转录结果与说话人时间段合并，生成带说话人标签的字幕

功能：
1. SubtitleMerger: 片段级合并器（无词级时间戳）
2. WordLevelMerger: 词级精确合并器（需词级时间戳）

本模块不依赖 pyannote.audio，仅处理字幕合并逻辑。
说话人分离功能由 pyannote_audio_service 提供。
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from services.common.logger import get_logger

logger = get_logger('subtitle_merger')


class SubtitleMerger:
    """
    字幕片段级合并器
    适用于：没有词级时间戳的转录结果

    核心功能：
    - 将转录片段与说话人时间段合并
    - 自动检测说话人边界
    - 分割跨边界片段
    - 计算说话人匹配置信度
    """

    def __init__(self,
                 min_duration: float = 0.5,
                 max_duration: float = 10.0,
                 max_gap: float = 0.5):
        """
        初始化合并器

        Args:
            min_duration: 最小字幕时长（秒）
            max_duration: 最大字幕时长（秒）
            max_gap: 最大时间间隔（秒），用于匹配说话人
        """
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.max_gap = max_gap
        logger.info(f"SubtitleMerger 初始化: min={min_duration}s, max={max_duration}s, gap={max_gap}s")

    def merge(self,
             transcript_segments: List[Dict],
             speaker_segments: List[Dict]) -> List[Dict]:
        """
        合并转录结果与说话人时间段

        Args:
            transcript_segments: 转录片段列表
                格式: [{
                    'start': float,
                    'end': float,
                    'text': str,
                    'words': List[Dict] (可选)
                }]
            speaker_segments: 说话人时间段列表
                格式: [{
                    'start': float,
                    'end': float,
                    'speaker': str
                }]

        Returns:
            List[Dict]: 合并后的字幕片段
                格式: [{
                    'start': float,
                    'end': float,
                    'text': str,
                    'speaker': str,
                    'speaker_confidence': float
                }]
        """
        merged_segments = []

        # 如果diarization_segments为空，使用默认说话人标签
        if not speaker_segments:
            logger.warning("说话人分离结果为空，使用默认说话人标签")
            for trans_seg in transcript_segments:
                merged_segment = trans_seg.copy()
                merged_segment['speaker'] = 'SPEAKER_00'
                merged_segment['speaker_confidence'] = 0.5
                merged_segments.append(merged_segment)
            return merged_segments

        # 获取所有可用的说话人标签
        available_speakers = set(seg['speaker'] for seg in speaker_segments)
        logger.debug(f"可用的说话人标签: {sorted(available_speakers)}")

        # 检测说话人切换的关键时间点
        speaker_boundaries = self._detect_speaker_boundaries(speaker_segments)
        logger.debug(f"检测到 {len(speaker_boundaries)} 个说话人边界")

        # 为每个转录片段找到最匹配的说话人
        for i, trans_seg in enumerate(transcript_segments):
            trans_start = trans_seg['start']
            trans_end = trans_seg['end']
            trans_center = (trans_start + trans_end) / 2

            # 检查是否跨越了说话人边界
            crosses_boundary = self._crosses_speaker_boundary(trans_start, trans_end, speaker_boundaries)

            if crosses_boundary:
                # 如果跨越说话人边界，强制分割片段
                split_segments = self._split_by_boundaries(trans_seg, speaker_boundaries, speaker_segments)
                for split_seg in split_segments:
                    speaker_info = self._find_best_speaker(split_seg, speaker_segments)
                    split_seg['speaker'] = speaker_info['speaker']
                    split_seg['speaker_confidence'] = speaker_info['confidence']
                    merged_segments.append(split_seg)
                continue

            # 查找最佳说话人
            best_speaker_info = self._find_best_speaker(trans_seg, speaker_segments)

            # 创建合并后的片段
            merged_segment = trans_seg.copy()
            merged_segment['speaker'] = best_speaker_info['speaker']
            merged_segment['speaker_confidence'] = best_speaker_info['confidence']

            merged_segments.append(merged_segment)

        # 统计最终结果
        final_speakers = set(seg['speaker'] for seg in merged_segments)
        unknown_count = sum(1 for seg in merged_segments if seg['speaker'] == 'UNKNOWN')

        logger.info(f"说话人合并完成:")
        logger.info(f"  最终说话人: {sorted(final_speakers)}")
        logger.info(f"  总片段数: {len(merged_segments)}")
        if unknown_count > 0:
            logger.warning(f"  UNKNOWN片段数: {unknown_count} ({unknown_count/len(merged_segments)*100:.1f}%)")
        else:
            logger.info(f"  ✅ 无UNKNOWN片段")

        return merged_segments

    def _detect_speaker_boundaries(self, speaker_segments: List[Dict]) -> List[float]:
        """
        检测说话人切换的关键时间点

        Args:
            speaker_segments: 说话人时间段列表

        Returns:
            List[float]: 说话人边界时间点列表
        """
        boundaries = []

        for i in range(len(speaker_segments) - 1):
            current = speaker_segments[i]
            next_seg = speaker_segments[i + 1]

            # 如果说话人发生变化，记录边界时间
            if current['speaker'] != next_seg['speaker']:
                # 使用两个片段的中点作为边界
                boundary_time = (current['end'] + next_seg['start']) / 2
                boundaries.append(boundary_time)

        return sorted(boundaries)

    def _crosses_speaker_boundary(self,
                                  start: float,
                                  end: float,
                                  boundaries: List[float]) -> bool:
        """
        检查时间段是否跨越了说话人边界

        Args:
            start: 片段开始时间
            end: 片段结束时间
            boundaries: 说话人边界时间点列表

        Returns:
            bool: 是否跨越边界
        """
        for boundary in boundaries:
            if start < boundary < end:
                return True
        return False

    def _split_by_boundaries(self,
                            segment: Dict,
                            boundaries: List[float],
                            speaker_segments: List[Dict]) -> List[Dict]:
        """
        按说话人边界分割片段

        Args:
            segment: 原始转录片段
            boundaries: 说话人边界时间点列表
            speaker_segments: 说话人时间段列表（用于分配说话人）

        Returns:
            List[Dict]: 分割后的子片段列表
        """
        split_segments = []
        segment_start = segment['start']
        segment_end = segment['end']

        # 找到在片段范围内的所有边界
        relevant_boundaries = [b for b in boundaries if segment_start < b < segment_end]

        if not relevant_boundaries:
            return [segment]

        # 按边界排序
        relevant_boundaries.sort()

        # 创建分割点
        split_points = [segment_start] + relevant_boundaries + [segment_end]

        # 创建子片段
        for i in range(len(split_points) - 1):
            sub_start = split_points[i]
            sub_end = split_points[i + 1]

            # 只有当子片段长度足够时才创建
            if sub_end - sub_start >= 0.1:  # 最小0.1秒
                sub_segment = segment.copy()
                sub_segment['start'] = sub_start
                sub_segment['end'] = sub_end
                sub_segment['duration'] = sub_end - sub_start

                # 分割文本（如果有词级时间戳）
                if 'words' in segment and segment['words']:
                    sub_segment['words'] = [
                        word for word in segment['words']
                        if word['start'] >= sub_start and word['end'] <= sub_end
                    ]

                    # 重新计算文本
                    sub_segment['text'] = ' '.join(word['word'] for word in sub_segment['words'])

                split_segments.append(sub_segment)

        return split_segments

    def _find_best_speaker(self,
                          segment: Dict,
                          speaker_segments: List[Dict]) -> Dict:
        """
        为片段找到最佳说话人匹配

        Args:
            segment: 转录片段
            speaker_segments: 说话人时间段列表

        Returns:
            Dict: {'speaker': str, 'confidence': float}
        """
        seg_start = segment['start']
        seg_end = segment['end']
        seg_center = (seg_start + seg_end) / 2

        best_speaker = None
        best_score = -1
        best_overlap_ratio = 0

        for diar_seg in speaker_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']

            # 检查是否有时间重叠或接近
            if (seg_start <= diar_end and seg_end >= diar_start):
                # 计算重叠程度
                overlap_start = max(seg_start, diar_start)
                overlap_end = min(seg_end, diar_end)
                overlap_duration = max(0, overlap_end - overlap_start)

                # 计算重叠比例
                seg_duration = seg_end - seg_start
                overlap_ratio = overlap_duration / seg_duration if seg_duration > 0 else 0

                if overlap_ratio > best_score:
                    best_score = overlap_ratio
                    best_speaker = diar_seg['speaker']
                    best_overlap_ratio = overlap_ratio
            elif abs(seg_center - (diar_start + diar_end) / 2) <= self.max_gap:
                # 如果中心时间接近，也考虑匹配
                distance = abs(seg_center - (diar_start + diar_end) / 2)
                proximity_score = max(0, 1.0 - distance / self.max_gap)

                if proximity_score > best_score:
                    best_score = proximity_score
                    best_speaker = diar_seg['speaker']
                    best_overlap_ratio = 0

        # 确定置信度
        if best_speaker and best_score > 0:
            if best_overlap_ratio > 0:
                confidence = min(best_overlap_ratio, 1.0)
            else:
                confidence = best_score
        else:
            # 使用默认说话人
            best_speaker = 'SPEAKER_00'
            confidence = 0.3

        return {
            'speaker': best_speaker,
            'confidence': confidence
        }


class WordLevelMerger:
    """
    词级时间戳合并器
    适用于：有词级时间戳的转录结果（faster-whisper）

    核心功能：
    1. 基于词的中心时间点精确匹配说话人
    2. 按说话人自动分组生成字幕片段
    3. 智能分割过长片段
    """

    def __init__(self,
                 speaker_segments: List[Dict],
                 min_duration: float = 0.5,
                 max_duration: float = 10.0):
        """
        初始化词级合并器

        Args:
            speaker_segments: 说话人时间段列表
                格式: [{'start': float, 'end': float, 'speaker': str}]
            min_duration: 最小字幕时长（秒）
            max_duration: 最大字幕时长（秒）
        """
        self.speaker_segments = speaker_segments
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.speaker_timeline = self._build_speaker_timeline()
        logger.debug(f"WordLevelMerger初始化完成: {len(speaker_segments)}个说话人片段, min_duration={min_duration}s, max_duration={max_duration}s")

    def _build_speaker_timeline(self) -> List[Dict]:
        """
        构建说话人时间线
        为每个时间点确定对应的说话人

        Returns:
            List[Dict]: 时间线数据，按时间排序
        """
        timeline = []

        for seg in self.speaker_segments:
            timeline.append({
                'start': seg['start'],
                'end': seg['end'],
                'speaker': seg['speaker']
            })

        # 按开始时间排序
        timeline.sort(key=lambda x: x['start'])
        return timeline

    def merge(self, transcript_segments: List[Dict]) -> List[Dict]:
        """
        使用词级时间戳进行精确合并

        Args:
            transcript_segments: 包含 words 字段的转录片段
                格式: [{
                    'start': float,
                    'end': float,
                    'text': str,
                    'words': [
                        {'start': float, 'end': float, 'word': str}
                    ]
                }]

        Returns:
            List[Dict]: 增强的字幕片段，包含精确的说话人信息
        """
        enhanced_segments = []
        speaker_stats = set()  # 用于统计实际使用的说话人

        logger.debug(f"开始生成增强字幕，输入片段数: {len(transcript_segments)}")
        logger.debug(f"可用说话人时间段: {len(self.speaker_timeline)}")

        # 显示说话人时间段详情（前5个）
        for i, seg in enumerate(self.speaker_timeline[:5]):
            logger.debug(f"  说话人时间段 {i+1}: {seg['start']:.2f}s-{seg['end']:.2f}s, 说话人: {seg['speaker']}")

        for i, trans_seg in enumerate(transcript_segments):
            if 'words' not in trans_seg or not trans_seg['words']:
                # 没有词级信息，使用原有逻辑
                enhanced_seg = trans_seg.copy()
                # 使用片段中心时间匹配说话人
                center_time = (trans_seg['start'] + trans_seg['end']) / 2
                speaker = self._find_speaker_at_time(center_time)
                enhanced_seg['speaker'] = speaker
                enhanced_seg['speaker_confidence'] = 0.7
                enhanced_segments.append(enhanced_seg)
                speaker_stats.add(speaker)

                # 调试信息（前3个片段）
                if i < 3:
                    logger.debug(f"片段 {i+1} (无词级信息): {trans_seg['start']:.2f}s-{trans_seg['end']:.2f}s -> 匹配到说话人: {speaker}")
            else:
                # 有词级信息，使用精确匹配
                matched_words = self._match_words_to_speakers(trans_seg['words'])

                # 按说话人分组词
                word_groups = self._group_words_by_speaker_in_segment(matched_words)

                for group_words in word_groups:
                    if group_words:
                        enhanced_seg = self._create_segment_from_words(
                            group_words, group_words[0]['speaker']
                        )
                        enhanced_seg['speaker_confidence'] = 1.0  # 词级匹配，高置信度
                        enhanced_segments.append(enhanced_seg)
                        speaker_stats.add(group_words[0]['speaker'])

                # 调试信息（前3个有词级信息的片段）
                if i < 3:
                    word_speakers = set(word['speaker'] for word in matched_words)
                    logger.debug(f"片段 {i+1} (有词级信息): {trans_seg['start']:.2f}s-{trans_seg['end']:.2f}s -> 匹配到说话人: {sorted(word_speakers)}")

        # 统计最终使用的说话人
        logger.info(f"增强字幕生成完成: {len(enhanced_segments)} 个片段, 使用的说话人: {sorted(speaker_stats)}")

        # 检查是否有说话人丢失
        original_speakers = set(seg['speaker'] for seg in self.speaker_timeline)
        missing_speakers = original_speakers - speaker_stats
        if missing_speakers:
            logger.warning(f"⚠️  检测到说话人丢失: {sorted(missing_speakers)} (原始: {sorted(original_speakers)}, 使用: {sorted(speaker_stats)})")
            # 输出丢失说话人的时间段信息
            for speaker in missing_speakers:
                lost_segments = [seg for seg in self.speaker_timeline if seg['speaker'] == speaker]
                logger.warning(f"  丢失说话人 {speaker} 的时间段: {[(seg['start'], seg['end']) for seg in lost_segments]}")
        else:
            logger.info(f"✅ 所有说话人都被正确匹配")

        return enhanced_segments

    def _match_words_to_speakers(self, word_list: List[Dict]) -> List[Dict]:
        """
        将词列表匹配到对应的说话人

        Args:
            word_list: 词级时间戳列表，每个词包含start, end, word等信息

        Returns:
            List[Dict]: 带有说话人信息的词列表
        """
        matched_words = []

        for word_info in word_list:
            word_start = word_info['start']
            word_end = word_info['end']
            word_center = (word_start + word_end) / 2

            # 找到对应的说话人
            speaker = self._find_speaker_at_time(word_center)

            matched_word = word_info.copy()
            matched_word['speaker'] = speaker
            matched_words.append(matched_word)

        return matched_words

    def _find_speaker_at_time(self, timestamp: float) -> str:
        """
        查找指定时间点的说话人
        优化版本：改进距离计算逻辑，避免偏向长时间跨度的说话人

        Args:
            timestamp: 时间戳（秒）

        Returns:
            str: 说话人标签
        """
        # 首先检查是否在某个说话人时间段内
        for time_seg in self.speaker_timeline:
            if time_seg['start'] <= timestamp <= time_seg['end']:
                return time_seg['speaker']

        # 如果没有找到精确匹配，使用改进的匹配逻辑
        closest_speaker = None
        min_distance = float('inf')

        # 找到时间戳前后的说话人时间段，优先考虑时间接近度而不是跨度大小
        for time_seg in self.speaker_timeline:
            # 计算到时间段的距离
            if timestamp < time_seg['start']:
                # 时间戳在时间段之前，计算到开始时间的距离
                distance = time_seg['start'] - timestamp
            elif timestamp > time_seg['end']:
                # 时间戳在时间段之后，计算到结束时间的距离
                distance = timestamp - time_seg['end']
            else:
                # 在时间段内，距离为0（这种情况前面已经处理了）
                distance = 0

            # 只有当距离更小时才更新
            if distance < min_distance:
                min_distance = distance
                closest_speaker = time_seg['speaker']
            # 如果距离相等，优先选择时间上更接近的说话人
            elif distance == min_distance and distance > 0:
                # 计算时间戳到时间段中心的距离作为额外的判断依据
                current_center = (time_seg['start'] + time_seg['end']) / 2
                center_distance = abs(timestamp - current_center)

                # 找到当前closest_speaker的时间段中心距离
                for prev_seg in self.speaker_timeline:
                    if prev_seg['speaker'] == closest_speaker:
                        prev_center = (prev_seg['start'] + prev_seg['end']) / 2
                        prev_center_distance = abs(timestamp - prev_center)
                        break
                else:
                    prev_center_distance = float('inf')

                # 如果当前时间段的中心更接近，则更新
                if center_distance < prev_center_distance:
                    closest_speaker = time_seg['speaker']

        # 如果仍然没有找到，返回默认说话人
        if closest_speaker is None:
            logger.warning(f"无法找到时间戳 {timestamp:.2f}s 对应的说话人，使用默认说话人 SPEAKER_00")
            return 'SPEAKER_00'

        return closest_speaker

    def _group_words_by_speaker_in_segment(self, words: List[Dict]) -> List[List[Dict]]:
        """
        在单个转录片段内按说话人分组词

        Args:
            words: 已匹配说话人的词列表

        Returns:
            List[List[Dict]]: 按说话人分组的词列表
        """
        if not words:
            return []

        groups = []
        current_group = []
        current_speaker = words[0]['speaker']

        for word in words:
            if word['speaker'] != current_speaker:
                # 说话人变化，保存当前组
                if current_group:
                    groups.append(current_group)
                current_group = [word]
                current_speaker = word['speaker']
            else:
                current_group.append(word)

        # 保存最后一组
        if current_group:
            groups.append(current_group)

        return groups

    def _create_segment_from_words(self, words: List[Dict], speaker: str) -> Dict:
        """
        从词列表创建字幕片段

        Args:
            words: 词列表
            speaker: 说话人标签

        Returns:
            Dict: 字幕片段
        """
        if not words:
            return {}

        start_time = words[0]['start']
        end_time = words[-1]['end']
        text = ''.join(word['word'] for word in words)

        return {
            'start': start_time,
            'end': end_time,
            'duration': end_time - start_time,
            'text': text,
            'speaker': speaker,
            'word_count': len(words),
            'words': words
        }


# ========== 工具函数 ==========

def create_subtitle_merger(config: Optional[Dict] = None) -> SubtitleMerger:
    """
    创建片段级合并器的工厂函数

    Args:
        config: 配置参数
            - min_subtitle_duration: 最小字幕时长（默认 0.5s）
            - max_subtitle_duration: 最大字幕时长（默认 10.0s）
            - max_gap: 最大时间间隔（默认 0.5s）

    Returns:
        SubtitleMerger: 合并器实例
    """
    if config is None:
        config = {}

    return SubtitleMerger(
        min_duration=config.get('min_subtitle_duration', 0.5),
        max_duration=config.get('max_subtitle_duration', 10.0),
        max_gap=config.get('max_gap', 0.5)
    )


def create_word_level_merger(speaker_segments: List[Dict],
                            config: Optional[Dict] = None) -> WordLevelMerger:
    """
    创建词级合并器的工厂函数

    Args:
        speaker_segments: 说话人时间段列表
        config: 配置参数

    Returns:
        WordLevelMerger: 合并器实例
    """
    if not speaker_segments:
        logger.warning("说话人分离结果为空，使用默认匹配器")
        default_segment = {
            'start': 0.0,
            'end': 999999.0,
            'speaker': 'SPEAKER_00'
        }
        speaker_segments = [default_segment]

    if config is None:
        config = {}

    return WordLevelMerger(
        speaker_segments=speaker_segments,
        min_duration=config.get('min_subtitle_duration', 0.5),
        max_duration=config.get('max_subtitle_duration', 10.0)
    )


def validate_speaker_segments(speaker_segments: List[Dict]) -> bool:
    """
    验证说话人时间段数据的有效性

    Args:
        speaker_segments: 说话人时间段列表

    Returns:
        bool: 是否有效
    """
    if not speaker_segments:
        return False

    for seg in speaker_segments:
        if not all(key in seg for key in ['start', 'end', 'speaker']):
            return False
        if seg['end'] <= seg['start']:
            return False

    return True
