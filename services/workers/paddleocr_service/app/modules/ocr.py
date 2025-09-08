# pipeline/modules/ocr.py

import torch
import numpy as np
import multiprocessing
import os
import time
import yaml
import cv2
from paddleocr import PaddleOCR
from typing import List, Tuple, Dict, Any

from .decoder import GPUDecoder
from .change_detector import ChangeType
from ..utils.progress_logger import create_stage_progress

# 全局变量，用于多进程worker初始化
ocr_engine_process_global = None
# 全局调试计数器
debug_frame_counter = 0

class MultiProcessOCREngine:
    """
    [V3] Event-driven multiprocess OCR engine.
    使用多进程并发模式识别文本，在frames marked as needing OCR (APPEARED, CONTENT_CHANGED)
    并传递所有event types给后处理器。
    基于simple_test.py验证的多进程并发实现。
    """
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.lang = config.get('lang', 'en')
        
        # 多进程相关配置
        self.num_workers = self._get_num_workers_from_config()
        print(f"模块: OCR引擎已加载 (V3 - 多进程并发), 使用语言: {self.lang}, 工作进程数: {self.num_workers}")

    def _get_num_workers_from_config(self):
        """从配置中获取工作进程数量，如果未配置则使用默认值2"""
        # 首先尝试从ocr配置段获取num_workers
        try:
            num_workers = self.config.get('num_workers')
            if isinstance(num_workers, int) and num_workers > 0:
                print(f"从OCR配置加载：num_workers = {num_workers}")
                return num_workers
        except Exception:
            pass
            
        # 如果OCR配置段没有，尝试使用通用配置加载器（向后兼容）
        try:
            # 导入通用配置加载器
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from utils.config_loader import get_num_workers
            num_workers = get_num_workers(section='area_detector', default_workers=2)
            print(f"从通用配置加载器加载：num_workers = {num_workers}")
            return num_workers
        except Exception as e:
            print(f"通用配置加载器加载失败: {e}")
        
        print(f"警告：未找到有效的num_workers配置，将使用默认值2。")
        return 2

    def recognize(self, video_path: str, decoder: GPUDecoder, change_events: List[Tuple[int, ChangeType]], subtitle_area: Tuple[int, int, int, int], total_frames: int = 0) -> Dict[int, Tuple[str, Any, ChangeType]]:
        """
        使用多进程并发模式对必要的frames进行OCR处理。
        """
        frames_to_ocr_indices = [
            frame_idx for frame_idx, event_type in change_events 
            if event_type in [ChangeType.TEXT_APPEARED, ChangeType.CONTENT_CHANGED]
        ]

        if not frames_to_ocr_indices:
            print("没有需要OCR的关键事件。")
            # Still need to return disappearance events
            return {frame_idx: (None, None, event_type) for frame_idx, event_type in change_events}

        print(f"检测到 {len(change_events)} 个关键事件, 其中 {len(frames_to_ocr_indices)} 个需要进行OCR")
        x1, y1, x2, y2 = subtitle_area

        # 1. Decode and extract only the frames that need OCR
        key_frames_map = self._extract_key_frames(video_path, decoder, frames_to_ocr_indices, (x1, y1, x2, y2))
        if not key_frames_map:
            return {}

        # 2. 使用多进程并发处理OCR
        ocr_results_map = self._multiprocess_ocr_batch(key_frames_map, subtitle_area, total_frames)

        # 3. Construct final event-aware dictionary
        final_results = {}
        for frame_idx, event_type in change_events:
            if frame_idx in ocr_results_map:
                text, bbox = ocr_results_map[frame_idx]
                final_results[frame_idx] = (text, bbox, event_type)
            elif event_type == ChangeType.TEXT_DISAPPEARED:
                final_results[frame_idx] = (None, None, event_type)

        print("✅ OCR识别完成")
        return final_results

    def _multiprocess_ocr_batch(self, key_frames_map: Dict[int, np.ndarray], subtitle_area: Tuple[int, int, int, int], total_frames: int) -> Dict[int, Tuple[str, Any]]:
        """
        使用多进程并发处理OCR识别。
        参考simple_test.py中的test_multiprocess_concurrent实现。
        """
        # 构造worker任务列表：(frame_idx, image_data)
        worker_tasks = [(frame_idx, image_data) for frame_idx, image_data in key_frames_map.items()]
        
        # 创建OCR处理进度条
        progress_bar = create_stage_progress("OCR文本识别", len(worker_tasks), 
                                           show_rate=True, show_eta=True)
        
        ocr_results_map = {}
        pool = None
        
        # 先尝试使用ProcessPoolExecutor实现实时进度更新
        success_count = 0
        error_count = 0
        x1, y1, x2, y2 = subtitle_area
        
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            
            # 创建进程池执行器
            with ProcessPoolExecutor(
                max_workers=self.num_workers,
                initializer=_worker_initializer,
                initargs=(self.lang,)
            ) as executor:
                
                start_time = time.time()
                
                # 提交所有任务
                future_to_task = {}
                for task in worker_tasks:
                    future = executor.submit(_ocr_worker_task, task)
                    future_to_task[future] = task
                
                # 实时收集结果并更新进度条
                for future in as_completed(future_to_task, timeout=600):  # 10分钟总超时
                    try:
                        result = future.result(timeout=60)  # 单个任务60秒超时
                        
                        if result:  # 过滤掉None结果
                            frame_idx, texts, boxes = result
                            if texts and boxes:
                                # 确保texts是字符串列表
                                if isinstance(texts, list) and len(texts) > 0:
                                    full_text = " ".join(str(text) for text in texts if text)
                                    
                                    # 安全地处理boxes数据
                                    try:
                                        if boxes and len(boxes) > 0:
                                            # 确保boxes是数值类型的numpy数组
                                            valid_boxes = []
                                            for box in boxes:
                                                if isinstance(box, (list, np.ndarray)):
                                                    # 转换为float类型的numpy数组
                                                    box_array = np.array(box, dtype=np.float32)
                                                    valid_boxes.append(box_array)
                                            
                                            if valid_boxes:
                                                all_points = np.vstack(valid_boxes).reshape(-1, 2)
                                                min_x, min_y = np.min(all_points, axis=0)
                                                max_x, max_y = np.max(all_points, axis=0)
                                                
                                                abs_bbox = (int(min_x), int(min_y + y1), int(max_x), int(max_y + y1))
                                                ocr_results_map[frame_idx] = (full_text.strip(), abs_bbox)
                                                success_count += 1
                                            else:
                                                error_count += 1
                                        else:
                                            error_count += 1
                                    except Exception as box_error:
                                        error_count += 1
                                else:
                                    error_count += 1
                        else:
                            error_count += 1
                        
                        # 实时更新进度条
                        progress_bar.update(1, 成功=success_count, 失败=error_count)
                        
                    except Exception as e:
                        task = future_to_task[future]
                        frame_idx = task[0]
                        print(f"任务 {frame_idx} 处理失败: {e}")
                        error_count += 1
                        progress_bar.update(1, 成功=success_count, 失败=error_count)
                
                end_time = time.time()
                ocr_duration = end_time - start_time
                progress_bar.finish(f"✅ OCR识别完成: {len(worker_tasks)}项，耗时: {ocr_duration/60:.1f}m, 平均速率: {len(worker_tasks)/ocr_duration:.1f}/s")
            
        except Exception as e:
            print(f"ProcessPoolExecutor执行失败，回退到Pool.imap方式: {e}")
            
            # 回退到使用multiprocessing.Pool的imap方式实现实时进度
            try:
                pool = multiprocessing.Pool(
                    processes=self.num_workers, 
                    initializer=_worker_initializer,
                    initargs=(self.lang,)
                )
                
                start_time = time.time()
                
                # 使用imap而非map来获得实时结果
                results_iter = pool.imap(_ocr_worker_task, worker_tasks)
                
                success_count = 0
                error_count = 0
                
                for i, result in enumerate(results_iter):
                    if result:  # 过滤掉None结果
                        frame_idx, texts, boxes = result
                        if texts and boxes:
                            # 确保texts是字符串列表
                            if isinstance(texts, list) and len(texts) > 0:
                                full_text = " ".join(str(text) for text in texts if text)
                                
                                # 安全地处理boxes数据
                                try:
                                    if boxes and len(boxes) > 0:
                                        # 确保boxes是数值类型的numpy数组
                                        valid_boxes = []
                                        for box in boxes:
                                            if isinstance(box, (list, np.ndarray)):
                                                # 转换为float类型的numpy数组
                                                box_array = np.array(box, dtype=np.float32)
                                                valid_boxes.append(box_array)
                                        
                                        if valid_boxes:
                                            all_points = np.vstack(valid_boxes).reshape(-1, 2)
                                            min_x, min_y = np.min(all_points, axis=0)
                                            max_x, max_y = np.max(all_points, axis=0)
                                            
                                            abs_bbox = (int(min_x), int(min_y + y1), int(max_x), int(max_y + y1))
                                            ocr_results_map[frame_idx] = (full_text.strip(), abs_bbox)
                                            success_count += 1
                                        else:
                                            error_count += 1
                                    else:
                                        error_count += 1
                                except Exception as box_error:
                                    error_count += 1
                            else:
                                error_count += 1
                    else:
                        error_count += 1
                    
                    # 实时更新进度条
                    progress_bar.update(1, 成功=success_count, 失败=error_count)
                
                end_time = time.time()
                ocr_duration = end_time - start_time
                progress_bar.finish(f"✅ OCR识别完成: {len(worker_tasks)}项，耗时: {ocr_duration/60:.1f}m, 平均速率: {len(worker_tasks)/ocr_duration:.1f}/s")
                
            except Exception as e2:
                progress_bar.finish(f"❌ 多进程OCR处理失败: {e2}")
                import traceback
                traceback.print_exc()
            finally:
                if pool:
                    try:
                        pool.close()
                        pool.join()
                    except:
                        pass
        
        return ocr_results_map

    def _extract_key_frames(self, video_path: str, decoder: GPUDecoder, key_frame_indices: List[int], crop_rect: Tuple[int, int, int, int]) -> Dict[int, np.ndarray]:
        """Efficiently decodes and crops only the key frames."""
        key_frames_to_get = set(key_frame_indices)
        key_frames_map = {}
        x1, y1, x2, y2 = crop_rect
        
        # 创建调试目录 - 已注释，避免磁盘空间占用
        # debug_dir = "./pics"
        # os.makedirs(debug_dir, exist_ok=True)
        
        # 计数器，只保存前10帧 - 已注释
        # saved_count = 0
        # MAX_DEBUG_FRAMES = 10
        
        current_frame_idx = 0
        for batch_tensor, _ in decoder.decode(video_path):
            for frame_tensor in batch_tensor:
                if current_frame_idx in key_frames_to_get:
                    # 正确的tensor切片 - 已修复维度问题
                    cropped_tensor = frame_tensor[:, y1:y2, x1:x2]
                    frame_np = cropped_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    key_frames_map[current_frame_idx] = frame_np
                    
                    # 保存前10帧调试图像（阶段1：裁剪后的图像） - 已注释
                    # if saved_count < MAX_DEBUG_FRAMES:
                    #     debug_path = os.path.join(debug_dir, f"stage1_cropped_frame_{current_frame_idx:06d}.jpg")
                    #     cv2.imwrite(debug_path, cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR))
                    #     saved_count += 1
                    
                    key_frames_to_get.remove(current_frame_idx)
                
                current_frame_idx += 1
            
            if not key_frames_to_get:
                break
        
        return key_frames_map

    def recognize_keyframes(self, video_path: str, decoder: GPUDecoder, keyframes: List[int], 
                           subtitle_area: Tuple[int, int, int, int], total_frames: int = 0) -> Dict[int, Tuple[str, Any]]:
        """
        关键帧驱动的OCR识别方法 - 适配新架构
        
        基于KeyFrameDetector提供的关键帧列表进行OCR识别，
        替代原有的事件驱动模式。
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            keyframes: 关键帧索引列表 [0, 45, 89, ...]
            subtitle_area: 字幕区域坐标 (x1, y1, x2, y2)
            total_frames: 视频总帧数（用于进度显示）
            
        Returns:
            Dict[int, Tuple[str, bbox]]: 关键帧OCR结果映射
            {
                0: ("Hello World", (x1, y1, x2, y2)),
                45: ("Nice to meet you", (x1, y1, x2, y2)),
                ...
            }
        """
        if not keyframes:
            print("⚠️ 未提供关键帧列表，OCR识别跳过")
            return {}
            
        print(f"🔍 开始关键帧OCR识别: {len(keyframes)} 个关键帧")
        x1, y1, x2, y2 = subtitle_area
        
        # 1. 提取关键帧图像数据
        key_frames_map = self._extract_key_frames(video_path, decoder, keyframes, (x1, y1, x2, y2))
        if not key_frames_map:
            print("❌ 关键帧提取失败")
            return {}
            
        # 2. 使用多进程并发进行OCR识别
        ocr_results_map = self._multiprocess_ocr_batch(key_frames_map, subtitle_area, total_frames)
        
        print(f"✅ 关键帧OCR识别完成: {len(ocr_results_map)} 个结果")
        return ocr_results_map

    def recognize_keyframes_from_cache(self, keyframe_cache: Dict[int, np.ndarray], 
                                      subtitle_area: Tuple[int, int, int, int], 
                                      total_frames: int = 0) -> Dict[int, Tuple[str, Any]]:
        """
        🆕 优化方法：直接从缓存的关键帧图像进行OCR识别
        
        避免重复视频解码，直接使用关键帧检测阶段缓存的图像数据进行OCR处理。
        这是核心性能优化：消除第二次视频解码的时间开销。
        
        Args:
            keyframe_cache: 关键帧图像缓存 {frame_idx: image_array, ...}
            subtitle_area: 字幕区域坐标 (x1, y1, x2, y2) 
            total_frames: 视频总帧数（用于进度显示）
            
        Returns:
            Dict[int, Tuple[str, bbox]]: 关键帧OCR结果映射
            {
                0: ("Hello World", (x1, y1, x2, y2)),
                45: ("Nice to meet you", (x1, y1, x2, y2)),
                ...
            }
        """
        if not keyframe_cache:
            print("⚠️ 关键帧缓存为空，OCR识别跳过")
            return {}
            
        print(f"🔍 开始关键帧OCR识别: {len(keyframe_cache)} 个缓存关键帧")
        print(f"⚡ 性能优化: 跳过视频解码，直接使用缓存数据")
        
        # 使用多进程并发进行OCR识别 (复用现有逻辑)
        ocr_results_map = self._multiprocess_ocr_batch(keyframe_cache, subtitle_area, total_frames)
        
        print(f"✅ 关键帧OCR识别完成: {len(ocr_results_map)} 个结果")
        print(f"🚀 性能提升: 消除了第二次视频解码时间")
        return ocr_results_map


