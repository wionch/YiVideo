# services/workers/pyannote_audio_service/app/tasks.py
# -*- coding: utf-8 -*-

"""
Pyannote Audio Service Tasks
基于 pyannote.audio 的说话人分离任务实现
"""

import os
import tempfile
import subprocess
import sys
import time
from pathlib import Path
from tokenize import TokenInfo
from typing import Dict, Any, Optional
import logging

import torch
import librosa
import numpy as np
from pyannote.audio import Pipeline
from pyannote.core import Annotation, Segment

# 导入Celery应用和工作流模型
from services.workers.pyannote_audio_service.app.celery_app import celery_app

# 导入共享模块
from services.common.config_loader import get_config
from services.common.logger import get_logger
from services.common.locks import gpu_lock
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext

config = get_config()
logger = get_logger(__name__)

class PyannoteAudioTask:
    """Pyannote音频任务基类 - 简化版本，与测试脚本保持一致"""

    def __init__(self):
        logger.info("初始化PyannoteAudioTask...")

    def load_pipeline(self):
        """加载说话人分离管道 - 与测试脚本保持一致的简化实现"""
        try:
            logger.info("开始加载说话人分离管道...")

            # 直接使用测试脚本的简单方式
            hf_token = os.environ.get('HF_TOKEN', config.get('pyannote_audio_service', {}).get('hf_token', ''))
            model_name = "pyannote/speaker-diarization-community-1"

            logger.info(f"选择模型: {model_name}")
            logger.info(f"HF Token存在: {bool(hf_token)}")

            # 与测试脚本完全一致的加载方式
            logger.info("开始从HuggingFace加载pipeline...")
            pipeline = Pipeline.from_pretrained(model_name, token=hf_token)
            logger.info("Pipeline加载完成")

            # 移动到CUDA设备（与测试脚本一致）
            logger.info("将pipeline移动到CUDA设备...")
            pipeline.to(torch.device("cuda"))
            logger.info("Pipeline已移动到CUDA设备")

            return pipeline

        except Exception as e:
            logger.error(f"加载说话人分离管道失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            raise

@celery_app.task(bind=True, name='pyannote_audio.diarize_speakers')
@gpu_lock(timeout=1800, poll_interval=0.5)
def diarize_speakers(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    说话人分离工作流节点 - 使用subprocess调用独立推理脚本

    Args:
        context: 工作流上下文，包含以下字段：
            - workflow_id: 工作流ID
            - input_params: 输入参数
            - stages: 阶段信息
            - error: 错误信息（如果有）

    Returns:
        dict: 包含说话人分离结果的字典
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 验证输入上下文
        if not isinstance(context, dict):
            raise ValueError("工作流上下文必须为字典格式")

        workflow_id = workflow_context.workflow_id
        logger.info(f"[{workflow_id}] 开始说话人分离任务 (subprocess模式)")

        # 步骤1: 获取音频文件路径（与其他服务保持一致）
        audio_path = None
        audio_source = ""

        # 首先检查工作流中是否有其他任务产生的音频文件
        ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.output and ffmpeg_stage.output.get('audio_path'):
            audio_path = ffmpeg_stage.output.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                audio_source = "ffmpeg.extract_audio"
                logger.info(f"[{workflow_id}] 成功获取ffmpeg提取的音频: {audio_path}")

        # 如果没有ffmpeg提取的音频，检查音频分离服务
        if not audio_path:
            separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
            if separator_stage and separator_stage.output:
                # 优先使用vocal_audio，其次使用instrumental_audio
                for audio_key in ['vocal_audio', 'instrumental_audio']:
                    potential_path = separator_stage.output.get(audio_key)
                    if potential_path and os.path.exists(potential_path):
                        audio_path = potential_path
                        audio_source = f"audio_separator.separate_vocals.{audio_key}"
                        logger.info(f"[{workflow_id}] 成功获取音频分离的音频: {audio_path}")
                        break

        # 如果没有来自其他任务的音频，回退到 input_params 中的文件
        if not audio_path:
            # 优先使用 audio_path，否则使用 video_path（支持直接处理音频文件或视频文件）
            audio_path = workflow_context.input_params.get("audio_path") or workflow_context.input_params.get("video_path")
            if audio_path:
                audio_source = "原始输入文件"
                logger.info(f"[{workflow_id}] 回退到原始文件: {audio_path}")

        if not audio_path:
            raise ValueError("无法获取音频文件路径：请确保 ffmpeg.extract_audio 或 audio_separator.separate_vocals 任务已成功完成，或在 input_params 中提供 audio_path/video_path")

        # 检查音频文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        logger.info(f"[{workflow_id}] ========== 音频源选择结果 ==========")
        logger.info(f"[{workflow_id}] 选择的音频源: {audio_source}")
        logger.info(f"[{workflow_id}] 音频文件路径: {audio_path}")
        logger.info(f"[{workflow_id}] ======================================")

        # 创建工作流输出目录
        workflow_output_dir = Path(workflow_context.shared_storage_path) / "diarization"
        workflow_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{workflow_id}] 工作流输出目录创建成功: {workflow_output_dir}")

        # 准备输出文件路径 - 保存到工作流目录
        output_file = workflow_output_dir / "diarization_result.json"

        # 获取推理脚本路径
        current_dir = Path(__file__).parent
        infer_script = current_dir / "pyannote_infer.py"

        if not infer_script.exists():
            raise FileNotFoundError(f"推理脚本不存在: {infer_script}")

        # 获取配置 - 功能开关从配置文件读取，密钥从环境变量读取
        service_config = config.get('pyannote_audio_service', {})
        use_paid_api = service_config.get('use_paid_api', False)
        hf_token = os.environ.get('HF_TOKEN', service_config.get('hf_token', ''))
        pyannoteai_api_key = os.environ.get('PYANNOTEAI_API_KEY', service_config.get('pyannoteai_api_key', ''))

        # 准备subprocess命令
        logger.info(f"[{workflow_id}] 准备通过subprocess调用推理脚本")
        logger.info(f"[{workflow_id}] 推理脚本: {infer_script}")
        logger.info(f"[{workflow_id}] 音频文件: {audio_path}")
        logger.info(f"[{workflow_id}] 输出文件: {output_file}")
        logger.info(f"[{workflow_id}] 使用付费接口: {use_paid_api}")

        if use_paid_api:
            logger.info(f"[{workflow_id}] PyannoteAI API Key: {'已提供' if pyannoteai_api_key else '未提供'}")
        else:
            logger.info(f"[{workflow_id}] HF Token: {'已提供' if hf_token else '未提供'}")

        cmd = [
            sys.executable,  # 使用当前Python解释器
            str(infer_script),
            "--audio_path", str(audio_path),
            "--output_file", str(output_file)
        ]

        if use_paid_api:
            # 使用付费接口
            cmd.extend(["--use_paid_api"])
            if pyannoteai_api_key:
                cmd.extend(["--pyannoteai_api_key", pyannoteai_api_key])
        else:
            # 使用免费接口
            if hf_token:
                cmd.extend(["--hf_token", hf_token])

        logger.info(f"[{workflow_id}] 执行命令: {' '.join(cmd)}")

        # 执行subprocess
        logger.info(f"[{workflow_id}] 开始执行subprocess推理...")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30分钟超时
                cwd=str(current_dir),
                env=os.environ.copy()
            )

            execution_time = time.time() - start_time
            logger.info(f"[{workflow_id}] subprocess执行完成，耗时: {execution_time:.3f}s")

            # 检查执行结果
            if result.returncode != 0:
                error_msg = f"subprocess执行失败，返回码: {result.returncode}"
                logger.error(f"[{workflow_id}] {error_msg}")
                logger.error(f"[{workflow_id}] stdout: {result.stdout}")
                logger.error(f"[{workflow_id}] stderr: {result.stderr}")
                raise RuntimeError(f"{error_msg}\nstderr: {result.stderr}")

            logger.info(f"[{workflow_id}] subprocess执行成功")
            logger.info(f"[{workflow_id}] stdout: {result.stdout}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("subprocess执行超时（30分钟）")
        except Exception as e:
            raise RuntimeError(f"subprocess执行异常: {str(e)}")

        # 读取结果文件
        if not output_file.exists():
            raise RuntimeError(f"推理结果文件不存在: {output_file}")

        logger.info(f"[{workflow_id}] 读取推理结果文件: {output_file}")

        import json
        with open(output_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        if not result_data.get('success', False):
            error_info = result_data.get('error', {})
            raise RuntimeError(f"推理失败: {error_info.get('message', '未知错误')} (类型: {error_info.get('type', '未知')})")

        # 提取说话人片段
        speaker_segments = result_data.get('segments', [])
        total_speakers = result_data.get('total_speakers', 0)
        metadata = result_data.get('metadata', {})
        api_type = metadata.get('api_type', 'free')
        model_name = metadata.get('model', 'unknown')

        # 生成说话人相关数据，以便 faster_whisper.generate_subtitle_files 使用
        detected_speakers = [f"SPEAKER_{i:02d}" for i in range(total_speakers)]

        # 说话人统计信息
        speaker_statistics = {}
        for speaker in detected_speakers:
            speaker_segments_for_speaker = [seg for seg in speaker_segments if seg.get('speaker') == speaker]
            total_duration = sum(seg.get('duration', 0) for seg in speaker_segments_for_speaker)
            speaker_statistics[speaker] = {
                'segments': len(speaker_segments_for_speaker),
                'duration': total_duration,
                'words': 0  # 将在后续处理中填充
            }

        # 创建精简版的输出数据
        stage_name = "pyannote_audio.diarize_speakers"

        # 精简的API响应数据，移除冗长的 speaker_segments 数组和 speaker_enhanced_segments
        output_data = {
            "diarization_file": str(output_file),
            "detected_speakers": detected_speakers,  # 保留供 faster_whisper 使用
            "speaker_statistics": speaker_statistics,  # 保留供 faster_whisper 使用
            "total_speakers": total_speakers,
            "total_segments": len(speaker_segments),  # 只保留数量，不保留详细数据
            "summary": f"检测到 {total_speakers} 个说话人，共 {len(speaker_segments)} 个说话片段 (使用{'付费' if api_type == 'paid' else '免费'}接口: {model_name})",
            "execution_method": "subprocess",
            "execution_time": execution_time,
            "audio_source": audio_source,
            "api_type": api_type,
            "model_name": model_name,
            "use_paid_api": use_paid_api
        }

        # 更新阶段状态 - 成功
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        api_type_text = "付费" if use_paid_api else "免费"
        logger.info(f"[{workflow_id}] 说话人分离完成 (subprocess模式, {api_type_text}接口): {total_speakers} 个说话人，{len(speaker_segments)} 个片段，耗时: {execution_time:.3f}s")

    except Exception as e:
        # 获取workflow_id用于错误日志
        workflow_id = context.get('workflow_id', 'unknown')
        error_msg = f"[{workflow_id}] 说话人分离失败: {str(e)}"
        logger.error(error_msg)

        # 更新工作流上下文 - 错误格式
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"
    finally:
        # 无论如何都要更新状态
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()

@celery_app.task(bind=True, name='pyannote_audio.get_speaker_segments')
def get_speaker_segments(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取指定说话人的片段

    Args:
        context: 工作流上下文

    Returns:
        dict: 包含指定说话人片段的字典
    """
    try:
        workflow_id = context.get('workflow_id', 'unknown')
        input_params = context.get('input_params', {})

        diarization_file = input_params.get('diarization_file')
        target_speaker = input_params.get('speaker', None)

        if not diarization_file or not os.path.exists(diarization_file):
            raise FileNotFoundError(f"说话人分离结果文件不存在: {diarization_file}")

        # 加载结果文件
        import json
        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        segments = data.get('segments', [])

        if target_speaker:
            # 过滤指定说话人的片段
            filtered_segments = [seg for seg in segments if seg['speaker'] == target_speaker]
            summary = f"说话人 {target_speaker} 的片段: {len(filtered_segments)} 个"
        else:
            # 返回所有说话人的片段统计
            speaker_stats = {}
            for seg in segments:
                speaker = seg['speaker']
                if speaker not in speaker_stats:
                    speaker_stats[speaker] = []
                speaker_stats[speaker].append(seg)

            filtered_segments = segments
            summary = f"所有说话人片段统计: {len(speaker_stats)} 个说话人"

        return {
            "success": True,
            "data": {
                "segments": filtered_segments,
                "summary": summary
            }
        }

    except Exception as e:
        workflow_id = context.get('workflow_id', 'unknown') if 'context' in locals() else 'unknown'
        logger.error(f"[{workflow_id}] 获取说话人片段失败: {e}")
        return {
            "success": False,
            "error": {
                "task": "pyannote_audio.get_speaker_segments",
                "message": str(e),
                "type": type(e).__name__
            }
        }

@celery_app.task(bind=True, name='pyannote_audio.validate_diarization')
def validate_diarization(self: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证说话人分离结果的质量

    Args:
        context: 工作流上下文

    Returns:
        dict: 包含质量验证结果的字典
    """
    try:
        workflow_id = context.get('workflow_id', 'unknown')
        input_params = context.get('input_params', {})

        diarization_file = input_params.get('diarization_file')

        if not diarization_file or not os.path.exists(diarization_file):
            raise FileNotFoundError(f"说话人分离结果文件不存在: {diarization_file}")

        # 加载结果文件
        import json
        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        segments = data.get('segments', [])

        if not segments:
            return {
                "success": True,
                "data": {
                    "valid": False,
                    "issues": ["没有检测到任何说话人片段"],
                    "summary": "说话人分离结果无效"
                }
            }

        # 质量检查
        issues = []
        validation_results = {
            "valid": True,
            "total_segments": len(segments),
            "total_speakers": data.get('total_speakers', 0),
            "total_duration": 0,
            "avg_segment_duration": 0,
            "issues": []
        }

        # 计算总时长
        total_duration = 0
        segment_durations = []

        for segment in segments:
            duration = segment.get('duration', 0)
            segment_durations.append(duration)
            total_duration += duration

            # 检查片段时长
            if duration < 0.5:  # 片段过短
                issues.append(f"片段过短 ({duration:.2f}s)")
            elif duration > 30:  # 片段过长
                issues.append(f"片段过长 ({duration:.2f}s)")

        validation_results["total_duration"] = total_duration
        validation_results["avg_segment_duration"] = total_duration / len(segments) if segments else 0

        # 检查说话人数量
        if validation_results["total_speakers"] < 1:
            issues.append("没有检测到说话人")
            validation_results["valid"] = False
        elif validation_results["total_speakers"] > 10:  # 说话人过多可能是问题
            issues.append(f"检测到过多说话人 ({validation_results['total_speakers']})")

        # 检查片段分布
        if len(set(seg['speaker'] for seg in segments)) < validation_results["total_speakers"]:
            issues.append("部分说话人片段不完整")

        validation_results["issues"] = issues
        validation_results["valid"] = len(issues) == 0

        summary = "说话人分离结果有效" if validation_results["valid"] else "说话人分离结果存在问题"

        return {
            "success": True,
            "data": {
                "validation": validation_results,
                "summary": summary
            }
        }

    except Exception as e:
        workflow_id = context.get('workflow_id', 'unknown') if 'context' in locals() else 'unknown'
        logger.error(f"[{workflow_id}] 验证说话人分离失败: {e}")
        return {
            "success": False,
            "error": {
                "task": "pyannote_audio.validate_diarization",
                "message": str(e),
                "type": type(e).__name__
            }
        }