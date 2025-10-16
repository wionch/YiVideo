# services/workers/paddleocr_service/app/modules/ocr.py
import numpy as np

from services.common.logger import get_logger

logger = get_logger('ocr')
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

import cv2
import torch
from paddleocr import PaddleOCR

from ..utils.progress_logger import create_stage_progress

# Configure logging
# 日志已统一管理，使用 services.common.logger

# --- Global variables for worker processes ---
full_ocr_engine_process_global = None

class MultiProcessOCREngine:
    """
    V6: An optimized, multi-process OCR engine for full OCR tasks on stitched images.
    """
    def __init__(self, config):
        self.config = config
        self.lang = config.get('lang', 'en')
        self.num_workers = config.get('num_workers', 4)
        logger.info(f"OCR Engine loaded (V6), lang: {self.lang}, workers: {self.num_workers}")

    def recognize_stitched(self, ocr_tasks: List[Tuple[str, str]]) -> Dict[str, List[Tuple[str, Any]]]:
        """
        Performs full OCR on a batch of stitched images and returns a result map.

        Args:
            ocr_tasks: A list of tuples, where each tuple is (stitched_filename, image_path).

        Returns:
            A dictionary mapping each stitched_filename to its OCR result,
            which is a list of (text, box) tuples.
        """
        if not ocr_tasks:
            return {}
        
        logger.info(f"Starting batch OCR on {len(ocr_tasks)} stitched images.")

        # The worker task will return (stitched_filename, texts, boxes)
        raw_results = self._multiprocess_ocr_batch(ocr_tasks)

        # Re-assemble results into the dictionary format expected by the executor
        final_results_map = {}
        for stitched_filename, texts, boxes in raw_results:
            ocr_data_for_image = []
            for text, box in zip(texts, boxes):
                ocr_data_for_image.append((text, box))
            final_results_map[stitched_filename] = ocr_data_for_image
        
        logger.info(f"Finished batch OCR, returning results for {len(final_results_map)} images.")
        return final_results_map

    def _multiprocess_ocr_batch(self, tasks: List[Any]) -> List[Any]:
        """
        Generic multi-process OCR batch processor for the full_ocr worker.
        """
        if not tasks:
            return []

        progress_bar = create_stage_progress("拼接图像OCR", len(tasks), show_rate=True, show_eta=True)
        results = []
        ctx = multiprocessing.get_context('spawn')
        
        try:
            with ProcessPoolExecutor(
                max_workers=self.num_workers,
                initializer=_full_ocr_worker_initializer,
                initargs=(self.config,),
                mp_context=ctx
            ) as executor:
                
                future_to_task = {executor.submit(_full_ocr_worker_task, task): task for task in tasks}
                
                for future in as_completed(future_to_task):
                    try:
                        result = future.result(timeout=300)
                        if result:
                            results.append(result)
                        progress_bar.update(1)
                    except Exception as e:
                        logger.error(f"A task failed: {e}", exc_info=True)
                        progress_bar.update(1)
            
            progress_bar.finish(f"✅ 拼接图像OCR完成")
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("主进程 GPU 缓存已清理")
        except Exception as e:
            logger.error(f"Multi-process OCR failed: {e}", exc_info=True)
            progress_bar.finish(f"❌ 拼接图像OCR失败")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return results

# --- Full OCR (Det + Rec) Worker ---
def _full_ocr_worker_initializer(full_config: Dict):
    """Initializes a full PaddleOCR engine in each worker process."""
    global full_ocr_engine_process_global
    pid = os.getpid()
    try:
        # [修复] 基于PaddleOCR 3.x源码分析，使用正确的API参数
        try:
            # 导入通用配置加载器
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from utils.config_loader import get_ocr_lang

            # 获取语言设置
            lang = get_ocr_lang(default_lang='zh')
            logger.info(f"[PID: {pid}] 从配置加载语言设置: {lang}")

            # [修复] 使用PaddleOCR 3.x正确参数
            models_config = {
                'lang': lang,
                'use_textline_orientation': True,  # 新的正确参数名
                'device': None,  # 让PaddleOCR自动选择设备
            }

            logger.info(f"[PID: {pid}] 使用PaddleOCR 3.x配置: {models_config}")

        except Exception as e:
            # 回退到最简配置
            logger.warning(f"[PID: {pid}] 配置加载失败，使用最简配置: {e}")
            lang = 'en'
            models_config = {
                'lang': lang,
                'use_textline_orientation': True,
                'device': None,
            }

        logger.info(f"[PID: {pid}] Initializing PaddleOCR engine with config: {models_config}")

        # [简化] 直接使用PaddleOCR，不添加额外的参数
        full_ocr_engine_process_global = PaddleOCR(**models_config)
        logger.info(f"[PID: {pid}] Full PaddleOCR engine initialized successfully.")

    except Exception as e:
        logger.error(f"[PID: {pid}] ❌ Full PaddleOCR engine initialization failed: {e}", exc_info=True)
        # 尝试使用最简配置作为fallback
        try:
            logger.warning(f"[PID: {pid}] Attempting to initialize PaddleOCR with minimal config as fallback")
            fallback_config = {
                'lang': lang,
                'device': 'cpu',  # 强制使用CPU
            }
            full_ocr_engine_process_global = PaddleOCR(**fallback_config)
            logger.info(f"[PID: {pid}] PaddleOCR engine initialized successfully with fallback config.")
        except Exception as fallback_e:
            logger.error(f"[PID: {pid}] ❌ Fallback initialization also failed: {fallback_e}", exc_info=True)
            full_ocr_engine_process_global = None


def _full_ocr_worker_task(task: Tuple[str, str]) -> Tuple[str, List[str], List[Any]]:
    """Processes a stitched image from a file path using the full OCR engine."""
    global full_ocr_engine_process_global
    task_id, image_path = task # task_id is stitched_filename
    if not full_ocr_engine_process_global:
        return (task_id, [], [])
    
    try:
        image_data = cv2.imread(image_path)
        if image_data is None:
            logger.warning(f"Could not read image file for task {task_id}: {image_path}")
            return (task_id, [], [])

        ocr_output = full_ocr_engine_process_global.predict(image_data)

        if not ocr_output or not isinstance(ocr_output, list) or not ocr_output[0]:
            return (task_id, [], [])

        data_dict = ocr_output[0]

        # 尝试多种可能的字段名，确保兼容性
        positions = data_dict.get('dt_polys', data_dict.get('rec_polys', data_dict.get('polys', [])))
        texts = data_dict.get('rec_texts', data_dict.get('texts', data_dict.get('dt_texts', [])))
        
        final_texts = []
        final_boxes = []

        # 确保texts和positions的长度匹配
        if len(texts) != len(positions):
            # 取最小长度，避免索引越界
            min_length = min(len(texts), len(positions))
            texts = texts[:min_length]
            positions = positions[:min_length]

        for i, t in enumerate(texts):
            if t and t.strip():
                final_texts.append(t.strip())
                if i < len(positions):
                    final_boxes.append(positions[i])

        return (task_id, final_texts, final_boxes)

    except Exception as e:
        logger.error(f"Full OCR task {task_id} execution failed: {e}", exc_info=True)
        return (task_id, [], [])
