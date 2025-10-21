# services/api_gateway/app/monitoring/api_endpoints.py
# -*- coding: utf-8 -*-

"""
监控API端点

提供GPU锁监控相关的REST API接口。
"""

import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .gpu_lock_monitor import get_gpu_monitor
from .heartbeat_manager import get_heartbeat_manager
from .timeout_manager import get_timeout_manager
from services.common.locks import get_gpu_lock_status, get_gpu_lock_health_summary, release_gpu_lock

# 创建路由器
router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


# --- 请求/响应模型 ---

class LockStatusResponse(BaseModel):
    """锁状态响应模型"""
    lock_key: str
    is_locked: bool
    lock_holder: Optional[str]
    ttl_seconds: Optional[int]
    timestamp: float
    health: Dict[str, Any]
    statistics: Dict[str, Any]
    recent_history: list
    lock_type: str
    lock_age: Optional[float]


class LockHealthResponse(BaseModel):
    """锁健康状态响应模型"""
    overall_status: str
    issues_count: int
    total_attempts: int
    success_rate: float
    timeout_rate: float
    average_execution_time: float
    recent_success_rate: float
    lock_holder: Optional[str]
    lock_age: Optional[float]
    timestamp: float


class MonitorStatusResponse(BaseModel):
    """监控器状态响应模型"""
    monitor_status: Dict[str, Any]
    monitor_stats: Dict[str, Any]
    config: Dict[str, Any]
    is_running: bool
    uptime: float


class MonitorHealthResponse(BaseModel):
    """监控器健康状态响应模型"""
    status: str
    issues: list
    metrics: Dict[str, Any]
    timestamp: float


class HeartbeatStatusResponse(BaseModel):
    """心跳状态响应模型"""
    task_id: str
    heartbeat_exists: bool
    is_registered: bool
    status: str
    heartbeat_data: Optional[Dict[str, Any]] = None
    last_update: Optional[float] = None
    is_running: Optional[bool] = None


class AllHeartbeatsResponse(BaseModel):
    """所有心跳状态响应模型"""
    active_tasks: Dict[str, Dict[str, Any]]
    dead_tasks: list
    orphaned_tasks: list
    statistics: Dict[str, Any]
    timestamp: float


class TimeoutStatusResponse(BaseModel):
    """超时状态响应模型"""
    timeout_stats: Dict[str, Any]
    action_history: list
    configured_actions: list
    timestamp: float


class ManualReleaseRequest(BaseModel):
    """手动释放锁请求模型"""
    lock_key: str = Field(..., description="锁键")
    task_name: str = Field("manual", description="任务名称")


class ManualReleaseResponse(BaseModel):
    """手动释放锁响应模型"""
    success: bool
    message: str
    lock_key: str
    task_name: str


# --- API端点 ---

@router.get("/gpu-lock/status", response_model=LockStatusResponse)
async def get_gpu_lock_status_endpoint(
    lock_key: str = Query("gpu_lock:0", description="锁键")
):
    """获取GPU锁状态"""
    try:
        lock_status = get_gpu_lock_status(lock_key)
        if 'error' in lock_status:
            raise HTTPException(status_code=500, detail=lock_status['error'])
        return lock_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gpu-lock/health", response_model=LockHealthResponse)
async def get_gpu_lock_health_endpoint():
    """获取GPU锁健康状态摘要"""
    try:
        health_summary = get_gpu_lock_health_summary()
        if 'error' in health_summary:
            raise HTTPException(status_code=500, detail=health_summary['error'])
        return health_summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/status", response_model=MonitorStatusResponse)
async def get_monitor_status_endpoint():
    """获取监控器状态"""
    try:
        monitor = get_gpu_monitor()
        monitor_status = monitor.get_monitor_status()
        return monitor_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/health", response_model=MonitorHealthResponse)