# --- 多进程Worker函数（模块级别函数，供multiprocessing调用） ---

def _worker_initializer(lang='en'):
    """
    多进程worker初始化函数。
    每个子进程会调用此函数来初始化自己独立的PaddleOCR实例。
    使用基于测试结果优化的统一配置。
    """
    global ocr_engine_process_global
    pid = os.getpid()
    
    # 使用通用配置加载器获取完整的 PaddleOCR 3.x 配置
    try:
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from utils.config_loader import get_paddleocr_config
        
        # 🎯 核心修复：直接获取完整的优化配置
        ocr_kwargs = get_paddleocr_config()
        print(f"[PID: {pid}] 📋 从配置文件加载 PaddleOCR 3.x 完整参数:")
        print(f"[PID: {pid}] 🎯 语言={ocr_kwargs['lang']}, 模型版本={ocr_kwargs['ocr_version']}")
        print(f"[PID: {pid}] 📊 关键参数: thresh={ocr_kwargs['text_det_thresh']}, box_thresh={ocr_kwargs['text_det_box_thresh']}")
        
    except Exception as e:
        print(f"[PID: {pid}] ⚠️  配置加载失败，使用测试验证的最佳参数: {e}")
        # 即使配置加载失败，也使用测试验证的最佳配置
        ocr_kwargs = {
            'lang': 'en',  # 🔥 测试证明英文模式效果最佳(99.96%置信度)
            'ocr_version': 'PP-OCRv5',
            'text_det_limit_side_len': 736,
            'text_det_thresh': 0.30,
            'text_det_box_thresh': 0.60,
            'text_det_unclip_ratio': 1.50,
            'text_rec_score_thresh': 0,
            'use_doc_orientation_classify': False,
            'use_doc_unwarping': False,
            'use_textline_orientation': False
        }
    
    print(f"[PID: {pid}] 🚀 开始初始化 PaddleOCR 引擎 (基于测试结果优化)...")
    
    init_start_time = time.time()
    try:
        # print(f"[PID: {pid}] PaddleOCR初始化参数: {ocr_kwargs}")
        
        # 使用PaddleOCR 3.x API初始化 - 所有参数已优化
        from paddleocr import PaddleOCR
        ocr_engine_process_global = PaddleOCR(**ocr_kwargs)
        
        init_end_time = time.time()
        init_duration = init_end_time - init_start_time
        print(f"[PID: {pid}] ✅ PaddleOCR引擎初始化成功 (语言: {ocr_kwargs['lang']}, 模型: {ocr_kwargs['ocr_version']}, 耗时: {init_duration:.2f}s)")
        
    except Exception as e:
        print(f"[PID: {pid}] ❌ PaddleOCR引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
        ocr_engine_process_global = None


def _ocr_worker_task(task_data):
    """
    多进程OCR工作任务函数。
    处理单个frame的OCR识别。
    参考simple_test.py中的ocr_worker_task实现。
    
    Args:
        task_data: (frame_idx, image_data) 元组
        
    Returns:
        (frame_idx, texts, boxes) 或 None (如果处理失败)
    """
    global ocr_engine_process_global, debug_frame_counter
    pid = os.getpid()
    frame_idx, image_data = task_data
    
    if not ocr_engine_process_global:
        print(f"[PID: {pid}] 错误: OCR引擎未正确初始化")
        return None
    
    try:
        # 🔍 关键调试：检查传递给PaddleOCR的图像数据
        # print(f"[PID: {pid}] 🔍 OCR输入调试: image_data.shape={image_data.shape}, dtype={image_data.dtype}")
        # print(f"[PID: {pid}] 🔍 预期尺寸应为字幕条: 高度~80, 宽度~1280")
        
        # 🎯 关键修复：确保图像数据格式符合PaddleOCR 3.x要求
        if image_data.dtype != np.uint8:
            print(f"[PID: {pid}] 🔧 修复dtype: {image_data.dtype} -> uint8")
            image_data = image_data.astype(np.uint8)
        
        # 确保图像数据是连续的内存布局
        if not image_data.flags['C_CONTIGUOUS']:
            print(f"[PID: {pid}] 🔧 修复内存布局: 转为连续内存")
            image_data = np.ascontiguousarray(image_data)
        
        # 检查并修复图像尺寸范围
        height, width, channels = image_data.shape
        if height > 4000 or width > 4000:
            print(f"[PID: {pid}] ⚠️  图像尺寸异常: {height}x{width}, 需要调整")
            # 这不应该发生，但作为安全检查
            max_dim = 4000
            if height > max_dim or width > max_dim:
                scale = min(max_dim/height, max_dim/width)
                new_height = int(height * scale)
                new_width = int(width * scale)
                print(f"[PID: {pid}] 🔧 缩放图像: {height}x{width} -> {new_height}x{new_width}")
                import cv2
                image_data = cv2.resize(image_data, (new_width, new_height))
        
        # print(f"[PID: {pid}] 🎯 最终输入PaddleOCR: shape={image_data.shape}, dtype={image_data.dtype}")
        
        ocr_start_time = time.time()
        # 使用predict方法替代ocr方法，与simple_test.py保持一致
        ocr_output = ocr_engine_process_global.predict(image_data)
        ocr_end_time = time.time()
        ocr_duration = ocr_end_time - ocr_start_time
        
        # OCR识别完成，减少日志输出
        
        # 解析OCR结果 - 基于simple_test.py的format_ocr_results函数处理predict方法返回的字典格式
        if ocr_output and isinstance(ocr_output, list) and len(ocr_output) > 0:
            try:
                # predict方法返回字典格式数据，参考simple_test.py的format_ocr_results实现
                if isinstance(ocr_output[0], dict):
                    # 处理字典格式数据（predict方法）
                    data_dict = ocr_output[0]
                    
                    positions = data_dict.get('rec_polys', [])
                    texts = data_dict.get('rec_texts', [])
                    confidences = data_dict.get('rec_scores', [])
                    
                    # 检测到文本区域，减少日志输出
                    
                    extracted_texts = []
                    extracted_boxes = []
                    
                    # 保存调试图像（阶段2：OCR识别后带标注的图像）
                    debug_frame_counter += 1
                    # 已注释调试图像保存功能，避免磁盘空间占用
                    # if debug_frame_counter <= 10:
                    #     _save_debug_image_with_annotations(image_data, frame_idx, positions, texts, confidences)
                    
                    for i in range(len(texts)):
                        if texts[i] and texts[i].strip():
                            extracted_texts.append(texts[i].strip())
                            
                            # 处理边界框
                            if i < len(positions):
                                try:
                                    position = positions[i]
                                    if hasattr(position, 'tolist'):
                                        box_data = position.tolist()
                                    else:
                                        box_data = position
                                    
                                    if isinstance(box_data, (list, np.ndarray)):
                                        box_array = np.array(box_data, dtype=np.float32)
                                        if box_array.size > 0 and not np.isnan(box_array).any():
                                            extracted_boxes.append(box_array.tolist())
                                            # 提取文本成功，减少日志输出
                                except Exception as box_err:
                                    # 边界框处理失败，减少日志输出
                                    pass
                    
                    return (frame_idx, extracted_texts, extracted_boxes)
                    
                else:
                    # 处理列表格式数据（ocr方法的兼容性处理）
                    texts = []
                    boxes = []
                    
                    # 解析OCR结果，减少日志输出
                    
                    # 保存调试图像（阶段2：OCR识别后带标注的图像）
                    debug_frame_counter += 1
                    # 已注释调试图像保存功能，避免磁盘空间占用
                    # if debug_frame_counter <= 10:
                    #     _save_debug_image_with_annotations_list(image_data, frame_idx, ocr_output[0])
                    
                    for i, line in enumerate(ocr_output[0]):
                        if len(line) >= 2 and line[1]:
                            # 提取文本 (line[1][0])
                            text_info = line[1]
                            if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                                text = str(text_info[0]) if text_info[0] else ""
                                if text.strip():
                                    texts.append(text.strip())
                                    # 提取文本成功，减少日志输出
                                    
                                    # 提取边界框 (line[0])
                                    if line[0] is not None:
                                        try:
                                            box_data = line[0]
                                            if isinstance(box_data, (list, np.ndarray)):
                                                box_array = np.array(box_data, dtype=np.float32)
                                                if box_array.size > 0 and not np.isnan(box_array).any():
                                                    boxes.append(box_array.tolist())
                                        except (ValueError, TypeError) as box_err:
                                            # 边界框转换失败，减少日志输出
                                            pass
                            elif isinstance(text_info, str):
                                # 兼容性处理：如果text_info直接是字符串
                                if text_info.strip():
                                    texts.append(text_info.strip())
                                    # 提取文本成功，减少日志输出
                                    
                                    # 尝试提取边界框
                                    if line[0] is not None:
                                        try:
                                            box_data = line[0]
                                            if isinstance(box_data, (list, np.ndarray)):
                                                box_array = np.array(box_data, dtype=np.float32)
                                                if box_array.size > 0 and not np.isnan(box_array).any():
                                                    boxes.append(box_array.tolist())
                                        except (ValueError, TypeError) as box_err:
                                            # 边界框转换失败，减少日志输出
                                            pass
                            else:
                                # 文本信息格式异常，减少日志输出
                                pass
                    
                    return (frame_idx, texts, boxes)
                
            except Exception as parse_error:
                # OCR结果解析失败，减少日志输出
                import traceback
                traceback.print_exc()
                return (frame_idx, [], [])
        else:
            # 未检测到文本，减少日志输出
            return (frame_idx, [], [])
            
    except Exception as e:
        # OCR处理失败，减少日志输出
        return None


def _save_debug_image_with_annotations(image_data, frame_idx, positions, texts, confidences):
    """保存带标注的调试图像（字典格式） - 已注释，避免磁盘空间占用"""
    pass
    # 原函数体已注释，避免磁盘空间占用
    # try:
    #     debug_dir = "./pics"
    #     os.makedirs(debug_dir, exist_ok=True)
    #     debug_image = image_data.copy()
    #     if len(debug_image.shape) == 3 and debug_image.shape[2] == 3:
    #         debug_image = cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR)
    #     for i, (pos, text, conf) in enumerate(zip(positions, texts, confidences)):
    #         if pos is not None and text:
    #             try:
    #                 if isinstance(pos, (list, np.ndarray)):
    #                     box = np.array(pos, dtype=np.int32)
    #                     if box.shape[0] >= 4:
    #                         cv2.polylines(debug_image, [box], True, (0, 0, 255), 2)
    #                         x = int(box[0][0])
    #                         y = int(box[3][1]) + 20
    #                         text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
    #                         cv2.rectangle(debug_image, (x, y - text_size[1] - 5), (x + text_size[0], y + 5), (0, 0, 255), -1)
    #                         cv2.putText(debug_image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    #             except Exception as box_err:
    #                 print(f"绘制边界框失败: {box_err}")
    #     debug_path = os.path.join(debug_dir, f"stage2_annotated_frame_{frame_idx:06d}.jpg")
    #     cv2.imwrite(debug_path, debug_image)
    # except Exception as e:
    #     print(f"保存调试图像失败: {e}")


def _save_debug_image_with_annotations_list(image_data, frame_idx, ocr_results):
    """保存带标注的调试图像（列表格式） - 已注释，避免磁盘空间占用"""
    pass
    # 原函数体已注释，避免磁盘空间占用
    # try:
    #     debug_dir = "./pics"
    #     os.makedirs(debug_dir, exist_ok=True)
    #     
    #     # 复制图像数据以避免修改原始数据
    #     debug_image = image_data.copy()
    #     
    #     # 转换为BGR格式用于OpenCV
    #     if len(debug_image.shape) == 3 and debug_image.shape[2] == 3:
    #         debug_image = cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR)
    #     
    #     # 绘制标注
    #     for line in ocr_results:
    #         if len(line) >= 2 and line[1]:
    #             try:
    #                 box = line[0]  # 边界框
    #                 text_info = line[1]  # 文本信息
    #                 
    #                 # 获取文本
    #                 if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
    #                     text = str(text_info[0]) if text_info[0] else ""
    #                 elif isinstance(text_info, str):
    #                     text = text_info
    #                 else:
    #                     continue
    #                 
    #                 if not text.strip():
    #                     continue
    #                 
    #                 # 绘制边界框
    #                 if box is not None and isinstance(box, (list, np.ndarray)):
    #                     box_array = np.array(box, dtype=np.int32)
    #                     if box_array.size > 0:
    #                         # 绘制红色边界框
    #                         cv2.polylines(debug_image, [box_array], True, (0, 0, 255), 2)
    #                         
    #                         # 在边界框下方绘制文本
    #                         x = int(box_array[0][0])  # 左上角x坐标
    #                         y = int(box_array[3][1]) + 20  # 左下角y坐标 + 偏移
    #                         
    #                         # 绘制文本背景
    #                         text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
    #                         cv2.rectangle(debug_image, (x, y - text_size[1] - 5), 
    #                                     (x + text_size[0], y + 5), (0, 0, 255), -1)
    #                         
    #                         # 绘制白色文本
    #                         cv2.putText(debug_image, text, (x, y), 
    #                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    #                         
    #             except Exception as box_err:
    #                 print(f"绘制边界框失败: {box_err}")
    #     
    #     # 保存图像
    #     debug_path = os.path.join(debug_dir, f"stage2_annotated_frame_{frame_idx:06d}.jpg")
    #     cv2.imwrite(debug_path, debug_image)
    #     
    # except Exception as e:
    #     print(f"保存调试图像失败: {e}")
