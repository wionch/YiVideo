# -*- coding: utf-8 -*- 

import json
import logging
import math
import multiprocessing
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path

import numpy as np

from services.common.logger import get_logger

# 配置日志记录
logger = get_logger('video_decoder')

def get_video_info(video_path: str) -> dict:
    frame_count = 0
    try:
        command = ['mediainfo', '--Output=Video;%FrameCount%', video_path]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        frame_count = int(result.stdout.strip())
    except FileNotFoundError:
        logger.error("错误: 'mediainfo' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.warning(f"使用 mediainfo 获取帧数失败: {e}")
        pass

    duration = 0.0
    try:
        command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        duration = float(result.stdout.strip())
    except FileNotFoundError:
        logger.error("错误: 'ffprobe' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.warning(f"使用 ffprobe 获取时长失败: {e}")
        if frame_count == 0:
            return None

    return {
        'frame_count': frame_count,
        'duration': duration
    }

def split_video_fast(video_path: str, output_dir: str, num_splits: int) -> list:
    video_info = get_video_info(video_path)
    if not video_info or video_info['duration'] == 0:
        logger.error(f"无法获取视频 '{video_path}' 的时长信息，分割失败。")
        return []

    total_duration = video_info['duration']
    segment_duration = total_duration / num_splits

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    output_pattern = os.path.join(output_dir, 'segment_%03d.mp4')
    
    command = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        '-c', 'copy',
        '-map', '0',
        '-f', 'segment',
        '-segment_time', str(segment_duration),
        '-reset_timestamps', '1',
        output_pattern
    ]

    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        generated_files = [os.path.join(output_dir, f) for f in sorted(os.listdir(output_dir)) if f.startswith('segment_')]
        return generated_files
    except subprocess.CalledProcessError as e:
        logger.error(f"错误：ffmpeg 快速分割失败。\nFFmpeg Stderr: {e.stderr.strip()}")
        return []
    except FileNotFoundError:
        logger.error("错误: 'ffmpeg' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return []

def _decode_concurrently_worker(args):
    video_path, output_dir, start_frame, crop_filter, process_index = args
    start_time = time.perf_counter()
    
    frames_dir = os.path.join(output_dir, 'frames')
    output_pattern = os.path.join(frames_dir, '%08d.jpg')
    
    command = [
        'ffmpeg',
        '-hide_banner',
        '-hwaccel', 'cuda',
        '-c:v', 'h264_cuvid',
        '-i', video_path,
        '-start_number', str(start_frame),
        '-q:v', '2',
    ]

    if crop_filter:
        command.extend(['-vf', crop_filter])

    command.extend(['-f', 'image2', output_pattern])
    
    success = False
    error_message = ""
    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300, encoding='utf-8', errors='ignore')
        success = True
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip()
    except Exception as e:
        error_message = str(e)
        
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    return {
        'process_index': process_index,
        'video_path': os.path.basename(video_path),
        'duration': duration,
        'success': success,
        'error': error_message
    }

def decode_video_concurrently(video_path: str, output_dir: str, num_processes: int = 10, crop_area: list = None):
    total_start_time = time.time()
    logger.info(f"开始视频并发解码任务: {video_path}")
    num_processes = min(10, num_processes)
    
    frames_dir = os.path.join(output_dir, "frames")
    segments_dir = os.path.join(output_dir, "segments")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(frames_dir)
    os.makedirs(segments_dir)
    logger.info(f"输出目录已创建并清理: {output_dir}")

    task_data = {
        "video_path": video_path,
        "output_dir": output_dir,
        "num_processes": num_processes,
        "crop_area": crop_area,
        "decoding_stats": [],
    }

    logger.info("正在获取视频信息...")
    video_info = get_video_info(video_path)
    if not video_info or not video_info.get('duration') or not video_info.get('frame_count'):
        msg = "获取视频信息失败，任务终止。"
        logger.error(msg)
        return {"status": False, "msg": msg}
    
    task_data.update({
        'total_frames': video_info['frame_count'],
        'total_duration': video_info['duration']
    })
    logger.info(f"视频信息获取成功: 总时长={task_data['total_duration']:.2f}s, 总帧数={task_data['total_frames']}")

    logger.info(f"正在将视频快速分割成 {num_processes} 段...")
    split_start_time = time.time()
    
    segments = split_video_fast(video_path, segments_dir, num_processes)
    
    if not segments:
        msg = "视频分割失败。"
        logger.error(msg)
        return {"status": False, "msg": msg}

    split_duration = time.time() - split_start_time
    task_data['split_duration'] = split_duration
    logger.info(f"视频分割成功，耗时: {split_duration:.2f} 秒，生成 {len(segments)} 个片段。")

    logger.info("正在并发获取所有子视频的帧数信息...")
    with ThreadPoolExecutor() as executor:
        future_to_path = {executor.submit(get_video_info, path): path for path in segments}
        info_map = {}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                info = future.result()
                info_map[path] = info['frame_count'] if info else 0
            except Exception as e:
                logger.warning(f"获取片段 '{os.path.basename(path)}' 信息时出错: {e}")
                info_map[path] = 0
    
    sorted_infos = [(path, info_map.get(path, 0)) for path in segments]

    crop_filter = None
    if crop_area and len(crop_area) == 4:
        x1, y1, x2, y2 = crop_area
        width = x2 - x1
        height = y2 - y1
        crop_filter = f"crop={width}:{height}:{x1}:{y1}"
        logger.info(f"将应用裁剪区域: {crop_filter}")

    tasks = []
    current_frame_start = 1
    for i, (path, frame_count) in enumerate(sorted_infos):
        if frame_count > 0:
            tasks.append((path, output_dir, current_frame_start, crop_filter, i + 1))
            current_frame_start += frame_count

    logger.info(f"准备就绪，开始使用 {len(tasks)} 个进程进行并发解码...")
    decoding_start_time = time.time()
    
    with multiprocessing.Pool(processes=num_processes) as pool:
        results = pool.map(_decode_concurrently_worker, tasks)

    decoding_duration = time.time() - decoding_start_time
    task_data['decoding_duration'] = decoding_duration
    task_data['decoding_stats'] = results
    logger.info(f"所有解码任务完成，总耗时: {decoding_duration:.2f} 秒")

    total_task_duration = time.time() - total_start_time
    task_data['total_task_duration'] = total_task_duration
    
    task_json_path = os.path.join(output_dir, "task.json")
    try:
        with open(task_json_path, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=4)
        logger.info(f"任务信息已保存到: {task_json_path}")
    except IOError as e:
        msg = f"保存 task.json 失败: {e}"
        logger.error(msg)
        return {"status": False, "msg": msg}

    if any(not r['success'] for r in results):
        msg = "一个或多个解码任务失败，请检查日志和 task.json 获取详细信息。"
        logger.warning(msg)
        return {"status": False, "msg": msg}

    msg = f"视频并发解码任务成功完成。任务耗时: {total_task_duration}"
    logger.info(msg)
    return {"status": True, "msg": msg}

def extract_random_frames(video_path: str, num_frames: int, output_dir: str) -> list:
    logger.info(f"开始从视频 '{video_path}' 中高效随机抽取 {num_frames} 帧 (select模式)...")

    video_info = get_video_info(video_path)
    if not video_info or video_info.get('frame_count', 0) == 0:
        logger.error(f"无法获取视频 '{video_path}' 的总帧数信息，抽帧失败。")
        return []

    total_frames = video_info['frame_count']
    
    if num_frames > total_frames:
        logger.warning(f"请求抽取的帧数 ({num_frames}) 大于视频总帧数 ({total_frames})。将抽取所有帧。")
        num_frames = total_frames

    if num_frames == 0:
        logger.warning("计算出的抽帧数为 0，不执行抽帧。")
        return []

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    logger.info(f"抽帧输出目录已创建: {output_dir}")

    frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    
    select_filter = "select='" + "+".join([f"eq(n,{i})" for i in frame_indices]) + "'"
    
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")
    
    command = [
        'ffmpeg',
        '-hide_banner',
        '-i', video_path,
        '-vf', select_filter,
        '-vsync', 'vfr',
        '-q:v', '2',
        '-y',
        output_pattern
    ]
    
    logger.info("准备执行单次 FFmpeg 命令进行批量抽帧...")

    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"批量抽帧失败。FFmpeg 输出:\n{e.stderr}")
        return []

    successful_frames = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.jpg')])
    
    logger.info(f"抽帧任务完成，成功提取 {len(successful_frames)} / {num_frames} 帧。")

    return successful_frames