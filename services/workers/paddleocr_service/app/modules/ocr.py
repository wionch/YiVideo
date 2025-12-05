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

from services.common.progress_logger import create_stage_progress

# Configure logging
# 日志已统一管理，使用 services.common.logger

# --- Global variables for worker processes ---
full_ocr_engine_process_global = None

def _log_ocr_device_info(pid: int):
    """
    检测并记录OCR引擎实际使用的设备信息
    """
    try:
        # 检测PyTorch GPU可用性
        torch_gpu_available = torch.cuda.is_available()
        torch_device_count = torch.cuda.device_count() if torch_gpu_available else 0
        torch_device_name = torch.cuda.get_device_name(0) if torch_gpu_available and torch.cuda.device_count() > 0 else "N/A"

        # 检测PaddlePaddle GPU可用性
        try:
            import paddle
            paddle_gpu_available = paddle.device.is_compiled_with_cuda()
        except:
            paddle_gpu_available = False

        # 尝试检测当前进程使用的设备
        current_device = "unknown"
        try:
            if torch_gpu_available:
                # 尝试获取当前张量设备
                test_tensor = torch.tensor([1.0], device='cuda' if torch_gpu_available else 'cpu')
                current_device = str(test_tensor.device)
                del test_tensor
        except Exception as e:
            logger.debug(f"[PID: {pid}] 无法检测张量设备: {e}")

        # 记录设备信息
        logger.info(f"[PID: {pid}] ========== OCR设备检测 ==========")
        logger.info(f"[PID: {pid}] PyTorch GPU可用: {torch_gpu_available}")
        if torch_gpu_available:
            logger.info(f"[PID: {pid}] PyTorch GPU设备数: {torch_device_count}")
            logger.info(f"[PID: {pid}] PyTorch GPU设备名: {torch_device_name}")
        logger.info(f"[PID: {pid}] PaddlePaddle GPU可用: {paddle_gpu_available}")
        logger.info(f"[PID: {pid}] 当前计算设备: {current_device}")

        # 总结性判断
        if torch_gpu_available or paddle_gpu_available:
            logger.info(f"[PID: {pid}] ✅ OCR任务使用GPU加速")
        else:
            logger.info(f"[PID: {pid}] ℹ️ OCR任务使用CPU模式")
        logger.info(f"[PID: {pid}] ================================")

    except Exception as e:
        logger.warning(f"[PID: {pid}] 设备检测过程出错: {e}")

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

                # [新增] 确保所有子进程在任务完成后被正确终止
                try:
                    logger.debug("开始清理ProcessPoolExecutor...")
                    executor.shutdown(wait=True)
                    logger.debug("ProcessPoolExecutor已清理")
                except Exception as shutdown_e:
                    logger.warning(f"ProcessPoolExecutor清理时出现警告: {shutdown_e}")

            progress_bar.finish(f"✅ 拼接图像OCR完成")

            # 全面清理主进程GPU显存
            try:
                from services.common.gpu_memory_manager import log_gpu_memory_state, force_cleanup_gpu_memory
                log_gpu_memory_state("OCR批处理完成")
                force_cleanup_gpu_memory(aggressive=True)
                logger.info("主进程 GPU 显存已全面清理")
            except Exception as cleanup_e:
                logger.warning(f"主进程GPU显存清理失败: {cleanup_e}")
                # 降级到原有的简单清理
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("主进程 GPU 缓存已清理（降级模式）")
        except Exception as e:
            logger.error(f"Multi-process OCR failed: {e}", exc_info=True)
            progress_bar.finish(f"❌ 拼接图像OCR失败")

            # 出错时也要清理
            try:
                from services.common.gpu_memory_manager import force_cleanup_gpu_memory
                force_cleanup_gpu_memory(aggressive=True)
            except:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        return results

# --- Full OCR (Det + Rec) Worker ---
def _full_ocr_worker_initializer(full_config: Dict):
    """Initializes a full PaddleOCR engine in each worker process."""
    global full_ocr_engine_process_global
    pid = os.getpid()

    # 初始化GPU内存管理
    try:
        from services.common.gpu_memory_manager import initialize_worker_gpu_memory
        initialize_worker_gpu_memory()
        logger.info(f"[PID: {pid}] GPU内存管理初始化完成")
    except Exception as e:
        logger.warning(f"[PID: {pid}] GPU内存管理初始化失败: {e}")

    # 注册子进程退出清理函数
    try:
        import atexit
        atexit.register(_cleanup_worker_process)
        logger.debug(f"[PID: {pid}] 已注册子进程清理函数")
    except Exception as e:
        logger.warning(f"[PID: {pid}] 注册清理函数失败: {e}")

    try:
        # [修复] 基于PaddleOCR 3.x源码分析，使用正确的API参数
        try:
            # 导入通用配置加载器
            from services.common.config_loader import CONFIG

            # 获取语言设置
            lang = CONFIG.get('ocr', {}).get('lang', 'zh')
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

        # [新增] 检测并记录实际使用的设备
        _log_ocr_device_info(pid)

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

            # [新增] 记录fallback模式的设备使用情况
            _log_ocr_device_info(pid)
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

              # 清理中间变量
        del ocr_output
        del data_dict
        del image_data

        return (task_id, final_texts, final_boxes)

    except Exception as e:
        logger.error(f"Full OCR task {task_id} execution failed: {e}", exc_info=True)

        # 出错时也要清理显存
        try:
            from services.common.gpu_memory_manager import force_cleanup_gpu_memory
            force_cleanup_gpu_memory(aggressive=True)
        except:
            pass

        return (task_id, [], [])


def _cleanup_worker_process():
    """子进程退出前的完整清理流程"""
    global full_ocr_engine_process_global
    pid = os.getpid()

    try:
        logger.debug(f"[PID: {pid}] 开始清理子进程资源")

        # 1. 清理PaddleOCR引擎
        if full_ocr_engine_process_global is not None:
            try:
                # 清理PaddleOCR模型和GPU资源
                del full_ocr_engine_process_global
                full_ocr_engine_process_global = None
                logger.debug(f"[PID: {pid}] PaddleOCR引擎已清理")
            except Exception as e:
                logger.warning(f"[PID: {pid}] PaddleOCR引擎清理失败: {e}")

        # 2. 强制清理GPU显存
        try:
            from services.common.gpu_memory_manager import force_cleanup_gpu_memory
            force_cleanup_gpu_memory(aggressive=True)
            logger.debug(f"[PID: {pid}] GPU显存已强制清理")
        except Exception as e:
            logger.debug(f"[PID: {pid}] GPU显存清理失败: {e}")
            # 降级清理
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.debug(f"[PID: {pid}] GPU缓存已清理（降级模式）")
            except:
                pass

        # 3. 清理PaddlePaddle资源
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
                logger.debug(f"[PID: {pid}] PaddlePaddle显存已清理")
        except Exception as e:
            logger.debug(f"[PID: {pid}] PaddlePaddle显存清理失败: {e}")

        # 4. Python垃圾回收
        import gc
        gc.collect()

        logger.debug(f"[PID: {pid}] 子进程资源清理完成")

    except Exception as e:
        logger.error(f"[PID: {pid}] 子进程清理过程中发生错误: {e}")
