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
        enable_word_timestamps = whisperx_config.get('enable_word_timestamps', True)

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
        logger.info(f"[{stage_name}] 词级时间戳启用: {enable_word_timestamps}")

        # 第一步：执行转录
        transcribe_options = {
            "batch_size": batch_size
        }

        result = model.transcribe(audio, **transcribe_options)
        logger.info(f"[{stage_name}] 转录完成")

        # 第二步：如果启用词级时间戳，执行alignment
        if enable_word_timestamps:
            logger.info(f"[{stage_name}] 开始词级时间戳对齐...")

            try:
                # 检测转录结果的语言，用于alignment
                detected_language = result.get("language", whisperx_config.get('language', 'zh'))
                logger.info(f"[{stage_name}] 检测到语言: {detected_language}，开始加载alignment模型")

                # 加载alignment模型
                model_a, metadata = whisperx.load_align_model(
                    language_code=detected_language,
                    device=device
                )
                logger.info(f"[{stage_name}] Alignment模型加载完成")

                # 执行alignment以获取词级时间戳（使用官方推荐的参数）
                alignment_start_time = time.time()
                result = whisperx.align(
                    transcript=result["segments"],          # 转录结果
                    model=model_a,                          # alignment模型
                    align_model_metadata=metadata,          # 模型元数据
                    audio=audio,                            # 音频数据
                    device=device,                          # 设备
                    return_char_alignments=False,           # 关键：返回词级对齐，不是字符级
                    interpolate_method="nearest",           # 插值方法
                    print_progress=True                     # 显示进度
                )

                alignment_duration = time.time() - alignment_start_time
                logger.info(f"[{stage_name}] 词级时间戳对齐完成，耗时: {alignment_duration:.2f}秒")

            except Exception as e:
                logger.warning(f"[{stage_name}] 词级时间戳对齐失败: {e}")
                logger.info(f"[{stage_name}] 将使用基础转录结果继续处理")
                # 对齐失败时，继续使用原始结果

        # 生成字幕文件
        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)

        # 生成SRT字幕文件
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

        logger.info(f"[{stage_name}] SRT字幕生成完成: {subtitle_path} (共{len(segments)}条字幕)")

        # 如果启用词级时间戳，生成JSON文件
        json_subtitle_path = None
        if enable_word_timestamps:
            # 导入JSON生成函数
            from app.model_manager import segments_to_word_timestamp_json

            # 生成JSON字幕文件
            json_subtitle_filename = os.path.splitext(os.path.basename(audio_path))[0] + "_word_timestamps.json"
            json_subtitle_path = os.path.join(subtitles_dir, json_subtitle_filename)

            # 检查词级时间戳质量
            word_count = 0
            char_count = 0
            for segment in segments:
                if "words" in segment and segment["words"]:
                    word_count += len(segment["words"])
                    for word_info in segment["words"]:
                        char_count += len(word_info["word"])

            # 计算平均词长，判断是否为字符级对齐
            avg_word_length = char_count / word_count if word_count > 0 else 0

            logger.info(f"[{stage_name}] 词级时间戳质量检查:")
            logger.info(f"   - 总词数: {word_count}")
            logger.info(f"   - 平均词长: {avg_word_length:.2f}")

            if avg_word_length <= 1.5:
                logger.warning(f"   ⚠️  检测到可能的字符级对齐（平均词长: {avg_word_length:.2f}）")
                logger.warning(f"   ⚠️  如果需要词级对齐，请检查alignment参数设置")
            else:
                logger.info(f"   ✅ 检测到词级对齐（平均词长: {avg_word_length:.2f}）")

            # 生成词级时间戳JSON内容
            json_content = segments_to_word_timestamp_json(segments, include_segment_info=True)

            # 写入JSON文件
            with open(json_subtitle_path, "w", encoding="utf-8") as f:
                f.write(json_content)

            logger.info(f"[{stage_name}] 词级时间戳JSON文件生成完成: {json_subtitle_path}")

        # 如果启用了字幕断句优化，生成优化后的字幕
        optimized_subtitle_path = None
        if enable_word_timestamps and json_subtitle_path:
            try:
                # 导入字幕断句优化器
                from app.subtitle_segmenter import SubtitleSegmenter, SubtitleConfig

                logger.info(f"[{stage_name}] 开始字幕断句优化...")

                # 加载词级时间戳数据
                import json
                with open(json_subtitle_path, "r", encoding="utf-8") as f:
                    word_timestamps_data = json.load(f)

                # 创建断句优化器（使用您指定的配置参数）
                subtitle_config = SubtitleConfig(
                    max_subtitle_duration=5.0,  # 5秒最大时长（按您的要求）
                    min_subtitle_duration=1.2,  # 1.2秒最小时长（按您的要求）
                    max_chars_per_line=40,      # 40字符/行（按您的要求）
                    max_words_per_subtitle=16,  # 16个词最大限制
                    word_gap_threshold=1.2,     # 1.2秒词间间隔（按您的要求）
                    semantic_min_words=6,       # 6个词最小语义单元
                    prefer_complete_phrases=True # 优先保持短语完整性
                )

                segmenter = SubtitleSegmenter(subtitle_config)

                # 执行断句优化
                optimized_segments = segmenter.segment_by_word_timestamps(word_timestamps_data)

                # 保存优化后的SRT字幕文件
                optimized_subtitle_filename = os.path.splitext(os.path.basename(audio_path))[0] + "_optimized.srt"
                optimized_subtitle_path = os.path.join(subtitles_dir, optimized_subtitle_filename)

                # 生成优化后的SRT内容
                optimized_srt_content = segmenter.generate_optimized_srt(optimized_segments)

                with open(optimized_subtitle_path, "w", encoding="utf-8") as f:
                    f.write(optimized_srt_content)

                logger.info(f"[{stage_name}] 优化SRT字幕生成完成: {optimized_subtitle_path} (共{len(optimized_segments)}条字幕)")

                # 保存优化后的JSON文件
                optimized_json_filename = os.path.splitext(os.path.basename(audio_path))[0] + "_optimized_segments.json"
                optimized_json_path = os.path.join(subtitles_dir, optimized_json_filename)

                segmenter.save_optimized_subtitles(optimized_segments,
                                                 os.path.join(subtitles_dir, os.path.splitext(os.path.basename(audio_path))[0]),
                                                 "json")

                logger.info(f"[{stage_name}] 字幕断句优化完成")

            except Exception as e:
                logger.warning(f"[{stage_name}] 字幕断句优化失败: {e}")
                logger.info(f"[{stage_name}] 将使用原始字幕文件继续处理")

        # 构建返回数据
        output_data = {"subtitle_path": subtitle_path}
        if json_subtitle_path:
            output_data["word_timestamps_json_path"] = json_subtitle_path
        if optimized_subtitle_path:
            output_data["optimized_subtitle_path"] = optimized_subtitle_path
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