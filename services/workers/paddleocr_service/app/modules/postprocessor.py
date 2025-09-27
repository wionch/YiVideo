# services/workers/paddleocr_service/app/modules/postprocessor.py
# 字幕后处理模块 - 支持关键帧驱动和全帧处理两种模式
import numpy as np

from services.common.logger import get_logger

logger = get_logger('postprocessor')
import difflib  # 用于文本相似度比较
import logging
import re
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

# 配置日志输出格式
# 日志已统一管理，使用 services.common.logger

class SubtitlePostprocessor:
    """
    [V3] 字幕后处理器 - 支持关键帧驱动模式和全帧处理模式
    
    功能特性:
    - 关键帧模式: 基于预处理的segments进行高效处理
    - 全帧模式: 从原始帧数据构建完整的字幕时间线  
    - 自动去重和合并相似字幕
    - 可配置的最小持续时间过滤
    """
    def __init__(self, config):
        """
        初始化字幕后处理器
        
        Args:
            config: 配置字典，包含postprocessor相关设置
        """
        self.config = config.get('postprocessor', {})
        # 最小字幕持续时间阈值(秒)，过短的字幕将被过滤
        self.min_duration_seconds = self.config.get('min_duration_seconds', 0.2)
        # [FIX] 将相似度阈值设为可配置，并降低默认值以容忍OCR波动
        self.similarity_threshold = self.config.get('similarity_threshold', 0.6)
        logger.info(f"Subtitle Postprocessor loaded (V3 - Multi-Mode). Thresholds: min_duration={self.min_duration_seconds}s, similarity={self.similarity_threshold}")

    def format_from_keyframes(self, segments: List[Dict], ocr_results: Dict[int, Tuple[str, Any]], fps: float) -> List[Dict[str, Any]]:
        """
        关键帧驱动模式的后处理函数
        
        该函数处理已经预分段的数据，每个segment包含关键帧信息和时间范围。
        主要用于优化性能的场景，通过关键帧采样减少处理量。
        
        Args:
            segments: 预处理的字幕段列表，每个段包含start_time, end_time, key_frame等信息
            ocr_results: OCR识别结果字典 {frame_idx: (text, bbox)}
            fps: 视频帧率，用于时间计算
            
        Returns:
            List[Dict]: 格式化的字幕列表，包含id, startTime, endTime, text, bbox等字段
        """
        # 输入验证 - 检查关键输入参数
        if not segments or not ocr_results:
            logger.warning("Segments or OCR results are empty, skipping keyframe post-processing.")
            return []
            
        logger.info(f"Starting keyframe-driven post-processing: {len(segments)} segments, {len(ocr_results)} OCR results.")
        
        final_subtitles = []
        # 遍历每个预处理的segment
        for segment in segments:
            # 获取该segment的关键帧索引
            key_frame = segment['key_frame']
            # 检查该关键帧是否有对应的OCR结果
            if key_frame not in ocr_results:
                continue
                
            # 提取OCR识别的文本和边界框
            text, bbox = ocr_results[key_frame]
            # 过滤空文本
            if not text or not text.strip():
                continue
                
            # 计算字幕持续时间
            duration = segment['duration']
            # 过滤持续时间过短的字幕
            if duration < self.min_duration_seconds:
                continue
            
            # 格式化边界框为标准格式
            formatted_bbox = self._format_bbox(bbox)
            
            # 构建标准格式的字幕对象
            final_subtitles.append({
                'startTime': round(segment['start_time'], 3),  # 开始时间(秒)，保留3位小数
                'endTime': round(segment['end_time'], 3),     # 结束时间(秒)，保留3位小数
                'text': text.strip(),                        # 清理后的文本内容
                'bbox': formatted_bbox,                      # 标准化的边界框坐标
                'keyFrame': key_frame,                       # 关键帧索引
                'frameRange': [segment['start_frame'], segment['end_frame']]  # 帧范围
            })
        
        # 合并重复的相似字幕
        merged_subtitles = self._merge_duplicate_subtitles(final_subtitles)
        logger.info(f"Keyframe post-processing complete: {len(merged_subtitles)} subtitles generated.")
        # 重新分配连续ID并返回
        return self._reassign_ids(merged_subtitles)

    def format_from_full_frames(self, ocr_results: Dict[int, Tuple[str, Any]], fps: float) -> List[Dict[str, Any]]:
        """
        全帧处理模式的后处理函数
        
        该函数从原始的逐帧OCR结果构建完整的字幕时间线。
        通过分析文本相似度和帧连续性来自动分段，适用于需要精确捕获所有字幕变化的场景。
        
        Args:
            ocr_results: 逐帧OCR识别结果字典 {frame_idx: (text, bbox)}
            fps: 视频帧率，用于帧号到时间戳的转换
            
        Returns:
            List[Dict]: 格式化的字幕列表，包含id, startTime, endTime, text, bbox等字段
        """
        # 输入验证
        if not ocr_results:
            logger.warning("OCR results are empty, skipping full-frame post-processing.")
            return []

        logger.info(f"Starting full-frame post-processing for {len(ocr_results)} frames.")

        # 1. 从原始逐帧OCR结果构建字幕段
        segments = []
        # [BUG FIX] 按帧号的整数值排序，而不是字符串字典序
        sorted_frames = sorted(ocr_results.items(), key=lambda item: int(item[0]))
        
        if not sorted_frames:
            return []

        current_segment = None
        # 遍历所有帧的OCR结果
        for i, (frame_idx_str, (text, bbox)) in enumerate(sorted_frames):
            # [FIX] 将从JSON键转换而来的字符串帧号转换为整数
            frame_idx = int(frame_idx_str)

            # 处理空文本帧
            if not text or not text.strip():
                # 如果当前有活跃segment，则结束它
                if current_segment:
                    segments.append(current_segment)
                    current_segment = None
                continue

            # 开始新的segment
            if current_segment is None:
                current_segment = {
                    'start_frame': frame_idx,
                    'end_frame': frame_idx,
                    'text': text,
                    'bbox': bbox
                }
            else:
                # 判断是否应该合并到当前segment
                # [FIX] 使用可配置的相似度阈值
                is_similar_text = self._are_texts_similar(text, current_segment['text'], self.similarity_threshold)
                # 检查帧连续性（相邻帧）
                is_continuous_frame = (frame_idx == current_segment['end_frame'] + 1)

                # 如果文本相似且帧连续，则扩展当前segment
                if is_similar_text and is_continuous_frame:
                    current_segment['end_frame'] = frame_idx
                    # 可选：合并边界框（这里保持原有bbox）
                else:
                    # 文本不同或帧不连续，结束当前segment并开始新的
                    segments.append(current_segment)
                    current_segment = {
                        'start_frame': frame_idx,
                        'end_frame': frame_idx,
                        'text': text,
                        'bbox': bbox
                    }
        
        # 处理最后一个segment
        if current_segment:
            segments.append(current_segment)

        # 2. 清理、格式化并过滤segments
        final_subtitles = self._clean_and_format_segments(segments, fps)
        
        # 3. 合并可能因小间隙而产生的重复字幕
        merged_subtitles = self._merge_duplicate_subtitles(final_subtitles)
        logger.info(f"Full-frame post-processing complete: {len(merged_subtitles)} subtitles generated.")
        return self._reassign_ids(merged_subtitles)

    def _clean_and_format_segments(self, segments: List[Dict], fps: float) -> List[Dict]:
        """
        清理和格式化字幕段
        
        过滤掉无效的字幕段，并将帧号转换为时间戳。
        主要用于全帧模式中将构建的segments转换为标准字幕格式。
        
        Args:
            segments: 原始字幕段列表，包含start_frame, end_frame, text, bbox
            fps: 视频帧率，用于帧到时间的转换
            
        Returns:
            List[Dict]: 清理后的字幕列表
        """
        cleaned_subtitles = []
        for seg in segments:
            # 将帧号转换为时间戳
            start_time = seg['start_frame'] / fps
            end_time = seg['end_frame'] / fps
            duration = end_time - start_time

            # 过滤持续时间过短的字幕
            if duration < self.min_duration_seconds:
                continue
            
            # 格式化边界框
            formatted_bbox = self._format_bbox(seg.get('bbox'))

            # 构建标准字幕对象
            cleaned_subtitles.append({
                'startTime': round(start_time, 3),           # 开始时间(秒)
                'endTime': round(end_time, 3),               # 结束时间(秒) 
                'text': seg['text'],                         # 文本内容
                'bbox': formatted_bbox,                      # 边界框坐标
                'frameRange': [seg['start_frame'], seg['end_frame']]  # 帧范围
            })
            
        return cleaned_subtitles

    def _format_bbox(self, bbox: Any) -> List[List[int]]:
        """
        [FIXED] 格式化边界框为标准格式
        
        将输入的边界框（通常是包含多个[x, y]坐标点的列表）转换为标准的整数坐标列表。
        
        Args:
            bbox: 边界框，格式为 [[x1, y1], [x2, y2], ...]
            
        Returns:
            List[List[int]]: 标准化的顶点坐标列表
        """
        if not bbox or not isinstance(bbox, list):
            return []
        try:
            # 遍历每个点 [x, y]，并确保坐标是整数
            return [[int(p[0]), int(p[1])] for p in bbox]
        except (TypeError, IndexError, ValueError) as e:
            # 如果bbox的结构不是预期的 [[x,y], ...], 记录警告并返回空列表
            logger.warning(f"Failed to format bbox due to unexpected structure: {bbox}. Error: {e}")
            return []

    def _merge_duplicate_subtitles(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并相邻或重叠的相似字幕
        
        识别并合并文本相似且时间连续的字幕，减少冗余。
        这对于处理OCR识别中的重复内容或由小间隙分割的连续字幕很有用。
        
        Args:
            subtitles: 待处理的字幕列表
            
        Returns:
            List[Dict]: 合并后的字幕列表
        """
        if not subtitles:
            return []
            
        merged = []
        current_sub = subtitles[0]
        
        # 逐一比较相邻字幕
        for next_sub in subtitles[1:]:
            # [FIX] 使用可配置的相似度阈值
            is_similar = self._are_texts_similar(current_sub['text'], next_sub['text'], self.similarity_threshold)
            # 检查时间连续性：间隙小于1秒视为连续
            time_gap = next_sub['startTime'] - current_sub['endTime']
            is_continuous = time_gap < 1.0

            # 如果文本相似且时间连续，则合并
            if is_similar and is_continuous:
                # 扩展当前字幕的结束时间
                current_sub['endTime'] = max(current_sub['endTime'], next_sub['endTime'])
                # 同时合并帧范围
                if 'frameRange' in current_sub and 'frameRange' in next_sub:
                    current_sub['frameRange'][1] = max(current_sub['frameRange'][1], next_sub['frameRange'][1])
            else:
                # 不可合并，完成当前字幕并开始处理下一个
                merged.append(current_sub)
                current_sub = next_sub
        
        # 添加最后一个字幕
        merged.append(current_sub)
        return merged
    
    def _are_texts_similar(self, text1: str, text2: str, threshold: float) -> bool:
        """
        比较两个文本的相似度
        
        使用SequenceMatcher算法计算文本相似度，用于判断是否应该合并字幕。
        相似度基于字符序列的匹配程度。
        
        Args:
            text1: 第一个文本
            text2: 第二个文本  
            threshold: 相似度阈值
            
        Returns:
            bool: 如果相似度超过阈值返回True，否则返回False
        """
        if not text1 or not text2:
            return False
        # 使用difflib计算序列匹配相似度
        return difflib.SequenceMatcher(None, text1.strip(), text2.strip()).ratio() >= threshold

    def _reassign_ids(self, subtitles: List[Dict]) -> List[Dict]:
        """
        重新分配字幕ID
        
        为最终的字幕列表分配连续的序号ID，从1开始。
        这确保输出的字幕具有规范的标识符。
        
        Args:
            subtitles: 待分配ID的字幕列表
            
        Returns:
            List[Dict]: 已分配ID的字幕列表
        """
        # 为每个字幕分配从1开始的连续ID
        for i, sub in enumerate(subtitles, 1):
            sub['id'] = i
        return subtitles