# services/common/context.py
# -*- coding: utf-8 -*-

"""
定义所有工作流任务共享的、标准化的数据结构。

该模块使用 Pydantic 定义了核心的 `WorkflowContext` 模型，确保了在不同服务、
不同任务之间传递的数据拥有一致、可预测且经过验证的结构。
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid

class StageExecution(BaseModel):
    """
    代表工作流中单个阶段的执行状态和结果。
    """
    status: str = Field(..., description="阶段的执行状态 (e.g., PENDING, IN_PROGRESS, SUCCESS, FAILED)")
    output: Dict[str, Any] = Field(default_factory=dict, description="阶段成功执行后的输出数据")
    error: Optional[str] = Field(None, description="如果阶段执行失败，记录错误信息")
    duration: float = Field(0.0, description="阶段执行耗时（秒）")

class WorkflowContext(BaseModel):
    """
    标准化的工作流上下文。

    这个对象在整个工作流的生命周期中被传递和修改，作为所有任务间通信的唯一载体。
    """
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="工作流的唯一标识符")
    input_params: Dict[str, Any] = Field(default_factory=dict, description="从API请求传入的原始参数")
    shared_storage_path: str = Field(..., description="该工作流独有的、用于存放所有中间和最终文件的共享存储根路径")
    
    stages: Dict[str, StageExecution] = Field(default_factory=dict, description="工作流中所有阶段的执行状态和结果的集合")
    execution_summary: Dict[str, Any] = Field(default_factory=dict, description="工作流结束时，各阶段耗时及总耗时的摘要")
    
    error: Optional[str] = Field(None, description="顶层错误信息，当任何阶段失败时，应在此处记录摘要")

    class Config:
        # Pydantic v2 uses `model_config`
        # For older versions, it's `Config`
        # Assuming a version that supports this for broader compatibility
        extra = 'allow' # 允许模型包含未明确声明的字段，以提供灵活性
