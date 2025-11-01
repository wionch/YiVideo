# services/workers/faster_whisper_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
faster-whisper Service 的 Celery 任务定义。
优化版本：直接使用faster-whisper原生API的词级时间戳功能，参考v3脚本实现。
修复版本：解决之前实现中词级时间戳丢失问题，使用faster-whisper原生API。
GPU锁版本：使用GPU锁装饰器保护GPU资源，实现细粒度资源管理。
"""

import os
import time
import json

from services.common.logger import get_logger
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext

# 导入 Celery 应用配置
from services.workers.faster_whisper_service.app.celery_app import celery_app

# 导入新的通用配置加载器
from services.common.config_loader import CONFIG

# 导入GPU锁装饰器
from services.common.locks import gpu_lock
from services.common.parameter_resolver import resolve_parameters

# 导入字幕合并模块
from services.workers.faster_whisper_service.app.subtitle_merger import (
    SubtitleMerger,
    WordLevelMerger,
    create_subtitle_merger,
    create_word_level_merger,
    validate_speaker_segments
)
# 导入字幕校正模块
from services.common.subtitle.subtitle_correction import SubtitleCorrector, CorrectionResult
from services.common.subtitle.subtitle_parser import SubtitleEntry, SRTParser

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


def segments_to_word_timestamp_json(segments: list, include_segment_info: bool = True) -> str:
    """
    将faster-whisper的segments转换为包含词级时间戳的JSON格式

    Args:
        segments: faster-whisper转录结果的segments列表
        include_segment_info: 是否包含句子级别信息

    Returns:
        JSON格式的字符串，包含详细的词级时间戳信息
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

        # 如果包含句子级别信息，添加SRT格式时间
        if include_segment_info:
            segment_data["srt_time"] = f"{int(segment['start'] // 3600):02}:{int((segment['start'] % 3600) // 60):02}:{int(segment['start'] % 60):02},{int((segment['start'] * 1000) % 1000):03} --> {int(segment['end'] // 3600):02}:{int((segment['end'] % 3600) // 60):02}:{int(segment['end'] % 60):02},{int((segment['end'] * 1000) % 1000):03}"

        # 检查是否有词级时间戳数据
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
            # 如果没有词级时间戳，将整个segment作为一个词处理
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


def _transcribe_audio_with_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
    """
    使用faster-whisper原生API进行ASR，生成转录结果。
    
    根据配置条件性使用GPU锁：
    - CUDA模式：使用GPU锁
    - CPU模式：跳过GPU锁
    
    Args:
        audio_path: 音频文件路径
        service_config: 服务配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    # 检查是否需要使用GPU锁
    need_gpu_lock = _should_use_gpu_lock_for_transcription(service_config)
    
    if need_gpu_lock:
        # 需要GPU锁，调用带锁版本
        return _transcribe_audio_with_gpu_lock(audio_path, service_config, stage_name)
    else:
        # 不需要GPU锁，直接执行
        logger.info(f"[{stage_name}] 语音转录使用非GPU模式，跳过GPU锁")
        return _transcribe_audio_without_lock(audio_path, service_config, stage_name)


@gpu_lock()  # 仅在CUDA模式下获取GPU锁
def _transcribe_audio_with_gpu_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
    """
    带GPU锁的语音转录功能（CUDA模式）
    
    Args:
        audio_path: 音频文件路径
        service_config: 服务配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    logger.info(f"[{stage_name}] 语音转录使用GPU锁模式（CUDA）")
    # 直接执行转录逻辑，GPU锁由装饰器管理
    return _execute_transcription(audio_path, service_config, stage_name)


