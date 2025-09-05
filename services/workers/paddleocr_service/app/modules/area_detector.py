# app/modules/area_detector.py
import torch
import numpy as np
from paddleocr import TextDetection, TextRecognition
from typing import Tuple, List
import time
import multiprocessing
import itertools
import signal
import sys
import gc
import os
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError

# 导入我们自己的解码器
from .decoder import GPUDecoder

# --- 多进程工作函数 ---

# 每个工作进程的全局OCR引擎实例
worker_text_detector = None
worker_text_recognizer = None

def initialize_worker():
    """
    进程池中每个工作进程的初始化函数。
    为每个进程创建独立的TextDetection和TextRecognition实例。
    """
    global worker_text_detector, worker_text_recognizer
    
    # 设置信号处理，确保子进程能够正确响应终止信号
    def signal_handler(signum, frame):
        print(f"[PID: {os.getpid()}] 收到信号 {signum}，正在清理资源...")
        try:
            if worker_text_detector:
                del worker_text_detector
            if worker_text_recognizer:
                del worker_text_recognizer
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # 使用通用配置加载器获取语言设置
    try:
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from utils.config_loader import get_ocr_lang
        lang = get_ocr_lang(default_lang='ch')
        print(f"[PID: {os.getpid()}] 从配置加载语言设置: {lang}")
    except Exception as e:
        lang = 'ch'  # 后备默认值
        print(f"[PID: {os.getpid()}] 配置加载失败，使用默认语言: {lang}，错误: {e}")
    
    try:
        # 使用PaddleOCR 3.x的分离模块API
        # 根据语言设置选择合适的模型 - 修复模型名称问题
        if lang in ['ch', 'zh', 'chinese_cht', 'japan']:
            det_model = "PP-OCRv5_server_det"
            rec_model = "PP-OCRv5_server_rec"  # PP-OCRv5主模型支持中文、繁体中文、日文、英文、拼音
        elif lang == 'en':
            det_model = "PP-OCRv5_server_det"
            rec_model = "en_PP-OCRv5_mobile_rec"  # 英文专用优化模型
        elif lang == 'korean':
            det_model = "PP-OCRv5_server_det" 
            rec_model = "korean_PP-OCRv5_mobile_rec"  # 韩文模型
        elif lang in ['latin', 'french', 'german', 'spanish', 'italian', 'portuguese']:
            det_model = "PP-OCRv5_server_det"
            rec_model = "latin_PP-OCRv5_mobile_rec"  # 拉丁语系模型
        elif lang in ['russian', 'ukrainian', 'belarusian']:
            det_model = "PP-OCRv5_server_det"
            rec_model = "eslav_PP-OCRv5_mobile_rec"  # 东斯拉夫语系模型
        elif lang == 'thai':
            det_model = "PP-OCRv5_server_det"
            rec_model = "th_PP-OCRv5_mobile_rec"  # 泰文模型
        elif lang == 'greek':
            det_model = "PP-OCRv5_server_det"
            rec_model = "el_PP-OCRv5_mobile_rec"  # 希腊文模型
        else:
            # 对于不支持的语言，回退到PP-OCRv5主模型（支持中英日等）
            det_model = "PP-OCRv5_server_det"
            rec_model = "PP-OCRv5_server_rec"
            print(f"[PID: {os.getpid()}] 语言 '{lang}' 暂不支持专用模型，使用通用PP-OCRv5模型")
        
        worker_text_detector = TextDetection(model_name=det_model)
        worker_text_recognizer = TextRecognition(model_name=rec_model)
        print(f"[PID: {os.getpid()}] TextDetection和TextRecognition模块初始化完成 (语言: {lang})")
    except Exception as e:
        print(f"[PID: {os.getpid()}] OCR模块初始化失败: {e}")
        worker_text_detector = None
        worker_text_recognizer = None

