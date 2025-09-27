# app/modules/area_detector.py
import gc
import itertools
import logging
import multiprocessing
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError
from concurrent.futures import as_completed
from typing import List
from typing import Tuple

import av
import numpy as np
import torch
from paddleocr import TextDetection
from paddleocr import TextRecognition

from services.common.logger import get_logger

from ..utils.progress_logger import create_stage_progress

# 导入我们自己的解码器
from .decoder import GPUDecoder
from .base_detector import BaseDetector, ConfigManager

# Configure logging
logger = get_logger('area_detector')

# Set the multiprocessing start method to 'spawn' to avoid issues with Celery.
# This must be done at the top level of the module, before any other
# multiprocessing-related code is executed.
if __name__ != '__main__':
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass # It's ok if it's already set.

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
        logger.info(f"[PID: {os.getpid()}] 收到信号 {signum}，正在清理资源...")
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
        logger.info(f"[PID: {os.getpid()}] 从配置加载语言设置: {lang}")
    except Exception as e:
        lang = 'ch'  # 后备默认值
        logger.warning(f"[PID: {os.getpid()}] 配置加载失败，使用默认语言: {lang}，错误: {e}")
    
    try:
        # 使用统一的模型配置加载器
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from utils.config_loader import get_detection_model
        from utils.config_loader import get_ocr_lang
        from utils.config_loader import get_ocr_models_config
        from utils.config_loader import get_recognition_model_for_lang

        # 获取语言设置
        lang = get_ocr_lang(default_lang='zh')
        logger.info(f"[PID: {os.getpid()}] 从配置加载语言设置: {lang}")
        
        # 获取统一的模型配置
        det_model = get_detection_model()
        rec_model = get_recognition_model_for_lang(lang)
        models_config = get_ocr_models_config()
        
        logger.info(f"[PID: {os.getpid()}] 使用模型配置: 检测={det_model}, 识别={rec_model}")
        
        # 使用PaddleOCR 3.x的分离模块API - 应用字幕场景优化设置
        worker_text_detector = TextDetection(model_name=det_model)
        worker_text_recognizer = TextRecognition(model_name=rec_model)
        
        logger.info(f"[PID: {os.getpid()}] TextDetection和TextRecognition模块初始化完成 (语言: {lang})")
        
    except Exception as e:
        logger.error(f"[PID: {os.getpid()}] OCR模块初始化失败: {e}")
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
        logger.warning(f"[PID: {pid}] 警告：OCR模块未初始化，尝试重新初始化...")
        initialize_worker()
        if worker_text_detector is None or worker_text_recognizer is None:
            logger.error(f"[PID: {pid}] OCR模块初始化失败，跳过帧 {frame_index}")
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
                            
                            # 清理识别结果，释放内存
                            del rec_result
                            
                        except Exception as rec_e:
                            # 如果识别失败，仍然保留检测框，但文本为空
                            logger.warning(f"[PID: {pid}] 文本识别失败: {rec_e}")
                            detections_with_text.append((box_np, ""))
                            
                        # 清理文本区域数据
                        del text_region
        
        process_end_time = time.time()
        process_duration = process_end_time - process_start_time
        
        # 输出处理信息 - 减少日志输出，改用进度条显示
        detection_count = len(detections_with_text)
        text_count = sum(1 for _, text in detections_with_text if len(text.strip()) > 0)
        
        # 强制垃圾回收，释放临时变量
        del det_result
        del frame  # 释放帧数据
        gc.collect()
        
        # 定期清理工作进程内存
        if frame_index % 50 == 0:  # 每处理50帧清理一次
            try:
                # 清理PaddlePaddle缓存
                import paddle
                if paddle.is_compiled_with_cuda():
                    paddle.device.cuda.empty_cache()
            except:
                pass
        
        return detections_with_text
        
    except Exception as e:
        logger.error(f"[PID: {pid}] 处理帧 {frame_index+1} 时发生错误: {e}")
        return []

