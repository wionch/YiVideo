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

    def recognize(self, video_path: str, decoder: GPUDecoder, change_events: List[Tuple[int, ChangeType]], subtitle_area: Tuple[int, int, int, int]) -> Dict[int, Tuple[str, Any, ChangeType]]:
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

        print(f"检测到 {len(change_events)} 个关键事件, 其中 {len(frames_to_ocr_indices)} 个需要进行OCR...")
        x1, y1, x2, y2 = subtitle_area

        # 1. Decode and extract only the frames that need OCR
        key_frames_map = self._extract_key_frames(video_path, decoder, frames_to_ocr_indices, (x1, y1, x2, y2))
        if not key_frames_map:
            return {}

        print(f"  - [进度] 已提取 {len(key_frames_map)} 帧图像，准备进行多进程并发OCR处理...")

        # 2. 使用多进程并发处理OCR
        ocr_results_map = self._multiprocess_ocr_batch(key_frames_map, subtitle_area)
        
        print("  - [进度] 多进程OCR处理完成，开始整理结果...")

        # 3. Construct final event-aware dictionary
        final_results = {}
        for frame_idx, event_type in change_events:
            if frame_idx in ocr_results_map:
                text, bbox = ocr_results_map[frame_idx]
                final_results[frame_idx] = (text, bbox, event_type)
            elif event_type == ChangeType.TEXT_DISAPPEARED:
                final_results[frame_idx] = (None, None, event_type)

        print("OCR (多进程并发模式)完成。")
        return final_results

    def _multiprocess_ocr_batch(self, key_frames_map: Dict[int, np.ndarray], subtitle_area: Tuple[int, int, int, int]) -> Dict[int, Tuple[str, Any]]:
        """
        使用多进程并发处理OCR识别。
        参考simple_test.py中的test_multiprocess_concurrent实现。
        """
        print(f"创建 {self.num_workers} 个子进程进行并发OCR处理...")
        
        # 构造worker任务列表：(frame_idx, image_data)
        worker_tasks = [(frame_idx, image_data) for frame_idx, image_data in key_frames_map.items()]
        
        ocr_results_map = {}
        pool = None
        try:
            # 创建进程池，每个worker初始化自己的PaddleOCR实例
            pool = multiprocessing.Pool(
                processes=self.num_workers, 
                initializer=_worker_initializer,
                initargs=(self.lang,)
            )
            
            print(f"开始将 {len(worker_tasks)} 个OCR任务映射到工作进程...")
            start_time = time.time()
            
            # 使用pool.map进行并发处理
            results = pool.map(_ocr_worker_task, worker_tasks)
            
            end_time = time.time()
            ocr_duration = end_time - start_time
            print(f"多进程OCR处理耗时: {ocr_duration:.4f} 秒")
            
            # 关闭进程池 - 先关闭再join
            pool.close()
            pool.join()
            print("进程池已关闭。")
            
            # 整理结果
            x1, y1, x2, y2 = subtitle_area
            for result in results:
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
                                        print(f"  处理帧 {frame_idx}: 文本='{full_text}', 坐标={abs_bbox}")
                                    else:
                                        print(f"  帧 {frame_idx}: 无有效边界框数据")
                                else:
                                    print(f"  帧 {frame_idx}: 无边界框数据")
                            except Exception as box_error:
                                print(f"  帧 {frame_idx}: 处理边界框时出错: {box_error}")
                        else:
                            print(f"  帧 {frame_idx}: 文本数据格式异常")
            
        except Exception as e:
            print(f"多进程OCR处理期间发生错误: {e}")
            import traceback
            traceback.print_exc()
            if pool:
                try:
                    pool.terminate()
                    pool.join()
                    print("进程池已强制终止。")
                except:
                    pass
        
        return ocr_results_map

    def _extract_key_frames(self, video_path: str, decoder: GPUDecoder, key_frame_indices: List[int], crop_rect: Tuple[int, int, int, int]) -> Dict[int, np.ndarray]:
        """Efficiently decodes and crops only the key frames."""
        key_frames_to_get = set(key_frame_indices)
        key_frames_map = {}
        x1, y1, x2, y2 = crop_rect
        
        # 创建调试目录
        debug_dir = "/app/pics"
        os.makedirs(debug_dir, exist_ok=True)
        
        # 计数器，只保存前10帧
        saved_count = 0
        MAX_DEBUG_FRAMES = 10
        
        current_frame_idx = 0
        for batch_tensor, _ in decoder.decode(video_path):
            for frame_tensor in batch_tensor:
                if current_frame_idx in key_frames_to_get:
                    cropped_tensor = frame_tensor[:, y1:y2, x1:x2]
                    frame_np = cropped_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    key_frames_map[current_frame_idx] = frame_np
                    
                    # 保存前10帧调试图像（阶段1：裁剪后的图像）
                    if saved_count < MAX_DEBUG_FRAMES:
                        debug_path = os.path.join(debug_dir, f"stage1_cropped_frame_{current_frame_idx:06d}.jpg")
                        cv2.imwrite(debug_path, cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR))
                        saved_count += 1
                    
                    key_frames_to_get.remove(current_frame_idx)
                
                current_frame_idx += 1
            
            if not key_frames_to_get:
                break
        
        return key_frames_map


