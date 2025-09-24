# services/workers/paddleocr_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
paddleocr_service 的 Celery 任务定义。
此模块中的核心计算任务通过调用外部隔离的Python脚本来执行，
以规避Celery prefork Worker中无法创建子进程的限制。
"""

import os
import sys
import shutil
import json
import time
import cv2
import av
import logging
import subprocess
import re
from pathlib import Path
from celery import Celery, Task
from concurrent.futures import ProcessPoolExecutor, as_completed

# 导入标准上下文、锁和状态管理器
from services.common.context import WorkflowContext, StageExecution
from services.common.locks import gpu_lock
from services.common import state_manager
from services.common.config_loader import CONFIG

# 导入此服务内部的核心逻辑模块
from app.modules.postprocessor import SubtitlePostprocessor

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Celery App 初始化 ---
BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
BACKEND_URL = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

celery_app = Celery(
    'paddleocr_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True
)

# --- 核心逻辑组件实例化 ---
postprocessor = SubtitlePostprocessor(CONFIG.get('postprocessor', {}))

# --- Helper Functions ---
def _get_video_fps(video_path: str) -> float:
    """Helper function to get the frames per second of a video."""
    try:
        with av.open(video_path) as container:
            return float(container.streams.video[0].average_rate)
    except Exception as e:
        logging.warning(f"Could not get FPS from video metadata using PyAV: {e}. Defaulting to 30.0")
        return 30.0

def _write_srt_file(subtitles: list, srt_path: str):
    """Helper function to write a list of subtitle dicts to an SRT file."""
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(subtitles, 1):
            start_time = sub['startTime']
            end_time = sub['endTime']
            text = sub['text']
            
            start_h, rem = divmod(start_time, 3600)
            start_m, rem = divmod(rem, 60)
            start_s, start_ms = divmod(rem, 1)
            
            end_h, rem = divmod(end_time, 3600)
            end_m, rem = divmod(rem, 60)
            end_s, end_ms = divmod(rem, 1)

            start_srt = f"{int(start_h):02}:{int(start_m):02}:{int(start_s):02},{int(start_ms*1000):03}"
            end_srt = f"{int(end_h):02}:{int(end_m):02}:{int(end_s):02},{int(end_ms*1000):03}"
            
            f.write(f"{i}\n")
            f.write(f"{start_srt} --> {end_srt}\n")
            f.write(f"{text}\n\n")

def natural_sort_key(s: str) -> list:
    """
    为字符串提供自然排序的键。例如：img1.png, img2.png, img10.png。
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

# --- Celery 任务定义 ---

