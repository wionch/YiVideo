# services/api_gateway/app/single_task_models.py
# -*- coding: utf-8 -*-

"""
单任务API模型定义。

定义单任务接口使用的所有Pydantic模型。
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SingleTaskRequest(BaseModel):
    """单任务请求模型"""
    task_name: str = Field(..., description="工作流节点名称，如 'ffmpeg.extract_audio'")
    task_id: Optional[str] = Field(None, description="任务唯一标识符，如不提供将自动生成")
    callback: Optional[str] = Field(None, description="任务完成后回调的URL")
    input_data: Dict[str, Any] = Field(..., description="任务输入数据")


class SingleTaskResponse(BaseModel):
    """单任务响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: str = Field(..., description="状态消息")


class TaskStatusResponse(BaseModel):
    """任务状态查询响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: str = Field(..., description="状态消息")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果数据")
    minio_files: Optional[List[Dict[str, str]]] = Field(None, description="MinIO文件信息列表")
    create_at: Optional[str] = Field(None, description="任务创建时间（保持与WorkflowContext字段一致）")
    created_at: Optional[str] = Field(None, description="任务创建时间")
    updated_at: Optional[str] = Field(None, description="任务更新时间")
    callback_status: Optional[str] = Field(None, description="callback发送状态")


class FileInfo(BaseModel):
    """文件信息模型"""
    name: str = Field(..., description="文件名")
    url: str = Field(..., description="下载URL")
    type: str = Field(..., description="文件类型")
    size: Optional[int] = Field(None, description="文件大小")


class CallbackResult(BaseModel):
    """Callback结果模型"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态：completed 或 failed")
    result: Dict[str, Any] = Field(..., description="任务执行结果数据")
    minio_files: Optional[List[Dict[str, str]]] = Field(None, description="MinIO文件信息列表")
    timestamp: str = Field(..., description="时间戳")


# 文件操作相关的模型
class FileUploadRequest(BaseModel):
    """文件上传请求模型"""
    file_path: str = Field(..., description="文件在MinIO中的路径")
    bucket: Optional[str] = Field("yivideo", description="文件桶名称")


class FileUploadResponse(BaseModel):
    """文件上传响应模型"""
    file_path: str = Field(..., description="文件路径")
    bucket: str = Field(..., description="文件桶")
    download_url: str = Field(..., description="下载链接")
    size: int = Field(..., description="文件大小")
    uploaded_at: str = Field(..., description="上传时间")
    content_type: Optional[str] = Field(None, description="文件MIME类型")


class FileOperationResponse(BaseModel):
    """文件操作响应模型"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")
    file_path: Optional[str] = Field(None, description="文件路径")
    file_size: Optional[int] = Field(None, description="文件大小")


class FileListItem(BaseModel):
    """文件列表项模型"""
    file_path: str = Field(..., description="文件路径")
    size: int = Field(..., description="文件大小")
    last_modified: Optional[str] = Field(None, description="最后修改时间")
    etag: Optional[str] = Field(None, description="文件ETag")
    content_type: Optional[str] = Field(None, description="文件MIME类型")


class FileListResponse(BaseModel):
    """文件列表响应模型"""
    prefix: str = Field(..., description="查询前缀")
    bucket: str = Field(..., description="文件桶")
    files: List[FileListItem] = Field(..., description="文件列表")
    total_count: int = Field(..., description="文件总数")


class DeletionResource(str, Enum):
    """删除资源类型"""
    LOCAL_DIRECTORY = "local_directory"
    REDIS = "redis"
    MINIO = "minio"


class DeletionResourceStatus(str, Enum):
    """删除资源处理结果"""
    DELETED = "deleted"
    SKIPPED = "skipped"
    FAILED = "failed"


class TaskDeletionRequest(BaseModel):
    """任务删除请求"""
    force: bool = Field(False, description="是否强制删除运行/排队中的任务")


class ResourceDeletionItem(BaseModel):
    """分资源删除结果"""
    resource: DeletionResource = Field(..., description="资源类型")
    status: DeletionResourceStatus = Field(..., description="处理结果")
    message: Optional[str] = Field(None, description="补充说明")
    retriable: Optional[bool] = Field(None, description="是否建议重试")
    details: Optional[Dict[str, Any]] = Field(None, description="附加信息，如删除对象列表或错误代码")


class TaskDeletionStatus(str, Enum):
    """任务删除整体状态"""
    SUCCESS = "success"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class TaskDeletionResult(BaseModel):
    """任务删除结果"""
    status: TaskDeletionStatus = Field(..., description="整体删除结果状态")
    results: List[ResourceDeletionItem] = Field(..., description="分资源删除结果列表")
    warnings: Optional[List[str]] = Field(None, description="非阻断警告或重试提示")
    timestamp: str = Field(..., description="处理完成时间戳，ISO 8601")


# 错误响应模型
class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: Dict[str, Any] = Field(..., description="错误信息")
    
    @classmethod
    def create_error(cls, code: str, message: str, details: Optional[Dict] = None, task_id: Optional[str] = None):
        """创建错误响应"""
        error_dict = {
            "code": code,
            "message": message,
            "timestamp": "2025-11-16T17:45:00Z"  # 这里应该使用实际的时间
        }
        
        if details:
            error_dict["details"] = details
        
        if task_id:
            error_dict["task_id"] = task_id
            
        return cls(error=error_dict)
