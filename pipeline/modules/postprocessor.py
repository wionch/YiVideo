# pipeline/modules/postprocessor.py
import numpy as np
from typing import List, Dict, Tuple, Any

class SubtitlePostprocessor:
    """
    将OCR识别出的离散文本，处理成带有精确时间轴的连续字幕。
    """
    def __init__(self, config):
        self.config = config
        # 最小字幕持续时间（秒），过滤掉闪现的噪声
        self.min_duration_seconds = config.get('min_duration_seconds', 0.2)
        print("模块: 字幕后处理器已加载。")

    def format(self, ocr_results: Dict[int, Tuple[str, Tuple]], video_fps: float, total_frames: int) -> List[Dict[str, Any]]:
        """
        执行后处理，生成最终的字幕列表。

        Args:
            ocr_results (Dict): OCR引擎的结果, {帧索引: (文本, Bbox)}。
            video_fps (float): 视频的帧率。
            total_frames (int): 视频总帧数。

        Returns:
            List[Dict[str, Any]]: 最终的、格式化的字幕列表。
        """
        if not ocr_results:
            return []
        
        print("开始对OCR结果进行后处理...")

        # 1. 将离散的关键帧结果，构建成连续的片段
        segments = self._build_segments(ocr_results, total_frames)
        print(f"已构建 {len(segments)} 个原始字幕片段。")

        # 2. 清洗和格式化片段
        final_subtitles = self._clean_and_format_segments(segments, video_fps)
        print(f"清洗和格式化后，剩余 {len(final_subtitles)} 条字幕。")

        return final_subtitles

    def _normalize_text(self, text: str) -> str:
        """将文本转为小写并移除常见标点符号和空格，用于比较。"""
        import string
        return text.lower().translate(str.maketrans('', '', string.punctuation + string.whitespace))

    def _build_segments(self, ocr_results: Dict[int, Tuple[str, Tuple]], total_frames: int) -> List[Dict]:
        """
        根据文本变化，将关键帧组合成时间片段。
        """
        if not ocr_results:
            return []

        sorted_indices = sorted(ocr_results.keys())
        segments = []
        
        current_segment_start_idx = sorted_indices[0]
        current_text, current_bbox = ocr_results[current_segment_start_idx]

        for i in range(1, len(sorted_indices)):
            next_idx = sorted_indices[i]
            next_text, next_bbox = ocr_results[next_idx]
            
            # 使用归一化的文本进行比较
            if self._normalize_text(next_text) != self._normalize_text(current_text):
                # 文本发生变化，结束当前片段
                segment_end_idx = next_idx - 1
                segments.append({
                    'start_frame': current_segment_start_idx,
                    'end_frame': segment_end_idx,
                    'text': current_text,
                    'bbox': current_bbox
                })
                # 开始新片段
                current_segment_start_idx = next_idx
                current_text = next_text
                current_bbox = next_bbox

        # 添加最后一个片段
        segments.append({
            'start_frame': current_segment_start_idx,
            'end_frame': total_frames - 1, # 直到视频结束
            'text': current_text,
            'bbox': current_bbox
        })
        
        return segments

    def _clean_and_format_segments(self, segments: List[Dict], fps: float) -> List[Dict]:
        """
        过滤掉无效片段，并将帧号转换为时间戳。
        """
        cleaned_subtitles = []
        subtitle_id = 1

        for seg in segments:
            # 1. 过滤掉没有文本的片段
            if not seg['text'].strip():
                continue

            start_time = seg['start_frame'] / fps
            end_time = seg['end_frame'] / fps
            duration = end_time - start_time

            # 2. 过滤掉持续时间过短的片段
            if duration < self.min_duration_seconds:
                continue
            
            # 3. 格式化输出
            x1, y1, x2, y2 = seg['bbox']
            formatted_bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

            cleaned_subtitles.append({
                'id': subtitle_id,
                'startTime': round(start_time, 3),
                'endTime': round(end_time, 3),
                'text': seg['text'],
                'bbox': formatted_bbox
            })
            subtitle_id += 1
            
        return cleaned_subtitles