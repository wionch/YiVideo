# services/workers/ffmpeg_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
ffmpeg_service 的 Celery 任务定义。
"""

import os
import sys
import json
import time
import logging
import subprocess
from celery import Celery, Task

# 导入项目定义的标准上下文、状态管理和分布式锁
from services.common.context import WorkflowContext, StageExecution
from services.common.locks import gpu_lock
from services.common import state_manager

# 导入该服务内部的核心视频处理逻辑模块
from .modules.video_decoder import extract_random_frames

# --- Celery App 初始化与配置 ---

BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
BACKEND_URL = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

celery_app = Celery(
    'ffmpeg_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['app.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# --- Celery 任务定义 ---

@celery_app.task(bind=True, name='ffmpeg.extract_keyframes')
@gpu_lock(lock_key="gpu_lock:0", timeout=600)
def extract_keyframes(self: Task, context: dict) -> dict:
    """
    [工作流任务] 从视频中抽取若干关键帧图片。
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        os.makedirs(workflow_context.shared_storage_path, exist_ok=True)

        video_path = workflow_context.input_params.get("video_path")
        num_frames = workflow_context.input_params.get("keyframe_sample_count", 100)
        keyframes_dir = os.path.join(workflow_context.shared_storage_path, "keyframes")

        logging.info(f"[{stage_name}] 开始从 {video_path} 抽取 {num_frames} 帧...")
        
        frame_paths = extract_random_frames(video_path, num_frames, keyframes_dir)

        if not frame_paths:
            raise RuntimeError("核心函数 extract_random_frames 未能成功抽取任何帧。")

        output_data = {"keyframe_dir": keyframes_dir}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        logging.info(f"[{stage_name}] 抽帧完成，产物目录: {keyframes_dir}。")

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='ffmpeg.crop_subtitle_images')
@gpu_lock(lock_key="gpu_lock:0", timeout=1800)
def crop_subtitle_images(self: Task, context: dict) -> dict:
    """
    [工作流任务] 通过调用外部脚本，并发解码并裁剪出所有字幕条图片。
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        video_path = workflow_context.input_params.get("video_path")
        
        prev_stage = workflow_context.stages.get('paddleocr.detect_subtitle_area')
        prev_stage_output = prev_stage.output if prev_stage else {}
        crop_area = prev_stage_output.get("subtitle_area")
        if not crop_area:
            raise ValueError("上下文中缺少 'subtitle_area' (字幕区域) 信息，无法执行裁剪。")

        cropped_images_dir = os.path.join(workflow_context.shared_storage_path, "cropped_images")

        logging.info(f"[{stage_name}] 准备通过外部脚本从 {video_path} 并发解码并裁剪字幕区域: {crop_area}...")
        
        result_str = ""
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_decode_video.py")
            crop_area_json = json.dumps(crop_area)
            num_processes = workflow_context.input_params.get("decode_processes", 10)

            command = [
                sys.executable,
                executor_script_path,
                "--video-path", video_path,
                "--output-dir", cropped_images_dir,
                "--num-processes", str(num_processes),
                "--crop-area-json", crop_area_json
            ]

            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
            result_str = result.stdout.strip()

            if result.stderr:
                logging.warning(f"[{stage_name}] 视频解码子进程有 stderr 输出:\n{result.stderr.strip()}")

            if not result_str:
                raise RuntimeError("视频解码脚本执行成功，但没有返回任何输出。")

            result_data = json.loads(result_str)
            if not result_data.get("status"):
                raise RuntimeError(f"核心函数 decode_video_concurrently 未能成功完成: {result_data.get('msg')}")

        except json.JSONDecodeError as e:
            logging.error(f"[{stage_name}] JSON解码失败。接收到的原始 stdout 是:\n---\n{result_str}\n---")
            raise RuntimeError("Failed to decode JSON from video decoder subprocess.") from e
        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 视频解码子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Video decoding subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logging.error(f"[{stage_name}] 视频解码子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Video decoding subprocess failed with exit code {e.returncode}.") from e

        final_frames_path = os.path.join(cropped_images_dir, "frames")
        output_data = {"cropped_images_path": final_frames_path}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        logging.info(f"[{stage_name}] 字幕条裁剪完成。")

    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()