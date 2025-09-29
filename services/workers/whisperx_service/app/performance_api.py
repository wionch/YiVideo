#!/usr/bin/env python3
"""
性能监控 API 端点
提供性能指标查询和监控功能
"""

import time
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging

from app.performance_monitoring import (
    performance_monitor, get_performance_summary,
    get_performance_insights, export_performance_metrics
)
from services.common.logger import get_logger

logger = get_logger('performance_api')

router = APIRouter()

@router.get("/performance/summary", response_model=Dict[str, Any])
async def get_performance_summary_endpoint(
    operation: Optional[str] = Query(None, description="操作名称")
):
    """获取性能摘要"""
    try:
        summary = get_performance_summary(operation)
        return {
            "success": True,
            "data": summary,
            "timestamp": performance_monitor.get_system_health().get("timestamp")
        }
    except Exception as e:
        logger.error(f"获取性能摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance/insights", response_model=Dict[str, Any])
async def get_performance_insights_endpoint(
    operation: Optional[str] = Query(None, description="操作名称")
):
    """获取性能洞察"""
    try:
        insights = get_performance_insights(operation)
        return {
            "success": True,
            "data": insights,
            "timestamp": performance_monitor.get_system_health().get("timestamp")
        }
    except Exception as e:
        logger.error(f"获取性能洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance/metrics", response_model=Dict[str, Any])
async def get_performance_metrics(
    operation: Optional[str] = Query(None, description="操作名称"),
    minutes: int = Query(60, description="查询时间范围(分钟)", ge=1, le=1440),
    limit: int = Query(100, description="返回结果数量限制", ge=1, le=1000)
):
    """获取性能指标"""
    try:
        metrics = performance_monitor.get_recent_metrics(operation, minutes)

        # 限制返回数量
        if len(metrics) > limit:
            metrics = metrics[-limit:]

        # 转换为字典格式
        metrics_data = []
        for metric in metrics:
            metrics_data.append({
                "timestamp": metric.timestamp,
                "operation": metric.operation,
                "duration": metric.duration,
                "memory_usage_mb": metric.memory_usage_mb,
                "cpu_usage_percent": metric.cpu_usage_percent,
                "gpu_memory_usage_mb": metric.gpu_memory_usage_mb,
                "batch_size": metric.batch_size,
                "audio_duration": metric.audio_duration,
                "success": metric.success,
                "error_message": metric.error_message,
                "context": metric.context
            })

        return {
            "success": True,
            "data": {
                "metrics": metrics_data,
                "total_count": len(metrics_data),
                "time_range_minutes": minutes,
                "operation_filter": operation
            },
            "timestamp": performance_monitor.get_system_health().get("timestamp")
        }
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance/system-health", response_model=Dict[str, Any])
async def get_system_health():
    """获取系统健康状态"""
    try:
        system_health = performance_monitor.get_system_health()
        return {
            "success": True,
            "data": system_health
        }
    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance/operations", response_model=List[str])
async def get_available_operations():
    """获取所有可用的操作列表"""
    try:
        summaries = performance_monitor.get_all_summaries()
        operations = list(summaries.keys())
        return operations
    except Exception as e:
        logger.error(f"获取操作列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/performance/export", response_model=Dict[str, str])
async def export_performance_data(
    format: str = Query("json", description="导出格式", regex="^(json|csv)$")
):
    """导出性能数据"""
    try:
        timestamp = int(time.time())
        filename = f"performance_metrics_{timestamp}.{format}"
        filepath = f"/tmp/{filename}"

        export_performance_metrics(filepath, format)

        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "format": format,
            "timestamp": timestamp
        }
    except Exception as e:
        logger.error(f"导出性能数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/performance/clear", response_model=Dict[str, str])
async def clear_performance_history():
    """清空性能历史记录"""
    try:
        performance_monitor.clear_history()
        return {
            "success": True,
            "message": "性能历史记录已清空"
        }
    except Exception as e:
        logger.error(f"清空性能历史记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/performance/monitoring/{action}", response_model=Dict[str, str])
async def control_monitoring(action: str):
    """控制性能监控开关"""
    try:
        if action == "enable":
            performance_monitor.enable_monitoring()
            message = "性能监控已启用"
        elif action == "disable":
            performance_monitor.disable_monitoring()
            message = "性能监控已禁用"
        else:
            raise HTTPException(status_code=400, detail="无效的操作，必须是 'enable' 或 'disable'")

        return {
            "success": True,
            "message": message,
            "action": action
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"控制性能监控失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance/dashboard", response_model=Dict[str, Any])
async def get_performance_dashboard():
    """获取性能仪表板数据"""
    try:
        # 获取系统健康状态
        system_health = performance_monitor.get_system_health()

        # 获取所有操作摘要
        summaries = performance_monitor.get_all_summaries()

        # 获取性能洞察
        insights = get_performance_insights()

        # 获取最近的性能指标
        recent_metrics = performance_monitor.get_recent_metrics(minutes=30)  # 最近30分钟

        # 计算总体统计
        total_operations = sum(s.total_operations for s in summaries.values())
        total_success = sum(s.successful_operations for s in summaries.values())
        overall_success_rate = (total_success / total_operations * 100) if total_operations > 0 else 0

        dashboard_data = {
            "system_health": system_health,
            "overall_stats": {
                "total_operations": total_operations,
                "total_success": total_success,
                "overall_success_rate": round(overall_success_rate, 2),
                "active_operations": len(summaries),
                "recent_metrics_count": len(recent_metrics)
            },
            "operation_summaries": {
                op: {
                    "total_operations": s.total_operations,
                    "successful_operations": s.successful_operations,
                    "failed_operations": s.failed_operations,
                    "success_rate": round(s.success_rate, 2),
                    "average_duration": round(s.average_duration, 2),
                    "peak_memory_usage": round(s.peak_memory_usage, 2),
                    "throughput_per_minute": s.throughput_per_minute
                }
                for op, s in summaries.items()
            },
            "insights": insights,
            "recent_performance": [
                {
                    "timestamp": m.timestamp,
                    "operation": m.operation,
                    "duration": round(m.duration, 2),
                    "memory_usage_mb": round(m.memory_usage_mb, 2),
                    "success": m.success
                }
                for m in recent_metrics[-50:]  # 最近50条记录
            ]
        }

        return {
            "success": True,
            "data": dashboard_data,
            "timestamp": system_health.get("timestamp")
        }
    except Exception as e:
        logger.error(f"获取性能仪表板数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # 测试API端点
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/v1", tags=["performance"])

    uvicorn.run(app, host="0.0.0.0", port=8001)