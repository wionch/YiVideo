# services/workers/paddleocr_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
paddleocr_service 的 Celery 任务定义。
此模块中的核心计算任务通过调用外部隔离的Python脚本来执行，
以规避Celery prefork Worker中无法创建子进程的限制。
"""

import os

from services.common.logger import get_logger

logger = get_logger('tasks')
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path

import av
import cv2

# 导入此服务内部的核心逻辑模块
from app.modules.postprocessor import SubtitlePostprocessor
from celery import Celery
from celery import Task

from services.common import state_manager
from services.common.config_loader import CONFIG
from services.common.config_loader import get_cleanup_temp_files_config
from services.common.subtitle.subtitle_parser import SubtitleEntry, write_srt_file as common_write_srt_file

# 导入标准上下文、锁和状态管理器
from services.common.context import StageExecution
from services.common.context import WorkflowContext
from services.common.minio_url_utils import normalize_minio_url
# 使用智能GPU锁机制
from services.common.locks import gpu_lock
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service
from services.common.minio_directory_download import download_directory_from_minio
from services.common.minio_directory_upload import upload_directory_to_minio
from services.common.temp_path_utils import get_temp_path

# --- 日志配置 ---
# 日志已统一管理，使用 services.common.logger

# --- Celery App 初始化 ---
from services.common.celery_config import BROKER_URL, BACKEND_URL

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
        logger.warning(f"Could not get FPS from video metadata using PyAV: {e}. Defaulting to 30.0")
        return 30.0

def natural_sort_key(s: str) -> list:
    """
    为字符串提供自然排序的键。例如：img1.png, img2.png, img10.png。
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

# --- Celery 任务定义 ---

@celery_app.task(bind=True, name='paddleocr.detect_subtitle_area')
@gpu_lock()  # 使用配置化的GPU锁，支持运行时参数调整
def detect_subtitle_area(self: Task, context: dict) -> dict:
    """
    [工作流任务] 检测视频关键帧中的字幕区域 - 使用 subprocess 调用独立脚本。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.paddleocr_service.executors import PaddleOCRDetectSubtitleAreaExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PaddleOCRDetectSubtitleAreaExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.create_stitched_images')
def create_stitched_images(self: Task, context: dict) -> dict:
    """
    [工作流任务] 将裁剪后的字幕条图像并发拼接成大图。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.paddleocr_service.executors import PaddleOCRCreateStitchedImagesExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PaddleOCRCreateStitchedImagesExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.perform_ocr')
@gpu_lock()  # 使用配置化的GPU锁，支持运行时参数调整
def perform_ocr(self: Task, context: dict) -> dict:
    """
    [工作流任务] 调用外部脚本对拼接好的图片执行OCR。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.paddleocr_service.executors import PaddleOCRPerformOCRExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PaddleOCRPerformOCRExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()

@celery_app.task(bind=True, name='paddleocr.postprocess_and_finalize')
def postprocess_and_finalize(self: Task, context: dict) -> dict:
    """
    [工作流任务] 对OCR结果进行后处理，生成最终字幕文件。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.paddleocr_service.executors import PaddleOCRPostprocessAndFinalizeExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = PaddleOCRPostprocessAndFinalizeExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
