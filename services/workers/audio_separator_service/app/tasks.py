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
from .config import get_config

# 配置日志
logger = get_logger('audio_separator.tasks')


class AudioSeparatorTask(Task):
    """音频分离任务基类"""

    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.model_manager = get_model_manager()

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

    Args:
        context: 工作流上下文字典

    Returns:
        dict: 更新后的工作流上下文
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name

    # 初始化阶段状态
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 1. 从 workflow_context.input_params 中获取输入音频路径
        # 优先使用 audio_path，否则使用 video_path（支持直接处理音频文件或视频文件）
        audio_path = workflow_context.input_params.get("audio_path") or workflow_context.input_params.get("video_path")
        if not audio_path:
            raise ValueError("input_params 中缺少 audio_path 或 video_path")

        logger.info(f"[{stage_name}] 开始音频分离任务")
        logger.info(f"[{stage_name}] 输入文件: {audio_path}")

        # 2. 从配置文件读取默认参数
        quality_mode = "default"  # 默认质量模式
        use_vocal_optimization = False  # 默认不使用人声优化
        vocal_optimization_level = self.config.vocal_optimization_level
        model_type = self.config.model_type  # 新增模型类型
        
        # 从input_params中获取覆盖参数（如果有的话）
        audio_separator_config = workflow_context.input_params.get('audio_separator_config', {})
        if audio_separator_config:
            quality_mode = audio_separator_config.get('quality_mode', quality_mode)
            use_vocal_optimization = audio_separator_config.get('use_vocal_optimization', use_vocal_optimization)
            vocal_optimization_level = audio_separator_config.get('vocal_optimization_level', vocal_optimization_level)
            # 兼容旧的参数传递方式
            model_type = audio_separator_config.get('model_type', model_type)

        logger.info(f"[{stage_name}] 质量模式: {quality_mode}")
        logger.info(f"[{stage_name}] 使用人声优化: {use_vocal_optimization}")
        logger.info(f"[{stage_name}] 模型类型: {model_type}")
        if use_vocal_optimization:
            logger.info(f"[{stage_name}] 优化级别: {vocal_optimization_level}")

        # 3. 验证输入文件
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 4. 确定使用的模型
        if model_type.lower() == "demucs":
            # Demucs 模型选择逻辑
            model_name = self.config.demucs_default_model  # 默认使用Demucs模型
            
            # 根据质量模式选择模型（如果没有明确指定模型名称）
            if audio_separator_config and 'model_name' in audio_separator_config:
                model_name = audio_separator_config['model_name']
            elif quality_mode == 'high_quality':
                model_name = getattr(self.config, 'demucs_high_quality_model', 'htdemucs_6s')
            elif quality_mode == 'fast':
                model_name = self.config.demucs_fast_model
            else:  # default or balanced
                model_name = self.config.demucs_balanced_model
        else:
            # MDX 模型选择逻辑（原有逻辑）
            model_name = self.config.default_model  # 默认使用配置文件中的模型
            
            # 根据质量模式选择模型（如果没有明确指定模型名称）
            if audio_separator_config and 'model_name' in audio_separator_config:
                model_name = audio_separator_config['model_name']
            elif quality_mode == 'high_quality':
                model_name = self.config.high_quality_model
            elif quality_mode == 'fast':
                model_name = self.config.fast_model

        logger.info(f"[{stage_name}] 使用模型: {model_name}")

        # 5. 创建任务专属输出目录 - 使用新的目录结构
        task_id = workflow_context.workflow_id
        task_output_dir = Path(f"/share/workflows/{task_id}/audio/audio_separated")
        task_output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{stage_name}] 输出目录: {task_output_dir}")

        # 6. 执行音频分离
        logger.info(f"[{stage_name}] 开始执行分离...")
        if use_vocal_optimization:
            # 使用优化的人声分离方法
            result = self.model_manager.separate_vocals_optimized(
                audio_path=audio_path,
                model_name=model_name,
                output_dir=str(task_output_dir),
                optimization_level=vocal_optimization_level
            )
        else:
            # 使用标准分离方法，传递模型类型
            result = self.model_manager.separate_audio(
                audio_path=audio_path,
                model_name=model_name,
                output_dir=str(task_output_dir),
                model_type=model_type
            )

        # 7. 计算处理时间
        processing_time = time.time() - start_time

        logger.info(f"[{stage_name}] 分离完成，耗时: {processing_time:.2f} 秒")
        logger.info(f"[{stage_name}] 人声文件: {result['vocals']}")
        logger.info(f"[{stage_name}] 背景音文件: {result['instrumental']}")

        # 8. 更新 WorkflowContext
        workflow_context.stages[stage_name] = StageExecution(
            status="COMPLETED",
            output_data={
                'vocals_path': result['vocals'],
                'instrumental_path': result['instrumental'],
                'model_used': model_name,
                'quality_mode': quality_mode,
                'processing_time': round(processing_time, 2)
            }
        )

        # 9. 将分离结果添加到 context 中，供后续任务使用
        updated_context = workflow_context.model_dump()
        updated_context['vocals_path'] = result['vocals']
        updated_context['instrumental_path'] = result['instrumental']

        # 10. 更新状态
        state_manager.update_workflow_state(workflow_context)

        logger.info(f"[{stage_name}] 任务完成，状态已更新")
        return updated_context

    except Exception as e:
        logger.error(f"[{stage_name}] 音频分离失败: {str(e)}", exc_info=True)

        # 更新失败状态
        workflow_context.stages[stage_name] = StageExecution(
            status="FAILED",
            output_data={'error': str(e)}
        )
        state_manager.update_workflow_state(workflow_context)

        # 记录错误并重试
        if self.request.retries < self.max_retries:
            logger.warning(f"[{stage_name}] 准备重试 (第 {self.request.retries + 1} 次)")
            raise self.retry(exc=e)

        # 返回失败的 context
        return workflow_context.model_dump()


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.separate_vocals_optimized',
    max_retries=3,
    default_retry_delay=60
)
@gpu_lock()  # 🔒 集成 GPU 锁
def separate_vocals_optimized(self, context: dict) -> dict:
    """
    [工作流任务] 使用优化参数分离音频中的人声和背景音
    
    专门针对人声分离效果不好的问题进行优化，减少背景音乐残留。
    
    Args:
        context: 工作流上下文字典
    
    Returns:
        dict: 更新后的工作流上下文
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name

    # 初始化阶段状态
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 1. 从 workflow_context.input_params 中获取输入音频路径
        audio_path = workflow_context.input_params.get("audio_path") or workflow_context.input_params.get("video_path")
        if not audio_path:
            raise ValueError("input_params 中缺少 audio_path 或 video_path")

        logger.info(f"[{stage_name}] 开始优化人声分离任务")
        logger.info(f"[{stage_name}] 输入文件: {audio_path}")

        # 2. 从 workflow_context.input_params 中获取配置参数
        audio_separator_config = workflow_context.input_params.get('audio_separator_config', {})
        optimization_level = audio_separator_config.get('vocal_optimization_level', 'balanced')
        model_name = audio_separator_config.get('model_name', self.config.vocal_optimization_model)
        output_dir = audio_separator_config.get('output_dir')

        logger.info(f"[{stage_name}] 优化级别: {optimization_level}")
        logger.info(f"[{stage_name}] 使用模型: {model_name}")

        # 3. 验证输入文件
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 4. 创建任务专属输出目录 - 使用新的目录结构
        task_id = workflow_context.workflow_id
        task_output_dir = Path(f"/share/workflows/{task_id}/audio/audio_separated")
        task_output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{stage_name}] 输出目录: {task_output_dir}")

        # 5. 执行优化人声分离
        logger.info(f"[{stage_name}] 开始执行优化人声分离...")
        result = self.model_manager.separate_vocals_optimized(
            audio_path=audio_path,
            model_name=model_name,
            output_dir=str(task_output_dir),
            optimization_level=optimization_level
        )

        # 6. 计算处理时间
        processing_time = time.time() - start_time

        logger.info(f"[{stage_name}] 优化分离完成，耗时: {processing_time:.2f} 秒")
        logger.info(f"[{stage_name}] 人声文件: {result['vocals']}")
        logger.info(f"[{stage_name}] 背景音文件: {result['instrumental']}")

        # 7. 更新 WorkflowContext
        workflow_context.stages[stage_name] = StageExecution(
            status="COMPLETED",
            output_data={
                'vocals_path': result['vocals'],
                'instrumental_path': result['instrumental'],
                'model_used': model_name,
                'optimization_level': optimization_level,
                'processing_time': round(processing_time, 2),
                'vocal_optimization_enabled': True
            }
        )

        # 8. 将分离结果添加到 context 中，供后续任务使用
        updated_context = workflow_context.model_dump()
        updated_context['vocals_path'] = result['vocals']
        updated_context['instrumental_path'] = result['instrumental']

        # 9. 更新状态
        state_manager.update_workflow_state(workflow_context)

        logger.info(f"[{stage_name}] 优化任务完成，状态已更新")
        return updated_context

    except Exception as e:
        logger.error(f"[{stage_name}] 优化人声分离失败: {str(e)}", exc_info=True)

        # 更新失败状态
        workflow_context.stages[stage_name] = StageExecution(
            status="FAILED",
            output_data={'error': str(e)}
        )
        state_manager.update_workflow_state(workflow_context)

        # 记录错误并重试
        if self.request.retries < self.max_retries:
            logger.warning(f"[{stage_name}] 准备重试 (第 {self.request.retries + 1} 次)")
            raise self.retry(exc=e)

        # 返回失败的 context
        return workflow_context.model_dump()


@celery_app.task(
    bind=True,
    base=AudioSeparatorTask,
    name='audio_separator.batch_separate',
    max_retries=2,
    default_retry_delay=30
)
@gpu_lock()  # 🔒 集成 GPU 锁
def batch_separate_vocals(
    self,
    audio_files: list,
    output_dir: Optional[str] = None,
    model_name: Optional[str] = None,
    quality_mode: str = 'default'
) -> Dict[str, Any]:
    """
    批量分离音频文件

    注意：此任务已集成GPU锁，确保GPU资源安全

    Args:
        audio_files: 音频文件路径列表
        output_dir: 输出目录
        model_name: 模型名称
        quality_mode: 质量模式

    Returns:
        Dict[str, Any]: 批量处理结果
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] 开始批量分离任务，共 {len(audio_files)} 个文件")

    # 验证输入
    if not audio_files:
        raise ValueError("音频文件列表不能为空")

    # 验证所有文件存在
    missing_files = []
    for audio_path in audio_files:
        if not Path(audio_path).exists():
            missing_files.append(audio_path)

    if missing_files:
        raise FileNotFoundError(f"以下音频文件不存在: {missing_files}")

    results = []
    failed_files = []

    for idx, audio_path in enumerate(audio_files):
        logger.info(f"[{task_id}] 处理第 {idx + 1}/{len(audio_files)} 个文件: {audio_path}")

        try:
            # 验证单个文件
            if not Path(audio_path).exists():
                error_msg = f"文件不存在: {audio_path}"
                logger.error(f"[{task_id}] {error_msg}")
                failed_files.append((audio_path, error_msg))
                continue

            # 为每个文件创建独立的 context
            context = {
                'workflow_id': f"{task_id}_file_{idx}",
                'audio_path': audio_path,
                'audio_separator_config': {
                    'quality_mode': quality_mode,
                    'model_name': model_name,
                    'output_dir': output_dir
                }
            }

            # 调用单文件分离任务
            # 注意：由于已经获得GPU锁，这里使用同步调用避免嵌套锁
            try:
                result = separate_vocals.apply(
                    args=(context,),
                    throw=True  # 抛出异常以便处理
                )

                if result and result.result:
                    results.append({
                        'file': audio_path,
                        'status': 'success',
                        'result': result.result
                    })
                else:
                    error_msg = "任务返回空结果"
                    logger.error(f"[{task_id}] 处理文件 {audio_path} 失败: {error_msg}")
                    failed_files.append((audio_path, error_msg))

            except Exception as task_error:
                error_msg = f"任务执行失败: {str(task_error)}"
                logger.error(f"[{task_id}] 处理文件 {audio_path} 失败: {error_msg}")
                failed_files.append((audio_path, error_msg))

        except Exception as e:
            error_msg = f"处理文件时发生未知错误: {str(e)}"
            logger.error(f"[{task_id}] {error_msg}", exc_info=True)
            failed_files.append((audio_path, error_msg))

    # 统计结果
    success_count = len(results)
    failed_count = len(failed_files)

    logger.info(f"[{task_id}] 批量分离完成: 成功 {success_count}, 失败 {failed_count}")

    # 如果失败率过高，记录警告
    if len(audio_files) > 0 and failed_count / len(audio_files) > 0.5:
        logger.warning(f"[{task_id}] 批量任务失败率过高: {failed_count}/{len(audio_files)}")

    # 添加失败文件详情
    failed_details = []
    for file_path, error in failed_files:
        failed_details.append({
            'file': file_path,
            'status': 'failed',
            'error': error
        })

    return {
        'status': 'completed',
        'task_id': task_id,
        'total_files': len(audio_files),
        'success_count': success_count,
        'failed_count': failed_count,
        'success_rate': success_count / len(audio_files) if audio_files else 0,
        'results': results + failed_details
    }


@celery_app.task(name='audio_separator.health_check')
def health_check() -> Dict[str, Any]:
    """
    健康检查任务

    Returns:
        Dict[str, Any]: 健康状态
    """
    try:
        model_manager = get_model_manager()
        health_status = model_manager.health_check()

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
    # 测试任务
    logging.basicConfig(level=logging.INFO)
    print("Audio Separator Tasks 模块加载成功")