# --- 多进程Worker函数（模块级别函数，供multiprocessing调用） ---

def _worker_initializer(lang='en'):
    """
    多进程worker初始化函数。
    每个子进程会调用此函数来初始化自己独立的PaddleOCR实例。
    参考simple_test.py中的worker_initializer实现。
    """
    global ocr_engine_process_global
    pid = os.getpid()
    
    # 使用通用配置加载器获取语言设置（优先级高于参数传递）
    try:
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from utils.config_loader import get_ocr_lang
        actual_lang = get_ocr_lang(default_lang=lang)
        print(f"[PID: {pid}] 从配置加载语言设置: {actual_lang} (原参数: {lang})")
        lang = actual_lang
    except Exception as e:
        print(f"[PID: {pid}] 配置加载失败，使用传入参数语言: {lang}，错误: {e}")
    
    # 修正语言代码映射，确保与PaddleOCR兼容
    paddleocr_lang_map = {
        'zh': 'ch',  # 中文简体
        'chinese': 'ch',
        'chinese_cht': 'chinese_cht',  # 中文繁体
        'en': 'en',  # 英文
        'english': 'en',
        'ja': 'japan',  # 日文
        'japan': 'japan',
        'ko': 'korean',  # 韩文
        'korean': 'korean',
        'fr': 'french',  # 法文
        'french': 'french',
        'de': 'german',  # 德文
        'german': 'german',
        'it': 'it',  # 意大利文
        'es': 'es',  # 西班牙文
        'pt': 'pt',  # 葡萄牙文
        'ru': 'ru',  # 俄文
        'th': 'th',  # 泰文
        'ar': 'ar',  # 阿拉伯文
    }
    
    # 转换语言代码
    paddleocr_lang = paddleocr_lang_map.get(lang, 'ch')  # 默认使用中文
    if paddleocr_lang != lang:
        print(f"[PID: {pid}] 语言代码转换: {lang} -> {paddleocr_lang}")
    
    print(f"[PID: {pid}] 开始初始化独立的PaddleOCR引擎 (语言: {paddleocr_lang})...")
    
    init_start_time = time.time()
    try:
        # 使用转换后的语言代码初始化PaddleOCR
        ocr_engine_process_global = PaddleOCR(lang=paddleocr_lang)
        init_end_time = time.time()
        init_duration = init_end_time - init_start_time
        print(f"[PID: {pid}] PaddleOCR引擎初始化完成 (语言: {paddleocr_lang}, 耗时: {init_duration:.4f} 秒)。")
    except Exception as e:
        print(f"[PID: {pid}] PaddleOCR引擎初始化失败: {e}")
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
        ocr_start_time = time.time()
        # 使用predict方法替代ocr方法，与simple_test.py保持一致
        ocr_output = ocr_engine_process_global.predict(image_data)
        ocr_end_time = time.time()
        ocr_duration = ocr_end_time - ocr_start_time
        
        print(f"[PID: {pid}] 帧 {frame_idx}: OCR识别完成 (耗时: {ocr_duration:.4f} 秒)")
        
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
                    
                    print(f"[PID: {pid}] 帧 {frame_idx}: 检测到 {len(texts)} 个文本区域 (字典格式)")
                    
                    extracted_texts = []
                    extracted_boxes = []
                    
                    # 保存调试图像（阶段2：OCR识别后带标注的图像）
                    debug_frame_counter += 1
                    if debug_frame_counter <= 10:
                        _save_debug_image_with_annotations(image_data, frame_idx, positions, texts, confidences)
                    
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
                                            print(f"[PID: {pid}] 帧 {frame_idx}: 提取文本 '{texts[i]}'，置信度: {confidences[i] if i < len(confidences) else 'N/A'}")
                                except Exception as box_err:
                                    print(f"[PID: {pid}] 帧 {frame_idx}: 边界框处理失败: {box_err}")
                    
                    return (frame_idx, extracted_texts, extracted_boxes)
                    
                else:
                    # 处理列表格式数据（ocr方法的兼容性处理）
                    texts = []
                    boxes = []
                    
                    print(f"[PID: {pid}] 帧 {frame_idx}: 解析OCR结果，检测到 {len(ocr_output[0])} 个文本区域 (列表格式)")
                    
                    # 保存调试图像（阶段2：OCR识别后带标注的图像）
                    debug_frame_counter += 1
                    if debug_frame_counter <= 10:
                        _save_debug_image_with_annotations_list(image_data, frame_idx, ocr_output[0])
                    
                    for i, line in enumerate(ocr_output[0]):
                        if len(line) >= 2 and line[1]:
                            # 提取文本 (line[1][0])
                            text_info = line[1]
                            if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                                text = str(text_info[0]) if text_info[0] else ""
                                if text.strip():
                                    texts.append(text.strip())
                                    print(f"[PID: {pid}] 帧 {frame_idx}: 提取文本: '{text}'")
                                    
                                    # 提取边界框 (line[0])
                                    if line[0] is not None:
                                        try:
                                            box_data = line[0]
                                            if isinstance(box_data, (list, np.ndarray)):
                                                box_array = np.array(box_data, dtype=np.float32)
                                                if box_array.size > 0 and not np.isnan(box_array).any():
                                                    boxes.append(box_array.tolist())
                                        except (ValueError, TypeError) as box_err:
                                            print(f"[PID: {pid}] 帧 {frame_idx}: 边界框转换失败: {box_err}")
                            elif isinstance(text_info, str):
                                # 兼容性处理：如果text_info直接是字符串
                                if text_info.strip():
                                    texts.append(text_info.strip())
                                    print(f"[PID: {pid}] 帧 {frame_idx}: 提取文本(字符串): '{text_info}'")
                                    
                                    # 尝试提取边界框
                                    if line[0] is not None:
                                        try:
                                            box_data = line[0]
                                            if isinstance(box_data, (list, np.ndarray)):
                                                box_array = np.array(box_data, dtype=np.float32)
                                                if box_array.size > 0 and not np.isnan(box_array).any():
                                                    boxes.append(box_array.tolist())
                                        except (ValueError, TypeError) as box_err:
                                            print(f"[PID: {pid}] 帧 {frame_idx}: 边界框转换失败: {box_err}")
                            else:
                                print(f"[PID: {pid}] 帧 {frame_idx}: 文本信息格式异常: {type(text_info)}")
                    
                    return (frame_idx, texts, boxes)
                
            except Exception as parse_error:
                print(f"[PID: {pid}] 帧 {frame_idx}: OCR结果解析失败: {parse_error}")
                import traceback
                traceback.print_exc()
                return (frame_idx, [], [])
        else:
            print(f"[PID: {pid}] 帧 {frame_idx}: 未检测到文本")
            return (frame_idx, [], [])
            
    except Exception as e:
        print(f"[PID: {pid}] 帧 {frame_idx}: OCR处理失败: {e}")
        return None


