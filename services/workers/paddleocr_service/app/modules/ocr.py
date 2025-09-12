# services/workers/paddleocr_service/app/modules/ocr.py
import numpy as np
import multiprocessing
import os
import time
import cv2
import logging
import torch
from paddleocr import PaddleOCR
from typing import List, Tuple, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from ..utils.progress_logger import create_stage_progress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global variable for the OCR engine in each worker process
ocr_engine_process_global = None

class MultiProcessOCREngine:
    """
    V4: A flexible, multi-process OCR engine supporting multiple strategies.
    """
    def __init__(self, config):
        self.config = config
        self.lang = config.get('lang', 'en')
        self.num_workers = config.get('num_workers', 4)
        logging.info(f"OCR Engine loaded (V4 - Multi-Strategy), lang: {self.lang}, workers: {self.num_workers}")

    def _multiprocess_ocr_batch(self, tasks: List[Tuple[Any, Any]]) -> List[Tuple[Any, List[str], List[np.ndarray]]]:
        """
        Generic multi-process OCR batch processor.
        """
        if not tasks:
            return []

        progress_bar = create_stage_progress("OCR文本识别", len(tasks), show_rate=True, show_eta=True)
        results = []
        
        try:
            # Pass the full config to the initializer
            with ProcessPoolExecutor(
                max_workers=self.num_workers,
                initializer=_worker_initializer,
                initargs=(self.config,)
            ) as executor:
                
                future_to_task = {executor.submit(_ocr_worker_task, task): task for task in tasks}
                
                for future in as_completed(future_to_task):
                    try:
                        result = future.result(timeout=120)
                        if result:
                            results.append(result)
                        progress_bar.update(1)
                    except Exception as e:
                        task_id = future_to_task[future][0]
                        logging.error(f"Task {task_id} failed: {e}", exc_info=True)
                        progress_bar.update(1)
            
            progress_bar.finish("✅ OCR识别完成")
            
            # 主进程 GPU 资源清理
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logging.info("主进程 GPU 缓存已清理")
        except Exception as e:
            logging.error(f"Multi-process OCR failed: {e}", exc_info=True)
            progress_bar.finish("❌ OCR识别失败")
            
            # 出错时也要清理 GPU 资源
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        return results

    def recognize_keyframes_from_cache(
        self, 
        keyframe_cache: Dict[int, Any], 
        subtitle_area: Tuple[int, int, int, int], 
        total_frames: int,
        cache_strategy: str
    ) -> Dict[int, Tuple[str, Any]]:
        """
        Optimized OCR from cache, with resource cleanup.
        """
        if not keyframe_cache:
            logging.warning("关键帧缓存为空，OCR识别跳过")
            return {}

        logging.info(f"开始从 {len(keyframe_cache)} 个缓存帧进行OCR (策略: {cache_strategy})")

        tasks = list(keyframe_cache.items())
        
        # Cleanup cache right after creating the task list to free up resources
        if cache_strategy == 'memory':
            # 显式清理内存缓存
            for frame_idx in list(keyframe_cache.keys()):
                del keyframe_cache[frame_idx]
            keyframe_cache.clear()
            # 强制垃圾回收
            import gc
            gc.collect()
        elif cache_strategy == 'pic':
            for _, path in tasks:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError as e:
                    logging.warning(f"Failed to remove temp file {path}: {e}")

        raw_results = self._multiprocess_ocr_batch(tasks)
        
        ocr_results_map = {}
        x1, y1, _, _ = subtitle_area
        for frame_idx, texts, boxes in raw_results:
            if texts and boxes:
                full_text = " ".join(texts)
                all_points = np.vstack(boxes).reshape(-1, 2)
                min_x, min_y = np.min(all_points, axis=0)
                max_x, max_y = np.max(all_points, axis=0)
                
                abs_bbox = (int(x1 + min_x), int(y1 + min_y), int(x1 + max_x), int(y1 + max_y))
                ocr_results_map[frame_idx] = (full_text.strip(), abs_bbox)
            elif texts:
                 ocr_results_map[frame_idx] = (" ".join(texts).strip(), None)

        logging.info(f"完成 {len(ocr_results_map)} 个关键帧的OCR")
        
        # 清理任务列表，释放内存
        tasks.clear()
        del tasks
        
        # 强制垃圾回收
        import gc
        gc.collect()
        
        return ocr_results_map

    def recognize_stitched_images(
        self, 
        ocr_tasks: List[Dict[str, Any]],
        cache_strategy: str
    ) -> List[Dict[str, Any]]:
        """
        Performs OCR on stitched images.
        """
        if not ocr_tasks:
            return []

        logging.info(f"开始对 {len(ocr_tasks)} 个拼接图像进行OCR")
        
        tasks_for_worker = [(i, task['image']) for i, task in enumerate(ocr_tasks)]

        raw_results = self._multiprocess_ocr_batch(tasks_for_worker)

        final_results = []
        results_map = {task_id: (texts, boxes) for task_id, texts, boxes in raw_results}

        for i, original_task in enumerate(ocr_tasks):
            if i in results_map:
                texts, boxes = results_map[i]
                ocr_data = []
                for text, box in zip(texts, boxes):
                    ocr_data.append((text, box))
                
                final_results.append({
                    "meta": original_task['meta'],
                    "ocr_data": ocr_data
                })
        
        if cache_strategy == 'pic':
            for _, path in tasks_for_worker:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError as e:
                    logging.warning(f"Failed to remove temp stitched file {path}: {e}")

        logging.info(f"完成 {len(final_results)} 个拼接图像的OCR")
        
        # 清理中间数据，释放内存
        tasks_for_worker.clear()
        raw_results.clear()
        results_map.clear()
        del tasks_for_worker, raw_results, results_map
        
        # 强制垃圾回收
        import gc
        gc.collect()
        
        return final_results

