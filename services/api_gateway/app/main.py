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
from typing import Any, Dict, Optional, Literal, List
from pydantic import model_validator

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

# 导入共享的数据结构
from services.common.context import WorkflowContext, StageExecution

# 导入本服务的核心逻辑模块
from services.common import state_manager
from . import workflow_factory

# --- FastAPI 应用初始化 ---

app = FastAPI(
    title="YiVideo AI Workflow Engine API",
    description="一个用于动态编排AI视频处理工作流的引擎。",
    version="1.1.0"
)

# 导入监控模块
from .monitoring import monitoring_api

# 导入新添加的模块
from .file_operations import get_file_operations_router
from .single_task_api import get_single_task_router
from . import incremental_utils

# 集成监控API路由
monitoring_router = monitoring_api.get_router()
app.include_router(monitoring_router)

# 集成文件操作API路由
file_operations_router = get_file_operations_router()
app.include_router(file_operations_router)

# 集成单任务API路由
single_task_router = get_single_task_router()
app.include_router(single_task_router)

# --- API 请求/响应 模型定义 ---

class WorkflowRequest(BaseModel):
    """工作流请求模型"""
    video_path: Optional[str] = Field(
        None,
        description="视频文件路径。创建新工作流时必需，增量执行时可选"
    )
    workflow_config: Dict[str, Any] = Field(
        ...,
        description="工作流配置字典，必须包含 'workflow_chain' 列表"
    )
    workflow_id: Optional[str] = Field(
        None,
        description="现有工作流的唯一ID。提供此字段时进入增量执行模式"
    )
    execution_mode: Literal["full", "incremental", "retry"] = Field(
        "full",
        description="""
        执行模式：
        - full: 创建全新工作流（默认）
        - incremental: 追加新任务到现有工作流（仅允许尾部追加）
        - retry: 从失败任务开始重新执行
        """
    )
    param_merge_strategy: Literal["merge", "override", "strict"] = Field(
        "merge",
        description="""
        参数合并策略：
        - merge: 智能合并，新参数覆盖旧参数（默认）
        - override: 完全使用新参数，忽略旧参数
        - strict: 检测到参数冲突时报错
        """
    )

    @model_validator(mode='after')
    def validate_execution_mode(self):
        """验证执行模式与参数的一致性"""
        if self.execution_mode == "full":
            if not self.video_path:
                raise ValueError("创建新工作流时 'video_path' 字段为必需")
            if self.workflow_id:
                raise ValueError("创建新工作流时不应提供 'workflow_id'")
        else:
            if not self.workflow_id:
                raise ValueError(f"执行模式 '{self.execution_mode}' 需要提供 'workflow_id'")
        return self

    class Config:
        extra = "allow"

class WorkflowResponse(BaseModel):
    """定义成功创建工作流后的响应模型。"""
    workflow_id: str
    execution_mode: str
    tasks_total: int
    tasks_skipped: int
    tasks_to_execute: int
    message: str

# --- 测试端点定义 ---

@app.get("/test")
@app.post("/test")
async def test_endpoint(request: Request):
    """
    测试端点，打印所有请求的headers和body
    """
    # 获取所有headers
    headers = dict(request.headers)
    
    # 获取请求方法
    method = request.method
    
    # 获取请求URL
    url = str(request.url)
    
    # 获取客户端IP
    client_ip = request.client.host if request.client else "Unknown"
    
    # 记录请求信息
    logger.info(f"收到{method}请求到{url}")
    logger.info(f"客户端IP: {client_ip}")
    logger.info("请求Headers:")
    for key, value in headers.items():
        logger.info(f"  {key}: {value}")
    
    # 获取请求body
    body_content = None
    content_length = 0
    
    try:
        # 尝试读取请求体
        if method in ["POST", "PUT", "PATCH"]:
            # 读取原始body
            body_bytes = await request.body()
            content_length = len(body_bytes)
            
            if content_length > 0:
                # 尝试解码为文本
                try:
                    body_content = body_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    # 如果不是UTF-8，显示为十六进制
                    body_content = body_bytes.hex()
                    
                logger.info(f"请求Body (长度: {content_length} bytes):")
                if content_length > 1024:  # 如果body太长，只显示前1024字符
                    logger.info(f"  {body_content[:1024]}...")
                else:
                    logger.info(f"  {body_content}")
            else:
                logger.info("请求Body: 空")
        else:
            logger.info("GET请求，无Body内容")
            
    except Exception as e:
        logger.error(f"读取请求Body时出错: {e}")
        body_content = f"Error reading body: {str(e)}"
    
    # 返回响应
    return {
        "status": "success",
        "message": "Test endpoint received your request",
        "request_info": {
            "method": method,
            "url": url,
            "client_ip": client_ip,
            "content_length": content_length
        },
        "headers": headers,
        "body": body_content,
        "timestamp": datetime.now().isoformat()
    }

# --- API 端点定义 ---

