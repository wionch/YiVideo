# services/workers/paddleocr_service/app/modules/ocr.py
import numpy as np
import multiprocessing
import os
import cv2
import logging
import torch
from paddleocr import PaddleOCR
from typing import List, Tuple, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from ..utils.progress_logger import create_stage_progress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        logging.info(f"OCR Engine loaded (V6), lang: {self.lang}, workers: {self.num_workers}")

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
        
        logging.info(f"Starting batch OCR on {len(ocr_tasks)} stitched images.")

        # The worker task will return (stitched_filename, texts, boxes)
        raw_results = self._multiprocess_ocr_batch(ocr_tasks)

        # Re-assemble results into the dictionary format expected by the executor
        final_results_map = {}
        for stitched_filename, texts, boxes in raw_results:
            ocr_data_for_image = []
            for text, box in zip(texts, boxes):
                ocr_data_for_image.append((text, box))
            final_results_map[stitched_filename] = ocr_data_for_image
        
        logging.info(f"Finished batch OCR, returning results for {len(final_results_map)} images.")
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
                        logging.error(f"A task failed: {e}", exc_info=True)
                        progress_bar.update(1)
            
            progress_bar.finish(f"✅ 拼接图像OCR完成")
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logging.info("主进程 GPU 缓存已清理")
        except Exception as e:
            logging.error(f"Multi-process OCR failed: {e}", exc_info=True)
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
        ocr_config = full_config.get('ocr', {})
        paddle_config = ocr_config.get('paddleocr_config', {})
        lang = ocr_config.get('lang', 'en')

        logging.info(f"[PID: {pid}] Initializing full PaddleOCR engine for lang '{lang}'")
        
        full_ocr_engine_process_global = PaddleOCR(lang=lang, **paddle_config)
        logging.info(f"[PID: {pid}] Full PaddleOCR engine initialized successfully.")

    except Exception as e:
        logging.error(f"[PID: {pid}] ❌ Full PaddleOCR engine initialization failed: {e}", exc_info=True)
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
            logging.warning(f"Could not read image file for task {task_id}: {image_path}")
            return (task_id, [], [])

        ocr_output = full_ocr_engine_process_global.predict(image_data)
        
        if not ocr_output or not isinstance(ocr_output, list) or not ocr_output[0]:
            return (task_id, [], [])

        data_dict = ocr_output[0]
        positions = data_dict.get('rec_polys', [])
        texts = data_dict.get('rec_texts', [])
        
        final_texts = []
        final_boxes = []
        for i, t in enumerate(texts):
            if t and t.strip():
                final_texts.append(t.strip())
                if i < len(positions):
                    final_boxes.append(positions[i])

        return (task_id, final_texts, final_boxes)

    except Exception as e:
        logging.error(f"Full OCR task {task_id} execution failed: {e}", exc_info=True)
        return (task_id, [], [])
