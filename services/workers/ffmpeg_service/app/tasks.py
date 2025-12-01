# services/workers/ffmpeg_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
ffmpeg_service 的 Celery 任务定义。
"""

import os

from services.common.logger import get_logger

logger = get_logger('tasks')
import json
import logging
import subprocess
import sys
import time

from celery import Task

# 从 .celery_app 模块导入已配置的 celery 实例
from .celery_app import celery_app
from services.common import state_manager

# 导入项目定义的标准上下文、状态管理和分布式锁
from services.common.context import StageExecution
from services.common.context import WorkflowContext
# 使用智能GPU锁机制
from services.common.locks import gpu_lock
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service

# 导入该服务内部的核心视频处理逻辑模块
from .modules.video_decoder import extract_random_frames
# 导入音频分割相关模块
from .modules.subtitle_parser import parse_subtitle_segments
from .modules.audio_splitter import AudioSplitter, split_audio_segments as split_audio_by_segments

# --- Celery 任务定义 ---

@celery_app.task(bind=True, name='ffmpeg.extract_keyframes')
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
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，记录全局输入参数
        if not recorded_input_params:
            input_data = workflow_context.input_params.get("input_data", {})
            if input_data.get("video_path"):
                recorded_input_params['video_path'] = input_data.get("video_path")
        
        # MinIO上传参数
        upload_to_minio = get_param_with_fallback(
            "upload_keyframes_to_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        delete_local_keyframes = get_param_with_fallback(
            "delete_local_keyframes_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        
        # 压缩上传参数（新增）
        compress_keyframes_before_upload = get_param_with_fallback(
            "compress_keyframes_before_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        keyframe_compression_format = get_param_with_fallback(
            "keyframe_compression_format",
            resolved_params,
            workflow_context,
            default="zip"
        )
        keyframe_compression_level = get_param_with_fallback(
            "keyframe_compression_level", 
            resolved_params,
            workflow_context,
            default="default"
        )
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        os.makedirs(workflow_context.shared_storage_path, exist_ok=True)

        # 优先从 resolved_params 获取参数，回退到全局 input_data (兼容单步任务)
        video_path = get_param_with_fallback("video_path", resolved_params, workflow_context)

        # --- 文件下载 ---
        file_service = get_file_service()
        logger.info(f"[{stage_name}] 开始下载视频文件: {video_path}")
        video_path = file_service.resolve_and_download(video_path, workflow_context.shared_storage_path)
        # 更新本地 input_params 中的 video_path 为下载后的本地路径
        workflow_context.stages[stage_name].input_params["video_path"] = video_path
        logger.info(f"[{stage_name}] 视频文件下载完成: {video_path}")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        num_frames = get_param_with_fallback(
            "keyframe_sample_count",
            resolved_params,
            workflow_context,
            default=100
        )
        keyframes_dir = os.path.join(workflow_context.shared_storage_path, "keyframes")

        logger.info(f"[{stage_name}] 开始从 {video_path} 抽取 {num_frames} 帧...")

        frame_paths = extract_random_frames(video_path, num_frames, keyframes_dir)

        if not frame_paths:
            raise RuntimeError("核心函数 extract_random_frames 未能成功抽取任何帧。")

        # 基础输出数据
        output_data = {"keyframe_dir": keyframes_dir}

        # 检查是否需要上传关键帧目录到MinIO
        upload_to_minio = get_param_with_fallback(
            "upload_keyframes_to_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        delete_local_keyframes = get_param_with_fallback(
            "delete_local_keyframes_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        
        # 压缩上传参数（新增）
        compress_keyframes_before_upload = get_param_with_fallback(
            "compress_keyframes_before_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        keyframe_compression_format = get_param_with_fallback(
            "keyframe_compression_format",
            resolved_params,
            workflow_context,
            default="zip"
        )
        keyframe_compression_level = get_param_with_fallback(
            "keyframe_compression_level", 
            resolved_params,
            workflow_context,
            default="default"
        )
        
        if upload_to_minio and frame_paths:
            try:
                if compress_keyframes_before_upload:
                    # 使用压缩上传
                    from services.common.minio_directory_upload import upload_directory_compressed
                    
                    logger.info(f"[{stage_name}] 开始压缩并上传关键帧目录到MinIO...")
                    logger.info(f"[{stage_name}] 压缩格式: {keyframe_compression_format}, 级别: {keyframe_compression_level}")
                    
                    # 构建关键帧在MinIO中的路径
                    minio_base_path = f"{workflow_context.workflow_id}/keyframes"
                    
                    upload_result = upload_directory_compressed(
                        local_dir=keyframes_dir,
                        minio_base_path=minio_base_path,
                        file_pattern="*.jpg",
                        compression_format=keyframe_compression_format,
                        compression_level=keyframe_compression_level,
                        delete_local=delete_local_keyframes
                    )
                    
                    if upload_result["success"]:
                        compression_info = upload_result.get("compression_info", {})
                        output_data.update({
                            "keyframe_minio_url": upload_result["minio_base_url"],
                            "keyframe_compressed_archive_url": upload_result["archive_url"],
                            "keyframe_files_count": upload_result["total_files"],
                            "keyframe_compression_info": {
                                "original_size": compression_info.get("original_size", 0),
                                "compressed_size": compression_info.get("compressed_size", 0),
                                "compression_ratio": compression_info.get("compression_ratio", 0),
                                "files_count": compression_info.get("files_count", 0),
                                "compression_time": compression_info.get("compression_time", 0),
                                "checksum": compression_info.get("checksum", ""),
                                "format": compression_info.get("format", keyframe_compression_format)
                            }
                        })
                        logger.info(f"[{stage_name}] 关键帧压缩上传成功: {compression_info.get('compression_ratio', 0):.1%} 压缩率, "
                                   f"{upload_result['total_files']} 个文件")
                    else:
                        logger.warning(f"[{stage_name}] 关键帧压缩上传失败: {upload_result.get('error', '未知错误')}")
                        output_data.update({
                            "keyframe_upload_error": upload_result.get("error"),
                            "keyframe_files_count": upload_result.get("total_files", 0)
                        })
                else:
                    # 使用原有的单文件上传（向后兼容）
                    from services.common.minio_directory_upload import upload_keyframes_directory
                    
                    logger.info(f"[{stage_name}] 开始上传关键帧目录到MinIO...")
                    upload_result = upload_keyframes_directory(
                        local_dir=keyframes_dir,
                        workflow_id=workflow_context.workflow_id,
                        delete_local=delete_local_keyframes
                    )
                    
                    if upload_result["success"]:
                        output_data.update({
                            "keyframe_minio_url": upload_result["minio_base_url"],
                            "keyframe_files_count": len(upload_result["uploaded_files"]),
                            "keyframe_uploaded_files": upload_result["uploaded_files"]
                        })
                        logger.info(f"[{stage_name}] 关键帧目录上传成功: {upload_result['total_files']} 个文件")
                    else:
                        logger.warning(f"[{stage_name}] 关键帧目录上传失败: {upload_result.get('error', '未知错误')}")
                        output_data.update({
                            "keyframe_upload_error": upload_result.get("error"),
                            "keyframe_files_count": upload_result["total_files"]
                        })
            except Exception as e:
                logger.warning(f"[{stage_name}] 关键帧目录上传过程出错: {e}", exc_info=True)
                output_data.update({
                    "keyframe_upload_error": str(e),
                    "keyframe_files_count": len(frame_paths)
                })
                # 异常处理后直接返回，避免继续执行传统上传逻辑
                workflow_context.stages[stage_name].status = 'FAILED' if compress_keyframes_before_upload else 'SUCCESS'
                workflow_context.stages[stage_name].output = output_data
                workflow_context.stages[stage_name].error = str(e) if compress_keyframes_before_upload else None
                if compress_keyframes_before_upload:
                    workflow_context.error = f"在阶段 {stage_name} 压缩上传过程中发生错误: {e}"
                return workflow_context.model_dump()
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        logger.info(f"[{stage_name}] 抽帧完成，产物目录: {keyframes_dir}。")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='ffmpeg.extract_audio')
def extract_audio(self: Task, context: dict) -> dict:
    """
    [工作流任务] 从视频中提取音频文件。
    """
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
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，记录全局输入参数
        if not recorded_input_params:
            input_data = workflow_context.input_params.get("input_data", {})
            if input_data.get("video_path"):
                recorded_input_params['video_path'] = input_data.get("video_path")
        
        # MinIO上传参数
        upload_to_minio = get_param_with_fallback(
            "upload_keyframes_to_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        delete_local_keyframes = get_param_with_fallback(
            "delete_local_keyframes_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        
        # 压缩上传参数（新增）
        compress_keyframes_before_upload = get_param_with_fallback(
            "compress_keyframes_before_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        keyframe_compression_format = get_param_with_fallback(
            "keyframe_compression_format",
            resolved_params,
            workflow_context,
            default="zip"
        )
        keyframe_compression_level = get_param_with_fallback(
            "keyframe_compression_level", 
            resolved_params,
            workflow_context,
            default="default"
        )
        
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        # --- 文件下载 ---
        file_service = get_file_service()
        # 优先从 resolved_params 获取参数
        video_path = resolved_params.get("video_path")
        if not video_path:
             video_path = workflow_context.input_params.get("input_data", {}).get("video_path")
             
        if not video_path:
            raise ValueError("缺少必需参数: video_path")
        
        logger.info(f"[{stage_name}] 开始下载视频文件: {video_path}")
        video_path = file_service.resolve_and_download(video_path, workflow_context.shared_storage_path)
        # 更新本地 input_params 中的 video_path 为下载后的本地路径
        workflow_context.stages[stage_name].input_params["video_path"] = video_path
        logger.info(f"[{stage_name}] 视频文件下载完成: {video_path}")
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 在共享存储中创建音频目录
        audio_dir = os.path.join(workflow_context.shared_storage_path, "audio")
        os.makedirs(audio_dir, exist_ok=True)

        # 生成音频文件名
        video_filename = os.path.basename(video_path)
        audio_filename = os.path.splitext(video_filename)[0] + ".wav"
        audio_path = os.path.join(audio_dir, audio_filename)

        logger.info(f"[{stage_name}] 开始从 {video_path} 提取音频...")

        # 使用 ffmpeg 提取音频
        command = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)

            if result.stderr:
                logger.warning(f"[{stage_name}] ffmpeg 有 stderr 输出:\n{result.stderr.strip()}")

            if not os.path.exists(audio_path):
                raise RuntimeError(f"音频提取失败：输出文件不存在 {audio_path}")

            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                raise RuntimeError(f"音频提取失败：输出文件为空 {audio_path}")

            logger.info(f"[{stage_name}] 音频提取完成：{audio_path} (大小: {file_size} 字节)")

            output_data = {"audio_path": audio_path}
            workflow_context.stages[stage_name].status = 'SUCCESS'
            workflow_context.stages[stage_name].output = output_data

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] ffmpeg 音频提取超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"音频提取超时: {e.timeout} 秒") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] ffmpeg 音频提取失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"音频提取失败: ffmpeg 返回码 {e.returncode}") from e

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='ffmpeg.crop_subtitle_images')
@gpu_lock()  # 使用配置化的GPU锁，支持运行时参数调整
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
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，记录全局输入参数
        if not recorded_input_params:
            input_data = workflow_context.input_params.get("input_data", {})
            if input_data.get("video_path"):
                recorded_input_params['video_path'] = input_data.get("video_path")
        
        # MinIO上传参数
        upload_to_minio = get_param_with_fallback(
            "upload_cropped_images_to_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        delete_local_images = get_param_with_fallback(
            "delete_local_cropped_images_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        
        # 压缩上传参数（新增）
        compress_before_upload = get_param_with_fallback(
            "compress_directory_before_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        compression_format = get_param_with_fallback(
            "compression_format",
            resolved_params,
            workflow_context,
            default="zip"
        )
        compression_level = get_param_with_fallback(
            "compression_level", 
            resolved_params,
            workflow_context,
            default="default"
        )
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        video_path = get_param_with_fallback("video_path", resolved_params, workflow_context)

        # --- 文件下载 ---
        file_service = get_file_service()
        logger.info(f"[{stage_name}] 开始下载视频文件: {video_path}")
        video_path = file_service.resolve_and_download(video_path, workflow_context.shared_storage_path)
        # 更新本地 input_params 中的 video_path 为下载后的本地路径
        workflow_context.stages[stage_name].input_params["video_path"] = video_path
        logger.info(f"[{stage_name}] 视频文件下载完成: {video_path}")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 智能字幕区域选择：优先使用传入参数(包括input_data)，其次从上游节点获取
        crop_area = get_param_with_fallback(
            "subtitle_area",
            resolved_params,
            workflow_context,
            fallback_from_stage="paddleocr.detect_subtitle_area"
        )

        if not crop_area:
            raise ValueError("缺少字幕区域坐标信息：请通过 'subtitle_area' 参数传入，或确保 paddleocr.detect_subtitle_area 节点已成功完成并输出了字幕区域数据。")

        cropped_images_dir = os.path.join(workflow_context.shared_storage_path, "cropped_images")

        logger.info(f"[{stage_name}] 准备通过外部脚本从 {video_path} 并发解码并裁剪字幕区域: {crop_area}...")
        
        result_str = ""
        try:
            executor_script_path = os.path.join(os.path.dirname(__file__), "executor_decode_video.py")
            crop_area_json = json.dumps(crop_area)
            num_processes = get_param_with_fallback(
                "decode_processes",
                resolved_params,
                workflow_context,
                default=10
            )

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
                logger.warning(f"[{stage_name}] 视频解码子进程有 stderr 输出:\n{result.stderr.strip()}")

            if not result_str:
                raise RuntimeError("视频解码脚本执行成功，但没有返回任何输出。")

            result_data = json.loads(result_str)
            if not result_data.get("status"):
                raise RuntimeError(f"核心函数 decode_video_concurrently 未能成功完成: {result_data.get('msg')}")

        except json.JSONDecodeError as e:
            logger.error(f"[{stage_name}] JSON解码失败。接收到的原始 stdout 是:\n---\n{result_str}\n---")
            raise RuntimeError("Failed to decode JSON from video decoder subprocess.") from e
        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 视频解码子进程执行超时({e.timeout}秒)。Stderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Video decoding subprocess timed out after {e.timeout} seconds.") from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(f"[{stage_name}] 视频解码子进程执行失败，返回码: {e.returncode}。\nStdout:\n---\n{stdout_output}\n---\nStderr:\n---\n{stderr_output}\n---")
            raise RuntimeError(f"Video decoding subprocess failed with exit code {e.returncode}.") from e

        # 智能路径解析：支持带/不带 frames 子目录的两种模式
        final_frames_path = os.path.join(cropped_images_dir, "frames")
        if not os.path.exists(final_frames_path):
            # 如果 frames 子目录不存在，直接使用 cropped_images 目录
            if os.path.exists(cropped_images_dir):
                logger.warning(f"[{stage_name}] frames 子目录不存在，使用上级目录: {cropped_images_dir}")
                final_frames_path = cropped_images_dir
            else:
                final_frames_path = None

        output_data = {"cropped_images_path": final_frames_path or cropped_images_dir}

        # 如果启用了 MinIO 上传，且路径存在
        if upload_to_minio and final_frames_path and os.path.exists(final_frames_path):
            try:
                # 构建裁剪图片在MinIO中的路径
                minio_base_path = f"{workflow_context.workflow_id}/cropped_images"
                
                if compress_before_upload:
                    # 使用压缩上传
                    from services.common.minio_directory_upload import upload_cropped_images_compressed
                    
                    logger.info(f"[{stage_name}] 开始压缩并上传裁剪图片目录到MinIO...")
                    logger.info(f"[{stage_name}] 压缩格式: {compression_format}, 级别: {compression_level}")
                    
                    upload_result = upload_cropped_images_compressed(
                        local_dir=final_frames_path,
                        workflow_id=workflow_context.workflow_id,
                        delete_local=delete_local_images,
                        compression_format=compression_format,
                        compression_level=compression_level
                    )
                    
                    if upload_result["success"]:
                        compression_info = upload_result.get("compression_info", {})
                        output_data.update({
                            "cropped_images_minio_url": upload_result["minio_base_url"],
                            "compressed_archive_url": upload_result["archive_url"],
                            "cropped_images_files_count": upload_result["total_files"],
                            "compression_info": {
                                "original_size": compression_info.get("original_size", 0),
                                "compressed_size": compression_info.get("compressed_size", 0),
                                "compression_ratio": compression_info.get("compression_ratio", 0),
                                "files_count": compression_info.get("files_count", 0),
                                "compression_time": compression_info.get("compression_time", 0),
                                "checksum": compression_info.get("checksum", ""),
                                "format": compression_info.get("format", compression_format)
                            }
                        })
                        logger.info(f"[{stage_name}] 压缩上传成功: {compression_info.get('compression_ratio', 0):.1%} 压缩率, "
                                   f"{upload_result['total_files']} 个文件")
                    else:
                        logger.warning(f"[{stage_name}] 压缩上传失败，回退到非压缩模式: {upload_result.get('error', '未知错误')}")

                        # 回退到非压缩上传模式
                        from services.common.minio_directory_upload import upload_directory_to_minio

                        logger.info(f"[{stage_name}] 开始回退上传（不使用压缩）...")

                        fallback_result = upload_directory_to_minio(
                            local_dir=final_frames_path,
                            minio_base_path=minio_base_path,
                            file_pattern="*.jpg,*.jpeg,*.png,*.bmp,*.tiff,*.gif",
                            delete_local=delete_local_images,
                            preserve_structure=True
                        )

                        if fallback_result["success"]:
                            output_data.update({
                                "cropped_images_minio_url": fallback_result["minio_base_url"],
                                "cropped_images_files_count": len(fallback_result["uploaded_files"]),
                                "fallback_from_compression": True
                            })
                            logger.info(f"[{stage_name}] 回退上传成功: {fallback_result['total_files']} 个文件")
                        else:
                            logger.error(f"[{stage_name}] 回退上传也失败: {fallback_result.get('error', '未知错误')}")
                            output_data.update({
                                "cropped_images_upload_error": f"压缩失败: {upload_result.get('error')}, 回退也失败: {fallback_result.get('error')}",
                                "cropped_images_files_count": upload_result.get("total_files", 0),
                                "fallback_from_compression": True
                            })
                else:
                    # 使用原有的单文件上传（向后兼容）
                    from services.common.minio_directory_upload import upload_directory_to_minio
                    
                    logger.info(f"[{stage_name}] 开始上传裁剪图片目录到MinIO...")
                    
                    upload_result = upload_directory_to_minio(
                        local_dir=final_frames_path,
                        minio_base_path=minio_base_path,
                        file_pattern="*.jpg,*.jpeg,*.png,*.bmp,*.tiff,*.gif",  # 支持多种图片格式
                        delete_local=delete_local_images,
                        preserve_structure=True
                    )
                    
                    if upload_result["success"]:
                        output_data.update({
                            "cropped_images_minio_url": upload_result["minio_base_url"],
                            "cropped_images_files_count": len(upload_result["uploaded_files"]),
                            # "cropped_images_uploaded_files": upload_result["uploaded_files"]
                        })
                        logger.info(f"[{stage_name}] 裁剪图片目录上传成功: {upload_result['total_files']} 个文件")
                    else:
                        logger.warning(f"[{stage_name}] 裁剪图片目录上传失败: {upload_result.get('error', '未知错误')}")
                        output_data.update({
                            "cropped_images_upload_error": upload_result.get("error"),
                            "cropped_images_files_count": upload_result["total_files"],
                            # "cropped_images_uploaded_files": upload_result["uploaded_files"]
                        })
                        
            except Exception as e:
                logger.warning(f"[{stage_name}] 裁剪图片目录上传过程出错: {e}", exc_info=True)

                # 如果是压缩上传模式，尝试回退到非压缩模式
                if compress_before_upload and final_frames_path and os.path.exists(final_frames_path):
                    logger.info(f"[{stage_name}] 尝试回退上传（异常处理）...")

                    try:
                        from services.common.minio_directory_upload import upload_directory_to_minio

                        fallback_result = upload_directory_to_minio(
                            local_dir=final_frames_path,
                            minio_base_path=minio_base_path,
                            file_pattern="*.jpg,*.jpeg,*.png,*.bmp,*.tiff,*.gif",
                            delete_local=delete_local_images,
                            preserve_structure=True
                        )

                        if fallback_result["success"]:
                            output_data.update({
                                "cropped_images_minio_url": fallback_result["minio_base_url"],
                                "cropped_images_files_count": len(fallback_result["uploaded_files"]),
                                "fallback_from_compression": True,
                                "original_error": str(e)
                            })
                            workflow_context.stages[stage_name].status = 'SUCCESS'
                            workflow_context.stages[stage_name].error = None
                            logger.info(f"[{stage_name}] 异常回退上传成功: {fallback_result['total_files']} 个文件")
                        else:
                            output_data.update({
                                "cropped_images_upload_error": f"压缩异常: {str(e)}, 回退失败: {fallback_result.get('error')}",
                                "cropped_images_files_count": fallback_result.get("total_files", 0),
                                "fallback_from_compression": True
                            })
                            workflow_context.stages[stage_name].status = 'FAILED'
                            workflow_context.stages[stage_name].error = f"压缩异常且回退失败: {str(e)}, 回退: {fallback_result.get('error')}"
                            workflow_context.error = f"在阶段 {stage_name} 压缩上传异常且回退失败"
                    except Exception as fallback_e:
                        logger.error(f"[{stage_name}] 回退上传也出现异常: {fallback_e}", exc_info=True)
                        output_data.update({
                            "cropped_images_upload_error": f"压缩异常: {str(e)}, 回退异常: {str(fallback_e)}",
                            "cropped_images_files_count": len(os.listdir(final_frames_path)) if os.path.exists(final_frames_path) else 0
                        })
                        workflow_context.stages[stage_name].status = 'FAILED'
                        workflow_context.stages[stage_name].error = f"压缩异常且回退异常: {str(e)}, 回退: {str(fallback_e)}"
                        workflow_context.error = f"在阶段 {stage_name} 压缩上传异常且回退也异常"

                    workflow_context.stages[stage_name].output = output_data
                    return workflow_context.model_dump()
                else:
                    # 非压缩模式或路径不存在，直接标记失败
                    output_data.update({
                        "cropped_images_upload_error": str(e),
                        "cropped_images_files_count": len(os.listdir(final_frames_path)) if final_frames_path and os.path.exists(final_frames_path) else 0
                    })
                    workflow_context.stages[stage_name].status = 'FAILED'
                    workflow_context.stages[stage_name].error = str(e)
                    workflow_context.error = f"在阶段 {stage_name} 上传过程中发生错误: {e}"
                    workflow_context.stages[stage_name].output = output_data
                    return workflow_context.model_dump()
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        logger.info(f"[{stage_name}] 字幕条裁剪完成。")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='ffmpeg.split_audio_segments')
def split_audio_segments(self: Task, context: dict) -> dict:
    """
    [工作流任务] 根据字幕文件中的时间戳数据分割音频片段

    此任务根据字幕文件中的时间戳数据，使用ffmpeg循环截取音频中对应的时间区间的音频段，
    为后续语音生成提供数据参考和参考音。支持按说话人分组和多种输出格式。

    输入模式：
    - 工作流模式：自动从工作流上下文获取音频文件和字幕文件路径
    - 单步测试模式：通过参数直接传入音频文件和字幕文件路径

    功能特性：
    - 智能音频源选择（优先人声音频，回退到默认音频）
    - 智能字幕文件选择（支持SRT、JSON等格式）
    - 按说话人分组存储
    - 详细的分割信息和统计
    - 完善的错误处理和进度跟踪
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 导入配置加载器
        from services.common.config_loader import CONFIG

        # 加载ffmpeg_service配置
        ffmpeg_config = CONFIG.get('ffmpeg_service', {})
        split_config = ffmpeg_config.get('split_audio', {})
        subtitle_config = ffmpeg_config.get('subtitle', {})
        audio_source_config = ffmpeg_config.get('audio_source', {})

        # 步骤0: 解析参数
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，记录全局输入参数
        if not recorded_input_params:
            input_data = workflow_context.input_params.get("input_data", {})
            if input_data.get("video_path"):
                recorded_input_params['video_path'] = input_data.get("video_path")
        
        # MinIO上传参数
        upload_to_minio = get_param_with_fallback(
            "upload_keyframes_to_minio",
            resolved_params,
            workflow_context,
            default=False
        )
        delete_local_keyframes = get_param_with_fallback(
            "delete_local_keyframes_after_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        
        # 压缩上传参数（新增）
        compress_keyframes_before_upload = get_param_with_fallback(
            "compress_keyframes_before_upload",
            resolved_params,
            workflow_context,
            default=False
        )
        keyframe_compression_format = get_param_with_fallback(
            "keyframe_compression_format",
            resolved_params,
            workflow_context,
            default="zip"
        )
        keyframe_compression_level = get_param_with_fallback(
            "keyframe_compression_level", 
            resolved_params,
            workflow_context,
            default="default"
        )
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        logger.info(f"[{stage_name}] ========== 音频分割任务开始 ==========")
        logger.info(f"[{stage_name}] 配置加载完成")
        logger.info(f"[{stage_name}] 解析后的节点参数: {resolved_params}")

        # 步骤1: 获取音频文件路径
        audio_path = get_param_with_fallback("audio_path", resolved_params, workflow_context)
        audio_source = "参数传入"

        if not audio_path:
            # 尝试从 audio_separator 获取人声
            audio_path = get_param_with_fallback(
                "vocal_audio", 
                resolved_params, 
                workflow_context, 
                fallback_from_stage="audio_separator.separate_vocals",
                fallback_from_input_data=False
            )
            if audio_path:
                audio_source = "人声音频 (audio_separator)"

        if not audio_path:
            # 尝试从 ffmpeg 获取默认音频
            audio_path = get_param_with_fallback(
                "audio_path", 
                resolved_params, 
                workflow_context, 
                fallback_from_stage="ffmpeg.extract_audio",
                fallback_from_input_data=False
            )
            if audio_path:
                audio_source = "默认音频 (ffmpeg)"

        # 验证音频文件
        if not audio_path or not os.path.exists(audio_path):
            error_msg = "无法获取音频文件路径：请确保 audio_separator.separate_vocals 或 ffmpeg.extract_audio 任务已成功完成，或通过参数传入音频文件"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[{stage_name}] 音频源: {audio_source}, 路径: {audio_path}")

        # 步骤2: 获取字幕文件路径
        subtitle_path = get_param_with_fallback("subtitle_path", resolved_params, workflow_context)
        subtitle_source = "参数传入"

        if not subtitle_path:
            # 尝试从 wservice 获取带说话人SRT
            subtitle_path = get_param_with_fallback(
                "speaker_srt_path",
                resolved_params,
                workflow_context,
                fallback_from_stage="wservice.generate_subtitle_files",
                fallback_from_input_data=False
            )
            if subtitle_path:
                subtitle_source = "带说话人信息SRT"

        if not subtitle_path:
            # 尝试从 wservice 获取基础SRT
            subtitle_path = get_param_with_fallback(
                "subtitle_path",
                resolved_params,
                workflow_context,
                fallback_from_stage="wservice.generate_subtitle_files",
                fallback_from_input_data=False
            )
            if subtitle_path:
                subtitle_source = "基础SRT"

        if not subtitle_path:
            # 尝试从 wservice 获取JSON
            subtitle_path = get_param_with_fallback(
                "speaker_json_path",
                resolved_params,
                workflow_context,
                fallback_from_stage="wservice.generate_subtitle_files",
                fallback_from_input_data=False
            )
            if subtitle_path:
                subtitle_source = "带说话人信息JSON"

        # 验证字幕文件
        if not subtitle_path or not os.path.exists(subtitle_path):
            error_msg = "无法获取字幕文件路径：请确保 faster_whisper.generate_subtitle_files 任务已成功完成，或通过参数传入字幕文件"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[{stage_name}] 字幕源: {subtitle_source}, 路径: {subtitle_path}")

        # 步骤3: 创建输出目录
        output_base_dir = workflow_context.shared_storage_path
        audio_segments_dir = os.path.join(output_base_dir, "audio_segments")
        os.makedirs(audio_segments_dir, exist_ok=True)

        # 步骤4: 配置音频分割器参数
        # 优先级: resolved_params > split_config (from config.yml) > hardcoded defaults
        split_params = {
            'output_format': split_config.get('output_format', 'wav'),
            'sample_rate': split_config.get('sample_rate', 16000),
            'channels': split_config.get('channels', 1),
            'min_segment_duration': split_config.get('min_segment_duration', 1.0),
            'max_segment_duration': split_config.get('max_segment_duration', 30.0),
            'group_by_speaker': split_config.get('group_by_speaker', False),
            'include_silence': split_config.get('include_silence', False),
            # 并发分割配置
            'enable_concurrent': split_config.get('enable_concurrent', True),
            'max_workers': split_config.get('max_workers', 8),
            'concurrent_timeout': split_config.get('concurrent_timeout', 600)
        }
        # 使用解析后的参数覆盖默认配置
        split_params.update(resolved_params)

        logger.info(f"[{stage_name}] 开始执行音频分割...")
        logger.info(f"[{stage_name}] 分割参数: {split_params}")

        # 记录并发配置
        if split_params.get('enable_concurrent'):
            logger.info(f"[{stage_name}] 并发分割已启用，最大工作线程数: {split_params.get('max_workers')}")
        else:
            logger.info(f"[{stage_name}] 使用串行分割模式")

        # 步骤5: 执行音频分割
        result = split_audio_by_segments(
            input_audio=audio_path,
            subtitle_file=subtitle_path,
            output_dir=audio_segments_dir,
            **split_params
        )

        # 步骤6: 验证分割结果
        if result.successful_segments == 0:
            raise RuntimeError("音频分割完成但没有成功生成任何片段")

        logger.info(f"[{stage_name}] ========== 分割结果统计 ==========")
        logger.info(f"[{stage_name}] 总片段数: {result.total_segments}")
        logger.info(f"[{stage_name}] 成功分割: {result.successful_segments}")
        logger.info(f"[{stage_name}] 失败分割: {result.failed_segments}")
        logger.info(f"[{stage_name}] 总时长: {result.total_duration:.2f}s")
        logger.info(f"[{stage_name}] 处理时间: {result.processing_time:.2f}s")

        # 步骤7: 构建输出数据（精简Redis存储）
        output_data = {
            "audio_segments_dir": audio_segments_dir,
            "audio_source": audio_path,  # 修复：存储实际文件路径而非描述
            "subtitle_source": subtitle_path,  # 修复：存储实际文件路径而非描述
            "total_segments": result.total_segments,
            "successful_segments": result.successful_segments,
            "failed_segments": result.failed_segments,
            "total_duration": result.total_duration,
            "processing_time": result.processing_time,
            "audio_format": result.audio_format,
            "sample_rate": result.sample_rate,
            "channels": result.channels,
            "split_info_file": result.split_info_file,
            "segments_count": len(result.segments)
            # 移除：speaker_groups 详细数据，改为通过 split_info_file 引用
        }

        # 添加说话人统计摘要（不存储详细文件列表）
        if result.speaker_groups:
            speaker_summary = {}
            for speaker, segments in result.speaker_groups.items():
                speaker_summary[speaker] = {
                    "count": len(segments),
                    "duration": sum(seg.duration for seg in segments)
                    # 移除：files 列表，减少Redis内存占用
                }
            output_data["speaker_summary"] = speaker_summary

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 音频分割任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()