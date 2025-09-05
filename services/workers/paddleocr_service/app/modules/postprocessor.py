# pipeline/modules/postprocessor.py
import numpy as np
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