# --- Multi-process Worker Functions ---

def _worker_initializer(full_config: Dict):
    """
    Initializes a PaddleOCR instance in each worker process using the original robust method.
    """
    global ocr_engine_process_global
    pid = os.getpid()
    
    try:
        # Use the original method of getting the full config
        ocr_kwargs = full_config.get('paddleocr_config', {})
        ocr_kwargs['lang'] = full_config.get('lang', 'en')
        # Ensure show_log is not passed, as it's unsupported
        ocr_kwargs.pop('show_log', None) 

        logging.info(f"[PID: {pid}] Initializing PaddleOCR with lang='{ocr_kwargs['lang']}'")
        ocr_engine_process_global = PaddleOCR(**ocr_kwargs)
        logging.info(f"[PID: {pid}] PaddleOCR engine initialized successfully.")
    except Exception as e:
        logging.error(f"[PID: {pid}] ❌ PaddleOCR engine initialization failed: {e}", exc_info=True)
        ocr_engine_process_global = None

def _worker_cleanup():
    """
    清理工作进程的 GPU 资源
    """
    global ocr_engine_process_global
    pid = os.getpid()
    
    try:
        if ocr_engine_process_global:
            # 清理 PaddleOCR 实例
            del ocr_engine_process_global
            ocr_engine_process_global = None
            
        # 清理 PaddlePaddle GPU 缓存
        import paddle
        if paddle.is_compiled_with_cuda():
            paddle.device.cuda.empty_cache()
            logging.info(f"[PID: {pid}] PaddleOCR worker GPU cache cleared")
            
    except Exception as e:
        logging.warning(f"[PID: {pid}] Worker cleanup error: {e}")

def _ocr_worker_task(task: Tuple[Any, Any]) -> Tuple[Any, List[str], List[np.ndarray]]:
    """
    The actual OCR task, using the original robust parsing logic.
    """
    global ocr_engine_process_global
    task_id, task_data = task

    if not ocr_engine_process_global:
        return (task_id, [], [])

    try:
        image_data = None
        if isinstance(task_data, str):
            if os.path.exists(task_data):
                image_data = cv2.imread(task_data)
                if image_data is None: return (task_id, [], [])
            else:
                return (task_id, [], [])
        elif isinstance(task_data, np.ndarray):
            image_data = task_data
        else:
            return (task_id, [], [])

        if isinstance(task_data, np.ndarray) and image_data.shape[2] == 3:
             image_data = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)

        # Restore the original .predict() call and parsing logic
        ocr_output = ocr_engine_process_global.predict(image_data)
        
        if not ocr_output or not isinstance(ocr_output, list) or not ocr_output[0]:
            return (task_id, [], [])

        # Original, robust parsing for the dictionary format from .predict()
        data_dict = ocr_output[0]
        positions = data_dict.get('rec_polys', [])
        texts = data_dict.get('rec_texts', [])
        
        extracted_texts = []
        extracted_boxes = []

        for i in range(len(texts)):
            if texts[i] and texts[i].strip():
                extracted_texts.append(texts[i].strip())
                if i < len(positions):
                    try:
                        box_data = positions[i]
                        # Ensure the box data is a numpy array of floats, which can be reshaped
                        box_array = np.array(box_data, dtype=np.float32)
                        if box_array.size >= 8: # A valid box has at least 4 points (8 values)
                            extracted_boxes.append(box_array.tolist())
                        else:
                            extracted_boxes.append(None) # Append a placeholder if box is invalid
                    except (ValueError, TypeError):
                        extracted_boxes.append(None)
                else:
                    extracted_boxes.append(None)

        # Filter out pairs where the box is None
        final_texts = []
        final_boxes = []
        for t, b in zip(extracted_texts, extracted_boxes):
            if b is not None:
                final_texts.append(t)
                final_boxes.append(b)

        return (task_id, final_texts, final_boxes)

    except Exception as e:
        logging.error(f"OCR task {task_id} execution failed: {e}", exc_info=True)
        return (task_id, [], [])
    finally:
        # 尽力清理工作进程中的临时资源
        try:
            import gc
            gc.collect()  # 强制垃圾回收
        except:
            pass