def process_frame_worker(frame_data) -> List[Tuple[np.ndarray, str]]:
    """
    在独立进程中执行的工作函数。
    它对单个帧执行文本检测和识别，返回检测框和识别文本。
    """
    global worker_text_detector, worker_text_recognizer
    
    # 解包数据
    frame_index, frame = frame_data
    pid = os.getpid()
    
    if worker_text_detector is None or worker_text_recognizer is None:
        # 如果初始化函数没有被调用（理论上不应该发生），则作为后备。
        print(f"[PID: {pid}] 警告：OCR模块未初始化，尝试重新初始化...")
        initialize_worker()
        if worker_text_detector is None or worker_text_recognizer is None:
            print(f"[PID: {pid}] OCR模块初始化失败，跳过帧 {frame_index}")
            return []

    try:
        # 记录单帧处理开始时间
        process_start_time = time.time()
        
        # 步骤1：文本检测
        det_result = worker_text_detector.predict(frame)
        
        detections_with_text = []
        
        if det_result and det_result[0]:
            det_boxes = det_result[0].get('dt_polys', [])
            
            # 步骤2：对每个检测框进行文本识别
            for box in det_boxes:
                box_np = np.array(box, dtype=np.int32)
                
                # 从原图中截取文本区域
                x_min = int(np.min(box_np[:, 0]))
                y_min = int(np.min(box_np[:, 1]))
                x_max = int(np.max(box_np[:, 0]))
                y_max = int(np.max(box_np[:, 1]))
                
                # 确保坐标在有效范围内
                x_min = max(0, x_min)
                y_min = max(0, y_min)
                x_max = min(frame.shape[1], x_max)
                y_max = min(frame.shape[0], y_max)
                
                # 截取文本区域
                if x_max > x_min and y_max > y_min:
                    text_region = frame[y_min:y_max, x_min:x_max]
                    
                    if text_region.size > 0:
                        # 对截取区域进行文本识别
                        try:
                            rec_result = worker_text_recognizer.predict(text_region)
                            text = ""
                            if rec_result and rec_result[0]:
                                text = rec_result[0].get('rec_text', '')
                            
                            detections_with_text.append((box_np, text))
                        except Exception as rec_e:
                            # 如果识别失败，仍然保留检测框，但文本为空
                            print(f"[PID: {pid}] 文本识别失败: {rec_e}")
                            detections_with_text.append((box_np, ""))
        
        process_end_time = time.time()
        process_duration = process_end_time - process_start_time
        
        # 输出处理信息
        detection_count = len(detections_with_text)
        text_count = sum(1 for _, text in detections_with_text if len(text.strip()) > 0)
        print(f"[PID: {pid}] 帧 {frame_index+1}: 检测到 {detection_count} 个文本框，成功识别 {text_count} 个文本 (总耗时: {process_duration:.4f} 秒)")
        
        # 强制垃圾回收，释放临时变量
        del det_result
        del frame  # 释放帧数据
        gc.collect()
        
        return detections_with_text
        
    except Exception as e:
        print(f"[PID: {pid}] 处理帧 {frame_index+1} 时发生错误: {e}")
        return []