@celery_app.task(bind=True, name='paddleocr.detect_subtitle_area')
@gpu_lock(lock_key="gpu_lock:0", timeout=600)
def detect_subtitle_area(self: Task, context: dict) -> dict:
    """[工作流任务] 通过调用外部脚本，检测视频关键帧中的字幕区域。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    keyframe_dir = None
    try:
        prev_stage = workflow_context.stages.get('ffmpeg.extract_keyframes')
        prev_stage_output = prev_stage.output if prev_stage else {}

        keyframe_dir = prev_stage_output.get("keyframe_dir")
        if not keyframe_dir or not os.path.isdir(keyframe_dir):
            raise ValueError(f"上下文中缺少或无效的 'keyframe_dir' 信息: {keyframe_dir}")

        try:
            keyframe_files = sorted(os.listdir(keyframe_dir))
            keyframe_paths = [os.path.join(keyframe_dir, f) for f in keyframe_files]
        except OSError as e:
            raise RuntimeError(f"无法读取关键帧目录 {keyframe_dir}: {e}") from e

        if not keyframe_paths:
            raise ValueError("关键帧目录为空，无法进行字幕区域检测。")

        logging.info(f"[{stage_name}] 准备通过外部脚本从 {len(keyframe_paths)} 个关键帧检测字幕区域...")
        
        result_str = ""
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_area_detection.py")
            keyframe_paths_json = json.dumps(keyframe_paths)
            
            command = [
                sys.executable,
                executor_script_path,
                "--keyframe-paths-json",
                keyframe_paths_json
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
            
            result_str = result.stdout.strip()

            if result.stderr:
                logging.warning(f"[{stage_name}] 字幕区域检测子进程有 stderr 输出:\n{result.stderr.strip()}")

            if not result_str:
                raise RuntimeError("字幕区域检测脚本执行成功，但没有返回任何输出 (stdout is empty)。")
            
            output_data = json.loads(result_str)
            logging.info(f"[{stage_name}] 外部脚本完成字幕区域检测: {output_data.get('subtitle_area')}")
        
        except json.JSONDecodeError as e:
            logging.error(f"[{stage_name}] JSON解码失败。接收到的原始 stdout 是:\n---\n{result_str}\n---")
            raise RuntimeError("Failed to decode JSON from subprocess.") from e
        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 字幕区域检测子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Area detection subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 字幕区域检测子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Area detection subprocess failed with exit code {e.returncode}.") from e
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.create_stitched_images')
def create_stitched_images(self: Task, context: dict) -> dict:
    """[工作流任务] 通过调用外部脚本，将裁剪后的字幕条图像并发拼接成大图。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 1. 获取输入和输出路径
        prev_stage = workflow_context.stages.get("ffmpeg.crop_subtitle_images")
        prev_stage_output = prev_stage.output if prev_stage else {}
        input_dir_str = prev_stage_output.get('cropped_images_path')
        
        if not input_dir_str:
            raise ValueError("在上下文中未找到来自上一阶段的 'cropped_images_path'。")
        
        input_dir = Path(input_dir_str)
        if not input_dir.is_dir():
            raise FileNotFoundError(f"输入目录不存在: {input_dir}")

        # 输出根目录是输入目录的父目录
        output_root_dir = input_dir.parent

        # 2. 获取配置
        pipeline_config = CONFIG.get('pipeline', {})
        batch_size = pipeline_config.get('concat_batch_size', 50)
        max_workers = pipeline_config.get('stitching_workers', 10)

        logging.info(f"[{stage_name}] 准备通过外部脚本拼接图像...")
        logging.info(f"[{stage_name}]   - 输入目录: {input_dir_str}")
        logging.info(f"[{stage_name}]   - 输出根目录: {output_root_dir}")
        logging.info(f"[{stage_name}]   - 并发数: {max_workers}, 批次大小: {batch_size}")

        # 3. 调用外部脚本执行拼接
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_stitch_images.py")
            command = [
                sys.executable,
                executor_script_path,
                "--input-dir", str(input_dir),
                "--output-root", str(output_root_dir),
                "--batch-size", str(batch_size),
                "--workers", str(max_workers)
            ]
            
            # 设置一个合理的超时，例如30分钟
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
            
            if result.stderr:
                logging.warning(f"[{stage_name}] 图像拼接子进程有 stderr 输出:\n{result.stderr.strip()}")

            logging.info(f"[{stage_name}] 外部脚本成功完成图像拼接。")

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 图像拼接子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Image stitching subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 图像拼接子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Image stitching subprocess failed with exit code {e.returncode}.") from e

        # 4. 构造输出并更新上下文
        output_data = {
            "multi_frames_path": str(output_root_dir / "multi_frames"),
            "manifest_path": str(output_root_dir / "multi_frames.json")
        }
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.perform_ocr')
@gpu_lock(lock_key="gpu_lock:0", timeout=3600)
def perform_ocr(self: Task, context: dict) -> dict:
    """[工作流任务] 调用外部脚本对拼接好的图片执行OCR。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    try:
        prev_stage = workflow_context.stages.get('paddleocr.create_stitched_images')
        prev_stage_output = prev_stage.output if prev_stage else {}

        manifest_path = prev_stage_output.get("manifest_path")
        multi_frames_path = prev_stage_output.get("multi_frames_path")

        if not manifest_path or not os.path.exists(manifest_path):
            raise ValueError(f"上下文中缺少或无效的 'manifest_path' 信息: {manifest_path}")
        if not multi_frames_path or not os.path.isdir(multi_frames_path):
            raise ValueError(f"上下文中缺少或无效的 'multi_frames_path' 信息: {multi_frames_path}")

        logging.info(f"[{stage_name}] 准备通过外部脚本对清单 {manifest_path} 中的图片执行OCR...")
        
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_ocr.py")
            command = [
                sys.executable,
                executor_script_path,
                "--manifest-path",
                manifest_path,
                "--multi-frames-path",
                multi_frames_path
            ]

            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=3600)

            if result.stderr:
                logging.info(f"[{stage_name}] OCR 子进程 stderr 输出:\n{result.stderr.strip()}")
            
            ocr_results_str = result.stdout.strip()
            if not ocr_results_str:
                raise RuntimeError("OCR执行脚本没有返回任何输出。")
            ocr_results = json.loads(ocr_results_str)
            logging.info(f"[{stage_name}] 外部脚本OCR完成，识别出 {len(ocr_results)} 帧的文本。")

        except subprocess.TimeoutExpired as e:
            logging.error(f"[{stage_name}] OCR子进程执行超时({e.timeout}秒)。Stderr: {e.stderr}")
            raise RuntimeError(f"OCR subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            logging.error(f"[{stage_name}] OCR子进程执行失败，返回码: {e.returncode}。Stderr: {e.stderr}")
            raise RuntimeError(f"OCR subprocess failed with exit code {e.returncode}.") from e

        ocr_results_path = os.path.join(workflow_context.shared_storage_path, "ocr_results.json")
        with open(ocr_results_path, 'w', encoding='utf-8') as f:
            json.dump(ocr_results, f, ensure_ascii=False)
        logging.info(f"[{stage_name}] OCR结果已保存到文件: {ocr_results_path}")

        output_data = {"ocr_results_path": ocr_results_path}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()

@celery_app.task(bind=True, name='paddleocr.postprocess_and_finalize')
def postprocess_and_finalize(self: Task, context: dict) -> dict:
    """[工作流任务] 对OCR结果进行后处理，生成最终字幕文件。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        prev_stage = workflow_context.stages.get('paddleocr.perform_ocr')
        prev_stage_output = prev_stage.output if prev_stage else {}

        ocr_results_path = prev_stage_output.get("ocr_results_path")
        if not ocr_results_path or not os.path.exists(ocr_results_path):
            raise ValueError(f"上下文中缺少或无效的 'ocr_results_path' 信息: {ocr_results_path}")
        
        logging.info(f"[{stage_name}] 正在从文件加载OCR结果: {ocr_results_path}")
        with open(ocr_results_path, 'r', encoding='utf-8') as f:
            ocr_results = json.load(f)

        video_path = workflow_context.input_params.get("video_path")
        if not video_path:
            raise ValueError("上下文中缺少 'video_path' 信息，无法获取FPS。")

        logging.info(f"[{stage_name}] 开始对 {len(ocr_results)} 条OCR结果进行后处理...")
        
        fps = _get_video_fps(video_path)

        final_subtitles = postprocessor.format_from_full_frames(ocr_results, fps)

        if not final_subtitles:
            logging.warning(f"[{stage_name}] 后处理完成，但未生成任何有效字幕，任务结束。")
            output_data = {"srt_file": None, "json_file": None}
        else:
            video_basename = os.path.basename(video_path)
            video_name, _ = os.path.splitext(video_basename)
            
            final_srt_path = os.path.join(workflow_context.shared_storage_path, f"{video_name}.srt")
            final_json_path = os.path.join(workflow_context.shared_storage_path, f"{video_name}.json")
            
            _write_srt_file(final_subtitles, final_srt_path)
            with open(final_json_path, 'w', encoding='utf-8') as f:
                json.dump(final_subtitles, f, ensure_ascii=False, indent=4)

            logging.info(f"[{stage_name}] 后处理完成，生成最终文件: {final_json_path}")
            output_data = {"srt_file": final_srt_path, "json_file": final_json_path}

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
        
        ocr_results_path_to_clean = workflow_context.stages.get('paddleocr.perform_ocr', {}).get('output', {}).get("ocr_results_path")
        if ocr_results_path_to_clean and os.path.exists(ocr_results_path_to_clean):
            os.remove(ocr_results_path_to_clean)
            logging.info(f"[{stage_name}] 清理临时OCR结果文件: {ocr_results_path_to_clean}")

    return workflow_context.model_dump()
