# pipeline/modules/area_detector.py
import torch
import numpy as np
from paddleocr import PaddleOCR
from typing import Tuple, List
import time

# 导入我们自己的解码器
from .decoder import GPUDecoder

class SubtitleAreaDetector:
    """
    通过对视频帧进行采样和文本检测，智能确定字幕的主要区域。
    """
    def __init__(self, config):
        self.config = config
        self.sample_count = config.get('sample_count', 300)
        self.min_text_len = config.get('min_text_len', 2) # 用于加权的最小文本长度
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # 开启识别功能(rec=True), 以便使用字数进行加权
        self.text_detector = PaddleOCR(use_gpu=True, use_angle_cls=False, lang='en', show_log=False, det=True, rec=True)
        print("模块: 字幕区域检测器已加载 (已开启文本识别用于加权)。")

    def detect(self, video_path: str, decoder: GPUDecoder) -> Tuple[int, int, int, int]:
        """
        执行字幕区域检测。
        """
        print("开始智能检测字幕区域...")
        
        frame_samples = self._sample_frames(video_path, decoder)
        if not frame_samples:
            raise RuntimeError("无法从视频中采样到任何帧来进行字幕区域检测。")
        
        video_height, video_width = frame_samples[0].shape[:2]
        print(f"  - [进度] 已采样 {len(frame_samples)} 帧，视频尺寸: {video_width}x{video_height}")

        all_detections = self._detect_text_in_samples(frame_samples)
        if not all_detections:
            raise RuntimeError("在采样帧中未能检测到任何文本框，无法确定字幕区域。")
        print(f"  - [进度] 在采样帧中检测到 {len(all_detections)} 个文本片段。")

        subtitle_area = self._find_stable_area(all_detections, video_width, video_height)
        print(f"检测完成，最终字幕区域: {subtitle_area}")
        
        return subtitle_area

    def _sample_frames(self, video_path: str, decoder: GPUDecoder) -> List[np.ndarray]:
        """使用解码器从视频中均匀采样指定数量的帧。"""
        total_frames = 0
        try:
            container = decoder.av.open(video_path)
            stream = container.streams.video[0]
            total_frames = stream.frames
            if total_frames == 0:
                total_frames = int(stream.duration * stream.time_base * stream.average_rate)
            container.close()
        except Exception:
            total_frames = 5000

        if total_frames == 0: total_frames = 5000

        sample_indices = np.linspace(0, total_frames - 1, self.sample_count, dtype=int)
        
        frames = []
        current_frame_idx = 0
        sample_idx_ptr = 0

        for batch_tensor, _ in decoder.decode(video_path, log_progress=True):
            for frame_tensor in batch_tensor:
                if sample_idx_ptr < len(sample_indices) and current_frame_idx == sample_indices[sample_idx_ptr]:
                    frame_np = frame_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    frames.append(frame_np)
                    sample_idx_ptr += 1
                current_frame_idx += 1
            if sample_idx_ptr >= len(sample_indices):
                break
        return frames

    def _detect_text_in_samples(self, frames: List[np.ndarray]) -> List[Tuple[np.ndarray, str]]:
        """对采样帧批量进行文本检测和识别。"""
        all_detections = []
        start_time = time.time()
        for i, frame in enumerate(frames):
            # 同时进行检测和识别
            result = self.text_detector.ocr(frame, cls=False)
            if result and result[0]:
                for res in result[0]:
                    box = np.array(res[0], dtype=np.int32)
                    text = res[1][0]
                    all_detections.append((box, text))

            if (i + 1) % 50 == 0:
                print(f"    - [检测进度] 已OCR {i + 1}/{len(frames)} 帧... (耗时: {time.time() - start_time:.2f}s)")
                start_time = time.time()
        return all_detections

    def _find_stable_area(self, detections: List[Tuple[np.ndarray, str]], width: int, height: int) -> Tuple[int, int, int, int]:
        """通过带字数权重的Y轴投影来确定最稳定的字幕区域。"""
        if not detections:
            return (0, height * 2 // 3, width, height - 10)

        y_histogram = np.zeros(height, dtype=int)
        
        # 关键优化: 使用文本长度作为权重进行Y轴投影
        for box, text in detections:
            if len(text) < self.min_text_len:
                continue # 过滤掉过短的文本
            min_y = np.min(box[:, 1])
            max_y = np.max(box[:, 1])
            y_histogram[min_y:max_y] += len(text) # 使用字数加权
        
        if np.sum(y_histogram) == 0:
            # 如果所有检测到的文本都太短, 回退到不加权的方式
            print("  - [警告] 未发现足够长的文本进行加权，回退到标准区域检测。")
            all_boxes = [d[0] for d in detections]
            return self._find_stable_area_no_weight(all_boxes, width, height)

        # 关键优化: 对视频下半部分增加权重，优先选择底部的字幕
        mid_point = height // 2
        y_histogram[mid_point:] = y_histogram[mid_point:] * 1.5

        peak_y = np.argmax(y_histogram)
        y_threshold = y_histogram[peak_y] * 0.3

        y_min = peak_y
        while y_min > 0 and y_histogram[y_min] > y_threshold:
            y_min -= 1
        
        y_max = peak_y
        while y_max < height - 1 and y_histogram[y_max] > y_threshold:
            y_max += 1

        x_min = 0
        x_max = width

        y_padding = 15
        final_y_min = max(0, y_min - y_padding)
        final_y_max = min(height, y_max + y_padding)

        if final_y_max - final_y_min < 20:
             return (0, height * 2 // 3, width, height - 10)

        return (int(x_min), int(final_y_min), int(x_max), int(final_y_max))
    
    def _find_stable_area_no_weight(self, boxes: List[np.ndarray], width: int, height: int) -> Tuple[int, int, int, int]:
        """不带权重的后备检测算法"""
        y_histogram = np.zeros(height, dtype=int)
        for box in boxes:
            min_y = np.min(box[:, 1])
            max_y = np.max(box[:, 1])
            y_histogram[min_y:max_y] += 1
        mid_point = height // 2
        y_histogram[mid_point:] = y_histogram[mid_point:] * 1.5
        peak_y = np.argmax(y_histogram)
        y_threshold = y_histogram[peak_y] * 0.3
        y_min = peak_y
        while y_min > 0 and y_histogram[y_min] > y_threshold: y_min -= 1
        y_max = peak_y
        while y_max < height - 1 and y_histogram[y_max] > y_threshold: y_max += 1
        y_padding = 15
        final_y_min = max(0, y_min - y_padding)
        final_y_max = min(height, y_max + y_padding)
        return (0, int(final_y_min), width, int(final_y_max))