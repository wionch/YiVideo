# services/api_gateway/app/file_operations.py
# -*- coding: utf-8 -*-

"""
文件操作API端点。

提供MinIO文件上传、下载、删除、列出等操作的API接口。
"""

import mimetypes
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import ValidationError

from services.common.logger import get_logger
from .minio_service import get_minio_service
from .single_task_models import (
    FileUploadRequest, FileUploadResponse, FileOperationResponse, 
    FileListResponse, FileListItem, ErrorResponse
)

logger = get_logger('file_operations')

# 创建路由器
router = APIRouter(prefix="/v1/files", tags=["File Operations"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    file_path: str = Query(..., description="文件在MinIO中的路径"),
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    上传文件到MinIO（流式上传优化版本）
    
    Args:
        file: 要上传的文件
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        FileUploadResponse: 上传结果
    """
    logger.info(f"开始流式上传文件: {file_path}, 桶: {bucket}, 文件大小: {file.size} bytes")
    
    try:
        # 验证请求参数
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path不能为空")
        
        # 验证文件名安全性（防止路径遍历攻击）
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 验证文件对象
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名为空")
        
        if not file.size or file.size == 0:
            raise HTTPException(status_code=400, detail="文件大小为0")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 使用流式上传（优化版本）
        result = minio_service.upload_file_stream(file, file_path, bucket)
        
        logger.info(f"文件流式上传成功: {file_path}, 实际大小: {result['size']} bytes")
        return FileUploadResponse(**result)
        
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        raise HTTPException(status_code=400, detail=f"参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    从MinIO下载文件
    
    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        文件二进制数据
    """
    logger.info(f"开始下载文件: {file_path}, 桶: {bucket}")
    
    try:
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 下载文件
        file_data = minio_service.download_file(file_path, bucket)
        
        # 推断MIME类型
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        logger.info(f"文件下载成功: {file_path}, 大小: {len(file_data)} bytes")
        
        # 返回文件数据
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_path.split("/")[-1]}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")


@router.delete("/{file_path:path}", response_model=FileOperationResponse)
async def delete_file(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    删除MinIO中的文件
    
    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        FileOperationResponse: 删除结果
    """
    logger.info(f"开始删除文件: {file_path}, 桶: {bucket}")
    
    try:
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 删除文件
        success = minio_service.delete_file(file_path, bucket)
        
        if success:
            message = f"文件删除成功: {file_path}"
            logger.info(message)
            return FileOperationResponse(
                success=True,
                message=message,
                file_path=file_path
            )
        else:
            message = f"文件删除失败: {file_path}"
            logger.warning(message)
            return FileOperationResponse(
                success=False,
                message=message,
                file_path=file_path
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")


@router.get("/list/{prefix:path}", response_model=FileListResponse)
async def list_files_with_prefix(
    prefix: str = "",
    bucket: Optional[str] = Query("yivideo", description="文件桶名称"),
    recursive: bool = Query(True, description="是否递归列出子目录")
):
    """
    列出MinIO中的文件（指定前缀）
    
    Args:
        prefix: 文件路径前缀
        bucket: 文件桶名称（默认yivideo）
        recursive: 是否递归列出子目录
        
    Returns:
        FileListResponse: 文件列表
    """
    logger.info(f"开始列出文件（指定前缀）: 前缀={prefix}, 桶={bucket}, 递归={recursive}")
    
    try:
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 列出文件
        files_info = minio_service.list_files(prefix, bucket, recursive)
        
        # 转换为响应格式
        file_items = [
            FileListItem(
                file_path=info["file_path"],
                size=info["size"],
                last_modified=info["last_modified"],
                etag=info["etag"],
                content_type=info["content_type"]
            )
            for info in files_info
        ]
        
        response = FileListResponse(
            prefix=prefix,
            bucket=bucket or "yivideo",
            files=file_items,
            total_count=len(file_items)
        )
        
        logger.info(f"文件列表获取成功: 找到 {len(file_items)} 个文件")
        return response
        
    except Exception as e:
        logger.error(f"文件列表获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件列表获取失败: {str(e)}")


# 新增路由：支持只使用查询参数的列表请求
@router.get("/list", response_model=FileListResponse)
async def list_files_no_prefix(
    bucket: Optional[str] = Query("yivideo", description="文件桶名称"),
    recursive: bool = Query(True, description="是否递归列出子目录")
):
    """
    列出MinIO中的文件（通过查询参数）
    
    Args:
        bucket: 文件桶名称（默认yivideo）
        recursive: 是否递归列出子目录
        
    Returns:
        FileListResponse: 文件列表
    """
    logger.info(f"开始列出文件（通过查询参数）: 桶={bucket}, 递归={recursive}")
    
    try:
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 列出文件（空前缀表示所有文件）
        files_info = minio_service.list_files("", bucket, recursive)
        
        # 转换为响应格式
        file_items = [
            FileListItem(
                file_path=info["file_path"],
                size=info["size"],
                last_modified=info["last_modified"],
                etag=info["etag"],
                content_type=info["content_type"]
            )
            for info in files_info
        ]
        
        response = FileListResponse(
            prefix="",
            bucket=bucket or "yivideo",
            files=file_items,
            total_count=len(file_items)
        )
        
        logger.info(f"文件列表获取成功: 找到 {len(file_items)} 个文件")
        return response
        
    except Exception as e:
        logger.error(f"文件列表获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件列表获取失败: {str(e)}")


@router.get("/exists/{file_path:path}")
async def check_file_exists(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    检查文件是否存在
    
    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        dict: 文件存在信息
    """
    logger.info(f"检查文件存在性: {file_path}, 桶: {bucket}")
    
    try:
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 检查文件存在性
        exists = minio_service.file_exists(file_path, bucket)
        
        return {
            "file_path": file_path,
            "bucket": bucket or "yivideo",
            "exists": exists
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查文件存在性失败: {e}")
        raise HTTPException(status_code=500, detail=f"检查文件存在性失败: {str(e)}")


@router.get("/url/{file_path:path}")
async def get_file_url(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称"),
    expires_hours: int = Query(24, description="链接有效期（小时）")
):
    """
    获取文件的预签名URL
    
    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        expires_hours: 链接有效期（小时）
        
    Returns:
        dict: 预签名URL信息
    """
    logger.info(f"获取文件URL: {file_path}, 桶: {bucket}, 有效期: {expires_hours}小时")
    
    try:
        from datetime import timedelta
        
        # 验证参数
        if expires_hours <= 0 or expires_hours > 168:  # 最多7天
            raise HTTPException(status_code=400, detail="有效期必须在1-168小时之间")
        
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 获取预签名URL
        url = minio_service.get_presigned_url(
            file_path, 
            bucket, 
            expires=timedelta(hours=expires_hours)
        )
        
        return {
            "file_path": file_path,
            "bucket": bucket or "yivideo",
            "download_url": url,
            "expires_in_hours": expires_hours
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件URL失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文件URL失败: {str(e)}")


@router.get("/health")
async def health_check():
    """
    文件服务健康检查
    
    Returns:
        dict: 健康状态信息
    """
    try:
        # 尝试获取MinIO服务实例
        minio_service = get_minio_service()
        
        # 简单检查：尝试列出根目录（不应该有太多文件）
        files = minio_service.list_files("", "yivideo", recursive=False)
        
        return {
            "status": "healthy",
            "minio_host": minio_service.host,
            "default_bucket": minio_service.default_bucket,
            "test_files_count": len(files)
        }
        
    except Exception as e:
        logger.error(f"文件服务健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


def get_file_operations_router():
    """获取文件操作路由器"""
    return router