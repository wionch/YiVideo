# services/workers/faster_whisper_service/app/tts_merger.py
# -*- coding: utf-8 -*-

"""
为TTS参考音准备字幕片段的合并与分割工具。
"""

from typing import List, Dict, Any
from services.common.logger import get_logger
from collections import defaultdict

logger = get_logger('tts_merger')

class TtsMerger:
    """
    根据TTS参考音的要求，对字幕片段进行智能合并与分割。
    """
    def __init__(self, config: Dict[str, Any]):
        """
        初始化合并器。

        Args:
            config (Dict[str, Any]): 节点的配置参数。
        """
        self.min_duration = config.get('min_duration', 3.0)
        self.max_duration = config.get('max_duration', 10.0)
        self.max_gap = config.get('max_gap', 1.0)
        self.split_on_punctuation = config.get('split_on_punctuation', False)
        self.PUNCTUATION = set("。！？.”")
        logger.info(f"TtsMerger 初始化: min_duration={self.min_duration}, max_duration={self.max_duration}, max_gap={self.max_gap}, split_on_punctuation={self.split_on_punctuation}")

    def merge_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        主入口函数，执行完整的合并与优化流程。

        Args:
            segments (List[Dict]): 原始字幕片段列表。

        Returns:
            List[Dict]: 处理后的字幕片段列表。
        """
        if not segments:
            return []

        # 1. 按说话人对所有片段进行分组
        speaker_groups = self._group_by_speaker(segments)
        
        final_segments = []
        for speaker, speaker_segments in speaker_groups.items():
            logger.debug(f"正在处理说话人 '{speaker}' 的 {len(speaker_segments)} 个片段...")
            # 2. 对每个说话人的片段执行初步合并
            preliminary_merged = self._preliminary_merge(speaker_segments)
            
            # 3. 对合并后的片段进行优化调整
            optimized_segments = self._optimize_segments(preliminary_merged)
            final_segments.extend(optimized_segments)
            
        # 4. 按开始时间对最终结果排序
        final_segments.sort(key=lambda x: x['start'])

        # 5. 为所有最终片段重新分配唯一的、从1开始的ID
        for i, segment in enumerate(final_segments):
            segment['id'] = i + 1
            
        logger.info(f"合并与优化完成，共生成 {len(final_segments)} 个片段。")
        return final_segments

    def _group_by_speaker(self, segments: List[Dict]) -> Dict[str, List[Dict]]:
        """按说话人对片段进行分组。"""
        groups = defaultdict(list)
        for segment in segments:
            speaker = segment.get('speaker', 'SPEAKER_UNKNOWN')
            groups[speaker].append(segment)
        return groups

    def _preliminary_merge(self, segments: List[Dict]) -> List[Dict]:
        """阶段一：初步迭代合并。"""
        if not segments:
            return []

        merged_groups = []
        current_group = [segments[0]]

        for i in range(1, len(segments)):
            current_segment = segments[i]
            last_segment_in_group = current_group[-1]

            # 条件检查
            gap = current_segment['start'] - last_segment_in_group['end']
            
            # 计算当前组的总时长
            group_start = current_group[0]['start']
            group_end = last_segment_in_group['end']
            current_group_duration = group_end - group_start
            
            new_total_duration = (current_segment['end'] - group_start)

            # 检查标点
            ends_with_punctuation = False
            if self.split_on_punctuation:
                if last_segment_in_group['text'].strip() and last_segment_in_group['text'].strip()[-1] in self.PUNCTUATION:
                    ends_with_punctuation = True

            # 决策
            if gap <= self.max_gap and new_total_duration <= self.max_duration and not ends_with_punctuation:
                current_group.append(current_segment)
            else:
                merged_groups.append(self._finalize_group(current_group))
                current_group = [current_segment]
        
        # 处理最后一组
        if current_group:
            merged_groups.append(self._finalize_group(current_group))

        return merged_groups

    def _finalize_group(self, group: List[Dict]) -> Dict:
        """将一个片段组固化成一个合并后的片段。"""
        if not group:
            return {}
        
        start_time = group[0]['start']
        end_time = group[-1]['end']
        text = " ".join(s['text'].strip() for s in group)
        
        # 合并 words 列表
        words = []
        for s in group:
            if 'words' in s:
                words.extend(s['words'])

        return {
            'start': start_time,
            'end': end_time,
            'duration': end_time - start_time,
            'text': text,
            'speaker': group[0].get('speaker', 'SPEAKER_UNKNOWN'),
            'words': words
        }

    def _optimize_segments(self, segments: List[Dict]) -> List[Dict]:
        """阶段二：优化调整，处理过长和过短的片段。"""
        optimized = []
        for segment in segments:
            if segment['duration'] > self.max_duration:
                optimized.extend(self._split_long_segment(segment))
            else:
                optimized.append(segment)
        
        # 注意：二次合并逻辑较为复杂，此处暂时简化为直接过滤，后续可根据需求增强
        final_segments = self._handle_short_segments(optimized)
        return final_segments

    def _split_long_segment(self, segment: Dict) -> List[Dict]:
        """智能分割过长片段，利用词级时间戳和标点符号。"""
        logger.warning(f"检测到过长片段 (时长: {segment['duration']:.2f}s > {self.max_duration:.2f}s)，将进行智能分割。")
        
        words = segment.get('words')
        if not words:
            # 如果没有词级时间戳，回退到暴力分割
            return self._split_long_segment_fallback(segment)

        split_segments = []
        current_split_words = []
        
        for i, word in enumerate(words):
            current_split_words.append(word)
            
            current_duration = word['end'] - current_split_words[0]['start']
            
            # 寻找分割点
            # 条件1: 当前时长已接近max_duration
            # 条件2: 遇到句末标点
            # 条件3: 是最后一个词
            is_last_word = (i == len(words) - 1)
            is_punctuation_stop = word['word'].strip() and word['word'].strip()[-1] in self.PUNCTUATION
            is_duration_exceeded = current_duration >= self.max_duration

            if is_duration_exceeded or is_punctuation_stop or is_last_word:
                if current_split_words:
                    new_seg = self._finalize_group(current_split_words)
                    # 只有当新片段时长有效时才添加
                    if new_seg['duration'] > 0.1:
                        split_segments.append(new_seg)
                    current_split_words = []

        # 如果循环结束后仍有剩余的词，处理最后一部分
        if current_split_words:
            new_seg = self._finalize_group(current_split_words)
            if new_seg['duration'] > 0.1:
                split_segments.append(new_seg)

        return split_segments

    def _split_long_segment_fallback(self, segment: Dict) -> List[Dict]:
        """没有词级时间戳时的暴力分割方法。"""
        num_splits = int(segment['duration'] // self.max_duration) + 1
        split_duration = segment['duration'] / num_splits
        
        split_segments = []
        current_start = segment['start']
        
        for i in range(num_splits):
            split_end = min(current_start + split_duration, segment['end'])
            if split_end > current_start:
                new_seg = segment.copy()
                new_seg['start'] = current_start
                new_seg['end'] = split_end
                new_seg['duration'] = split_end - current_start
                new_seg['text'] = f"[SPLIT {i+1}/{num_splits}] {segment['text']}"
                new_seg['words'] = [] # 清空words，因为无法准确分割
                split_segments.append(new_seg)
            current_start = split_end
            
        return split_segments

    def _handle_short_segments(self, segments: List[Dict]) -> List[Dict]:
        """处理过短的片段，尝试与相邻片段进行二次合并。"""
        if not segments:
            return []

        # 创建一个可变列表用于操作
        mutable_segments = list(segments)
        i = 0
        while i < len(mutable_segments):
            current_seg = mutable_segments[i]
            
            if current_seg['duration'] < self.min_duration:
                # 尝试与后一个片段合并
                if i + 1 < len(mutable_segments):
                    next_seg = mutable_segments[i+1]
                    # 检查说话人是否一致，以及合并后是否超长
                    if current_seg['speaker'] == next_seg['speaker']:
                        merged_duration = (next_seg['end'] - current_seg['start'])
                        if merged_duration <= self.max_duration:
                            logger.debug(f"二次合并：将短片段 {i} 与后一个片段 {i+1} 合并。")
                            merged_seg = self._finalize_group([current_seg, next_seg])
                            mutable_segments[i] = merged_seg
                            del mutable_segments[i+1]
                            # 合并后，停在当前位置，再次检查新合并的片段是否仍然过短
                            continue
                
                # 如果无法向后合并，尝试与前一个片段合并
                if i > 0:
                    prev_seg = mutable_segments[i-1]
                    if current_seg['speaker'] == prev_seg['speaker']:
                        merged_duration = (current_seg['end'] - prev_seg['start'])
                        if merged_duration <= self.max_duration:
                            logger.debug(f"二次合并：将短片段 {i} 与前一个片段 {i-1} 合并。")
                            merged_seg = self._finalize_group([prev_seg, current_seg])
                            mutable_segments[i-1] = merged_seg
                            del mutable_segments[i]
                            # 合并后，回退一个索引，以便再次检查新合并的片段
                            i -= 1
                            continue
            
            i += 1

        # 最后，过滤掉仍然过短的片段
        final_segments = [seg for seg in mutable_segments if seg['duration'] >= self.min_duration]
        
        if len(final_segments) < len(mutable_segments):
            logger.info(f"经过二次合并后，仍过滤掉 {len(mutable_segments) - len(final_segments)} 个无法合并的短片段。")

        return final_segments
