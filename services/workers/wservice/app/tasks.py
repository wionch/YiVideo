# services/workers/wservice/app/tasks.py
# -*- coding: utf-8 -*-

"""
wservice - 通用工作流服务

负责与GPU无关的、可复用的工作流任务节点，例如字幕文件生成、合并与校正。
"""

import os
import time
import json
import asyncio

from services.common.logger import get_logger
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext
from services.common.config_loader import CONFIG

# 导入 wservice 自己的 Celery app (将在下一步创建)
from .celery_app import celery_app

# 导入重构后的公共字幕合并模块
from services.common.subtitle.subtitle_merger import (
    create_subtitle_merger,
    create_word_level_merger,
    validate_speaker_segments
)
# 导入公共字幕校正模块
from services.common.subtitle.subtitle_correction import SubtitleCorrector
# 导入AI字幕优化模块
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer
from services.common.subtitle.metrics import metrics_collector

logger = get_logger('wservice_tasks')


# ============================================================================
# 数据读取辅助函数 (从 faster_whisper_service 迁移)
# ============================================================================

def load_segments_from_file(segments_file: str) -> list:
    """
    从文件加载segments数据
    """
    try:
        if not os.path.exists(segments_file):
            logger.warning(f"Segments文件不存在: {segments_file}")
            return []
        with open(segments_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'segments' in data:
            return data['segments']
        else:
            logger.warning(f"Segments文件格式无效: {segments_file}")
            return []
    except Exception as e:
        logger.error(f"加载segments文件失败: {e}")
        return []

def load_speaker_data_from_file(diarization_file: str) -> dict:
    """
    从文件加载说话人分离数据
    """
    try:
        if not os.path.exists(diarization_file):
            logger.warning(f"说话人分离文件不存在: {diarization_file}")
            return {}
        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        required_fields = ['speaker_enhanced_segments', 'diarization_segments']
        for field in required_fields:
            if field not in data:
                # This is a soft warning, data might still be usable
                pass
        return data
    except Exception as e:
        logger.error(f"加载说话人分离文件失败: {e}")
        return {}

def get_segments_data(stage_output: dict, field_name: str = None) -> list:
    """
    统一的数据获取接口，支持新旧格式
    """
    if field_name and field_name in stage_output:
        segments = stage_output[field_name]
        if segments and isinstance(segments, list):
            return segments
    segments_file = stage_output.get('segments_file')
    if segments_file:
        return load_segments_from_file(segments_file)
    return []

def segments_to_word_timestamp_json(segments: list, include_segment_info: bool = True) -> str:
    """
    将faster-whisper的segments转换为包含词级时间戳的JSON格式
    """
    result = {
        "format": "word_timestamps",
        "total_segments": len(segments),
        "segments": []
    }
    for i, segment in enumerate(segments):
        segment_data = {
            "id": i + 1,
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        }
        if include_segment_info:
            segment_data["srt_time"] = f"{int(segment['start'] // 3600):02}:{int((segment['start'] % 3600) // 60):02}:{int(segment['start'] % 60):02},{int((segment['start'] * 1000) % 1000):03} --> {int(segment['end'] // 3600):02}:{int((segment['end'] % 3600) // 60):02}:{int(segment['end'] % 60):02},{int((segment['end'] * 1000) % 1000):03}"
        if "words" in segment and segment["words"]:
            segment_data["words"] = []
            for word_info in segment["words"]:
                word_data = {
                    "word": word_info["word"],
                    "start": word_info["start"],
                    "end": word_info["end"],
                    "confidence": word_info.get("confidence", 0.0)
                }
                segment_data["words"].append(word_data)
        else:
            segment_data["words"] = [{
                "word": segment["text"].strip(),
                "start": segment["start"],
                "end": segment["end"],
                "confidence": 1.0
            }]
        result["segments"].append(segment_data)
    return json.dumps(result, indent=2, ensure_ascii=False)

def get_speaker_data(stage_output: dict) -> dict:
    """
    获取说话人分离数据，支持新旧格式
    """
    if 'speaker_enhanced_segments' in stage_output:
        return {
            'speaker_enhanced_segments': stage_output.get('speaker_enhanced_segments'),
            'diarization_segments': stage_output.get('diarization_segments'),
            'detected_speakers': stage_output.get('detected_speakers', []),
            'speaker_statistics': stage_output.get('speaker_statistics', {})
        }
    if 'statistics' in stage_output and isinstance(stage_output['statistics'], dict):
        statistics = stage_output['statistics']
        speaker_data = {
            'detected_speakers': statistics.get('detected_speakers', []),
            'speaker_statistics': statistics.get('speaker_statistics', {}),
            'diarization_duration': statistics.get('diarization_duration', 0)
        }
        diarization_file = stage_output.get('diarization_file')
        if diarization_file:
            detailed_data = load_speaker_data_from_file(diarization_file)
            speaker_data.update({
                'speaker_enhanced_segments': detailed_data.get('speaker_enhanced_segments'),
                'diarization_segments': detailed_data.get('diarization_segments')
            })
        return speaker_data
    diarization_file = stage_output.get('diarization_file')
    if diarization_file:
        return load_speaker_data_from_file(diarization_file)
    return {}

# ============================================================================
# Celery 任务 (从 faster_whisper_service 迁移)
# ============================================================================

@celery_app.task(bind=True, name='wservice.generate_subtitle_files')
def generate_subtitle_files(self, context: dict) -> dict:
    """
    独立字幕文件生成任务节点
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
            raise ValueError("无法获取转录结果：请确保 faster_whisper.transcribe_audio 任务已成功完成")

        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
        has_speaker_info = False
        transcribe_output = transcribe_stage.output

        if not transcribe_output or not isinstance(transcribe_output, dict):
            raise ValueError("转录结果数据格式错误")

        segments = get_segments_data(transcribe_output, 'segments')
        audio_path = transcribe_output.get('audio_path')
        audio_duration = transcribe_output.get('audio_duration', 0)
        language = transcribe_output.get('language', 'unknown')
        enable_word_timestamps = transcribe_output.get('enable_word_timestamps', True)

        if not segments or not audio_path:
            raise ValueError("转录结果中缺少必要的数据（segments 或 audio_path）")

        service_config = CONFIG.get('faster_whisper_service', {})
        speaker_segments = None
        speaker_enhanced_segments = None
        detected_speakers = []
        speaker_statistics = {}

        if diarize_stage and diarize_stage.status in ['SUCCESS', 'COMPLETED']:
            diarize_output = diarize_stage.output
            if diarize_output and isinstance(diarize_output, dict):
                speaker_data = get_speaker_data(diarize_output)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                detected_speakers = speaker_data.get('detected_speakers', [])
                speaker_statistics = speaker_data.get('speaker_statistics', {})

                if speaker_segments and segments and enable_word_timestamps:
                    try:
                        merge_config = service_config.get('subtitle_merge', {})
                        merger = create_word_level_merger(speaker_segments, merge_config)
                        speaker_enhanced_segments = merger.merge(segments)
                        has_speaker_info = True
                    except Exception as e:
                        logger.warning(f"[{stage_name}] 说话人信息合并失败: {e}")
                        has_speaker_info = False
                        speaker_enhanced_segments = None
                else:
                    has_speaker_info = bool(speaker_segments)

        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(audio_path))[0]
        subtitle_filename = f"{base_filename}.srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        with open(subtitle_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                start_str = f"{int(segment['start']//3600):02d}:{int((segment['start']%3600)//60):02d}:{int(segment['start']%60):02d},{int((segment['start']%1)*1000):03d}"
                end_str = f"{int(segment['end']//3600):02d}:{int((segment['end']%3600)//60):02d}:{int(segment['end']%60):02d},{int((segment['end']%1)*1000):03d}"
                f.write(f"{i+1}\n{start_str} --> {end_str}\n{segment['text'].strip()}\n\n")

        output_data = {"subtitle_path": subtitle_path, "subtitle_files": {"basic": subtitle_path}}

        if has_speaker_info and speaker_enhanced_segments:
            speaker_srt_filename = f"{base_filename}_with_speakers.srt"
            speaker_srt_path = os.path.join(subtitles_dir, speaker_srt_filename)
            with open(speaker_srt_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(speaker_enhanced_segments):
                    start_str = f"{int(segment['start']//3600):02d}:{int((segment['start']%3600)//60):02d}:{int(segment['start']%60):02d},{int((segment['start']%1)*1000):03d}"
                    end_str = f"{int(segment['end']//3600):02d}:{int((segment['end']%3600)//60):02d}:{int(segment['end']%60):02d},{int((segment['end']%1)*1000):03d}"
                    speaker = segment.get("speaker", "UNKNOWN")
                    f.write(f"{i+1}\n{start_str} --> {end_str}\n[{speaker}] {segment['text'].strip()}\n\n")
            output_data["speaker_srt_path"] = speaker_srt_path
            output_data["subtitle_files"]["with_speakers"] = speaker_srt_path

        if enable_word_timestamps and segments:
            word_timestamps_filename = f"{base_filename}_word_timestamps.json"
            word_timestamps_json_path = os.path.join(subtitles_dir, word_timestamps_filename)
            json_content = segments_to_word_timestamp_json(segments, include_segment_info=True)
            with open(word_timestamps_json_path, "w", encoding="utf-8") as f:
                f.write(json_content)
            output_data["word_timestamps_json_path"] = word_timestamps_json_path
            output_data["subtitle_files"]["word_timestamps"] = word_timestamps_json_path

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(name='wservice.merge_speaker_segments', bind=True)
def merge_speaker_segments(self, context: dict) -> dict:
    """
    合并转录字幕与说话人时间段(片段级)
    """
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    start_time = time.time()
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    try:
        transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        transcript_segments = get_segments_data(transcribe_stage.output, 'segments')
        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
        speaker_segments = get_speaker_data(diarize_stage.output).get('speaker_enhanced_segments')
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})
        merger = create_subtitle_merger(merge_config)
        merged_segments = merger.merge(transcript_segments, speaker_segments)
        output_data = {'merged_segments': merged_segments}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    return workflow_context.model_dump()


@celery_app.task(name='wservice.merge_with_word_timestamps', bind=True)
def merge_with_word_timestamps(self, context: dict) -> dict:
    """
    使用词级时间戳进行精确字幕合并
    """
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    start_time = time.time()
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    try:
        transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        transcript_segments = get_segments_data(transcribe_stage.output, 'segments')
        if not any('words' in seg and seg['words'] for seg in transcript_segments):
            raise ValueError("转录结果不包含词级时间戳")
        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
        speaker_segments = get_speaker_data(diarize_stage.output).get('speaker_enhanced_segments')
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})
        merger = create_word_level_merger(speaker_segments, merge_config)
        merged_segments = merger.merge(transcript_segments)
        output_data = {'merged_segments': merged_segments}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    return workflow_context.model_dump()


@celery_app.task(bind=True, name='wservice.correct_subtitles')
def correct_subtitles(self, context: dict) -> dict:
    """
    字幕AI校正任务节点
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    try:
        correction_params = workflow_context.input_params.get('params', {}).get('subtitle_correction', {})
        is_enabled = correction_params.get('enabled', False)
        if not is_enabled:
            workflow_context.stages[stage_name].status = 'SKIPPED'
            return workflow_context.model_dump()
        provider = correction_params.get('provider', None)
        generate_stage = workflow_context.stages.get('wservice.generate_subtitle_files')
        subtitle_to_correct = generate_stage.output.get('speaker_srt_path') or generate_stage.output.get('subtitle_path')
        if not subtitle_to_correct or not os.path.exists(subtitle_to_correct):
            raise FileNotFoundError(f"未找到可供校正的字幕文件")
        corrector = SubtitleCorrector(provider=provider)
        corrected_filename = os.path.basename(subtitle_to_correct).replace('.srt', '_corrected_by_ai.srt')
        corrected_path = os.path.join(os.path.dirname(subtitle_to_correct), corrected_filename)
        correction_result = asyncio.run(corrector.correct_subtitle_file(subtitle_path=subtitle_to_correct, output_path=corrected_path))
        if not correction_result.success:
            raise RuntimeError(f"AI字幕校正失败: {correction_result.error_message}")
        output_data = {
            "corrected_subtitle_path": correction_result.corrected_subtitle_path,
            "original_subtitle_path": correction_result.original_subtitle_path,
            "provider_used": correction_result.provider_used,
            "statistics": correction_result.statistics,
        }
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    return workflow_context.model_dump()


@celery_app.task(bind=True, name='wservice.ai_optimize_subtitles')
def ai_optimize_subtitles(self, context: dict) -> dict:
    """
    AI字幕优化任务节点

    通过AI大模型对转录后的字幕进行智能优化和校正，包括：
    1. 修正错别字和语法错误
    2. 添加适当的标点符号
    3. 删除口头禅和填充词
    4. 支持大体积字幕的并发处理
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 获取配置参数
        optimization_params = workflow_context.input_params.get('params', {}).get('subtitle_optimization', {})
        is_enabled = optimization_params.get('enabled', False)

        if not is_enabled:
            logger.info(f"[{stage_name}] 字幕优化未启用，跳过处理")
            workflow_context.stages[stage_name].status = 'SKIPPED'
            return workflow_context.model_dump()

        # 获取AI提供商
        provider = optimization_params.get('provider', 'deepseek')

        # 获取批处理配置
        batch_size = optimization_params.get('batch_size', 50)
        overlap_size = optimization_params.get('overlap_size', 10)

        logger.info(f"[{stage_name}] 开始AI字幕优化 - 提供商: {provider}, "
                   f"批次大小: {batch_size}, 重叠大小: {overlap_size}")

        # 获取转录文件路径
        faster_whisper_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        if not faster_whisper_stage:
            raise FileNotFoundError("未找到faster_whisper转录阶段")

        segments_file = faster_whisper_stage.output.get('segments_file')
        if not segments_file or not os.path.exists(segments_file):
            raise FileNotFoundError(f"未找到转录文件: {segments_file}")

        # 初始化字幕优化器
        optimizer = SubtitleOptimizer(
            batch_size=batch_size,
            overlap_size=overlap_size,
            provider=provider
        )

        # 执行优化
        result = optimizer.optimize_subtitles(
            transcribe_file_path=segments_file,
            output_file_path=None,  # 自动生成输出路径
            prompt_file_path=None   # 使用默认提示词
        )

        if not result['success']:
            raise RuntimeError(f"AI字幕优化失败: {result.get('error', '未知错误')}")

        # 记录指标
        metrics_collector.record_request(
            provider=provider,
            status='success',
            duration=time.time() - start_time
        )
        metrics_collector.set_processing_time(provider, result['processing_time'])
        metrics_collector.set_batch_size(provider, batch_size)
        metrics_collector.record_subtitle_count(
            result['subtitles_count'],
            result['batch_mode']
        )

        # 构造输出数据
        output_data = {
            "optimized_file_path": result['file_path'],
            "original_file_path": segments_file,
            "provider_used": provider,
            "processing_time": result['processing_time'],
            "subtitles_count": result['subtitles_count'],
            "commands_applied": result['commands_applied'],
            "batch_mode": result['batch_mode'],
            "batches_count": result.get('batches_count', 1),
            "statistics": {
                "total_commands": result['commands_applied'],
                "optimization_rate": result['commands_applied'] / max(result['subtitles_count'], 1)
            }
        }

        # 更新工作流状态
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 字幕优化完成 - 文件: {result['file_path']}, "
                   f"处理时间: {result['processing_time']:.2f}秒")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)

        # 记录错误指标
        if 'provider' in locals():
            metrics_collector.record_request(
                provider=provider,
                status='failure',
                duration=time.time() - start_time
            )

        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)

    finally:
        # 记录持续时间
        duration = time.time() - start_time
        workflow_context.stages[stage_name].duration = duration
        state_manager.update_workflow_state(workflow_context)
        logger.info(f"[{stage_name}] 任务完成 - 状态: {workflow_context.stages[stage_name].status}, "
                   f"耗时: {duration:.2f}秒")

    return workflow_context.model_dump()
