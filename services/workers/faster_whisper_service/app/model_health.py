#!/usr/bin/env python3
"""
模型健康检查端点
提供模型状态监控和管理功能
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from app.model_manager import model_manager
from services.common.logger import get_logger

logger = get_logger('model_health')

router = APIRouter()

@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """基础健康检查"""
    try:
        health_status = model_manager.health_check()
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/model/info", response_model=Dict[str, Any])
async def get_model_info():
    """获取模型详细信息"""
    try:
        model_info = model_manager.get_model_info()
        return model_info
    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/reload", response_model=Dict[str, str])
async def reload_models():
    """重新加载模型"""
    try:
        model_manager.unload_models()
        model_manager.ensure_models_loaded()
        return {"status": "success", "message": "Models reloaded successfully"}
    except Exception as e:
        logger.error(f"Failed to reload models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/unload", response_model=Dict[str, str])
async def unload_models():
    """卸载模型"""
    try:
        model_manager.unload_models()
        return {"status": "success", "message": "Models unloaded successfully"}
    except Exception as e:
        logger.error(f"Failed to unload models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/model/usage", response_model=Dict[str, Any])
async def get_model_usage():
    """获取模型使用统计"""
    try:
        # 这里可以添加更详细的使用统计
        model_info = model_manager.get_model_info()
        usage_stats = {
            "asr_model_loaded": model_info['asr_model_loaded'],
            "align_model_loaded": model_info['align_model_loaded'],
            "last_load_time": model_info['last_load_time'],
            "load_failed": model_info['load_failed'],
            "model_config": model_info.get('model_config', {})
        }
        return usage_stats
    except Exception as e:
        logger.error(f"Failed to get model usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))