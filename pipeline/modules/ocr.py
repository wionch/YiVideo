# pipeline/modules/ocr.py

import torch
import numpy as np
from paddleocr import PaddleOCR
from typing import List, Tuple, Dict

from .decoder import GPUDecoder

class BatchOCREngine:
    """
    [ROLLBACK VERSION]
    This version reverts to a simple, stable, frame-by-frame OCR process.
    It does NOT use batching in order to ensure stability and correct output,
    as requested by the user.
    """
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        lang = config.get('lang', 'en')
        # Use the full, stable PaddleOCR instance
        self.ocr_engine = PaddleOCR(use_gpu=True, use_angle_cls=True, lang=lang, show_log=False)
        print(f"模块: OCR引擎已加载 (回退至稳定版), 使用语言: {lang}")

    def recognize(self, video_path: str, decoder: GPUDecoder, key_frame_indices: List[int], subtitle_area: Tuple[int, int, int, int]) -> Dict[int, Tuple[str, Tuple[int, int, int, int]]]:
        """
        [ROLLBACK VERSION] Performs OCR frame by frame for maximum stability.
        """
        print(f"开始对 {len(key_frame_indices)} 个关键帧进行OCR (稳定模式, 逐帧)...")
        x1, y1, x2, y2 = subtitle_area
        crop_y_start_for_coords = y1

        key_frames_map = self._extract_key_frames(video_path, decoder, key_frame_indices, (x1, y1, x2, y2))
        if not key_frames_map:
            return {}

        final_results = {}
        
        count = 0
        for frame_idx in sorted(key_frames_map.keys()):
            frame = key_frames_map[frame_idx]
            
            # Use the full, stable ocr method on a single frame
            ocr_output = self.ocr_engine.ocr(frame, cls=False)

            if ocr_output and ocr_output[0]: # Check for valid, non-empty result
                texts = []
                boxes = []
                for line in ocr_output[0]:
                    # line is -> [box, (text, confidence)]
                    box = line[0]
                    text = line[1][0]
                    texts.append(text)
                    boxes.append(box)

                if texts:
                    full_text = " ".join(texts)
                    all_points = np.vstack([np.array(b) for b in boxes]).reshape(-1, 2)
                    min_x, min_y = np.min(all_points, axis=0)
                    max_x, max_y = np.max(all_points, axis=0)
                    
                    # Convert bbox to absolute coordinates
                    abs_bbox = (int(min_x), int(min_y + crop_y_start_for_coords), int(max_x), int(max_y + crop_y_start_for_coords))
                    final_results[frame_idx] = (full_text.strip(), abs_bbox)
            
            count += 1
            if count % 100 == 0:
                print(f"  - [进度] 已OCR {count}/{len(key_frame_indices)} 帧...")

        print("OCR (稳定模式)完成。")
        return final_results

    def _extract_key_frames(self, video_path: str, decoder: GPUDecoder, key_frame_indices: List[int], crop_rect: Tuple[int, int, int, int]) -> Dict[int, np.ndarray]:
        """Efficiently decodes and crops only the key frames."""
        key_frames_to_get = set(key_frame_indices)
        key_frames_map = {}
        x1, y1, x2, y2 = crop_rect
        
        current_frame_idx = 0
        for batch_tensor, _ in decoder.decode(video_path):
            for frame_tensor in batch_tensor:
                if current_frame_idx in key_frame_indices:
                    cropped_tensor = frame_tensor[:, y1:y2, x1:x2]
                    frame_np = cropped_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    key_frames_map[current_frame_idx] = frame_np
                    key_frames_to_get.remove(current_frame_idx)
                
                current_frame_idx += 1
            
            if not key_frames_to_get:
                break
        
        return key_frames_map