@app.post("/v1/workflows", response_model=WorkflowResponse, status_code=202)
def create_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    """
    创建或增量执行一个AI处理工作流。
    """
    try:
        if request.execution_mode == "full":
            return _create_new_workflow(request)
        else:
            return _execute_incremental_workflow(request)
    except HTTPException:
        # HTTPException 应该直接向上传播，不做任何处理
        # 这样可以保持原始的状态码（404, 409, 410 等）
        raise
    except ValueError as e:
        # ValueError 通常是业务逻辑错误，返回 400
        logger.error(f"工作流处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 其他未预期的异常，返回 500
        logger.error(f"处理工作流时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

def _create_new_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    """
    处理创建全新工作流的逻辑。
    """
    logger.info(f"接收到新的工作流创建请求: video_path='{request.video_path}', config='{request.workflow_config}'")
    
    workflow_id = str(uuid.uuid4())
    shared_storage_path = f"/share/workflows/{workflow_id}"

    os.makedirs(shared_storage_path, exist_ok=True)
    os.chmod(shared_storage_path, 0o777)
    logger.info(f"已为 workflow_id='{workflow_id}' 创建共享目录: {shared_storage_path}")

    all_params = request.model_dump()
    standard_keys = {"video_path", "workflow_config", "workflow_id", "execution_mode", "param_merge_strategy"}
    node_params = {k: v for k, v in all_params.items() if k not in standard_keys}
    
    workflow_chain_list = request.workflow_config.get("workflow_chain", [])
    if not workflow_chain_list:
        raise ValueError("workflow_config 中的 'workflow_chain' 不能为空")

    initial_context = WorkflowContext(
        workflow_id=workflow_id,
        create_at=datetime.now().isoformat(),
        input_params={
            "video_path": request.video_path,
            "workflow_chain": workflow_chain_list,
            "node_params": node_params
        },
        shared_storage_path=shared_storage_path,
        stages={},
        error=None
    )

    state_manager.create_workflow_state(initial_context)

    workflow_chain = workflow_factory.build_workflow_chain(
        workflow_config=request.workflow_config,
        initial_context=initial_context.model_dump()
    )

    workflow_chain.apply_async()
    logger.info(f"正在为 workflow_id='{workflow_id}' 启动任务链...")

    return {
        "workflow_id": workflow_id,
        "execution_mode": "full",
        "tasks_total": len(workflow_chain_list),
        "tasks_skipped": 0,
        "tasks_to_execute": len(workflow_chain_list),
        "message": "New workflow created and started successfully."
    }

def _execute_incremental_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    """
    处理增量执行或重试工作流的逻辑。
    """
    workflow_id = request.workflow_id
    logger.info(f"接收到增量执行请求: workflow_id='{workflow_id}', mode='{request.execution_mode}'")

    # 获取分布式锁，防止并发修改
    lock_value = incremental_utils.acquire_workflow_lock(workflow_id)
    if not lock_value:
        raise HTTPException(status_code=409, detail="工作流正在被另一个请求修改，请稍后重试")

    try:
        existing_state = state_manager.get_workflow_state(workflow_id)
        # 修复：只有当工作流状态真正不存在时才报错
        # 不应该因为有error字段就认为工作流不存在，失败的工作流也应该可以重试
        if not existing_state:
            raise HTTPException(status_code=404, detail=f"工作流 '{workflow_id}' 不存在")

        # 如果工作流存在但有错误，仍然允许重试
        if existing_state.get("error"):
            logger.info(f"工作流 '{workflow_id}' 存在但之前有错误，允许重试: {existing_state.get('error')}")

        existing_context = WorkflowContext(**existing_state)
        
        if not os.path.exists(existing_context.shared_storage_path):
            raise HTTPException(status_code=410, detail=f"工作流存储目录不存在: {existing_context.shared_storage_path}")

        old_chain = existing_context.input_params.get("workflow_chain", [])
        new_chain = request.workflow_config.get("workflow_chain", [])
        if not new_chain:
            raise ValueError("workflow_config 中的 'workflow_chain' 不能为空")

        diff_result = incremental_utils.compute_workflow_diff(
            old_chain=old_chain,
            new_chain=new_chain,
            existing_stages=existing_context.stages,
            mode=request.execution_mode
        )

        all_params = request.model_dump()
        standard_keys = {"video_path", "workflow_config", "workflow_id", "execution_mode", "param_merge_strategy"}
        new_node_params = {k: v for k, v in all_params.items() if k not in standard_keys}

        merged_params = incremental_utils.merge_node_params(
            old_params=existing_context.input_params.get("node_params", {}),
            new_params=new_node_params,
            strategy=request.param_merge_strategy
        )

        existing_context.input_params["workflow_chain"] = new_chain
        existing_context.input_params["node_params"] = merged_params

        if not diff_result.tasks_to_execute:
            logger.info(f"工作流 '{workflow_id}' 所有任务已完成，无需执行。")
            return {
                "workflow_id": workflow_id,
                "execution_mode": request.execution_mode,
                "tasks_total": len(new_chain),
                "tasks_skipped": len(diff_result.tasks_to_skip),
                "tasks_to_execute": 0,
                "message": "All tasks already completed, no execution needed."
            }

        incremental_config = {"workflow_chain": diff_result.tasks_to_execute}
        workflow_chain = workflow_factory.build_workflow_chain(
            workflow_config=incremental_config,
            initial_context=existing_context.model_dump()
        )

        state_manager.update_workflow_state(existing_context)
        
        # 推荐：重置TTL
        if state_manager.redis_client:
            state_manager.redis_client.expire(f"workflow_state:{workflow_id}", state_manager.WORKFLOW_TTL_SECONDS)
            logger.info(f"已重置工作流 TTL: {workflow_id}")

        workflow_chain.apply_async()
        logger.info(f"已为 workflow_id='{workflow_id}' 提交增量任务链: {diff_result.tasks_to_execute}")

        return {
            "workflow_id": workflow_id,
            "execution_mode": request.execution_mode,
            "tasks_total": len(new_chain),
            "tasks_skipped": len(diff_result.tasks_to_skip),
            "tasks_to_execute": len(diff_result.tasks_to_execute),
            "message": "Incremental execution started successfully."
        }
    finally:
        # 安全释放锁：使用获取锁时得到的 lock_value
        incremental_utils.release_workflow_lock(workflow_id, lock_value)


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