# services/api_gateway/app/main.py
# -*- coding: utf-8 -*-

"""
API Gateway的主应用文件。

使用FastAPI创建Web服务，提供工作流的创建和状态查询端点。
"""

import os

from services.common.logger import get_logger

logger = get_logger('main')
import logging
import uuid
from datetime import datetime
from typing import Any
from typing import Dict

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import Field

# 导入共享的数据结构
from services.common.context import WorkflowContext

# 导入本服务的核心逻辑模块
from . import state_manager
from . import workflow_factory

# 导入监控模块
from .monitoring import monitoring_api

# --- FastAPI 应用初始化 ---

app = FastAPI(
    title="YiVideo AI Workflow Engine API",
    description="一个用于动态编排AI视频处理工作流的引擎。",
    version="1.0.0"
)

# 集成监控API路由
monitoring_router = monitoring_api.get_router()
app.include_router(monitoring_router)

# 日志已统一管理，使用 services.common.logger

# --- API 请求/响应 模型定义 ---

class WorkflowRequest(BaseModel):
    """定义创建工作流请求的Body模型。"""
    video_path: str = Field(..., description="待处理视频在共享存储中的绝对路径，例如 '/share/videos/example.mp4'")
    workflow_config: Dict[str, Any] = Field(..., description='定义工作流具体行为的配置字典，例如 {"workflow_chain": ["task1", "task2"]}')

class WorkflowResponse(BaseModel):
    """定义成功创建工作流后的响应模型。"""
    workflow_id: str

# --- API 端点定义 ---

@app.post("/v1/workflows", response_model=WorkflowResponse, status_code=202)
def create_workflow(request: WorkflowRequest) -> Dict[str, str]:
    """
    创建并启动一个新的AI处理工作流。
    """
    logger.info(f"接收到新的工作流请求: video_path='{request.video_path}', config='{request.workflow_config}'")
    
    workflow_id = str(uuid.uuid4())
    shared_storage_path = f"/share/workflows/{workflow_id}"

    try:
        # 关键步骤：确保工作流的独立目录存在
        os.makedirs(shared_storage_path, exist_ok=True)
        os.chmod(shared_storage_path, 0o777) # 赋予777权限，允许任何worker服务写入
        logger.info(f"已为 workflow_id='{workflow_id}' 创建共享目录: {shared_storage_path}")

        # 1. 创建初始工作流上下文
        initial_context = WorkflowContext(
            workflow_id=workflow_id,
            create_at=datetime.now().isoformat(),
            input_params={"video_path": request.video_path, **request.workflow_config},
            shared_storage_path=shared_storage_path,
            stages={},
            error=None
        )

        # 2. 持久化初始状态到Redis
        state_manager.create_workflow_state(initial_context)

        # 3. 调用工厂，根据配置构建任务链
        workflow_chain = workflow_factory.build_workflow_chain(
            workflow_config=request.workflow_config,
            initial_context=initial_context.model_dump()
        )

        # 4. 异步执行任务链
        logger.info(f"正在为 workflow_id='{workflow_id}' 启动任务链...")
        workflow_chain.apply_async()

        # 5. 立即返回，表示请求已被接受处理
        return {"workflow_id": workflow_id}

    except ValueError as e:
        logger.error(f"工作流构建失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建工作流时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while creating the workflow.")


@app.get("/v1/workflows/status/{workflow_id}", response_model=Dict[str, Any])
def get_workflow_status(workflow_id: str) -> Dict[str, Any]:
    """
    查询一个工作流的当前状态。
    """
    logger.info(f"正在查询 workflow_id='{workflow_id}' 的状态...")
    state = state_manager.get_workflow_state(workflow_id)
    
    if state.get("error"):
        raise HTTPException(status_code=404, detail=state["error"])
        
    return state

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("正在初始化API Gateway...")

    try:
        # 初始化监控服务
        monitoring_api.initialize_monitoring()
        logger.info("监控服务初始化完成")
    except Exception as e:
        logger.error(f"监控服务初始化失败: {e}")

    logger.info("API Gateway 初始化完成")


@app.get("/", include_in_schema=False)
def root():
    """根路径，用于简单的健康检查。"""
    return {"message": "YiVideo AI Workflow Engine API is running."}