def _transcribe_audio_without_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
    """
    不带GPU锁的语音转录功能（CPU模式）
    
    Args:
        audio_path: 音频文件路径
        service_config: 服务配置
        stage_name: 阶段名称（用于日志）
    
    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    logger.info(f"[{stage_name}] 语音转录使用非GPU模式")
    # 直接执行转录逻辑，无需GPU锁
    return _execute_transcription(audio_path, service_config, stage_name)


def _execute_transcription(audio_path: str, service_config: dict, stage_name: str) -> dict:
    """
    执行语音转录 - 使用 subprocess 隔离模式

    改造说明:
    - 原: 直接在 Celery worker 进程中加载 WhisperModel
    - 新: 通过 subprocess 调用独立推理脚本
    - 原因: 解决 Celery prefork pool 与 CUDA 初始化冲突

    Args:
        audio_path: 音频文件路径
        service_config: 服务配置
        stage_name: 阶段名称（用于日志）

    Returns:
        dict: 转录结果，包含segments、audio_path、audio_duration等信息
    """
    import subprocess
    import sys
    import json
    from pathlib import Path

    logger.info(f"[{stage_name}] 开始处理音频 (subprocess模式): {audio_path}")
    
    # 验证音频文件是否存在
    if not os.path.exists(audio_path):
        error_msg = f"音频文件不存在: {audio_path}"
        logger.error(f"[{stage_name}] {error_msg}")
        raise ValueError(error_msg)

    # ===== 参数提取 =====
    model_name = service_config.get('model_name', 'large-v3')
    device = service_config.get('device', 'cuda')
    compute_type = service_config.get('compute_type', 'float16')
    language = service_config.get('language', None)
    beam_size = service_config.get('beam_size', 3)
    best_of = service_config.get('best_of', 3)
    temperature = service_config.get('temperature', [0.0, 0.2, 0.4, 0.6])
    word_timestamps = service_config.get('word_timestamps', True)
    vad_filter = service_config.get('vad_filter', False)
    vad_parameters = service_config.get('vad_parameters', None)

    # ===== 准备输出路径 =====
    # 使用临时目录存储推理结果
    import tempfile
    temp_dir = tempfile.gettempdir()
    output_file = Path(temp_dir) / f"faster_whisper_result_{int(time.time() * 1000)}.json"

    logger.info(f"[{stage_name}] 准备通过 subprocess 执行转录")
    logger.info(f"[{stage_name}] 音频文件: {audio_path}")
    logger.info(f"[{stage_name}] 结果文件: {output_file}")

    # ===== 准备推理脚本路径 =====
    current_dir = Path(__file__).parent
    infer_script = current_dir / "faster_whisper_infer.py"

    if not infer_script.exists():
        raise FileNotFoundError(f"推理脚本不存在: {infer_script}")

    logger.info(f"[{stage_name}] 推理脚本: {infer_script}")

    # ===== 构建命令 =====
    cmd = [
        sys.executable,  # 使用当前 Python 解释器
        str(infer_script),
        "--audio_path", str(audio_path),
        "--output_file", str(output_file),
        "--model_name", model_name,
        "--device", device,
        "--compute_type", compute_type,
        "--beam_size", str(beam_size),
        "--best_of", str(best_of),
        "--temperature", ','.join(map(str, temperature)),
    ]

    # 可选参数
    if language:
        cmd.extend(["--language", language])

    if word_timestamps:
        cmd.append("--word_timestamps")

    if vad_filter:
        cmd.append("--vad_filter")

    if vad_parameters:
        cmd.extend(["--vad_parameters", json.dumps(vad_parameters)])

    # 日志命令
    cmd_str = ' '.join(cmd)
    logger.info(f"[{stage_name}] 执行命令: {cmd_str}")

    # ===== 执行 subprocess =====
    logger.info(f"[{stage_name}] 开始执行 subprocess 推理...")
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 分钟超时
            cwd=str(current_dir),
            env=os.environ.copy()  # 继承环境变量（包括 CUDA_VISIBLE_DEVICES）
        )

        execution_time = time.time() - start_time
        logger.info(f"[{stage_name}] subprocess 执行完成，耗时: {execution_time:.3f}s")

        # ===== 检查执行结果 =====
        if result.returncode != 0:
            error_msg = f"subprocess 执行失败，返回码: {result.returncode}"
            logger.error(f"[{stage_name}] {error_msg}")
            logger.error(f"[{stage_name}] stdout: {result.stdout}")
            logger.error(f"[{stage_name}] stderr: {result.stderr}")
            raise RuntimeError(f"{error_msg}\nstderr: {result.stderr}")

        logger.info(f"[{stage_name}] subprocess 执行成功")

        # 记录 stderr 输出（推理脚本的日志）
        if result.stderr:
            logger.debug(f"[{stage_name}] subprocess stderr 输出:")
            for line in result.stderr.strip().split('\n')[:20]:  # 只显示前20行
                logger.debug(f"  | {line}")

    except subprocess.TimeoutExpired as e:
        error_msg = f"subprocess 执行超时 (30分钟)"
        logger.error(f"[{stage_name}] {error_msg}")
        raise RuntimeError(error_msg) from e

    except Exception as e:
        error_msg = f"subprocess 执行异常: {str(e)}"
        logger.error(f"[{stage_name}] {error_msg}")
        raise RuntimeError(error_msg) from e

    # ===== 读取结果文件 =====
    if not output_file.exists():
        raise RuntimeError(f"推理结果文件不存在: {output_file}")

    logger.info(f"[{stage_name}] 读取推理结果: {output_file}")

    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[{stage_name}] 结果文件 JSON 解析失败: {e}")
        raise RuntimeError(f"结果文件 JSON 解析失败: {e}") from e

    # ===== 验证结果 =====
    if not result_data.get('success', False):
        error_info = result_data.get('error', {})
        error_msg = error_info.get('message', '未知错误')
        error_type = error_info.get('type', 'Unknown')

        logger.error(f"[{stage_name}] 推理失败: {error_type}: {error_msg}")
        raise RuntimeError(f"推理失败: {error_type}: {error_msg}")

    # ===== 提取结果数据 =====
    segments_list = result_data.get('segments', [])
    info_dict = result_data.get('info', {})
    statistics = result_data.get('statistics', {})

    logger.info(f"[{stage_name}] ========== 转录结果统计 ==========")
    logger.info(f"[{stage_name}] 转录片段数: {statistics.get('total_segments', len(segments_list))}")
    logger.info(f"[{stage_name}] 音频时长: {statistics.get('audio_duration', 0):.2f}s")
    logger.info(f"[{stage_name}] 转录耗时: {statistics.get('transcribe_duration', 0):.2f}s")
    logger.info(f"[{stage_name}] 检测语言: {statistics.get('language', 'unknown')}")
    logger.info(f"[{stage_name}] =====================================")

    # ===== 清理临时文件 =====
    try:
        output_file.unlink()
        logger.debug(f"[{stage_name}] 已清理临时结果文件: {output_file}")
    except Exception as e:
        logger.warning(f"[{stage_name}] 清理临时文件失败: {e}")

    # ===== 构建返回结果（保持与原格式兼容）=====
    result = {
        "segments": segments_list,
        "audio_path": audio_path,
        "audio_duration": info_dict.get('duration', 0),
        "language": info_dict.get('language'),
        "transcribe_duration": statistics.get('transcribe_duration', 0),
        "model_name": model_name,
        "device": device,
        "enable_word_timestamps": word_timestamps
    }

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


def _should_use_gpu_lock_for_transcription(service_config: dict) -> bool:
    """
    判断语音转录是否应该使用GPU锁
    
    根据需求：
    - 需要上gpu锁任务: cuda模式下的: `语音转录功能`
    - 不需要上gpu锁的任务: cpu模式下的`语音转录功能`
    
    Args:
        service_config: 服务配置
    
    Returns:
        bool: True表示应该使用GPU锁
    """
    try:
        # 获取设备配置
        device = service_config.get('device', 'cpu')
        
        # 检查CUDA可用性
        if device == 'cuda':
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("[faster-whisper] CUDA模式语音转录，需要GPU锁")
                    return True
                else:
                    logger.info("[faster-whisper] CUDA不可用，语音转录使用CPU模式，跳过GPU锁")
                    return False
            except ImportError:
                logger.warning("[faster-whisper] PyTorch未安装，语音转录使用CPU模式，跳过GPU锁")
                return False
        else:
            logger.info(f"[faster-whisper] {device}模式语音转录，跳过GPU锁")
            return False
            
    except Exception as e:
        logger.warning(f"[faster-whisper] 检查语音转录GPU锁需求时出错: {e}")
        # 出错时默认不使用GPU锁，避免阻塞
        return False

# ============================================================================
# faster-whisper 功能拆分 - 独立任务节点
# ============================================================================

@celery_app.task(bind=True, name='faster_whisper.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    """
    faster-whisper 独立转录任务节点

    此任务专门负责音频文件的语音转录功能。
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
        # --- Parameter Resolution ---
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
                # 将解析后的参数更新回 input_params 的顶层
                workflow_context.input_params.update(resolved_params)
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e

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

        # 加载服务配置
        service_config = CONFIG.get('faster_whisper_service', {})
        enable_word_timestamps = service_config.get('enable_word_timestamps', True)

        logger.info(f"[{stage_name}] 开始语音转录流程")
        logger.info(f"[{stage_name}] 词级时间戳: {'启用' if enable_word_timestamps else '禁用'}")

        # 执行语音转录
        logger.info(f"[{stage_name}] 执行语音转录...")
        transcribe_result = _transcribe_audio_with_lock(audio_path, service_config, stage_name)

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


