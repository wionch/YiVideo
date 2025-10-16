# -*- coding: utf-8 -*-
"""
独立的OCR执行脚本，通过subprocess调用。
此脚本消费由上游任务生成的拼接图片和清单(manifest)文件，执行OCR并进行坐标反推。
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

import numpy as np

# [修复] 确保子进程日志能正确输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from services.common.logger import get_logger

# [核心修正] 动态将项目根目录('/app')添加到 sys.path
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from services.common.config_loader import CONFIG

# 使用绝对路径导入，确保无歧义
from services.workers.paddleocr_service.app.modules.ocr import MultiProcessOCREngine

# 日志已统一管理，使用 services.common.logger

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
                
                # [核心修正] 计算反推后的真实坐标
                # 子图的x偏移（即字幕区域的x1）
                x_offset = meta.get('x_offset', 0) 
                # 子图在拼接图中的y偏移
                y_offset = meta['y_offset']
                
                # 创建一个新的box，将坐标转换回去
                # 新x = 当前x + 字幕区域的x1
                # 新y = 当前y - 子图在拼接图中的y偏移
                transformed_box = [[p[0] + x_offset, p[1] - y_offset] for p in box]

                if frame_idx not in transformed_results:
                    # 存储包含真实坐标的结果
                    transformed_results[frame_idx] = (text, transformed_box)
                else:
                    # 如果一帧内有多行文本，将它们拼接起来
                    # 注意：这里的坐标合并策略可能需要根据实际需求调整
                    # 当前简单地使用新识别到的文本和其坐标，覆盖旧的
                    existing_text, _ = transformed_results[frame_idx]
                    # 拼接文本，但保留新检测到的box作为代表
                    transformed_results[frame_idx] = (existing_text + " " + text, transformed_box)
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
            return

        # 2. 准备OCR任务列表
        ocr_tasks = []
        for stitched_filename in manifest_data.keys():
            image_path = os.path.join(args.multi_frames_path, stitched_filename)
            if os.path.exists(image_path):
                # 任务ID设为拼接图文件名，方便后续匹配
                ocr_tasks.append((stitched_filename, image_path))

        if not ocr_tasks:
            logging.error("No valid image files found based on the manifest.")
            return

        # 3. 执行批量OCR
        ocr_engine = MultiProcessOCREngine(CONFIG.get('ocr', {}))
        # recognize_stitched 返回一个字典 {stitched_filename: ocr_data}
        raw_results_map = ocr_engine.recognize_stitched(ocr_tasks)

        # 4. 坐标反推和结果聚合
        final_ocr_results = {}
        total_ocr_data_count = 0
        successful_transforms = 0

        for stitched_filename, ocr_data in raw_results_map.items():
            if stitched_filename in manifest_data:
                total_ocr_data_count += len(ocr_data)
                sub_images_meta = manifest_data[stitched_filename].get('sub_images', [])
                transformed_part = _transform_coordinates(ocr_data, sub_images_meta)
                successful_transforms += len(transformed_part)
                final_ocr_results.update(transformed_part)

                            else:
                logging.warning(f"Received OCR result for an unknown image not in manifest: {stitched_filename}")

        # 5. 输出最终结果
        string_key_results = {str(k): v for k, v in final_ocr_results.items()}
        logging.info(f"OCR processing completed:")
        logging.info(f"  - Total OCR data items: {total_ocr_data_count}")
        logging.info(f"  - Successful transforms: {successful_transforms}")
        logging.info(f"  - Final results for {len(string_key_results)} frames")

                
        # 确保结果不为空
        if not string_key_results:
            logging.warning("OCR processing completed but no results were generated. This might indicate an issue with the OCR engine or input images.")
            # 仍然输出空JSON，避免父进程等待超时
            print("{}")
        else:
            # 输出JSON结果到stdout，供父进程读取
            try:
                json_output = json.dumps(string_key_results, cls=NumpyEncoder)
                print(json_output)
                logging.info(f"Successfully output JSON results ({len(json_output)} characters)")
            except Exception as e:
                logging.error(f"Failed to serialize OCR results to JSON: {e}")
                # 输出空JSON作为fallback
                print("{}")

    except Exception as e:
        logging.error(f"An error occurred during OCR execution: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
