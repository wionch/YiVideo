# services/workers/whisperx_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
WhisperX Service 的 Celery 任务定义。
优化版本：直接使用faster-whisper原生API的词级时间戳功能，参考v3脚本实现。
修复版本：解决WhisperX封装层词级时间戳丢失问题，使用faster-whisper原生API。
GPU锁版本：使用GPU锁装饰器保护GPU资源，实现细粒度资源管理。
"""

import os
import time
import json
import numpy as np

from services.common.logger import get_logger
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext

# 导入 Celery 应用配置
from app.celery_app import celery_app

# 导入新的通用配置加载器
from services.common.config_loader import CONFIG

# 导入GPU锁装饰器
from services.common.locks import gpu_lock

logger = get_logger('tasks')


# ============================================================================
# Redis数据优化 - 数据读取辅助函数
# ============================================================================

def load_segments_from_file(segments_file: str) -> list:
    """
    从文件加载segments数据

    Args:
        segments_file: segments数据文件路径

    Returns:
        list: segments列表，失败时返回空列表
    """
    try:
        if not os.path.exists(segments_file):
            logger.warning(f"Segments文件不存在: {segments_file}")
            return []

        with open(segments_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 支持两种文件格式：直接的segments数组或包含segments的对象
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

    Args:
        diarization_file: 说话人分离数据文件路径

    Returns:
        dict: 包含说话人分离信息的字典，失败时返回空字典
    """
    try:
        if not os.path.exists(diarization_file):
            logger.warning(f"说话人分离文件不存在: {diarization_file}")
            return {}

        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 验证必要的数据字段
        required_fields = ['speaker_enhanced_segments', 'diarization_segments']
        for field in required_fields:
            if field not in data:
                logger.warning(f"说话人分离文件缺少字段 {field}: {diarization_file}")

        return data

    except Exception as e:
        logger.error(f"加载说话人分离文件失败: {e}")
        return {}


def get_segments_data(stage_output: dict, field_name: str = None) -> list:
    """
    统一的数据获取接口，支持新旧格式

    Args:
        stage_output: 任务输出数据
        field_name: 字段名称（'segments', 'original_segments', 'speaker_enhanced_segments', 'diarization_segments'）

    Returns:
        list: segments数据
    """
    # 优先尝试直接从输出中获取segments数据（旧格式兼容）
    if field_name and field_name in stage_output:
        segments = stage_output[field_name]
        if segments and isinstance(segments, list):
            return segments

    # 尝试从文件加载（新格式优化）
    segments_file = stage_output.get('segments_file')
    if segments_file:
        return load_segments_from_file(segments_file)

    # 如果都没有，返回空列表
    return []


def get_speaker_data(stage_output: dict) -> dict:
    """
    获取说话人分离数据，支持新旧格式

    Args:
        stage_output: 任务输出数据

    Returns:
        dict: 说话人分离数据
    """
    # 优先尝试直接从输出中获取（旧格式兼容）
    if 'speaker_enhanced_segments' in stage_output:
        return {
            'speaker_enhanced_segments': stage_output.get('speaker_enhanced_segments'),
            'diarization_segments': stage_output.get('diarization_segments'),
            'detected_speakers': stage_output.get('detected_speakers', []),
            'speaker_statistics': stage_output.get('speaker_statistics', {})
        }

    # 尝试从精简格式中获取统计信息（新优化格式）
    if 'statistics' in stage_output and isinstance(stage_output['statistics'], dict):
        statistics = stage_output['statistics']
        # 从statistics对象中提取说话人信息
        speaker_data = {
            'detected_speakers': statistics.get('detected_speakers', []),
            'speaker_statistics': statistics.get('speaker_statistics', {}),
            'diarization_duration': statistics.get('diarization_duration', 0)
        }

        # 检查是否有文件路径，尝试加载详细数据
        diarization_file = stage_output.get('diarization_file')
        if diarization_file:
            detailed_data = load_speaker_data_from_file(diarization_file)
            # 合并详细数据和统计摘要
            speaker_data.update({
                'speaker_enhanced_segments': detailed_data.get('speaker_enhanced_segments'),
                'diarization_segments': detailed_data.get('diarization_segments')
            })

        return speaker_data

    # 尝试从文件加载（旧新格式兼容）
    diarization_file = stage_output.get('diarization_file')
    if diarization_file:
        return load_speaker_data_from_file(diarization_file)

    # 如果都没有，返回空字典
    return {}


def _transcribe_audio_with_lock(audio_path: str, whisperx_config: dict, stage_name: str) -> dict:
    """
    使用faster-whisper原生API进行ASR，生成转录结果。
    
    根据配置条件性使用GPU锁：
    - CUDA模式：使用GPU锁
    - CPU模式：跳过GPU锁
    
    Args:
        audio_path: 音频文件路径
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    # 检查是否需要使用GPU锁
    need_gpu_lock = _should_use_gpu_lock_for_transcription(whisperx_config)
    
    if need_gpu_lock:
        # 需要GPU锁，调用带锁版本
        return _transcribe_audio_with_gpu_lock(audio_path, whisperx_config, stage_name)
    else:
        # 不需要GPU锁，直接执行
        logger.info(f"[{stage_name}] 语音转录使用非GPU模式，跳过GPU锁")
        return _transcribe_audio_without_lock(audio_path, whisperx_config, stage_name)


@gpu_lock()  # 仅在CUDA模式下获取GPU锁
def _transcribe_audio_with_gpu_lock(audio_path: str, whisperx_config: dict, stage_name: str) -> dict:
    """
    带GPU锁的语音转录功能（CUDA模式）
    
    Args:
        audio_path: 音频文件路径
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    logger.info(f"[{stage_name}] 语音转录使用GPU锁模式（CUDA）")
    # 直接执行转录逻辑，GPU锁由装饰器管理
    return _execute_transcription(audio_path, whisperx_config, stage_name)


