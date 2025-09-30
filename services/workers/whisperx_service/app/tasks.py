# services/workers/whisperx_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
WhisperX Service 的 Celery 任务定义。
"""

import os
import time
import whisperx

from services.common.logger import get_logger
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext

# 导入 Celery 应用配置
from app.celery_app import celery_app

# 导入新的通用配置加载器
from services.common.config_loader import CONFIG

logger = get_logger('tasks')

@celery_app.task(bind=True, name='whisperx.generate_subtitles')
def generate_subtitles(self, context: dict) -> dict:
    """
    使用WhisperX进行ASR，生成字幕文件。

    注意：此任务应接收由 ffmpeg.extract_audio 任务处理好的音频文件路径，
    而不是直接处理视频文件。这符合服务分离的设计原则。
    """
    from celery import Task

    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 从前一个任务的输出中获取音频文件路径
        audio_path = None

        # 检查 ffmpeg.extract_audio 阶段的输出
        ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.status == 'SUCCESS':
            if hasattr(ffmpeg_stage.output, 'audio_path'):
                audio_path = ffmpeg_stage.output.audio_path
            elif isinstance(ffmpeg_stage.output, dict) and 'audio_path' in ffmpeg_stage.output:
                audio_path = ffmpeg_stage.output['audio_path']

        if not audio_path:
            raise ValueError("无法获取音频文件路径：请确保 ffmpeg.extract_audio 任务已成功完成")

        logger.info(f"[{stage_name}] 开始处理音频: {audio_path}")

        # 验证音频文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 加载配置（实时读取，支持热重载）
        whisperx_config = CONFIG.get('whisperx_service', {})
        model_name = whisperx_config.get('model_name', 'base')
        device = whisperx_config.get('device', 'cpu')
        compute_type = whisperx_config.get('compute_type', 'float32')
        batch_size = whisperx_config.get('batch_size', 16)

        logger.info(f"[{stage_name}] 配置已实时读取，支持热重载")

        # CUDA检测和设备自动切换
        if device == 'cuda':
            try:
                import torch
                if not torch.cuda.is_available():
                    logger.warning(f"[{stage_name}] CUDA不可用，自动切换到CPU模式")
                    device = 'cpu'
                    # 如果是CUDA模式，通常用float16，切换CPU后改为float32更稳定
                    if compute_type == 'float16':
                        compute_type = 'float32'
                        logger.info(f"[{stage_name}] CPU模式：自动调整计算类型为 float32")
                else:
                    logger.info(f"[{stage_name}] CUDA可用，使用GPU模式")
            except ImportError:
                logger.warning(f"[{stage_name}] PyTorch未安装，自动切换到CPU模式")
                device = 'cpu'
                compute_type = 'float32'

        logger.info(f"[{stage_name}] 使用配置: {model_name} (batch_size={batch_size})")
        logger.info(f"[{stage_name}] 最终设备: {device}, 计算类型: {compute_type}")

        # 加载音频
        audio = whisperx.load_audio(audio_path)
        audio_duration = audio.shape[0] / 16000  # 假设16kHz采样率
        logger.info(f"[{stage_name}] 音频加载完成，时长: {audio_duration:.2f}s")

        # 加载模型并转录
        logger.info(f"[{stage_name}] 加载模型: {model_name}")

        # 检查Hugging Face Token是否已配置
        hf_token = os.getenv('HF_TOKEN')
        if hf_token:
            logger.info(f"[{stage_name}] Hugging Face Token已配置，将使用环境变量中的token")
        else:
            logger.warning(f"[{stage_name}] 未找到Hugging Face Token，可能会遇到访问限制")

        # 直接加载模型，token将通过环境变量自动获取
        model = whisperx.load_model(model_name, device, compute_type=compute_type)

        logger.info(f"[{stage_name}] 开始转录...")
        result = model.transcribe(audio, batch_size=batch_size)
        logger.info(f"[{stage_name}] 转录完成")

        # 生成字幕文件
        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)

        subtitle_filename = os.path.splitext(os.path.basename(audio_path))[0] + ".srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        # 转换为SRT格式
        segments = result["segments"]
        with open(subtitle_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                segment_start = segment["start"]
                segment_end = segment["end"]
                text = segment["text"].strip()

                # 格式化为SRT时间格式
                start_str = f"{int(segment_start//3600):02d}:{int((segment_start%3600)//60):02d}:{int(segment_start%60):02d},{int((segment_start%1)*1000):03d}"
                end_str = f"{int(segment_end//3600):02d}:{int((segment_end%3600)//60):02d}:{int(segment_end%60):02d},{int((segment_end%1)*1000):03d}"

                f.write(f"{i+1}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{text}\n\n")

        logger.info(f"[{stage_name}] 字幕生成完成: {subtitle_path} (共{len(segments)}条字幕)")

        # 返回字幕文件路径
        output_data = {"subtitle_path": subtitle_path}
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

    return workflow_context.model_dump()