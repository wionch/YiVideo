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
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service

logger = get_logger('tasks')


# ============================================================================
# Redis数据优化 - 数据读取辅助函数
# ============================================================================


def _transcribe_audio_with_lock(
    audio_path: str, 
    service_config: dict, 
    stage_name: str, 
    workflow_context: WorkflowContext
) -> dict:
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
        return _transcribe_audio_with_gpu_lock(audio_path, service_config, stage_name, workflow_context)
    else:
        # 不需要GPU锁，直接执行
        logger.info(f"[{stage_name}] 语音转录使用非GPU模式，跳过GPU锁")
        return _transcribe_audio_without_lock(audio_path, service_config, stage_name, workflow_context)


@gpu_lock()  # 仅在CUDA模式下获取GPU锁
def _transcribe_audio_with_gpu_lock(
    audio_path: str, 
    service_config: dict, 
    stage_name: str, 
    workflow_context: WorkflowContext
) -> dict:
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
    return _execute_transcription(audio_path, service_config, stage_name, workflow_context)


def _transcribe_audio_without_lock(
    audio_path: str, 
    service_config: dict, 
    stage_name: str, 
    workflow_context: WorkflowContext
) -> dict:
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
    return _execute_transcription(audio_path, service_config, stage_name, workflow_context)


def _execute_transcription(
    audio_path: str, 
    service_config: dict, 
    stage_name: str, 
    workflow_context: WorkflowContext
) -> dict:
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
    # 构建基于任务ID的临时目录
    task_id = workflow_context.workflow_id
    temp_dir = f"/share/workflows/{task_id}/tmp"
    os.makedirs(temp_dir, exist_ok=True)
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
        try:
            # 使用新的实时日志输出函数
            from services.common.subprocess_utils import run_gpu_command

            result = run_gpu_command(
                cmd,
                stage_name=stage_name,
                timeout=1800,  # 30 分钟超时
                cwd=str(current_dir),
                env=os.environ.copy()  # 继承环境变量（包括 CUDA_VISIBLE_DEVICES）
            )

            # ===== 检查执行结果 =====
            if result.returncode != 0:
                error_msg = f"subprocess 执行失败，返回码: {result.returncode}"
                logger.error(f"[{stage_name}] {error_msg}")
                logger.error(f"[{stage_name}] stdout: {result.stdout}")
                logger.error(f"[{stage_name}] stderr: {result.stderr}")
                raise RuntimeError(f"{error_msg}\nstderr: {result.stderr}")

            logger.info(f"[{stage_name}] subprocess 执行成功")
            logger.info(f"[{stage_name}] 总执行时间: {result.execution_time:.3f}s")

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

    finally:
        # ===== 清理临时文件（无论成功或失败）=====
        try:
            if output_file.exists():
                output_file.unlink()
                logger.debug(f"[{stage_name}] 已清理临时结果文件: {output_file}")
        except Exception as e:
            logger.warning(f"[{stage_name}] 清理临时文件失败: {e}")






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
    [工作流任务] 使用 Faster-Whisper 进行语音转录。

    该任务已迁移到统一的 BaseNodeExecutor 框架。

    输入：音频文件路径（通过工作流上下文获取）
    输出：标准化的转录结果，包含segments、词级时间戳等
    """
    from services.workers.faster_whisper_service.executors import FasterWhisperTranscribeExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = FasterWhisperTranscribeExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


