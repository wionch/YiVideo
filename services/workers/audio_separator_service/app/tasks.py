#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - Celery 任务定义
功能：基于 UVR-MDX 模型的人声/背景音分离任务
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from celery import Task

from services.common.locks import gpu_lock
from services.common.logger import get_logger
from services.common.context import WorkflowContext, StageExecution
from services.common import state_manager
from .celery_app import celery_app
from .model_manager import get_model_manager
# 导入新的通用配置加载器
from services.common.config_loader import CONFIG
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
from services.common.file_service import get_file_service

# 配置日志
logger = get_logger('audio_separator.tasks')


class AudioSeparatorTask(Task):
    """音频分离任务基类"""

    def __init__(self):
        super().__init__()
        self.model_manager = get_model_manager()
        self._config_cache = None
        self._config_timestamp = 0

    def get_config(self):
        """获取实时配置，支持热重载和简单缓存"""
        import time
        current_time = time.time()

        # 缓存5秒，避免频繁读取文件，但保持实时性
        if (self._config_cache is None or
            current_time - self._config_timestamp > 5):
            self._config_cache = CONFIG.get('audio_separator_service', {})
            self._config_timestamp = current_time
            logger.debug("配置缓存已更新")

        return self._config_cache

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时的回调"""
        logger.error(f"任务 {task_id} 失败: {exc}", exc_info=True)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功时的回调"""
        logger.info(f"任务 {task_id} 成功完成")
        super().on_success(retval, task_id, args, kwargs)


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.separate_vocals',
    max_retries=3,
    default_retry_delay=60
)
@gpu_lock()  # 🔒 集成 GPU 锁
def separate_vocals(self, context: dict) -> dict:
    """
    [工作流任务] 分离音频中的人声和背景音

    从 WorkflowContext 中获取输入，执行人声/背景音分离，并将结果添加到 context 中。
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name

    # 初始化阶段状态
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 先初始化为空，稍后在音频源选择完成后记录
        workflow_context.stages[stage_name].input_params = resolved_params.copy() if resolved_params else {}

        # --- 文件下载准备 ---
        file_service = get_file_service()
        
        # 1. 音频源选择逻辑：优先使用已提取的音频文件
        audio_path = None
        audio_source = ""

        logger.info(f"[{stage_name}] 开始音频源选择逻辑")
        
        # 优先检查 ffmpeg.extract_audio 阶段的音频输出
        ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.status == 'SUCCESS' and ffmpeg_stage.output.get('audio_path'):
            audio_path = ffmpeg_stage.output['audio_path']
            audio_source = "已提取音频 (ffmpeg.extract_audio)"
            logger.info(f"[{stage_name}] 成功获取已提取音频: {audio_path}")

        # 如果没有已提取音频，使用统一的参数获取逻辑
        if not audio_path:
            # 使用 get_param_with_fallback 进行统一的参数获取
            audio_path = get_param_with_fallback(
                "audio_path",
                resolved_params,
                workflow_context,
                fallback_from_input_data=True
            )
            
            if audio_path:
                audio_source = "原始输入文件"
                logger.info(f"[{stage_name}] 统一参数获取成功: {audio_path}")
            else:
                # 尝试从 video_path 回退（兼容性）
                video_path = get_param_with_fallback(
                    "video_path",
                    resolved_params,
                    workflow_context,
                    fallback_from_input_data=True
                )
                if video_path:
                    audio_path = video_path
                    audio_source = "原始视频文件"
                    logger.info(f"[{stage_name}] 从 video_path 回退成功: {audio_path}")

        if not audio_path:
            raise ValueError("无法获取音频文件路径：请确保 ffmpeg.extract_audio 任务已成功完成，或在 input_params 中提供 audio_path/video_path")

        logger.info(f"[{stage_name}] ========== 音频源选择结果 ==========")
        logger.info(f"[{stage_name}] 选择的音频源: {audio_source}")
        logger.info(f"[{stage_name}] 音频文件路径: {audio_path}")
        logger.info(f"[{stage_name}] =================================")
        
        # --- 文件下载 ---
        if audio_path and not os.path.exists(audio_path):
            logger.info(f"[{stage_name}] 开始下载音频文件: {audio_path}")
            audio_path = file_service.resolve_and_download(audio_path, workflow_context.shared_storage_path)
            logger.info(f"[{stage_name}] 音频文件下载完成: {audio_path}")

        logger.info(f"[{stage_name}] 开始音频分离任务")

        # 记录实际使用的输入参数到input_params
        recorded_input_params = workflow_context.stages[stage_name].input_params.copy()
        
        # 如果没有显式参数，记录智能选择的输入源
        if not recorded_input_params:
            if audio_source == "已提取音频 (ffmpeg.extract_audio)":
                recorded_input_params['audio_source'] = 'ffmpeg.extract_audio'
            elif audio_source == "原始输入文件":
                recorded_input_params['audio_source'] = 'input_data'
                # 记录实际使用的输入文件路径
                input_audio = workflow_context.input_params.get("input_data", {}).get("audio_path") or workflow_context.input_params.get("input_data", {}).get("video_path")
                if input_audio:
                    recorded_input_params['audio_path'] = input_audio
            else:
                recorded_input_params['audio_source'] = 'unknown'
        
        # 2. 从配置文件读取默认参数
        config = self.get_config()
        quality_mode = "default"
        use_vocal_optimization = False
        vocal_optimization_level = config.get('vocal_optimization_level')
        model_type = config.get('model_type')
        
        # 从input_params中获取覆盖参数 (优先使用 resolved_params)
        audio_separator_config = resolved_params.get('audio_separator_config', 
                                                   workflow_context.input_params.get('audio_separator_config', {}))
        quality_mode = audio_separator_config.get('quality_mode', quality_mode)
        use_vocal_optimization = audio_separator_config.get('use_vocal_optimization', use_vocal_optimization)
        vocal_optimization_level = audio_separator_config.get('vocal_optimization_level', vocal_optimization_level)
        model_type = audio_separator_config.get('model_type', model_type)

        logger.info(f"[{stage_name}] 质量模式: {quality_mode}")
        logger.info(f"[{stage_name}] 使用人声优化: {use_vocal_optimization}")
        logger.info(f"[{stage_name}] 模型类型: {model_type}")

        # 记录音频分离配置参数到input_params
        if audio_separator_config or quality_mode != "default" or model_type:
            recorded_input_params['quality_mode'] = quality_mode
            recorded_input_params['model_type'] = model_type
            if use_vocal_optimization:
                recorded_input_params['use_vocal_optimization'] = True
                if vocal_optimization_level:
                    recorded_input_params['vocal_optimization_level'] = vocal_optimization_level
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        # 3. 验证输入文件
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 4. 确定使用的模型
        if model_type.lower() == "demucs":
            model_name = config.get('demucs_default_model')
            if audio_separator_config and 'model_name' in audio_separator_config:
                model_name = audio_separator_config['model_name']
            elif quality_mode == 'high_quality':
                model_name = config.get('demucs_high_quality_model', 'htdemucs_6s')
            elif quality_mode == 'fast':
                model_name = config.get('demucs_fast_model')
            else:
                model_name = config.get('demucs_balanced_model')
        else:
            model_name = config.get('default_model')
            if audio_separator_config and 'model_name' in audio_separator_config:
                model_name = audio_separator_config['model_name']
            elif quality_mode == 'high_quality':
                model_name = config.get('high_quality_model')
            elif quality_mode == 'fast':
                model_name = config.get('fast_model')

        logger.info(f"[{stage_name}] 使用模型: {model_name}")

        # 5. 创建任务专属输出目录
        task_id = workflow_context.workflow_id
        task_output_dir = Path(f"/share/workflows/{task_id}/audio/audio_separated")
        task_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{stage_name}] 输出目录: {task_output_dir}")

        # 6. 执行音频分离 (Subprocess 模式)
        logger.info(f"[{stage_name}] 开始执行分离 (subprocess模式)...")
        result = self.model_manager.separate_audio_subprocess(
            audio_path=audio_path,
            model_name=model_name,
            output_dir=str(task_output_dir),
            model_type=model_type,
            use_vocal_optimization=use_vocal_optimization,
            vocal_optimization_level=vocal_optimization_level
        )

        # 7. 计算处理时间
        processing_time = time.time() - start_time
        logger.info(f"[{stage_name}] 分离完成，耗时: {processing_time:.2f} 秒")
        logger.info(f"[{stage_name}] 人声文件: {result.get('vocals')}")
        logger.info(f"[{stage_name}] 背景音文件: {result.get('instrumental')}")

        # 8. 准备输出数据结构
        audio_list = list(result.get('all_tracks', {}).values())
        vocal_audio = result.get('vocals')

        # 确保保存的是完整路径而非文件名
        if vocal_audio and not os.path.isabs(vocal_audio):
            # 如果是相对路径，补充为完整路径
            vocal_audio = str(task_output_dir / vocal_audio)
            logger.info(f"[{stage_name}] 转换人声文件路径为完整路径: {vocal_audio}")

        # 处理 audio_list，确保所有路径都是完整的
        full_audio_list = []
        for audio_file in audio_list:
            if audio_file and not os.path.isabs(audio_file):
                full_audio_list.append(str(task_output_dir / audio_file))
            else:
                full_audio_list.append(audio_file)
        audio_list = full_audio_list

        if not vocal_audio:
            logger.error(f"[{stage_name}] 未能确定人声音频文件")
            raise ValueError("无法确定人声音频文件")

        # 9. 更新 WorkflowContext
        workflow_context.stages[stage_name] = StageExecution(
            status="SUCCESS",
            output={
                'audio_list': audio_list,
                'vocal_audio': vocal_audio,
                'model_used': model_name,
                'quality_mode': quality_mode
            },
            duration=round(processing_time, 2)
        )

        # 10. 更新状态并返回
        state_manager.update_workflow_state(workflow_context)
        logger.info(f"[{stage_name}] 任务完成，状态已更新")
        return workflow_context.model_dump()

    except Exception as e:
        logger.error(f"[{stage_name}] 音频分离失败: {str(e)}", exc_info=True)
        processing_time = time.time() - start_time
        workflow_context.stages[stage_name] = StageExecution(
            status="FAILED",
            output={'error': str(e)},
            duration=round(processing_time, 2)
        )
        state_manager.update_workflow_state(workflow_context)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.health_check'
)
def health_check(self) -> Dict[str, Any]:
    """健康检查任务"""
    try:
        health_status = self.model_manager.health_check()
        health_status['service_status'] = 'healthy'
        health_status['timestamp'] = time.time()
        return health_status
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}", exc_info=True)
        return {
            'service_status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Audio Separator Tasks 模块加载成功")
