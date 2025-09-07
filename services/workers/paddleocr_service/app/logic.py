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
from app.modules.keyframe_detector import KeyFrameDetector  # 🆕 新的关键帧检测器
# 🚫 旧版本已替换: from app.modules.change_detector import ChangeDetector, ChangeType
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
    从视频文件中提取字幕的核心逻辑函数 - 重构版本

    重大更新: 从"事件驱动"改为"关键帧驱动"模式
    - 第一帧默认为关键帧
    - 基于相似度的逐帧比对
    - 符合行业标准的阈值设定

    Args:
        video_path (str): 要处理的视频文件的绝对路径。
        config (Dict): 包含所有模块配置的字典。

    Returns:
        List[Dict[str, Any]]: 提取出的字幕列表，包含keyFrame和frameRange字段。
    """
    print("🚀 开始字幕提取 (关键帧驱动模式)...")
    
    # 1. 初始化所有处理模块
    decoder = GPUDecoder(config.get('decoder', {}))
    area_detector = SubtitleAreaDetector(config.get('area_detector', {}))
    keyframe_detector = KeyFrameDetector(config.get('keyframe_detector', {}))  # 🆕 新检测器
    ocr_engine = MultiProcessOCREngine(config.get('ocr', {}))
    postprocessor = SubtitlePostprocessor(config.get('postprocessor', {}))
    
    # 2. 获取视频元数据
    fps, total_frames = _get_video_metadata(video_path)
    print(f"📹 视频信息: {fps:.1f}fps, {total_frames}帧")

    # 3. 智能字幕区域检测
    subtitle_area = area_detector.detect(video_path, decoder)
    if subtitle_area is None:
        print("❌ 未能检测到字幕区域，视频可能不包含字幕或字幕不够清晰，任务结束")
        return []  # 返回空的字幕列表
    print(f"📍 字幕区域: {subtitle_area}")

    # 4. 关键帧检测 (新逻辑)
    keyframes = keyframe_detector.detect_keyframes(video_path, decoder, subtitle_area)
    if not keyframes:
        print("❌ 未检测到关键帧，任务结束")
        return []

    # 5. 生成段落信息 (新逻辑) 
    segments = keyframe_detector.generate_subtitle_segments(keyframes, fps, total_frames)

    # 6. OCR识别 (需要适配新的输入格式)
    ocr_results = ocr_engine.recognize_keyframes(video_path, decoder, keyframes, subtitle_area, total_frames)

    # 7. 后处理 (需要适配新的数据结构)
    final_subtitles = postprocessor.format_from_keyframes(segments, ocr_results, fps)
    
    print(f"✅ 字幕提取完成，共生成 {len(final_subtitles)} 条字幕")
    return final_subtitles
