# -*- coding: utf-8 -*-
"""
独立的OCR执行脚本，通过subprocess调用。
此脚本消费由上游任务生成的拼接图片和清单(manifest)文件，执行OCR并进行坐标反推。
"""
import os
import sys
import json
import logging
import argparse
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Any

# [核心修正] 动态将项目根目录('/app')添加到 sys.path
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# 使用绝对路径导入，确保无歧义
from services.workers.paddleocr_service.app.modules.ocr import MultiProcessOCREngine
from services.common.config_loader import CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [OCRExecutor] - %(levelname)s - %(message)s')

class NumpyEncoder(json.JSONEncoder):
    """ 自定义JSON编码器，用于处理Numpy数据类型 """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(NumpyEncoder, self).default(obj)

def _transform_coordinates(ocr_data: List[Tuple[str, Any]], sub_images_meta: List[Dict[str, Any]]) -> Dict[int, Tuple[str, Any]]:
    """
    将单张拼接图的OCR结果，根据其子图元数据，转换回原始帧的坐标和文本。
    """
    transformed_results = {}

    for text, box in ocr_data:
        if box is None:
            continue
        
        box_points = np.array(box)
        
        # 使用Y坐标的中位数来确定它属于哪个子图，这比仅用第一个点更稳健
        center_y = np.median(box_points[:, 1])

        for meta in sub_images_meta:
            if meta['y_offset'] <= center_y < meta['y_offset'] + meta['height']:
                frame_idx = meta['frame_idx']
                if frame_idx not in transformed_results:
                    transformed_results[frame_idx] = (text, None)
                else:
                    # 如果一帧内有多行文本，将它们拼接起来
                    existing_text, _ = transformed_results[frame_idx]
                    transformed_results[frame_idx] = (existing_text + " " + text, None)
                break
    return transformed_results

def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(description="Perform OCR on a directory of stitched images using a manifest file.")
    parser.add_argument("--manifest-path", required=True, help="Path to the manifest.json file.")
    parser.add_argument("--multi-frames-path", required=True, help="Path to the directory containing stitched images.")
    args = parser.parse_args()

    if not os.path.exists(args.manifest_path):
        logging.error(f"Manifest file not found: {args.manifest_path}")
        sys.exit(1)
    if not os.path.isdir(args.multi_frames_path):
        logging.error(f"Stitched images directory not found: {args.multi_frames_path}")
        sys.exit(1)

    try:
        # 1. 读取清单文件
        with open(args.manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        if not manifest_data:
            logging.warning("Manifest file is empty. No images to process.")
            print(json.dumps({}))
            return

        # 2. 准备OCR任务列表
        ocr_tasks = []
        for stitched_filename in manifest_data.keys():
            image_path = os.path.join(args.multi_frames_path, stitched_filename)
            if os.path.exists(image_path):
                # 任务ID设为拼接图文件名，方便后续匹配
                ocr_tasks.append((stitched_filename, image_path))
            else:
                logging.warning(f"Image file listed in manifest not found: {image_path}")

        if not ocr_tasks:
            logging.error("No valid image files found based on the manifest.")
            print(json.dumps({}))
            return

        # 3. 执行批量OCR
        logging.info(f"Starting batch OCR on {len(ocr_tasks)} stitched images.")
        ocr_engine = MultiProcessOCREngine(CONFIG.get('ocr', {}))
        # recognize_stitched 返回一个字典 {stitched_filename: ocr_data}
        raw_results_map = ocr_engine.recognize_stitched(ocr_tasks)
        logging.info(f"Batch OCR completed. Received results for {len(raw_results_map)} images.")

        # 4. 坐标反推和结果聚合
        final_ocr_results = {}
        for stitched_filename, ocr_data in raw_results_map.items():
            if stitched_filename in manifest_data:
                sub_images_meta = manifest_data[stitched_filename].get('sub_images', [])
                transformed_part = _transform_coordinates(ocr_data, sub_images_meta)
                final_ocr_results.update(transformed_part)
            else:
                logging.warning(f"Received OCR result for an unknown image not in manifest: {stitched_filename}")

        # 5. 输出最终结果
        string_key_results = {str(k): v for k, v in final_ocr_results.items()}
        print(json.dumps(string_key_results, cls=NumpyEncoder))

    except Exception as e:
        logging.error(f"An error occurred during OCR execution: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
