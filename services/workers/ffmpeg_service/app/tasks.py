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

from celery import Celery
from celery import Task

from services.common import state_manager

# 导入项目定义的标准上下文、状态管理和分布式锁
from services.common.context import StageExecution
from services.common.context import WorkflowContext
# 使用智能锁选择器，根据配置自动选择V1或V2
from services.common.lock_selector import gpu_lock

# 导入该服务内部的核心视频处理逻辑模块
from .modules.video_decoder import extract_random_frames
# 导入音频分割相关模块
from .modules.subtitle_parser import parse_subtitle_segments
from .modules.audio_splitter import AudioSplitter, split_audio_segments as split_audio_by_segments

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

        logger.info(f"[{stage_name}] 开始从 {video_path} 抽取 {num_frames} 帧...")
        
        frame_paths = extract_random_frames(video_path, num_frames, keyframes_dir)

        if not frame_paths:
            raise RuntimeError("核心函数 extract_random_frames 未能成功抽取任何帧。")

        output_data = {"keyframe_dir": keyframes_dir}
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
        video_path = workflow_context.input_params.get("video_path")
        if not video_path or not os.path.exists(video_path):
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
            "-i", video_path,  # 输入视频文件
            "-vn",            # 不包含视频
            "-acodec", "pcm_s16le",  # 16-bit PCM 编码
            "-ar", "16000",   # 采样率 16kHz (WhisperX 推荐的采样率)
            "-ac", "1",       # 单声道
            "-y",             # 覆盖输出文件
            audio_path
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)

            if result.stderr:
                logger.warning(f"[{stage_name}] ffmpeg 有 stderr 输出:\n{result.stderr.strip()}")

            # 验证输出文件
            if not os.path.exists(audio_path):
                raise RuntimeError(f"音频提取失败：输出文件不存在 {audio_path}")

            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                raise RuntimeError(f"音频提取失败：输出文件为空 {audio_path}")

            logger.info(f"[{stage_name}] 音频提取完成：{audio_path} (大小: {file_size} 字节)")

            # 返回音频文件路径
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
        video_path = workflow_context.input_params.get("video_path")
        
        prev_stage = workflow_context.stages.get('paddleocr.detect_subtitle_area')
        prev_stage_output = prev_stage.output if prev_stage else {}
        crop_area = prev_stage_output.get("subtitle_area")
        if not crop_area:
            raise ValueError("上下文中缺少 'subtitle_area' (字幕区域) 信息，无法执行裁剪。")

        cropped_images_dir = os.path.join(workflow_context.shared_storage_path, "cropped_images")

        logger.info(f"[{stage_name}] 准备通过外部脚本从 {video_path} 并发解码并裁剪字幕区域: {crop_area}...")
        
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

        final_frames_path = os.path.join(cropped_images_dir, "frames")
        output_data = {"cropped_images_path": final_frames_path}
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

        logger.info(f"[{stage_name}] ========== 音频分割任务开始 ==========")
        logger.info(f"[{stage_name}] 配置加载完成")

        # 步骤1: 获取音频文件路径
        audio_path = None
        audio_source = ""

        # 检查是否通过参数传入音频文件（单步测试模式）
        audio_path_param = workflow_context.input_params.get("audio_path")
        if audio_path_param and os.path.exists(audio_path_param):
            audio_path = audio_path_param
            audio_source = "参数传入"
            logger.info(f"[{stage_name}] 使用参数传入的音频文件: {audio_path}")
        else:
            # 工作流模式：从上下文中自动获取音频文件
            logger.info(f"[{stage_name}] 开始音频源选择逻辑...")
            priority_order = audio_source_config.get('priority_order', ["vocal_audio", "audio_path"])

            for source_type in priority_order:
                if source_type == "vocal_audio":
                    # 检查 audio_separator.separate_vocals 阶段的人声音频输出
                    audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
                    if (audio_separator_stage and
                        audio_separator_stage.status in ['SUCCESS', 'COMPLETED'] and
                        audio_separator_stage.output and
                        isinstance(audio_separator_stage.output, dict) and
                        audio_separator_stage.output.get('vocal_audio')):
                        audio_path = audio_separator_stage.output['vocal_audio']
                        audio_source = "人声音频 (audio_separator)"
                        logger.info(f"[{stage_name}] 成功获取人声音频: {audio_path}")
                        break

                elif source_type == "audio_path":
                    # 检查 ffmpeg.extract_audio 阶段的默认音频输出
                    ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
                    if (ffmpeg_stage and
                        ffmpeg_stage.status in ['SUCCESS', 'COMPLETED'] and
                        ffmpeg_stage.output and
                        isinstance(ffmpeg_stage.output, dict) and
                        ffmpeg_stage.output.get('audio_path')):
                        audio_path = ffmpeg_stage.output['audio_path']
                        audio_source = "默认音频 (ffmpeg)"
                        logger.info(f"[{stage_name}] 成功获取默认音频: {audio_path}")
                        break

        # 验证音频文件
        if not audio_path or not os.path.exists(audio_path):
            error_msg = "无法获取音频文件路径：请确保 audio_separator.separate_vocals 或 ffmpeg.extract_audio 任务已成功完成，或通过参数传入音频文件"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[{stage_name}] 音频源: {audio_source}, 路径: {audio_path}")

        # 步骤2: 获取字幕文件路径
        subtitle_path = None
        subtitle_source = ""

        # 检查是否通过参数传入字幕文件（单步测试模式）
        subtitle_path_param = workflow_context.input_params.get("subtitle_path")
        if subtitle_path_param and os.path.exists(subtitle_path_param):
            subtitle_path = subtitle_path_param
            subtitle_source = "参数传入"
            logger.info(f"[{stage_name}] 使用参数传入的字幕文件: {subtitle_path}")
        else:
            # 工作流模式：从上下文中自动获取字幕文件
            logger.info(f"[{stage_name}] 开始字幕文件选择逻辑...")
            priority_order = subtitle_config.get('priority_order', ["speaker_srt_path", "subtitle_path", "speaker_json_path"])

            for source_type in priority_order:
                subtitle_stage = workflow_context.stages.get('whisperx.generate_subtitle_files')
                if subtitle_stage and subtitle_stage.status in ['SUCCESS', 'COMPLETED'] and subtitle_stage.output:
                    if source_type == "speaker_srt_path" and subtitle_stage.output.get('speaker_srt_path'):
                        subtitle_path = subtitle_stage.output['speaker_srt_path']
                        subtitle_source = "带说话人信息SRT"
                        break
                    elif source_type == "subtitle_path" and subtitle_stage.output.get('subtitle_path'):
                        subtitle_path = subtitle_stage.output['subtitle_path']
                        subtitle_source = "基础SRT"
                        break
                    elif source_type == "speaker_json_path" and subtitle_stage.output.get('speaker_json_path'):
                        subtitle_path = subtitle_stage.output['speaker_json_path']
                        subtitle_source = "带说话人信息JSON"
                        break

        # 验证字幕文件
        if not subtitle_path or not os.path.exists(subtitle_path):
            error_msg = "无法获取字幕文件路径：请确保 whisperx.generate_subtitle_files 任务已成功完成，或通过参数传入字幕文件"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[{stage_name}] 字幕源: {subtitle_source}, 路径: {subtitle_path}")

        # 步骤3: 创建输出目录
        output_base_dir = workflow_context.shared_storage_path
        audio_segments_dir = os.path.join(output_base_dir, "audio_segments")
        os.makedirs(audio_segments_dir, exist_ok=True)

        # 步骤4: 配置音频分割器参数
        split_params = {
            'output_format': split_config.get('output_format', 'wav'),
            'sample_rate': split_config.get('sample_rate', 16000),
            'channels': split_config.get('channels', 1),
            'min_segment_duration': split_config.get('min_segment_duration', 1.0),
            'max_segment_duration': split_config.get('max_segment_duration', 30.0),
            'group_by_speaker': split_config.get('group_by_speaker', True),
            'include_silence': split_config.get('include_silence', False),
            # 并发分割配置
            'enable_concurrent': split_config.get('enable_concurrent', True),
            'max_workers': split_config.get('max_workers', 8),
            'concurrent_timeout': split_config.get('concurrent_timeout', 600)
        }

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