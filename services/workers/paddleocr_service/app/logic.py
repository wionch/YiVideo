# services/workers/paddleocr_service/app/logic.py
import yaml
import os
import av
import torch
import numpy as np
from typing import List, Dict, Tuple, Any

# Correctly import modules from the new location
from app.modules.decoder import GPUDecoder
from app.modules.area_detector import SubtitleAreaDetector
from app.modules.change_detector import ChangeDetector, ChangeType
from app.modules.ocr import MultiProcessOCREngine
from app.modules.postprocessor import SubtitlePostprocessor

def _get_video_metadata(video_path: str) -> Tuple[float, int]:
    """获取视频的帧率和总帧数"""
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            fps = stream.average_rate
            total_frames = stream.frames
            if total_frames == 0:  # 如果元数据中没有总帧数，则估算
                total_frames = int(stream.duration * stream.time_base * fps)
            return float(fps), total_frames
    except (av.AVError, IndexError) as e:
        print(f"警告: 无法准确获取视频元数据: {e}. 将使用估算值。")
        return 25.0, 99999  # 返回一个通用估算值

def extract_subtitles_from_video(video_path: str, config: Dict) -> List[Dict[str, Any]]:
    """
    从视频文件中提取字幕的核心逻辑函数。

    这是一个纯函数，它接收视频路径和配置字典，并返回提取结果，
    不依赖任何外部状态或文件（除了视频本身）。

    Args:
        video_path (str): 要处理的视频文件的绝对路径。
        config (Dict): 包含所有模块配置的字典。

    Returns:
        List[Dict[str, Any]]: 提取出的字幕列表。
    """
    # 1. 初始化所有处理模块
    decoder = GPUDecoder(config.get('decoder', {}))
    area_detector = SubtitleAreaDetector(config.get('area_detector', {}))
    change_detector = ChangeDetector(config.get('change_detector', {}))
    ocr_engine = MultiProcessOCREngine(config.get('ocr', {}))
    postprocessor = SubtitlePostprocessor(config.get('postprocessor', {}))
    
    # 2. 获取视频元数据
    fps, total_frames = _get_video_metadata(video_path)

    # 3. 智能字幕区域检测
    subtitle_area = area_detector.detect(video_path, decoder)
    if subtitle_area is None:
        print("未能检测到字幕区域，视频可能不包含字幕或字幕不够清晰，任务结束")
        return []  # 返回空的字幕列表

    # 4. 变化点检测 (事件驱动)
    change_events = change_detector.find_key_frames(video_path, decoder, subtitle_area)

    # 5. 批量OCR识别 (事件驱动)
    ocr_results = ocr_engine.recognize(video_path, decoder, change_events, subtitle_area, total_frames)

    # 6. 后处理与格式化
    final_subtitles = postprocessor.format(ocr_results, fps, total_frames)
    
    return final_subtitles