class SubtitleAreaDetector:
    """
    通过对视频帧进行采样和文本检测，智能确定字幕的主要区域。
    """
    def __init__(self, config):
        self.config = config
        self.sample_count = config.get('sample_count', 300)
        self.min_text_len = config.get('min_text_len', 2) # 用于加权的最小文本长度
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        # 从配置中读取区域检测器的特定配置
        area_detector_config = self.config
        # 设置工作进程数，如果未在config.yml中指定，则使用默认值
        default_workers = min(multiprocessing.cpu_count(), 4)
        self.num_workers = area_detector_config.get('num_workers', default_workers)
        
        print("模块: 字幕区域检测器已加载 (PaddleOCR 3.x API, 已恢复文本长度加权算法)。")
        print(f"    - [配置] 字幕区域检测器将使用 {self.num_workers} 个工作进程。")

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
            print("  - [警告] 在采样帧中未能检测到任何文本框，无法确定字幕区域，任务退出")
            return None  # 返回 None 表示未检测到字幕区域
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
        """
        对采样帧进行文本检测和识别 (使用PaddleOCR 3.x API)。
        现在返回检测框和对应的识别文本。
        """
        all_detections = []
        start_time = time.time()

        # 为提高兼容性（尤其是在Windows/macOS上），设置启动方法为'spawn'
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            # 如果启动方法已经设置，则忽略错误
            pass

        # 使用配置中定义的进程数
        num_processes = self.num_workers
        print(f"    - [检测进度] 使用 {num_processes} 个进程并行处理 {len(frames)} 帧...")

        # 准备任务数据：添加索引以便跟踪处理进度
        indexed_frames = [(i, frame) for i, frame in enumerate(frames)]
        
        # 方案1：使用 ProcessPoolExecutor 替代 multiprocessing.Pool，提供更好的异常处理
        try:
            self._process_frames_with_executor(indexed_frames, num_processes, all_detections, start_time)
        except Exception as e:
            print(f"    - [警告] ProcessPoolExecutor 方式失败: {e}，回退到传统 Pool 方式...")
            # 方案2：回退到改进的 multiprocessing.Pool
            self._process_frames_with_pool(indexed_frames, num_processes, all_detections, start_time)
        
        total_elapsed = time.time() - start_time
        print(f"    - [检测进度] 所有帧处理完毕，总耗时: {total_elapsed:.2f}s")
        
        return all_detections
    
    def _process_frames_with_executor(self, indexed_frames, num_processes, all_detections, start_time):
        """
        使用 ProcessPoolExecutor 处理帧 - 更好的异常处理和资源管理
        现在处理带有文本内容的棄测结果
        """
        print("    - [方法] 使用 ProcessPoolExecutor 进行处理")
        
        with ProcessPoolExecutor(
            max_workers=num_processes,
            initializer=initialize_worker
        ) as executor:
            # 提交所有任务
            future_to_index = {}
            for i, frame_data in enumerate(indexed_frames):
                future = executor.submit(process_frame_worker, frame_data)
                future_to_index[future] = i
            
            # 收集结果
            completed_count = 0
            for future in as_completed(future_to_index, timeout=300):  # 5分钟超时
                try:
                    detections_with_text = future.result(timeout=30)  # 单个任务30秒超时
                    frame_index = future_to_index[future]
                    
                    # 添加检测结果（现在包含文本内容）
                    for box_np, text in detections_with_text:
                        all_detections.append((box_np, text))
                    
                    completed_count += 1
                    
                    # 输出详细信息
                    elapsed = time.time() - start_time
                    frame_actual_index, _ = indexed_frames[frame_index]
                    detection_count = len(detections_with_text)
                    text_count = sum(1 for _, text in detections_with_text if len(text.strip()) > 0)
                    print(f"    - [检测] 帧 {frame_actual_index+1}/{len(indexed_frames)}: 检测到 {detection_count} 个文本框，成功识别 {text_count} 个文本 (已完成: {completed_count}/{len(indexed_frames)}, 耗时: {elapsed:.2f}s)")
                        
                except TimeoutError:
                    frame_index = future_to_index[future]
                    frame_actual_index, _ = indexed_frames[frame_index] 
                    print(f"    - [警告] 帧 {frame_actual_index+1} 处理超时，跳过")
                except Exception as e:
                    frame_index = future_to_index[future]
                    frame_actual_index, _ = indexed_frames[frame_index]
                    print(f"    - [警告] 帧 {frame_actual_index+1} 处理失败: {e}")
    
    def _process_frames_with_pool(self, indexed_frames, num_processes, all_detections, start_time):
        """
        使用改进的 multiprocessing.Pool 处理帧 - 回退方案
        现在处理带有文本内容的检测结果
        """
        print("    - [方法] 使用 multiprocessing.Pool 进行处理")
        
        pool = None
        try:
            # 使用手动池管理以便更好地控制资源清理
            pool = multiprocessing.Pool(
                processes=num_processes, 
                initializer=initialize_worker,
                maxtasksperchild=50  # 防止内存泄露
            )
            
            # 使用 map 而不是 imap_unordered 来确保所有任务完成
            print("    - [执行] 开始批处理所有帧...")
            results = pool.map(process_frame_worker, indexed_frames)
            
            # 处理结果
            for i, detections_with_text in enumerate(results):
                if detections_with_text:  # 只处理非空结果
                    for box_np, text in detections_with_text:
                        all_detections.append((box_np, text))
                
                if (i + 1) % 50 == 0 or (i + 1) == len(results):
                    elapsed = time.time() - start_time
                    total_detections = sum(len(det) for det in results[:i+1] if det)
                    total_texts = sum(sum(1 for _, text in det if len(text.strip()) > 0) for det in results[:i+1] if det)
                    print(f"    - [检测进度] 已处理 {i + 1}/{len(results)} 帧，检测到 {total_detections} 个文本框，识别 {total_texts} 个文本 (耗时: {elapsed:.2f}s)")
                    
        except Exception as e:
            print(f"    - [错误] 多进程处理期间发生错误: {e}")
            if pool:
                print("    - [清理] 强制终止进程池...")
                pool.terminate()
                pool.join()
            raise
        finally:
            # 确保进程池被正确关闭
            if pool:
                print("    - [清理] 正常关闭进程池...")
                pool.close()
                pool.join()
                print("    - [清理] 进程池已关闭")

    def _find_stable_area(self, detections: List[Tuple[np.ndarray, str]], width: int, height: int) -> Tuple[int, int, int, int]:
        """恢复使用文本长度加权的字幕区域检测算法。"""
        if not detections:
            return (0, height * 2 // 3, width, height - 10)

        y_histogram = np.zeros(height, dtype=int)
        
        # 恢复关键优化: 使用文本长度作为权重进行Y轴投影
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

        # 恢复关键优化: 对视频下半部分增加权重，优先选择底部的字幕
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

        # 参照老版本设置 padding
        y_padding = 15  # 与老版本保持一致
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