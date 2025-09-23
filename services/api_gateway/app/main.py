# services/api_gateway/app/main.py
# -*- coding: utf-8 -*-

"""
API Gateway的主应用文件。

使用FastAPI创建Web服务，提供工作流的创建和状态查询端点。
"""

import os
import uuid
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any

# 导入本服务的核心逻辑模块
from . import state_manager
from . import workflow_factory

# 导入共享的数据结构
from services.common.context import WorkflowContext

# --- FastAPI 应用初始化 ---

app = FastAPI(
    title="YiVideo AI Workflow Engine API",
    description="一个用于动态编排AI视频处理工作流的引擎。",
    version="1.0.0"
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    logging.info(f"接收到新的工作流请求: video_path='{request.video_path}', config='{request.workflow_config}'")
    
    workflow_id = str(uuid.uuid4())
    shared_storage_path = f"/share/workflows/{workflow_id}"

    try:
        # 关键步骤：确保工作流的独立目录存在
        os.makedirs(shared_storage_path, exist_ok=True)
        os.chmod(shared_storage_path, 0o777) # 赋予777权限，允许任何worker服务写入
        logging.info(f"已为 workflow_id='{workflow_id}' 创建共享目录: {shared_storage_path}")

        # 1. 创建初始工作流上下文
        initial_context = WorkflowContext(
            workflow_id=workflow_id,
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
        logging.info(f"正在为 workflow_id='{workflow_id}' 启动任务链...")
        workflow_chain.apply_async()

        # 5. 立即返回，表示请求已被接受处理
        return {"workflow_id": workflow_id}

    except ValueError as e:
        logging.error(f"工作流构建失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"创建工作流时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while creating the workflow.")


@app.get("/v1/workflows/status/{workflow_id}", response_model=Dict[str, Any])
def get_workflow_status(workflow_id: str) -> Dict[str, Any]:
    """
    查询一个工作流的当前状态。
    """
    logging.info(f"正在查询 workflow_id='{workflow_id}' 的状态...")
    state = state_manager.get_workflow_state(workflow_id)
    
    if state.get("error"):
        raise HTTPException(status_code=404, detail=state["error"])
        
    return state

@app.get("/", include_in_schema=False)
def root():
    """根路径，用于简单的健康检查。"""
    return {"message": "YiVideo AI Workflow Engine API is running."}