class SubtitleAreaDetector(BaseDetector):
    """
    通过对视频帧进行采样和文本检测，智能确定字幕的主要区域。
    """
    def __init__(self, config):
        """
        初始化字幕区域检测器

        Args:
            config: 检测器配置
        """
        # 使用ConfigManager验证和规范化配置
        required_keys = []
        optional_keys = {
            'sample_count': 300,
            'min_text_len': 2,
            'y_padding': 10,
            'num_workers': min(multiprocessing.cpu_count(), 4),
            'frame_memory_estimate_mb': 0.307,
            'progress_interval_frames': 1000,
            'progress_interval_batches': 50
        }

        validated_config = ConfigManager.validate_config(config, required_keys, optional_keys)

        # 调用父类初始化
        super().__init__(validated_config)

        # 设置字幕区域检测器特有的配置
        self.sample_count = ConfigManager.validate_range(
            validated_config['sample_count'], 10, 1000, 'sample_count'
        )

        self.min_text_len = ConfigManager.validate_range(
            validated_config['min_text_len'], 1, 20, 'min_text_len'
        )

        self.y_padding = ConfigManager.validate_range(
            validated_config['y_padding'], 0, 50, 'y_padding'
        )

        self.num_workers = ConfigManager.validate_range(
            validated_config['num_workers'], 1, multiprocessing.cpu_count(), 'num_workers'
        )

        logger.info("字幕区域检测器已加载 (PaddleOCR 3.x API, 已恢复文本长度加权算法)。")
        logger.info(f"    - [配置] 字幕区域检测器将使用 {self.num_workers} 个工作进程。")

    def _detect_original(self, video_path: str, decoder: GPUDecoder) -> Tuple[int, int, int, int]:
        """
        执行字幕区域检测。
        """
        logger.info("开始智能检测字幕区域...")
        
        frame_samples = self._sample_frames(video_path, decoder)
        if not frame_samples:
            raise RuntimeError("无法从视频中采样到任何帧来进行字幕区域检测。")
        
        video_height, video_width = frame_samples[0].shape[:2]
        logger.info(f"  - [进度] 已采样 {len(frame_samples)} 帧，视频尺寸: {video_width}x{video_height}")

        all_detections = self._detect_text_in_samples(frame_samples)
        if not all_detections:
            logger.warning("  - [警告] 在采样帧中未能检测到任何文本框，无法确定字幕区域，任务退出")
            return None  # 返回 None 表示未检测到字幕区域
        logger.info(f"  - [进度] 在采样帧中检测到 {len(all_detections)} 个文本片段。")

        subtitle_area = self._find_stable_area(all_detections, video_width, video_height)
        logger.info(f"检测完成，最终字幕区域: {subtitle_area}")
        
        return subtitle_area

    def _sample_frames(self, video_path: str, decoder: GPUDecoder) -> List[np.ndarray]:
        """使用优化的精准采样从视频中获取指定数量的帧。"""
        # 获取视频基本信息
        total_frames = 0
        duration = 0
        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
            total_frames = stream.frames
            if total_frames == 0:
                total_frames = int(stream.duration * stream.time_base * stream.average_rate)
            duration = float(stream.duration * stream.time_base)  # 总时长（秒）
            container.close()
        except Exception as e:
            logger.warning(f"警告: 无法获取视频元数据: {e}, 使用估算值")
            duration = 300  # 估算5分钟
            total_frames = 5000

        if total_frames == 0: 
            total_frames = 5000
        if duration == 0:
            duration = 300

        logger.info(f"  - [信息] 视频时长: {duration:.1f}秒, 总帧数: {total_frames}")

        # 优化策略选择
        if total_frames <= self.sample_count * 2:
            # 短视频：使用传统方法（避免过度seek）
            logger.info(f"  - [策略] 短视频检测，使用传统采样方法")
            return self._sample_frames_traditional(video_path, decoder)
        else:
            # 长视频：使用精准采样（显著提升效率）
            logger.info(f"  - [策略] 长视频检测，使用精准采样方法")
            return self._sample_frames_precise(video_path, decoder, duration)

    def _sample_frames_traditional(self, video_path: str, decoder: GPUDecoder) -> List[np.ndarray]:
        """传统采样方法：遍历所有帧（适用于短视频）"""
        total_frames = 0
        try:
            container = av.open(video_path)
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
        
        # 创建采样进度条
        sampling_progress = create_stage_progress("帧采样", self.sample_count, show_rate=True, show_eta=False)

        for batch_tensor, _ in decoder.decode(video_path, log_progress=False):
            for frame_tensor in batch_tensor:
                if sample_idx_ptr < len(sample_indices) and current_frame_idx == sample_indices[sample_idx_ptr]:
                    frame_np = frame_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    frames.append(frame_np)
                    sample_idx_ptr += 1
                    
                    # 更新采样进度
                    sampling_progress.update(1)
                    
                    # 清理帧tensor
                    del frame_np
                    
                current_frame_idx += 1
            
            # 清理批次数据
            del batch_tensor
            
            if sample_idx_ptr >= len(sample_indices):
                break
        
        sampling_progress.finish("✅ 传统采样完成")
        return frames

    def _sample_frames_precise(self, video_path: str, decoder: GPUDecoder, duration: float) -> List[np.ndarray]:
        """精准采样方法：直接seek到目标时间点（适用于长视频）"""
        # 计算目标时间戳（均匀分布）
        target_timestamps = np.linspace(0, duration * 0.95, self.sample_count).tolist()  # 避免文件末尾
        
        # 创建采样进度条
        sampling_progress = create_stage_progress("精准采样", self.sample_count, show_rate=True, show_eta=True)
        
        frames = []
        successful_samples = 0
        failed_count = 0
        
        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
            
            # 获取视频的时间基准，用于更准确的seek
            time_base = float(stream.time_base)
            logger.info(f"  - [信息] 视频时间基准: {time_base}, 流时长: {duration:.1f}s")
            
            for i, timestamp in enumerate(target_timestamps):
                try:
                    # 使用PyAV标准的时间转换方式
                    # 将秒转换为PyAV的时间单位 (AV_TIME_BASE = 1000000)
                    seek_target = int(timestamp * av.time_base)
                    
                    # 使用标准的时间seek方式，更稳定
                    container.seek(seek_target)
                    
                    # 解码该时间点的帧 - 增加容错性
                    frame_found = False
                    frames_checked = 0
                    best_frame = None
                    best_time_diff = float('inf')
                    
                    for frame in container.decode(stream):
                        frames_checked += 1
                        if frames_checked > 20:  # 增加检查帧数到20帧
                            break
                            
                        if frame.pts is None:
                            continue
                            
                        frame_time = float(frame.pts * time_base)
                        time_diff = abs(frame_time - timestamp)
                        
                        # 记录最接近的帧
                        if time_diff < best_time_diff:
                            best_time_diff = time_diff
                            best_frame = frame
                        
                        # 找到足够接近的帧就使用（容差放宽到3.0秒）
                        if time_diff <= 3.0:
                            frame_found = True
                            break
                    
                    # 如果没有找到很接近的帧，使用最接近的帧（时间差放宽到5.0秒）
                    if not frame_found and best_frame is not None and best_time_diff <= 5.0:
                        frame = best_frame
                        frame_found = True
                    
                    if frame_found:
                        try:
                            frame_np = frame.to_ndarray(format='rgb24')
                            frames.append(frame_np)
                            successful_samples += 1
                            # 清理帧数据
                            del frame_np, frame
                        except Exception as convert_e:
                            logger.warning(f"    转换错误 {timestamp:.1f}s: {convert_e}")
                            failed_count += 1
                    else:
                        failed_count += 1
                        if i < 5:  # 只对前5次失败打印警告，减少日志噪音
                            logger.warning(f"    警告: 时间戳 {timestamp:.1f}s 采样失败 (检查了{frames_checked}帧)")
                        
                except Exception as e:
                    failed_count += 1
                    if i < 3:  # 只对前3次失败打印详细错误
                        logger.warning(f"    seek错误 {timestamp:.1f}s: {e}")
                
                # 更新进度
                sampling_progress.update(1, 成功=successful_samples, 失败=failed_count)
                
                # 调整提前终止条件，更宽松
                if i > 100 and successful_samples < i * 0.2:
                    logger.warning(f"  - [终止] 成功率过低 ({successful_samples}/{i+1})，提前终止精准采样")
                    break
            
            container.close()
            
        except Exception as e:
            logger.error(f"精准采样过程出错: {e}")
            # 回退到传统方法
            sampling_progress.finish("⚠️  精准采样失败，回退到传统方法")
            # 清理已采样的数据，避免内存泄漏
            frames.clear()
            return self._sample_frames_traditional(video_path, decoder)
        
        success_rate = successful_samples / len(target_timestamps) if target_timestamps else 0
        sampling_progress.finish(f"✅ 精准采样完成，成功率: {success_rate:.1%} ({successful_samples}/{len(target_timestamps)})")
        
        # 降低回退阈值到30%，更宽松的成功标准
        if len(frames) < self.sample_count * 0.3:
            logger.warning(f"  - [回退] 采样成功率过低 ({len(frames)}/{self.sample_count})，使用传统方法")
            # 清理当前采样结果
            frames.clear()
            return self._sample_frames_traditional(video_path, decoder)
        
        # 强制垃圾回收
        import gc
        gc.collect()
        
        return frames

    def _detect_text_in_samples(self, frames: List[np.ndarray]) -> List[Tuple[np.ndarray, str]]:
        """
        对采样帧进行文本检测和识别 (使用PaddleOCR 3.x API)。
        现在返回检测框和对应的识别文本。
        
        解决方案：使用进程上下文替代修改daemon状态，避免序列化问题。
        """
        all_detections = []
        start_time = time.time()

        # 使用配置中定义的进程数
        num_processes = self.num_workers
        
        # 创建区域检测进度条
        progress_bar = create_stage_progress("字幕区域检测", len(frames), show_rate=True, show_eta=True)

        # 准备任务数据：添加索引以便跟踪处理进度
        indexed_frames = [(i, frame) for i, frame in enumerate(frames)]
        
        try:
            # 方案1：使用独立进程上下文的 ProcessPoolExecutor
            self._process_frames_with_executor(indexed_frames, num_processes, all_detections, start_time, progress_bar)
        except Exception as e:
            logger.warning(f"    - [警告] ProcessPoolExecutor 方式失败: {e}，回退到传统 Pool 方式...")
            # 方案2：回退到独立进程上下文的 multiprocessing.Pool
            self._process_frames_with_pool(indexed_frames, num_processes, all_detections, start_time, progress_bar)

        total_elapsed = time.time() - start_time
        progress_bar.finish(f"✅ 区域检测完成，总耗时: {total_elapsed:.2f}s")
        
        return all_detections
    
    def _process_frames_with_executor(self, indexed_frames, num_processes, all_detections, start_time, progress_bar):
        """
        使用 ProcessPoolExecutor 处理帧 - 更好的异常处理和资源管理
        现在处理带有文本内容的棄测结果
        """
        logger.info("    - [方法] 使用 ProcessPoolExecutor 进行处理（独立进程上下文）")
        
        # 使用独立的进程上下文，避免影响当前进程的 daemon 状态
        ctx = multiprocessing.get_context('spawn')
        
        # 总进度条统计变量
        total_detections = 0
        total_recognized_texts = 0
        
        # 使用独立上下文的 ProcessPoolExecutor
        with ProcessPoolExecutor(
            max_workers=num_processes,
            initializer=initialize_worker,
            mp_context=ctx  # 关键：使用独立的进程上下文
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
                    
                    # 统计总数据
                    frame_detection_count = len(detections_with_text)
                    frame_text_count = sum(1 for _, text in detections_with_text if len(text.strip()) > 0)
                    total_detections += frame_detection_count
                    total_recognized_texts += frame_text_count
                    
                    # 更新进度条
                    progress_bar.update(1, 检测框=frame_detection_count, 识别文本=frame_text_count)
                        
                except TimeoutError:
                    frame_index = future_to_index[future]
                    frame_actual_index, _ = indexed_frames[frame_index] 
                    logger.warning(f"    - [警告] 帧 {frame_actual_index+1} 处理超时，跳过")
                except Exception as e:
                    frame_index = future_to_index[future]
                    frame_actual_index, _ = indexed_frames[frame_index]
                    logger.warning(f"    - [警告] 帧 {frame_actual_index+1} 处理失败: {e}")
    
    def _process_frames_with_pool(self, indexed_frames, num_processes, all_detections, start_time, progress_bar):
        """
        使用改进的 multiprocessing.Pool 处理帧 - 回退方案
        现在处理带有文本内容的检测结果
        """
        logger.info("    - [方法] 使用 multiprocessing.Pool 进行处理（独立进程上下文）")
        
        # 使用独立的进程上下文，避免影响当前进程的 daemon 状态
        ctx = multiprocessing.get_context('spawn')
        
        pool = None
        try:
            # 使用独立上下文创建进程池
            pool = ctx.Pool(
                processes=num_processes, 
                initializer=initialize_worker,
                maxtasksperchild=50  # 防止内存泄露
            )
            
            # 使用 map 而不是 imap_unordered 来确保所有任务完成
            logger.info("    - [执行] 开始批处理所有帧...")
            results = pool.map(process_frame_worker, indexed_frames)
            
            # 处理结果
            for i, detections_with_text in enumerate(results):
                if detections_with_text:  # 只处理非空结果
                    for box_np, text in detections_with_text:
                        all_detections.append((box_np, text))
                
                # 批量更新进度条
                if (i + 1) % 50 == 0 or (i + 1) == len(results):
                    total_detections = sum(len(det) for det in results[:i+1] if det)
                    total_texts = sum(sum(1 for _, text in det if len(text.strip()) > 0) for det in results[:i+1] if det)
                    progress_bar.update(50 if (i + 1) % 50 == 0 else (i + 1) % 50, 
                                      检测框=total_detections, 识别文本=total_texts)
                    
        except Exception as e:
            logger.error(f"    - [错误] 多进程处理期间发生错误: {e}")
            if pool:
                logger.info("    - [清理] 强制终止进程池...")
                pool.terminate()
                pool.join()
            raise
        finally:
            # 确保进程池被正确关闭
            if pool:
                logger.info("    - [清理] 正常关闭进程池...")
                pool.close()
                pool.join()
                logger.info("    - [清理] 进程池已关闭")

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
            logger.warning("  - [警告] 未发现足够长的文本进行加权，回退到标准区域检测。")
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

        # 使用配置中的 padding 值
        final_y_min = max(0, y_min - self.y_padding)
        final_y_max = min(height, y_max + self.y_padding)

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
        final_y_min = max(0, y_min - self.y_padding)
        final_y_max = min(height, y_max + self.y_padding)
        return (0, int(final_y_min), width, int(final_y_max))

    def detect(self, video_path: str, decoder, **kwargs) -> Tuple[int, int, int, int]:
        """
        实现基类的抽象检测方法

        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            **kwargs: 其他参数

        Returns:
            字幕区域坐标 (x1, y1, x2, y2)
        """
        self._start_processing()
        try:
            area = self._detect_original(video_path, decoder)
            return area
        finally:
            self._finish_processing()

    def get_detector_name(self) -> str:
        """
        获取检测器名称

        Returns:
            检测器名称
        """
        return "SubtitleAreaDetector"
