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
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

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

    # 执行GPU显存清理
    _cleanup_gpu_memory(stage_name, locals_to_delete=['model'])

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
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

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
    _cleanup_gpu_memory(stage_name, locals_to_delete=['diarizer'])

    return result


def _cleanup_gpu_memory(stage_name: str, locals_to_delete: list = None) -> None:
    """
    通用的GPU显存清理函数
    
    Args:
        stage_name: 阶段名称（用于日志）
        locals_to_delete: 需要删除的本地变量名列表
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

            # 注意：由于Python的限制，无法从外部函数内部删除调用者的本地变量
            # 这个参数保留用于文档目的，实际清理需要在使用_前手动删除变量
            if locals_to_delete:
                logger.debug(f"[{stage_name}] 注意：无法自动删除变量 {locals_to_delete}，请在调用前手动删除")

            # 激进的CUDA缓存清理
            for device_id in range(torch.cuda.device_count()):
                try:
                    with torch.cuda.device(device_id):
                        torch.cuda.empty_cache()
                        torch.cuda.ipc_collect()
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

            # 再次垃圾回收和缓存清理
            for _ in range(3):
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

        # 检查 ffmpeg.extract_audio 阶段的输出
        ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.status == 'SUCCESS':
            if hasattr(ffmpeg_stage.output, 'audio_path'):
                audio_path = ffmpeg_stage.output.audio_path
            elif isinstance(ffmpeg_stage.output, dict) and 'audio_path' in ffmpeg_stage.output:
                audio_path = ffmpeg_stage.output['audio_path']

        if not audio_path:
            raise ValueError("无法获取音频文件路径：请确保 ffmpeg.extract_audio 任务已成功完成")

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