@celery_app.task(bind=True, name='faster_whisper.generate_subtitle_files')
def generate_subtitle_files(self, context: dict) -> dict:
    """
    faster-whisper 独立字幕文件生成任务节点

    此任务专门负责将转录结果（和可选的说话人分离结果）转换为各种格式的字幕文件。
    支持多种输入模式和输出格式。

    输入模式：
    - 仅转录结果（来自 faster_whisper.transcribe_audio）
    - 转录结果 + 说话人分离结果（来自 pyannote_audio.diarize_speakers）

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
        # --- Parameter Resolution ---
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
                # 将解析后的参数更新回 input_params 的顶层
                workflow_context.input_params.update(resolved_params)
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e

        # 获取转录结果（必需）
        transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
            error_msg = "无法获取转录结果：请确保 faster_whisper.transcribe_audio 任务已成功完成"
            logger.error(f"[{stage_name}] {error_msg}")
            raise ValueError(error_msg)

        # 获取说话人分离结果（可选）
        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
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

        # 加载服务配置（提前定义以便在说话人匹配中使用）
        service_config = CONFIG.get('faster_whisper_service', {})

        # 检查是否有说话人分离结果
        speaker_segments = None
        speaker_enhanced_segments = None
        detected_speakers = []
        speaker_statistics = {}

        # Redis优化：使用统一的说话人数据获取接口
        if diarize_stage and diarize_stage.status in ['SUCCESS', 'COMPLETED']:
            diarize_output = diarize_stage.output
            if diarize_output and isinstance(diarize_output, dict):
                speaker_data = get_speaker_data(diarize_output)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')  # 这里是纯说话人信息
                detected_speakers = speaker_data.get('detected_speakers', [])
                speaker_statistics = speaker_data.get('speaker_statistics', {})

                # 如果有说话人信息和转录片段，进行合并
                if speaker_segments and segments and enable_word_timestamps:
                    try:
                        # 使用新的词级合并器（subtitle_merger模块）
                        logger.info(f"[{stage_name}] 使用词级时间戳进行精确说话人匹配")

                        # 获取合并配置
                        service_config = CONFIG.get('faster_whisper_service', {})
                        merge_config = service_config.get('subtitle_merge', {})

                        # 创建词级合并器并执行合并
                        merger = create_word_level_merger(speaker_segments, merge_config)
                        speaker_enhanced_segments = merger.merge(segments)
                        has_speaker_info = True

                        logger.info(f"[{stage_name}] 成功合并 {len(segments)} 个转录片段与 {len(speaker_segments)} 个说话人片段")
                        logger.info(f"[{stage_name}] 生成了 {len(speaker_enhanced_segments)} 个带说话人信息的字幕片段")

                    except Exception as e:
                        logger.warning(f"[{stage_name}] 说话人信息合并失败: {e}")
                        has_speaker_info = False
                        speaker_enhanced_segments = None
                else:
                    has_speaker_info = bool(speaker_segments)
                    if not has_speaker_info:
                        logger.warning(f"[{stage_name}] 缺少必要数据用于说话人信息合并: speaker_segments={len(speaker_segments) if speaker_segments else 0}, segments={len(segments)}, word_timestamps={enable_word_timestamps}")

                # 记录数据来源
                if 'diarization_file' in diarize_output:
                    logger.info(f"[{stage_name}] 从优化文件加载说话人数据: {diarize_output['diarization_file']}")
                else:
                    logger.info(f"[{stage_name}] 从Redis内存加载说话人数据")

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

        # 获取配置参数
        show_speaker_labels = service_config.get('show_speaker_labels', True)

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
                # 本地函数，无需导入

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


# ============================================================================
# 字幕合并任务 - 新增功能
# ============================================================================

@celery_app.task(name='faster_whisper.merge_speaker_segments', bind=True)
def merge_speaker_segments(self, context: dict) -> dict:
    """
    合并转录字幕与说话人时间段(片段级)

    这是一个独立的工作流节点,用于将转录结果与说话人分离结果进行合并。
    使用片段中心时间匹配算法,适用于没有词级时间戳的场景。

    输入要求:
    - context['stages']['transcribe']['output']['segments']: 转录片段列表
    - context['stages']['diarize_speakers']['output']['speaker_segments']: 说话人时间段列表

    输出:
    - merged_segments: 包含说话人信息的字幕片段列表
    - metadata: 合并过程的统计信息

    Args:
        context: 工作流上下文字典

    Returns:
        dict: 更新后的工作流上下文
    """
    workflow_context = WorkflowContext(**context)
    stage_name = workflow_context.current_stage

    logger.info(f"[{stage_name}] ========== 开始片段级字幕合并任务 ==========")

    try:
        # 标记任务开始
        start_time = time.time()
        workflow_context.stages[stage_name].status = 'IN_PROGRESS'
        workflow_context.stages[stage_name].metadata = {'task_type': 'subtitle_merge_segment_level'}
        state_manager.update_workflow_state(workflow_context)

        # 1. 获取输入数据
        logger.info(f"[{stage_name}] 正在获取输入数据...")

        # 获取转录结果
        transcribe_stage = workflow_context.get_stage_by_type('transcribe')
        if not transcribe_stage or not transcribe_stage.output:
            raise ValueError("未找到转录结果阶段或输出数据")

        transcript_segments = transcribe_stage.output.get('segments', [])
        if not transcript_segments:
            raise ValueError("转录结果为空")

        logger.info(f"[{stage_name}] 获取到转录片段: {len(transcript_segments)} 个")

        # 获取说话人分离结果
        diarize_stage = workflow_context.get_stage_by_type('diarize_speakers')
        if not diarize_stage or not diarize_stage.output:
            raise ValueError("未找到说话人分离结果阶段或输出数据")

        speaker_segments = diarize_stage.output.get('speaker_segments', [])
        if not speaker_segments:
            raise ValueError("说话人分离结果为空")

        logger.info(f"[{stage_name}] 获取到说话人时间段: {len(speaker_segments)} 个")

        # 2. 验证说话人时间段数据
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")

        # 3. 从配置获取合并参数
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})

        logger.info(f"[{stage_name}] 合并配置: {merge_config}")

        # 4. 创建合并器并执行合并
        logger.info(f"[{stage_name}] 开始执行片段级合并...")
        merger = create_subtitle_merger(merge_config)
        merged_segments = merger.merge(transcript_segments, speaker_segments)

        logger.info(f"[{stage_name}] 合并完成,生成 {len(merged_segments)} 个片段")

        # 5. 准备输出数据
        output_data = {
            'merged_segments': merged_segments,
            'metadata': {
                'merge_method': 'segment_level',
                'input_transcript_count': len(transcript_segments),
                'input_speaker_count': len(speaker_segments),
                'output_count': len(merged_segments),
                'speaker_count': len(set(seg.get('speaker', 'UNKNOWN') for seg in merged_segments))
            }
        }

        # 6. 统计信息
        logger.info(f"[{stage_name}] ========== 合并统计 ==========")
        logger.info(f"[{stage_name}] 输入转录片段: {len(transcript_segments)}")
        logger.info(f"[{stage_name}] 输入说话人时间段: {len(speaker_segments)}")
        logger.info(f"[{stage_name}] 输出合并片段: {len(merged_segments)}")
        logger.info(f"[{stage_name}] 检测到说话人数: {output_data['metadata']['speaker_count']}")
        logger.info(f"[{stage_name}] ===============================")

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 片段级字幕合并任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(name='faster_whisper.merge_with_word_timestamps', bind=True)
def merge_with_word_timestamps(self, context: dict) -> dict:
    """
    使用词级时间戳进行精确字幕合并

    这是一个独立的工作流节点,用于利用词级时间戳信息将转录结果与说话人分离结果进行精确合并。
    每个词都会被分配给最匹配的说话人,然后按说话人分组,准确度比片段级合并提升30-50%。

    输入要求:
    - context['stages']['transcribe']['output']['segments']: 转录片段列表(必须包含words字段)
    - context['stages']['diarize_speakers']['output']['speaker_segments']: 说话人时间段列表

    输出:
    - merged_segments: 包含说话人信息和词级时间戳的字幕片段列表
    - metadata: 合并过程的统计信息

    Args:
        context: 工作流上下文字典

    Returns:
        dict: 更新后的工作流上下文
    """
    workflow_context = WorkflowContext(**context)
    stage_name = workflow_context.current_stage

    logger.info(f"[{stage_name}] ========== 开始词级精确字幕合并任务 ==========")

    try:
        # 标记任务开始
        start_time = time.time()
        workflow_context.stages[stage_name].status = 'IN_PROGRESS'
        workflow_context.stages[stage_name].metadata = {'task_type': 'subtitle_merge_word_level'}
        state_manager.update_workflow_state(workflow_context)

        # 1. 获取输入数据
        logger.info(f"[{stage_name}] 正在获取输入数据...")

        # 获取转录结果
        transcribe_stage = workflow_context.get_stage_by_type('transcribe')
        if not transcribe_stage or not transcribe_stage.output:
            raise ValueError("未找到转录结果阶段或输出数据")

        transcript_segments = transcribe_stage.output.get('segments', [])
        if not transcript_segments:
            raise ValueError("转录结果为空")

        # 验证是否包含词级时间戳
        has_word_timestamps = False
        for seg in transcript_segments:
            if 'words' in seg and seg['words']:
                has_word_timestamps = True
                break

        if not has_word_timestamps:
            raise ValueError("转录结果不包含词级时间戳,无法使用词级合并。请使用 merge_speaker_segments 任务或在转录时启用词级时间戳")

        logger.info(f"[{stage_name}] 获取到转录片段: {len(transcript_segments)} 个 (包含词级时间戳)")

        # 获取说话人分离结果
        diarize_stage = workflow_context.get_stage_by_type('diarize_speakers')
        if not diarize_stage or not diarize_stage.output:
            raise ValueError("未找到说话人分离结果阶段或输出数据")

        speaker_segments = diarize_stage.output.get('speaker_segments', [])
        if not speaker_segments:
            raise ValueError("说话人分离结果为空")

        logger.info(f"[{stage_name}] 获取到说话人时间段: {len(speaker_segments)} 个")

        # 2. 验证说话人时间段数据
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")

        # 3. 从配置获取合并参数
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})

        logger.info(f"[{stage_name}] 合并配置: {merge_config}")

        # 4. 创建词级合并器并执行合并
        logger.info(f"[{stage_name}] 开始执行词级精确合并...")
        merger = create_word_level_merger(speaker_segments, merge_config)
        merged_segments = merger.merge(transcript_segments)

        logger.info(f"[{stage_name}] 合并完成,生成 {len(merged_segments)} 个片段")

        # 5. 统计词级匹配信息
        total_words = 0
        matched_words = 0
        for seg in merged_segments:
            if 'words' in seg:
                total_words += len(seg['words'])
                matched_words += sum(1 for w in seg['words'] if 'speaker' in w)

        match_rate = (matched_words / total_words * 100) if total_words > 0 else 0

        # 6. 准备输出数据
        output_data = {
            'merged_segments': merged_segments,
            'metadata': {
                'merge_method': 'word_level',
                'input_transcript_count': len(transcript_segments),
                'input_speaker_count': len(speaker_segments),
                'output_count': len(merged_segments),
                'total_words': total_words,
                'matched_words': matched_words,
                'match_rate': round(match_rate, 2),
                'speaker_count': len(set(seg.get('speaker', 'UNKNOWN') for seg in merged_segments))
            }
        }

        # 7. 统计信息
        logger.info(f"[{stage_name}] ========== 合并统计 ==========")
        logger.info(f"[{stage_name}] 输入转录片段: {len(transcript_segments)}")
        logger.info(f"[{stage_name}] 输入说话人时间段: {len(speaker_segments)}")
        logger.info(f"[{stage_name}] 输出合并片段: {len(merged_segments)}")
        logger.info(f"[{stage_name}] 总词数: {total_words}")
        logger.info(f"[{stage_name}] 匹配词数: {matched_words}")
        logger.info(f"[{stage_name}] 匹配率: {match_rate:.2f}%")
        logger.info(f"[{stage_name}] 检测到说话人数: {output_data['metadata']['speaker_count']}")
        logger.info(f"[{stage_name}] ===============================")

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 词级精确字幕合并任务完成")

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
# 字幕AI校正任务 - 新增功能
# ============================================================================

@celery_app.task(bind=True, name='faster_whisper.correct_subtitles')
def correct_subtitles(self, context: dict) -> dict:
    """
    字幕AI校正任务节点

    此任务负责对已生成的字幕文件进行AI校正、润色和优化。
    它会智能选择最佳的字幕文件作为输入，并根据工作流配置调用相应的AI服务。

    输入：
    - 来自 `generate_subtitle_files` 阶段的输出，包含字幕文件路径。

    输出：
    - 校正后的字幕文件路径及相关统计信息。
    """
    import asyncio

    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 1. 从工作流参数中获取校正配置
        # 检查 params 中是否有 subtitle_correction 配置
        correction_params = workflow_context.input_params.get('params', {}).get('subtitle_correction', {})
        is_enabled = correction_params.get('enabled', False)
        provider = correction_params.get('provider', None) # 使用工作流指定的provider或配置文件的默认值

        if not is_enabled:
            logger.info(f"[{stage_name}] 字幕AI校正未在工作流配置中启用，跳过此阶段。")
            workflow_context.stages[stage_name].status = 'SKIPPED'
            workflow_context.stages[stage_name].output = {"message": "Correction skipped as per workflow configuration."}
            return workflow_context.model_dump()

        logger.info(f"[{stage_name}] ========== 开始字幕AI校正任务 ==========")
        logger.info(f"[{stage_name}] 使用的AI提供商: {provider or '默认'}")

        # 2. 获取并解析参数
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
        
        # 3. 获取待校正的字幕文件（新逻辑）
        subtitle_to_correct = None
        subtitle_source = ""

        # 优先级1：检查动态参数
        subtitle_path_param = resolved_params.get("subtitle_path")
        if subtitle_path_param and os.path.exists(subtitle_path_param):
            subtitle_to_correct = subtitle_path_param
            subtitle_source = "参数传入"
        
        # 优先级2：如果参数未提供，则回退到自动检测
        if not subtitle_to_correct:
            generate_stage = workflow_context.stages.get('faster_whisper.generate_subtitle_files')
            if generate_stage and generate_stage.output:
                # 优先使用带说话人的SRT
                subtitle_to_correct = generate_stage.output.get('speaker_srt_path')
                if subtitle_to_correct and os.path.exists(subtitle_to_correct):
                    subtitle_source = "自动检测 (带说话人SRT)"
                else:
                    # 其次使用基础SRT
                    subtitle_to_correct = generate_stage.output.get('subtitle_path')
                    if subtitle_to_correct and os.path.exists(subtitle_to_correct):
                        subtitle_source = "自动检测 (基础SRT)"

        # 最终验证
        if not subtitle_to_correct or not os.path.exists(subtitle_to_correct):
            raise FileNotFoundError("未找到可供校正的字幕文件。请检查工作流配置或确保前序任务已成功生成字幕文件。")

        logger.info(f"[{stage_name}] 选择的校正源: {subtitle_source}, 路径: {subtitle_to_correct}")

        # 4. 执行校正
        # SubtitleCorrector 的方法是 async 的，所以我们需要在同步的Celery任务中运行它
        corrector = SubtitleCorrector(provider=provider)
        
        # 定义输出路径
        corrected_filename = os.path.basename(subtitle_to_correct).replace('.srt', '_corrected_by_ai.srt')
        corrected_path = os.path.join(os.path.dirname(subtitle_to_correct), corrected_filename)

        logger.info(f"[{stage_name}] 开始调用AI进行校正，输出路径: {corrected_path}")
        
        # 在同步函数中运行异步代码
        correction_result = asyncio.run(
            corrector.correct_subtitle_file(
                subtitle_path=subtitle_to_correct,
                output_path=corrected_path
            )
        )

        # 4. 处理校正结果
        if not correction_result.success:
            raise RuntimeError(f"AI字幕校正失败: {correction_result.error_message}")

        logger.info(f"[{stage_name}] AI字幕校正成功，耗时: {correction_result.processing_time:.2f}秒")
        logger.info(f"[{stage_name}] 校正后的文件保存在: {correction_result.corrected_subtitle_path}")

        # 5. 准备输出数据
        output_data = {
            "corrected_subtitle_path": correction_result.corrected_subtitle_path,
            "original_subtitle_path": correction_result.original_subtitle_path,
            "provider_used": correction_result.provider_used,
            "statistics": correction_result.statistics,
            "message": "Subtitle correction completed successfully."
        }

        # 标记任务成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 字幕AI校正任务完成")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()

@celery_app.task(bind=True, name='faster_whisper.merge_for_tts')
def merge_for_tts(self, context: dict) -> dict:
    """
    为TTS参考音合并字幕片段的工作流节点。
    """
    import json
    from .tts_merger import TtsMerger

    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    start_time = time.time()

    try:
        # --- Parameter Resolution ---
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
                # 将解析后的参数更新回 input_params 的顶层
                workflow_context.input_params.update(resolved_params)
                # 更新 node_params 以便后续逻辑使用
                node_params = resolved_params
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        logger.info(f"[{stage_name}] 节点参数: {node_params}")

        # 2. 获取输入字幕文件路径（智能选择）
        subtitle_file_path = None
        source_description = ""

        # 优先级 1: 从节点参数中直接指定
        if node_params and node_params.get('subtitle_path'):
            subtitle_file_path = node_params['subtitle_path']
            source_description = f"参数指定路径 ({subtitle_file_path})"
            logger.info(f"[{stage_name}] 使用参数指定的字幕文件: {subtitle_file_path}")

        # 优先级 2: 从 generate_subtitle_files 阶段获取 speaker_json_path
        if not subtitle_file_path:
            generate_stage = workflow_context.stages.get('faster_whisper.generate_subtitle_files')
            if generate_stage and generate_stage.output and generate_stage.output.get('speaker_json_path'):
                subtitle_file_path = generate_stage.output['speaker_json_path']
                source_description = f"来自 'generate_subtitle_files' 的带说话人JSON ({subtitle_file_path})"
                logger.info(f"[{stage_name}] 使用来自 'generate_subtitle_files' 的带说话人JSON: {subtitle_file_path}")

        # 优先级 3: 从 transcribe_audio 阶段获取 segments_file
        if not subtitle_file_path:
            transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
            if transcribe_stage and transcribe_stage.output and transcribe_stage.output.get('segments_file'):
                subtitle_file_path = transcribe_stage.output['segments_file']
                source_description = f"来自 'transcribe_audio' 的转录数据文件 ({subtitle_file_path})"
                logger.info(f"[{stage_name}] 使用来自 'transcribe_audio' 的转录数据文件: {subtitle_file_path}")

        if not subtitle_file_path or not os.path.exists(subtitle_file_path):
            raise FileNotFoundError(f"未找到可供合并的字幕数据文件。搜索路径: {subtitle_file_path}")

        logger.info(f"[{stage_name}] 最终选择的字幕源: {source_description}")

        with open(subtitle_file_path, 'r', encoding='utf-8') as f:
            subtitle_data = json.load(f)
        
        # 兼容纯segments列表或包含segments的JSON对象
        if isinstance(subtitle_data, dict):
            segments = subtitle_data.get('segments', [])
        elif isinstance(subtitle_data, list):
            segments = subtitle_data
        else:
            segments = []

        if not segments:
            raise ValueError("字幕数据文件中不包含 'segments' 或为空。")

        # 3. 初始化并执行合并
        # TtsMerger 的配置仍然从节点参数中获取
        merger = TtsMerger(config=node_params)
        merged_segments = merger.merge_segments(segments)

        # 4. 准备输出
        base_filename = os.path.splitext(os.path.basename(subtitle_file_path))[0]
        # 确保输出文件名不会重复 "_merged_for_tts"
        if base_filename.endswith('_merged_for_tts'):
            base_filename = base_filename.rsplit('_merged_for_tts', 1)[0]
        if base_filename.endswith('_with_speakers'):
            base_filename = base_filename.rsplit('_with_speakers', 1)[0]
        
        output_filename = f"{base_filename}_merged_for_tts.json"
        output_file_path = os.path.join(os.path.dirname(subtitle_file_path), output_filename)
        
        output_json_data = {
            "metadata": {
                "source_file": subtitle_file_path,
                "source_description": source_description,
                "merge_config": node_params,
                "original_segment_count": len(segments),
                "merged_segment_count": len(merged_segments),
                "created_at": time.time()
            },
            "segments": merged_segments
        }

        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(output_json_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[{stage_name}] 合并后的TTS字幕JSON文件已生成: {output_file_path}")

        # 新增：生成SRT格式的字幕文件
        srt_output_filename = f"{base_filename}_merged_for_tts.srt"
        srt_output_file_path = os.path.join(os.path.dirname(subtitle_file_path), srt_output_filename)

        try:
            srt_entries = [
                SubtitleEntry(
                    index=i + 1,
                    start_time=seg['start'],
                    end_time=seg['end'],
                    text=f"[{seg.get('speaker')}] {seg['text']}" if 'speaker' in seg and seg.get('speaker') else seg['text']
                ) for i, seg in enumerate(merged_segments)
            ]
            
            parser = SRTParser()
            parser.write_file(srt_entries, srt_output_file_path)
            logger.info(f"[{stage_name}] 合并后的TTS字幕SRT文件已生成: {srt_output_file_path}")
        except Exception as e:
            logger.warning(f"[{stage_name}] 生成SRT文件失败: {e}")
            srt_output_file_path = None

        output_data = {
            "merged_tts_json_path": output_file_path,
            "merged_tts_srt_path": srt_output_file_path,
            "statistics": {
                "original_count": len(segments),
                "merged_count": len(merged_segments),
                "merged_items": len(segments) - len(merged_segments)
            }
        }
        
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