def _save_debug_image_with_annotations(image_data, frame_idx, positions, texts, confidences):
    """保存带标注的调试图像（字典格式）"""
    try:
        debug_dir = "/app/pics"
        os.makedirs(debug_dir, exist_ok=True)
        
        # 复制图像数据以避免修改原始数据
        debug_image = image_data.copy()
        
        # 转换为BGR格式用于OpenCV
        if len(debug_image.shape) == 3 and debug_image.shape[2] == 3:
            debug_image = cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR)
        
        # 绘制标注
        for i, (pos, text, conf) in enumerate(zip(positions, texts, confidences)):
            if pos is not None and text:
                try:
                    # 转换边界框坐标
                    if isinstance(pos, (list, np.ndarray)):
                        box = np.array(pos, dtype=np.int32)
                        if box.shape[0] >= 4:  # 确保至少有4个点
                            # 绘制红色边界框
                            cv2.polylines(debug_image, [box], True, (0, 0, 255), 2)
                            
                            # 在边界框下方绘制文本
                            x = int(box[0][0])  # 左上角x坐标
                            y = int(box[3][1]) + 20  # 左下角y坐标 + 偏移
                            
                            # 绘制文本背景
                            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                            cv2.rectangle(debug_image, (x, y - text_size[1] - 5), 
                                        (x + text_size[0], y + 5), (0, 0, 255), -1)
                            
                            # 绘制白色文本
                            cv2.putText(debug_image, text, (x, y), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                except Exception as box_err:
                    print(f"绘制边界框失败: {box_err}")
        
        # 保存图像
        debug_path = os.path.join(debug_dir, f"stage2_annotated_frame_{frame_idx:06d}.jpg")
        cv2.imwrite(debug_path, debug_image)
        
    except Exception as e:
        print(f"保存调试图像失败: {e}")


def _save_debug_image_with_annotations_list(image_data, frame_idx, ocr_results):
    """保存带标注的调试图像（列表格式）"""
    try:
        debug_dir = "/app/pics"
        os.makedirs(debug_dir, exist_ok=True)
        
        # 复制图像数据以避免修改原始数据
        debug_image = image_data.copy()
        
        # 转换为BGR格式用于OpenCV
        if len(debug_image.shape) == 3 and debug_image.shape[2] == 3:
            debug_image = cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR)
        
        # 绘制标注
        for line in ocr_results:
            if len(line) >= 2 and line[1]:
                try:
                    box = line[0]  # 边界框
                    text_info = line[1]  # 文本信息
                    
                    # 获取文本
                    if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                        text = str(text_info[0]) if text_info[0] else ""
                    elif isinstance(text_info, str):
                        text = text_info
                    else:
                        continue
                    
                    if not text.strip():
                        continue
                    
                    # 绘制边界框
                    if box is not None and isinstance(box, (list, np.ndarray)):
                        box_array = np.array(box, dtype=np.int32)
                        if box_array.size > 0:
                            # 绘制红色边界框
                            cv2.polylines(debug_image, [box_array], True, (0, 0, 255), 2)
                            
                            # 在边界框下方绘制文本
                            x = int(box_array[0][0])  # 左上角x坐标
                            y = int(box_array[3][1]) + 20  # 左下角y坐标 + 偏移
                            
                            # 绘制文本背景
                            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                            cv2.rectangle(debug_image, (x, y - text_size[1] - 5), 
                                        (x + text_size[0], y + 5), (0, 0, 255), -1)
                            
                            # 绘制白色文本
                            cv2.putText(debug_image, text, (x, y), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                            
                except Exception as box_err:
                    print(f"绘制边界框失败: {box_err}")
        
        # 保存图像
        debug_path = os.path.join(debug_dir, f"stage2_annotated_frame_{frame_idx:06d}.jpg")
        cv2.imwrite(debug_path, debug_image)
        
    except Exception as e:
        print(f"保存调试图像失败: {e}")