def _transcribe_audio_without_lock(audio_path: str, whisperx_config: dict, stage_name: str) -> dict:
    """
    不带GPU锁的语音转录功能（CPU模式）
    
    Args:
        audio_path: 音频文件路径
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    logger.info(f"[{stage_name}] 语音转录使用非GPU模式")
    # 直接执行转录逻辑，无需GPU锁
    return _execute_transcription(audio_path, whisperx_config, stage_name)


def _execute_transcription(audio_path: str, whisperx_config: dict, stage_name: str) -> dict:
    """
    执行语音转录的核心逻辑（无GPU锁）
    
    Args:
        audio_path: 音频文件路径
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    logger.info(f"[{stage_name}] 开始处理音频: {audio_path}")
    
    # 验证音频文件是否存在
    if not os.path.exists(audio_path):
        error_msg = f"音频文件不存在: {audio_path}"
        logger.error(f"[{stage_name}] {error_msg}")
        # 抛出ValueError而不是FileNotFoundError，避免触发Celery重试机制
        raise ValueError(error_msg)

    # 加载配置参数
    model_name = whisperx_config.get('model_name', 'base')
    device = whisperx_config.get('device', 'cpu')
    compute_type = whisperx_config.get('compute_type', 'float32')
    enable_word_timestamps = whisperx_config.get('enable_word_timestamps', True)

    logger.info(f"[{stage_name}] 使用配置: {model_name}")
    logger.info(f"[{stage_name}] 设备: {device}, 计算类型: {compute_type}")

    # CUDA检测和设备自动切换
    if device == 'cuda':
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning(f"[{stage_name}] CUDA不可用，自动切换到CPU模式")
                device = 'cpu'
                if compute_type == 'float16':
                    compute_type = 'float32'
                    logger.info(f"[{stage_name}] CPU模式：自动调整计算类型为 float32")
            else:
                logger.info(f"[{stage_name}] CUDA可用，使用GPU模式")
        except ImportError:
            logger.warning(f"[{stage_name}] PyTorch未安装，自动切换到CPU模式")
            device = 'cpu'
            compute_type = 'float32'

    # 加载音频
    import librosa
    audio, sr = librosa.load(audio_path, sr=16000)  # 确保采样率为16kHz
    audio_duration = len(audio) / sr
    logger.info(f"[{stage_name}] 音频加载完成，时长: {audio_duration:.2f}s")

    # 检查Hugging Face Token是否已配置
    hf_token = os.getenv('HF_TOKEN')
    if hf_token:
        logger.info(f"[{stage_name}] Hugging Face Token已配置，将使用环境变量中的token")
    else:
        logger.warning(f"[{stage_name}] 未找到Hugging Face Token，可能会遇到访问限制")

    # 加载模型并转录
    logger.info(f"[{stage_name}] 加载faster-whisper模型: {model_name} (使用原生API)")
    
    # 导入faster-whisper模型
    from faster_whisper import WhisperModel
    
    # 直接创建faster-whisper模型实例
    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type
    )

    logger.info(f"[{stage_name}] 开始转录...")
    logger.info(f"[{stage_name}] 词级时间戳JSON文件生成: {'启用' if enable_word_timestamps else '禁用'}")

    # 执行转录 - 使用faster-whisper的原生API
    transcribe_options = {
        "beam_size": 3,
        "best_of": 3,
        "temperature": (0.0, 0.2, 0.4, 0.6),
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 2.4,
        "no_speech_threshold": 0.5,
        "without_timestamps": False,
        "word_timestamps": True,
        "language": whisperx_config.get('language', None),
    }

    transcribe_start_time = time.time()
    
    # 使用faster-whisper的原生transcribe方法
    segments_generator, info = model.transcribe(
        audio,
        **transcribe_options
    )
    
    # 将生成器转换为列表，同时提取词级时间戳信息
    segments = []
    for segment in segments_generator:
        # 转换Segment对象到字典格式
        segment_dict = {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "words": []  # 包含词级时间戳
        }
        
        # 添加词级时间戳信息（如果存在）
        if segment.words:
            for word in segment.words:
                word_dict = {
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                    "probability": word.probability
                }
                segment_dict["words"].append(word_dict)
        
        segments.append(segment_dict)
    
    transcribe_duration = time.time() - transcribe_start_time

    logger.info(f"[{stage_name}] 转录完成，耗时: {transcribe_duration:.2f}秒")
    logger.info(f"[{stage_name}] 转录完成，词级时间戳已启用（确保时间戳准确度）")

    # 构建返回数据
    result = {
        "segments": segments,
        "audio_path": audio_path,
        "audio_duration": audio_duration,
        "language": info.language,
        "transcribe_duration": transcribe_duration,
        "model_name": model_name,
        "device": device,
        "enable_word_timestamps": enable_word_timestamps
    }

    # 显式释放faster-whisper模型
    logger.info(f"[{stage_name}] 开始释放faster-whisper模型...")
    try:
        # 如果是CUDA模式，将模型移至CPU
        if device == 'cuda':
            import torch
            if hasattr(model, 'model'):
                # faster-whisper内部模型对象
                if hasattr(model.model, 'cpu'):
                    model.model.cpu()
            # 尝试移动整个模型对象
            if hasattr(model, 'cpu'):
                model.cpu()

        # 删除模型引用
        del model
        logger.info(f"[{stage_name}] faster-whisper模型已删除")

        # 强制垃圾回收
        import gc
        collected = gc.collect()
        logger.info(f"[{stage_name}] 垃圾回收: 清理了 {collected} 个对象")

    except Exception as e:
        logger.warning(f"[{stage_name}] 释放模型时出错: {e}")

    # 执行GPU显存清理
    _cleanup_gpu_memory(stage_name)

    return result


def _diarize_speakers_with_lock(audio_path: str, transcribe_result: dict, whisperx_config: dict, stage_name: str) -> dict:
    """
    执行说话人分离功能，支持本地CUDA模式和远程付费接口模式。
    
    根据配置条件性使用GPU锁：
    - 本地CUDA模式：使用GPU锁
    - 付费接口模式：跳过GPU锁
    - CPU模式：跳过GPU锁
    
    Args:
        audio_path: 音频文件路径
        transcribe_result: 转录结果
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 说话人分离结果
    """
    # 检查是否需要使用GPU锁
    need_gpu_lock = _should_use_gpu_lock_for_diarization(whisperx_config)
    
    if need_gpu_lock:
        # 需要GPU锁，调用带锁版本
        return _diarize_speakers_with_gpu_lock(audio_path, transcribe_result, whisperx_config, stage_name)
    else:
        # 不需要GPU锁，直接执行
        logger.info(f"[{stage_name}] 说话人分离使用非GPU模式，跳过GPU锁")
        return _diarize_speakers_without_lock(audio_path, transcribe_result, whisperx_config, stage_name)


@gpu_lock()  # 仅在本地CUDA模式下获取GPU锁
def _diarize_speakers_with_gpu_lock(audio_path: str, transcribe_result: dict, whisperx_config: dict, stage_name: str) -> dict:
    """
    带GPU锁的说话人分离功能（本地CUDA模式）
    
    Args:
        audio_path: 音频文件路径
        transcribe_result: 转录结果
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 说话人分离结果
    """
    logger.info(f"[{stage_name}] 说话人分离使用GPU锁模式（本地CUDA）")
    # 直接执行说话人分离逻辑，GPU锁由装饰器管理
    return _execute_speaker_diarization(audio_path, transcribe_result, whisperx_config, stage_name)


def _diarize_speakers_without_lock(audio_path: str, transcribe_result: dict, whisperx_config: dict, stage_name: str) -> dict:
    """
    不带GPU锁的说话人分离功能（付费接口模式或CPU模式）
    
    Args:
        audio_path: 音频文件路径
        transcribe_result: 转录结果
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 说话人分离结果
    """
    logger.info(f"[{stage_name}] 说话人分离使用非GPU模式")
    # 直接执行说话人分离逻辑，无需GPU锁
    return _execute_speaker_diarization(audio_path, transcribe_result, whisperx_config, stage_name)


def _execute_speaker_diarization(audio_path: str, transcribe_result: dict, whisperx_config: dict, stage_name: str) -> dict:
    """
    执行说话人分离的核心逻辑（无GPU锁）
    
    Args:
        audio_path: 音频文件路径
        transcribe_result: 转录结果
        whisperx_config: WhisperX配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 说话人分离结果
    """
    logger.info(f"[{stage_name}] 开始处理音频: {audio_path}")
    logger.info(f"[{stage_name}] 转录片段数: {len(transcribe_result.get('segments', []))}")

    # 验证音频文件是否存在
    if not os.path.exists(audio_path):
        error_msg = f"音频文件不存在: {audio_path}"
        logger.error(f"[{stage_name}] {error_msg}")
        # 抛出ValueError而不是FileNotFoundError，避免触发Celery重试机制
        raise ValueError(error_msg)

    # 检查说话人分离是否启用
    enable_diarization = whisperx_config.get('enable_diarization', False)
    
    if not enable_diarization:
        logger.info(f"[{stage_name}] 说话人分离功能已禁用，跳过处理")
        return {
            "segments": transcribe_result['segments'],
            "audio_path": audio_path,
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "diarization_enabled": False,
            "speaker_enhanced_segments": None
        }

    logger.info(f"[{stage_name}] 开始说话人分离...")
    diarization_start_time = time.time()

    try:
        # 导入说话人分离模块
        from app.speaker_diarization import create_speaker_diarizer_v2

        # 创建说话人分离器
        diarizer = create_speaker_diarizer_v2(whisperx_config)

        # 执行说话人分离
        diarization_annotation = diarizer.diarize(audio_path)

        # 使用新的转换函数处理pyannote Annotation
        from app.speaker_word_matcher import convert_annotation_to_segments
        diarization_segments = convert_annotation_to_segments(diarization_annotation)

        # 使用词级时间戳进行精确匹配
        speaker_enhanced_segments = None
        if transcribe_result['segments']:
            try:
                # 导入词级匹配器
                from app.speaker_word_matcher import create_speaker_word_matcher

                logger.info(f"[{stage_name}] 使用词级时间戳进行精确说话人匹配")
                word_matcher = create_speaker_word_matcher(diarization_segments, whisperx_config)

                # 生成增强的字幕片段
                speaker_enhanced_segments = word_matcher.generate_enhanced_subtitles(transcribe_result['segments'])

                logger.info(f"[{stage_name}] 词级匹配完成，生成 {len(speaker_enhanced_segments)} 个精确片段")

            except Exception as e:
                logger.warning(f"[{stage_name}] 词级匹配失败: {e}，回退到传统匹配方式")
                # 回退到传统合并方式
                speaker_enhanced_segments = diarizer.merge_transcript_with_diarization(
                    transcript_segments=transcribe_result['segments'],
                    diarization_segments=diarization_segments
                )

        # 清理资源
        diarizer.cleanup()

        diarization_duration = time.time() - diarization_start_time
        logger.info(f"[{stage_name}] 说话人分离完成，耗时: {diarization_duration:.2f}秒")

        # 统计说话人信息
        speakers = set()
        if speaker_enhanced_segments:
            for segment in speaker_enhanced_segments:
                if 'speaker' in segment:
                    speakers.add(segment['speaker'])

        logger.info(f"[{stage_name}] 检测到 {len(speakers)} 个说话人: {sorted(speakers)}")

        # 构建返回数据
        result = {
            "segments": transcribe_result['segments'],
            "audio_path": audio_path,
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "diarization_enabled": True,
            "speaker_enhanced_segments": speaker_enhanced_segments,
            "diarization_segments": diarization_segments,
            "diarization_duration": diarization_duration
        }

    except Exception as e:
        logger.warning(f"[{stage_name}] 说话人分离失败: {e}")
        logger.info(f"[{stage_name}] 将使用基础转录结果继续处理")
        
        # 分离失败时，返回原始转录结果
        result = {
            "segments": transcribe_result['segments'],
            "audio_path": audio_path,
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "diarization_enabled": False,
            "speaker_enhanced_segments": None,
            "diarization_error": str(e)
        }

    # 执行统一的GPU显存清理
    _cleanup_gpu_memory(stage_name)

    return result


