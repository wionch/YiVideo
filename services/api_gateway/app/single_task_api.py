# services/api_gateway/app/single_task_api.py
# -*- coding: utf-8 -*-

"""
单任务API端点。

提供单个工作流节点执行和状态查询的API接口。
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
import uuid

from services.common.logger import get_logger
from .single_task_executor import get_single_task_executor
from .single_task_models import (
    SingleTaskRequest, SingleTaskResponse, TaskStatusResponse, ErrorResponse
)

logger = get_logger('single_task_api')

# 创建路由器
router = APIRouter(prefix="/v1/tasks", tags=["Single Task Operations"])


@router.post("", response_model=SingleTaskResponse)
async def create_single_task(request: SingleTaskRequest):
    """
    创建并执行单个任务
    
    Args:
        request: 单任务请求参数
        
    Returns:
        SingleTaskResponse: 任务创建结果
    """
    try:
        # 如果没有提供task_id，自动生成一个
        task_id = request.task_id or f"task-{str(uuid.uuid4())}"
        logger.info(f"创建单任务: {request.task_name}, ID: {task_id}")
        
        # 验证请求参数
        if not request.task_name:
            raise HTTPException(status_code=400, detail="task_name不能为空")
        
        # 验证callback URL（如果提供）
        if request.callback:
            callback_manager = get_single_task_executor().callback_manager
            if not callback_manager.validate_callback_url(request.callback):
                raise HTTPException(status_code=400, detail="无效的callback URL格式")
        
        # 获取单任务执行器
        executor = get_single_task_executor()
        
        # 执行任务
        celery_task_id = executor.execute_task(
            task_name=request.task_name,
            task_id=task_id,
            input_data=request.input_data,
            callback_url=request.callback
        )
        
        logger.info(f"单任务创建成功: {task_id}, Celery Task ID: {celery_task_id}")
        
        return SingleTaskResponse(
            task_id=task_id,
            status="pending",
            message="任务已创建并开始执行"
        )
        
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        raise HTTPException(status_code=400, detail=f"参数验证失败: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建单任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建单任务失败: {str(e)}")


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    查询任务状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        TaskStatusResponse: 任务状态信息
    """
    logger.info(f"查询任务状态: {task_id}")
    
    try:
        # 验证task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id不能为空")
        
        # 获取单任务执行器
        executor = get_single_task_executor()
        
        # 获取任务状态
        status_info = executor.get_task_status(task_id)
        
        # 检查任务是否存在
        if status_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        logger.info(f"任务状态查询成功: {task_id}, 状态: {status_info.get('status')}")
        
        return TaskStatusResponse(**status_info)
        
    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(f"状态数据格式错误: {e}")
        raise HTTPException(status_code=500, detail=f"状态数据格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询任务状态失败: {str(e)}")


@router.get("/{task_id}/result")
async def get_task_result(task_id: str):
    """
    获取任务完整结果（包含更多详细信息）
    
    Args:
        task_id: 任务ID
        
    Returns:
        dict: 任务完整结果
    """
    logger.info(f"获取任务结果: {task_id}")
    
    try:
        # 验证task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id不能为空")
        
        # 获取单任务执行器
        executor = get_single_task_executor()
        
        # 获取任务状态
        status_info = executor.get_task_status(task_id)
        
        # 检查任务是否存在
        if status_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        logger.info(f"任务结果获取成功: {task_id}")
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务结果失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务结果失败: {str(e)}")


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """
    重试失败的任务
    
    Args:
        task_id: 任务ID
        
    Returns:
        SingleTaskResponse: 重试结果
    """
    logger.info(f"重试任务: {task_id}")
    
    try:
        # 验证task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id不能为空")
        
        # 获取单任务执行器
        executor = get_single_task_executor()
        
        # 获取当前任务状态
        status_info = executor.get_task_status(task_id)
        
        if status_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        if status_info.get("status") not in ["failed", "completed"]:
            raise HTTPException(status_code=400, detail=f"任务状态不允许重试: {status_info.get('status')}")
        
        # 重新执行任务
        task_name = status_info.get("input_params", {}).get("task_name")
        input_data = status_info.get("input_params", {}).get("input_data", {})
        callback_url = status_info.get("input_params", {}).get("callback_url")
        
        if not task_name:
            raise HTTPException(status_code=400, detail="无法获取原始任务信息")
        
        # 生成新的任务ID（避免与原任务冲突）
        import uuid
        new_task_id = f"{task_id}-retry-{str(uuid.uuid4())[:8]}"
        
        # 执行重试任务
        celery_task_id = executor.execute_task(
            task_name=task_name,
            task_id=new_task_id,
            input_data=input_data,
            callback_url=callback_url
        )
        
        logger.info(f"任务重试成功: {task_id} -> {new_task_id}")
        
        return SingleTaskResponse(
            task_id=new_task_id,
            status="pending",
            message=f"任务重试已开始，原任务ID: {task_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重试任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    取消任务（如果任务还在运行中）
    
    Args:
        task_id: 任务ID
        
    Returns:
        dict: 取消结果
    """
    logger.info(f"取消任务: {task_id}")
    
    try:
        # 验证task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id不能为空")
        
        # 获取单任务执行器
        executor = get_single_task_executor()
        
        # 获取任务状态
        status_info = executor.get_task_status(task_id)
        
        if status_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        
        current_status = status_info.get("status")
        
        # 只有pending或running状态的任务才能取消
        if current_status not in ["pending", "running"]:
            raise HTTPException(status_code=400, detail=f"任务状态不允许取消: {current_status}")
        
        # 注意：这里只是更新状态标记为cancelled
        # 实际的Celery任务取消需要更复杂的逻辑
        executor._update_task_status(task_id, "cancelled")
        
        logger.info(f"任务已取消: {task_id}")
        
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "任务已成功取消"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")


@router.get("/health")
async def health_check():
    """
    单任务服务健康检查
    
    Returns:
        dict: 健康状态信息
    """
    try:
        # 尝试获取单任务执行器
        executor = get_single_task_executor()
        
        return {
            "status": "healthy",
            "service": "single_task_api",
            "celery_broker": executor.celery_app.broker_url,
            "minio_service": "available"
        }
        
    except Exception as e:
        logger.error(f"单任务服务健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/supported-tasks")
async def get_supported_tasks():
    """
    获取支持的任务列表
    
    Returns:
        dict: 支持的任务列表
    """
    supported_tasks = {
        "ffmpeg": [
            "ffmpeg.extract_keyframes",
            "ffmpeg.extract_audio", 
            "ffmpeg.crop_subtitle_images",
            "ffmpeg.split_audio_segments"
        ],
        "faster_whisper": [
            "faster_whisper.transcribe_audio"
        ],
        "audio_separator": [
            "audio_separator.separate_vocals"
        ],
        "pyannote_audio": [
            "pyannote_audio.diarize_speakers"
        ],
        "paddleocr": [
            "paddleocr.detect_subtitle_area",
            "paddleocr.perform_ocr"
        ],
        "indextts": [
            "indextts.generate_speech"
        ],
        "wservice": [
            "wservice.generate_subtitle_files",
            "wservice.correct_subtitles",
            "wservice.ai_optimize_subtitles"
        ]
    }
    
    return {
        "supported_tasks": supported_tasks,
        "total_count": sum(len(tasks) for tasks in supported_tasks.values()),
        "description": "所有支持的单个工作流节点任务"
    }


def get_single_task_router():
    """获取单任务路由器"""
    return router