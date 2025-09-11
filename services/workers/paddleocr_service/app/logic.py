# services/workers/paddleocr_service/app/logic.py
import yaml
import os
import av
import torch
import paddle
import numpy as np
from typing import List, Dict, Tuple, Any
import uuid
import shutil
import cv2
import logging
import time

# Correctly import modules from the new location
from app.modules.decoder import GPUDecoder
from app.modules.area_detector import SubtitleAreaDetector
from app.modules.keyframe_detector import KeyFrameDetector
from app.modules.ocr import MultiProcessOCREngine
from app.modules.postprocessor import SubtitlePostprocessor
from app.utils.progress_logger import create_stage_progress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _get_video_metadata(video_path: str) -> Tuple[float, int]:
    """获取视频的帧率和总帧数"""
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            fps = stream.average_rate
            total_frames = stream.frames
            if total_frames == 0:
                total_frames = int(stream.duration * stream.time_base * fps)
            return float(fps), total_frames
    except (av.AVError, IndexError) as e:
        logging.warning(f"无法准确获取视频元数据: {e}. 将使用估算值。")
        return 25.0, 99999

def _prepare_ocr_tasks(frame_cache: Dict, concat_config: Dict, temp_dir: str, cache_strategy: str) -> List[Dict[str, Any]]:
    """
    将帧缓存按批次拼接成适合OCR的大图任务。
    """
    tasks = []
    frames = sorted(frame_cache.items())
    batch_size = concat_config.get('concat_batch_size', 20)

    progress_bar = create_stage_progress("拼接OCR图像", len(frames), show_rate=False, show_eta=True)

    for i in range(0, len(frames), batch_size):
        batch = frames[i:i+batch_size]
        images_to_concat = []
        
        for _, frame_data in batch:
            if isinstance(frame_data, str): # 'pic' mode
                img = cv2.imread(frame_data)
                if img is not None:
                    images_to_concat.append(img)
            else: # 'memory' mode
                images_to_concat.append(frame_data)

        if not images_to_concat:
            progress_bar.update(len(batch))
            continue

        stitched_image = cv2.vconcat(images_to_concat)
        metadata = []
        y_offset = 0
        for (frame_idx, _), img in zip(batch, images_to_concat):
            height = img.shape[0]
            metadata.append({"frame_idx": frame_idx, "y_offset": y_offset, "height": height})
            y_offset += height
        
        task_image_data = stitched_image
        if cache_strategy == 'pic':
            task_path = os.path.join(temp_dir, 'stitched', f'stitched_{i//batch_size}.jpg')
            cv2.imwrite(task_path, stitched_image)
            task_image_data = task_path

        tasks.append({"image": task_image_data, "meta": metadata})
        progress_bar.update(len(batch))
    
    progress_bar.finish("✅ 拼接完成")
    return tasks

def _transform_coordinates(ocr_results: List[Dict[str, Any]], subtitle_area: Tuple[int, int, int, int]) -> Dict[int, Tuple[str, Any]]:
    """
    将拼接大图OCR结果中的相对坐标转换回原始视频帧的绝对坐标。
    """
    transformed_results = {}
    x1_global, y1_global, _, _ = subtitle_area

    for task_result in ocr_results:
        meta_list = task_result.get('meta', [])
        for text, box in task_result.get('ocr_data', []):
            if box is None:
                continue

            box_points = np.array(box).reshape(4, 2)
            min_x, min_y = np.min(box_points, axis=0)
            max_x, max_y = np.max(box_points, axis=0)

            for meta in meta_list:
                if meta['y_offset'] <= min_y < meta['y_offset'] + meta['height']:
                    real_x1 = int(x1_global + min_x)
                    real_y1 = int(y1_global + (min_y - meta['y_offset']))
                    real_x2 = int(x1_global + max_x)
                    real_y2 = int(y1_global + (max_y - meta['y_offset']))
                    
                    frame_idx = meta['frame_idx']
                    if frame_idx not in transformed_results:
                        transformed_results[frame_idx] = (text, (real_x1, real_y1, real_x2, real_y2))
                    else:
                        existing_text, existing_box = transformed_results[frame_idx]
                        new_text = existing_text + " " + text
                        ex1, ey1, ex2, ey2 = existing_box
                        new_box = (min(ex1, real_x1), min(ey1, real_y1), max(ex2, real_x2), max(ey2, real_y2))
                        transformed_results[frame_idx] = (new_text, new_box)
                    break
    return transformed_results

