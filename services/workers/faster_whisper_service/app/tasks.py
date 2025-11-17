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
from services.common.file_service import get_file_service

logger = get_logger('tasks')


# ============================================================================
# Redis数据优化 - 数据读取辅助函数
# ============================================================================


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

        # --- 文件下载准备 ---
        file_service = get_file_service()
        
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
        
        # --- 文件下载 ---
        logger.info(f"[{stage_name}] 开始下载音频文件: {audio_path}")
        audio_path = file_service.resolve_and_download(audio_path, workflow_context.shared_storage_path)
        logger.info(f"[{stage_name}] 音频文件下载完成: {audio_path}")
        
        # 验证音频文件存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

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