def _cleanup_gpu_memory(stage_name: str) -> None:
    """
    通用的GPU显存清理函数

    Args:
        stage_name: 阶段名称（用于日志）
    """
    try:
        import gc
        import torch

        # 强制垃圾回收
        logger.info(f"[{stage_name}] 开始GPU显存清理...")
        for round_num in range(5):
            collected = gc.collect()
            if collected > 0:
                logger.debug(f"[{stage_name}] 垃圾回收第{round_num+1}轮: 清理了 {collected} 个对象")
            else:
                break

        # PyTorch模型和缓存清理
        if torch.cuda.is_available():
            # 记录清理前的显存使用情况
            before_allocated = torch.cuda.memory_allocated() / 1024**3  # GB
            before_cached = torch.cuda.memory_reserved() / 1024**3  # GB

            logger.debug(f"[{stage_name}] 清理前显存状态:")
            logger.debug(f"  已分配: {before_allocated:.2f}GB")
            logger.debug(f"  缓存: {before_cached:.2f}GB")

            # 激进的CUDA缓存清理 - 增强版
            for device_id in range(torch.cuda.device_count()):
                try:
                    with torch.cuda.device(device_id):
                        # 多轮清理以确保彻底释放
                        for _ in range(3):
                            torch.cuda.empty_cache()
                            torch.cuda.ipc_collect()
                            gc.collect()
                except:
                    pass

            torch.cuda.synchronize()

            # 重置内存统计
            try:
                current_device = torch.cuda.current_device()
                torch.cuda.reset_peak_memory_stats(current_device)
                torch.cuda.reset_accumulated_memory_stats(current_device)
            except:
                pass

            # 再次垃圾回收和缓存清理 - 增强到5轮
            for _ in range(5):
                gc.collect()
                torch.cuda.empty_cache()

            torch.cuda.synchronize()

            # 记录清理后的显存使用情况
            after_allocated = torch.cuda.memory_allocated() / 1024**3  # GB
            after_cached = torch.cuda.memory_reserved() / 1024**3  # GB

            freed_allocated = before_allocated - after_allocated
            freed_cached = before_cached - after_cached

            logger.info(f"[{stage_name}] GPU显存清理完成:")
            logger.info(f"  已分配显存: {before_allocated:.2f}GB -> {after_allocated:.2f}GB (释放 {freed_allocated:.2f}GB)")
            logger.info(f"  缓存显存: {before_cached:.2f}GB -> {after_cached:.2f}GB (释放 {freed_cached:.2f}GB)")

        else:
            logger.debug(f"[{stage_name}] CUDA不可用，跳过GPU显存清理")

    except ImportError as e:
        logger.debug(f"[{stage_name}] PyTorch未安装，跳过CUDA缓存清理: {e}")
    except Exception as e:
        logger.warning(f"[{stage_name}] GPU显存清理时出错: {e}", exc_info=True)


def _should_use_gpu_lock_for_transcription(whisperx_config: dict) -> bool:
    """
    判断语音转录是否应该使用GPU锁
    
    根据需求：
    - 需要上gpu锁任务: cuda模式下的: `语音转录功能`
    - 不需要上gpu锁的任务: cpu模式下的`语音转录功能`
    
    Args:
        whisperx_config: WhisperX配置
    
    Returns:
        bool: True表示应该使用GPU锁
    """
    try:
        # 获取设备配置
        device = whisperx_config.get('device', 'cpu')
        
        # 检查CUDA可用性
        if device == 'cuda':
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("[whisperx] CUDA模式语音转录，需要GPU锁")
                    return True
                else:
                    logger.info("[whisperx] CUDA不可用，语音转录使用CPU模式，跳过GPU锁")
                    return False
            except ImportError:
                logger.warning("[whisperx] PyTorch未安装，语音转录使用CPU模式，跳过GPU锁")
                return False
        else:
            logger.info(f"[whisperx] {device}模式语音转录，跳过GPU锁")
            return False
            
    except Exception as e:
        logger.warning(f"[whisperx] 检查语音转录GPU锁需求时出错: {e}")
        # 出错时默认不使用GPU锁，避免阻塞
        return False


def _should_use_gpu_lock_for_diarization(whisperx_config: dict) -> bool:
    """
    判断说话人分离是否应该使用GPU锁
    
    根据需求：
    - 需要上gpu锁任务: cuda模式下的: `语音转录功能`; 本地模型cuda模式下的`说话人分离功能`
    - 不需要上gpu锁的任务: 付费接口模式下的`说话人分离功能`; cpu模式下的`说话人分离功能`
    
    Args:
        whisperx_config: WhisperX配置
    
    Returns:
        bool: True表示应该使用GPU锁
    """
    try:
        # 导入说话人分离模块
        from app.speaker_diarization import SpeakerDiarizerV2
        
        # 创建临时实例来检查配置
        temp_diarizer = SpeakerDiarizerV2(whisperx_config)
        
        # 检查是否使用付费模式
        if temp_diarizer._use_premium_mode():
            logger.info("[whisperx] 付费模式说话人分离，跳过GPU锁")
            return False
        
        # 检查设备类型
        device = temp_diarizer.device
        if device == 'cuda':
            logger.info("[whisperx] 本地CUDA模式说话人分离，需要GPU锁")
            return True
        else:
            logger.info(f"[whisperx] {device}模式说话人分离，跳过GPU锁")
            return False
            
    except Exception as e:
        logger.warning(f"[whisperx] 检查说话人分离GPU锁需求时出错: {e}")
        # 出错时默认不使用GPU锁，避免阻塞
        return False


