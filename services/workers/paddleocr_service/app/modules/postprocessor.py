# pipeline/modules/postprocessor.py
import numpy as np
import re
import difflib
from typing import List, Dict, Tuple, Any

from .change_detector import ChangeType

class SubtitlePostprocessor:
    """
    [V2] Event-driven postprocessor.
    Builds precise subtitle timelines based on a stream of change events.
    """
    def __init__(self, config):
        self.config = config
        self.min_duration_seconds = config.get('min_duration_seconds', 0.2)
        print("模块: 字幕后处理器已加载 (V2 - 事件驱动)。")

    def format(self, ocr_results: Dict[int, Tuple[str, Any, ChangeType]], video_fps: float, total_frames: int) -> List[Dict[str, Any]]:
        """
        Executes post-processing to generate the final list of subtitles.

        Args:
            ocr_results (Dict): Results from the OCR engine, in event format {frame_idx: (text, bbox, event_type)}.
            video_fps (float): The video's frames per second.
            total_frames (int): The total number of frames in the video.

        Returns:
            List[Dict[str, Any]]: The final, formatted list of subtitles.
        """
        if not ocr_results:
            return []
        
        print("开始对OCR事件流进行后处理...")

        # 1. Build continuous segments from discrete events
        segments = self._build_segments(ocr_results, total_frames)
        print(f"已构建 {len(segments)} 个原始字幕片段。")

        # 2. Clean and format segments
        final_subtitles = self._clean_and_format_segments(segments, video_fps)
        print(f"清洗和格式化后，剩余 {len(final_subtitles)} 条字幕。")

        return final_subtitles

    def _build_segments(self, ocr_results: Dict[int, Tuple[str, Any, ChangeType]], total_frames: int) -> List[Dict]:
        """
        Builds time segments by processing a stream of change events.
        """
        if not ocr_results:
            return []

        sorted_events = sorted(ocr_results.items())
        segments = []
        active_segment = None

        for i, (frame_idx, (text, bbox, event_type)) in enumerate(sorted_events):
            if event_type in [ChangeType.TEXT_APPEARED, ChangeType.CONTENT_CHANGED]:
                # The start of a new subtitle implies the end of the previous one.
                if active_segment:
                    active_segment['end_frame'] = frame_idx - 1
                    segments.append(active_segment)
                
                # Start a new active segment
                active_segment = {
                    'start_frame': frame_idx,
                    'text': text,
                    'bbox': bbox
                }

            elif event_type == ChangeType.TEXT_DISAPPEARED:
                # A disappearance event explicitly ends the current segment.
                if active_segment:
                    active_segment['end_frame'] = frame_idx - 1
                    segments.append(active_segment)
                    active_segment = None  # Enter a blank period

        # After the loop, handle the very last active segment
        if active_segment:
            active_segment['end_frame'] = total_frames - 1
            segments.append(active_segment)
        
        return segments

    def _clean_and_format_segments(self, segments: List[Dict], fps: float) -> List[Dict]:
        """
        Filters invalid segments and converts frame numbers to timestamps.
        """
        cleaned_subtitles = []
        subtitle_id = 1

        for seg in segments:
            if not seg.get('text') or not seg['text'].strip():
                continue

            start_time = seg['start_frame'] / fps
            end_time = seg['end_frame'] / fps
            duration = end_time - start_time

            if duration < self.min_duration_seconds:
                continue
            
            # Format the bounding box if it exists
            bbox = seg.get('bbox')
            if bbox:
                x1, y1, x2, y2 = bbox
                formatted_bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                formatted_bbox = []

            cleaned_subtitles.append({
                'id': subtitle_id,
                'startTime': round(start_time, 3),
                'endTime': round(end_time, 3),
                'text': seg['text'],
                'bbox': formatted_bbox
            })
            subtitle_id += 1
            
        return cleaned_subtitles

    def format_from_keyframes(self, segments: List[Dict], ocr_results: Dict[int, Tuple[str, Any]], fps: float) -> List[Dict[str, Any]]:
        """
        关键帧驱动的后处理方法 - 适配新架构
        
        基于KeyFrameDetector生成的段落信息和OCR识别结果，
        生成最终的字幕列表。
        
        Args:
            segments: KeyFrameDetector生成的段落列表
                [
                    {
                        'key_frame': 0,
                        'start_frame': 0,
                        'end_frame': 44, 
                        'start_time': 0.0,
                        'end_time': 1.76,
                        'duration': 1.76
                    },
                    ...
                ]
            ocr_results: OCR识别结果映射 {key_frame: (text, bbox)}
            fps: 视频帧率
            
        Returns:
            List[Dict[str, Any]]: 最终格式化的字幕列表
        """
        if not segments or not ocr_results:
            print("⚠️ 段落信息或OCR结果为空，跳过后处理")
            return []
            
        print(f"🔄 开始关键帧驱动的后处理: {len(segments)} 个段落, {len(ocr_results)} 个OCR结果")
        
        final_subtitles = []
        subtitle_id = 1
        
        # 统计数据初始化
        process_stats = {
            'total_segments': len(segments),     # 识别总帧数
            'successful': 0,                   # 识别成功帧数
            'missing_ocr': 0,                  # 缺少OCR结果帧数
            'short_duration': 0,               # 小于最短限制帧数
            'empty_text': 0                    # 空文本帧数
        }
        
        for segment in segments:
            key_frame = segment['key_frame']
            
            # 获取对应关键帧的OCR结果
            if key_frame not in ocr_results:
                process_stats['missing_ocr'] += 1
                continue
                
            text, bbox = ocr_results[key_frame]
            
            # 过滤空文本
            if not text or not text.strip():
                process_stats['empty_text'] += 1
                continue
                
            # 检查最短时长限制
            duration = segment['duration']
            if duration < self.min_duration_seconds:
                process_stats['short_duration'] += 1
                continue
            
            # 格式化边界框
            formatted_bbox = []
            if bbox:
                try:
                    x1, y1, x2, y2 = bbox
                    formatted_bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                except Exception as e:
                    print(f"⚠️ 关键帧 {key_frame} 边界框格式化失败: {e}")
            
            # 生成最终字幕项
            final_subtitles.append({
                'id': subtitle_id,
                'startTime': round(segment['start_time'], 3),
                'endTime': round(segment['end_time'], 3), 
                'text': text.strip(),
                'bbox': formatted_bbox,
                # 新增 keyFrame 和 frameRange 字段
                'keyFrame': key_frame,
                'frameRange': [segment['start_frame'], segment['end_frame']]
            })
            
            subtitle_id += 1
            process_stats['successful'] += 1
        
        # 输出统计信息
        failed_total = process_stats['missing_ocr'] + process_stats['short_duration'] + process_stats['empty_text']
        print(f"📊 后处理统计: 识别总帧数:{process_stats['total_segments']}/"
              f"识别成功帧数:{process_stats['successful']}/"
              f"识别失败总帧数:{failed_total}/"
              f"缺少OCR帧数:{process_stats['missing_ocr']}/"
              f"小于最短限制帧数:{process_stats['short_duration']}")
        
        # 合并重复字幕
        merged_subtitles = self._merge_duplicate_subtitles(final_subtitles)
        print(f"🔄 重复字幕合并: {len(final_subtitles)} → {len(merged_subtitles)} 条字幕")
        print(f"✅ 关键帧后处理完成: 生成 {len(merged_subtitles)} 条字幕")
        return merged_subtitles
    
    def _merge_duplicate_subtitles(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并重复的字幕内容
        
        合并规则:
        1. 相同文本内容的相邻字幕进行合并
        2. 合并后的时间范围为: start=最早开始时间, end=最晚结束时间
        3. 保留第一个字幕的其他属性
        
        Args:
            subtitles: 原始字幕列表
            
        Returns:
            去重后的字幕列表
        """
        if not subtitles or len(subtitles) <= 1:
            return subtitles
            
        merged = []
        current_group = [subtitles[0]]  # 当前待合并组
        
        for i in range(1, len(subtitles)):
            current_sub = subtitles[i]
            last_in_group = current_group[-1]
            
            # 检查是否为重复字幕 (改进的文本相似度比较)
            if self._are_texts_similar(current_sub['text'], last_in_group['text']):
                # 检查时间连续性 (修复时间间隔判断逻辑)
                if self._are_times_continuous(current_sub, last_in_group):
                    # 添加到当前合并组
                    current_group.append(current_sub)
                    continue
            
            # 完成当前组的合并，开始新组
            merged_sub = self._merge_subtitle_group(current_group)
            merged.append(merged_sub)
            current_group = [current_sub]
        
        # 处理最后一组
        if current_group:
            merged_sub = self._merge_subtitle_group(current_group)
            merged.append(merged_sub)
        
        # 重新分配ID
        for i, subtitle in enumerate(merged, 1):
            subtitle['id'] = i
            
        return merged
    
    def _are_texts_similar(self, text1: str, text2: str, similarity_threshold: float = 0.8) -> bool:
        """
        使用difflib比较两个文本的相似度，处理标点符号和空格差异
        
        Args:
            text1: 第一个文本
            text2: 第二个文本  
            similarity_threshold: 相似度阈值，默认0.8 (80%)
            
        Returns:
            bool: 是否为相似文本
        """
        if not text1 or not text2:
            return False
        
        # 标准化文本 (去除标点符号和多余空格，转小写)
        normalized_text1 = self._normalize_text(text1)
        normalized_text2 = self._normalize_text(text2)
        
        # 完全相同
        if normalized_text1 == normalized_text2:
            return True
            
        # 使用difflib计算相似度
        similarity = difflib.SequenceMatcher(None, normalized_text1, normalized_text2).ratio()
        return similarity >= similarity_threshold
    
    def _normalize_text(self, text: str) -> str:
        """
        标准化文本，移除标点符号和多余空格
        
        Args:
            text: 原始文本
            
        Returns:
            标准化后的文本
        """
        if not text:
            return ""
        
        # 转换为小写并去除首尾空格
        normalized = text.strip().lower()
        
        # 移除常见标点符号和特殊字符
        normalized = re.sub(r'[,，。.!！?？;；:：\'"""""''`@#$%^&*()_+=\-\[\]{}|\\~]+', '', normalized)
        
        # 统一空格 (移除多余空格)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _are_times_continuous(self, sub1: Dict[str, Any], sub2: Dict[str, Any]) -> bool:
        """
        检查两个字幕的时间是否连续或重叠
        
        Args:
            sub1: 第一个字幕
            sub2: 第二个字幕
            
        Returns:
            bool: 是否时间连续
        """
        # 时间重叠检测
        if (sub1['startTime'] <= sub2['endTime'] and sub2['startTime'] <= sub1['endTime']):
            return True
        
        # 时间间隔检测 (允许5秒内的间隔)
        time_gap = min(
            abs(sub1['endTime'] - sub2['startTime']),    # sub1结束到sub2开始
            abs(sub2['endTime'] - sub1['startTime'])     # sub2结束到sub1开始
        )
        return time_gap <= 5.0
    
    def _merge_subtitle_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        合并一组相同文本的字幕
        
        Args:
            group: 待合并的字幕组
            
        Returns:
            合并后的字幕
        """
        if len(group) == 1:
            return group[0]
            
        # 找到最早开始时间和最晚结束时间
        start_time = min(sub['startTime'] for sub in group)
        end_time = max(sub['endTime'] for sub in group)
        
        # 合并帧范围 (添加安全检查)
        frame_ranges = [sub['frameRange'] for sub in group if 'frameRange' in sub and sub['frameRange']]
        if frame_ranges:
            start_frame = min(fr[0] for fr in frame_ranges)
            end_frame = max(fr[1] for fr in frame_ranges)
        else:
            # 如果没有帧范围信息，使用第一个字幕的关键帧作为默认值
            start_frame = group[0].get('keyFrame', 0)
            end_frame = start_frame
        
        # 使用第一个字幕作为模板
        merged = group[0].copy()
        merged.update({
            'startTime': round(start_time, 3),
            'endTime': round(end_time, 3),
            'frameRange': [start_frame, end_frame]
        })
        
        return merged
