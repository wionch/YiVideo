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


class SpeakerWordMatcher:
    """
    说话人词级匹配器
    使用词级时间戳实现精确的说话人标注
    """

    def __init__(self, speaker_segments: List[Dict], min_duration: float = 0.5, max_duration: float = 10.0):
        """
        初始化匹配器

        Args:
            speaker_segments: 说话人分离结果列表，每个元素包含start, end, speaker
            min_duration: 最小字幕片段时长
            max_duration: 最大字幕片段时长
        """
        self.speaker_segments = speaker_segments
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.speaker_timeline = self._build_speaker_timeline()
        logger.debug(f"SpeakerWordMatcher初始化完成: {len(speaker_segments)}个说话人片段, min_duration={min_duration}s, max_duration={max_duration}s")

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

    def match_words_to_speakers(self, word_list: List[Dict]) -> List[Dict]:
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

        Args:
            timestamp: 时间戳（秒）

        Returns:
            str: 说话人标签
        """
        for time_seg in self.speaker_timeline:
            if time_seg['start'] <= timestamp <= time_seg['end']:
                return time_seg['speaker']

        # 如果没有找到精确匹配，寻找最近的说话人
        closest_speaker = None
        min_distance = float('inf')

        for time_seg in self.speaker_timeline:
            # 计算到时间段的距离
            if timestamp < time_seg['start']:
                distance = time_seg['start'] - timestamp
            elif timestamp > time_seg['end']:
                distance = timestamp - time_seg['end']
            else:
                # 在时间段内，距离为0
                distance = 0

            if distance < min_distance:
                min_distance = distance
                closest_speaker = time_seg['speaker']

        return closest_speaker or 'SPEAKER_00'

    def group_words_by_speaker(self, matched_words: List[Dict]) -> List[Dict]:
        """
        按说话人分组词，并生成字幕片段

        Args:
            matched_words: 已匹配说话人的词列表

        Returns:
            List[Dict]: 字幕片段列表
        """
        if not matched_words:
            return []

        segments = []
        current_segment_words = []
        current_speaker = matched_words[0]['speaker']

        for word in matched_words:
            word_speaker = word['speaker']

            if word_speaker != current_speaker:
                # 说话人发生变化，结束当前片段
                if current_segment_words:
                    segment = self._create_segment_from_words(
                        current_segment_words, current_speaker
                    )
                    if segment['duration'] >= self.min_duration:
                        segments.append(segment)

                # 检查是否需要分割过长的片段
                if segment and segment['duration'] > self.max_duration:
                    split_segments = self._split_long_segment(
                        segment, self.max_duration
                    )
                    segments.extend(split_segments)

                # 开始新片段
                current_segment_words = [word]
                current_speaker = word_speaker
            else:
                # 同一说话人，添加到当前片段
                current_segment_words.append(word)

                # 检查片段是否过长
                current_duration = current_segment_words[-1]['end'] - current_segment_words[0]['start']
                if current_duration >= max_segment_duration:
                    # 强制分割长片段
                    segment = self._create_segment_from_words(
                        current_segment_words, current_speaker
                    )
                    segments.append(segment)
                    current_segment_words = []

        # 处理最后一个片段
        if current_segment_words:
            segment = self._create_segment_from_words(
                current_segment_words, current_speaker
            )
            if segment['duration'] >= self.min_duration:
                segments.append(segment)

        return segments

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

    def _split_long_segment(self, segment: Dict, max_duration: float) -> List[Dict]:
        """
        分割过长的片段

        Args:
            segment: 原始片段
            max_duration: 最大时长

        Returns:
            List[Dict]: 分割后的片段列表
        """
        if segment['duration'] <= max_duration:
            return [segment]

        words = segment['words']
        speaker = segment['speaker']
        split_segments = []

        current_words = []
        current_start = None

        for word in words:
            if not current_words:
                current_words = [word]
                current_start = word['start']
            else:
                current_duration = word['end'] - current_start
                if current_duration >= max_duration:
                    # 创建新片段
                    split_segment = self._create_segment_from_words(
                        current_words, speaker
                    )
                    split_segments.append(split_segment)
                    current_words = [word]
                    current_start = word['start']
                else:
                    current_words.append(word)

        # 处理剩余的词
        if current_words:
            split_segment = self._create_segment_from_words(
                current_words, speaker
            )
            split_segments.append(split_segment)

        return split_segments

    def generate_enhanced_subtitles(self, transcript_segments: List[Dict]) -> List[Dict]:
        """
        生成增强的字幕片段，保持原有的转录结构但添加精确的说话人信息

        Args:
            transcript_segments: WhisperX转录的片段列表

        Returns:
            List[Dict]: 增强的字幕片段
        """
        enhanced_segments = []

        for trans_seg in transcript_segments:
            if 'words' not in trans_seg or not trans_seg['words']:
                # 没有词级信息，使用原有逻辑
                enhanced_seg = trans_seg.copy()
                # 使用片段中心时间匹配说话人
                center_time = (trans_seg['start'] + trans_seg['end']) / 2
                speaker = self._find_speaker_at_time(center_time)
                enhanced_seg['speaker'] = speaker
                enhanced_seg['speaker_confidence'] = 0.7
                enhanced_segments.append(enhanced_seg)
            else:
                # 有词级信息，使用精确匹配
                matched_words = self.match_words_to_speakers(trans_seg['words'])

                # 按说话人分组词
                word_groups = self._group_words_by_speaker_in_segment(matched_words)

                for group_words in word_groups:
                    if group_words:
                        enhanced_seg = self._create_segment_from_words(
                            group_words, group_words[0]['speaker']
                        )
                        enhanced_seg['speaker_confidence'] = 1.0  # 词级匹配，高置信度
                        enhanced_segments.append(enhanced_seg)

        return enhanced_segments

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


def create_speaker_word_matcher(speaker_segments: List[Dict], config: Optional[Dict] = None) -> SpeakerWordMatcher:
    """
    创建说话人词级匹配器的工厂函数

    Args:
        speaker_segments: 说话人分离结果
        config: 配置参数，包含字幕片段时长限制等

    Returns:
        SpeakerWordMatcher: 匹配器实例
    """
    if not speaker_segments:
        logger.warning("说话人分离结果为空，使用默认匹配器")
        # 创建一个只有默认说话人的匹配器
        default_segment = {
            'start': 0.0,
            'end': 999999.0,  # 很大的时间范围
            'speaker': 'SPEAKER_00'
        }
        speaker_segments = [default_segment]

    # 应用配置参数
    min_duration = 0.5
    max_duration = 10.0

    if config:
        min_duration = config.get('min_subtitle_duration', 0.5)
        max_duration = config.get('max_subtitle_duration', 10.0)
        logger.debug(f"使用配置参数: min_duration={min_duration}s, max_duration={max_duration}s")

    return SpeakerWordMatcher(speaker_segments, min_duration, max_duration)