@celery_app.task(bind=True, name='whisperx.generate_subtitles')
def generate_subtitles(self, context: dict) -> dict:
    """
    WhisperX 字幕生成任务，支持GPU锁管理。
    
    此任务作为唯一入口，内部调用带GPU锁的函数来执行GPU操作：
    1. 调用 _transcribe_audio_with_lock 进行语音转录（CUDA模式下使用GPU锁）
    2. 根据配置调用 _diarize_speakers_with_lock 进行说话人分离（本地CUDA模式下使用GPU锁）
    3. 生成最终的字幕文件
    
    GPU锁说明：
    - CUDA模式下的语音转录功能会自动获取GPU锁
    - 本地模型CUDA模式下的说话人分离功能会自动获取GPU锁
    - CPU模式和付费接口模式下直接执行，无需等待锁
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
        audio_source = ""

        logger.info(f"[{stage_name}] 开始音频源选择逻辑")
        logger.info(f"[{stage_name}] 当前工作流阶段数量: {len(workflow_context.stages)}")
        logger.info(f"[{stage_name}] 可用阶段列表: {list(workflow_context.stages.keys())}")

        # 优先检查 audio_separator.separate_vocals 阶段的人声音频输出
        audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
        logger.debug(f"[{stage_name}] 检查 audio_separator.separate_vocals 阶段: 状态={audio_separator_stage.status if audio_separator_stage else 'None'}")

        if audio_separator_stage and audio_separator_stage.status in ['SUCCESS', 'COMPLETED']:
            logger.debug(f"[{stage_name}] audio_separator 阶段输出类型: {type(audio_separator_stage.output)}")
            logger.debug(f"[{stage_name}] audio_separator 输出内容: {audio_separator_stage.output}")

            # 直接检查 vocal_audio 字段
            if (audio_separator_stage.output and
                isinstance(audio_separator_stage.output, dict) and
                audio_separator_stage.output.get('vocal_audio')):
                audio_path = audio_separator_stage.output['vocal_audio']
                audio_source = "人声音频 (audio_separator)"
                logger.info(f"[{stage_name}] 成功获取人声音频: {audio_path}")

        # 如果没有人声音频，回退到 ffmpeg.extract_audio 的默认音频
        if not audio_path:
            ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
            logger.debug(f"[{stage_name}] 检查 ffmpeg.extract_audio 阶段: 状态={ffmpeg_stage.status if ffmpeg_stage else 'None'}")

            if ffmpeg_stage and ffmpeg_stage.status in ['SUCCESS', 'COMPLETED']:
                logger.debug(f"[{stage_name}] ffmpeg 阶段输出类型: {type(ffmpeg_stage.output)}")
                logger.debug(f"[{stage_name}] ffmpeg 输出内容: {ffmpeg_stage.output}")

                # 尝试从字典中获取 audio_path
                if (ffmpeg_stage.output and
                    isinstance(ffmpeg_stage.output, dict) and
                    ffmpeg_stage.output.get('audio_path')):
                    audio_path = ffmpeg_stage.output['audio_path']
                    audio_source = "默认音频 (ffmpeg)"
                    logger.info(f"[{stage_name}] 成功获取默认音频: {audio_path}")
                else:
                    logger.warning(f"[{stage_name}] ffmpeg 输出中未找到 audio_path 字段")

        if not audio_path:
            # 提供更详细的错误信息帮助调试
            logger.error(f"[{stage_name}] 无法获取音频文件路径")
            logger.error(f"[{stage_name}] 检查的工作流阶段:")

            # 检查ffmpeg阶段
            ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
            if ffmpeg_stage:
                logger.error(f"[{stage_name}] - ffmpeg.extract_audio: 状态={ffmpeg_stage.status}")
                if hasattr(ffmpeg_stage, 'output') and ffmpeg_stage.output:
                    logger.error(f"[{stage_name}] - ffmpeg.extract_audio.output: {ffmpeg_stage.output}")
                elif isinstance(ffmpeg_stage.output, dict):
                    logger.error(f"[{stage_name}] - ffmpeg.extract_audio.output (dict): {ffmpeg_stage.output}")
            else:
                logger.error(f"[{stage_name}] - ffmpeg.extract_audio: 未找到阶段信息")

            # 检查audio_separator阶段
            audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
            if audio_separator_stage:
                logger.error(f"[{stage_name}] - audio_separator.separate_vocals: 状态={audio_separator_stage.status}")
                if hasattr(audio_separator_stage, 'output') and audio_separator_stage.output:
                    logger.error(f"[{stage_name}] - audio_separator.separate_vocals.output: {audio_separator_stage.output}")
                    if isinstance(audio_separator_stage.output, dict):
                        logger.error(f"[{stage_name}] - vocal_audio: {'存在' if audio_separator_stage.output.get('vocal_audio') else '不存在'}")
                        logger.error(f"[{stage_name}] - audio_list: {'存在' if audio_separator_stage.output.get('audio_list') else '不存在'}")
                elif isinstance(audio_separator_stage.output, dict):
                    logger.error(f"[{stage_name}] - audio_separator.separate_vocals.output (dict): {audio_separator_stage.output}")
                    logger.error(f"[{stage_name}] - vocal_audio: {'存在' if audio_separator_stage.output.get('vocal_audio') else '不存在'}")
                    logger.error(f"[{stage_name}] - audio_list: {'存在' if audio_separator_stage.output.get('audio_list') else '不存在'}")
            else:
                logger.error(f"[{stage_name}] - audio_separator.separate_vocals: 未找到阶段信息")

            # 检查context中的音频路径（仅显示是否存在，不显示完整路径）
            logger.error(f"[{stage_name}] context中的音频路径:")
            logger.error(f"[{stage_name}] - audio_path: {'存在' if context.get('audio_path') else '不存在'}")

            # 检查输入参数中的文件名（不显示完整路径）
            input_params = workflow_context.input_params
            if input_params:
                video_path = input_params.get('video_path', '')
                if video_path:
                    video_name = os.path.basename(video_path)
                    logger.error(f"[{stage_name}] 原始视频文件: {video_name}")

            raise ValueError("无法获取音频文件路径：请确保 ffmpeg.extract_audio 或 audio_separator.separate_vocals 任务已成功完成")

        logger.info(f"[{stage_name}] ========== 音频源选择结果 ==========")
        logger.info(f"[{stage_name}] 选择的音频源: {audio_source}")
        logger.info(f"[{stage_name}] 音频文件路径: {audio_path}")
        logger.info(f"[{stage_name}] =================================")

        # 加载配置
        whisperx_config = CONFIG.get('whisperx_service', {})
        enable_diarization = whisperx_config.get('enable_diarization', False)
        show_speaker_labels = whisperx_config.get('show_speaker_labels', True)
        enable_word_timestamps = whisperx_config.get('enable_word_timestamps', True)

        logger.info(f"[{stage_name}] 开始字幕生成流程")
        logger.info(f"[{stage_name}] 说话人分离: {'启用' if enable_diarization else '禁用'}")
        logger.info(f"[{stage_name}] 词级时间戳: {'启用' if enable_word_timestamps else '禁用'}")

        # 第一步：调用带GPU锁的转录函数
        logger.info(f"[{stage_name}] 步骤1: 执行语音转录")
        transcribe_result = _transcribe_audio_with_lock(audio_path, whisperx_config, stage_name)
        logger.info(f"[{stage_name}] 转录完成，获得 {len(transcribe_result.get('segments', []))} 个片段")

        # 第二步：如果启用说话人分离，调用带GPU锁的说话人分离函数
        speaker_enhanced_segments = None
        diarization_segments = None
        
        if enable_diarization:
            logger.info(f"[{stage_name}] 步骤2: 执行说话人分离")
            diarize_result = _diarize_speakers_with_lock(audio_path, transcribe_result, whisperx_config, stage_name)
            
            speaker_enhanced_segments = diarize_result.get('speaker_enhanced_segments')
            diarization_segments = diarize_result.get('diarization_segments')
            
            if speaker_enhanced_segments:
                logger.info(f"[{stage_name}] 说话人分离完成，获得 {len(speaker_enhanced_segments)} 个增强片段")
            else:
                logger.warning(f"[{stage_name}] 说话人分离未返回增强片段")

        # 第三步：生成字幕文件
        logger.info(f"[{stage_name}] 步骤3: 生成字幕文件")
        
        # 获取基本信息
        audio_duration = transcribe_result.get('audio_duration', 0)
        language = transcribe_result.get('language', 'unknown')
        segments = transcribe_result.get('segments', [])
        
        # 创建字幕目录
        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)

        # 生成基础SRT字幕文件
        subtitle_filename = os.path.splitext(os.path.basename(audio_path))[0] + ".srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        # 转换为SRT格式
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

        logger.info(f"[{stage_name}] 基础SRT字幕生成完成: {subtitle_path} (共{len(segments)}条字幕)")

        # 初始化输出数据
        output_data = {"subtitle_path": subtitle_path}

        # 如果启用说话人分离且成功，生成带说话人信息的字幕文件
        speaker_srt_path = None
        speaker_json_path = None

        if enable_diarization and speaker_enhanced_segments and show_speaker_labels:
            try:
                # 生成带说话人信息的SRT字幕文件
                speaker_srt_filename = os.path.splitext(os.path.basename(audio_path))[0] + "_with_speakers.srt"
                speaker_srt_path = os.path.join(subtitles_dir, speaker_srt_filename)

                with open(speaker_srt_path, "w", encoding="utf-8") as f:
                    for i, segment in enumerate(speaker_enhanced_segments):
                        segment_start = segment["start"]
                        segment_end = segment["end"]
                        text = segment["text"].strip()
                        speaker = segment.get("speaker", "UNKNOWN")
                        confidence = segment.get("speaker_confidence", 0.0)

                        # 格式化为SRT时间格式
                        start_str = f"{int(segment_start//3600):02d}:{int((segment_start%3600)//60):02d}:{int(segment_start%60):02d},{int((segment_start%1)*1000):03d}"
                        end_str = f"{int(segment_end//3600):02d}:{int((segment_end%3600)//60):02d}:{int(segment_end%60):02d},{int((segment_end%1)*1000):03d}"

                        f.write(f"{i+1}\n")
                        f.write(f"{start_str} --> {end_str}\n")
                        f.write(f"[{speaker}] {text}\n\n")

                logger.info(f"[{stage_name}] 带说话人信息的SRT字幕生成完成: {speaker_srt_path} (共{len(speaker_enhanced_segments)}条字幕)")

                # 生成带说话人信息的JSON文件
                speaker_json_filename = os.path.splitext(os.path.basename(audio_path))[0] + "_with_speakers.json"
                speaker_json_path = os.path.join(subtitles_dir, speaker_json_filename)

                # 构建带说话人信息的JSON数据
                import json
                speaker_json_data = {
                    "metadata": {
                        "audio_file": os.path.basename(audio_path),
                        "total_duration": audio_duration,
                        "language": language,
                        "word_timestamps_enabled": enable_word_timestamps,
                        "diarization_enabled": enable_diarization,
                        "speakers": sorted(set(seg.get("speaker", "UNKNOWN") for seg in speaker_enhanced_segments)) if speaker_enhanced_segments else [],
                        "total_segments": len(speaker_enhanced_segments),
                        "transcribe_method": "gpu-lock-v2"  # 标识使用GPU锁版本
                    },
                    "segments": []
                }

                for i, segment in enumerate(speaker_enhanced_segments):
                    segment_data = {
                        "id": i + 1,
                        "start": segment["start"],
                        "end": segment["end"],
                        "duration": segment["end"] - segment["start"],
                        "text": segment["text"].strip(),
                        "speaker": segment.get("speaker", "UNKNOWN"),
                        "speaker_confidence": segment.get("speaker_confidence", 0.0)
                    }

                    # 如果有词级时间戳，添加到JSON中
                    if "words" in segment and segment["words"]:
                        segment_data["words"] = segment["words"]

                    speaker_json_data["segments"].append(segment_data)

                # 写入JSON文件
                with open(speaker_json_path, "w", encoding="utf-8") as f:
                    json.dump(speaker_json_data, f, ensure_ascii=False, indent=2)

                logger.info(f"[{stage_name}] 带说话人信息的JSON文件生成完成: {speaker_json_path}")

                # 生成说话人统计信息
                speaker_stats = {}
                if speaker_enhanced_segments:
                    for segment in speaker_enhanced_segments:
                        speaker = segment.get("speaker", "UNKNOWN")
                        duration = segment["end"] - segment["start"]
                        if speaker not in speaker_stats:
                            speaker_stats[speaker] = {"duration": 0.0, "segments": 0, "words": 0}
                        speaker_stats[speaker]["duration"] += duration
                        speaker_stats[speaker]["segments"] += 1
                        if "words" in segment:
                            speaker_stats[speaker]["words"] += len(segment["words"])

                logger.info(f"[{stage_name}] 说话人统计信息:")
                for speaker in sorted(speaker_stats.keys()):
                    stats = speaker_stats[speaker]
                    duration_percentage = (stats["duration"] / audio_duration) * 100 if audio_duration > 0 else 0
                    logger.info(f"  {speaker}: {stats['segments']}段, {stats['duration']:.2f}秒 ({duration_percentage:.1f}%), {stats['words']}词")

                # 添加到输出数据
                output_data["speaker_srt_path"] = speaker_srt_path
                output_data["speaker_json_path"] = speaker_json_path

            except Exception as e:
                logger.warning(f"[{stage_name}] 生成带说话人信息的字幕文件失败: {e}")

        # 如果启用词级时间戳，生成JSON文件
        json_subtitle_path = None
        if enable_word_timestamps and segments:
            try:
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
                    logger.warning(f"   ⚠️  词级时间戳质量可能不佳")
                else:
                    logger.info(f"   ✅ 检测到词级对齐（平均词长: {avg_word_length:.2f}）")

                # 生成词级时间戳JSON内容
                json_content = segments_to_word_timestamp_json(segments, include_segment_info=True)

                # 写入JSON文件
                with open(json_subtitle_path, "w", encoding="utf-8") as f:
                    f.write(json_content)

                logger.info(f"[{stage_name}] 词级时间戳JSON文件生成完成: {json_subtitle_path}")
                
                # 添加到输出数据
                output_data["word_timestamps_json_path"] = json_subtitle_path

            except Exception as e:
                logger.warning(f"[{stage_name}] 生成词级时间戳JSON文件失败: {e}")

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        
        logger.info(f"[{stage_name}] 字幕生成任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


# ============================================================================
# WhisperX 功能拆分 - 独立任务节点
# ============================================================================

@celery_app.task(bind=True, name='whisperx.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    """
    WhisperX 独立转录任务节点

    此任务专门负责音频文件的语音转录功能，是WhisperX功能拆分的第一步。
    使用GPU锁装饰器保护GPU资源，支持CUDA和CPU模式。

    输入：音频文件路径（通过工作流上下文获取）
    输出：标准化的转录结果，包含segments、词级时间戳等

    GPU锁说明：
    - CUDA模式：自动获取GPU锁
    - CPU模式：跳过GPU锁，直接执行
    """
    import json

    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 从前一个任务的输出中获取音频文件路径
        audio_path = None
        audio_source = ""

        logger.info(f"[{stage_name}] ========== 音频源选择逻辑 ==========")
        logger.info(f"[{stage_name}] 当前工作流阶段数量: {len(workflow_context.stages)}")
        logger.info(f"[{stage_name}] 可用阶段列表: {list(workflow_context.stages.keys())}")

        # 优先检查 audio_separator.separate_vocals 阶段的人声音频输出
        audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
        logger.debug(f"[{stage_name}] 检查 audio_separator.separate_vocals 阶段: 状态={audio_separator_stage.status if audio_separator_stage else 'None'}")

        if audio_separator_stage and audio_separator_stage.status in ['SUCCESS', 'COMPLETED']:
            logger.debug(f"[{stage_name}] audio_separator 阶段输出类型: {type(audio_separator_stage.output)}")
            logger.debug(f"[{stage_name}] audio_separator 输出内容: {audio_separator_stage.output}")

            # 直接检查 vocal_audio 字段
            if (audio_separator_stage.output and
                isinstance(audio_separator_stage.output, dict) and
                audio_separator_stage.output.get('vocal_audio')):
                audio_path = audio_separator_stage.output['vocal_audio']
                audio_source = "人声音频 (audio_separator)"
                logger.info(f"[{stage_name}] 成功获取人声音频: {audio_path}")

        # 如果没有人声音频，回退到 ffmpeg.extract_audio 的默认音频
        if not audio_path:
            ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
            logger.debug(f"[{stage_name}] 检查 ffmpeg.extract_audio 阶段: 状态={ffmpeg_stage.status if ffmpeg_stage else 'None'}")

            if ffmpeg_stage and ffmpeg_stage.status in ['SUCCESS', 'COMPLETED']:
                logger.debug(f"[{stage_name}] ffmpeg 阶段输出类型: {type(ffmpeg_stage.output)}")
                logger.debug(f"[{stage_name}] ffmpeg 输出内容: {ffmpeg_stage.output}")

                # 尝试从字典中获取 audio_path
                if (ffmpeg_stage.output and
                    isinstance(ffmpeg_stage.output, dict) and
                    ffmpeg_stage.output.get('audio_path')):
                    audio_path = ffmpeg_stage.output['audio_path']
                    audio_source = "默认音频 (ffmpeg)"
                    logger.info(f"[{stage_name}] 成功获取默认音频: {audio_path}")

        if not audio_path:
            error_msg = "无法获取音频文件路径：请确保 ffmpeg.extract_audio 或 audio_separator.separate_vocals 任务已成功完成"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[{stage_name}] ========== 音频源选择结果 ==========")
        logger.info(f"[{stage_name}] 选择的音频源: {audio_source}")
        logger.info(f"[{stage_name}] 音频文件路径: {audio_path}")
        logger.info(f"[{stage_name}] =================================")

        # 加载WhisperX配置
        whisperx_config = CONFIG.get('whisperx_service', {})
        enable_word_timestamps = whisperx_config.get('enable_word_timestamps', True)

        logger.info(f"[{stage_name}] 开始语音转录流程")
        logger.info(f"[{stage_name}] 词级时间戳: {'启用' if enable_word_timestamps else '禁用'}")

        # 执行语音转录
        logger.info(f"[{stage_name}] 执行语音转录...")
        transcribe_result = _transcribe_audio_with_lock(audio_path, whisperx_config, stage_name)

        logger.info(f"[{stage_name}] 转录完成，获得 {len(transcribe_result.get('segments', []))} 个片段")

        # 优化：使用工作流ID的前8位作为文件标识，避免冗余的UUID
        workflow_short_id = workflow_context.workflow_id[:8]  # 取工作流ID前8位

        # 创建转录数据文件
        transcribe_data_file = os.path.join(
            workflow_context.shared_storage_path,
            f"transcribe_data_{workflow_short_id}.json"
        )

        # 准备转录数据文件内容
        transcribe_data_content = {
            "metadata": {
                "task_name": stage_name,
                "workflow_id": workflow_context.workflow_id,
                "audio_file": os.path.basename(audio_path),
                "audio_source": audio_source,
                "total_duration": transcribe_result.get('audio_duration', 0),
                "language": transcribe_result.get('language', 'unknown'),
                "word_timestamps_enabled": enable_word_timestamps,
                "model_name": transcribe_result.get('model_name', 'unknown'),
                "device": transcribe_result.get('device', 'unknown'),
                "transcribe_method": "gpu-lock-v3-split",
                "created_at": time.time()
            },
            "segments": transcribe_result.get('segments', []),
            "statistics": {
                "total_segments": len(transcribe_result.get('segments', [])),
                "total_words": sum(len(seg.get('words', [])) for seg in transcribe_result.get('segments', [])),
                "transcribe_duration": transcribe_result.get('transcribe_duration', 0),
                "average_segment_duration": 0
            }
        }

        # 计算平均片段时长
        if transcribe_data_content["statistics"]["total_segments"] > 0:
            total_duration = sum(seg.get('end', 0) - seg.get('start', 0) for seg in transcribe_result.get('segments', []))
            transcribe_data_content["statistics"]["average_segment_duration"] = total_duration / transcribe_data_content["statistics"]["total_segments"]

        # 写入转录数据文件
        with open(transcribe_data_file, "w", encoding="utf-8") as f:
            json.dump(transcribe_data_content, f, ensure_ascii=False, indent=2)

        logger.info(f"[{stage_name}] 转录数据文件生成完成: {transcribe_data_file}")

        # 统计信息
        total_words = transcribe_data_content["statistics"]["total_words"]
        transcribe_duration = transcribe_result.get('transcribe_duration', 0)
        audio_duration = transcribe_result.get('audio_duration', 0)

        logger.info(f"[{stage_name}] ========== 转录统计信息 ==========")
        logger.info(f"[{stage_name}] 总片段数: {transcribe_data_content['statistics']['total_segments']}")
        logger.info(f"[{stage_name}] 总词数: {total_words}")
        logger.info(f"[{stage_name}] 音频时长: {audio_duration:.2f}秒")
        logger.info(f"[{stage_name}] 转录耗时: {transcribe_duration:.2f}秒")
        if transcribe_duration > 0:
            logger.info(f"[{stage_name}] 处理速度: {audio_duration/transcribe_duration:.2f}x")
        logger.info(f"[{stage_name}] =================================")

        # 构建输出数据 - Redis优化版本：精简segments数据，仅存储文件路径
        output_data = {
            # 优化：将segments数组替换为文件路径，大幅减少Redis内存占用
            "segments_file": transcribe_data_file,  # 替代 "segments": transcribe_result.get('segments', [])
            "audio_path": transcribe_result.get('audio_path', audio_path),
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "transcribe_duration": transcribe_result.get('transcribe_duration', 0),
            "model_name": transcribe_result.get('model_name', 'unknown'),
            "device": transcribe_result.get('device', 'unknown'),
            "enable_word_timestamps": enable_word_timestamps,
            "transcribe_data_file": transcribe_data_file,
            "statistics": transcribe_data_content["statistics"],

            # 兼容性：保留segments_count用于快速统计
            "segments_count": len(transcribe_result.get('segments', []))
        }

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 语音转录任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='whisperx.diarize_speakers')
def diarize_speakers(self, context: dict) -> dict:
    """
    WhisperX 独立说话人分离任务节点

    此任务专门负责对转录结果进行说话人分离功能，是WhisperX功能拆分的第二步。
    接收转录任务的输出作为输入，为转录片段添加说话人信息。

    输入：转录结果（通过工作流上下文从 whisperx.transcribe_audio 获取）
    输出：带有说话人信息的增强片段和统计信息

    GPU锁说明：
    - 本地CUDA模式：自动获取GPU锁
    - 付费接口模式：跳过GPU锁，直接执行
    - CPU模式：跳过GPU锁，直接执行
    """
    import json

    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 从前一个任务的输出中获取转录结果
        transcribe_stage = workflow_context.stages.get('whisperx.transcribe_audio')
        if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
            error_msg = "无法获取转录结果：请确保 whisperx.transcribe_audio 任务已成功完成"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 获取转录结果数据
        transcribe_output = transcribe_stage.output
        if not transcribe_output or not isinstance(transcribe_output, dict):
            error_msg = "转录结果数据格式错误"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # Redis优化：使用统一的数据获取接口，支持新旧格式
        segments = get_segments_data(transcribe_output, 'segments')
        audio_path = transcribe_output.get('audio_path')
        transcribe_data_file = transcribe_output.get('transcribe_data_file')

        if not segments or not audio_path:
            error_msg = "转录结果中缺少必要的数据（segments 或 audio_path）"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 记录数据来源
        if 'segments_file' in transcribe_output:
            logger.info(f"[{stage_name}] 从优化文件加载segments: {transcribe_output['segments_file']}")
        else:
            logger.info(f"[{stage_name}] 从Redis内存加载segments (旧格式)")

        logger.info(f"[{stage_name}] ========== 输入数据验证 ==========")
        logger.info(f"[{stage_name}] 转录片段数: {len(segments)}")
        logger.info(f"[{stage_name}] 音频文件: {audio_path}")
        logger.info(f"[{stage_name}] 转录数据文件: {transcribe_data_file}")
        logger.info(f"[{stage_name}] 语言: {transcribe_output.get('language', 'unknown')}")
        logger.info(f"[{stage_name}] 音频时长: {transcribe_output.get('audio_duration', 0):.2f}秒")
        logger.info(f"[{stage_name}] =================================")

        # 验证音频文件是否存在
        if not os.path.exists(audio_path):
            error_msg = f"音频文件不存在: {audio_path}"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 验证转录数据文件是否存在
        if transcribe_data_file and os.path.exists(transcribe_data_file):
            try:
                with open(transcribe_data_file, 'r', encoding='utf-8') as f:
                    transcribe_data = json.load(f)
                logger.info(f"[{stage_name}] 成功读取转录数据文件: {transcribe_data_file}")
            except Exception as e:
                logger.warning(f"[{stage_name}] 读取转录数据文件失败: {e}，将使用内存中的数据")
                transcribe_data = None
        else:
            logger.info(f"[{stage_name}] 转录数据文件不存在或未指定，使用内存中的数据")
            transcribe_data = None

        # 加载WhisperX配置
        whisperx_config = CONFIG.get('whisperx_service', {})
        enable_diarization = whisperx_config.get('enable_diarization', False)

        logger.info(f"[{stage_name}] 开始说话人分离流程")
        logger.info(f"[{stage_name}] 说话人分离: {'启用' if enable_diarization else '禁用'}")

        # 构建转录结果字典格式
        transcribe_result = {
            'segments': segments,
            'audio_path': audio_path,
            'audio_duration': transcribe_output.get('audio_duration', 0),
            'language': transcribe_output.get('language', 'unknown'),
            'transcribe_duration': transcribe_output.get('transcribe_duration', 0),
            'model_name': transcribe_output.get('model_name', 'unknown'),
            'device': transcribe_output.get('device', 'unknown'),
            'enable_word_timestamps': transcribe_output.get('enable_word_timestamps', True)
        }

        # 执行说话人分离
        speaker_enhanced_segments = None
        diarization_segments = None
        diarization_enabled = False

        if enable_diarization:
            logger.info(f"[{stage_name}] 执行说话人分离...")
            diarize_result = _diarize_speakers_with_lock(audio_path, transcribe_result, whisperx_config, stage_name)

            speaker_enhanced_segments = diarize_result.get('speaker_enhanced_segments')
            diarization_segments = diarize_result.get('diarization_segments')
            diarization_enabled = diarize_result.get('diarization_enabled', False)

            if speaker_enhanced_segments:
                logger.info(f"[{stage_name}] 说话人分离完成，获得 {len(speaker_enhanced_segments)} 个增强片段")
            else:
                logger.warning(f"[{stage_name}] 说话人分离未返回增强片段")
        else:
            logger.info(f"[{stage_name}] 说话人分离功能已禁用，跳过处理")

        # 优化：使用工作流ID的前8位作为文件标识，避免冗余的UUID
        workflow_short_id = workflow_context.workflow_id[:8]  # 取工作流ID前8位

        # 创建说话人分离数据文件
        diarization_data_file = os.path.join(
            workflow_context.shared_storage_path,
            f"diarization_data_{workflow_short_id}.json"
        )

        # 准备说话人分离数据文件内容
        diarization_data_content = {
            "metadata": {
                "task_name": stage_name,
                "workflow_id": workflow_context.workflow_id,
                "audio_file": os.path.basename(audio_path),
                "total_duration": transcribe_result.get('audio_duration', 0),
                "language": transcribe_result.get('language', 'unknown'),
                "diarization_enabled": diarization_enabled,
                "diarization_method": "gpu-lock-v3-split",
                "created_at": time.time(),
                "source_transcribe_file": transcribe_data_file
            },
            "original_segments": transcribe_result['segments'],
            "speaker_enhanced_segments": speaker_enhanced_segments,
            "diarization_segments": diarization_segments,
            "statistics": {
                "total_original_segments": len(transcribe_result['segments']),
                "total_enhanced_segments": len(speaker_enhanced_segments) if speaker_enhanced_segments else 0,
                "total_diarization_segments": len(diarization_segments) if diarization_segments else 0,
                "diarization_duration": 0,
                "detected_speakers": [],
                "speaker_statistics": {}
            }
        }

        # 如果启用了说话人分离且成功，添加统计信息
        if diarization_enabled and speaker_enhanced_segments:
            # 获取说话人分离耗时
            diarization_duration = diarize_result.get('diarization_duration', 0)
            diarization_data_content["statistics"]["diarization_duration"] = diarization_duration

            # 统计说话人信息
            speakers = set()
            speaker_stats = {}

            for segment in speaker_enhanced_segments:
                speaker = segment.get("speaker", "UNKNOWN")
                duration = segment["end"] - segment["start"]

                speakers.add(speaker)

                if speaker not in speaker_stats:
                    speaker_stats[speaker] = {
                        "duration": 0.0,
                        "segments": 0,
                        "words": 0
                    }

                speaker_stats[speaker]["duration"] += duration
                speaker_stats[speaker]["segments"] += 1

                # 统计词数
                if "words" in segment and segment["words"]:
                    speaker_stats[speaker]["words"] += len(segment["words"])

            diarization_data_content["statistics"]["detected_speakers"] = sorted(speakers)
            diarization_data_content["statistics"]["speaker_statistics"] = speaker_stats

            logger.info(f"[{stage_name}] 检测到 {len(speakers)} 个说话人: {sorted(speakers)}")
            for speaker in sorted(speakers):
                stats = speaker_stats[speaker]
                audio_duration = transcribe_result.get('audio_duration', 0)
                duration_percentage = (stats["duration"] / audio_duration) * 100 if audio_duration > 0 else 0
                logger.info(f"  {speaker}: {stats['segments']}段, {stats['duration']:.2f}秒 ({duration_percentage:.1f}%), {stats['words']}词")

        # 写入说话人分离数据文件
        with open(diarization_data_file, "w", encoding="utf-8") as f:
            json.dump(diarization_data_content, f, ensure_ascii=False, indent=2)

        logger.info(f"[{stage_name}] 说话人分离数据文件生成完成: {diarization_data_file}")

        # 构建输出数据 - Redis优化版本：精简segments数据，仅存储文件路径，消除重复字段
        output_data = {
            # 优化：将3组segments数据替换为文件路径，大幅减少Redis内存占用
            "segments_file": transcribe_data_file,           # 替代 "original_segments": transcribe_result['segments']
            "diarization_file": diarization_data_file,      # 替代 "speaker_enhanced_segments" 和 "diarization_segments"
            "audio_path": transcribe_result.get('audio_path', audio_path),
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "diarization_enabled": diarization_enabled,
            # 精简：统一统计信息到statistics对象中，消除重复字段
            "statistics": diarization_data_content["statistics"],

            # 兼容性：保留segments计数用于快速统计
            "original_segments_count": len(transcribe_result['segments']),
            "enhanced_segments_count": len(speaker_enhanced_segments) if speaker_enhanced_segments else 0,
            "diarization_segments_count": len(diarization_segments) if diarization_segments else 0
        }

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 说话人分离任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(bind=True, name='whisperx.generate_subtitle_files')
def generate_subtitle_files(self, context: dict) -> dict:
    """
    WhisperX 独立字幕文件生成任务节点

    此任务专门负责将转录结果（和可选的说话人分离结果）转换为各种格式的字幕文件。
    支持多种输入模式和输出格式，是WhisperX功能拆分的第三步。

    输入模式：
    - 仅转录结果（来自 whisperx.transcribe_audio）
    - 转录结果 + 说话人分离结果（来自 whisperx.diarize_speakers）

    输出格式：
    - 基础SRT字幕文件
    - 带说话人信息的SRT字幕文件（如果可用）
    - JSON格式字幕文件（如果可用）
    - 词级时间戳JSON文件（如果可用）
    """
    import json

    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 获取转录结果（必需）
        transcribe_stage = workflow_context.stages.get('whisperx.transcribe_audio')
        if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
            error_msg = "无法获取转录结果：请确保 whisperx.transcribe_audio 任务已成功完成"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 获取说话人分离结果（可选）
        diarize_stage = workflow_context.stages.get('whisperx.diarize_speakers')
        has_speaker_info = False

        transcribe_output = transcribe_stage.output
        if not transcribe_output or not isinstance(transcribe_output, dict):
            error_msg = "转录结果数据格式错误"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # Redis优化：使用统一的数据获取接口，支持新旧格式
        segments = get_segments_data(transcribe_output, 'segments')
        audio_path = transcribe_output.get('audio_path')
        audio_duration = transcribe_output.get('audio_duration', 0)
        language = transcribe_output.get('language', 'unknown')
        enable_word_timestamps = transcribe_output.get('enable_word_timestamps', True)

        if not segments or not audio_path:
            error_msg = "转录结果中缺少必要的数据（segments 或 audio_path）"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 记录数据来源
        if 'segments_file' in transcribe_output:
            logger.info(f"[{stage_name}] 从优化文件加载segments: {transcribe_output['segments_file']}")
        else:
            logger.info(f"[{stage_name}] 从Redis内存加载segments (旧格式)")

        # 检查是否有说话人分离结果
        speaker_enhanced_segments = None
        detected_speakers = []
        speaker_statistics = {}

        # Redis优化：使用统一的说话人数据获取接口
        if diarize_stage and diarize_stage.status in ['SUCCESS', 'COMPLETED']:
            diarize_output = diarize_stage.output
            if diarize_output and isinstance(diarize_output, dict):
                speaker_data = get_speaker_data(diarize_output)
                speaker_enhanced_segments = speaker_data.get('speaker_enhanced_segments')
                detected_speakers = speaker_data.get('detected_speakers', [])
                speaker_statistics = speaker_data.get('speaker_statistics', {})
                has_speaker_info = bool(speaker_enhanced_segments)

                # 记录数据来源
                if 'diarization_file' in diarize_output:
                    logger.info(f"[{stage_name}] 从优化文件加载说话人数据: {diarize_output['diarization_file']}")
                else:
                    logger.info(f"[{stage_name}] 从Redis内存加载说话人数据 (旧格式)")

        logger.info(f"[{stage_name}] ========== 输入数据验证 ==========")
        logger.info(f"[{stage_name}] 转录片段数: {len(segments)}")
        logger.info(f"[{stage_name}] 音频文件: {audio_path}")
        logger.info(f"[{stage_name}] 音频时长: {audio_duration:.2f}秒")
        logger.info(f"[{stage_name}] 语言: {language}")
        logger.info(f"[{stage_name}] 词级时间戳: {'启用' if enable_word_timestamps else '禁用'}")
        logger.info(f"[{stage_name}] 说话人信息: {'可用' if has_speaker_info else '不可用'}")
        if has_speaker_info:
            logger.info(f"[{stage_name}] 检测到说话人: {detected_speakers}")
        logger.info(f"[{stage_name}] =================================")

        # 加载WhisperX配置
        whisperx_config = CONFIG.get('whisperx_service', {})
        show_speaker_labels = whisperx_config.get('show_speaker_labels', True)

        logger.info(f"[{stage_name}] 开始字幕文件生成流程")

        # 创建字幕目录
        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)

        # 获取基础文件名（不含扩展名）
        base_filename = os.path.splitext(os.path.basename(audio_path))[0]

        # 生成基础SRT字幕文件（始终生成）
        subtitle_filename = f"{base_filename}.srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        # 生成基础SRT文件
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

        logger.info(f"[{stage_name}] 基础SRT字幕生成完成: {subtitle_path} (共{len(segments)}条字幕)")

        # 初始化输出数据
        output_data = {
            "subtitle_path": subtitle_path,
            "subtitle_files": {
                "basic": subtitle_path
            }
        }

        # 可选：生成带说话人信息的字幕文件
        speaker_srt_path = None
        speaker_json_path = None

        if has_speaker_info and speaker_enhanced_segments and show_speaker_labels:
            try:
                # 生成带说话人信息的SRT字幕文件
                speaker_srt_filename = f"{base_filename}_with_speakers.srt"
                speaker_srt_path = os.path.join(subtitles_dir, speaker_srt_filename)

                with open(speaker_srt_path, "w", encoding="utf-8") as f:
                    for i, segment in enumerate(speaker_enhanced_segments):
                        segment_start = segment["start"]
                        segment_end = segment["end"]
                        text = segment["text"].strip()
                        speaker = segment.get("speaker", "UNKNOWN")
                        confidence = segment.get("speaker_confidence", 0.0)

                        # 格式化为SRT时间格式
                        start_str = f"{int(segment_start//3600):02d}:{int((segment_start%3600)//60):02d}:{int(segment_start%60):02d},{int((segment_start%1)*1000):03d}"
                        end_str = f"{int(segment_end//3600):02d}:{int((segment_end%3600)//60):02d}:{int(segment_end%60):02d},{int((segment_end%1)*1000):03d}"

                        f.write(f"{i+1}\n")
                        f.write(f"{start_str} --> {end_str}\n")
                        f.write(f"[{speaker}] {text}\n\n")

                logger.info(f"[{stage_name}] 带说话人信息的SRT字幕生成完成: {speaker_srt_path} (共{len(speaker_enhanced_segments)}条字幕)")

                # 生成带说话人信息的JSON文件
                speaker_json_filename = f"{base_filename}_with_speakers.json"
                speaker_json_path = os.path.join(subtitles_dir, speaker_json_filename)

                # 构建带说话人信息的JSON数据
                speaker_json_data = {
                    "metadata": {
                        "audio_file": os.path.basename(audio_path),
                        "total_duration": audio_duration,
                        "language": language,
                        "word_timestamps_enabled": enable_word_timestamps,
                        "speakers": detected_speakers,
                        "total_segments": len(speaker_enhanced_segments),
                        "subtitle_method": "gpu-lock-v3-split",
                        "created_at": time.time()
                    },
                    "segments": []
                }

                for i, segment in enumerate(speaker_enhanced_segments):
                    segment_data = {
                        "id": i + 1,
                        "start": segment["start"],
                        "end": segment["end"],
                        "duration": segment["end"] - segment["start"],
                        "text": segment["text"].strip(),
                        "speaker": segment.get("speaker", "UNKNOWN"),
                        "speaker_confidence": segment.get("speaker_confidence", 0.0)
                    }

                    # 如果有词级时间戳，添加到JSON中
                    if "words" in segment and segment["words"]:
                        segment_data["words"] = segment["words"]

                    speaker_json_data["segments"].append(segment_data)

                # 写入JSON文件
                with open(speaker_json_path, "w", encoding="utf-8") as f:
                    json.dump(speaker_json_data, f, ensure_ascii=False, indent=2)

                logger.info(f"[{stage_name}] 带说话人信息的JSON文件生成完成: {speaker_json_path}")

                # 添加到输出数据
                output_data["speaker_srt_path"] = speaker_srt_path
                output_data["speaker_json_path"] = speaker_json_path
                output_data["subtitle_files"]["with_speakers"] = speaker_srt_path
                output_data["subtitle_files"]["speaker_json"] = speaker_json_path

                # 显示说话人统计信息
                logger.info(f"[{stage_name}] 说话人统计信息:")
                for speaker in sorted(speaker_statistics.keys()):
                    stats = speaker_statistics[speaker]
                    duration_percentage = (stats["duration"] / audio_duration) * 100 if audio_duration > 0 else 0
                    logger.info(f"  {speaker}: {stats['segments']}段, {stats['duration']:.2f}秒 ({duration_percentage:.1f}%), {stats.get('words', 0)}词")

            except Exception as e:
                logger.warning(f"[{stage_name}] 生成带说话人信息的字幕文件失败: {e}")

        # 可选：生成词级时间戳JSON文件
        word_timestamps_json_path = None

        if enable_word_timestamps and segments:
            try:
                # 导入JSON生成函数
                from app.model_manager import segments_to_word_timestamp_json

                # 生成JSON字幕文件
                word_timestamps_filename = f"{base_filename}_word_timestamps.json"
                word_timestamps_json_path = os.path.join(subtitles_dir, word_timestamps_filename)

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
                    logger.warning(f"   ⚠️  词级时间戳质量可能不佳")
                else:
                    logger.info(f"   ✅ 检测到词级对齐（平均词长: {avg_word_length:.2f}）")

                # 生成词级时间戳JSON内容
                json_content = segments_to_word_timestamp_json(segments, include_segment_info=True)

                # 写入JSON文件
                with open(word_timestamps_json_path, "w", encoding="utf-8") as f:
                    f.write(json_content)

                logger.info(f"[{stage_name}] 词级时间戳JSON文件生成完成: {word_timestamps_json_path}")

                # 添加到输出数据
                output_data["word_timestamps_json_path"] = word_timestamps_json_path
                output_data["subtitle_files"]["word_timestamps"] = word_timestamps_json_path

            except Exception as e:
                logger.warning(f"[{stage_name}] 生成词级时间戳JSON文件失败: {e}")

        # 生成字幕元数据
        metadata = {
            "total_segments": len(segments),
            "total_speaker_segments": len(speaker_enhanced_segments) if speaker_enhanced_segments else 0,
            "detected_speakers": detected_speakers if has_speaker_info else [],
            "audio_duration": audio_duration,
            "language": language,
            "has_speaker_info": has_speaker_info,
            "has_word_timestamps": enable_word_timestamps,
            "generated_files": list(output_data["subtitle_files"].values()),
            "subtitle_method": "gpu-lock-v3-split",
            "created_at": time.time()
        }

        output_data["metadata"] = metadata

        # 最终统计信息
        logger.info(f"[{stage_name}] ========== 字幕生成统计 ==========")
        logger.info(f"[{stage_name}] 基础字幕片段: {len(segments)}")
        if has_speaker_info:
            logger.info(f"[{stage_name}] 说话人字幕片段: {len(speaker_enhanced_segments)}")
        logger.info(f"[{stage_name}] 生成文件数量: {len(output_data['subtitle_files'])}")
        logger.info(f"[{stage_name}] 说话人信息: {'包含' if has_speaker_info else '不包含'}")
        logger.info(f"[{stage_name}] 词级时间戳: {'包含' if enable_word_timestamps else '不包含'}")
        logger.info(f"[{stage_name}] =================================")

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 字幕文件生成任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()