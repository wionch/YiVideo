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

# 导入标准上下文、锁和状态管理器
from services.common.context import StageExecution
from services.common.context import WorkflowContext
# 使用智能GPU锁机制
from services.common.locks import gpu_lock
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service
from services.common.minio_directory_download import download_directory_from_minio
from services.common.minio_directory_upload import upload_directory_to_minio

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
@gpu_lock()  # 使用配置化的GPU锁，支持运行时参数调整
def detect_subtitle_area(self: Task, context: dict) -> dict:
    """[工作流任务] 通过调用外部脚本，检测视频关键帧中的字幕区域。

    支持三种输入模式：
    1. 工作流模式：从前置阶段自动获取关键帧目录
    2. 参数模式：通过 node_params 直接传入关键帧目录路径
    3. 远程模式：从 MinIO 目录下载关键帧后进行检测
    
    自定义参数：
    - keyframe_dir: 直接指定关键帧目录路径（本地或MinIO URL）
    - download_from_minio: 是否从MinIO下载关键帧（默认false）
    - local_keyframe_dir: 本地保存下载关键帧的目录
    - keyframe_sample_count: 关键帧采样数量（用于调试，暂未使用）
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    keyframe_dir = None
    local_download_dir = None
    execution_metadata = {} # [新增] 用于存储执行过程中的元数据，不污染 input_params
    try:
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # [修复] 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        # [新增] 记录GPU锁和设备信息
        logger.info(f"[{stage_name}] ========== 字幕区域检测设备信息 ==========")
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "N/A"
                logger.info(f"[{stage_name}] 当前GPU数量: {gpu_count}")
                logger.info(f"[{stage_name}] GPU设备: {gpu_name}")
                logger.info(f"[{stage_name}] ✅ 已获取GPU锁，字幕区域检测将使用GPU加速")
            else:
                logger.info(f"[{stage_name}] ℹ️ 当前设备为CPU，字幕区域检测将使用CPU模式")
        except Exception as e:
            logger.warning(f"[{stage_name}] 设备检测失败: {e}")
        logger.info(f"[{stage_name}] ======================================")

        # 步骤1: 获取参数
        # 优先从 resolved_params 获取，回退到 input_data，再回退到上游节点
        keyframe_dir = get_param_with_fallback(
            "keyframe_dir",
            resolved_params,
            workflow_context,
            fallback_from_stage="ffmpeg.extract_keyframes"
        )
        
        download_from_minio = get_param_with_fallback(
            "download_from_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        
        local_download_dir = get_param_with_fallback(
            "local_keyframe_dir",
            resolved_params,
            workflow_context
        )

        logger.info(f"[{stage_name}] 获取到的keyframe_dir: {keyframe_dir}")
        logger.info(f"[{stage_name}] download_from_minio: {download_from_minio}")
        
        if keyframe_dir and os.path.isdir(keyframe_dir):
            # 情况1: 参数中提供了本地关键帧目录
            logger.info(f"[{stage_name}] 使用参数指定的关键帧目录: {keyframe_dir}")
            execution_metadata['input_source'] = 'parameter_local'
        elif keyframe_dir and keyframe_dir.startswith('minio://'):
            # 情况2: 参数中提供了MinIO关键帧目录URL (minio://格式)
            logger.info(f"[{stage_name}] 检测到MinIO关键帧目录URL: {keyframe_dir}")
            if not download_from_minio:
                logger.warning(f"[{stage_name}] 检测到MinIO URL但未启用下载，将尝试使用现有实现")
            else:
                # 执行MinIO目录下载
                try:
                    from services.common.minio_directory_download import download_keyframes_directory

                    # 如果没有指定本地下载目录，使用默认路径
                    if not local_download_dir:
                        local_download_dir = os.path.join(workflow_context.shared_storage_path, "downloaded_keyframes")

                    logger.info(f"[{stage_name}] 开始从MinIO下载关键帧目录: {keyframe_dir}")
                    logger.info(f"[{stage_name}] 本地保存目录: {local_download_dir}")

                    download_result = download_keyframes_directory(
                        minio_url=keyframe_dir,
                        workflow_id=workflow_context.workflow_id,
                        local_dir=local_download_dir
                    )

                    if download_result["success"]:
                        keyframe_dir = local_download_dir
                        logger.info(f"[{stage_name}] MinIO目录下载成功: {download_result['total_files']} 个文件")
                        execution_metadata['input_source'] = 'parameter_minio'
                        # 注意：不修改原始的keyframe_dir，保持为MinIO URL
                        # 下载后的本地路径将在output中记录
                        execution_metadata['minio_download_result'] = {
                            'total_files': download_result['total_files'],
                            'downloaded_files_count': len(download_result['downloaded_files']),
                            'downloaded_local_dir': keyframe_dir  # 在output中记录本地路径
                        }
                    else:
                        raise RuntimeError(f"MinIO目录下载失败: {download_result.get('error', '未知错误')}")

                except Exception as e:
                    logger.error(f"[{stage_name}] MinIO目录下载过程出错: {e}")
                    raise RuntimeError(f"无法从MinIO下载关键帧目录: {e}")
        elif keyframe_dir and keyframe_dir.startswith('http://'):
            # 情况3: 参数中提供了HTTP格式的MinIO关键帧目录URL
            logger.info(f"[{stage_name}] 检测到HTTP格式的MinIO目录URL: {keyframe_dir}")
            if not download_from_minio:
                logger.warning(f"[{stage_name}] 检测到HTTP URL但未启用下载，将尝试使用现有实现")
            else:
                # 执行MinIO目录下载
                try:
                    from services.common.minio_directory_download import download_keyframes_directory

                    # 转换HTTP URL为minio://格式
                    # 示例: http://host.docker.internal:9000/yivideo/task_id/keyframes
                    # 转换为: minio://yivideo/task_id/keyframes
                    from urllib.parse import urlparse
                    parsed_url = urlparse(keyframe_dir)
                    path_parts = parsed_url.path.strip('/').split('/', 1)  # 分割路径，取第一部分作为bucket
                    if len(path_parts) < 2:
                        raise ValueError(f"无法从HTTP URL中提取bucket和路径: {keyframe_dir}")

                    bucket_name = path_parts[0]
                    minio_path = path_parts[1] if len(path_parts) > 1 else ''
                    minio_url = f"minio://{bucket_name}/{minio_path}"

                    logger.info(f"[{stage_name}] HTTP URL转换: {keyframe_dir} -> {minio_url}")

                    # 如果没有指定本地下载目录，使用默认路径
                    if not local_download_dir:
                        local_download_dir = os.path.join(workflow_context.shared_storage_path, "downloaded_keyframes")

                    logger.info(f"[{stage_name}] 开始从MinIO下载关键帧目录: {minio_url}")
                    logger.info(f"[{stage_name}] 本地保存目录: {local_download_dir}")

                    download_result = download_keyframes_directory(
                        minio_url=minio_url,
                        workflow_id=workflow_context.workflow_id,
                        local_dir=local_download_dir
                    )

                    if download_result["success"]:
                        keyframe_dir = local_download_dir
                        logger.info(f"[{stage_name}] MinIO目录下载成功: {download_result['total_files']} 个文件")
                        execution_metadata['input_source'] = 'parameter_http_minio'
                        # 注意：不修改原始的keyframe_dir，保持为HTTP URL
                        # 下载后的本地路径将在output中记录
                        execution_metadata['minio_download_result'] = {
                            'total_files': download_result['total_files'],
                            'downloaded_files_count': len(download_result['downloaded_files']),
                            'downloaded_local_dir': keyframe_dir  # 在output中记录本地路径
                        }
                    else:
                        raise RuntimeError(f"MinIO目录下载失败: {download_result.get('error', '未知错误')}")

                except Exception as e:
                    logger.error(f"[{stage_name}] MinIO目录下载过程出错: {e}")
                    raise RuntimeError(f"无法从MinIO下载关键帧目录: {e}")
        else:
             # 最后的尝试：检查前置阶段是否提供了MinIO URL (即使keyframe_dir本身可能为空)
             # 这处理了 keyframe_dir 为空，但上游输出了 keyframe_minio_url 的情况
             prev_stage = workflow_context.stages.get('ffmpeg.extract_keyframes')
             if prev_stage and prev_stage.output:
                 keyframe_minio_url = prev_stage.output.get("keyframe_minio_url")
                 if keyframe_minio_url and download_from_minio:
                    logger.info(f"[{stage_name}] 前置阶段提供了MinIO关键帧目录，将下载到本地")
                    try:
                        from services.common.minio_directory_download import download_keyframes_directory
                        
                        if not local_download_dir:
                            local_download_dir = os.path.join(workflow_context.shared_storage_path, "downloaded_keyframes")
                        
                        minio_url = f"minio://yivideo/{keyframe_minio_url.split('/yivideo/')[-1]}" if 'yivideo' in keyframe_minio_url else keyframe_minio_url
                        
                        download_result = download_keyframes_directory(
                            minio_url=minio_url,
                            workflow_id=workflow_context.workflow_id,
                            local_dir=local_download_dir
                        )
                        
                        if download_result["success"]:
                            keyframe_dir = local_download_dir
                            execution_metadata['input_source'] = 'workflow_minio'
                            execution_metadata['minio_download_result'] = {
                                'total_files': download_result['total_files'],
                                'downloaded_files_count': len(download_result['downloaded_files']),
                                'downloaded_local_dir': keyframe_dir
                            }
                            logger.info(f"[{stage_name}] 工作流MinIO目录下载成功")
                        else:
                            logger.warning(f"[{stage_name}] 工作流MinIO目录下载失败")
                    except Exception as e:
                        logger.warning(f"[{stage_name}] 工作流MinIO目录下载过程出错: {e}")

        # 验证关键帧目录
        if not keyframe_dir or not os.path.isdir(keyframe_dir):
            raise ValueError(f"无法获取有效的关键帧目录: {keyframe_dir}")

        try:
            keyframe_files = sorted(os.listdir(keyframe_dir))
            keyframe_paths = [os.path.join(keyframe_dir, f) for f in keyframe_files]
        except OSError as e:
            raise RuntimeError(f"无法读取关键帧目录 {keyframe_dir}: {e}") from e

        if not keyframe_paths:
            raise ValueError("关键帧目录为空，无法进行字幕区域检测。")

        # logger.info(f"[{stage_name}] 准备通过外部脚本从 {len(keyframe_paths)} 个关键帧检测字幕区域...")
        
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
                pass  # logger.warning(f"[{stage_name}] 字幕区域检测子进程有 stderr 输出:\n{result.stderr.strip()}")

            if not result_str:
                raise RuntimeError("字幕区域检测脚本执行成功，但没有返回任何输出 (stdout is empty)。")

            output_data = json.loads(result_str)

            # [修复] 将下载后的本地路径添加到output中，保持input_params为原始参数
            if download_from_minio and local_download_dir and os.path.isdir(local_download_dir):
                # 只在真正进行了下载操作时记录本地路径
                output_data['downloaded_keyframes_dir'] = local_download_dir
                logger.info(f"[{stage_name}] 已将下载后的本地路径添加到output: {local_download_dir}")

            # [新增] 将执行元数据合并到output中
            output_data.update(execution_metadata)

            # logger.info(f"[{stage_name}] 外部脚本完成字幕区域检测: {output_data.get('subtitle_area')}")

        except json.JSONDecodeError as e:
            logger.error(f"[{stage_name}] JSON解码失败。接收到的原始 stdout 是:\n---\n{result_str}\n---")
            raise RuntimeError("Failed to decode JSON from subprocess.") from e
        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 字幕区域检测子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Area detection subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 字幕区域检测子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Area detection subprocess failed with exit code {e.returncode}.") from e
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
        
        # 临时文件清理：下载的keyframes目录在字幕区域检测完成后删除
        if get_cleanup_temp_files_config():
            # 清理下载的目录
            if local_download_dir and os.path.isdir(local_download_dir):
                try:
                    shutil.rmtree(local_download_dir)
                    logger.info(f"[{stage_name}] 清理下载的关键帧目录: {local_download_dir}")
                except Exception as e:
                    logger.warning(f"[{stage_name}] 清理下载关键帧目录失败: {e}")
            
            # 清理原始keyframes目录（如果是从工作流获取的）
            if (execution_metadata.get('input_source') == 'workflow_ffmpeg' and 
                keyframe_dir and os.path.isdir(keyframe_dir)):
                try:
                    shutil.rmtree(keyframe_dir)
                    logger.info(f"[{stage_name}] 清理原始关键帧目录: {keyframe_dir}")
                except Exception as e:
                    logger.warning(f"[{stage_name}] 清理原始关键帧目录失败: {e}")

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.create_stitched_images')
def create_stitched_images(self: Task, context: dict) -> dict:
    """[工作流任务] 通过调用外部脚本，将裁剪后的字幕条图像并发拼接成大图。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    input_dir_str = None  # 用于清理的变量
    local_download_dir = None # [新增] 记录下载的临时目录

    try:
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e

        # [修复] 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}

        # 1. 获取输入路径和字幕区域（使用统一参数获取机制）
        input_dir_str = get_param_with_fallback(
            "cropped_images_path",
            resolved_params,
            workflow_context,
            fallback_from_stage="ffmpeg.crop_subtitle_images"
        )

        subtitle_area = get_param_with_fallback(
            "subtitle_area",
            resolved_params,
            workflow_context,
            fallback_from_stage="paddleocr.detect_subtitle_area"
        )

        # [新增] 获取MinIO上传配置
        upload_to_minio = get_param_with_fallback(
            "upload_stitched_images_to_minio",
            resolved_params,
            workflow_context,
            default=True
        )
        delete_local_images = get_param_with_fallback(
            "delete_local_stitched_images_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )

        # 如果没有显式参数，只记录需要的参数到input_params
        if not recorded_input_params:
            if input_dir_str:
                recorded_input_params['cropped_images_path'] = input_dir_str
            if subtitle_area:
                recorded_input_params['subtitle_area'] = subtitle_area

        # [修复] 确保input_params只包含原始参数，不包含执行元数据
        workflow_context.stages[stage_name].input_params = recorded_input_params.copy()

        # [新增] MinIO下载逻辑
        if input_dir_str and (input_dir_str.startswith("http://") or input_dir_str.startswith("https://") or input_dir_str.startswith("minio://")):
            logger.info(f"[{stage_name}] 检测到输入路径为URL，尝试从MinIO下载目录: {input_dir_str}")
            # 创建一个临时目录用于存放下载的图片
            local_download_dir = os.path.join(workflow_context.shared_storage_path, f"downloaded_cropped_{int(time.time())}")
            
            # 处理HTTP格式的URL转换为minio://格式
            minio_url = input_dir_str
            if input_dir_str.startswith("http://") or input_dir_str.startswith("https://"):
                try:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(input_dir_str)
                    path_parts = parsed_url.path.strip('/').split('/', 1)  # 分割路径，取第一部分作为bucket
                    if len(path_parts) < 2:
                        raise ValueError(f"无法从HTTP URL中提取bucket和路径: {input_dir_str}")

                    bucket_name = path_parts[0]
                    minio_path = path_parts[1] if len(path_parts) > 1 else ''
                    minio_url = f"minio://{bucket_name}/{minio_path}"

                    logger.info(f"[{stage_name}] HTTP URL转换: {input_dir_str} -> {minio_url}")
                except Exception as e:
                    logger.error(f"[{stage_name}] HTTP URL转换失败: {e}")
                    raise ValueError(f"无法处理HTTP格式的MinIO URL: {input_dir_str}")
            
            download_result = download_directory_from_minio(
                minio_url=minio_url,
                local_dir=local_download_dir,
                create_structure=True
            )
            
            if not download_result["success"]:
                raise RuntimeError(f"从MinIO下载目录失败: {download_result.get('error')}")
            
            input_dir_str = local_download_dir
            logger.info(f"[{stage_name}] MinIO目录下载成功，使用本地路径: {input_dir_str}")

        if not input_dir_str or not Path(input_dir_str).is_dir():
            raise FileNotFoundError(f"输入目录不存在或无效: {input_dir_str}")
        if not subtitle_area:
            raise ValueError("在上下文中未找到来自 'detect_subtitle_area' 阶段的 'subtitle_area'。")

        # 输出根目录是输入目录的父目录
        output_root_dir = Path(input_dir_str).parent

        # 2. 获取配置
        pipeline_config = CONFIG.get('pipeline', {})
        batch_size = pipeline_config.get('concat_batch_size', 50)
        max_workers = pipeline_config.get('stitching_workers', 10)

        # logger.info(f"[{stage_name}] 准备通过外部脚本拼接图像...")
        # logger.info(f"[{stage_name}]   - 输入目录: {input_dir_str}")
        # logger.info(f"[{stage_name}]   - 字幕区域: {subtitle_area}")

        # 3. 调用外部脚本执行拼接
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_stitch_images.py")
            subtitle_area_json = json.dumps(subtitle_area)
            
            command = [
                sys.executable,
                executor_script_path,
                "--input-dir", str(input_dir_str),
                "--output-root", str(output_root_dir),
                "--batch-size", str(batch_size),
                "--workers", str(max_workers),
                "--subtitle-area-json", subtitle_area_json # [核心修正] 传递字幕区域
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
            
            if result.stderr:
                pass  # logger.warning(f"[{stage_name}] 图像拼接子进程有 stderr 输出:\n{result.stderr.strip()}")

            # logger.info(f"[{stage_name}] 外部脚本成功完成图像拼接。")

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 图像拼接子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Image stitching subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 图像拼接子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Image stitching subprocess failed with exit code {e.returncode}.") from e

        # 4. 构造输出并更新上下文
        output_data = {
            "multi_frames_path": str(output_root_dir / "multi_frames"),
            "manifest_path": str(output_root_dir / "multi_frames.json")
        }

        # [新增] MinIO上传逻辑
        if upload_to_minio and os.path.exists(output_data["multi_frames_path"]):
            try:
                logger.info(f"[{stage_name}] 开始上传拼接图片目录到MinIO...")
                minio_base_path = f"{workflow_context.workflow_id}/stitched_images"
                
                upload_result = upload_directory_to_minio(
                    local_dir=output_data["multi_frames_path"],
                    minio_base_path=minio_base_path,
                    delete_local=delete_local_images,
                    preserve_structure=True
                )
                
                if upload_result["success"]:
                    output_data["multi_frames_minio_url"] = upload_result["minio_base_url"]
                    logger.info(f"[{stage_name}] 拼接图片上传成功: {upload_result['minio_base_url']}")
                else:
                    output_data["multi_frames_upload_error"] = upload_result.get("error")
                    logger.warning(f"[{stage_name}] 拼接图片上传失败: {upload_result.get('error')}")
            except Exception as e:
                logger.warning(f"[{stage_name}] 上传过程异常: {e}", exc_info=True)
                output_data["multi_frames_upload_error"] = str(e)
        
        # [新增] 上传manifest文件到MinIO
        if upload_to_minio and os.path.exists(output_data["manifest_path"]):
            try:
                logger.info(f"[{stage_name}] 开始上传manifest文件到MinIO...")
                file_service = get_file_service()
                
                # 构建manifest文件在MinIO中的路径
                minio_manifest_path = f"{workflow_context.workflow_id}/manifest/multi_frames.json"
                
                manifest_minio_url = file_service.upload_to_minio(
                    local_file_path=output_data["manifest_path"],
                    object_name=minio_manifest_path
                )
                
                output_data["manifest_minio_url"] = manifest_minio_url
                logger.info(f"[{stage_name}] manifest文件上传成功: {manifest_minio_url}")
                
            except Exception as e:
                logger.warning(f"[{stage_name}] manifest文件上传失败: {e}", exc_info=True)
                output_data["manifest_upload_error"] = str(e)

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
        
        # 临时文件清理：
        # 1. 清理下载的临时目录（如果存在）
        if local_download_dir and os.path.exists(local_download_dir):
             if get_cleanup_temp_files_config():
                try:
                    shutil.rmtree(local_download_dir)
                    logger.info(f"[{stage_name}] 清理下载的临时目录: {local_download_dir}")
                except Exception as e:
                    logger.warning(f"[{stage_name}] 清理下载目录失败: {e}")
        
        # 2. 清理输入的input_dir_str (如果不是下载的临时目录，即原始的本地目录)
        # 如果 input_dir_str 被指向了 local_download_dir，上面的代码已经清理了
        # 所以这里只需要处理 input_dir_str != local_download_dir 的情况
        elif get_cleanup_temp_files_config() and input_dir_str and Path(input_dir_str).exists():
            try:
                # 只删除 frames 子目录，不删除整个 cropped_images 目录
                shutil.rmtree(input_dir_str)
                # logger.info(f"[{stage_name}] 清理临时裁剪图像帧目录: {input_dir_str}")
            except Exception as e:
                logger.warning(f"[{stage_name}] 清理裁剪图像帧目录失败: {e}")

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='paddleocr.perform_ocr')
@gpu_lock()  # 使用配置化的GPU锁，支持运行时参数调整
def perform_ocr(self: Task, context: dict) -> dict:
    """[工作流任务] 调用外部脚本对拼接好的图片执行OCR。"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    manifest_path = None  # 用于清理的变量
    multi_frames_path = None  # 用于清理的变量
    try:
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # [修复] 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，只记录需要的参数到input_params
        if not recorded_input_params:
            prev_stage = workflow_context.stages.get('ffmpeg.extract_keyframes')
            if prev_stage:
                keyframe_dir = prev_stage.output.get("keyframe_dir") if prev_stage.output else None
                if keyframe_dir:
                    recorded_input_params['keyframe_dir'] = keyframe_dir
        
        # [修复] 确保input_params只包含原始参数，不包含执行元数据
        workflow_context.stages[stage_name].input_params = recorded_input_params.copy()

        manifest_path = get_param_with_fallback(
            "manifest_path",
            resolved_params,
            workflow_context,
            fallback_from_stage="paddleocr.create_stitched_images"
        )
        
        multi_frames_path = get_param_with_fallback(
            "multi_frames_path",
            resolved_params,
            workflow_context,
            fallback_from_stage="paddleocr.create_stitched_images"
        )

        if not manifest_path or not os.path.exists(manifest_path):
            raise ValueError(f"上下文中缺少或无效的 'manifest_path' 信息: {manifest_path}")
        if not multi_frames_path or not os.path.isdir(multi_frames_path):
            raise ValueError(f"上下文中缺少或无效的 'multi_frames_path' 信息: {multi_frames_path}")

        # [新增] 记录GPU锁和设备信息
        logger.info(f"[{stage_name}] ========== OCR任务设备信息 ==========")
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "N/A"
                logger.info(f"[{stage_name}] 当前GPU数量: {gpu_count}")
                logger.info(f"[{stage_name}] GPU设备: {gpu_name}")
                logger.info(f"[{stage_name}] ✅ 已获取GPU锁，OCR任务将使用GPU加速")
            else:
                logger.info(f"[{stage_name}] ℹ️ 当前设备为CPU，OCR任务将使用CPU模式")
        except Exception as e:
            logger.warning(f"[{stage_name}] 设备检测失败: {e}")
        logger.info(f"[{stage_name}] ================================")

        # logger.info(f"[{stage_name}] 准备通过外部脚本对清单 {manifest_path} 中的图片执行OCR...")
        
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
                logger.info(f"[{stage_name}] OCR 子进程 stderr 输出:\n{result.stderr.strip()}")
            
            ocr_results_str = result.stdout.strip()
            if not ocr_results_str:
                raise RuntimeError("OCR执行脚本没有返回任何输出。")
            ocr_results = json.loads(ocr_results_str)
            # logger.info(f"[{stage_name}] 外部脚本OCR完成，识别出 {len(ocr_results)} 帧的文本。")

        except subprocess.TimeoutExpired as e:
            logger.error(f"[{stage_name}] OCR子进程执行超时({e.timeout}秒)。Stderr: {e.stderr}")
            raise RuntimeError(f"OCR subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            logger.error(f"[{stage_name}] OCR子进程执行失败，返回码: {e.returncode}。Stderr: {e.stderr}")
            raise RuntimeError(f"OCR subprocess failed with exit code {e.returncode}.") from e

        ocr_results_path = os.path.join(workflow_context.shared_storage_path, "ocr_results.json")
        with open(ocr_results_path, 'w', encoding='utf-8') as f:
            json.dump(ocr_results, f, ensure_ascii=False)
        # logger.info(f"[{stage_name}] OCR结果已保存到文件: {ocr_results_path}")

        output_data = {"ocr_results_path": ocr_results_path}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
        
        # 临时文件清理：multi_frames 目录和 manifest 文件在OCR完成后删除
        if get_cleanup_temp_files_config():
            try:
                # 删除 multi_frames 目录
                if multi_frames_path and os.path.isdir(multi_frames_path):
                    shutil.rmtree(multi_frames_path)
                    # logger.info(f"[{stage_name}] 清理临时多帧图像目录: {multi_frames_path}")

                # 删除 manifest 文件
                if manifest_path and os.path.exists(manifest_path):
                    os.remove(manifest_path)
                    # logger.info(f"[{stage_name}] 清理临时清单文件: {manifest_path}")

                # 删除整个 cropped_images 目录（现在应该只剩空目录或其他临时文件）
                if multi_frames_path:
                    cropped_images_parent = Path(multi_frames_path).parent
                    if cropped_images_parent.exists() and cropped_images_parent.name == "cropped_images":
                        try:
                            shutil.rmtree(str(cropped_images_parent))
                            # logger.info(f"[{stage_name}] 清理整个裁剪图像目录: {cropped_images_parent}")
                        except Exception as e:
                            # 如果删除失败，可能是目录不为空，记录警告但不影响主流程
                            logger.warning(f"[{stage_name}] 清理cropped_images目录失败（可能不为空）: {e}")

            except Exception as e:
                logger.warning(f"[{stage_name}] 清理多帧图像文件失败: {e}")

        # [新增] 强制清理PaddleOCR相关进程和GPU显存
        try:
            from services.common.gpu_memory_manager import cleanup_paddleocr_processes, log_gpu_memory_state

            logger.info(f"[{stage_name}] 开始清理OCR相关进程和GPU资源...")
            log_gpu_memory_state("OCR任务完成前")

            # 清理残留的OCR进程
            cleanup_paddleocr_processes()

            # 记录清理后的状态
            log_gpu_memory_state("OCR任务清理后")

        except Exception as cleanup_e:
            logger.warning(f"[{stage_name}] OCR资源清理过程中出现问题: {cleanup_e}")

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
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # [修复] 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，只记录需要的参数到input_params
        if not recorded_input_params:
            prev_stage = workflow_context.stages.get('ffmpeg.extract_keyframes')
            if prev_stage:
                keyframe_dir = prev_stage.output.get("keyframe_dir") if prev_stage.output else None
                if keyframe_dir:
                    recorded_input_params['keyframe_dir'] = keyframe_dir
        
        # [修复] 确保input_params只包含原始参数，不包含执行元数据
        workflow_context.stages[stage_name].input_params = recorded_input_params.copy()

        ocr_results_path = get_param_with_fallback(
            "ocr_results_path",
            resolved_params,
            workflow_context,
            fallback_from_stage="paddleocr.perform_ocr"
        )
        
        if not ocr_results_path or not os.path.exists(ocr_results_path):
            raise ValueError(f"上下文中缺少或无效的 'ocr_results_path' 信息: {ocr_results_path}")
        
        # logger.info(f"[{stage_name}] 正在从文件加载OCR结果: {ocr_results_path}")
        with open(ocr_results_path, 'r', encoding='utf-8') as f:
            ocr_results = json.load(f)

        # 优先从 resolved_params 获取参数
        video_path = get_param_with_fallback("video_path", resolved_params, workflow_context)
        
        if not video_path:
            raise ValueError("上下文中缺少 'video_path' 信息，无法获取FPS。")

        # logger.info(f"[{stage_name}] 开始对 {len(ocr_results)} 条OCR结果进行后处理...")
        
        fps = _get_video_fps(video_path)

        final_subtitles = postprocessor.format_from_full_frames(ocr_results, fps)

        if not final_subtitles:
            logger.warning(f"[{stage_name}] 后处理完成，但未生成任何有效字幕，任务结束。")
            output_data = {"srt_file": None, "json_file": None}
        else:
            video_basename = os.path.basename(video_path)
            video_name, _ = os.path.splitext(video_basename)
            
            final_srt_path = os.path.join(workflow_context.shared_storage_path, f"{video_name}.srt")
            final_json_path = os.path.join(workflow_context.shared_storage_path, f"{video_name}.json")
            
            _write_srt_file(final_subtitles, final_srt_path)
            with open(final_json_path, 'w', encoding='utf-8') as f:
                json.dump(final_subtitles, f, ensure_ascii=False, indent=4)

            # logger.info(f"[{stage_name}] 后处理完成，生成最终文件: {final_json_path}")
            output_data = {"srt_file": final_srt_path, "json_file": final_json_path}

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
        
        # 临时文件清理：OCR结果文件在后处理完成后删除
        if get_cleanup_temp_files_config():
            prev_ocr_stage = workflow_context.stages.get('paddleocr.perform_ocr')
            ocr_results_path_to_clean = prev_ocr_stage.output.get("ocr_results_path") if prev_ocr_stage else None
            if ocr_results_path_to_clean and os.path.exists(ocr_results_path_to_clean):
                os.remove(ocr_results_path_to_clean)
                # logger.info(f"[{stage_name}] 清理临时OCR结果文件: {ocr_results_path_to_clean}")

    return workflow_context.model_dump()