def extract_subtitles_from_video(video_path: str, config: Dict) -> List[Dict[str, Any]]:
    """
    从视频文件中提取字幕的核心逻辑函数 - V2 优化版
    """
    # 记录开始时间
    start_time = time.time()
    
    pipeline_config = config.get('pipeline', {})
    detect_kf = pipeline_config.get('detect_keyframes', True)
    use_concat = pipeline_config.get('use_image_concat', False)
    cache_strategy = pipeline_config.get('frame_cache_strategy', 'memory')

    logging.info(f"流水线策略: 关键帧={detect_kf}, 拼接={use_concat}, 缓存={cache_strategy}")

    task_id = uuid.uuid4().hex
    temp_dir = os.path.join('./tmp', task_id)
    if cache_strategy == 'pic':
        os.makedirs(os.path.join(temp_dir, 'frames'), exist_ok=True)
        if use_concat:
            os.makedirs(os.path.join(temp_dir, 'stitched'), exist_ok=True)

    try:
        decoder = GPUDecoder(config.get('decoder', {}))
        area_detector = SubtitleAreaDetector(config.get('area_detector', {}))
        keyframe_detector = KeyFrameDetector(config.get('keyframe_detector', {}))
        ocr_engine = MultiProcessOCREngine(config.get('ocr', {}))
        postprocessor = SubtitlePostprocessor(config.get('postprocessor', {}))
        
        fps, total_frames = _get_video_metadata(video_path)
        logging.info(f"视频信息: {fps:.1f}fps, {total_frames}帧")

        subtitle_area = area_detector.detect(video_path, decoder)
        if subtitle_area is None:
            logging.error("未能检测到字幕区域，任务结束")
            return []
        logging.info(f"字幕区域: {subtitle_area}")

        frame_cache = {}
        x1, y1, x2, y2 = subtitle_area
        
        if detect_kf:
            logging.info("模式: 关键帧检测")
            keyframes, cached_images = keyframe_detector.detect_keyframes_with_cache(video_path, decoder, subtitle_area)
            if not keyframes:
                logging.warning("未检测到关键帧，任务结束")
                return []
            
            if cache_strategy == 'pic':
                for frame_idx, img_data in cached_images.items():
                    path = os.path.join(temp_dir, 'frames', f'{frame_idx}.jpg')
                    cv2.imwrite(path, cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR))
                    frame_cache[frame_idx] = path
            else: # memory
                frame_cache = cached_images
        else:
            logging.warning("模式: 全帧处理 (此模式将导致处理速度大幅下降)")
            current_frame_idx = 0
            for batch_tensor, _ in decoder.decode_gpu(video_path, log_progress=True):
                for frame_tensor in batch_tensor:
                    cropped_tensor = frame_tensor[:, y1:y2, x1:x2]
                    frame_np = cropped_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    
                    if cache_strategy == 'pic':
                        path = os.path.join(temp_dir, 'frames', f'{current_frame_idx}.jpg')
                        cv2.imwrite(path, cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR))
                        frame_cache[current_frame_idx] = path
                    else: # memory
                        frame_cache[current_frame_idx] = frame_np
                    current_frame_idx += 1
        
        logging.info(f"缓存了 {len(frame_cache)} 帧图像 (策略: {cache_strategy})")

        if use_concat:
            logging.info("模式: 拼接OCR")
            ocr_tasks = _prepare_ocr_tasks(frame_cache, pipeline_config, temp_dir, cache_strategy)
            raw_results = ocr_engine.recognize_stitched_images(ocr_tasks, cache_strategy)
            ocr_results = _transform_coordinates(raw_results, subtitle_area)
        else:
            logging.info("模式: 独立OCR")
            ocr_results = ocr_engine.recognize_keyframes_from_cache(frame_cache, subtitle_area, total_frames, cache_strategy)

        if detect_kf:
            segments = keyframe_detector.generate_subtitle_segments(keyframes, fps, total_frames)
            final_subtitles = postprocessor.format_from_keyframes(segments, ocr_results, fps)
        else:
            logging.warning("全帧模式的后处理使用基本格式化，可能不适用于所有场景。")
            final_subtitles = postprocessor.format_from_full_frames(ocr_results, fps)

        # 计算执行时间并输出有效字幕统计信息
        execution_time = time.time() - start_time
        logging.info(f"获取有效字幕: {len(final_subtitles)}条. 执行时间: {execution_time:.2f}秒")
        
        logging.info(f"字幕提取完成，共生成 {len(final_subtitles)} 条字幕")
        return final_subtitles

    except Exception as e:
        logging.error(f"字幕提取过程中发生严重错误: {e}", exc_info=True)
        return []
    finally:
        # 显式清理 PyTorch 和 PaddlePaddle 的 GPU 缓存
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logging.info("PyTorch CUDA cache cleared.")
            if paddle.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
                logging.info("PaddlePaddle CUDA cache cleared.")
        except Exception as cleanup_error:
            logging.warning(f"An error occurred during GPU cache cleanup: {cleanup_error}")

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logging.info(f"清理临时目录: {temp_dir}")