async def get_monitor_health_endpoint():
    """获取监控器健康状态"""
    try:
        monitor = get_gpu_monitor()
        monitor_health = monitor.get_monitor_health()
        return monitor_health
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitor/start")
async def start_monitor_endpoint():
    """启动监控器"""
    try:
        monitor = get_gpu_monitor()
        monitor.start_monitoring()
        return {"message": "监控器已启动", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitor/stop")
async def stop_monitor_endpoint():
    """停止监控器"""
    try:
        monitor = get_gpu_monitor()
        monitor.stop_monitoring()
        return {"message": "监控器已停止", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heartbeat/task/{task_id}", response_model=HeartbeatStatusResponse)
async def get_task_heartbeat_endpoint(task_id: str):
    """获取指定任务的心跳状态"""
    try:
        heartbeat_manager = get_heartbeat_manager()
        heartbeat_info = heartbeat_manager.check_task_heartbeat(task_id)
        return heartbeat_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heartbeat/all", response_model=AllHeartbeatsResponse)
async def get_all_heartbeats_endpoint():
    """获取所有任务的心跳状态"""
    try:
        heartbeat_manager = get_heartbeat_manager()
        all_heartbeats = heartbeat_manager.check_all_heartbeats()
        return all_heartbeats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/task/{task_id}/start")
async def start_task_heartbeat_endpoint(task_id: str):
    """启动任务心跳"""
    try:
        from .heartbeat_manager import start_task_heartbeat
        heartbeat = start_task_heartbeat(task_id)
        if heartbeat:
            return {"message": f"任务 {task_id} 心跳已启动", "success": True}
        else:
            raise HTTPException(status_code=500, detail="启动心跳失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/heartbeat/task/{task_id}")
async def stop_task_heartbeat_endpoint(task_id: str):
    """停止任务心跳"""
    try:
        from .heartbeat_manager import stop_task_heartbeat
        stop_task_heartbeat(task_id)
        return {"message": f"任务 {task_id} 心跳已停止", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/cleanup")
async def cleanup_heartbeats_endpoint():
    """清理死任务和孤立心跳"""
    try:
        heartbeat_manager = get_heartbeat_manager()

        # 清理死任务
        dead_count = len(heartbeat_manager.check_all_heartbeats().get('dead_tasks', []))
        heartbeat_manager.cleanup_dead_tasks()

        # 清理孤立心跳
        heartbeat_manager.cleanup_orphaned_heartbeats()

        return {
            "message": "心跳清理完成",
            "success": True,
            "cleaned_dead_tasks": dead_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeout/status", response_model=TimeoutStatusResponse)
async def get_timeout_status_endpoint():
    """获取超时处理状态"""
    try:
        timeout_manager = get_timeout_manager()
        timeout_status = timeout_manager.get_timeout_status()
        return timeout_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeout/config")
async def get_timeout_config_endpoint():
    """获取超时配置"""
    try:
        timeout_manager = get_timeout_manager()
        timeout_config = timeout_manager.get_timeout_config()
        return timeout_config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/timeout/check")
async def check_timeouts_endpoint(
    lock_key: str = Query("gpu_lock:0", description="锁键")
):
    """检查并处理超时"""
    try:
        from .timeout_manager import check_lock_timeouts
        timeout_result = check_lock_timeouts(lock_key)
        return timeout_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lock/release", response_model=ManualReleaseResponse)
async def manual_release_lock_endpoint(request: ManualReleaseRequest):
    """手动释放GPU锁"""
    try:
        success = release_gpu_lock(request.lock_key, request.task_name)
        if success:
            return ManualReleaseResponse(
                success=True,
                message=f"锁 {request.lock_key} 已成功释放",
                lock_key=request.lock_key,
                task_name=request.task_name
            )
        else:
            return ManualReleaseResponse(
                success=False,
                message=f"释放锁 {request.lock_key} 失败",
                lock_key=request.lock_key,
                task_name=request.task_name
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_monitoring_statistics_endpoint():
    """获取监控统计信息"""
    try:
        # 收集各个组件的统计信息
        stats = {
            "timestamp": time.time(),
            "gpu_lock": get_gpu_lock_health_summary(),
            "monitor": get_gpu_monitor().get_monitor_status(),
            "heartbeat": get_heartbeat_manager().get_statistics(),
            "timeout": get_timeout_manager().get_timeout_status()
        }
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_monitoring_health_endpoint():
    """获取监控服务健康状态"""
    try:
        # 检查各个组件的健康状态
        monitor_health = get_gpu_monitor().get_monitor_health()
        heartbeat_stats = get_heartbeat_manager().get_statistics()

        # 计算整体健康状态
        overall_status = "healthy"
        issues = []

        if monitor_health['status'] != "healthy":
            overall_status = "warning"
            issues.extend(monitor_health['issues'])

        if heartbeat_stats.get('failure_rate', 0) > 0.1:
            overall_status = "warning"
            issues.append("心跳故障率过高")

        return {
            "status": overall_status,
            "issues": issues,
            "components": {
                "monitor": monitor_health,
                "heartbeat": heartbeat_stats
            },
            "timestamp": time.time()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 监控API类 ---

class MonitoringAPI:
    """监控API管理类"""

    def __init__(self):
        self.router = router

    def get_router(self) -> APIRouter:
        """获取路由器"""
        return self.router

    def initialize_monitoring(self):
        """初始化监控服务"""
        try:
            # 启动GPU锁监控
            monitor = get_gpu_monitor()
            if monitor.config.get('enabled', True):
                monitor.start_monitoring()
                print("GPU锁监控器已启动")

            print("监控API初始化完成")
        except Exception as e:
            print(f"监控API初始化失败: {e}")


# 全局监控API实例
monitoring_api = MonitoringAPI()