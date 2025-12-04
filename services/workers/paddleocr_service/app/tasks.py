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
    paths_file_path = None  # [新增] 用于传递给子进程的临时文件路径
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
        
        auto_decompress = get_param_with_fallback(
            "auto_decompress",
            resolved_params,
            workflow_context,
            default=True
        )

        logger.info(f"[{stage_name}] 获取到的keyframe_dir: {keyframe_dir}")
        logger.info(f"[{stage_name}] download_from_minio: {download_from_minio}")
        logger.info(f"[{stage_name}] auto_decompress: {auto_decompress}")
        
        if keyframe_dir and os.path.isdir(keyframe_dir):
            # 情况1: 参数中提供了本地关键帧目录
            logger.info(f"[{stage_name}] 使用参数指定的关键帧目录: {keyframe_dir}")
            execution_metadata['input_source'] = 'parameter_local'
        else:
            # 情况2 & 3: 或者是MinIO/HTTP URL，或者是空值需要从上游获取
            if not keyframe_dir:
                 # 检查前置阶段是否提供了MinIO URL
                 prev_stage = workflow_context.stages.get('ffmpeg.extract_keyframes')
                 if prev_stage and prev_stage.output:
                     keyframe_dir = prev_stage.output.get("keyframe_minio_url")
            
            if keyframe_dir:
                # 统一处理URL格式 (支持http://, https://, minio://)
                # [修复] 改进URL检测，支持更多主机名格式的MinIO URL
                from services.common.minio_url_utils import is_minio_url, normalize_minio_url
                import urllib.parse
                
                # 检查是否为HTTP/HTTPS URL或标准的MinIO URL
                is_url = (keyframe_dir.startswith(('http://', 'https://')) or 
                         keyframe_dir.startswith('minio://'))
                
                if is_url or is_minio_url(keyframe_dir):
                    logger.info(f"[{stage_name}] 检测到URL格式的关键帧目录: {keyframe_dir}")
                    
                    # 如果是HTTP URL且未明确指定下载，先尝试验证是否为MinIO服务器
                    if keyframe_dir.startswith(('http://', 'https://')) and not is_minio_url(keyframe_dir):
                        parsed_url = urllib.parse.urlparse(keyframe_dir)
                        # 检查URL路径是否包含MinIO的bucket结构
                        path_parts = parsed_url.path.strip('/').split('/', 1)
                        if len(path_parts) >= 1 and path_parts[0]:
                            logger.info(f"[{stage_name}] 检测到HTTP URL，可能为MinIO服务器: {parsed_url.netloc}")
                            # 将HTTP URL当作MinIO URL处理
                            is_url = True
                    
                    if not download_from_minio and is_url:
                        logger.warning(f"[{stage_name}] 检测到URL但未启用下载，将尝试验证URL有效性")
                    elif is_url:
                        # 执行URL下载（MinIO或HTTP）
                        try:
                            from services.common.minio_directory_download import download_keyframes_directory

                            # 尝试统一规范化为minio://格式（即使原始是HTTP URL）
                            try:
                                minio_url = normalize_minio_url(keyframe_dir)
                                logger.info(f"[{stage_name}] 规范化URL为MinIO格式: {minio_url}")
                            except ValueError as e:
                                # 如果规范化失败，保持原始URL
                                minio_url = keyframe_dir
                                logger.info(f"[{stage_name}] 保持原始URL格式: {minio_url}")

                            # 如果没有指定本地下载目录，使用默认路径
                            if not local_download_dir:
                                local_download_dir = os.path.join(workflow_context.shared_storage_path, "downloaded_keyframes")

                            logger.info(f"[{stage_name}] 开始从URL下载关键帧目录: {minio_url}")
                            logger.info(f"[{stage_name}] 本地保存目录: {local_download_dir}")

                            download_result = download_keyframes_directory(
                                minio_url=minio_url,
                                workflow_id=workflow_context.workflow_id,
                                local_dir=local_download_dir,
                                auto_decompress=auto_decompress
                            )

                            if download_result["success"]:
                                keyframe_dir = local_download_dir
                                logger.info(f"[{stage_name}] URL目录下载成功: {download_result['total_files']} 个文件")
                                execution_metadata['input_source'] = 'url_download'
                                execution_metadata['url_download_result'] = {
                                    'total_files': download_result['total_files'],
                                    'downloaded_files_count': len(download_result['downloaded_files']),
                                    'downloaded_local_dir': keyframe_dir,
                                    'original_url': keyframe_dir
                                }
                            else:
                                raise RuntimeError(f"URL目录下载失败: {download_result.get('error', '未知错误')}")

                        except Exception as e:
                            logger.error(f"[{stage_name}] URL目录下载过程出错: {e}")
                            raise RuntimeError(f"无法从URL下载关键帧目录: {e}")

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
            
            # [修改] 使用基于工作流ID的临时文件传递路径列表，避免参数过长
            paths_file_path = get_temp_path(workflow_context.workflow_id, '.json')
            with open(paths_file_path, 'w', encoding='utf-8') as f:
                json.dump(keyframe_paths, f)
            
            command = [
                sys.executable,
                executor_script_path,
                "--keyframe-paths-file",
                paths_file_path
            ]
            
            # 使用新的实时日志输出函数
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(command, stage_name=stage_name, check=True, timeout=1800)
            
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
        
        # [新增] 清理传递参数的临时文件
        if paths_file_path and os.path.exists(paths_file_path):
            try:
                os.remove(paths_file_path)
                # logger.info(f"[{stage_name}] 清理参数临时文件: {paths_file_path}")
            except Exception as e:
                logger.warning(f"[{stage_name}] 清理参数临时文件失败: {e}")

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
        
        auto_decompress = get_param_with_fallback(
            "auto_decompress",
            resolved_params,
            workflow_context,
            default=True
        )

        # 如果没有显式参数，只记录需要的参数到input_params
        if not recorded_input_params:
            if input_dir_str:
                recorded_input_params['cropped_images_path'] = input_dir_str
            if subtitle_area:
                recorded_input_params['subtitle_area'] = subtitle_area

        # [修复] 确保input_params只包含原始参数，不包含执行元数据
        workflow_context.stages[stage_name].input_params = recorded_input_params.copy()

        # [修复] MinIO/HTTP URL下载逻辑 - 支持HTTP URL检测和处理
        from services.common.minio_url_utils import is_minio_url, normalize_minio_url
        from services.common.minio_directory_download import is_archive_url
        import urllib.parse

        # 检查是否为HTTP/HTTPS URL或标准的MinIO URL
        is_url = (input_dir_str and input_dir_str.startswith(('http://', 'https://'))) or \
                 (input_dir_str and input_dir_str.startswith('minio://'))

        if input_dir_str and (is_url or is_minio_url(input_dir_str)):
            logger.info(f"[{stage_name}] 检测到输入路径为URL，尝试从远程下载目录: {input_dir_str}")

            # [重要修复] 先检查原始URL是否为压缩包，避免URL规范化时丢失文件名
            is_original_archive = is_archive_url(input_dir_str)
            logger.info(f"[{stage_name}] 原始URL是否为压缩包: {is_original_archive}")

            # 如果是HTTP URL且未明确是MinIO，尝试规范化
            if input_dir_str.startswith(('http://', 'https://')) and not is_minio_url(input_dir_str):
                parsed_url = urllib.parse.urlparse(input_dir_str)
                # 检查URL路径是否包含MinIO的bucket结构
                path_parts = parsed_url.path.strip('/').split('/', 1)
                if len(path_parts) >= 1 and path_parts[0]:
                    logger.info(f"[{stage_name}] 检测到HTTP URL，可能为MinIO服务器: {parsed_url.netloc}")

            # 创建一个临时目录用于存放下载的图片
            local_download_dir = os.path.join(workflow_context.shared_storage_path, f"downloaded_cropped_{int(time.time())}")

            # [重要修复] 如果原始URL是压缩包且启用了自动解压，直接使用原始URL
            # 这样可以避免URL规范化过程中丢失文件名的问题
            if is_original_archive and auto_decompress:
                # 对于压缩包URL，使用原始URL（保留完整文件名）
                download_url = input_dir_str
                logger.info(f"[{stage_name}] 检测到压缩包URL，使用原始URL避免文件名丢失: {download_url}")
            else:
                # 对于普通目录URL，进行规范化处理
                try:
                    download_url = normalize_minio_url(input_dir_str)
                    logger.info(f"[{stage_name}] 规范化URL为MinIO格式: {download_url}")
                except ValueError as e:
                    # 如果规范化失败，保持原始URL
                    download_url = input_dir_str
                    logger.info(f"[{stage_name}] 保持原始URL格式: {download_url}")

            download_result = download_directory_from_minio(
                minio_url=download_url,
                local_dir=local_download_dir,
                create_structure=True,
                auto_decompress=auto_decompress
            )

            if not download_result["success"]:
                raise RuntimeError(f"从URL下载目录失败: {download_result.get('error')}")

            input_dir_str = local_download_dir
            logger.info(f"[{stage_name}] URL目录下载成功，使用本地路径: {input_dir_str}")
            logger.info(f"[{stage_name}] 下载结果: {download_result.get('total_files', 0)} 个文件")

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
            
            # 使用新的实时日志输出函数
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(command, stage_name=stage_name, check=True, timeout=1800)
            
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

        # [优化] MinIO上传逻辑 - 使用压缩上传提高效率
        if upload_to_minio and os.path.exists(output_data["multi_frames_path"]):
            try:
                logger.info(f"[{stage_name}] 开始上传拼接图片目录到MinIO（压缩优化）...")
                minio_base_path = f"{workflow_context.workflow_id}/stitched_images"
                
                # [重要优化] 使用压缩上传替代逐个文件上传
                from services.common.minio_directory_upload import upload_directory_compressed
                
                upload_result = upload_directory_compressed(
                    local_dir=output_data["multi_frames_path"],
                    minio_base_path=minio_base_path,
                    file_pattern="*.jpg",  # 只压缩图片文件
                    compression_format="zip",
                    compression_level="default",
                    delete_local=delete_local_images,
                    workflow_id=workflow_context.workflow_id
                )
                
                if upload_result["success"]:
                    # 返回压缩包的URL（而非目录URL）
                    output_data["multi_frames_minio_url"] = upload_result["archive_url"]
                    output_data["compression_info"] = upload_result.get("compression_info", {})
                    output_data["stitched_images_count"] = upload_result.get("total_files", 0)
                    
                    compression_info = upload_result.get("compression_info", {})
                    if compression_info:
                        compression_ratio = compression_info.get("compression_ratio", 0)
                        logger.info(f"[{stage_name}] 拼接图片压缩上传成功: {upload_result['archive_url']}")
                        logger.info(f"[{stage_name}] 压缩统计: {compression_info.get('files_count', 0)} 个文件, "
                                   f"压缩率 {compression_ratio:.1%}, "
                                   f"原始大小 {compression_info.get('original_size', 0)/1024/1024:.1f}MB, "
                                   f"压缩后 {compression_info.get('compressed_size', 0)/1024/1024:.1f}MB")
                    else:
                        logger.info(f"[{stage_name}] 拼接图片上传成功: {upload_result['archive_url']}")
                    
                    # [新增] 压缩包上传成功后清理本地文件
                    try:
                        logger.info(f"[{stage_name}] 开始清理本地临时文件...")
                        
                        # 1. 清理下载的压缩包和解压缩的图片目录
                        if 'cropped_images_local_compression' in output_data and os.path.exists(output_data['cropped_images_local_compression']):
                            shutil.rmtree(output_data['cropped_images_local_compression'])
                            logger.info(f"[{stage_name}] 已清理下载压缩包目录: {output_data['cropped_images_local_compression']}")
                        
                        if 'cropped_images_local_dir' in output_data and os.path.exists(output_data['cropped_images_local_dir']):
                            shutil.rmtree(output_data['cropped_images_local_dir'])
                            logger.info(f"[{stage_name}] 已清理解压缩图片目录: {output_data['cropped_images_local_dir']}")
                        
                        # 2. 清理执行后合并图片的目录和压缩包文件
                        # 注意：upload_directory_compressed 已经处理了 delete_local 参数
                        # 这里主要是清理其他可能的临时文件
                        
                        if os.path.exists(output_data["multi_frames_path"]):
                            # 如果 delete_local=False，这里需要手动清理
                            if not delete_local_images:
                                shutil.rmtree(output_data["multi_frames_path"])
                                logger.info(f"[{stage_name}] 已清理拼接图片目录: {output_data['multi_frames_path']}")
                        
                        # 清理可能的临时压缩包文件（如果存在）
                        # 注意：upload_directory_compressed 会自动处理这个
                        
                        logger.info(f"[{stage_name}] 本地文件清理完成")
                        
                    except Exception as cleanup_error:
                        logger.warning(f"[{stage_name}] 清理本地文件时出现警告: {cleanup_error}")
                        # 不将清理错误标记为失败，只记录警告
                        output_data["local_cleanup_warning"] = str(cleanup_error)
                    
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
    """[工作流任务] 调用外部脚本对拼接好的图片执行OCR。

    支持单步任务模式：
    - 可通过 manifest_path 和 multi_frames_path 参数直接传入
    - 支持 ${{...}} 格式的动态引用
    - 自动上传OCR结果到MinIO
    
    新增参数：
    - manifest_path: 拼接图像的清单文件路径
    - multi_frames_path: 拼接图像的目录路径
    - upload_ocr_results_to_minio: 是否上传OCR结果到MinIO (默认true)
    - delete_local_ocr_results_after_upload: 上传后是否删除本地OCR结果 (默认false)
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    manifest_path = None  # 用于清理的变量
    multi_frames_path = None  # 用于清理的变量
    ocr_results_path = None  # 用于清理的变量
    # [新增] 远程URL下载后的临时目录
    local_manifest_path = None
    local_multi_frames_path = None
    manifest_download_dir = None
    multi_frames_download_dir = None
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

        # [新增] 获取MinIO上传配置
        upload_to_minio = get_param_with_fallback(
            "upload_ocr_results_to_minio",
            resolved_params,
            workflow_context,
            default=True
        )
        delete_local_results = get_param_with_fallback(
            "delete_local_ocr_results_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )

        # 如果没有显式参数，只记录需要的参数到input_params
        if not recorded_input_params:
            if manifest_path:
                recorded_input_params['manifest_path'] = manifest_path
            if multi_frames_path:
                recorded_input_params['multi_frames_path'] = multi_frames_path
        
        # [修复] 确保input_params只包含原始参数，不包含执行元数据
        workflow_context.stages[stage_name].input_params = recorded_input_params.copy()

        # [修复] HTTP/MinIO URL检测和下载逻辑 - 支持HTTP URL
        from services.common.minio_url_utils import is_minio_url, normalize_minio_url
        import urllib.parse

        # 处理manifest_path：如果是HTTP/MinIO URL则下载
        manifest_is_url = (manifest_path and manifest_path.startswith(('http://', 'https://'))) or \
                         (manifest_path and manifest_path.startswith('minio://'))
        if manifest_path and (manifest_is_url or is_minio_url(manifest_path)):
            logger.info(f"[{stage_name}] 检测到manifest_path为URL，尝试下载: {manifest_path}")
            manifest_download_dir = os.path.join(workflow_context.shared_storage_path, f"download_manifest_{int(time.time())}")

            # 统一处理manifest_path的URL格式
            try:
                minio_url = normalize_minio_url(manifest_path)
                logger.info(f"[{stage_name}] 规范化manifest URL为MinIO格式: {minio_url}")
            except ValueError as e:
                # 如果规范化失败，保持原始URL
                minio_url = manifest_path
                logger.info(f"[{stage_name}] 保持原始manifest URL格式: {minio_url}")

            # 下载manifest文件
            file_service = get_file_service()
            os.makedirs(manifest_download_dir, exist_ok=True)
            try:
                local_manifest_path = file_service.resolve_and_download(minio_url, manifest_download_dir)
                logger.info(f"[{stage_name}] manifest文件下载成功: {local_manifest_path}")
            except Exception as e:
                raise RuntimeError(f"从URL下载manifest文件失败: {minio_url}, error: {e}")
        else:
            # 本地路径，直接使用
            local_manifest_path = manifest_path

        # 处理multi_frames_path：如果是HTTP/MinIO URL则下载
        multi_frames_is_url = (multi_frames_path and multi_frames_path.startswith(('http://', 'https://'))) or \
                             (multi_frames_path and multi_frames_path.startswith('minio://'))
        if multi_frames_path and (multi_frames_is_url or is_minio_url(multi_frames_path)):
            logger.info(f"[{stage_name}] 检测到multi_frames_path为URL，尝试下载目录: {multi_frames_path}")

            # 统一处理multi_frames_path的URL格式
            try:
                minio_url = normalize_minio_url(multi_frames_path)
                logger.info(f"[{stage_name}] 规范化multi_frames URL为MinIO格式: {minio_url}")
            except ValueError as e:
                # 如果规范化失败，保持原始URL
                minio_url = multi_frames_path
                logger.info(f"[{stage_name}] 保持原始multi_frames URL格式: {minio_url}")

            multi_frames_download_dir = os.path.join(workflow_context.shared_storage_path, f"download_multi_frames_{int(time.time())}")

            # 下载目录
            download_result = download_directory_from_minio(
                minio_url=minio_url,
                local_dir=multi_frames_download_dir,
                create_structure=True,
                auto_decompress=True  # OCR任务也支持压缩包
            )

            if not download_result["success"]:
                raise RuntimeError(f"从URL下载目录失败: {download_result.get('error')}")

            local_multi_frames_path = multi_frames_download_dir
            logger.info(f"[{stage_name}] 目录下载成功，使用本地路径: {local_multi_frames_path}")
        else:
            # 本地路径，直接使用
            local_multi_frames_path = multi_frames_path

        # 验证本地路径
        if not local_manifest_path or not os.path.exists(local_manifest_path):
            raise ValueError(f"上下文中缺少或无效的 'manifest_path' 信息: {manifest_path}")
        if not local_multi_frames_path or not os.path.isdir(local_multi_frames_path):
            raise ValueError(f"上下文中缺少或无效的 'multi_frames_path' 信息: {multi_frames_path}")

        # 使用本地路径进行后续处理
        manifest_path = local_manifest_path
        multi_frames_path = local_multi_frames_path

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

            # 使用新的实时日志输出函数
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(command, stage_name=stage_name, check=True, timeout=3600)

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

        # 构造基础输出数据
        output_data = {"ocr_results_path": ocr_results_path}

        # [新增] MinIO上传逻辑 - 上传OCR结果JSON文件
        if upload_to_minio and ocr_results_path and os.path.exists(ocr_results_path):
            try:
                logger.info(f"[{stage_name}] 开始上传OCR结果JSON文件到MinIO...")
                file_service = get_file_service()
                
                # 构建OCR结果文件在MinIO中的路径
                minio_ocr_path = f"{workflow_context.workflow_id}/ocr_results/ocr_results.json"
                
                ocr_minio_url = file_service.upload_to_minio(
                    local_file_path=ocr_results_path,
                    object_name=minio_ocr_path
                )
                
                output_data["ocr_results_minio_url"] = ocr_minio_url
                logger.info(f"[{stage_name}] OCR结果文件上传成功: {ocr_minio_url}")
                
            except Exception as e:
                logger.warning(f"[{stage_name}] OCR结果文件上传失败: {e}", exc_info=True)
                output_data["ocr_results_upload_error"] = str(e)

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

        # [新增] 清理下载的临时目录
        if get_cleanup_temp_files_config():
            try:
                # 清理manifest下载目录
                if manifest_download_dir and os.path.exists(manifest_download_dir):
                    shutil.rmtree(manifest_download_dir)
                    logger.info(f"[{stage_name}] 清理manifest下载目录: {manifest_download_dir}")

                # 清理multi_frames下载目录
                if multi_frames_download_dir and os.path.exists(multi_frames_download_dir):
                    shutil.rmtree(multi_frames_download_dir)
                    logger.info(f"[{stage_name}] 清理multi_frames下载目录: {multi_frames_download_dir}")
            except Exception as e:
                logger.warning(f"[{stage_name}] 清理下载目录失败: {e}")

        # 临时文件清理：multi_frames 目录、manifest 文件和OCR结果文件在完成后删除
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

                # 删除 OCR 结果文件（如果未上传到MinIO或上传后删除了本地文件）
                should_clean_ocr_results = True
                if upload_to_minio and not delete_local_results:
                    should_clean_ocr_results = False
                
                if should_clean_ocr_results and ocr_results_path and os.path.exists(ocr_results_path):
                    os.remove(ocr_results_path)
                    # logger.info(f"[{stage_name}] 清理临时OCR结果文件: {ocr_results_path}")

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
